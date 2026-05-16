#!/usr/bin/env python3
"""Report sanctions entries that don't have sanction_types classified yet."""

import json
import os

INPUT = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'explorer_data.json')


def main():
    with open(INPUT) as f:
        data = json.load(f)

    sanctions = [e for e in data if e.get('consequence', '') in ('sanctions_party', 'sanctions_attorney')]
    unclassified = [e for e in sanctions if not e.get('sanction_types')]

    if not unclassified:
        print(f"All {len(sanctions)} sanctions entries are classified.")
        return

    print(f"{len(unclassified)} of {len(sanctions)} sanctions entries need classification:\n")
    for e in unclassified:
        print(f"  ID {e['id']:4d}  {e.get('judge', 'unknown'):30s}  {e.get('court', ''):20s}  {e.get('date', '')}")
        if e.get('summary'):
            print(f"           {e['summary'][:100]}...")
        print()

    print(f"\nTo classify, run a Claude Code session with these IDs.")


if __name__ == '__main__':
    main()
