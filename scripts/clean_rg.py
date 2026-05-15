#!/usr/bin/env python3
"""Clean Ropes & Gray JSON into RAILS schema format."""

import csv
import json
import re
import os
from html import unescape

INPUT = os.path.join(os.path.dirname(__file__), '..', 'data', 'sources', 'ropes_gray_court_orders.json')
OUTPUT = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'rg_clean.csv')

JUDGE_PREFIXES = [
    'Chief Administrative Hearing Officer ',
    'Magistrate Judge ',
    'Chief Justice ',
    'Chief Judge ',
    'Senior Judge ',
    'Judge ',
    'Hon. ',
    'Justice ',
]

# RAILS schema columns (the 33 snake_case columns from clean_rails.py)
RAILS_COLUMNS = [
    'document_name', 'link_to_source', 'document_type', 'judge_author',
    'court_type', 'country', 'state', 'court', 'date_yyyy_mm',
    'order_type', 'case_types', 'ai_type', 'ai_use_case_for_filings',
    'prohibited', 'disclose_ai_use_w_each_filing', 'disclose_ai_tool_used',
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
    'ai_to_record_in_courtroom', 'applies_to', 'other_reqs_notes',
]

EXTRA_COLUMNS = [
    'court_original', 'court_abbreviation', 'judge_title', 'judge_name_clean',
    'judge_last_name', 'rg_id', 'rg_tags', 'rg_summary',
    'rg_consequences_attorneys', 'rg_consequences_parties',
]


def strip_html(text):
    """Remove HTML tags and decode entities."""
    text = re.sub(r'<[^>]+>', '', text)
    text = unescape(text)
    return text.strip()


def extract_court_abbreviation(court_array):
    """Extract standardized abbreviation from R&G court array.

    R&G format varies:
    - Federal district: ["State - Federal District Court", "State - N.D. Tex."]
    - State: ["State - State Trial Court", "State - Del. Ch."]
    - Circuit: ["10th Circuit - Federal Court of Appeals", "10th Circuit - 10th Cir."]
    - Bankruptcy: ["State - Federal District Bankruptcy Court", "State - Bankr. D. Colo."]
    """
    if not court_array:
        return '', ''

    full = ' | '.join(court_array)

    # Look through all elements for abbreviation patterns (prefer last element)
    for c in reversed(court_array):
        after_dash = c.split(' - ')[-1].strip() if ' - ' in c else c.strip()
        if not after_dash:
            continue

        # Federal district: "N.D. Tex.", "S.D.N.Y.", "D. Colo.", "D.N.J."
        if re.match(r'^[NSEWCM]\.D\.?\s*\S+\.?$', after_dash):
            return full, after_dash
        if re.match(r'^D\.?\s*\S+\.?$', after_dash):
            return full, after_dash

        # Circuit courts: "10th Cir.", "3d Cir.", "5th Cir."
        if re.match(r'^\d+\w*\s+Cir\.?$', after_dash):
            return full, after_dash

        # Bankruptcy: "Bankr. D. Colo.", "Bankr. N.D. Tex."
        if after_dash.startswith('Bankr.'):
            return full, after_dash

        # State court abbreviations containing dots: "Del. Ch.", "N.Y. Sup. Ct.",
        # "Ind. Ct. App.", "Cal. Ct. App.", "Ct. Int'l. Trade"
        if '.' in after_dash and len(after_dash) < 40:
            return full, after_dash

    return full, ''


def parse_judge(judge_array):
    """Parse judge array into clean components."""
    if not judge_array:
        return '', '', '', ''

    first = judge_array[0].strip()
    full = ' | '.join(judge_array)

    title = ''
    name = first
    for prefix in JUDGE_PREFIXES:
        if first.startswith(prefix):
            title = prefix.strip()
            name = first[len(prefix):].strip()
            break

    parts = name.split()
    if not parts:
        return full, title, name, ''

    suffixes = {'Jr.', 'Jr', 'Sr.', 'Sr', 'II', 'III', 'IV', 'V'}
    last = parts[-1]
    if last in suffixes and len(parts) > 1:
        last = parts[-2]

    return full, title, name, last


def parse_date(iso_date):
    """Convert ISO date to YYYY-MM."""
    if not iso_date or iso_date.startswith('0001'):
        return ''
    m = re.match(r'^(\d{4})-(\d{2})', iso_date)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return ''


