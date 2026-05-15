#!/usr/bin/env python3
"""Search CourtListener API for free links to replace paywalled LexisNexis links."""

import json, re, time, sys, urllib.request, urllib.parse, urllib.error, ssl
from datetime import datetime

# Fix macOS SSL certificate issue
ssl_ctx = ssl.create_default_context()
try:
    import certifi
    ssl_ctx.load_verify_locations(certifi.where())
except ImportError:
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

DATA_FILE = "data/processed/explorer_data.json"
OUTPUT_FILE = "data/processed/cl_links.json"

with open(DATA_FILE) as f:
    data = json.load(f)

# Load existing results
try:
    with open(OUTPUT_FILE) as f:
        found = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    found = {}

# Indices with Lexis links that haven't been searched yet
lexis_indices = [i for i, d in enumerate(data) if d.get('link', '').startswith('https://advance.lexis.com')]
remaining = [i for i in lexis_indices if str(i) not in found and str(i) not in getattr(sys, '_searched', set())]
searched_no_match = set()

# Try to load "no match" cache too
try:
    with open("data/processed/cl_no_match.json") as f:
        searched_no_match = set(json.load(f))
except:
    searched_no_match = set()

remaining = [i for i in remaining if str(i) not in searched_no_match]
print(f"Lexis links: {len(lexis_indices)}, Already found: {len(found)}, Already searched (no match): {len(searched_no_match)}, Remaining: {len(remaining)}")

def extract_case_name(entry):
    """Try to extract a searchable case name from the entry."""
    summary = entry.get('summary', '')
    name = entry.get('name', '')

    # Try to find "In CaseName," pattern from summary
    m = re.search(r'In\s+(.+?),\s+\d{4}', summary)
    if m:
        return m.group(1).strip()

    # Try "In CaseName, the court" or "In CaseName, Judge"
    m = re.search(r'In\s+(.+?),\s+(?:the |Judge |Chief )', summary)
    if m:
        return m.group(1).strip()

    # Use the name field if it looks like a case name
    if name and ' v. ' in name:
        return name.strip()
    if name and ' v ' in name:
        return name.strip()

    return None

def search_cl(query, date_str=None):
    """Search CourtListener API. Returns (url, case_name) or (None, None)."""
    params = {
        'q': query,
        'type': 'o',
        'format': 'json',
        'page_size': 5,
    }

    # Add date filter if we have a date
    if date_str:
        try:
            dt = datetime.strptime(date_str, '%Y-%m')
            # Search within a 3-month window
            start = f"{dt.year}-{max(1, dt.month-1):02d}-01"
            if dt.month == 12:
                end = f"{dt.year+1}-01-28"
            else:
                end = f"{dt.year}-{min(12, dt.month+1):02d}-28"
            params['filed_after'] = start
            params['filed_before'] = end
        except:
            pass

    url = f"https://www.courtlistener.com/api/rest/v4/search/?{urllib.parse.urlencode(params)}"

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (research project)'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())

        if result.get('results'):
            r = result['results'][0]
            # Build opinion URL
            op_url = f"https://www.courtlistener.com{r.get('absolute_url', '')}"
            if not r.get('absolute_url'):
                op_url = f"https://www.courtlistener.com/opinion/{r['id']}/{r.get('slug', '')}/"
            return op_url, r.get('caseName', '')
    except urllib.error.HTTPError as e:
        if e.code == 429:
            print("  Rate limited, waiting 30s...")
            time.sleep(30)
            return search_cl(query, date_str)  # retry once
        print(f"  HTTP {e.code}: {e.reason}")
    except Exception as e:
        print(f"  Error: {e}")

    return None, None

def save():
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(found, f, indent=2)
    with open("data/processed/cl_no_match.json", 'w') as f:
        json.dump(list(searched_no_match), f)

matches = 0
searched = 0

for idx in remaining:
    entry = data[idx]
    judge = entry.get('judge', '').strip()
    court = entry.get('court', '').strip()
    date = entry.get('date', '').strip()

    case_name = extract_case_name(entry)

    # Build search query
    if case_name:
        query = case_name
    elif judge:
        # Extract last name
        judge_clean = re.sub(r'(?:Chief |Hon\. |Judge |Magistrate |Justice )', '', judge).strip()
        parts = judge_clean.split()
        last_name = parts[-1] if parts else judge_clean
        query = f'judge:"{last_name}"'
        if court and len(court) < 30:
            query += f' court:"{court}"'
    else:
        searched_no_match.add(str(idx))
        continue

    searched += 1
    sys.stdout.write(f"[{searched}/{len(remaining)}] idx={idx} q={query[:60]}... ")
    sys.stdout.flush()

    url, cl_name = search_cl(query, date)

    if url:
        found[str(idx)] = url
        matches += 1
        print(f"FOUND: {cl_name[:50]}")
    else:
        searched_no_match.add(str(idx))
        print("no match")

    # Save every 20 searches
    if searched % 20 == 0:
        save()
        print(f"  -- Saved. {matches} matches so far --")

    # Rate limiting: 2 seconds between requests
    time.sleep(2)

save()
print(f"\nDone. {matches} new matches found ({len(found)} total). {len(searched_no_match)} confirmed no-match.")
