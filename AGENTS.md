# AGENTS.md — GitHub Wrapped Neo4j

## Project Overview
GitHub Wrapped demo: imports GitHub activity CSVs into AuraDB, serves a Spotify-Wrapped-style
web app from GitHub Pages, GDS notebook for community detection, FastAPI MCP server.

## Feedback Instructions

No automated test suite yet. For Cypher files: validate syntax by reading carefully.
For Python: `python -m py_compile <file>` to check syntax.
For HTML/JS: Open in browser and check console for errors.

## Data

- `data/` contains 6 CSVs: persons (348 rows), repos (14), prs (32252), reviews (92721), files (52996), files_touched (206196)
- `prs.csv` labels field is semicolon-separated (e.g. `dependencies;plg`) — must split on `;` when creating Label nodes
- `files.csv` directory field can be empty (file at repo root)
- `reviews.csv` has a `body` field that may contain commas — treat carefully in LOAD CSV (it is quoted in the CSV)

## Schema

- `import/schema.cypher` — full DDL with constraints and indexes; run this FIRST before any LOAD CSV
- Constraints use `IF NOT EXISTS` — idempotent, safe to re-run
- Directory uniqueness is composite: `(path, repoId)` — same path can exist across repos
- PullRequest state values seen in data: OPEN, CLOSED, MERGED

## AuraDB Notes

- AuraDB Free: ≤200k nodes, ≤400k relationships
- Estimated nodes: ~50k (persons + repos + prs + files + dirs + labels)
- Estimated rels: ~400k (AUTHORED + REVIEWED + TOUCHES + IN_DIR + HAS_LABEL + IN_REPO + MERGED)
- IMPORTANT: files_touched has 206196 rows → each creates a TOUCHES rel → may approach limit
- Use MERGE not CREATE everywhere to keep scripts idempotent
- AuraDB HTTP transaction endpoint for web app: `POST {auraUri}/db/neo4j/tx/commit`

## Cypher Patterns

- `LOAD CSV WITH HEADERS FROM 'file:///...' AS row` — use `file:///` URI with AuraDB import bucket
  or paste directly into Neo4j Browser / Aura Query Editor
- For AuraDB: upload CSVs to the AuraDB-provided import URL (or use public GitHub raw URL)
- Split labels: `SPLIT(row.labels, ";")` in Cypher
- Parse integers: `toInteger(row.additions)`, booleans: `row.isDraft = "true"`
- Parse datetimes: `datetime(row.createdAt)`, handle nulls with `CASE WHEN row.mergedAt <> "" THEN datetime(row.mergedAt) ELSE null END`
- LOAD CSV URL must be a string literal — cannot use `:param csvBase` + string concat in LOAD CSV FROM clause
- For large CSVs (32k+ rows): split into multiple LOAD CSV passes in the same file to keep each query focused
- MERGE on (reviewer, pr) in reviews collapses multiple reviews per pair to one rel — intentional for analytics

## Capacity: Actual Node/Rel Counts (computed from data/)

