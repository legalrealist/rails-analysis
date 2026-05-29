#!/usr/bin/env python3
"""
DEPRECATED — not the canonical pipeline. `scripts/update.py` is the
canonical R&G → explorer_data pipeline (run by scripts/weekly_update.sh)
and already includes the dedup / full-date fixes from this script.
Kept for reference only; do not run for production updates.

Fetch court orders from the Ropes & Gray AI Court Order Tracker API
and merge them into explorer_data.json.

Usage:
    python scripts/update_rg_data.py                  # dry-run (prints diff stats)
    python scripts/update_rg_data.py --write           # writes updated explorer_data.json
    python scripts/update_rg_data.py --write --backup   # backs up before writing

API: https://www.ropesgray.com/sitecore/api/CourtOrder/search
"""

import json, argparse, shutil, sys, time, re, os, urllib.request, urllib.parse, urllib.error, ssl
from pathlib import Path
from datetime import datetime

try:
    import requests
except ImportError:
    sys.exit("Install requests: pip install requests")

# ── SSL context for CourtListener API ────────────────────────────────────────
_ssl_ctx = ssl.create_default_context()
try:
    import certifi
    _ssl_ctx.load_verify_locations(certifi.where())
except ImportError:
    _ssl_ctx.check_hostname = False
    _ssl_ctx.verify_mode = ssl.CERT_NONE

# ── paths ────────────────────────────────────────────────────────────────────
# The data file lives in different places depending on the tree:
#   - source repo (AI-orders-explorer):  data/processed/explorer_data.json
#   - deployed Grav site (legalhack):     public_html/assets/data/explorer_data.json
# Resolve robustly so the script works from either, and allow an explicit override
# via the EXPLORER_DATA env var. Prefers an existing file; falls back to the repo layout.
REPO_ROOT = Path(__file__).resolve().parent.parent
_DATA_CANDIDATES = [
    REPO_ROOT / "data" / "processed" / "explorer_data.json",          # source repo
    REPO_ROOT / "public_html" / "assets" / "data" / "explorer_data.json",  # deployed site
]
if "EXPLORER_DATA" in __import__("os").environ:
    DATA_FILE = Path(__import__("os").environ["EXPLORER_DATA"])
else:
    DATA_FILE = next((p for p in _DATA_CANDIDATES if p.exists()), _DATA_CANDIDATES[0])

# ── Ropes & Gray API ─────────────────────────────────────────────────────────
RG_API     = "https://www.ropesgray.com/sitecore/api/CourtOrder/search"
PAGE_SIZE  = 100          # max items per request

# ── US state name → abbreviation ─────────────────────────────────────────────
STATE_ABBR = {
    "Alabama":"AL","Alaska":"AK","Arizona":"AZ","Arkansas":"AR","California":"CA",
    "Colorado":"CO","Connecticut":"CT","D.C.":"DC","Delaware":"DE",
    "District of Columbia":"DC","Florida":"FL","Georgia":"GA","Hawaii":"HI",
    "Idaho":"ID","Illinois":"IL","Indiana":"IN","Iowa":"IA","Kansas":"KS",
    "Kentucky":"KY","Louisiana":"LA","Maine":"ME","Maryland":"MD",
    "Massachusetts":"MA","Michigan":"MI","Minnesota":"MN","Mississippi":"MS",
    "Missouri":"MO","Montana":"MT","Nebraska":"NE","Nevada":"NV",
    "New Hampshire":"NH","New Jersey":"NJ","New Mexico":"NM","New York":"NY",
    "North Carolina":"NC","North Dakota":"ND","Ohio":"OH","Oklahoma":"OK",
    "Oregon":"OR","Pennsylvania":"PA","Rhode Island":"RI","South Carolina":"SC",
    "South Dakota":"SD","Tennessee":"TN","Texas":"TX","Utah":"UT","Vermont":"VT",
    "Virginia":"VA","Washington":"WA","West Virginia":"WV","Wisconsin":"WI",
    "Wyoming":"WY","Puerto Rico":"PR","Guam":"GU","U.S. Virgin Islands":"VI",
    "American Samoa":"AS","Northern Mariana Islands":"MP",
}

