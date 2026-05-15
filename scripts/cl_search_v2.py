#!/usr/bin/env python3
"""Search CourtListener API for free links to replace paywalled LexisNexis links.
Uses the API key from the court-listener MCP .env file and improved extraction."""

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

lexis_indices = [i for i, d in enumerate(data) if d.get('link', '').startswith('https://advance.lexis.com')]
remaining = [i for i in lexis_indices if str(i) not in found and str(i) not in no_match]
print(f"Lexis links: {len(lexis_indices)}, Already found: {len(found)}, No match: {len(no_match)}, Remaining: {len(remaining)}")


def extract_case_name(entry):
    """Extract case name from summary or name field."""
    summary = entry.get('summary', '')
    name = entry.get('name', '')

    # "In CaseName, ..." at start of summary (most common pattern)
    m = re.search(r'In\s+(.+?),\s+(?:No\.|the |Judge |Chief |Magistrate |\d{4})', summary)
    if m:
        cn = m.group(1).strip()
        # Clean up trailing citation numbers
        cn = re.sub(r'\s*\d{4}\s+(?:U\.S\.|Fla\.|N\.C\.).*$', '', cn)
        if len(cn) > 5:
            return cn

    # Broader "In X," pattern
    m = re.search(r'In\s+(.+?),', summary)
    if m:
        cn = m.group(1).strip()
        if ' v. ' in cn or ' v ' in cn:
            cn = re.sub(r'\s*\d{4}\s+(?:U\.S\.|Fla\.|N\.C\.).*$', '', cn)
            if len(cn) > 5:
                return cn

    # Use name field if it has v.
    if name and (' v. ' in name or ' v ' in name):
        return name.strip()

    return None


def extract_docket_number(entry):
    """Extract docket/case number from summary."""
    summary = entry.get('summary', '')
    m = re.search(r'No\.\s+([\d:]+[-](?:cv|cr|mc|mj)[-]\d+)', summary)
    if m:
        return m.group(1)
    return None


def extract_date_range(entry):
    """Get filed_after and filed_before from entry date."""
    date = entry.get('date', '').strip()
    if not date:
        return None, None
    try:
        parts = date.split('-')
        year = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 else 6
        # 3-month window
        start_month = max(1, month - 1)
        end_month = min(12, month + 1)
        end_year = year
        if month == 12:
            end_month = 1
            end_year = year + 1
        return f"{year}-{start_month:02d}-01", f"{end_year}-{end_month:02d}-28"
    except:
        return None, None


def search_cl(query, filed_after=None, filed_before=None, court=None):
    """Search CourtListener v4 search API. Returns (url, case_name) or (None, None)."""
    params = {
        'q': query,
        'type': 'o',
        'format': 'json',
        'page_size': 5,
    }
    if filed_after:
        params['filed_after'] = filed_after
    if filed_before:
        params['filed_before'] = filed_before
    if court:
        params['court'] = court

    url = f"https://www.courtlistener.com/api/rest/v4/search/?{urllib.parse.urlencode(params)}"

    try:
        req = urllib.request.Request(url, headers={
            'Authorization': f'Token {API_KEY}',
            'User-Agent': 'rails-analysis/1.0',
        })
        with urllib.request.urlopen(req, context=ssl_ctx, timeout=15) as resp:
            result = json.loads(resp.read().decode())

        if result.get('results'):
            r = result['results'][0]
            abs_url = r.get('absolute_url', '')
            if abs_url:
                op_url = f"https://www.courtlistener.com{abs_url}"
            else:
                op_url = f"https://www.courtlistener.com/opinion/{r['id']}/{r.get('slug', '')}/"
            return op_url, r.get('caseName', '')
    except urllib.error.HTTPError as e:
        if e.code == 429:
            print("  Rate limited, waiting 60s...")
            time.sleep(60)
            return search_cl(query, filed_after, filed_before, court)
        print(f"  HTTP {e.code}: {e.reason}")
    except Exception as e:
        print(f"  Error: {e}")

    return None, None


# Court name to CL court ID mapping
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
    'D. Or.': 'ord', 'W.D. Mich.': 'miwd', 'D.V.I.': 'vid',
    'M.D. La.': 'lamd',
    # Circuit courts
    '1st Cir.': 'ca1', '2d Cir.': 'ca2', '3d Cir.': 'ca3',
    '4th Cir.': 'ca4', '5th Cir.': 'ca5', '6th Cir.': 'ca6',
    '7th Cir.': 'ca7', '8th Cir.': 'ca8', '9th Cir.': 'ca9',
    '10th Cir.': 'ca10', '11th Cir.': 'ca11', 'D.C. Cir.': 'cadc',
    'Fed. Cir.': 'cafc',
}


def get_court_id(entry):
    """Try to map entry court to CL court ID."""
    court = entry.get('court', '').strip()
    if court in COURT_MAP:
        return COURT_MAP[court]
    # Try partial match
    for key, val in COURT_MAP.items():
        if key in court:
            return val
    return None


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
    filed_after, filed_before = extract_date_range(entry)
    court_id = get_court_id(entry)

    # Strategy 1: Search by case name (best)
    # Strategy 2: Search by docket number
    # Strategy 3: Search by judge + court

    strategies = []
    if case_name:
        strategies.append(('case_name', f'"{case_name}"'))
    if docket_num:
        strategies.append(('docket', f'docketNumber:"{docket_num}"'))
    if not strategies:
        judge = entry.get('judge', '').strip()
        judge_clean = re.sub(r'(?:Chief |Hon\. |Judge |Magistrate |Justice )', '', judge).strip()
        parts = judge_clean.split()
        if parts:
            last_name = parts[-1]
            strategies.append(('judge', f'judge:"{last_name}"'))

    if not strategies:
        no_match.add(str(idx))
        continue

    searched += 1
    found_it = False

    for strat_name, query in strategies:
        sys.stdout.write(f"[{searched}/{len(remaining)}] idx={idx} ({strat_name}) {query[:55]}... ")
        sys.stdout.flush()

        url, cl_name = search_cl(query, filed_after, filed_before, court_id if strat_name != 'case_name' else None)

        if url:
            found[str(idx)] = url
            matches += 1
            print(f"FOUND: {cl_name[:50]}")
            found_it = True
            break
        else:
            print("no match")

        # If case_name search failed, try without date filter
        if strat_name == 'case_name' and not url:
            sys.stdout.write(f"  retry no date filter... ")
            sys.stdout.flush()
            url, cl_name = search_cl(query)
            if url:
                found[str(idx)] = url
                matches += 1
                print(f"FOUND: {cl_name[:50]}")
                found_it = True
                break
            else:
                print("no match")

        time.sleep(1.5)

    if not found_it:
        no_match.add(str(idx))

    # Save every 25
    if searched % 25 == 0:
        save()
        print(f"  -- Saved. {matches}/{searched} matches so far ({len(found)} total) --")

    time.sleep(1.5)

save()
print(f"\nDone. {matches} new matches from {searched} searched ({len(found)} total found). {len(no_match)} no-match.")
