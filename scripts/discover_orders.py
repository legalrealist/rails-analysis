#!/usr/bin/env python3
"""
EXPERIMENTAL — not part of the deploy pipeline and not run by
weekly_update.sh. CourtListener self-discovery was evaluated and found
to mostly re-surface orders the R&G feed already provides, so it isn't
used in production. Kept for reference. (Imports helpers from the
deprecated update_rg_data.py.)

Self-discovery of new AI court orders (judicial opinions) via CourtListener
full-text search — independent of the Ropes & Gray API.

Searches CourtListener for AI-misconduct keyword sets, dedupes against the
existing explorer_data.json, and writes new candidates to a review file.
Does NOT auto-merge — candidates are written for human review first, since
keyword search surfaces false positives (cases that merely mention AI).

Usage:
    python scripts/discover_orders.py                      # since last 60 days, dry-run preview
    python scripts/discover_orders.py --since 2026-05-01    # opinions filed on/after this date
    python scripts/discover_orders.py --write              # write candidates to data/discovered_candidates.json

Covers judicial opinions only (~74% of the dataset). Standing orders / local
rules / administrative orders are not in opinion databases and remain the
domain of the R&G / RAILS backstop (see update_rg_data.py).

API: https://www.courtlistener.com/api/rest/v4/search/
"""

import json, argparse, sys, time, re, urllib.request, urllib.parse, urllib.error
from pathlib import Path
from datetime import datetime, timedelta

# Reuse the CourtListener + dedup infrastructure from the R&G pipeline
sys.path.insert(0, str(Path(__file__).resolve().parent))
from update_rg_data import (        # noqa: E402
    _cl_api_get, _ssl_ctx, CL_API_KEY,
    make_match_key, format_date, DATA_FILE,
)

# Write candidates next to the resolved data file, so output tracks whichever
# tree DATA_FILE resolved to (source repo vs deployed site).
CANDIDATES_FILE = DATA_FILE.parent / "discovered_candidates.json"

CL_DELAY = 5  # seconds between API calls

# AI-misconduct keyword sets. Each runs as a separate full-text query.
KEYWORDS = [
    '"hallucinated citation"',
    '"hallucinated citations"',
    '"fabricated cases"',
    '"nonexistent cases"',
    '"fictitious authority"',
    '"fictitious cases"',
    '"artificial intelligence" "show cause"',
    '"generative artificial intelligence" sanctions',
    '"ChatGPT" "Rule 11"',
    '"AI-generated" citations sanctions',
]


