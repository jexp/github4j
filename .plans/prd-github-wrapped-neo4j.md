# PRD: GitHub Wrapped — Neo4j Demo

## Overview

A "Spotify Wrapped"-style analytics demo built on Neo4j AuraDB, using GitHub activity data (PRs, reviews, files, contributors) exported as CSVs. The project delivers four layered artifacts: a graph data model + import, Aura Dashboards, a static web app on GitHub Pages, a GDS exploration notebook, and a Claude-accessible MCP server.

## Goals

- Model and import GitHub CSV data into Neo4j AuraDB as a property graph
- Surface compelling "hero stats" (biggest code cleaner, top bug fixer) alongside supporting team/collaboration metrics
- Provide a polished, shareable Wrapped-style web demo (GitHub Pages)
- Enable graph data science exploration (community detection vs. formal teams)
- Expose the graph via an MCP server so Claude can answer questions about it

## Non-Goals

- Real-time GitHub webhook ingestion (batch CSV import only)
- Authentication / per-user personalised views
- Full CI/CD pipeline beyond GitHub Pages deployment
- Commit-level granularity (PR-level data is the atomic unit)

## Data Available

| File | Key Fields |
|---|---|
| `persons.csv` | login, url |
| `repos.csv` | repoId, owner, name, url |
| `prs.csv` | prId, repoId, title, state, isDraft, createdAt, mergedAt, additions, deletions, changedFiles, authorLogin, mergedBy, labels, commentCount |
| `reviews.csv` | reviewerLogin, prId, repoId, state, submittedAt, commentCount |
| `files.csv` | fileId, path, filename, directory, repoId |
| `files_touched.csv` | prId, fileId, repoId, additions, deletions |

## Requirements

### Functional Requirements

#### P1 — Graph Model & Import

- REQ-F-001: Define a Neo4j property graph schema with nodes: `Person`, `Repo`, `PullRequest`, `File`, `Directory`, `Label`
- REQ-F-002: Define relationships: `(:Person)-[:AUTHORED]->(:PullRequest)`, `(:Person)-[:REVIEWED]->(:PullRequest)`, `(:PullRequest)-[:IN_REPO]->(:Repo)`, `(:PullRequest)-[:TOUCHES]->(:File)`, `(:File)-[:IN_DIR]->(:Directory)`, `(:PullRequest)-[:HAS_LABEL]->(:Label)`, `(:Person)-[:MERGED]->(:PullRequest)`
- REQ-F-003: Cypher `LOAD CSV` scripts to import all 6 CSVs into AuraDB in dependency order (persons → repos → files → prs → reviews → files_touched)
- REQ-F-004: Create indexes on `Person.login`, `Repo.repoId`, `PullRequest.prId`, `File.fileId`
- REQ-F-005: Aura Dashboard JSON config with at minimum: top contributors bar chart, PR merge rate over time, top reviewers, hottest files/directories, label distribution

#### P2 — Static Web App (GitHub Pages)

- REQ-F-010: Single-page HTML app served from GitHub Pages (`gh-pages` branch or `docs/` folder)
- REQ-F-011: Connect to AuraDB via Neo4j HTTP API (`/db/data/transaction/commit`) using fetch() — avoids Bolt/WSS CORS issues from static hosting
- REQ-F-012: Credentials (AuraDB URI, user, password) entered via a config panel on first load and stored in `localStorage` — no secrets in the repo
- REQ-F-013: **Hero stat — The Great Deleter**: ranked list of contributors by total lines deleted across all their PRs
- REQ-F-014: **Hero stat — Bug Slayer**: ranked list of contributors by number of PRs carrying the `bug` label that were merged
- REQ-F-015: Supporting stats displayed as cards/sections:
  - Top 10 contributors by PRs opened
  - Top 10 reviewers by review count (approvals + comments)
  - Top 10 hottest files by number of distinct PRs touching them
  - Top 10 hottest directories (aggregate)
  - PR velocity: average hours open-to-merge, by author (top 10 fastest)
  - Collaboration pairs: top 10 author↔reviewer relationships (graph-native)
  - Label leaderboard: most-used labels
- REQ-F-016: Wrapped-style visual presentation — dark background, large numbers, animated stat reveals (CSS transitions), shareable cards
- REQ-F-017a: Use **NVL** (Neo4j Visualization Library, JS) to render the collaboration graph (author↔reviewer pairs) as an interactive force-directed network in the web app
- REQ-F-017: Deployed and publicly accessible via GitHub Pages HTTPS URL

#### P3 — GDS Exploration Notebook

