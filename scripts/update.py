#!/usr/bin/env python3
"""Incremental update for AI Court Orders Explorer.

Fetches from R&G's Sitecore API (ground truth), uses date-based cutoff
to find new entries, converts via OpenRouter AI, appends to dataset.
Runs CourtListener cross-check and refreshes bar opinions.

Usage:
    export OPENROUTER_API_KEY="your-key"
    export CL_API_KEY="your-key"          # optional
    python3 scripts/update.py
"""

import json
import os
import re
import ssl
import time
import urllib.request
import urllib.parse
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(PROJECT_DIR, 'data', 'processed')
CHARTS_DATA_DIR = os.path.join(PROJECT_DIR, 'charts', 'data')
RG_SOURCE_DIR = os.path.join(PROJECT_DIR, 'data', 'sources')
EXPLORER_PATH = os.path.join(DATA_DIR, 'explorer_data.json')
OPINIONS_PATH = os.path.join(DATA_DIR, 'bar_opinions.json')
CL_REVIEW_PATH = os.path.join(DATA_DIR, 'cl_review.json')

RG_API = 'https://www.ropesgray.com/sitecore/api/CourtOrder/search'
LAG_BASE = 'https://legalaigovernance.com/data'
CL_API_KEY = os.environ.get('CL_API_KEY', '')
OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY', '')
OPENROUTER_MODEL = os.environ.get('OPENROUTER_MODEL', 'deepseek/deepseek-v4-flash')

EXPLORER_SCHEMA_PROMPT = """You convert raw court order data from Ropes & Gray into a structured JSON object.

Output a single JSON object with these fields:

- "name": Clean display name. Use format "Court Abbreviation – Judge Title Name" (e.g. "D. Colo. – Judge Nina Y. Wang"). Strip pipe characters, state hierarchy prefixes, and parenthesized middle names. For supreme courts use full name like "Supreme Court of Montana – Chief Justice Cory James Swanson".
- "judge": Full judge name with title (e.g. "Judge Nina Y. Wang", "Chief Justice Cory James Swanson"). If multiple judges, join with " | ".
- "court": Court abbreviation or short name (e.g. "D. Colo.", "N.D. Ill.", "Supreme Court of Montana"). Use the most specific/abbreviated form from the court array.
- "state": Full state name (e.g. "Montana", "New York"). For DC variants use "District of Columbia". For empty state with federal circuit courts, use "Federal".
- "state_abbr": Standard 2-letter postal abbreviation (e.g. "MT", "NY", "DC", "PR", "GU", "MP"). Use "FED" for federal circuits with no state.
- "date": Format as "YYYY-MM" from the effectiveDate field. If effectiveDate is null or "0001-01-01", return "".
- "type": One of: "Standing Order", "Judicial Opinion", "Local Rules", "Administrative Order", "Practice Direction". Use "Judicial Opinion" if the summary describes a specific case (mentions parties, "v.", ruling). Use "Standing Order" for court-wide directives. Use "Local Rules" for rule amendments.
- "ai_type": "Any AI" if applicableTo includes "Any AI Usage", otherwise "Gen AI".
- "applies_to": Comma-separated from: "Attorneys", "Any Parties". Use "Attorneys" if consequences target attorneys/law firms. Use "Any Parties" if consequences target parties. Default to "Attorneys" if unclear.
- "summary": Plain text, no HTML tags. Preserve the substantive content.
- "reqs": Object with optional keys. Set "disclose": "checked" if applicableTo includes "Requires Disclosure and/or Verification". Set "prohibited": "checked" if "Prohibits Use of AI". Set "warning": "checked" if "Suggests Cautious Use of AI". Omit keys that don't apply.
- "consequence": One of: "" (empty string), "warning", "sanctions_attorney", "sanctions_party". Use "sanctions_attorney" if applicableTo includes "Court-Imposed Consequences - Attorneys/Law Firms". Use "sanctions_party" if it includes "Court-Imposed Consequences - Parties" (and no attorney consequences). Use "warning" if only "Suggests Cautious Use of AI" with no consequences tags. Default to "".

Also include these fields exactly as provided (do not modify):
- "applicableTo": Copy the array directly from the input
- "link": Copy from linkToCourtOrder.url
- "source": Always "rg"
- "jurisdiction": Always "US"

If consequence starts with "sanctions", also include:
- "sanction_types": {"types": [], "amount_sought": null, "amount_awarded": null}

Return ONLY the JSON object, no markdown fences or explanation."""


