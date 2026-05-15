# AI Court Orders Explorer — Project Retrospective

## Project Summary
Built an interactive explorer for 663 court orders and opinions on AI use in legal proceedings (May 2023 -- May 2026), combining the RAILS (Duke Law) and Ropes & Gray trackers. Single-page app embedded in Grav CMS via `rawhtml.md` template. Features: SVG choropleth map, full-text search (MiniSearch), multi-filter system with dynamic dropdowns, judge-grouped list with detail panel, free CourtListener links replacing Lexis paywalls.

**Live URL:** https://legalhack.io/en/data/ai-court-orders

---

## What Went Wrong

### 1. No design spec upfront
Jumped straight to code. The layout went through three major iterations:
- Original: bipanel with map + filters + list on left, detail on right
- User feedback: "bipanel isn't right, should be map and filter at top and then the entry at bottom"
- Final: map/filters full-width on top, list + detail side-by-side below

That single pivot touched every CSS rule and the HTML structure. A 5-minute wireframe sketch would have caught this before any code was written.

### 2. Single-file architecture made changes expensive
Everything — 800+ lines of CSS, HTML, and JS — lives in one `rawhtml.md` file. The Grav `rawhtml` template forced everything into one blob. Every change required reading through the whole file, and edits risked breaking unrelated things. A standard project would have separate CSS, JS module, and template.

### 3. Verification loop was broken
The Claude in Chrome MCP lost access to legalhack.io mid-session and never recovered (per-domain restriction in the MCP bridge layer, independent of Chrome extension permissions). Instead of see -> fix -> see -> done, the cycle became: fix -> deploy -> "does this look right?" -> user describes what's wrong -> guess -> fix -> deploy -> repeat. Half the back-and-forth was compensating for not being able to see the page.

### 4. Requirements emerged incrementally
These requests came one at a time across many turns:
- "Remove stats bar"
- "Remove date filters"
- "Remove has link chip"
- "Remove R&G badges"
- "Clean up the top"
- "Just leave search bar"

Each was trivial individually but collectively they were a full redesign. Asking "what elements do you actually want?" upfront would have been one pass instead of six.

### 5. Data quality discovered late
Judge name normalization (25+ duplicate groups — missing initials, title variations, accent differences, typos) was found only after the UI was working and split entries were visible. Should have been caught during data processing, before the UI was built.

---

## What Should Have Happened

### Phase 1: Study the competitor (20 min)
Start by screenshotting and analyzing the R&G tracker — the existing product users already know. Document what it does well (flat scannable table, lawyer-written summaries, clean filters) and what it's missing (no map, no judge grouping, paywalled links, no search). This gives you a concrete design baseline instead of inventing from scratch. The competitor's layout decisions encode real user research — they built it for practicing lawyers. Use that for free.

### Phase 2: Data first (30 min)
Clean the data before touching any UI. Duplicate analysis, judge name normalization, link validation, missing field checks. Dirty data means every UI decision is based on wrong counts and split entries.

### Phase 3: Design against the competitor (15 min)
With the R&G tracker as reference, define what to keep, what to improve, and what to add:
- **Keep:** Their filter categories (type, state, outcome) — proven useful
- **Improve:** Group by judge instead of flat table (our differentiator), replace paywalled links with free ones
- **Add:** Map, fuzzy search, mobile support
- **Cut:** Anything not in the competitor AND not clearly needed — start minimal

This conversation anchored to a real product would have prevented the layout restructure, the six rounds of element removal, and the scroll target fixes. Instead of "what do you want?" in the abstract, it's "like R&G but with these specific changes."

### Phase 4: Build with local preview (2 hours)
Use a local Grav server or `python3 -m http.server` for instant feedback instead of deploying to production after every change. No dependency on browser MCP that can break.

### Phase 5: One deployment at the end
Ship when it's done, not 15 times during iteration.

---

## Key Lesson
**Start from the competitor, not from a blank canvas.** The R&G tracker already exists and encodes real design decisions made for real lawyer users. Instead of inventing a layout and iterating through three versions, we should have screenshotted R&G, said "like this but grouped by judge, with a map, and free links," and built exactly that. Most of the back-and-forth was rediscovering design choices that R&G had already made — filter categories, what metadata to show, how much density is too much. When you're building a better version of something that exists, the existing thing *is* your spec.

---

## Technical Details

### Architecture
- **CMS:** Grav with `rawhtml.html.twig` template (renders page content as raw HTML)
- **File:** `/Users/hao/legalhack/public_html/user/pages/05.Data/ai-court-orders/rawhtml.md`
- **Data:** `/Users/hao/legalhack/public_html/assets/data/explorer_data.json` (663 entries)
- **Search:** MiniSearch library (prefix, fuzzy, AND combiner)
- **Map:** SVG choropleth, hardcoded `LABEL_POS` coordinates, viewBox 0 0 959 593
- **Deploy:** `cd /Users/hao/legalhack && bash deploy.sh` (rsync to hosting)

### Data Pipeline
- RAILS (Duke Law) + Ropes & Gray trackers merged
- CourtListener API used to find free links replacing Lexis paywalls (`batch_cl_search_v2.py`)
- Judge name normalization: 22 mapping rules, 27 entries updated

### Features Implemented
- Collapsible SVG choropleth map with sessionStorage persistence
- Full-text fuzzy search (judges, courts, states)
- Multi-filter: type, state, judge (dynamic), outcome, sector + boolean chips
- Active filter chip bar with removable pills
- Judge-grouped list with entry counts, sorted by most entries
- Timeline detail panel with type badges, consequence tags, requirement pills
- Truncation warning (500+ results)
- Mobile scroll-to-detail on judge select
- Loading/error states for data fetch

### Comparison vs Ropes & Gray Tracker
| Feature | This Explorer | R&G Tracker |
|---------|--------------|-------------|
| Access | Free, instant load | Law firm site, cookie wall |
| Data | 663 entries (merged) | ~400 (R&G subset only) |
| Map | SVG choropleth | None |
| Grouping | By judge | Flat table |
| Links | Free (CourtListener) | Paywalled (Westlaw/Lexis) |
| Search | Fuzzy full-text | Basic column filters |
| Brand | Unknown | BigLaw authority |
| Curation | Inherited summaries | Lawyer-written |
| Export | Not yet | PDF/download |
