# AI Court Orders — Data Pipeline & Analysis

Data pipeline for tracking court orders and opinions on AI use in legal proceedings. Powers the [AI Court Orders Explorer](https://legalhack.io/explorer) on legalhack.io.

## Data Sources

| Source | Used for | Access |
|--------|----------|--------|
| [Ropes & Gray AI Court Order Tracker](https://www.ropesgray.com/en/sites/artificial-intelligence-court-order-tracker) | **Primary** — court orders & opinions (Sitecore API) | JSON API |
| [Legal AI Governance](https://legalaigovernance.com/) | Bar opinions refresh (`bar_opinions.json`) | JSON |
| [CourtListener](https://www.courtlistener.com/) | Free-link replacement for paywalled (Lexis) links + coverage cross-check | REST API |

## Updating the data

```bash
export OPENROUTER_API_KEY="…"   # required: AI conversion of new entries
export CL_API_KEY="…"           # optional: CourtListener link replacement / cross-check

python3 scripts/update.py             # incremental: fetch R&G, append new entries, swap Lexis→CL links
python3 scripts/update.py --backfill  # one-time: replace Lexis links across ALL existing entries
./scripts/weekly_update.sh            # wrapper that runs update.py
```

`update.py` is the **canonical pipeline**. It:
1. Loads existing `explorer_data.json` and **appends** only new entries (never regenerates — existing records are preserved)
2. Fetches the R&G Sitecore API, dedups on `YYYY-MM` + state + judge, converts new entries via OpenRouter AI (regex fallback), stores **full `YYYY-MM-DD` dates**
3. Replaces Lexis paywalled links with free CourtListener links
4. Writes `data/processed/explorer_data.json` **and** mirrors it to `charts/data/explorer_data.json` (the deploy source)
5. Runs a CourtListener cross-check and logs possible-missing cases to `data/processed/cl_review.json` (review queue — not auto-merged)

> `scripts/update_rg_data.py` (DEPRECATED) and `scripts/discover_orders.py` (EXPERIMENTAL) are kept for reference only — **do not use them**; `update.py` is canonical.

## Output

- **`data/processed/explorer_data.json`** — court orders & opinions for the explorer (also mirrored to `charts/data/`)
- **`data/processed/bar_opinions.json`** — state bar AI guidance
- **`charts/explorer.html`** — the explorer app (hand-maintained; see brand-header note below)
- **`charts/*.html`** — standalone Plotly charts
- Generated intermediates/logs in `data/processed/` (batch files, `cl_review.json`, search queues, etc.) are gitignored.

## Hosting note: brand header

`charts/explorer.html` includes an optional **legalhack.io brand header** (logo + site nav) at the top of `<body>`, marked by the comment block:

```
<!-- legalhack.io BRAND HEADER (optional) ... -->  …  <!-- END legalhack.io BRAND HEADER -->
```

It's self-contained (inline styles) and references the site logo by absolute path, so it only renders correctly when hosted on legalhack.io. **To run the explorer standalone elsewhere, delete that block.**

## License

Data sourced from public court records via [Ropes & Gray](https://www.ropesgray.com/en/sites/artificial-intelligence-court-order-tracker), [Legal AI Governance](https://legalaigovernance.com/), and [CourtListener](https://www.courtlistener.com/). Scripts and analysis are open source.
