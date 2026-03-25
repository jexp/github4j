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
