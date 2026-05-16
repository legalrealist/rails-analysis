#!/usr/bin/env python3
"""Scrape Ropes & Gray AI Court Order Tracker using Playwright + cookies.

Strategy:
1. Launch headless Chromium via Playwright to pass Cloudflare
2. Navigate to the tracker page once
3. Extract cookies and Next.js build ID
4. Use requests library with extracted cookies to fetch each state's JSON
5. Parse HTML tables from the JSON responses
6. Output to data/sources/ropes_gray_court_orders.json
"""

import json
import os
import re
import sys
import time
from html.parser import HTMLParser

try:
    import requests
except ImportError:
    sys.exit("pip install requests")

BASE_URL = "https://www.ropesgray.com"
TRACKER_PATH = "/en/sites/artificial-intelligence-court-order-tracker"
OUTPUT = os.path.join(os.path.dirname(__file__), '..', 'data', 'sources', 'ropes_gray_court_orders.json')

os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)


class TableParser(HTMLParser):
    """Parse HTML tables into list of row dicts."""

    def __init__(self):
        super().__init__()
        self._in_table = False
        self._in_thead = False
        self._in_tbody = False
        self._in_th = False
        self._in_td = False
        self._in_a = False
        self._current_href = None
        self._current_text = ''
        self._headers = []
        self._current_row = []
        self._rows = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == 'table':
            self._in_table = True
            self._headers = []
            self._rows = []
        elif tag == 'thead':
            self._in_thead = True
        elif tag == 'tbody':
            self._in_tbody = True
        elif tag == 'th' and self._in_thead:
            self._in_th = True
            self._current_text = ''
        elif tag == 'td' and self._in_tbody:
            self._in_td = True
            self._current_text = ''
            self._current_href = None
        elif tag == 'a' and self._in_td:
            self._in_a = True
            self._current_href = attrs_dict.get('href', '')

    def handle_endtag(self, tag):
        if tag == 'table':
            self._in_table = False
        elif tag == 'thead':
            self._in_thead = False
        elif tag == 'tbody':
            self._in_tbody = False
        elif tag == 'th':
            if self._in_th:
                self._headers.append(self._current_text.strip())
            self._in_th = False
        elif tag == 'td':
            if self._in_td:
                cell = self._current_text.strip()
                if self._current_href:
                    cell = {'text': cell, 'href': self._current_href}
                self._current_row.append(cell)
            self._in_td = False
        elif tag == 'tr':
            if self._in_tbody and self._current_row:
                self._rows.append(self._current_row)
            self._current_row = []
        elif tag == 'a':
            self._in_a = False

    def handle_data(self, data):
        if self._in_th or self._in_td:
            self._current_text += data

    def get_table_data(self):
        result = []
        for row in self._rows:
            if len(row) >= len(self._headers):
                entry = {}
                for i, h in enumerate(self._headers):
                    entry[h] = row[i]
                result.append(entry)
        return result


def extract_build_id(page_source):
    """Extract Next.js build ID from page source."""
    match = re.search(r'"buildId"\s*:\s*"([^"]+)"', page_source)
    if match:
        return match.group(1)
    match = re.search(r'/_next/data/([^/]+)/', page_source)
    if match:
        return match.group(1)
    return None


def extract_states_from_page(page_source):
    """Extract state slugs from the interactive map or navigation links."""
    slugs = set()
    for match in re.finditer(r'/states/([a-z-]+?)(?:["\']|$)', page_source):
        slug = match.group(1)
        if slug and len(slug) > 1:
            slugs.add(slug)
    return sorted(slugs)


def parse_table_html(html_content):
    """Parse an HTML table string into rows."""
    parser = TableParser()
    parser.feed(html_content)
    return parser.get_table_data()


