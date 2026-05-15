#!/usr/bin/env python3
"""Enrich R&G-only rows by classifying summaries with Claude Haiku."""

import csv
import json
import os
import time
import sys
from anthropic import Anthropic

INPUT = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'orders_merged.csv')
OUTPUT = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'orders_enriched.csv')
REPORT = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'enrichment_report.txt')

MODEL = "claude-haiku-4-5-20251001"
BATCH_SIZE = 20  # rows per API call to reduce total calls

# Columns to classify via LLM
CLASSIFY_COLS = [
    'document_type',
    'order_type',
    'case_types',
    'ai_type',
    'ai_use_case_for_filings',
    'prohibited',
    'disclose_ai_use_w_each_filing',
    'disclose_ai_tool_used',
    'disclose_how_ai_tool_used',
    'identify_sections_drafted_with_ai',
    'disclose_process_used_to_check_accuracy',
    'certify_accuracy_non_use_on_notice',
    'certify_accuracy_non_use_w_each_filing',
    'certify_accuracy_if_planning_to_use_ai',
    'certify_no_unauthorized_disclosure',
    'certify_accuracy_w_each_filing_if_ai_used',
    'just_a_warning',
    'references_other_procedural_rules',
    'maintain_ai_prompt_records',
    'proprietary_info_nondisclosure_req',
    'disclose_ai_generated_evidence',
    'notice_to_opposing_parties_ai_evidence',
    'ai_to_record_in_courtroom',
    'applies_to',
]

COLUMN_DESCRIPTIONS = """
Column definitions and allowed values:

- document_type: "Standing Order" | "Local Rules" | "Administrative Order" | "Judicial Opinion" | "Practice Direction" | "" (if unclear)
- order_type: "Judge Level" | "Court Level" | "District Level" | "" (if unclear)
- case_types: comma-separated from: "Civil", "Criminal", "Bankruptcy", "All". Use "" if not specified.
- ai_type: "Gen AI" | "Any AI" | "Gen AI, excluding standard research tools" | "" if unclear
- ai_use_case_for_filings: comma-separated from: "Draft", "Research", "Prepare", "Create". Use "" if not mentioned.
- prohibited: "checked" if AI use is prohibited/banned outright, else ""
- disclose_ai_use_w_each_filing: "Yes" if must disclose AI use with each filing, "No" if explicitly not required, "" if not addressed
- disclose_ai_tool_used: "checked" if must identify which AI tool was used, else ""
- disclose_how_ai_tool_used: "checked" if must explain how AI was used, else ""
- identify_sections_drafted_with_ai: "checked" if must identify which sections AI drafted, else ""
- disclose_process_used_to_check_accuracy: "checked" if must describe verification process, else ""
- certify_accuracy_non_use_on_notice: "checked" if must certify accuracy or non-use on notice of appearance, else ""
- certify_accuracy_non_use_w_each_filing: "Yes" if must certify with each filing, "No" if not, "" if not addressed
- certify_accuracy_if_planning_to_use_ai: "checked" if must certify when planning to use AI, else ""
- certify_no_unauthorized_disclosure: "checked" if must certify no unauthorized disclosure of confidential info to AI, else ""
- certify_accuracy_w_each_filing_if_ai_used: "checked" if must certify accuracy only when AI was used, else ""
- just_a_warning: "checked" if the order is just a cautionary warning without specific requirements, else ""
- references_other_procedural_rules: specific rule referenced (e.g., "FRCP 11", "Rule 3.3") or "No" or ""
- maintain_ai_prompt_records: "checked" if must retain/preserve AI prompts, else ""
- proprietary_info_nondisclosure_req: "checked" if prohibits sharing proprietary/confidential info with AI, else ""
- disclose_ai_generated_evidence: "checked" if must disclose AI-generated evidence, else ""
- notice_to_opposing_parties_ai_evidence: "checked" if must notify opposing parties about AI evidence, else ""
- ai_to_record_in_courtroom: "checked" if addresses AI recording in courtroom, else ""
- applies_to: comma-separated from: "Attorneys", "Pro Se Litigants", "Any Parties", "Judicial Officers", "Court Staff". Use "" if not specified.

IMPORTANT: Many R&G entries are descriptions of judicial opinions about AI misuse (sanctions cases, show cause orders) rather than standing orders with specific requirements. For these:
- document_type should be "Judicial Opinion"
- Most disclosure/certification columns should be "" since opinions don't impose prospective requirements
- just_a_warning should be "checked" if the opinion merely warns about AI use
- Focus on what the order/opinion actually REQUIRES going forward, not what happened in the case
"""


def build_few_shot_examples(matched_rows):
    """Build few-shot examples from matched rows with both RAILS and R&G data."""
    examples = []
    for row in matched_rows[:5]:
        summary = row.get('rg_summary', '')
        if not summary:
            continue
        classification = {}
        for col in CLASSIFY_COLS:
            val = row.get(col, '')
            if val:
                classification[col] = val
        if classification:
            examples.append({
                'summary': summary[:800],
                'tags': row.get('rg_tags', ''),
                'classification': classification,
            })
    return examples