def _ssl_ctx():
    ctx = ssl.create_default_context()
    try:
        import certifi
        ctx.load_verify_locations(certifi.where())
    except ImportError:
        pass
    return ctx

SSL_CTX = _ssl_ctx()


def fetch_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'AI-Orders-Explorer/2.0'})
    with urllib.request.urlopen(req, timeout=60, context=SSL_CTX) as resp:
        return json.loads(resp.read().decode())


def strip_html(text):
    return re.sub(r'<[^>]+>', '', text).strip()


VALID_TYPES = {'Standing Order', 'Judicial Opinion', 'Local Rules', 'Administrative Order', 'Practice Direction'}
VALID_CONSEQUENCES = {'', 'warning', 'sanctions_attorney', 'sanctions_party'}


def validate_entry(entry):
    """Validate AI-generated entry. Returns (ok, errors) tuple."""
    errors = []
    for field in ('name', 'judge', 'court', 'state', 'date', 'type', 'summary'):
        if field not in entry or not isinstance(entry.get(field), str):
            errors.append(f'missing or invalid {field}')
    if entry.get('type') not in VALID_TYPES:
        errors.append(f'invalid type: {entry.get("type")}')
    if entry.get('consequence', '') not in VALID_CONSEQUENCES:
        errors.append(f'invalid consequence: {entry.get("consequence")}')
    d = entry.get('date', '')
    if d and not re.match(r'^\d{4}-\d{2}$', d):
        errors.append(f'invalid date format: {d}')
    sa = entry.get('state_abbr', '')
    if not sa or not re.match(r'^[A-Z]{2,3}$', sa):
        errors.append(f'invalid state_abbr: {sa}')
    if not isinstance(entry.get('reqs', {}), dict):
        errors.append('reqs is not a dict')
    if not isinstance(entry.get('applicableTo', []), list):
        errors.append('applicableTo is not a list')
    return (len(errors) == 0, errors)


def ai_convert_entry(item, idx):
    """Convert an R&G API entry to explorer schema using OpenRouter AI."""
    raw_json = json.dumps(item, indent=2)

    payload = json.dumps({
        'model': OPENROUTER_MODEL,
        'messages': [
            {'role': 'system', 'content': EXPLORER_SCHEMA_PROMPT},
            {'role': 'user', 'content': raw_json},
        ],
        'temperature': 0,
        'response_format': {'type': 'json_object'},
    }).encode()

    req = urllib.request.Request(
        'https://openrouter.ai/api/v1/chat/completions',
        data=payload,
        headers={
            'Authorization': f'Bearer {OPENROUTER_API_KEY}',
            'Content-Type': 'application/json',
            'User-Agent': 'AI-Orders-Explorer/2.0',
        },
    )

    with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as resp:
        result = json.loads(resp.read().decode())

    content = result['choices'][0]['message']['content']
    entry = json.loads(content)
    entry['id'] = idx
    return entry


