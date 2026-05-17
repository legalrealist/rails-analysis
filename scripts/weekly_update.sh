#!/bin/bash
# Weekly update pipeline for AI Court Orders Explorer
# Fetches latest data from sources, merges, and regenerates charts.
#
# Usage: ./scripts/weekly_update.sh

set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== AI Court Orders Explorer — Weekly Update ==="
echo "$(date)"
echo

# 1. Fetch bar opinions from Legal AI Governance
echo "1. Fetching bar opinions..."
curl -sS https://legalaigovernance.com/data/opinions.json -o data/processed/bar_opinions.json
echo "   Done. $(python3 -c "import json; d=json.load(open('data/processed/bar_opinions.json')); print(f'{d.get(\"count\", len(d.get(\"items\", [])))} jurisdictions')")"

# 2. Scrape Ropes & Gray (requires Playwright)
echo "2. Scraping Ropes & Gray tracker..."
if python3 -c "import playwright" 2>/dev/null; then
    python3 scripts/scrape_rg.py
else
    echo "   SKIP: Playwright not installed. Run: pip install playwright && playwright install chromium"
fi

# 3. Regenerate charts
echo "3. Regenerating charts..."
python3 scripts/analysis.py

# 4. Report unclassified sanctions
echo "4. Checking for unclassified sanctions..."
python3 scripts/report_unclassified.py

# 5. Sync data to charts/data for explorer
echo "5. Syncing data to charts/data..."
cp data/processed/explorer_data.json charts/data/
cp data/processed/bar_opinions.json charts/data/
echo "   Done."

echo
echo "=== Update complete ==="