def build_prompt(examples, batch):
    """Build classification prompt for a batch of summaries."""
    example_text = ""
    for i, ex in enumerate(examples):
        example_text += f"\n--- Example {i+1} ---\n"
        example_text += f"Tags: {ex['tags']}\n"
        example_text += f"Summary: {ex['summary']}\n"
        example_text += f"Classification: {json.dumps(ex['classification'])}\n"

    items_text = ""
    for i, item in enumerate(batch):
        items_text += f"\n--- Item {i} ---\n"
        items_text += f"Tags: {item['rg_tags']}\n"
        items_text += f"Summary: {item['rg_summary'][:1500]}\n"

    return f"""Classify each court order/opinion below according to the RAILS schema.

{COLUMN_DESCRIPTIONS}

Here are examples of correctly classified orders:
{example_text}

Now classify these {len(batch)} items. Return a JSON array where each element corresponds to an item (by index) and contains only the columns you can determine from the summary. Omit columns where the answer is unclear. Be conservative — only fill a column if the summary clearly supports it.

{items_text}

Return ONLY valid JSON: [{{"item": 0, ...}}, {{"item": 1, ...}}, ...]"""


def classify_batch(client, examples, batch, retries=2):
    """Send batch to Claude for classification."""
    prompt = build_prompt(examples, batch)

    for attempt in range(retries + 1):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
            # Extract JSON from response
            if text.startswith('['):
                return json.loads(text)
            # Try to find JSON array in response
            start = text.find('[')
            end = text.rfind(']') + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
            print(f"  Warning: could not parse response, attempt {attempt+1}")
        except Exception as e:
            print(f"  Error: {e}, attempt {attempt+1}")
            if attempt < retries:
                time.sleep(2)
    return []


def main():
    with open(INPUT, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    # Separate by source
    matched = [r for r in rows if r['source'] == 'both']
    rg_only = [r for r in rows if r['source'] == 'rg' and r.get('rg_summary', '').strip()]
    other = [r for r in rows if r['source'] not in ('rg',) or not r.get('rg_summary', '').strip()]

    print(f"Rows to enrich: {len(rg_only)}")
    print(f"Matched examples for few-shot: {len(matched)}")

    # Build few-shot examples from matched rows
    examples = build_few_shot_examples(matched)
    print(f"Few-shot examples built: {len(examples)}")

    client = Anthropic()
    enriched_count = 0
    total_cols_filled = 0

    # Process in batches
    batches = [rg_only[i:i+BATCH_SIZE] for i in range(0, len(rg_only), BATCH_SIZE)]
    print(f"Batches: {len(batches)} (size {BATCH_SIZE})")

    for batch_idx, batch in enumerate(batches):
        print(f"  Batch {batch_idx+1}/{len(batches)} ({len(batch)} items)...", end='', flush=True)

        results = classify_batch(client, examples, batch)

        if not results:
            print(" FAILED")
            continue

        # Apply results
        result_map = {}
        for r in results:
            if isinstance(r, dict) and 'item' in r:
                result_map[r['item']] = r

        batch_filled = 0
        for i, row in enumerate(batch):
            classification = result_map.get(i, {})
            for col in CLASSIFY_COLS:
                val = classification.get(col, '')
                if val and not row.get(col, '').strip():
                    row[col] = val
                    batch_filled += 1

            # Update enrichment_needed
            empty = [c for c in CLASSIFY_COLS if not row.get(c, '').strip()]
            row['enrichment_needed'] = ', '.join(empty)

            if classification:
                enriched_count += 1

        total_cols_filled += batch_filled
        print(f" OK ({batch_filled} cells filled)")

        # Rate limit
        time.sleep(0.5)

    # Rebuild full dataset
    all_rows = other + rg_only
    # Sort by date to maintain order
    all_rows.sort(key=lambda r: (r.get('date_yyyy_mm', '') or 'zzzz', r.get('judge_last_name', '')))

    # Add enrichment_method column
    if 'enrichment_method' not in fieldnames:
        fieldnames = list(fieldnames) + ['enrichment_method']
    for row in all_rows:
        if row['source'] == 'rg':
            row['enrichment_method'] = 'llm+keyword'
        elif row['source'] == 'both':
            row['enrichment_method'] = 'rails_authoritative'
        else:
            row['enrichment_method'] = 'rails_original'

    with open(OUTPUT, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(all_rows)

    # Report
    report_lines = [
        "=== ENRICHMENT REPORT ===",
        f"Total R&G-only rows processed: {len(rg_only)}",
        f"Successfully enriched: {enriched_count}",
        f"Total cells filled by LLM: {total_cols_filled}",
        "",
        "=== POST-ENRICHMENT FILL RATES ===",
    ]

    for col in CLASSIFY_COLS:
        filled_before_rg = sum(1 for r in rows if r['source'] == 'rg' and r.get(col, '').strip())
        filled_after_rg = sum(1 for r in rg_only if r.get(col, '').strip())
        total_filled = sum(1 for r in all_rows if r.get(col, '').strip())
        report_lines.append(
            f"  {col:50s}  total={total_filled:3d}/{len(all_rows)}  "
            f"rg_before={filled_before_rg:3d}  rg_after={filled_after_rg:3d}  "
            f"delta=+{filled_after_rg - filled_before_rg}"
        )

    remaining_gaps = sum(1 for r in all_rows for c in CLASSIFY_COLS if not r.get(c, '').strip())
    report_lines.extend([
        "",
        f"Remaining gaps: {remaining_gaps}",
        f"Output: {OUTPUT}",
    ])

    report_text = '\n'.join(report_lines)
    with open(REPORT, 'w') as f:
        f.write(report_text)

    print()
    print(report_text)


if __name__ == '__main__':
    main()
