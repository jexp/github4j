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

## GDS notebook pattern (task-011)
- `graphdatascience` version 1.20 installed; `uv sync --extra notebook` installs all notebook deps
- `gds.graph.cypher.project(query, database=db, **params)` — single Cypher query ending with `RETURN gds.graph.project($graphName, sourceNode, targetNode, dataConfig)`. Params (e.g. `graphName=GRAPH_NAME`) passed as kwargs.
- `gds.graph.exists(name)` returns a **pandas Series**; check `result['exists']` (not `.exists` attribute)
- `gds.graph.drop(g)` accepts a `Graph` object returned by `cypher.project()` or `gds.graph.get(name)`
- Louvain API: `gds.louvain.mutate(G, mutateProperty='community', ...)`, `gds.louvain.stream(G, ...)`, `gds.louvain.write(G, writeProperty='community', ...)` — all accept keyword config args, not a dict
- `louvain.write()` re-runs Louvain and writes to AuraDB; `louvain.mutate()` stores only in-memory
- For undirected Cypher projection: use `WHERE id(a) < id(b)` to avoid duplicate pairs + `undirectedRelationshipTypes` in dataConfig
- No `python-dotenv` needed: use inline `_load_env_file()` helper scanning cwd and parent for integration.env

## GDS notebook pattern (task-012)
- PageRank API: `gds.pageRank.mutate(G, mutateProperty='pagerank', relationshipWeightProperty='weight', dampingFactor=0.85, maxIterations=20)` then `gds.pageRank.stream(G, ...)` to get scores as DataFrame
- PageRank stream returns `nodeId` + `score`; resolve nodeId → login via separate `gds.run_cypher("MATCH (p:Person) RETURN id(p) AS nodeId, p.login AS login")`
- **neo4j-viz Relationship uses `source`/`target` (not `start_node`/`end_node`)** — verify against PyPI docs; mandatory fields are `source` and `target` only
- neo4j-viz Node mandatory field: `id`; optional: `caption`, `color`, `size`
- neo4j-viz 1.3.0 (current as of Mar 2026): `from neo4j_viz import Node, Relationship, VisualizationGraph`; render with `VisualizationGraph(nodes=nodes, relationships=rels).show()`
- Majority-label team comparison: query `AUTHORED→PR→HAS_LABEL` with `l.name STARTS WITH 'team-'`; fallback to any label if 0 results; compute per-community accuracy as `majority_count / labelled_size`
- NotebookEdit tool required for editing .ipynb files — `Edit` tool will error with "use NotebookEdit" if you try it on a notebook

## MCP server pattern (task-013)
- `mcp_server/` is a standalone uv project with its own `pyproject.toml` — run with `uv run uvicorn main:app` from inside `mcp_server/`
- FastAPI auto-generates OAS 3.1.0 (not 3.0) at `/openapi.json` — still importable by Salesforce External Services
- Lazy driver init: use a module-level `_driver = None` + getter function; avoids RuntimeError on import when env vars not set
- `get_top_contributors` `deletions` metric: use `pr.deletions` (INTEGER property on PullRequest), not TOUCHES rel — avoids needing 06_files_touched.cypher imported
- `get_community_summary` gracefully returns 404 with helpful message when `Person.community` is not set (before GDS notebook runs)
- All Cypher uses `$param` syntax only — never f-strings; search_person's `$q` parameter passed directly to `toLower($q) CONTAINS` in Cypher
- Python syntax check via uv: `uv run python -m py_compile main.py` (plain `python` may not exist on system path)
- AuraDB REVIEWED relationship direction: `(reviewer:Person)-[:REVIEWED]->(pr:PullRequest)` — reviewer points TO the PR

## Embedding pattern (task-015)
- `embed.py` is a standalone script at repo root; install embed extra with `uv sync --extra embed` (adds openai package)
- openai v2.x (2.29.0) breaking API change from v1: use `OpenAI(api_key=...)` client object + `client.embeddings.create(input=texts, model=model)` — old `openai.Embedding.create()` does not exist in v2
- embed.py uses `--dry-run` flag to verify AuraDB connectivity + PR count without calling any embedding API — useful for CI
- Vector index `pr_title_vector` is pre-created by schema.cypher / seed.py with `vector.dimensions: 1536, vector.similarity_function: 'cosine'` — matches text-embedding-3-small output exactly
- Smoke-test after write: query `db.index.vector.queryNodes('pr_title_vector', 5, $vec)` using a freshly embedded node's vector; index may still be building (0 results is normal for a few seconds)
- openai package added as `[project.optional-dependencies] embed = ["openai>=1.0"]` — keep separate from notebook/mcp extras