def infer_court_type(court_array):
    """Infer Federal/State from court description."""
    text = ' '.join(court_array).lower()
    if 'federal' in text or 'district court' in text and ('n.d.' in text or 's.d.' in text or 'e.d.' in text or 'w.d.' in text or 'c.d.' in text or 'm.d.' in text or 'd.' in text):
        return 'Federal'
    if 'state' in text or 'supreme court' in text or 'circuit court' in text or 'court of appeal' in text or 'superior court' in text:
        return 'State'
    return ''


def extract_from_summary(summary, tags):
    """Extract RAILS classification columns from R&G summary and tags."""
    s = summary.lower()
    tag_set = set(tags)
    out = {}

    # AI Type
    if 'Any AI Usage' in tag_set:
        out['ai_type'] = 'Any AI'
    elif 'Generative AI Usage' in tag_set:
        out['ai_type'] = 'Gen AI'

    # Prohibited
    if 'Prohibits Use of AI' in tag_set:
        out['prohibited'] = 'checked'
    elif 'prohibit' in s and ('use of ai' in s or 'use of generative' in s or 'use of artificial' in s):
        out['prohibited'] = 'checked'

    # Disclosure requirements
    if 'Requires Disclosure and/or Verification' in tag_set:
        if 'disclos' in s and ('filing' in s or 'each filing' in s):
            out['disclose_ai_use_w_each_filing'] = 'Yes'
        if 'identify' in s and 'tool' in s:
            out['disclose_ai_tool_used'] = 'checked'
        if ('how' in s or 'manner' in s) and ('ai' in s or 'tool' in s) and 'disclos' in s:
            out['disclose_how_ai_tool_used'] = 'checked'
        if 'section' in s and 'draft' in s and ('identify' in s or 'disclos' in s):
            out['identify_sections_drafted_with_ai'] = 'checked'
        if ('verify' in s or 'check' in s or 'ensur' in s) and 'accura' in s:
            out['disclose_process_used_to_check_accuracy'] = 'checked'

    # Certification requirements
    if 'certif' in s or 'attest' in s:
        if 'notice of appearance' in s:
            out['certify_accuracy_non_use_on_notice'] = 'checked'
        if ('each filing' in s or 'every filing' in s) and ('certif' in s or 'attest' in s):
            if 'non-use' in s or 'not use' in s or 'did not' in s:
                out['certify_accuracy_non_use_w_each_filing'] = 'Yes'
            elif 'only if' in s and 'used' in s:
                out['certify_accuracy_w_each_filing_if_ai_used'] = 'checked'
            else:
                out['certify_accuracy_non_use_w_each_filing'] = 'Yes'
        if 'planning to use' in s or 'intend' in s:
            out['certify_accuracy_if_planning_to_use_ai'] = 'checked'
        if 'unauthorized' in s and 'disclos' in s:
            out['certify_no_unauthorized_disclosure'] = 'checked'

    # Prompt records
    if ('prompt' in s and ('retain' in s or 'record' in s or 'preserv' in s or 'maintain' in s)) or \
       ('log' in s and 'ai' in s and ('retain' in s or 'record' in s or 'maintain' in s)):
        out['maintain_ai_prompt_records'] = 'checked'

    # Procedural rules
    rules_mentioned = []
    if 'frcp 11' in s or 'rule 11' in s or 'fed. r. civ. p. 11' in s:
        rules_mentioned.append('FRCP 11')
    if '28 u.s.c.' in s or 'section 1927' in s:
        rules_mentioned.append('28 U.S.C. § 1927')
    if 'rule 3.3' in s or 'model rule' in s:
        rules_mentioned.append('Model Rules')
    if rules_mentioned:
        out['references_other_procedural_rules'] = ', '.join(rules_mentioned)

    # Proprietary info
    if ('proprietary' in s or 'confidential' in s) and ('disclos' in s or 'protect' in s):
        out['proprietary_info_nondisclosure_req'] = 'checked'

    # AI-generated evidence
    if 'evidence' in s and ('ai-generated' in s or 'ai generated' in s or 'artificial' in s):
        if 'disclos' in s:
            out['disclose_ai_generated_evidence'] = 'checked'
        if 'notice' in s and 'oppos' in s:
            out['notice_to_opposing_parties_ai_evidence'] = 'checked'

    # Just a warning
    if 'Suggests Cautious Use of AI' in tag_set and 'Requires Disclosure and/or Verification' not in tag_set:
        out['just_a_warning'] = 'checked'

    # Applies to
    parties = []
    if 'attorney' in s or 'counsel' in s or 'lawyer' in s:
        parties.append('Attorneys')
    if 'pro se' in s or 'self-represent' in s:
        parties.append('Pro Se Litigants')
    if 'all part' in s or 'any part' in s or 'litigant' in s:
        if 'Pro Se Litigants' not in parties:
            parties.append('Any Parties')
    if parties:
        out['applies_to'] = ','.join(parties)

    # AI use case
    uses = []
    if 'draft' in s:
        uses.append('Draft')
    if 'research' in s:
        uses.append('Research')
    if 'filing' in s and 'prepar' in s:
        uses.append('Prepare')
    if uses:
        out['ai_use_case_for_filings'] = ','.join(uses)

    return out