def normalize_name(s: str) -> str:
    """Normalize a case name for fuzzy comparison."""
    s = (s or "").lower()
    s = re.sub(r'\bv\.?\b', 'v', s)
    s = re.sub(r'[^a-z0-9 ]', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def cl_fulltext_search(query: str, filed_after: str, page_size: int = 20) -> list[dict]:
    """Full-text opinion search. Returns raw result dicts."""
    params = {
        'type': 'o',
        'format': 'json',
        'q': query,
        'filed_after': filed_after,
        'order_by': 'dateFiled desc',
        'page_size': str(page_size),
    }
    url = f"https://www.courtlistener.com/api/rest/v4/search/?{urllib.parse.urlencode(params)}"
    for attempt in range(3):
        result = _cl_api_get(url)
        if result == 'RATE_LIMITED':
            wait = 30 * (2 ** attempt)
            print(f"  CL 429 → waiting {wait}s...")
            sys.stdout.flush()
            time.sleep(wait)
            continue
        if result and isinstance(result, dict):
            return result.get('results', [])
        return []
    return []


def cl_result_to_candidate(r: dict) -> dict:
    """Convert a CourtListener opinion search result → candidate record."""
    case_name = r.get('caseName', '')
    abs_url = r.get('absolute_url', '')
    link = f"https://www.courtlistener.com{abs_url}" if abs_url else ''
    date_filed = r.get('dateFiled', '') or ''
    # dateFiled is already YYYY-MM-DD; keep full precision
    date = date_filed[:10] if date_filed else ''
    snippet = ''
    opinions = r.get('opinions') or []
    if opinions and isinstance(opinions[0], dict):
        snippet = (opinions[0].get('snippet') or '')[:300]
    return {
        "name":    case_name,
        "judge":   r.get('judge', '') or '',
        "court":   r.get('court', '') or '',          # CL court display name
        "court_id": r.get('court_id', '') or '',
        "date":    date,
        "type":    "Judicial Opinion",
        "source":  "courtlistener",
        "link":    link,
        "summary": snippet,
        "_cl_cluster_id": r.get('cluster_id') or r.get('id'),
    }


def build_existing_indexes(existing: list[dict]):
    """Indexes for dedup: match keys + normalized case names."""
    keys = set()
    names = set()
    for rec in existing:
        keys.add(make_match_key(rec))
        nm = normalize_name(rec.get('name', ''))
        if nm:
            names.add(nm)
        # Also index case names embedded in summaries
        m = re.search(r'In\s+(.+?),\s+(?:No\.|\d{4})', rec.get('summary', ''))
        if m:
            names.add(normalize_name(m.group(1)))
    return keys, names


def is_new(candidate: dict, existing_keys: set, existing_names: set) -> bool:
    """True if the candidate is not already represented in the dataset."""
    if make_match_key(candidate) in existing_keys:
        return False
    cn = normalize_name(candidate.get('name', ''))
    if cn and cn in existing_names:
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="Discover new AI court opinions via CourtListener")
    default_since = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
    parser.add_argument("--since", default=default_since,
                        help="Only opinions filed on/after this date (YYYY-MM-DD). Default: 60 days ago.")
    parser.add_argument("--write", action="store_true",
                        help="Write candidates to discovered_candidates.json (default: dry-run preview)")
    parser.add_argument("--page-size", type=int, default=20, help="Results per keyword query")
    args = parser.parse_args()

    print(f"Loading existing data from {DATA_FILE}")
    with open(DATA_FILE) as f:
        existing = json.load(f)
    print(f"  {len(existing)} existing records")
    existing_keys, existing_names = build_existing_indexes(existing)

    if not CL_API_KEY:
        print("  WARNING: CL_API_KEY not set — limited to 50 requests/hour (unauthenticated is worse).")

    print(f"Searching CourtListener for opinions filed since {args.since}...")
    seen_clusters = set()
    candidates = []
    for kw in KEYWORDS:
        print(f"  q={kw}")
        sys.stdout.flush()
        results = cl_fulltext_search(kw, args.since, args.page_size)
        for r in results:
            cand = cl_result_to_candidate(r)
            cid = cand.get('_cl_cluster_id')
            if cid and cid in seen_clusters:
                continue
            if cid:
                seen_clusters.add(cid)
            if is_new(cand, existing_keys, existing_names):
                candidates.append(cand)
        time.sleep(CL_DELAY)

    # Dedupe candidates among themselves by normalized name + date
    unique = {}
    for c in candidates:
        k = (normalize_name(c['name']), c['date'])
        if k not in unique:
            unique[k] = c
    candidates = list(unique.values())
    candidates.sort(key=lambda c: c.get('date', ''), reverse=True)

    print(f"\n{'─'*50}")
    print(f"  New candidate opinions (not already in dataset): {len(candidates)}")
    print(f"{'─'*50}")
    for c in candidates[:25]:
        print(f"  {c['date'] or '????-??-??'} | {c['court'][:30]:30} | {c['name'][:50]}")
    if len(candidates) > 25:
        print(f"  ... and {len(candidates) - 25} more")

    if not args.write:
        print("\nDry run — pass --write to save candidates for review.")
        return

    with open(CANDIDATES_FILE, "w") as f:
        json.dump(candidates, f, indent=2, ensure_ascii=False)
    print(f"\n  Wrote {len(candidates)} candidates to {CANDIDATES_FILE}")
    print("  Review these before merging — keyword search surfaces false positives.")


if __name__ == "__main__":
    main()
