#!/usr/bin/env python3
"""Batch search CourtListener for free links — final version.

Properly rate-limited (12s between requests, exponential backoff on 429).
Searches dockets first (federal), then opinions (all).
Covers all federal courts including previously missing ones.
"""

import os
import json, re, time, sys, urllib.request, urllib.parse, urllib.error, ssl

ssl_ctx = ssl.create_default_context()
try:
    import certifi
    ssl_ctx.load_verify_locations(certifi.where())
except ImportError:
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

API_KEY = os.environ.get("CL_API_KEY", "")
BASE = "/Users/hao/ClaudeCode/rails-analysis"
DATA_FILE = f"{BASE}/data/processed/explorer_data.json"
OUTPUT_FILE = f"{BASE}/data/processed/cl_links.json"

DELAY = 20  # seconds between API calls — conservative to avoid 429s

with open(DATA_FILE) as f:
    data = json.load(f)

try:
    with open(OUTPUT_FILE) as f:
        found = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    found = {}

# Complete court mapping — federal + state courts CourtListener knows
COURT_MAP = {
    # District courts
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
    'S.D. Ala.': 'alsd', 'S.D. Ala': 'alsd',  # handle missing period
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
    # Bankruptcy
    'Bankr. D. Colo.': 'cob',
    # Circuit courts
    '1st Cir.': 'ca1', '2d Cir.': 'ca2', '2nd Cir.': 'ca2',
    '3d Cir.': 'ca3', '3rd Cir.': 'ca3', '4th Cir.': 'ca4',
    '5th Cir.': 'ca5', '6th Cir.': 'ca6', '7th Cir.': 'ca7',
    '8th Cir.': 'ca8', '9th Cir.': 'ca9', '10th Cir.': 'ca10',
    '11th Cir.': 'ca11', 'D.C. Cir.': 'cadc', 'Fed. Cir.': 'cafc',
    # Special courts
    'Fed. Cl.': 'uscfc', 'Tax Ct.': 'tax',
    # State courts CL knows about
    'Del. Ch.': 'dech',
    'N.Y. Sup. Ct.': 'nysupct',
    'Ind. Ct. App.': 'indctapp',
    'Cal. Ct. App.': 'calctapp',
    'Or. Ct. App.': 'orctapp',
    'Md. App. Ct.': 'mdctspecapp',
    'Mo. Ct. App.': 'moctapp',
    'Ill. App. Ct.': 'illappct',
    'Ga. Ct. App.': 'gactapp',
}


def get_court_id(court_str):
    """Map court string to CL court ID."""
    if not court_str:
        return None
    # Exact match first
    if court_str in COURT_MAP:
        return COURT_MAP[court_str]
    # Partial match
    for key, val in sorted(COURT_MAP.items(), key=lambda x: -len(x[0])):
        if key in court_str:
            return val
    return None


def extract_case_name(entry):
    """Extract case name from summary or name field."""
    summary = entry.get('summary', '')
    name = entry.get('name', '')
    m = re.search(r'In\s+(.+?),\s+(?:No\.|the |Judge |Chief |Magistrate |\d{4})', summary)
    if m:
        cn = m.group(1).strip()
        cn = re.sub(r'\s*\d{4}\s+(?:U\.S\.|Fla\.|N\.C\.|Ill\.|Cal\.|Or\.|Ind\.).*$', '', cn)
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


def extract_docket_number(entry):
    """Extract federal docket number from summary."""
    summary = entry.get('summary', '')
    # Standard federal: 2:25-cv-01294
    m = re.search(r'No\.\s*(\d+:\d+-(?:cv|cr|mc|mj)-\d+)', summary)
    if m:
        return m.group(1)
    m = re.search(r'(\d+:\d+-(?:cv|cr|mc|mj)-\d+)', summary)
    if m:
        return m.group(1)
    return None


