#!/usr/bin/env python3
"""Search Google for CourtListener links to replace LexisNexis.

Uses Google site search: site:courtlistener.com "case name"
This avoids CL API rate limits entirely.
Delays 20s between searches to avoid Google CAPTCHAs.
"""

import json, re, time, sys, urllib.request, urllib.parse, ssl, html

ssl_ctx = ssl.create_default_context()
try:
    import certifi
    ssl_ctx.load_verify_locations(certifi.where())
except ImportError:
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

BASE = "/Users/hao/ClaudeCode/rails-analysis"
DATA_FILE = f"{BASE}/data/processed/explorer_data.json"
OUTPUT_FILE = f"{BASE}/data/processed/cl_links.json"
PROGRESS_FILE = f"{BASE}/data/processed/google_no_match.json"

with open(DATA_FILE) as f:
    data = json.load(f)

try:
    with open(OUTPUT_FILE) as f:
        found = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    found = {}

try:
    with open(PROGRESS_FILE) as f:
        no_match = set(str(x) for x in json.load(f))
except:
    no_match = set()


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


def simplify_case_name(case_name):
    """Simplify case name for better Google matching."""
    if not case_name:
        return None
    # Remove docket numbers, citations
    cn = re.sub(r',?\s*No\.?\s*\d.*$', '', case_name)
    cn = re.sub(r',?\s*\d{4}\s+.*$', '', cn)
    # Keep "X v. Y" - first few words of each party
    m = re.match(r'(.+?)\s+v\.?\s+(.+?)(?:\s*$|,)', cn)
    if m:
        p1 = ' '.join(m.group(1).strip().split()[:3])
        p2 = ' '.join(m.group(2).strip().split()[:3])
        return f"{p1} v. {p2}"
    return cn.strip()


def google_search(query):
    """Search Google. Returns list of (url, title) tuples for CL/Justia/Scholar results."""
    encoded = urllib.parse.quote(query)
    url = f"https://www.google.com/search?q={encoded}&num=10"

    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
        })
        with urllib.request.urlopen(req, context=ssl_ctx, timeout=15) as resp:
            if resp.info().get('Content-Encoding') == 'gzip':
                import gzip
                body = gzip.decompress(resp.read()).decode('utf-8', errors='replace')
            else:
                body = resp.read().decode('utf-8', errors='replace')

        # Check for CAPTCHA
        if 'unusual traffic' in body.lower() or 'captcha' in body.lower() or 'recaptcha' in body.lower():
            print("CAPTCHA! Pausing 5 minutes...")
            sys.stdout.flush()
            time.sleep(300)
            return 'CAPTCHA'

        results = []

        # Extract CourtListener docket/opinion URLs
        cl_urls = re.findall(r'(https://www\.courtlistener\.com/(?:docket|opinion)/\d+/[^"&\s<>]+)', body)
        for u in cl_urls:
            u = html.unescape(u)
            # Clean up - remove /parties/ suffix etc
            u = re.sub(r'/parties/?$', '/', u)
            results.append(('courtlistener', u))

        # Extract Justia case law URLs
        justia_urls = re.findall(r'(https://law\.justia\.com/cases/[^"&\s<>]+)', body)
        for u in justia_urls:
            results.append(('justia', html.unescape(u)))

        # Extract Google Scholar case URLs
        scholar_urls = re.findall(r'(https://scholar\.google\.com/scholar_case\?case=\d+)', body)
        for u in scholar_urls:
            results.append(('scholar', html.unescape(u)))

        return results

    except urllib.error.HTTPError as e:
        if e.code == 429:
            print("Google 429! Pausing 5 minutes...")
            time.sleep(300)
            return 'CAPTCHA'
        print(f"HTTP {e.code}")
    except Exception as e:
        print(f"Error: {e}")

    return []


def save():
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(found, f, indent=2)
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(sorted(no_match), f)


# Build work list
lexis_remaining = [i for i, d in enumerate(data)
                   if d.get('link', '').startswith('https://advance.lexis.com')
                   and str(i) not in found
                   and str(i) not in no_match]

print(f"Remaining: {len(lexis_remaining)}, Already found: {len(found)}, No match: {len(no_match)}")

matches = 0
searched = 0

for idx in lexis_remaining:
    entry = data[idx]
    case_name = extract_case_name(entry)
    if not case_name:
        no_match.add(str(idx))
        continue

    simple_name = simplify_case_name(case_name)
    if not simple_name or len(simple_name) < 8:
        no_match.add(str(idx))
        continue

    searched += 1

    # Search 1: site:courtlistener.com "case name"
    query1 = f'site:courtlistener.com "{simple_name}"'
    sys.stdout.write(f"[{searched}] idx={idx} \"{simple_name[:45]}\"... ")
    sys.stdout.flush()

    results = google_search(query1)
    if results == 'CAPTCHA':
        # Retry once after pause
        results = google_search(query1)
        if results == 'CAPTCHA':
            print("Double CAPTCHA, stopping.")
            break

    if results:
        # Prefer CourtListener docket, then opinion, then justia, then scholar
        best = None
        for source, url in results:
            if source == 'courtlistener' and '/docket/' in url:
                best = url
                break
        if not best:
            for source, url in results:
                if source == 'courtlistener':
                    best = url
                    break
        if not best:
            best = results[0][1]  # any result

        found[str(idx)] = best
        matches += 1
        print(f"FOUND: {best[:70]}")
    else:
        # Try broader: "case name" courtlistener OR justia OR scholar
        time.sleep(8)
        query2 = f'"{simple_name}" (courtlistener.com OR law.justia.com OR scholar.google.com)'
        sys.stdout.write(f"  broad... ")
        sys.stdout.flush()

        results2 = google_search(query2)
        if results2 == 'CAPTCHA':
            no_match.add(str(idx))
            print("CAPTCHA")
            continue

        if results2:
            best = results2[0][1]
            found[str(idx)] = best
            matches += 1
            print(f"FOUND: {best[:70]}")
        else:
            no_match.add(str(idx))
            print("X")

    # Save every 10
    if searched % 10 == 0:
        save()
        rate = matches / searched * 100
        print(f"  === {matches}/{searched} ({rate:.0f}%) | {len(found)} total ===")

    # 20s between searches to avoid CAPTCHA
    time.sleep(20)

save()
rate = matches / searched * 100 if searched else 0
print(f"\nDone. {matches}/{searched} ({rate:.0f}%). Total: {len(found)}.")