def fetch_with_playwright():
    """Use Playwright to pass Cloudflare, extract cookies and build ID."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("pip install playwright && playwright install chromium")

    print("Launching Playwright browser...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        url = BASE_URL + TRACKER_PATH
        print(f"Navigating to {url}...")
        page.goto(url, wait_until='networkidle', timeout=60000)
        time.sleep(3)

        page_source = page.content()
        build_id = extract_build_id(page_source)
        print(f"Build ID: {build_id}")

        state_slugs = extract_states_from_page(page_source)
        print(f"Found {len(state_slugs)} state slugs")

        cookies = context.cookies()
        cookie_dict = {c['name']: c['value'] for c in cookies}
        print(f"Extracted {len(cookie_dict)} cookies")

        browser.close()

    return build_id, state_slugs, cookie_dict


def fetch_state_data(build_id, state_slug, cookies, session):
    """Fetch a single state's data via Next.js JSON endpoint."""
    url = f"{BASE_URL}/_next/data/{build_id}/en/sites/artificial-intelligence-court-order-tracker/states/{state_slug}.json"
    resp = session.get(url, timeout=30)

    if resp.status_code != 200:
        print(f"  WARN: {state_slug} returned {resp.status_code}")
        return []

    data = resp.json()
    page_props = data.get('pageProps', {})
    components = page_props.get('route', {}).get('placeholders', {})

    rows = []
    for key, items in components.items():
        for item in (items if isinstance(items, list) else []):
            fields = item.get('fields', {})
            text_val = fields.get('text', {}).get('value', '') if isinstance(fields.get('text'), dict) else ''
            if '<table' in text_val.lower():
                parsed = parse_table_html(text_val)
                rows.extend(parsed)

    if not rows:
        content_str = json.dumps(data)
        tables = re.findall(r'<table[^>]*>.*?</table>', content_str, re.DOTALL | re.IGNORECASE)
        for table_html in tables:
            parsed = parse_table_html(table_html)
            rows.extend(parsed)

    return rows


def fetch_federal_data(build_id, cookies, session):
    """Fetch federal circuit decisions."""
    url = f"{BASE_URL}/_next/data/{build_id}/en/sites/artificial-intelligence-court-order-tracker/federal-circuit-decisions.json"
    resp = session.get(url, timeout=30)
    if resp.status_code != 200:
        print(f"  WARN: federal-circuit-decisions returned {resp.status_code}")
        return []

    data = resp.json()
    content_str = json.dumps(data)
    rows = []
    tables = re.findall(r'<table[^>]*>.*?</table>', content_str, re.DOTALL | re.IGNORECASE)
    for table_html in tables:
        parsed = parse_table_html(table_html)
        rows.extend(parsed)
    return rows


def slug_to_state_name(slug):
    """Convert URL slug to state name."""
    return slug.replace('-', ' ').title()


def main():
    build_id, state_slugs, cookies = fetch_with_playwright()

    if not build_id:
        sys.exit("ERROR: Could not extract Next.js build ID")
    if not state_slugs:
        sys.exit("ERROR: Could not find any state slugs")

    session = requests.Session()
    session.cookies.update(cookies)
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json',
    })

    all_entries = []

    for i, slug in enumerate(state_slugs):
        state_name = slug_to_state_name(slug)
        print(f"[{i+1}/{len(state_slugs)}] Fetching {state_name}...")
        rows = fetch_state_data(build_id, slug, cookies, session)
        for row in rows:
            row['_state'] = state_name
            row['_state_slug'] = slug
        all_entries.extend(rows)
        time.sleep(0.2)

    print(f"Fetching federal circuit decisions...")
    fed_rows = fetch_federal_data(build_id, cookies, session)
    for row in fed_rows:
        row['_state'] = 'Federal'
        row['_state_slug'] = 'federal-circuit-decisions'
    all_entries.extend(fed_rows)

    print(f"\nTotal entries scraped: {len(all_entries)}")

    output = {
        'scraped_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'build_id': build_id,
        'total_entries': len(all_entries),
        'states_scraped': len(state_slugs),
        'entries': all_entries,
    }

    with open(OUTPUT, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"Written to {OUTPUT}")


if __name__ == '__main__':
    main()
