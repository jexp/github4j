# github4j — GitHub Wrapped × Neo4j

> *Your year (or quarter, or sprint) in code. Spotify Wrapped, but for pull requests.*

Built at the Neo4j hackathon. Six CSVs of GitHub activity go in — contributor glory, collaboration graphs, and bug-slaying leaderboards come out.

---

## What's inside

| Layer | What it does |
|---|---|
| **Graph import** | Loads 6 CSVs into Neo4j AuraDB as a property graph (persons, repos, PRs, reviews, files, labels) |
| **NeoDash dashboard** | 10 pre-built panels — top contributors, PR velocity, hottest files, label heatmap |
| **Web app** | Static GitHub Pages site with Wrapped-style hero stats and an NVL collaboration graph |
| **GDS notebook** | Louvain community detection + PageRank — do the informal teams match the org chart? |
| **MCP server** | FastAPI server Claude can query to answer "who fixed the most bugs?" |

---

## Quickstart

### 1. Get an AuraDB instance

Free tier at [neo4j.com/cloud/aura](https://neo4j.com/cloud/aura) — takes 2 minutes. Save the connection URI and password.

### 2. Seed the database

```bash
# install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# clone and seed
git clone https://github.com/jexp/github4j
cd github4j

NEO4J_URI=neo4j+s://xxxx.databases.neo4j.io \
NEO4J_USER=neo4j \
NEO4J_PASSWORD=your-password \
uv run seed.py

# AuraDB Free tier? Skip the large TOUCHES import:
uv run seed.py --skip-touches
```

The seed script reads from `data/` locally — no remote CSV fetching, no LOAD CSV, just Python.

> **AuraDB Free tier note:** Full import creates ~507k relationships. `--skip-touches` skips the 206k `TOUCHES` rels (files per PR) and keeps everything under the 400k limit. All hero stats still work.

### 3. Open the web app

```bash
cd docs && python3 -m http.server 8080
# → http://localhost:8080
```

Enter your AuraDB credentials on first load (stored in `localStorage`, never committed).

Or deploy to GitHub Pages: Settings → Pages → Source: `docs/` folder.

### 4. Load the NeoDash dashboard

1. Go to [neodash.graphapp.io](https://neodash.graphapp.io) (or AuraDB → Apps → NeoDash)
2. New dashboard → Import → paste `dashboards/github-wrapped.json`
3. Connect to your AuraDB instance

### 5. Run the LOAD CSV scripts (alternative to seed.py)

If you prefer running Cypher directly in AuraDB Browser or cypher-shell:

```
import/01_persons.cypher
import/02_repos.cypher
import/03_files.cypher
import/04_prs.cypher
import/05_reviews.cypher
import/06_files_touched.cypher   ← optional, see note above
```

CSVs are fetched from `raw.githubusercontent.com/jexp/github4j/main/data/`.

### 6. Verify the import

Paste `import/verify.cypher` into AuraDB Browser. It checks node counts, relationship counts, and runs the hero stat queries.

---

## Hero stats

**The Great Deleter** — who deleted the most lines of code? Sometimes the best PR is the one that removes 10,000 lines.

**Bug Slayer** — ranked by merged PRs carrying the `bug` label. The unsung heroes of production stability.

---

## Graph schema

```
(:Person)-[:AUTHORED]->(:PullRequest)-[:IN_REPO]->(:Repo)
(:Person)-[:REVIEWED]->(:PullRequest)
(:Person)-[:MERGED]->(:PullRequest)
(:PullRequest)-[:HAS_LABEL]->(:Label)
(:PullRequest)-[:TOUCHES {additions, deletions}]->(:File)
(:File)-[:IN_DIR]->(:Directory)
```

---

## GDS notebook (community detection)

```bash
uv run --extra notebook jupyter notebook notebooks/github_gds.ipynb
```

Runs Louvain community detection on the collaboration graph (who reviews whose PRs) and compares detected communities against `team-*` labels. Visualised with `neo4j-viz`.

Requires `Person.community` to be written back to AuraDB (the notebook does this automatically).

---

## MCP server (Claude integration)

```bash
cd mcp_server
NEO4J_URI=... NEO4J_PASSWORD=... uv run uvicorn main:app --reload
```

Then add `http://localhost:8000/openapi.json` as a tool in Claude Projects. Ask things like:

- *"Who are the top 5 bug fixers?"*
- *"Which file is touched by the most PRs?"*
- *"What communities did Louvain detect?"*

---

## Data files

| File | Rows | Description |
|---|---|---|
| `data/persons.csv` | 348 | GitHub users |
| `data/repos.csv` | 14 | Repositories |
| `data/prs.csv` | 32,252 | Pull requests |
| `data/reviews.csv` | 92,721 | PR reviews |
| `data/files.csv` | 52,996 | Files in repos |
| `data/files_touched.csv` | 206,196 | Files changed per PR |

---

## Built with

- [Neo4j AuraDB](https://neo4j.com/cloud/aura) — managed graph database
- [NeoDash](https://neodash.graphapp.io) — no-code graph dashboards
- [NVL](https://neo4j.com/docs/nvl/current/) — Neo4j Visualization Library (JS)
- [neo4j-viz](https://neo4j.com/docs/python-graph-visualization/current/) — Python graph viz wrapper
- [neo4j-rust-ext](https://pypi.org/project/neo4j-rust-ext/) — fast Neo4j Python driver
- [graphdatascience](https://neo4j.com/docs/graph-data-science/current/python-client/) — GDS Python client
- [uv](https://astral.sh/uv) — Python package manager