def api_get(url):
    """Single API request. Returns parsed JSON or None. No retry — caller handles that."""
    try:
        req = urllib.request.Request(url, headers={
            'Authorization': f'Token {API_KEY}',
            'User-Agent': 'rails-analysis/2.0',
        })
        with urllib.request.urlopen(req, context=ssl_ctx, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 429:
            return 'RATE_LIMITED'
        elif e.code == 400:
            return None
        else:
            print(f"HTTP {e.code}", end=' ')
            return None
    except Exception as e:
        print(f"ERR:{e}", end=' ')
        return None


def cl_search(search_type, case_name=None, docket_number=None, court_id=None):
    """Search CL. Returns (url, name) or (None, None). Retries on 429 with backoff."""
    params = {'type': search_type, 'format': 'json', 'page_size': '3'}

    if search_type == 'd':
        if docket_number:
            params['docket_number'] = docket_number
        if case_name:
            params['case_name'] = case_name
        if court_id:
            params['court'] = court_id
    else:  # opinions
        if case_name:
            params['case_name'] = case_name
        if court_id:
            params['court'] = court_id

    url = f"https://www.courtlistener.com/api/rest/v4/search/?{urllib.parse.urlencode(params)}"

    for attempt in range(3):
        result = api_get(url)

        if result == 'RATE_LIMITED':
            wait = 30 * (2 ** attempt)
            print(f"429->wait {wait}s", end=' ')
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


def save():
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(found, f, indent=2)


# === Build work list ===
lexis_remaining = [i for i, d in enumerate(data)
                   if d.get('link', '').startswith('https://advance.lexis.com')
                   and str(i) not in found]

work = []
for idx in lexis_remaining:
    entry = data[idx]
    case_name = extract_case_name(entry)
    docket_num = extract_docket_number(entry)
    court_id = get_court_id(entry.get('court', ''))
    work.append({
        'idx': idx,
        'case_name': case_name,
        'docket': docket_num,
        'court_id': court_id,
        'court_raw': entry.get('court', ''),
    })

# Sort: docket number first, then federal by case name, then state
work.sort(key=lambda w: (
    0 if w['docket'] else 1,
    0 if w['court_id'] else 1,
))

with_docket = sum(1 for w in work if w['docket'])
with_court = sum(1 for w in work if w['court_id'])
with_name = sum(1 for w in work if w['case_name'])
print(f"Work items: {len(work)}")
print(f"  With docket#: {with_docket}")
print(f"  With CL court ID: {with_court}")
print(f"  With case name: {with_name}")
print(f"  Delay: {DELAY}s between requests")
est_minutes = len(work) * DELAY * 1.5 / 60  # ~1.5 requests per entry average
print(f"  Est. time: ~{est_minutes:.0f} minutes")
print()

matches = 0
searched = 0
api_calls = 0

for w in work:
    idx = w['idx']
    searched += 1
    found_it = False

    sys.stdout.write(f"[{searched}/{len(work)}] idx={idx} ")

    # Strategy 1: docket number (most precise)
    if w['docket'] and not found_it:
        sys.stdout.write(f"docket={w['docket']} ")
        sys.stdout.flush()
        url, name = cl_search('d', docket_number=w['docket'], court_id=w['court_id'])
        api_calls += 1
        if url:
            found[str(idx)] = url
            matches += 1
            print(f"-> {name[:50]}")
            found_it = True
        time.sleep(DELAY)

    # Strategy 2: docket search by case name + court
    if w['case_name'] and w['court_id'] and not found_it:
        sys.stdout.write(f"d:\"{w['case_name'][:35]}\" ")
        sys.stdout.flush()
        url, name = cl_search('d', case_name=w['case_name'], court_id=w['court_id'])
        api_calls += 1
        if url:
            found[str(idx)] = url
            matches += 1
            print(f"-> {name[:50]}")
            found_it = True
        time.sleep(DELAY)

    # Strategy 3: opinion search with court
    if w['case_name'] and not found_it:
        sys.stdout.write(f"o:\"{w['case_name'][:35]}\" ")
        if w['court_id']:
            sys.stdout.write(f"@{w['court_id']} ")
        sys.stdout.flush()
        url, name = cl_search('o', case_name=w['case_name'], court_id=w['court_id'])
        api_calls += 1
        if url:
            found[str(idx)] = url
            matches += 1
            print(f"-> {name[:50]}")
            found_it = True
        time.sleep(DELAY)

    # Strategy 4: opinion search without court (broadest)
    if w['case_name'] and w['court_id'] and not found_it:
        sys.stdout.write(f"o-broad ")
        sys.stdout.flush()
        url, name = cl_search('o', case_name=w['case_name'])
        api_calls += 1
        if url:
            found[str(idx)] = url
            matches += 1
            print(f"-> {name[:50]}")
            found_it = True
        time.sleep(DELAY)

    if not found_it:
        print("X")

    # Save every 15
    if searched % 15 == 0:
        save()
        rate = matches / searched * 100
        print(f"  === {matches}/{searched} ({rate:.0f}%) | {api_calls} API calls | {len(found)} total ===")
        sys.stdout.flush()

save()
rate = matches / searched * 100 if searched else 0
print(f"\nDone. {matches}/{searched} ({rate:.0f}%) new. {len(found)} total links. {api_calls} API calls.")
