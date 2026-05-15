#!/usr/bin/env python3
"""Search Google Scholar for free case law links to replace LexisNexis paywalled links."""

import json, re, time, sys, urllib.request, urllib.parse, ssl, html

ssl_ctx = ssl.create_default_context()
try:
    import certifi
    ssl_ctx.load_verify_locations(certifi.where())
except ImportError:
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

DATA_FILE = "data/processed/explorer_data.json"
CL_FILE = "data/processed/cl_links.json"  # reuse same output file
PROGRESS_FILE = "data/processed/scholar_no_match.json"

with open(DATA_FILE) as f:
    data = json.load(f)

try:
    with open(CL_FILE) as f:
        found = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    found = {}

try:
    with open(PROGRESS_FILE) as f:
        no_match = set(str(x) for x in json.load(f))
except:
    no_match = set()

lexis_indices = [i for i, d in enumerate(data) if d.get('link', '').startswith('https://advance.lexis.com')]
remaining = [i for i in lexis_indices if str(i) not in found and str(i) not in no_match]
print(f"Lexis links: {len(lexis_indices)}, Already found: {len(found)}, Scholar no-match: {len(no_match)}, Remaining: {len(remaining)}")


def extract_case_name(entry):
    """Extract case name from summary."""
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


def extract_party_names(case_name):
    """Extract plaintiff v. defendant for cleaner search."""
    if not case_name:
        return None
    # Remove docket numbers, extra info
    cn = re.sub(r',?\s*No\.?\s*\d.*$', '', case_name)
    cn = re.sub(r',?\s*\d{4}\s+.*$', '', cn)
    # Keep just "X v. Y" - take first party and second party
    m = re.match(r'(.+?)\s+v\.?\s+(.+?)(?:\s*$|,)', cn)
    if m:
        p1 = m.group(1).strip()
        p2 = m.group(2).strip()
        # Simplify long party names - take first 3 words each
        p1_words = p1.split()[:4]
        p2_words = p2.split()[:4]
        return ' '.join(p1_words) + ' v. ' + ' '.join(p2_words)
    return cn.strip()


def search_scholar(query, year=None):
    """Search Google Scholar case law. Returns (url, title) or (None, None)."""
    params = {
        'q': f'"{query}"',
        'hl': 'en',
        'as_sdt': '4',  # case law only
    }
    if year:
        params['as_ylo'] = str(year)
        params['as_yhi'] = str(year)

    url = f"https://scholar.google.com/scholar?{urllib.parse.urlencode(params)}"

    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'en-US,en;q=0.9',
        })
        with urllib.request.urlopen(req, context=ssl_ctx, timeout=15) as resp:
            body = resp.read().decode('utf-8', errors='replace')

        # Check for CAPTCHA / block
        if 'unusual traffic' in body.lower() or 'captcha' in body.lower():
            print("  CAPTCHA detected! Waiting 5 minutes...")
            time.sleep(300)
            return search_scholar(query, year)

        # Extract first scholar_case link
        case_matches = re.findall(r'scholar_case\?case=(\d+)', body)
        if case_matches:
            case_id = case_matches[0]
            scholar_url = f"https://scholar.google.com/scholar_case?case={case_id}"

            # Try to extract the case title from the result
            # Pattern: <h3 class="gs_rt"><a ...>TITLE</a></h3>
            title_match = re.search(r'<h3[^>]*class="gs_rt"[^>]*>.*?<a[^>]*>(.+?)</a>', body, re.DOTALL)
            title = ""
            if title_match:
                title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()
                title = html.unescape(title)

            return scholar_url, title

        # No results
        return None, None

    except urllib.error.HTTPError as e:
        if e.code == 429:
            print("  Scholar rate limited, waiting 5 minutes...")
            time.sleep(300)
            return None, None  # Don't retry, just skip
        print(f"  HTTP {e.code}")
    except Exception as e:
        print(f"  Error: {e}")

    return None, None