# ── CourtListener search infrastructure ──────────────────────────────────────
CL_API_KEY = os.environ.get("CL_API_KEY", "")
CL_DELAY   = 5    # seconds between API calls

CL_COURT_MAP = {
    'D. Or.': 'ord', 'E.D. Mich.': 'mied', 'W.D. Mich.': 'miwd',
    'E.D. Tex.': 'txed', 'C.D. Cal.': 'cacd', 'S.D. Fla.': 'flsd',
    'N.D. Ill.': 'ilnd', 'C.D. Ill.': 'ilcd', 'S.D. Ill.': 'ilsd',
    'S.D.N.Y.': 'nysd', 'E.D.N.Y.': 'nyed', 'N.D. Cal.': 'cand',
    'E.D. Cal.': 'caed', 'S.D. Cal.': 'casd',
    'D.N.J.': 'njd', 'E.D. Pa.': 'paed', 'W.D. Pa.': 'pawd', 'M.D. Pa.': 'pamd',
    'D. Md.': 'mdd', 'S.D. Tex.': 'txsd', 'N.D. Tex.': 'txnd', 'W.D. Tex.': 'txwd',
    'D. Ariz.': 'azd', 'D. Colo.': 'cod', 'D. Conn.': 'ctd',
    'M.D. Fla.': 'flmd', 'N.D. Fla.': 'flnd',
    'S.D. Ind.': 'insd', 'N.D. Ind.': 'innd',
    'D. Kan.': 'ksd', 'E.D. La.': 'laed', 'W.D. La.': 'lawd', 'M.D. La.': 'lamd',
    'D. Mass.': 'mad', 'D. Minn.': 'mnd',
    'S.D. Miss.': 'mssd', 'N.D. Miss.': 'msnd',
    'E.D. Mo.': 'moed', 'W.D. Mo.': 'mowd',
    'D. Nev.': 'nvd', 'D.N.M.': 'nmd',
    'W.D.N.Y.': 'nywd', 'N.D.N.Y.': 'nynd',
    'M.D.N.C.': 'ncmd', 'W.D.N.C.': 'ncwd', 'E.D.N.C.': 'nced',
    'N.D. Ohio': 'ohnd', 'S.D. Ohio': 'ohsd',
    'W.D. Okla.': 'okwd', 'E.D. Okla.': 'oked', 'N.D. Okla.': 'oknd',
    'D.S.C.': 'scd',
    'M.D. Tenn.': 'tnmd', 'W.D. Tenn.': 'tnwd', 'E.D. Tenn.': 'tned',
    'E.D. Va.': 'vaed', 'W.D. Va.': 'vawd',
    'E.D. Wis.': 'wied', 'W.D. Wis.': 'wiwd',
    'D. Utah': 'utd', 'D.D.C.': 'dcd',
    'M.D. Ga.': 'gamd', 'N.D. Ga.': 'gand', 'S.D. Ga.': 'gasd',
    'D. Haw.': 'hid',
    'S.D. Ala.': 'alsd', 'S.D. Ala': 'alsd',
    'M.D. Ala.': 'almd', 'N.D. Ala.': 'alnd',
    'E.D. Ark.': 'ared', 'W.D. Ark.': 'arwd',
    'D. Del.': 'ded', 'D. Idaho': 'idd',
    'S.D. Iowa': 'iasd', 'N.D. Iowa': 'iand',
    'E.D. Ky.': 'kyed', 'W.D. Ky.': 'kywd',
    'D. Me.': 'med', 'D. Mont.': 'mtd', 'D. Neb.': 'ned', 'D.N.H.': 'nhd',
    'D.R.I.': 'rid', 'D.S.D.': 'sdd', 'D. Vt.': 'vtd',
    'E.D. Wash.': 'waed', 'W.D. Wash.': 'wawd',
    'S.D.W. Va.': 'wvsd', 'N.D.W. Va.': 'wvnd',
    'D. Wyo.': 'wyd', 'D.V.I.': 'vid',
    'Bankr. D. Colo.': 'cob',
    '1st Cir.': 'ca1', '2d Cir.': 'ca2', '2nd Cir.': 'ca2',
    '3d Cir.': 'ca3', '3rd Cir.': 'ca3', '4th Cir.': 'ca4',
    '5th Cir.': 'ca5', '6th Cir.': 'ca6', '7th Cir.': 'ca7',
    '8th Cir.': 'ca8', '9th Cir.': 'ca9', '10th Cir.': 'ca10',
    '11th Cir.': 'ca11', 'D.C. Cir.': 'cadc', 'Fed. Cir.': 'cafc',
    'Fed. Cl.': 'uscfc', 'Tax Ct.': 'tax',
    'Del. Ch.': 'dech', 'N.Y. Sup. Ct.': 'nysupct',
    'Ind. Ct. App.': 'indctapp', 'Cal. Ct. App.': 'calctapp',
    'Or. Ct. App.': 'orctapp', 'Md. App. Ct.': 'mdctspecapp',
    'Mo. Ct. App.': 'moctapp', 'Ill. App. Ct.': 'illappct',
    'Ga. Ct. App.': 'gactapp',
}


