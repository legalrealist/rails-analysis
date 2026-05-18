#!/usr/bin/env python3
"""Validate explorer_data.json against known constraints."""
import json
import sys
from collections import Counter

DATA_PATH = "charts/data/explorer_data.json"

VALID_TYPE = {"Judicial Opinion", "Standing Order", "Administrative Order", "Local Rules", "Practice Direction"}
VALID_AI_TYPE = {"Any AI", "Gen AI", "Gen AI, excluding standard research tools"}
VALID_SOURCE = {"rails", "rg", "both"}
VALID_OUTCOME = {"", "warning", "sanctions_attorney", "sanctions_party"}
VALID_SANCTION_TYPES = {"monetary", "bar_referral", "admonishment", "contempt", "dismissal", "show_cause", "striking", "cle"}

REQUIRED_NONEMPTY = ["id", "type", "source", "ai_type", "summary", "jurisdiction"]
WARN_IF_EMPTY = ["judge", "court", "state", "applies_to", "date"]

def validate():
    with open(DATA_PATH) as f:
        data = json.load(f)

    errors = []
    warnings = []

    ids_seen = set()
    for i, d in enumerate(data):
        prefix = f"  #{d.get('id', i)}"

        # Duplicate IDs
        eid = d.get("id")
        if eid in ids_seen:
            errors.append(f"{prefix}: duplicate id={eid}")
        ids_seen.add(eid)

        # Required non-empty fields
        for field in REQUIRED_NONEMPTY:
            val = d.get(field)
            if val is None or (isinstance(val, str) and not val.strip()):
                errors.append(f"{prefix}: required field '{field}' is empty/missing")

        # Warn if empty
        for field in WARN_IF_EMPTY:
            val = d.get(field)
            if val is None or (isinstance(val, str) and not val.strip()):
                warnings.append(f"{prefix}: '{field}' is empty")

        # Enum: type
        if d.get("type") not in VALID_TYPE:
            errors.append(f"{prefix}: invalid type='{d.get('type')}'")

        # Enum: ai_type
        if d.get("ai_type") not in VALID_AI_TYPE:
            errors.append(f"{prefix}: invalid ai_type='{d.get('ai_type')}'")

        # Enum: source
        if d.get("source") not in VALID_SOURCE:
            errors.append(f"{prefix}: invalid source='{d.get('source')}'")

        # Enum: sanctions_outcome
        outcome = d.get("sanctions_outcome", "")
        if outcome not in VALID_OUTCOME:
            errors.append(f"{prefix}: invalid sanctions_outcome='{outcome}'")

        # reqs must be dict
        reqs = d.get("reqs", {})
        if not isinstance(reqs, dict):
            errors.append(f"{prefix}: reqs is {type(reqs).__name__}, should be dict")

        # sanction_types must be dict
        st = d.get("sanction_types", {})
        if not isinstance(st, dict):
            errors.append(f"{prefix}: sanction_types is {type(st).__name__}, should be dict")
            continue

        types = st.get("types", [])

        # Validate sanction type values
        for t in types:
            if t not in VALID_SANCTION_TYPES:
                errors.append(f"{prefix}: invalid sanction type '{t}'")

        # Cross-field: sanctions outcome ↔ sanction_types
        if outcome in ("sanctions_attorney", "sanctions_party"):
            if not types:
                errors.append(f"{prefix}: sanctions_outcome='{outcome}' but sanction_types.types is empty")
        elif outcome in ("", "warning"):
            if types:
                warnings.append(f"{prefix}: sanctions_outcome='{outcome}' but has sanction_types={types}")

        # Cross-field: monetary → amount should exist
        if "monetary" in types:
            if not st.get("amount_awarded") and not st.get("amount_sought"):
                warnings.append(f"{prefix}: sanction type 'monetary' but no amount_awarded or amount_sought")

        # Amount must be numeric
        for amt_field in ("amount_awarded", "amount_sought"):
            val = st.get(amt_field)
            if val is not None and not isinstance(val, (int, float)):
                errors.append(f"{prefix}: {amt_field} is {type(val).__name__} '{val}', should be numeric")

        # Warning: prohibited + disclose combo
        if isinstance(reqs, dict) and "prohibited" in reqs and "disclose" in reqs:
            warnings.append(f"{prefix}: has both 'prohibited' and 'disclose' in reqs")

        # Warning: standing order with sanctions
        if d.get("type") in ("Standing Order", "Local Rules", "Administrative Order") and outcome in ("sanctions_attorney", "sanctions_party"):
            warnings.append(f"{prefix}: {d.get('type')} has sanctions_outcome='{outcome}'")

    # Print results
    if errors:
        print(f"ERRORS ({len(errors)}):")
        for e in errors:
            print(e)
        print()

    if warnings:
        print(f"WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(w)
        print()

    print(f"SUMMARY: {len(errors)} errors, {len(warnings)} warnings across {len(data)} entries")

    # Stats
    outcomes = Counter(d.get("sanctions_outcome", "") for d in data)
    print(f"  sanctions_outcome distribution: {dict(outcomes)}")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(validate())
