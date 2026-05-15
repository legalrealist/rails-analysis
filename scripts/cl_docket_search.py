#!/usr/bin/env python3
"""Search CourtListener DOCKETS (not opinions) for free links to replace LexisNexis.

Most of the remaining entries are unpublished federal district court orders which
CourtListener has as docket entries (from PACER) but NOT as searchable opinions.
This script searches the docket endpoint instead.
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
DATA_FILE = "data/processed/explorer_data.json"
OUTPUT_FILE = "data/processed/cl_links.json"
NO_MATCH_FILE = "data/processed/cl_no_match.json"

with open(DATA_FILE) as f:
    data = json.load(f)

try:
    with open(OUTPUT_FILE) as f:
        found = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    found = {}

try:
    with open(NO_MATCH_FILE) as f:
        no_match = set(str(x) for x in json.load(f))
except:
    no_match = set()

# Reset no_match from previous opinion searches - those cases may have dockets
# Keep only non-federal-district entries in no_match
old_no_match_count = len(no_match)
# Actually, let's just clear no_match and re-search everything via dockets
no_match_keep = set()
for nm_idx in no_match:
    idx = int(nm_idx)
    if idx < len(data):
        court = data[idx].get('court', '')
        # Keep state court no-matches (those won't have PACER dockets)
        is_federal = any(x in court for x in [
            'D.', 'S.D.', 'N.D.', 'E.D.', 'W.D.', 'M.D.', 'C.D.', 'D.D.C.',
            'Cir.', 'Fed. Cl.', 'Tax Ct.'
        ])
        if not is_federal:
            no_match_keep.add(nm_idx)

print(f"Cleared {old_no_match_count - len(no_match_keep)} federal no-matches for docket re-search")
no_match = no_match_keep

lexis_indices = [i for i, d in enumerate(data) if d.get('link', '').startswith('https://advance.lexis.com')]
remaining = [i for i in lexis_indices if str(i) not in found and str(i) not in no_match]
print(f"Lexis links: {len(lexis_indices)}, Already found: {len(found)}, No match (state): {len(no_match)}, Remaining: {len(remaining)}")

COURT_MAP = {
    'D. Or.': 'ord', 'E.D. Mich.': 'mied', 'E.D. Tex.': 'txed',
    'C.D. Cal.': 'cacd', 'S.D. Fla.': 'flsd', 'N.D. Ill.': 'ilnd',
    'S.D.N.Y.': 'nysd', 'E.D.N.Y.': 'nyed', 'N.D. Cal.': 'cand',
    'D.N.J.': 'njd', 'E.D. Pa.': 'paed', 'W.D. Pa.': 'pawd',
    'D. Md.': 'mdd', 'S.D. Tex.': 'txsd', 'N.D. Tex.': 'txnd',
    'W.D. Tex.': 'txwd', 'D. Ariz.': 'azd', 'D. Colo.': 'cod',
    'D. Conn.': 'ctd', 'M.D. Fla.': 'flmd', 'N.D. Fla.': 'flnd',
    'S.D. Ind.': 'insd', 'N.D. Ind.': 'innd', 'D. Kan.': 'ksd',
    'E.D. La.': 'laed', 'W.D. La.': 'lawd', 'D. Mass.': 'mad',
    'D. Minn.': 'mnd', 'S.D. Miss.': 'mssd', 'E.D. Mo.': 'moed',
    'W.D. Mo.': 'mowd', 'D. Nev.': 'nvd', 'D.N.M.': 'nmd',
    'W.D.N.Y.': 'nywd', 'N.D.N.Y.': 'nynd', 'M.D.N.C.': 'ncmd',
    'W.D.N.C.': 'ncwd', 'N.D. Ohio': 'ohnd', 'S.D. Ohio': 'ohsd',
    'W.D. Okla.': 'okwd', 'D.S.C.': 'scd', 'M.D. Tenn.': 'tnmd',
    'W.D. Tenn.': 'tnwd', 'E.D. Va.': 'vaed', 'W.D. Va.': 'vawd',
    'E.D. Wis.': 'wied', 'W.D. Wis.': 'wiwd', 'D. Utah': 'utd',
    'D.D.C.': 'dcd', 'M.D. Ga.': 'gamd', 'N.D. Ga.': 'gand',
    'S.D. Ga.': 'gasd', 'D. Haw.': 'hid', 'S.D. Ala.': 'alsd',
    'M.D. Ala.': 'almd', 'N.D. Ala.': 'alnd', 'E.D. Ark.': 'ared',
    'W.D. Ark.': 'arwd', 'D. Del.': 'ded', 'D. Idaho': 'idd',
    'S.D. Iowa': 'iasd', 'N.D. Iowa': 'iand', 'E.D. Ky.': 'kyed',
    'W.D. Ky.': 'kywd', 'D. Me.': 'med', 'D. Mont.': 'mtd',
    'D. Neb.': 'ned', 'D.N.H.': 'nhd', 'E.D.N.C.': 'nced',
    'D.R.I.': 'rid', 'D.S.D.': 'sdd', 'D. Vt.': 'vtd',
    'E.D. Wash.': 'waed', 'W.D. Wash.': 'wawd', 'S.D.W. Va.': 'wvsd',
    'N.D.W. Va.': 'wvnd', 'D. Wyo.': 'wyd', 'M.D. Pa.': 'pamd',
    'W.D. Mich.': 'miwd', 'D.V.I.': 'vid', 'M.D. La.': 'lamd',
    'E.D. Okla.': 'oked', 'N.D. Okla.': 'oknd', 'W.D. Wash.': 'wawd',
    'D. Neb.': 'ned', 'M.D.N.C.': 'ncmd', 'E.D. Tenn.': 'tned',
    # Circuit courts
    '1st Cir.': 'ca1', '2d Cir.': 'ca2', '2nd Cir.': 'ca2',
    '3d Cir.': 'ca3', '3rd Cir.': 'ca3',
    '4th Cir.': 'ca4', '5th Cir.': 'ca5', '6th Cir.': 'ca6',
    '7th Cir.': 'ca7', '8th Cir.': 'ca8', '9th Cir.': 'ca9',
    '10th Cir.': 'ca10', '11th Cir.': 'ca11', 'D.C. Cir.': 'cadc',
    'Fed. Cir.': 'cafc',
    # Special courts
    'Fed. Cl.': 'uscfc', 'Tax Ct.': 'tax',
}


def get_court_id(entry):
    court = entry.get('court', '').strip()
    if court in COURT_MAP:
        return COURT_MAP[court]
    for key, val in COURT_MAP.items():
        if key in court:
            return val
    return None


def extract_case_name(entry):
    summary = entry.get('summary', '')
    name = entry.get('name', '')

    # "In CaseName, No. ..." or "In CaseName, 2024..."
    m = re.search(r'In\s+(.+?),\s+(?:No\.|the |Judge |Chief |Magistrate |\d{4})', summary)
    if m:
        cn = m.group(1).strip()
        cn = re.sub(r'\s*\d{4}\s+(?:U\.S\.|Fla\.|N\.C\.).*$', '', cn)
        if len(cn) > 5:
            return cn

    # Broader "In X," with v.
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
    summary = entry.get('summary', '')
    # Federal docket number patterns: 2:25-cv-01294, 1:23-cr-00100, etc.
    m = re.search(r'No\.\s*(\d+:\d+-\w+-\d+)', summary)
    if m:
        return m.group(1)
    # Also try without "No."
    m = re.search(r'(\d+:\d+-cv-\d+)', summary)
    if m:
        return m.group(1)
    return None


def _do_request(url):
    """Make an API request with retry on 429. Returns parsed JSON or None."""
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={
                'Authorization': f'Token {API_KEY}',
                'User-Agent': 'rails-analysis/1.0',
            })
            with urllib.request.urlopen(req, context=ssl_ctx, timeout=20) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 90 * (attempt + 1)
                print(f"  Rate limited, waiting {wait}s (attempt {attempt+1}/3)...")
                time.sleep(wait)
            elif e.code == 400:
                print(f"  HTTP 400 (bad query)")
                return None
            else:
                print(f"  HTTP {e.code}")
                return None
        except Exception as e:
            print(f"  Error: {e}")
            return None
    print("  Giving up after 3 retries")
    return None


def search_dockets(case_name=None, docket_number=None, court_id=None):
    """Search CourtListener dockets API. Returns (docket_url, case_name) or (None, None)."""
    params = {'format': 'json', 'page_size': 3}

    if docket_number:
        params['docket_number'] = docket_number
        if court_id:
            params['court'] = court_id
        url = f"https://www.courtlistener.com/api/rest/v4/search/?type=d&{urllib.parse.urlencode(params)}"
    elif case_name:
        params['q'] = case_name
        params['type'] = 'd'
        if court_id:
            params['court'] = court_id
        url = f"https://www.courtlistener.com/api/rest/v4/search/?{urllib.parse.urlencode(params)}"
    else:
        return None, None

    result = _do_request(url)
    if result and result.get('results'):
        r = result['results'][0]
        docket_url = r.get('docket_absolute_url', '')
        if docket_url:
            return f"https://www.courtlistener.com{docket_url}", r.get('caseName', '')
        docket_id = r.get('docket_id')
        if docket_id:
            slug = r.get('caseName', '').lower().replace(' ', '-')[:50]
            return f"https://www.courtlistener.com/docket/{docket_id}/{slug}/", r.get('caseName', '')

    return None, None


def search_opinions(case_name, court_id=None, filed_after=None, filed_before=None):
    """Search opinions API as fallback (works for published state court opinions)."""
    params = {
        'q': case_name,
        'type': 'o',
        'format': 'json',
        'page_size': 3,
    }
    if court_id:
        params['court'] = court_id
    if filed_after:
        params['filed_after'] = filed_after
    if filed_before:
        params['filed_before'] = filed_before

    url = f"https://www.courtlistener.com/api/rest/v4/search/?{urllib.parse.urlencode(params)}"
    result = _do_request(url)
    if result and result.get('results'):
        r = result['results'][0]
        abs_url = r.get('absolute_url', '')
        if abs_url:
            return f"https://www.courtlistener.com{abs_url}", r.get('caseName', '')

    return None, None


def save():
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(found, f, indent=2)
    with open(NO_MATCH_FILE, 'w') as f:
        json.dump(sorted(no_match), f)


matches = 0
searched = 0

for idx in remaining:
    entry = data[idx]
    case_name = extract_case_name(entry)
    docket_num = extract_docket_number(entry)
    court_id = get_court_id(entry)
    court = entry.get('court', '')
    date = entry.get('date', '')

    is_federal = court_id is not None

    searched += 1
    found_it = False

    # Strategy 1: Docket number search (most precise, federal only)
    if docket_num and is_federal:
        sys.stdout.write(f"[{searched}/{len(remaining)}] idx={idx} docket={docket_num}... ")
        sys.stdout.flush()
        url, cl_name = search_dockets(docket_number=docket_num, court_id=court_id)
        if url:
            found[str(idx)] = url
            matches += 1
            print(f"FOUND: {cl_name[:50]}")
            found_it = True
        else:
            print("no match")
        time.sleep(3)

    # Strategy 2: Case name docket search
    if not found_it and case_name and is_federal:
        sys.stdout.write(f"[{searched}/{len(remaining)}] idx={idx} docket_name=\"{case_name[:45]}\"... ")
        sys.stdout.flush()
        url, cl_name = search_dockets(case_name=case_name, court_id=court_id)
        if url:
            found[str(idx)] = url
            matches += 1
            print(f"FOUND: {cl_name[:50]}")
            found_it = True
        else:
            print("no match")
        time.sleep(3)

    # Strategy 3: Opinion search (for state courts / published opinions)
    if not found_it and case_name:
        # Build date range
        filed_after = filed_before = None
        if date:
            try:
                parts = date.split('-')
                year = int(parts[0])
                month = int(parts[1]) if len(parts) > 1 else 6
                filed_after = f"{year}-{max(1, month-1):02d}-01"
                end_month = min(12, month + 1)
                end_year = year
                if month == 12:
                    end_month = 1
                    end_year = year + 1
                filed_before = f"{end_year}-{end_month:02d}-28"
            except:
                pass

        sys.stdout.write(f"[{searched}/{len(remaining)}] idx={idx} opinion=\"{case_name[:45]}\"... ")
        sys.stdout.flush()
        url, cl_name = search_opinions(case_name, court_id, filed_after, filed_before)
        if not url and (filed_after or filed_before):
            # Retry without date
            url, cl_name = search_opinions(case_name)
            time.sleep(3)
        if url:
            found[str(idx)] = url
            matches += 1
            print(f"FOUND: {cl_name[:50]}")
            found_it = True
        else:
            print("no match")
        time.sleep(3)

    if not found_it:
        no_match.add(str(idx))

    # Save every 10
    if searched % 10 == 0:
        save()
        hit_rate = matches / searched * 100 if searched else 0
        print(f"  -- Saved. {matches}/{searched} ({hit_rate:.0f}%) new matches ({len(found)} total) --")

    time.sleep(2)  # Extra buffer between entries

save()
hit_rate = matches / searched * 100 if searched else 0
print(f"\nDone. {matches}/{searched} ({hit_rate:.0f}%) new matches. {len(found)} total found. {len(no_match)} no-match.")
