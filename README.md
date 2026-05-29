# AI Court Orders — Data Pipeline & Analysis

Data pipeline for tracking court orders and opinions on AI use in legal proceedings. Powers the [AI Court Orders Explorer](https://legalhack.io/en/data/ai-court-orders) on legalhack.io.

## Data Sources

| Source | Data | Format |
|--------|------|--------|
| [Legal AI Governance](https://legalaigovernance.com/) | Court orders, sanctions cases, bar opinions | JSON API |
| [CourtListener](https://www.courtlistener.com/) | Cross-check for coverage gaps | REST API |

## Weekly Update

```bash
# One command pulls everything
python3 scripts/update.py

# With CourtListener cross-check (flags entries not in legalaigovernance)
export CL_API_KEY="your-key-here"
python3 scripts/update.py --cl-check

# Full update including chart regeneration
./scripts/weekly_update.sh
```

`update.py` fetches from legalaigovernance.com's JSON endpoints, transforms to the explorer schema, and optionally queries CourtListener for recent AI-related orders that may be missing. Gaps are flagged in `data/processed/cl_review.json` for manual review — not auto-merged.

## Output

- **`data/processed/explorer_data.json`** — Court orders and sanctions cases for the interactive explorer
- **`data/processed/bar_opinions.json`** — State bar AI guidance (51 jurisdictions)
- **`data/processed/cl_review.json`** — CourtListener entries flagged for review (if `--cl-check`)
- **`charts/`** — Standalone Plotly HTML charts (cumulative growth, sanctions timeline, orders by state, etc.)

## Hosting note: brand header

`charts/explorer.html` includes an optional **legalhack.io brand header** (logo + site nav) at the top of `<body>`, marked by the comment block:

```
<!-- legalhack.io BRAND HEADER (optional) ... -->  …  <!-- END legalhack.io BRAND HEADER -->
```

It's self-contained (inline styles) and references the site logo by absolute path, so it only renders correctly when hosted on legalhack.io. **To run the explorer standalone elsewhere, delete that block.**

## License

Data sourced from public court records via [Legal AI Governance](https://legalaigovernance.com/) and [CourtListener](https://www.courtlistener.com/). Scripts and analysis are open source.
