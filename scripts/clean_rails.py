#!/usr/bin/env python3
"""Clean RAILS All_Data.csv into standardized format."""

import csv
import re
import os

INPUT = os.path.join(os.path.dirname(__file__), '..', 'data', 'sources', 'All_Data.csv')
OUTPUT = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'rails_clean.csv')

COLUMN_MAP = {
    'Document Name': 'document_name',
    'Link to Source': 'link_to_source',
    'Document Type': 'document_type',
    'Judge/Author': 'judge_author',
    'Court Type': 'court_type',
    'Country': 'country',
    'State': 'state',
    'Court': 'court',
    'Date (MM/YYYY)': 'date_mm_yyyy',
    'Order Type': 'order_type',
    'Case Types': 'case_types',
    'AI Type?': 'ai_type',
    'AI Use Case for Filings?': 'ai_use_case_for_filings',
    'Prohibited?': 'prohibited',
    'Disclose AI Use w/ Each Filing?': 'disclose_ai_use_w_each_filing',
    'Disclose AI Tool Used?': 'disclose_ai_tool_used',
    'Disclose How AI Tool Used?': 'disclose_how_ai_tool_used',
    'Identify Sections Drafted with AI?': 'identify_sections_drafted_with_ai',
    'Disclose Process Used to Check Accuracy': 'disclose_process_used_to_check_accuracy',
    'All Parties Certify Accuracy or Non-Use on Notice of Appearance?': 'certify_accuracy_non_use_on_notice',
    'All Parties Certify Accuracy or Non-Use w/ each Filing?': 'certify_accuracy_non_use_w_each_filing',
    'Certify Accuracy, if Planning to Use AI during Case?': 'certify_accuracy_if_planning_to_use_ai',
    'Certify No Unauthorized Disclosure': 'certify_no_unauthorized_disclosure',
    "Certify Accuracy w/ Each Filing, only if AI Used?": 'certify_accuracy_w_each_filing_if_ai_used',
    'Just a Warning to Follow Existing Court and Ethics Rules when using AI?': 'just_a_warning',
    'References Other Procedural Rules?': 'references_other_procedural_rules',
    'Maintain AI Prompt Records?': 'maintain_ai_prompt_records',
    'Proprietary / Confidential Info NonDisclosure Req?': 'proprietary_info_nondisclosure_req',
    'Disclose Use of AI-Generated Evidence?': 'disclose_ai_generated_evidence',
    'Provide Notice to Opposing Parties of AI-Generated Evidence?': 'notice_to_opposing_parties_ai_evidence',
    'Use of AI to Record in Courtroom?': 'ai_to_record_in_courtroom',
    'Applies To': 'applies_to',
    'Other Reqs, Notes': 'other_reqs_notes',
}

STATE_ABBREVS = {
    'Alabama': 'Ala.', 'Alaska': 'Alaska', 'Arizona': 'Ariz.', 'Arkansas': 'Ark.',
    'California': 'Cal.', 'Colorado': 'Colo.', 'Connecticut': 'Conn.',
    'Delaware': 'Del.', 'Florida': 'Fla.', 'Georgia': 'Ga.',
    'Hawaii': 'Haw.', 'Idaho': 'Idaho', 'Illinois': 'Ill.',
    'Indiana': 'Ind.', 'Iowa': 'Iowa', 'Kansas': 'Kan.',
    'Kentucky': 'Ky.', 'Louisiana': 'La.', 'Maine': 'Me.',
    'Maryland': 'Md.', 'Massachusetts': 'Mass.', 'Michigan': 'Mich.',
    'Minnesota': 'Minn.', 'Mississippi': 'Miss.', 'Missouri': 'Mo.',
    'Montana': 'Mont.', 'Nebraska': 'Neb.', 'Nevada': 'Nev.',
    'New Hampshire': 'N.H.', 'New Jersey': 'N.J.', 'New Mexico': 'N.M.',
    'New York': 'N.Y.', 'North Carolina': 'N.C.', 'North Dakota': 'N.D.',
    'Ohio': 'Ohio', 'Oklahoma': 'Okla.', 'Oregon': 'Or.',
    'Pennsylvania': 'Pa.', 'Rhode Island': 'R.I.', 'South Carolina': 'S.C.',
    'South Dakota': 'S.D.', 'Tennessee': 'Tenn.', 'Texas': 'Tex.',
    'Utah': 'Utah', 'Vermont': 'Vt.', 'Virginia': 'Va.',
    'Washington': 'Wash.', 'West Virginia': 'W. Va.', 'Wisconsin': 'Wis.',
    'Wyoming': 'Wyo.',
}

DIRECTION_MAP = {
    'Northern': 'N.D.', 'Southern': 'S.D.', 'Eastern': 'E.D.',
    'Western': 'W.D.', 'Central': 'C.D.', 'Middle': 'M.D.',
}

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