def _cl_get_court_id(court_str):
    if not court_str:
        return None
    if court_str in CL_COURT_MAP:
        return CL_COURT_MAP[court_str]
    for key, val in sorted(CL_COURT_MAP.items(), key=lambda x: -len(x[0])):
        if key in court_str:
            return val
    return None


def _cl_extract_case_name(entry):
    summary = entry.get('summary', '')
    name = entry.get('name', '')
    m = re.search(r'In\s+(.+?),\s+(?:No\.|the |Judge |Chief |Magistrate |\d{4})', summary)
    if m:
        cn = m.group(1).strip()
        cn = re.sub(r'\s*\d{4}\s+(?:U\.S\.|Fla\.|N\.C\.|Ill\.|Cal\.|Or\.|Ind\.|Mont\.).*$', '', cn)
        if len(cn) > 5:
            return cn
    m = re.search(r'In\s+(.+?),', summary)
    if m:
        cn = m.group(1).strip()
        if ' v. ' in cn or ' v ' in cn:
            cn = re.sub(r'\s*\d{4}\s+(?:U\.S\.|Fla\.|N\.C\.).*$', '', cn)
            if len(cn) > 5:
                return cn
    if name and (' v. ' in name or ' v ' in name):
        return name.strip()
    return None


def _cl_extract_docket_number(entry):
    summary = entry.get('summary', '')
    m = re.search(r'No\.\s*(\d+:\d+-(?:cv|cr|mc|mj)-\d+)', summary)
    if m:
        return m.group(1)
    m = re.search(r'(\d+:\d+-(?:cv|cr|mc|mj)-\d+)', summary)
    if m:
        return m.group(1)
    return None


def _cl_api_get(url):
    headers = {'User-Agent': 'legalhack-update/1.0'}
    if CL_API_KEY:
        headers['Authorization'] = f'Token {CL_API_KEY}'
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=_ssl_ctx, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 429:
            return 'RATE_LIMITED'
        return None
    except Exception:
        return None


def _cl_search(search_type, case_name=None, docket_number=None, court_id=None):
    params = {'type': search_type, 'format': 'json', 'page_size': '3'}
    if search_type == 'd':
        if docket_number:
            params['docket_number'] = docket_number
        if case_name:
            params['case_name'] = case_name
        if court_id:
            params['court'] = court_id
    else:
        if case_name:
            params['case_name'] = case_name
        if court_id:
            params['court'] = court_id

    url = f"https://www.courtlistener.com/api/rest/v4/search/?{urllib.parse.urlencode(params)}"

    for attempt in range(3):
        result = _cl_api_get(url)
        if result == 'RATE_LIMITED':
            wait = 30 * (2 ** attempt)
            print(f"    CL 429 → waiting {wait}s...")
            sys.stdout.flush()
            time.sleep(wait)
            continue
        if result and isinstance(result, dict) and result.get('results'):
            r = result['results'][0]
            if search_type == 'd':
                docket_url = r.get('docket_absolute_url', '')
                if docket_url:
                    return f"https://www.courtlistener.com{docket_url}", r.get('caseName', '')
                did = r.get('docket_id')
                if did:
                    slug = re.sub(r'[^a-z0-9-]', '', r.get('caseName', '').lower().replace(' ', '-'))[:50]
                    return f"https://www.courtlistener.com/docket/{did}/{slug}/", r.get('caseName', '')
            else:
                abs_url = r.get('absolute_url', '')
                if abs_url:
                    return f"https://www.courtlistener.com{abs_url}", r.get('caseName', '')
        return None, None
    return None, None