def main():
    with open(INPUT) as f:
        data = json.load(f)
    results = data['results']

    all_columns = RAILS_COLUMNS + EXTRA_COLUMNS
    cleaned = []

    for rec in results:
        out = {col: '' for col in all_columns}

        # Direct mappings
        link = rec.get('linkToCourtOrder', {})
        out['document_name'] = link.get('text', '')
        out['link_to_source'] = link.get('url', '')
        out['state'] = rec.get('state', '')
        out['country'] = 'US'  # R&G is US-focused

        # Court
        court_array = rec.get('court', [])
        court_full, court_abbr = extract_court_abbreviation(court_array)
        out['court'] = court_full
        out['court_original'] = court_full
        out['court_abbreviation'] = court_abbr
        out['court_type'] = infer_court_type(court_array)

        # Judge
        judge_array = rec.get('judge', [])
        judge_full, title, name, last = parse_judge(judge_array)
        out['judge_author'] = judge_full
        out['judge_title'] = title
        out['judge_name_clean'] = name
        out['judge_last_name'] = last

        # Date
        out['date_yyyy_mm'] = parse_date(rec.get('effectiveDate', ''))

        # R&G-specific
        out['rg_id'] = rec.get('id', '')
        tags = rec.get('applicableTo', [])
        out['rg_tags'] = ', '.join(tags)
        out['rg_summary'] = strip_html(rec.get('summary', ''))
        out['rg_consequences_attorneys'] = 'checked' if 'Court-Imposed Consequences - Attorneys/Law Firms' in tags else ''
        out['rg_consequences_parties'] = 'checked' if 'Court-Imposed Consequences - Parties' in tags else ''

        # Extract RAILS columns from summary + tags
        extracted = extract_from_summary(out['rg_summary'], tags)
        for k, v in extracted.items():
            if k in out:
                out[k] = v

        cleaned.append(out)

    with open(OUTPUT, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=all_columns)
        writer.writeheader()
        writer.writerows(cleaned)

    # Summary
    dates = [r['date_yyyy_mm'] for r in cleaned if r['date_yyyy_mm']]
    print(f"R&G cleaned: {len(cleaned)} rows")
    print(f"Date range: {min(dates)} to {max(dates)}" if dates else "No dates")

    # Tag distribution
    from collections import Counter
    all_tags = []
    for rec in results:
        all_tags.extend(rec.get('applicableTo', []))
    tc = Counter(all_tags)
    print("\nTag distribution:")
    for tag, n in tc.most_common():
        print(f"  {n:3d} {tag}")

    # Fill rates for RAILS classification columns
    classify_cols = RAILS_COLUMNS[11:]  # from ai_type onwards
    print("\nRAILS classification fill rates:")
    for col in classify_cols:
        filled = sum(1 for r in cleaned if r[col])
        print(f"  {col:50s} {filled:3d}/{len(cleaned)} ({100*filled/len(cleaned):.0f}%)")

    # Court abbreviation coverage
    with_abbr = sum(1 for r in cleaned if r['court_abbreviation'])
    print(f"\nCourt abbreviation extracted: {with_abbr}/{len(cleaned)}")

    print(f"\nOutput: {OUTPUT}")


if __name__ == '__main__':
    main()
