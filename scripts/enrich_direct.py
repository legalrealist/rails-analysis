#!/usr/bin/env python3
"""Apply enrichment classifications from JSON files back to merged dataset."""

import csv
import json
import os
import glob

MERGED = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'orders_merged.csv')
ENRICHMENT_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'enrichments')
OUTPUT = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'orders_enriched.csv')
REPORT = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'enrichment_report.txt')

CLASSIFY_COLS = [
    'document_type', 'order_type', 'case_types',
    'ai_type', 'ai_use_case_for_filings', 'prohibited',
    'disclose_ai_use_w_each_filing', 'disclose_ai_tool_used',
    'disclose_how_ai_tool_used', 'identify_sections_drafted_with_ai',
    'disclose_process_used_to_check_accuracy',
    'certify_accuracy_non_use_on_notice',
    'certify_accuracy_non_use_w_each_filing',
    'certify_accuracy_if_planning_to_use_ai',
    'certify_no_unauthorized_disclosure',
    'certify_accuracy_w_each_filing_if_ai_used',
    'just_a_warning', 'references_other_procedural_rules',
    'maintain_ai_prompt_records', 'proprietary_info_nondisclosure_req',
    'disclose_ai_generated_evidence',
    'notice_to_opposing_parties_ai_evidence',
    'ai_to_record_in_courtroom', 'applies_to',
]


def main():
    with open(MERGED, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    if 'enrichment_method' not in fieldnames:
        fieldnames.append('enrichment_method')

    # Load all enrichment JSON files
    enrichment_files = sorted(glob.glob(os.path.join(ENRICHMENT_DIR, 'batch_*.json')))
    print(f"Found {len(enrichment_files)} enrichment files")

    all_enrichments = {}
    for ef in enrichment_files:
        with open(ef) as f:
            batch = json.load(f)
        for item in batch:
            rg_id = item.get('rg_id', '')
            if rg_id:
                all_enrichments[rg_id] = item

    print(f"Total enrichments loaded: {len(all_enrichments)}")

    # Track before/after
    before_counts = {}
    for col in CLASSIFY_COLS:
        before_counts[col] = sum(1 for r in rows if r['source'] == 'rg' and r.get(col, '').strip())

    # Apply enrichments
    applied = 0
    cells_filled = 0
    for row in rows:
        if row['source'] == 'rg':
            rg_id = row.get('rg_id', '')
            enrichment = all_enrichments.get(rg_id)
            if enrichment:
                for col in CLASSIFY_COLS:
                    new_val = enrichment.get(col, '')
                    if new_val and not row.get(col, '').strip():
                        row[col] = new_val
                        cells_filled += 1
                    elif new_val and row.get(col, '').strip():
                        pass  # keep existing keyword-extracted value
                applied += 1
            row['enrichment_method'] = 'llm+keyword' if enrichment else 'keyword_only'
        elif row['source'] == 'both':
            row['enrichment_method'] = 'rails_authoritative'
        else:
            row['enrichment_method'] = 'rails_original'

        # Update enrichment_needed
        empty = [c for c in CLASSIFY_COLS if not row.get(c, '').strip()]
        row['enrichment_needed'] = ', '.join(empty)

    with open(OUTPUT, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)

    # Report
    after_counts = {}
    for col in CLASSIFY_COLS:
        after_counts[col] = sum(1 for r in rows if r['source'] == 'rg' and r.get(col, '').strip())

    report_lines = [
        "=== ENRICHMENT REPORT ===",
        f"Total R&G-only rows: {sum(1 for r in rows if r['source'] == 'rg')}",
        f"Enrichments applied: {applied}",
        f"Total cells filled: {cells_filled}",
        "",
        "=== FILL RATE CHANGES (R&G-only) ===",
    ]
    total_rg = sum(1 for r in rows if r['source'] == 'rg')
    for col in CLASSIFY_COLS:
        b = before_counts[col]
        a = after_counts[col]
        delta = a - b
        report_lines.append(f"  {col:50s}  before={b:3d}  after={a:3d}  delta=+{delta:3d}  ({100*a/total_rg:.0f}%)")

    remaining = sum(1 for r in rows for c in CLASSIFY_COLS if not r.get(c, '').strip())
    report_lines.extend(["", f"Remaining gaps: {remaining}", f"Output: {OUTPUT}"])

    report_text = '\n'.join(report_lines)
    with open(REPORT, 'w') as f:
        f.write(report_text)
    print(report_text)


if __name__ == '__main__':
    main()
