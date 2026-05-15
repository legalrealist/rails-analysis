#!/usr/bin/env python3
"""Merge RAILS and R&G cleaned datasets into one canonical dataset."""

import csv
import os
import re

RAILS_INPUT = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'rails_clean.csv')
RG_INPUT = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'rg_clean.csv')
MERGED_OUTPUT = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'orders_merged.csv')
REPORT_OUTPUT = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'merge_report.txt')
REVIEW_OUTPUT = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'review_needed.csv')
GAPS_OUTPUT = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'enrichment_gaps.csv')

# RAILS classification columns that we want filled for all rows
RAILS_CLASSIFY_COLS = [
    'document_type', 'court_type', 'order_type', 'case_types',
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

# R&G supplement columns to keep alongside RAILS schema
RG_SUPPLEMENT_COLS = [
    'rg_id', 'rg_tags', 'rg_summary',
    'rg_consequences_attorneys', 'rg_consequences_parties',
]


def normalize_for_match(s):
    """Normalize string for matching: lowercase, strip punctuation."""
    return re.sub(r'[.\s]+', '', s.lower().strip())


def normalize_court_for_match(abbr):
    """Normalize court abbreviation for matching.

    Handles variations like "Ct. Int'l Trade" vs "Ct. Int'l. Trade",
    extra dots, and spacing differences.
    """
    if not abbr:
        return ''
    s = abbr.lower().strip()
    # Remove all spaces
    s = re.sub(r'\s+', '', s)
    # Normalize apostrophes
    s = s.replace('’', "'").replace('‘', "'")
    # Remove periods (so "n.d.tex." and "n.d.tex" match)
    s = s.replace('.', '')
    return s


def extract_last_name_normalized(last):
    """Normalize last name for matching."""
    return last.lower().strip().rstrip('.')


def date_month_match(rails_date, rg_date):
    """Check if dates match at month level. RAILS: YYYY-MM, R&G: YYYY-MM-DD or YYYY-MM."""
    if not rails_date or not rg_date:
        return False, False
    rails_ym = rails_date[:7]
    rg_ym = rg_date[:7]
    if rails_ym == rg_ym:
        return True, False

    # Check near-match (within 2 months)
    try:
        ry, rm = int(rails_ym[:4]), int(rails_ym[5:7])
        gy, gm = int(rg_ym[:4]), int(rg_ym[5:7])
        diff = abs((ry * 12 + rm) - (gy * 12 + gm))
        if diff <= 2:
            return False, True
    except ValueError:
        pass

    return False, False


def main():
    with open(RAILS_INPUT, encoding='utf-8') as f:
        rails_rows = list(csv.DictReader(f))
    with open(RG_INPUT, encoding='utf-8') as f:
        rg_rows = list(csv.DictReader(f))

    # Build unified column set
    rails_cols = list(rails_rows[0].keys()) if rails_rows else []
    rg_cols = list(rg_rows[0].keys()) if rg_rows else []
    # All RAILS columns + any RG columns not already in RAILS
    all_cols = list(rails_cols)
    for c in rg_cols:
        if c not in all_cols:
            all_cols.append(c)
    all_cols.append('source')
    all_cols.append('enrichment_needed')

    # Index R&G by (last_name_norm, court_norm) for matching
    rg_index = {}
    for i, rg in enumerate(rg_rows):
        ln = extract_last_name_normalized(rg.get('judge_last_name', ''))
        cn = normalize_court_for_match(rg.get('court_abbreviation', ''))
        if ln and cn:
            key = (ln, cn)
            rg_index.setdefault(key, []).append(i)

    matched_rg = set()
    merged = []
    review = []

    # Match RAILS → R&G
    for rails in rails_rows:
        r_ln = extract_last_name_normalized(rails.get('judge_last_name', ''))
        r_cn = normalize_court_for_match(rails.get('court_abbreviation', ''))
        r_date = rails.get('date_yyyy_mm', '')

        best_match = None
        near_matches = []

        if r_ln and r_cn:
            key = (r_ln, r_cn)
            candidates = rg_index.get(key, [])
            for idx in candidates:
                rg = rg_rows[idx]
                exact, near = date_month_match(r_date, rg.get('date_yyyy_mm', ''))
                if exact:
                    best_match = idx
                    break
                elif near:
                    near_matches.append(idx)

        if best_match is not None:
            rg = rg_rows[best_match]
            matched_rg.add(best_match)
            row = {c: '' for c in all_cols}
            # RAILS columns are authoritative
            for c in rails_cols:
                row[c] = rails.get(c, '')
            # Supplement with R&G
            for c in RG_SUPPLEMENT_COLS:
                row[c] = rg.get(c, '')
            row['source'] = 'both'
            row['enrichment_needed'] = _find_gaps(row)
            merged.append(row)
        else:
            # RAILS-only
            row = {c: '' for c in all_cols}
            for c in rails_cols:
                row[c] = rails.get(c, '')
            row['source'] = 'rails'
            row['enrichment_needed'] = _find_gaps(row)
            merged.append(row)

            # Record near-matches for review
            for idx in near_matches:
                rg = rg_rows[idx]
                review.append({
                    'rails_judge': rails.get('judge_author', ''),
                    'rails_court': rails.get('court_abbreviation', ''),
                    'rails_date': r_date,
                    'rg_judge': rg.get('judge_author', ''),
                    'rg_court': rg.get('court_abbreviation', ''),
                    'rg_date': rg.get('date_yyyy_mm', ''),
                    'rg_id': rg.get('rg_id', ''),
                    'reason': 'date_near_match',
                })

    # R&G-only rows
    for i, rg in enumerate(rg_rows):
        if i not in matched_rg:
            row = {c: '' for c in all_cols}
            for c in rg_cols:
                if c in row:
                    row[c] = rg.get(c, '')
            row['source'] = 'rg'
            row['enrichment_needed'] = _find_gaps(row)
            merged.append(row)

    # Write merged
    with open(MERGED_OUTPUT, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=all_cols)
        writer.writeheader()
        writer.writerows(merged)

    # Write review needed
    if review:
        with open(REVIEW_OUTPUT, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=review[0].keys())
            writer.writeheader()
            writer.writerows(review)

    # Write enrichment gaps
    gaps = []
    for i, row in enumerate(merged):
        if row['enrichment_needed']:
            for col in row['enrichment_needed'].split(', '):
                gaps.append({
                    'row_id': i,
                    'judge': row.get('judge_author', ''),
                    'court': row.get('court_abbreviation', ''),
                    'date': row.get('date_yyyy_mm', ''),
                    'source': row['source'],
                    'column_name': col,
                    'rg_summary': row.get('rg_summary', '')[:200],
                })
    with open(GAPS_OUTPUT, 'w', newline='', encoding='utf-8') as f:
        if gaps:
            writer = csv.DictWriter(f, fieldnames=gaps[0].keys())
            writer.writeheader()
            writer.writerows(gaps)

    # Report
    rails_only = sum(1 for r in merged if r['source'] == 'rails')
    rg_only = sum(1 for r in merged if r['source'] == 'rg')
    both = sum(1 for r in merged if r['source'] == 'both')

    dates = [r['date_yyyy_mm'] for r in merged if r['date_yyyy_mm']]
    date_range = f"{min(dates)} to {max(dates)}" if dates else "N/A"

    report_lines = [
        "=== MERGE REPORT ===",
        f"Total unique orders: {len(merged)}",
        f"  RAILS-only: {rails_only}",
        f"  R&G-only: {rg_only}",
        f"  Matched (both): {both}",
        f"Date range: {date_range}",
        f"Near-matches flagged for review: {len(review)}",
        "",
        "=== FILL RATES (classification columns) ===",
    ]

    for col in RAILS_CLASSIFY_COLS:
        total_filled = sum(1 for r in merged if r.get(col, ''))
        rails_filled = sum(1 for r in merged if r['source'] in ('rails', 'both') and r.get(col, ''))
        rg_filled = sum(1 for r in merged if r['source'] == 'rg' and r.get(col, ''))
        report_lines.append(
            f"  {col:50s}  total={total_filled:3d}/{len(merged)}  "
            f"rails+both={rails_filled:3d}/{rails_only+both}  "
            f"rg_only={rg_filled:3d}/{rg_only}"
        )

    report_lines.extend([
        "",
        f"Total enrichment gaps: {len(gaps)}",
        f"Output: {MERGED_OUTPUT}",
        f"Review: {REVIEW_OUTPUT}",
        f"Gaps: {GAPS_OUTPUT}",
    ])

    report_text = '\n'.join(report_lines)

    with open(REPORT_OUTPUT, 'w') as f:
        f.write(report_text)

    print(report_text)


def _find_gaps(row):
    """Return comma-separated list of empty RAILS classification columns."""
    empty = []
    for col in RAILS_CLASSIFY_COLS:
        if not row.get(col, '').strip():
            empty.append(col)
    return ', '.join(empty)


if __name__ == '__main__':
    main()