def fallback_convert_entry(item, idx):
    """Regex-based fallback if AI conversion fails."""
    judges = item.get('judge', [])
    judge_str = ' | '.join(judges) if judges else ''

    courts = item.get('court', [])
    court_str = courts[-1].split(' - ', 1)[-1].strip() if courts else ''

    eff_date = item.get('effectiveDate', '')
    date_ym = eff_date[:7] if eff_date and not eff_date.startswith('0001') else ''

    categories = item.get('applicableTo', [])
    cat_set = set(categories)

    summary = strip_html(item.get('summary', ''))
    link_obj = item.get('linkToCourtOrder', {})
    link = link_obj.get('url', '')
    raw_name = link_obj.get('text', '')
    name = raw_name.split('|')[-1].strip()
    name = re.sub(r'\(([^)]*)\)', r'\1', name)
    name = re.sub(r'\s+', ' ', name).strip()

    st = item.get('state', '') or 'Federal'
    state_names = {
        'Alabama': 'AL', 'Alaska': 'AK', 'Arizona': 'AZ', 'Arkansas': 'AR',
        'California': 'CA', 'Colorado': 'CO', 'Connecticut': 'CT', 'Delaware': 'DE',
        'Florida': 'FL', 'Georgia': 'GA', 'Hawaii': 'HI', 'Idaho': 'ID',
        'Illinois': 'IL', 'Indiana': 'IN', 'Iowa': 'IA', 'Kansas': 'KS',
        'Kentucky': 'KY', 'Louisiana': 'LA', 'Maine': 'ME', 'Maryland': 'MD',
        'Massachusetts': 'MA', 'Michigan': 'MI', 'Minnesota': 'MN',
        'Mississippi': 'MS', 'Missouri': 'MO', 'Montana': 'MT', 'Nebraska': 'NE',
        'Nevada': 'NV', 'New Hampshire': 'NH', 'New Jersey': 'NJ',
        'New Mexico': 'NM', 'New York': 'NY', 'North Carolina': 'NC',
        'North Dakota': 'ND', 'Ohio': 'OH', 'Oklahoma': 'OK', 'Oregon': 'OR',
        'Pennsylvania': 'PA', 'Rhode Island': 'RI', 'South Carolina': 'SC',
        'South Dakota': 'SD', 'Tennessee': 'TN', 'Texas': 'TX', 'Utah': 'UT',
        'Vermont': 'VT', 'Virginia': 'VA', 'Washington': 'WA',
        'West Virginia': 'WV', 'Wisconsin': 'WI', 'Wyoming': 'WY',
        'District of Columbia': 'DC', 'D.C.': 'DC', 'Washington D.C.': 'DC',
        'Washington, DC': 'DC', 'Puerto Rico': 'PR',
        'Northern Mariana Islands': 'MP', 'Guam': 'GU',
    }
    if st in ('D.C.', 'Washington D.C.', 'Washington, DC'):
        st = 'District of Columbia'
    sa = state_names.get(st, 'FED' if st == 'Federal' else '')

    reqs = {}
    if 'Requires Disclosure and/or Verification' in cat_set:
        reqs['disclose'] = 'checked'
    if 'Prohibits Use of AI' in cat_set:
        reqs['prohibited'] = 'checked'
    if 'Suggests Cautious Use of AI' in cat_set:
        reqs['warning'] = 'checked'

    consequence = ''
    if 'Court-Imposed Consequences - Attorneys/Law Firms' in cat_set:
        consequence = 'sanctions_attorney'
    elif 'Court-Imposed Consequences - Parties' in cat_set:
        consequence = 'sanctions_party'
    elif 'Suggests Cautious Use of AI' in cat_set:
        consequence = 'warning'

    has_case = bool(re.search(r'\bv\.\s', summary))
    if has_case:
        entry_type = 'Judicial Opinion'
    else:
        entry_type = 'Standing Order'

    entry = {
        'id': idx,
        'name': name,
        'judge': judge_str,
        'court': court_str,
        'state': st,
        'date': date_ym,
        'type': entry_type,
        'source': 'rg',
        'link': link,
        'ai_type': 'Any AI' if 'Any AI Usage' in cat_set else 'Gen AI',
        'applies_to': 'Attorneys',
        'summary': summary,
        'reqs': reqs,
        'consequence': consequence,
        'applicableTo': categories,
        'jurisdiction': 'US',
        'state_abbr': sa,
    }
    if consequence.startswith('sanctions'):
        entry['sanction_types'] = {
            'types': [],
            'amount_sought': None,
            'amount_awarded': None,
        }
    return entry


