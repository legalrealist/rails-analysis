#!/usr/bin/env python3
"""Batch search CourtListener for free links to replace LexisNexis.

Strategy:
  1. Docket number search (49 entries) — most precise
  2. Docket case_name search with court filter (304 federal entries)
  3. Opinion search for all remaining (catches state courts too)
  4. Broader opinion search without court filter as fallback

Uses 4-second delays between requests and exponential backoff on 429s.
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
TASKS_FILE = "data/processed/search_tasks.json"
OUTPUT_FILE = "data/processed/cl_links.json"

with open(TASKS_FILE) as f:
    tasks = json.load(f)

try:
    with open(OUTPUT_FILE) as f:
        found = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    found = {}

# Filter to remaining tasks
remaining = [t for t in tasks if str(t['idx']) not in found]
print(f"Total tasks: {len(tasks)}, Already found: {len(found)}, Remaining: {len(remaining)}")

# Sort: docket number entries first (most precise), then federal, then state
remaining.sort(key=lambda t: (
    0 if t.get('docket') else 1,
    0 if t.get('court') else 1,
))


def api_request(url, max_retries=3):
    """Make CL API request with retry on 429."""
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers={
                'Authorization': f'Token {API_KEY}',
                'User-Agent': 'rails-analysis/2.0',
            })
            with urllib.request.urlopen(req, context=ssl_ctx, timeout=20) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 30 * (2 ** attempt)  # 30s, 60s, 120s
                print(f"  429 rate limit, waiting {wait}s (attempt {attempt+1}/{max_retries})...")
                sys.stdout.flush()
                time.sleep(wait)
            elif e.code == 400:
                return None  # Bad query, skip
            else:
                print(f"  HTTP {e.code}")
                return None
        except Exception as e:
            print(f"  Error: {e}")
            return None
    return None


def search_dockets(case_name=None, docket_number=None, court_id=None):
    """Search CL dockets. Returns (url, name) or (None, None)."""
    params = {'type': 'd', 'format': 'json', 'page_size': '3'}
    if case_name:
        params['case_name'] = case_name
    if docket_number:
        params['docket_number'] = docket_number
    if court_id:
        params['court'] = court_id

    url = f"https://www.courtlistener.com/api/rest/v4/search/?{urllib.parse.urlencode(params)}"
    result = api_request(url)

    if result and result.get('results'):
        r = result['results'][0]
        docket_url = r.get('docket_absolute_url', '')
        if docket_url:
            return f"https://www.courtlistener.com{docket_url}", r.get('caseName', '')
        docket_id = r.get('docket_id')
        if docket_id:
            slug = re.sub(r'[^a-z0-9-]', '', r.get('caseName', '').lower().replace(' ', '-'))[:50]
            return f"https://www.courtlistener.com/docket/{docket_id}/{slug}/", r.get('caseName', '')
    return None, None


def search_opinions(case_name, court_id=None, filed_after=None, filed_before=None):
    """Search CL opinions. Returns (url, name) or (None, None)."""
    params = {
        'type': 'o',
        'q': f'"{case_name}"',
        'format': 'json',
        'page_size': '3',
    }
    if court_id:
        params['court'] = court_id
    if filed_after:
        params['filed_after'] = filed_after
    if filed_before:
        params['filed_before'] = filed_before

    url = f"https://www.courtlistener.com/api/rest/v4/search/?{urllib.parse.urlencode(params)}"
    result = api_request(url)

    if result and result.get('results'):
        r = result['results'][0]
        abs_url = r.get('absolute_url', '')
        if abs_url:
            return f"https://www.courtlistener.com{abs_url}", r.get('caseName', '')
    return None, None


def get_date_range(task):
    """Extract date range from the original data."""
    # We'll need to look up the original entry
    return None, None


def save():
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(found, f, indent=2)


matches = 0
searched = 0
docket_hits = 0
opinion_hits = 0
skipped_429 = 0

for task in remaining:
    idx = task['idx']
    case_name = task.get('case_name', '')
    court_id = task.get('court')
    docket_num = task.get('docket')

    searched += 1
    found_it = False

    # === Strategy 1: Docket number search (most precise) ===
    if docket_num:
        sys.stdout.write(f"[{searched}/{len(remaining)}] idx={idx} docket={docket_num}")
        if court_id:
            sys.stdout.write(f" court={court_id}")
        sys.stdout.write("... ")
        sys.stdout.flush()

        url, cl_name = search_dockets(docket_number=docket_num, court_id=court_id)
        if url:
            found[str(idx)] = url
            matches += 1
            docket_hits += 1
            print(f"FOUND: {cl_name[:55]}")
            found_it = True
        else:
            print("miss")
        time.sleep(4)

    # === Strategy 2: Docket case_name search (federal) ===
    if not found_it and case_name and court_id:
        sys.stdout.write(f"[{searched}/{len(remaining)}] idx={idx} docket_name=\"{case_name[:45]}\" court={court_id}... ")
        sys.stdout.flush()

        url, cl_name = search_dockets(case_name=case_name, court_id=court_id)
        if url:
            found[str(idx)] = url
            matches += 1
            docket_hits += 1
            print(f"FOUND: {cl_name[:55]}")
            found_it = True
        else:
            print("miss")
        time.sleep(4)

    # === Strategy 3: Opinion search with court ===
    if not found_it and case_name:
        sys.stdout.write(f"[{searched}/{len(remaining)}] idx={idx} opinion=\"{case_name[:45]}\"")
        if court_id:
            sys.stdout.write(f" court={court_id}")
        sys.stdout.write("... ")
        sys.stdout.flush()

        url, cl_name = search_opinions(case_name, court_id=court_id)
        if url:
            found[str(idx)] = url
            matches += 1
            opinion_hits += 1
            print(f"FOUND: {cl_name[:55]}")
            found_it = True
        else:
            print("miss")
        time.sleep(4)

    # === Strategy 4: Opinion search WITHOUT court filter ===
    if not found_it and case_name and court_id:
        sys.stdout.write(f"  retry no court... ")
        sys.stdout.flush()

        url, cl_name = search_opinions(case_name)
        if url:
            found[str(idx)] = url
            matches += 1
            opinion_hits += 1
            print(f"FOUND: {cl_name[:55]}")
            found_it = True
        else:
            print("miss")
        time.sleep(4)

    if not found_it:
        pass  # Don't mark no_match — may want to retry with Scholar later

    # Save every 20
    if searched % 20 == 0:
        save()
        hit_rate = matches / searched * 100 if searched else 0
        print(f"  -- Saved. {matches}/{searched} ({hit_rate:.0f}%) | docket={docket_hits} opinion={opinion_hits} | {len(found)} total --")
        sys.stdout.flush()

save()
hit_rate = matches / searched * 100 if searched else 0
print(f"\nDone. {matches}/{searched} ({hit_rate:.0f}%) new matches.")
print(f"Docket hits: {docket_hits}, Opinion hits: {opinion_hits}")
print(f"Total links: {len(found)}")