def replace_lexis_with_cl(records):
    """Search CourtListener for free links to replace Lexis links in new records.

    Mutates records in-place. Returns count of replacements made.
    """
    lexis_entries = [(i, r) for i, r in enumerate(records)
                     if r.get('link', '').startswith('https://advance.lexis.com')]
    if not lexis_entries:
        return 0

    print(f"\n  Searching CourtListener for {len(lexis_entries)} Lexis-linked entries...")
    replaced = 0

    for seq, (i, entry) in enumerate(lexis_entries):
        case_name = _cl_extract_case_name(entry)
        docket_num = _cl_extract_docket_number(entry)
        court_id = _cl_get_court_id(entry.get('court', ''))

        label = (entry.get('name', '') or '')[:50]
        sys.stdout.write(f"    [{seq+1}/{len(lexis_entries)}] {label} ")
        sys.stdout.flush()

        found_url = None

        # Strategy 1: docket number search
        if docket_num and not found_url:
            url, name = _cl_search('d', docket_number=docket_num, court_id=court_id)
            if url:
                found_url = url
                print(f"→ docket: {(name or '')[:40]}")
            time.sleep(CL_DELAY)

        # Strategy 2: docket search by case name + court
        if case_name and court_id and not found_url:
            url, name = _cl_search('d', case_name=case_name, court_id=court_id)
            if url:
                found_url = url
                print(f"→ case+court: {(name or '')[:40]}")
            time.sleep(CL_DELAY)

        # Strategy 3: opinion search with court
        if case_name and not found_url:
            url, name = _cl_search('o', case_name=case_name, court_id=court_id)
            if url:
                found_url = url
                print(f"→ opinion: {(name or '')[:40]}")
            time.sleep(CL_DELAY)

        # Strategy 4: opinion search without court
        if case_name and court_id and not found_url:
            url, name = _cl_search('o', case_name=case_name)
            if url:
                found_url = url
                print(f"→ broad: {(name or '')[:40]}")
            time.sleep(CL_DELAY)

        if found_url:
            records[i]['link'] = found_url
            replaced += 1
        else:
            print("✗")

    print(f"  CL search complete: {replaced}/{len(lexis_entries)} Lexis links replaced")
    return replaced


# ── helpers ──────────────────────────────────────────────────────────────────