def cl_search_recent(all_names, days=14):
    if not CL_API_KEY:
        print('  SKIP: CL_API_KEY not set.')
        return []

    after = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    queries = [
        '"artificial intelligence" "court order"',
        '"ChatGPT" sanctions',
        '"generative AI" disclosure',
    ]
    results = []
    seen_ids = set()
    name_norms = set(re.sub(r'[^a-z0-9]', '', n.lower()) for n in all_names)

    for q in queries:
        params = urllib.parse.urlencode({
            'q': q, 'type': 'o', 'filed_after': after,
            'order_by': 'dateFiled desc', 'page_size': 20,
        })
        url = f'https://www.courtlistener.com/api/rest/v4/search/?{params}'
        req = urllib.request.Request(url, headers={
            'Authorization': f'Token {CL_API_KEY}',
            'User-Agent': 'AI-Orders-Explorer/2.0',
        })
        try:
            with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as resp:
                data = json.loads(resp.read().decode())
        except Exception as e:
            print(f'  WARN: CL query failed: {e}')
            continue
        for r in data.get('results', []):
            rid = r.get('id') or r.get('cluster_id', '')
            if rid in seen_ids:
                continue
            seen_ids.add(rid)
            norm = re.sub(r'[^a-z0-9]', '', (r.get('caseName', '')).lower())
            already = any(norm[:20] in n or n[:20] in norm for n in name_norms if len(n) > 10)
            if not already:
                results.append({
                    'case_name': r.get('caseName', ''),
                    'court': r.get('court', ''),
                    'date': r.get('dateFiled', ''),
                    'url': f"https://www.courtlistener.com{r.get('absolute_url', '')}",
                    'snippet': (r.get('snippet', '') or '')[:200],
                    'cl_id': rid,
                })
        time.sleep(2)

    return results


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(CHARTS_DATA_DIR, exist_ok=True)
    os.makedirs(RG_SOURCE_DIR, exist_ok=True)

    print('=== AI Court Orders Explorer — Update ===')
    print(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    # 1. Load existing data
    if os.path.exists(EXPLORER_PATH):
        with open(EXPLORER_PATH) as f:
            existing = json.load(f)
    else:
        existing = []
    print(f'\nBaseline: {len(existing)} entries')

    max_date = max((e.get('date', '') for e in existing), default='')
    print(f'Latest date: {max_date or "(none)"}')

    existing_keys = set()
    for e in existing:
        existing_keys.add((e.get('date', ''), e.get('state', ''), e.get('judge', '')))

    # 2. Fetch R&G data from Sitecore API
    print('Fetching R&G Sitecore API...')
    rg_url = f'{RG_API}?page=0&take=2000&sc_lang=en&sc_site=main'
    rg_data = fetch_json(rg_url)
    rg_entries = rg_data.get('results', [])
    total_found = rg_data.get('totalFound', 0)
    print(f'R&G: {total_found} total, {len(rg_entries)} fetched')

    if total_found > 2000:
        print(f'  WARN: {total_found} total but only fetching 2000 — increase take param')
    if len(rg_entries) == 0 and total_found > 0:
        print(f'  ERROR: API returned 0 results but reports {total_found} total')
        return

    # Save raw API response
    rg_source_path = os.path.join(RG_SOURCE_DIR, 'ropes_gray_court_orders.json')
    with open(rg_source_path, 'w') as f:
        json.dump(rg_data, f, indent=2)

    # 3. Find new entries by date cutoff + dedup
    new_rg = []
    for item in rg_entries:
        eff_date = item.get('effectiveDate', '')
        if not eff_date or eff_date.startswith('0001'):
            continue
        date_ym = eff_date[:7]
        if date_ym >= max_date:
            judge_str = ' | '.join(item.get('judge', []))
            state = item.get('state', '') or 'Federal'
            if (date_ym, state, judge_str) not in existing_keys:
                new_rg.append(item)

    new_entries = []
    if not new_rg:
        print('\n0 new entries (all dates <= cutoff)')
    else:
        print(f'\n{len(new_rg)} candidates after {max_date}')

        # 4. Convert via AI (or fallback)
        use_ai = bool(OPENROUTER_API_KEY)
        if not use_ai:
            print('  OPENROUTER_API_KEY not set — using regex fallback')

        next_id = max((e.get('id', 0) for e in existing), default=-1) + 1
        for i, item in enumerate(new_rg):
            name_hint = item.get('linkToCourtOrder', {}).get('text', '')[:50]
            try:
                if use_ai:
                    entry = ai_convert_entry(item, next_id)
                    ok, errs = validate_entry(entry)
                    if not ok:
                        print(f'  WARN: AI output invalid ({", ".join(errs)}), using fallback')
                        entry = fallback_convert_entry(item, next_id)
                    print(f'  + [{i+1}/{len(new_rg)}] {entry.get("date","")}  {entry.get("name","")[:55]}')
                else:
                    entry = fallback_convert_entry(item, next_id)
                    print(f'  + [{i+1}/{len(new_rg)}] {entry.get("date","")}  {entry.get("name","")[:55]}')
                new_entries.append(entry)
                next_id += 1
                if use_ai and i < len(new_rg) - 1:
                    time.sleep(0.5)
            except Exception as e:
                print(f'  WARN: AI failed for {name_hint}: {e}')
                try:
                    entry = fallback_convert_entry(item, next_id)
                    new_entries.append(entry)
                    next_id += 1
                    print(f'    fallback OK: {entry.get("name","")[:55]}')
                except Exception as e2:
                    print(f'    fallback also failed: {e2}')

        # 5. Append, sort, re-index
        if new_entries:
            existing.extend(new_entries)
            existing.sort(key=lambda e: e.get('date', '') or '', reverse=True)
            for i, e in enumerate(existing):
                e['id'] = i

    # 6. Save (only if new entries were added)
    n_added = len(new_entries)
    if n_added:
        with open(EXPLORER_PATH, 'w') as f:
            json.dump(existing, f, indent=2)
        with open(os.path.join(DATA_DIR, 'explorer_data.json')) as src:
            with open(os.path.join(CHARTS_DATA_DIR, 'explorer_data.json'), 'w') as dst:
                dst.write(src.read())
        print(f'Saved: {len(existing)} total entries (+{n_added} new)')
    else:
        print(f'No changes: {len(existing)} total entries')

    # 7. Refresh bar opinions from legalaigovernance
    try:
        print('\nRefreshing bar opinions...')
        opinions = fetch_json(f'{LAG_BASE}/opinions.json')
        with open(OPINIONS_PATH, 'w') as f:
            json.dump(opinions, f, indent=2)
        with open(os.path.join(CHARTS_DATA_DIR, 'bar_opinions.json'), 'w') as f:
            json.dump(opinions, f, indent=2)
        n = len(opinions.get('items', opinions)) if isinstance(opinions, dict) else len(opinions)
        print(f'  {n} bar opinions saved')
    except Exception as e:
        print(f'  WARN: bar opinions refresh failed: {e}')

    # 8. CourtListener cross-check
    print('\nCourtListener cross-check...')
    all_names = [e.get('name', '') for e in existing]
    flagged = cl_search_recent(all_names)
    print(f'{len(flagged)} flagged for review')

    log_entry = {
        'timestamp': datetime.now().isoformat(),
        'new_added': n_added,
        'total': len(existing),
        'rg_total': len(rg_entries),
        'flagged': flagged,
    }
    review_log = []
    if os.path.exists(CL_REVIEW_PATH):
        try:
            with open(CL_REVIEW_PATH) as f:
                review_log = json.load(f)
            if isinstance(review_log, dict):
                review_log = [review_log]
        except (json.JSONDecodeError, KeyError):
            pass
    review_log.append(log_entry)
    with open(CL_REVIEW_PATH, 'w') as f:
        json.dump(review_log, f, indent=2)

    if flagged:
        for fl in flagged:
            print(f'  ! {fl["case_name"]} ({fl["date"]})')
    print(f'Log: {CL_REVIEW_PATH}')
    print(f'\nDone: +{n_added} new, {len(existing)} total')


if __name__ == '__main__':
    main()