def search_justia(case_name, year=None):
    """Search Justia for case law. Returns (url, title) or (None, None)."""
    query = case_name
    if year:
        query += f" {year}"

    params = {
        'q': query,
        'cx': '',  # not needed for site search
    }
    # Use Google site search for justia.com
    url = f"https://www.google.com/search?q=site:law.justia.com+%22{urllib.parse.quote(case_name)}%22"
    if year:
        url += f"+{year}"

    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'en-US,en;q=0.9',
        })
        with urllib.request.urlopen(req, context=ssl_ctx, timeout=15) as resp:
            body = resp.read().decode('utf-8', errors='replace')

        if 'unusual traffic' in body.lower() or 'captcha' in body.lower():
            print("  Google CAPTCHA! ")
            return None, None

        # Extract justia case law URLs
        justia_urls = re.findall(r'(https://law\.justia\.com/cases/[^"&\s]+)', body)
        if justia_urls:
            justia_url = html.unescape(justia_urls[0])
            # Extract title nearby
            title_match = re.search(re.escape(justia_urls[0]) + r'[^>]*>([^<]+)', body)
            title = title_match.group(1).strip() if title_match else ""
            title = html.unescape(title)
            return justia_url, title

    except urllib.error.HTTPError as e:
        if e.code == 429:
            print("  Justia rate limited, skipping... ")
            return None, None
        print(f"  HTTP {e.code}")
    except Exception as e:
        print(f"  Error: {e}")

    return None, None


def save():
    with open(CL_FILE, 'w') as f:
        json.dump(found, f, indent=2)
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(sorted(no_match), f)


matches = 0
searched = 0
scholar_hits = 0
justia_hits = 0

for idx in remaining:
    entry = data[idx]
    case_name = extract_case_name(entry)

    if not case_name:
        no_match.add(str(idx))
        continue

    search_query = extract_party_names(case_name)
    if not search_query or len(search_query) < 8:
        no_match.add(str(idx))
        continue

    # Extract year from date
    date = entry.get('date', '')
    year = None
    if date:
        try:
            year = int(date.split('-')[0])
        except:
            pass

    searched += 1
    sys.stdout.write(f"[{searched}/{len(remaining)}] idx={idx} \"{search_query[:50]}\"")
    if year:
        sys.stdout.write(f" ({year})")
    sys.stdout.write("... ")
    sys.stdout.flush()

    url = None
    title = ""

    # Alternate: even entries -> Scholar first, odd -> Justia first
    if searched % 2 == 0:
        # Scholar first
        sys.stdout.write("scholar... ")
        sys.stdout.flush()
        url, title = search_scholar(search_query, year)
        source = "scholar"

        if not url:
            time.sleep(10)
            sys.stdout.write("justia... ")
            sys.stdout.flush()
            url, title = search_justia(search_query, year)
            source = "justia"
    else:
        # Justia first
        sys.stdout.write("justia... ")
        sys.stdout.flush()
        url, title = search_justia(search_query, year)
        source = "justia"

        if not url:
            time.sleep(10)
            sys.stdout.write("scholar... ")
            sys.stdout.flush()
            url, title = search_scholar(search_query, year)
            source = "scholar"

    if url:
        found[str(idx)] = url
        matches += 1
        if source == "scholar":
            scholar_hits += 1
        else:
            justia_hits += 1
        print(f"FOUND ({source}): {title[:50]}")
    else:
        no_match.add(str(idx))
        print("no match")

    # Save every 10
    if searched % 10 == 0:
        save()
        hit_rate = matches / searched * 100 if searched else 0
        print(f"  -- Saved. {matches}/{searched} ({hit_rate:.0f}%) | scholar={scholar_hits} justia={justia_hits} | {len(found)} total --")

    # 10-15s between entries — spreads load across both sources
    time.sleep(10 + (searched % 6))

save()
hit_rate = matches / searched * 100 if searched else 0
print(f"\nDone. {matches}/{searched} ({hit_rate:.0f}%) new matches.")
print(f"Scholar: {scholar_hits}, Justia: {justia_hits}")
print(f"Total links: {len(found)}. No-match: {len(no_match)}.")