- REQ-F-020: Jupyter notebook (`notebooks/github_gds.ipynb`) using `neo4j` Python driver and `graphdatascience` client library
- REQ-F-021: Project a collaboration graph: `(:Person)-[:REVIEWED]->(:Person)` (via shared PRs) into GDS in-memory
- REQ-F-022: Run Louvain community detection; assign `community` property back to `Person` nodes
- REQ-F-023: Compare detected communities against `team-*` labels from PRs — compute overlap/accuracy metric
- REQ-F-024: PageRank on the collaboration graph to find most "central" reviewers
- REQ-F-025: Visualise community graph using `neo4j-python-viz` (Neo4j's official Python visualisation wrapper)
- REQ-F-026: Export community assignments as CSV for use in the web app

#### P4 — MCP Server

- REQ-F-030: FastAPI app (`mcp_server/main.py`) exposing an MCP-compatible HTTP endpoint
- REQ-F-031: Tools exposed:
  - `get_top_contributors(metric: "prs"|"deletions"|"bug_fixes", limit: int)` → ranked list
  - `get_collaboration_pairs(limit: int)` → top author↔reviewer pairs with counts
  - `get_hottest_files(limit: int)` → files by PR touch count
  - `get_pr_velocity(author: str?)` → avg merge time, optionally filtered by author
  - `search_person(login: str)` → full stats for one contributor
  - `get_community_summary()` → community sizes and representative members
- REQ-F-032: Each tool runs a parameterised Cypher query against AuraDB; connection config via environment variables
- REQ-F-033: OpenAPI spec auto-generated at `/openapi.json` (importable into Claude Projects as a tool)
- REQ-F-034: Deploy to Vercel or Railway (free tier) so Claude can reach it over HTTPS

### Non-Functional Requirements

- REQ-NF-001: Import scripts must complete on AuraDB Free tier (≤200k nodes, ≤400k rels) — validate row counts before import
- REQ-NF-002: Web app page load must work with cold AuraDB (handle query latency gracefully with loading states)
- REQ-NF-003: No secrets committed to the repository; credentials via localStorage (web) and `.env` / env vars (MCP server)
- REQ-NF-004: All Cypher queries parameterised (no string interpolation) to prevent injection

## Technical Considerations

### Graph Schema (Cypher)
```cypher
(:Person {login, url})
(:Repo {repoId, owner, name, url})
(:PullRequest {prId, number, title, state, isDraft, createdAt, mergedAt, additions, deletions, changedFiles, commentCount})
(:File {fileId, path, filename, directory})
(:Directory {path, repoId})
(:Label {name})

[:AUTHORED] Person→PullRequest
[:REVIEWED {state, submittedAt, commentCount}] Person→PullRequest
[:MERGED] Person→PullRequest
[:IN_REPO] PullRequest→Repo
[:TOUCHES {additions, deletions}] PullRequest→File
[:IN_DIR] File→Directory
[:HAS_LABEL] PullRequest→Label
```

### Hero Stat Queries (sketch)
```cypher
// The Great Deleter
MATCH (p:Person)-[:AUTHORED]->(pr:PullRequest)
RETURN p.login, sum(pr.deletions) AS linesDeleted
ORDER BY linesDeleted DESC LIMIT 10

// Bug Slayer
MATCH (p:Person)-[:AUTHORED]->(pr:PullRequest)-[:HAS_LABEL]->(l:Label {name:"bug"})
WHERE pr.state = "MERGED"
RETURN p.login, count(pr) AS bugsFixed
ORDER BY bugsFixed DESC LIMIT 10
```

### Visualisation Libraries

**NVL (JavaScript)** — `@neo4j-nvl/base` (vanilla JS) or `@neo4j-nvl/react`
- Nodes require `id: string`; relationships require `id`, `from`, `to`
- Options: `{ layout: 'forceDirected', initialZoom: 2.0, disableTelemetry: true }`
- Container `div` **must have explicit CSS `height`** or graph renders invisibly
- Used in the static web app for the collaboration graph panel

**neo4j-viz (Python)** — `pip install neo4j-viz[notebook]`
- `Node(id, size, caption)`, `Relationship(source, target, caption)`, `VisualizationGraph(nodes, rels).render()`
- Renders interactive NVL-backed graph inside Jupyter notebooks
- Has native GDS integration — can pass GDS result DataFrames directly
- Used in the GDS notebook for community visualisation

### Deployment Architecture
```
AuraDB (cloud Neo4j)
    ↑ LOAD CSV (import scripts)
    ↑ Cypher HTTP API (web app)
    ↑ Bolt driver (MCP server, notebook)

GitHub Pages (static HTML)  →  AuraDB HTTP API
MCP Server (Vercel/Railway) →  AuraDB Bolt
Jupyter Notebook (local)    →  AuraDB Bolt + GDS
```

### SSL / CORS Constraint
AuraDB requires TLS. Static HTML on GitHub Pages (HTTPS) can use `fetch()` to the AuraDB HTTP transaction API — this works cross-origin if the AuraDB instance allows it. Test early; fallback is the MCP server acting as a proxy.

## Acceptance Criteria

- [ ] All 6 CSVs imported into AuraDB with correct relationships and indexes
- [ ] Aura Dashboard JSON config loads and shows at least 5 charts
- [ ] GitHub Pages URL is publicly accessible over HTTPS
- [ ] "Great Deleter" and "Bug Slayer" hero stats render correctly
- [ ] All 7 supporting stat sections render with real data
- [ ] GDS notebook runs end-to-end and produces community assignments
- [ ] Community detection result compared against team labels with a printed overlap metric
- [ ] MCP server deployed and all 6 tools return correct data
- [ ] Claude can call MCP tools via the public HTTPS URL and answer questions like "Who are the top bug fixers?" and "Which file is touched the most?"

## Out of Scope

- Historical trend analysis beyond what's in the CSVs
- Authentication or per-user login to the web app
- Automated CSV refresh / GitHub API polling
- Mobile-optimised layout (desktop demo is sufficient)

## Open Questions

- ~~Does AuraDB Free tier support GDS?~~ Confirmed: Neo4j GDS plugin is available.
- What is the AuraDB connection string and credentials for this hackathon instance?
- Should community detection results be written back to AuraDB nodes (for use in web app / dashboards) or kept notebook-only?
