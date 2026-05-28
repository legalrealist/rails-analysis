#!/bin/bash
# Weekly update pipeline for AI Court Orders Explorer
# Fetches R&G (ground truth), incremental append, CL cross-check.
#
# Usage: ./scripts/weekly_update.sh

set -euo pipefail
cd "$(dirname "$0")/.."

python3 scripts/update.py

echo
echo "=== Weekly update complete ==="