def fetch_all_rg_orders() -> list[dict]:
    """Page through the RG API and return all court order objects."""
    all_items = []
    page = 0
    total = None
    while True:
        params = {"page": page, "take": PAGE_SIZE, "sc_lang": "en", "sc_site": "main"}
        resp = requests.get(RG_API, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if total is None:
            total = data.get("totalFound", 0)
            print(f"  RG API reports {total} total orders")
        results = data.get("results", [])
        if not results:
            break
        all_items.extend(results)
        if total and len(all_items) >= total:
            break
        print(f"  fetched page {page} ({len(all_items)}/{total})")
        page += 1
        time.sleep(0.3)          # polite pause
    return all_items


def guess_type(title: str, applicable_to: list[str]) -> str:
    """Heuristically classify the order type from its title/tags."""
    t = title.lower()
    sanctions_tags = [
        "Court-Imposed Consequences",
        "Sanctions",
    ]
    if any(s.lower() in a.lower() for a in applicable_to for s in sanctions_tags):
        # could be a judicial opinion with sanctions
        pass
    if "standing order" in t:
        return "Standing Order"
    if "local rule" in t or "local rules" in t:
        return "Local Rules"
    if "administrative order" in t:
        return "Administrative Order"
    if "practice direction" in t:
        return "Practice Direction"
    # default
    return "Judicial Opinion"


def guess_ai_type(applicable_to: list[str]) -> str:
    """Infer ai_type from applicableTo tags."""
    tags_lower = [a.lower() for a in applicable_to]
    if any("generative" in t for t in tags_lower):
        return "Gen AI"
    return "Any AI"


def extract_applies_to(applicable_to: list[str]) -> str:
    """Map applicableTo tags → applies_to string."""
    parts = []
    tags_lower = [a.lower() for a in applicable_to]
    if any("attorney" in t or "law firm" in t for t in tags_lower):
        parts.append("Attorneys")
    if any("pro se" in t or "self-rep" in t for t in tags_lower):
        parts.append("Pro Se Litigants")
    if any("parties" in t for t in tags_lower):
        parts.append("Parties")
    return ",".join(parts) if parts else "Attorneys"


def format_date(iso_date: str | None) -> str:
    """Convert '2026-05-08T00:00:00Z' → '2026-05-08'."""
    if not iso_date:
        return ""
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return ""


def build_name(rg: dict) -> str:
    """Build a display name from state, court, judge."""
    courts = rg.get("court", [])
    judges = rg.get("judge", [])
    court_str = courts[0] if courts else ""
    judge_str = judges[0] if judges else ""
    state = rg.get("state", "")

    # Use the link text if present and meaningful
    link_text = (rg.get("linkToCourtOrder") or {}).get("text", "")
    if link_text and len(link_text) > 10 and len(link_text) < 200:
        # Take segment after last pipe if present, strip parentheses from name parts
        if "|" in link_text:
            link_text = link_text.rsplit("|", 1)[-1].strip()
        link_text = re.sub(r'[()]', '', link_text).replace('  ', ' ').strip()
        return link_text

    parts = [p for p in [state, court_str, judge_str] if p]
    return " - ".join(parts) if parts else "Unknown"


def build_link(rg: dict) -> str:
    """Build a link URL — prefer state page on RG site."""
    state = rg.get("state", "")
    link_obj = rg.get("linkToCourtOrder") or {}
    link_url = link_obj.get("url", "")
    if link_url:
        return link_url
    if state:
        slug = state.lower().replace(" ", "-").replace(".", "")
        return f"https://www.ropesgray.com/en/sites/artificial-intelligence-court-order-tracker/states/{slug}"
    return ""


def rg_to_explorer(rg: dict) -> dict:
    """Convert a single RG API record → explorer_data.json schema."""
    applicable_to = rg.get("applicableTo", [])
    state = rg.get("state", "")
    courts = rg.get("court", [])
    judges = rg.get("judge", [])
    name = build_name(rg)
    order_type = guess_type(name, applicable_to)

    # RG API prefixes court with "State - " or "Nth Circuit - "; take segment after last " - "
    raw_court = courts[-1] if courts else ""
    court_clean = raw_court.rsplit(" - ", 1)[-1].strip() if " - " in raw_court else raw_court

    # Filter garbage from judge list (API sometimes includes court names, tags like "Warning")
    clean_judges = [j for j in judges if re.search(r'Judge|Justice|Magistrate|Chief', j)]
    if not clean_judges:
        clean_judges = judges

    return {
        # id gets assigned during merge
        "name":             name,
        "judge":            " | ".join(clean_judges) if clean_judges else "",
        "court":            court_clean,
        "state":            state,
        "date":             format_date(rg.get("effectiveDate")),
        "type":             order_type,
        "source":           "rg",
        "link":             build_link(rg),
        "ai_type":          guess_ai_type(applicable_to),
        "applies_to":       extract_applies_to(applicable_to),
        "summary":          rg.get("summary", ""),
        "reqs":             {},          # RG API doesn't expose granular reqs
        "applicableTo":     applicable_to,
        "jurisdiction":     "US",
        "state_abbr":       STATE_ABBR.get(state, ""),
        "sanctions_outcome": "",
        "_rg_id":           rg.get("id", ""),   # keep RG UUID for dedup
    }


def make_match_key(rec: dict) -> str:
    """Fingerprint for dedup: lowercase judge + court + date."""
    judge = rec.get("judge", "").lower().strip()
    court = rec.get("court", "").lower().strip()
    date  = rec.get("date", "").strip()
    return f"{judge}|{court}|{date}"


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Update explorer_data.json from Ropes & Gray API")
    parser.add_argument("--write",  action="store_true", help="Write updated JSON (default: dry-run)")
    parser.add_argument("--backup", action="store_true", help="Backup existing file before writing")
    parser.add_argument("--dump-new", action="store_true", help="Print new records to stdout")
    parser.add_argument("--skip-cl", action="store_true", help="Skip CourtListener link replacement")
    args = parser.parse_args()

    # 1. Load existing data
    print(f"Loading existing data from {DATA_FILE}")
    with open(DATA_FILE) as f:
        existing = json.load(f)
    print(f"  {len(existing)} existing records")

    # 2. Build match-key index of existing records
    existing_keys = {}
    for rec in existing:
        key = make_match_key(rec)
        existing_keys[key] = rec

    # Also index by _rg_id if present (from previous runs)
    rg_id_index = {}
    for rec in existing:
        if rec.get("_rg_id"):
            rg_id_index[rec["_rg_id"]] = rec

    # 3. Fetch from RG
    print("Fetching from Ropes & Gray API...")
    rg_raw = fetch_all_rg_orders()
    print(f"  {len(rg_raw)} records fetched")

    # 4. Convert & merge
    latest_date = max((r.get("date", "") for r in existing), default="")
    new_records = []
    updated = 0
    skipped = 0
    for rg in rg_raw:
        converted = rg_to_explorer(rg)
        rg_id = converted["_rg_id"]

        # Check if already exists by RG UUID
        if rg_id and rg_id in rg_id_index:
            # Update summary if it changed
            ex = rg_id_index[rg_id]
            if converted["summary"] and converted["summary"] != ex.get("summary"):
                ex["summary"] = converted["summary"]
                updated += 1
            skipped += 1
            continue

        # Check by match key (try full date, then YYYY-MM for backward compat)
        key = make_match_key(converted)
        month_key = key.rsplit("|", 1)[0] + "|" + converted["date"][:7] if len(converted["date"]) > 7 else None
        matched_key = key if key in existing_keys else (month_key if month_key and month_key in existing_keys else None)
        if matched_key:
            ex = existing_keys[matched_key]
            if rg_id and not ex.get("_rg_id"):
                ex["_rg_id"] = rg_id
            if len(converted["date"]) > len(ex.get("date", "")):
                ex["date"] = converted["date"]
            skipped += 1
            continue

        # Skip older unmatched entries — likely API format noise, not genuinely new
        if converted["date"] < latest_date:
            skipped += 1
            continue

        new_records.append(converted)

    # 5. Assign IDs and append
    max_id = max((r.get("id", 0) for r in existing), default=-1)
    for i, rec in enumerate(new_records):
        rec["id"] = max_id + 1 + i

    # 5b. Replace Lexis links with free CourtListener links (new records only)
    if new_records and not args.skip_cl:
        replace_lexis_with_cl(new_records)

    merged = existing + new_records

    # 6. Report
    print(f"\n{'─'*50}")
    print(f"  Existing:   {len(existing)}")
    print(f"  RG fetched: {len(rg_raw)}")
    print(f"  Skipped (already present): {skipped}")
    print(f"  Updated summaries:         {updated}")
    print(f"  NEW records to add:        {len(new_records)}")
    print(f"  Total after merge:         {len(merged)}")
    print(f"{'─'*50}")

    if args.dump_new and new_records:
        print("\n=== NEW RECORDS ===")
        for r in new_records[:10]:
            print(f"  [{r['id']}] {r['name'][:80]}  ({r['state']}, {r['date']})")
        if len(new_records) > 10:
            print(f"  ... and {len(new_records) - 10} more")

    if not args.write:
        print("\nDry run — pass --write to save. Pass --dump-new to preview new records.")
        return

    # 7. Write
    if args.backup:
        backup = DATA_FILE.with_suffix(f".bak-{datetime.now():%Y%m%d-%H%M%S}.json")
        shutil.copy2(DATA_FILE, backup)
        print(f"  Backed up to {backup}")

    with open(DATA_FILE, "w") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    print(f"  Wrote {len(merged)} records to {DATA_FILE}")


if __name__ == "__main__":
    main()