def parse_date(raw):
    """Convert MM/YYYY to YYYY-MM."""
    raw = raw.strip()
    if not raw:
        return ''
    m = re.match(r'^(\d{1,2})/(\d{4})$', raw)
    if m:
        return f"{m.group(2)}-{int(m.group(1)):02d}"
    return raw


def normalize_court(court_name):
    """Convert verbose RAILS court name to standard abbreviation."""
    name = court_name.strip()
    if not name or name == '-':
        return ''

    # "US DC [Direction] District of [State]" pattern (case-insensitive "of")
    m = re.match(r'US DC (?:of )?(\w+) District [oO]f (.+?)(?:,.*)?$', name)
    if m:
        direction = m.group(1)
        state = m.group(2).strip()
        dir_abbr = DIRECTION_MAP.get(direction, '')
        st_abbr = STATE_ABBREVS.get(state, state)
        if dir_abbr:
            return f"{dir_abbr} {st_abbr}"
        return f"D. {st_abbr}"

    # "US DC District of [State]" (no direction)
    m = re.match(r'US DC District of (.+?)(?:,.*)?$', name)
    if m:
        state = m.group(1).strip()
        st_abbr = STATE_ABBREVS.get(state, state)
        return f"D. {st_abbr}"

    # Bankruptcy courts
    m = re.match(r'US Bankruptcy Court (\w+) District of (.+?)$', name)
    if m:
        direction = m.group(1)
        state = m.group(2).strip()
        dir_abbr = DIRECTION_MAP.get(direction, '')
        st_abbr = STATE_ABBREVS.get(state, state)
        if dir_abbr:
            return f"Bankr. {dir_abbr} {st_abbr}"
        return f"Bankr. D. {st_abbr}"

    # "US Bankruptcy Court Souther District of New York" (typo in data)
    m = re.match(r'US Bankruptcy Court Souther\w* District of (.+?)$', name)
    if m:
        state = m.group(1).strip()
        st_abbr = STATE_ABBREVS.get(state, state)
        return f"Bankr. S.D. {st_abbr}"

    # Appeals courts
    m = re.match(r'US Court of Appeals (.+) Circuit', name)
    if m:
        return f"{m.group(1)} Cir."

    # Court of International Trade
    if 'International Trade' in name:
        return 'Ct. Int\'l Trade'

    # State and international courts - return as-is
    return name


def parse_judge(raw):
    """Extract title, full name (no prefix), and last name from judge string."""
    raw = raw.strip()
    if not raw:
        return '', '', ''

    # Take first judge if multiple separated by ";"
    first = raw.split(';')[0].strip()

    title = ''
    name = first
    for prefix in JUDGE_PREFIXES:
        if first.startswith(prefix):
            title = prefix.strip()
            name = first[len(prefix):].strip()
            break

    # Extract last name: handle suffixes like Jr., III, Sr., IV
    parts = name.split()
    if not parts:
        return title, name, ''

    suffixes = {'Jr.', 'Jr', 'Sr.', 'Sr', 'II', 'III', 'IV', 'V'}
    last = parts[-1].rstrip(',')
    if last in suffixes and len(parts) > 1:
        last = parts[-2].rstrip(',')

    return title, name, last


def main():
    with open(INPUT, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    cleaned = []
    missing_judge = 0
    missing_court = 0

    for row in rows:
        out = {}
        for orig, snake in COLUMN_MAP.items():
            out[snake] = row.get(orig, '').strip()

        out['date_yyyy_mm'] = parse_date(out['date_mm_yyyy'])
        del out['date_mm_yyyy']

        out['court_original'] = out['court']
        out['court_abbreviation'] = normalize_court(out['court'])

        title, name, last = parse_judge(out['judge_author'])
        out['judge_title'] = title
        out['judge_name_clean'] = name
        out['judge_last_name'] = last

        if not out['judge_author']:
            missing_judge += 1
        if not out['court'] or out['court'] == '-':
            missing_court += 1

        cleaned.append(out)

    fieldnames = list(cleaned[0].keys())
    with open(OUTPUT, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(cleaned)

    # Summary
    dates = [r['date_yyyy_mm'] for r in cleaned if r['date_yyyy_mm']]
    print(f"RAILS cleaned: {len(cleaned)} rows")
    print(f"Date range: {min(dates)} to {max(dates)}" if dates else "No dates")
    print(f"Missing judge: {missing_judge}")
    print(f"Missing court: {missing_court}")
    print(f"Output: {OUTPUT}")

    # Check court normalization
    abbrevs = set(r['court_abbreviation'] for r in cleaned if r['court_abbreviation'])
    print(f"\nUnique court abbreviations ({len(abbrevs)}):")
    for a in sorted(abbrevs):
        print(f"  {a}")


if __name__ == '__main__':
    main()
