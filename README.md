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

## Deployment

The explorer and the main site deploy by **two independent paths** to Hostinger (shared hosting, hPanel):

```
This repo (AI-orders-explorer)                 legalhack.io repo (Grav site)
  charts/ + data + index.html + .htaccess        user/pages, themes, index.php
        │                                                │
   hPanel Git (manual "Deploy")                    deploy.sh  (rsync over SSH)
        ▼                                                ▼
  legalhack.io/explorer                          legalhack.io  (rest of the Grav site)
```

**Explorer → `legalhack.io/explorer`** (this repo):
- hPanel → Websites → legalhack.io → Advanced → GIT → repo `AI-orders-explorer`, branch `main`, install path `public_html/explorer`, then click **Deploy**.
- `index.html` redirects `/explorer/` → `charts/explorer.html`; `.htaccess` serves only the app and blocks `scripts/`, `data/`, source files.
- Data ships in the repo (`charts/data/`), so a Deploy publishes data + app together.

**Grav site → `legalhack.io`** (the *other* repo + a local script):
- The Grav site lives in a separate repo (`legalrealist/legalhack.io`, a backup mirror) and is pushed to Hostinger by `deploy.sh`, which lives in the **legalhack project root** (`/Users/hao/legalhack/deploy.sh`) — **not committed** (contains the server address). It rsyncs `public_html/` to Hostinger, **excludes `/explorer`** (managed by hPanel Git) and server-owned runtime (`cache/`, `logs/`, etc.), and takes a snapshot backup first.

**End-to-end after a data update:** run `update.py` → commit & push this repo → click **Deploy** in hPanel. Landing-page order counts read live from `/explorer/charts/data/explorer_data.json`.

## Hosting note: brand header

`charts/explorer.html` includes an optional **legalhack.io brand header** (logo + site nav) at the top of `<body>`, marked by the comment block:

```
<!-- legalhack.io BRAND HEADER (optional) ... -->  …  <!-- END legalhack.io BRAND HEADER -->
```

It's self-contained (inline styles) and references the site logo by absolute path, so it only renders correctly when hosted on legalhack.io. **To run the explorer standalone elsewhere, delete that block.**

## License

Data sourced from public court records via [Ropes & Gray](https://www.ropesgray.com/en/sites/artificial-intelligence-court-order-tracker), [Legal AI Governance](https://legalaigovernance.com/), and [CourtListener](https://www.courtlistener.com/). Scripts and analysis are open source.
