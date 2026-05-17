#!/bin/bash
# Build rawhtml.md for Grav from the canonical explorer.html
# Extracts content between GRAV-EXTRACT markers, prepends frontmatter.
#
# Usage: ./scripts/build_grav.sh [OUTPUT_PATH]

set -euo pipefail
cd "$(dirname "$0")/.."

SRC="charts/explorer.html"
DEFAULT_OUT="/Users/hao/legalhack/public_html/user/pages/05.Data/ai-court-orders/rawhtml.md"
OUT="${1:-$DEFAULT_OUT}"

if [ ! -f "$SRC" ]; then
  echo "ERROR: $SRC not found" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUT")"

cat > "$OUT" <<'FRONTMATTER'
---
title: 'AI Court Orders Explorer'
published: true
process:
    markdown: false
    twig: false
metadata:
    description: 'Check if your court or judge has an AI standing order, warning, or sanctions case.'
---
<script>window.__DATA_BASE = '/assets/data';</script>
FRONTMATTER

sed -n '/<!-- GRAV-EXTRACT-START -->/,/<!-- GRAV-EXTRACT-END -->/p' "$SRC" \
  | sed 's|<script src="minisearch.min.js"></script>|<script src="https://cdn.jsdelivr.net/npm/minisearch@7.1.1/dist/umd/index.min.js"></script>|' \
  >> "$OUT"

ASSETS_DIR="$(dirname "$OUT")/../../../../assets/data"
mkdir -p "$ASSETS_DIR"
cp charts/data/explorer_data.json "$ASSETS_DIR/"
cp charts/data/bar_opinions.json "$ASSETS_DIR/"

echo "Built $OUT"
echo "Copied data to $ASSETS_DIR/"