- Nodes: ~98,849 (persons 348 + repos 14 + prs 32,252 + files 52,996 + dirs 12,701 + labels 538) — within 200k
- Rels: ~507,277 — EXCEEDS 400k Free tier limit by ~107k
- Culprit: TOUCHES (206,196 from files_touched.csv)
- Solution: Either paid AuraDB tier, or skip/limit files_touched import (hero stats don't need TOUCHES)

## Neo4j Duration Gotchas

- `duration.between(d1, d2).hours` — hours component of Duration (can be 0-23, NOT total hours)
- `duration.between(d1, d2).seconds` — seconds component (0-59, NOT total seconds)
- For total elapsed hours: `duration.inSeconds(d1, d2).seconds / 3600.0`
- `duration.inSeconds()` returns a Duration where `.seconds` IS total elapsed seconds

## NeoDash Dashboard JSON Format

- NeoDash 2.4 format: top-level `uuid`, `title`, `version`, `settings`, `pages`, `extensions`, `parameters`
- Each report requires: `id` (UUID string), `title`, `type`, `query`, `x`, `y`, `width`, `height`, `selection`, `settings`
- Grid is 12 columns wide; height is in row units
- Chart types: `text`, `bar`, `line`, `pie`, `table`, `graph`, `value`, `select`, `map`, `json`, `iframe`
- Bar chart `selection`: `{index: "ColA", value: "ColB", key: "(none)"}` — `index` is the category axis, `value` is the numeric axis
- Line chart `selection`: `{x: "ColA", value: ["ColB"]}` — `value` must be an array
- Pie chart `selection`: same as bar (`index`, `value`, `key`)
- Interactive params use `$neodash_paramname` convention (requires a `select` report wired up); bare `$param` works only if set in top-level `parameters` object
- Horizontal bar layout: set `settings.layout: "horizontal"` with larger `marginBottom` for long labels
- Import via NeoDash UI: Load Dashboard button → paste/upload JSON file
- Gallery examples at: https://github.com/neo4j-labs/neodash/tree/master/gallery/dashboards

## Cypher Pattern Scope Gotcha

- `WHERE NOT ()-[:REL]->()` is a GLOBAL pattern check (always true/false for entire graph)
- To scope to a bound node: `WHERE NOT ()-[:REL]->(p)` or `WHERE NOT (p)-[:REL]->()`

## Web App (docs/index.html) Notes

- Scaffold at `docs/index.html` — single HTML file, no build step, no external deps yet
- `runQuery(cypher, params)` POSTs to `{uri}/db/neo4j/tx/commit` with Basic auth; returns `Array<Object>` (de-pivoted from Neo4j columnar format)
- `safeQuery()` = runQuery + spinner + error toast; use this in stat sections, not raw runQuery
- Credentials stored in localStorage under key `github_wrapped_neo4j_creds` as `{uri, user, pass}` JSON
- Config panel validates with `RETURN 1 AS ok` before closing; clears creds on failure so stale creds don't persist
- Neo4j HTTP response format: `payload.results[0].columns` + `data[].row` — de-pivot with `columns.forEach((col,i) => obj[col] = row.row[i])`
- NVL graph div (`#collab-graph`) has explicit `height: 520px` on container — required for NVL to render (task-008)
- Section reveal: IntersectionObserver (threshold 0.08) adds `.visible` class → CSS opacity+translateY transition

## Hero stat pattern (task-006+)
- Hero sections use `.hero-number-block` → `.hero-rank` / `.hero-login` / `.hero-big-number` / `.hero-label` CSS layout
- `hero-big-number` uses `clamp(3.5rem, 8vw, 5.5rem)` monospace font for the large stat number
- Always use `escapeHtml()` before inserting any user-data (logins, label names) into innerHTML
- Great Deleter: uses TOUCHES rels — if not imported, query returns 0 rows → show friendly notice (not an error)
- Bug Slayer: `toLower(l.name) = 'bug'` for case-insensitive label match; `COUNT(DISTINCT pr)` avoids double-counting
- `loadDashboard()` calls `s.classList.add('visible')` on all sections immediately after login — hero stat fns fire in parallel via `loadGreatDeleter(); loadBugSlayer();` (not awaited)

## CRITICAL: Library / Technology Choices

**NEVER replace a library or technology the user has explicitly requested without asking first.**
If a library proves difficult to load or use, investigate root cause and ask the user before switching to an alternative.
This applies especially to NVL, neo4j-rust-ext, uv, and any other tool the user named in the original brief.

## NVL integration pattern (task-008)
- @neo4j-nvl/base ships **ESM only** (dist/base.mjs, ~1MB) — no UMD/CDN script tag build
- Use `<script type="importmap">` + `<script type="module">` bridge: expose `window.initNVLGraph` so classic scripts can call it
- NVL constructor: `new NVL(container, nodes, rels, options)` — 5th arg (callbacks) also accepted but lifecycle events only (no mouse events)
- Mouse hover tooltips: use `container.addEventListener('pointermove', evt => nvl.getHits(evt))` — the hit object has `nvlTargets[].type === 'node'`
- `HoverInteraction` for hover requires separate `@neo4j-nvl/interaction-handlers` package — avoid unless already needed
- NVL `options.disableTelemetry: true` suppresses Segment analytics — required by acceptance criteria
- Node/rel data: `id` required on both; nodes get `caption`, `size`, `color`; rels get `from`, `to`, `width`, `color`
- Container must have explicit CSS height — `#collab-graph-container { height: 520px }` was already set from task-005

## Wrapped visual design pattern (task-009)
- Space Grotesk (Google Fonts, wght 700/800/900) used as `--font-display`; applied to `body`, headings, buttons
- Hero big numbers use gradient text: `background: linear-gradient(...)` + `-webkit-background-clip: text` + `-webkit-text-fill-color: transparent`
- Two-column layout: `.stats-grid { display:grid; grid-template-columns:1fr 1fr; gap:0 2rem }` inside `@media (min-width:900px)`. Full-width override: `.section-full { grid-column: 1/-1 }` scoped inside the media query.
- Hero card glow blob: `position:absolute; border-radius:50%; filter:blur(60px); opacity:0.06` using `--card-glow` CSS custom property per card variant
- `.loading-placeholder` should NOT have its own background/border — let parent `.stat-card` or `.hero-card` provide the surface
- Gold/silver/bronze rank: `tbody tr:nth-child(1) .rank { color:#ffd700 }`, etc.
- Graph container height: 560px (increased from 520px) to look better in wide two-column layout

## Supporting stats pattern (task-007)
- All 7 load functions use `safeQuery()` (not raw `runQuery()`) for spinner + error toast
- PR velocity: `WHERE pr.state = 'MERGED'` excludes unmerged; `mergedCount >= 3` filter prevents outliers; display as `Xh` if < 24h else `Xd`
- Label leaderboard renders an inline bar chart (width % relative to max) — more visual than a plain table
- All 7 functions fired in parallel from `loadDashboard()` (no await) — sections update independently

## GitHub Pages deployment (task-010)
- Public URL: https://www.jexp.de/github4j/ (custom domain, HTTPS enforced, source: docs/ on main branch)
- Add `docs/.nojekyll` (empty file) to prevent Jekyll from processing the single-file HTML app
- App uses Neo4j JS driver Bolt over `wss://` — Bolt/WebSocket is NOT subject to HTTP CORS policy
- No AuraDB allowlist configuration needed; CORS notes are irrelevant for Bolt connections
- Verify GitHub Pages config via: `gh api repos/{owner}/{repo}/pages` — shows build status, html_url, source
