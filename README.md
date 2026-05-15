# AI Court Orders — Data Pipeline & Analysis

Data pipeline for merging, enriching, and analyzing 663 court orders and opinions on AI use in legal proceedings (May 2023 -- May 2026). Powers the [AI Court Orders Explorer](https://legalhack.io/en/data/ai-court-orders) on legalhack.io.

## Data Sources

| Source | Records | Coverage |
|--------|---------|----------|
| [RAILS (Duke Law)](https://law.duke.edu/dclt/rails/) | ~500 | Standing orders, judicial opinions, local rules |
| [Ropes & Gray](https://www.ropesgray.com/en/sites/artificial-intelligence-court-order-tracker) | ~300 | Court orders with lawyer-written summaries |
| [CourtListener](https://www.courtlistener.com/) | — | Free links replacing paywalled Lexis/Westlaw sources |

After deduplication the merged dataset contains **663 unique entries**.

## Pipeline

```
data/sources/All_Data.csv          ─┐
                                     ├─ clean ─► merge ─► enrich ─► explorer_data.json
data/sources/ropes_gray_court_orders.json ─┘
```

| Step | Script | Description |
|------|--------|-------------|
| 1. Clean RAILS | `scripts/clean_rails.py` | Standardize RAILS CSV into common schema |
| 2. Clean R&G | `scripts/clean_rg.py` | Convert R&G JSON into RAILS schema format |
| 3. Merge | `scripts/merge.py` | Deduplicate and merge both sources |
| 4. Enrich | `scripts/enrich.py` | Classify R&G-only rows with Claude Haiku |
| 5. Apply enrichments | `scripts/enrich_direct.py` | Write classifications back to merged dataset |
| 6. Find free links | `scripts/batch_cl_search_v2.py` | Search CourtListener API for free alternatives to paywalled links |
| 7. Apply links | `scripts/apply_cl_links.py` | Replace Lexis URLs with CourtListener URLs |
| 8. Analysis | `scripts/analysis.py` | Generate summary stats and Plotly charts |

## Output

- **`data/processed/explorer_data.json`** — Final dataset (663 entries) used by the interactive explorer
- **`charts/`** — 13 standalone Plotly HTML charts (cumulative growth, sanctions timeline, orders by state, etc.)

## Setup

```bash
# CourtListener API key (needed for link search scripts only)
export CL_API_KEY="your-key-here"

# Run the pipeline
python3 scripts/clean_rails.py
python3 scripts/clean_rg.py
python3 scripts/merge.py
python3 scripts/enrich.py
python3 scripts/enrich_direct.py
python3 scripts/batch_cl_search_v2.py
python3 scripts/apply_cl_links.py
python3 scripts/analysis.py
```

## Project Retrospective

See [RETROSPECTIVE.md](RETROSPECTIVE.md) for lessons learned on building data viz tools with AI assistance.

## License

Data sourced from public court records via RAILS and Ropes & Gray. Scripts and analysis are open source.
