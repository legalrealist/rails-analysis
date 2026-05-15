#!/usr/bin/env python3
"""Apply CourtListener links to replace LexisNexis paywalled links in explorer data."""

import json

DATA_FILE = "data/processed/explorer_data.json"
CL_FILE = "data/processed/cl_links.json"
CSV_FILE = "data/processed/orders_enriched.csv"

# Load data
with open(DATA_FILE) as f:
    data = json.load(f)

with open(CL_FILE) as f:
    cl_links = json.load(f)

print(f"Explorer data: {len(data)} orders")
print(f"CourtListener links: {len(cl_links)} matches")

# Count current Lexis links
lexis_before = sum(1 for d in data if d.get('link', '').startswith('https://advance.lexis.com'))
print(f"LexisNexis links before: {lexis_before}")

# Apply CL links
replaced = 0
for idx_str, cl_url in cl_links.items():
    idx = int(idx_str)
    if idx < len(data) and data[idx].get('link', '').startswith('https://advance.lexis.com'):
        data[idx]['link'] = cl_url
        replaced += 1

# Save updated explorer data
with open(DATA_FILE, 'w') as f:
    json.dump(data, f, indent=2)

lexis_after = sum(1 for d in data if d.get('link', '').startswith('https://advance.lexis.com'))
print(f"\nReplaced: {replaced} links")
print(f"LexisNexis links after: {lexis_after}")
print(f"Remaining paywalled: {lexis_after}")

# Also update the CSV if it exists
try:
    import csv
    with open(CSV_FILE, newline='') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames

    # Build lookup from explorer data (by judge+court+date)
    updated_csv = 0
    for idx_str, cl_url in cl_links.items():
        idx = int(idx_str)
        entry = data[idx]
        judge = entry.get('judge', '')
        court = entry.get('court', '')
        date = entry.get('date', '')

        for row in rows:
            csv_judge = row.get('judge_author', '') or row.get('judge', '')
            csv_court = row.get('court', '') or row.get('court_abbreviation', '')
            csv_date = row.get('date_yyyy_mm', '') or row.get('date', '')

            if (judge and judge in csv_judge or csv_judge in judge) and \
               (court and court in csv_court or csv_court in court) and \
               csv_date == date:
                if row.get('link_to_source', '').startswith('https://advance.lexis.com'):
                    row['link_to_source'] = cl_url
                    updated_csv += 1
                break

    with open(CSV_FILE, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"CSV updated: {updated_csv} links replaced")
except Exception as e:
    print(f"CSV update skipped: {e}")

# Summary by domain
from collections import Counter
domains = Counter()
for d in data:
    link = d.get('link', '')
    if link:
        parts = link.split('/')
        domain = parts[2] if len(parts) > 2 else 'unknown'
        domains[domain] += 1
    else:
        domains['NO_LINK'] += 1

print("\nLink domains after update:")
for domain, count in domains.most_common(15):
    print(f"  {count:4d}  {domain}")
