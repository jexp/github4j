#!/usr/bin/env python3
"""
seed.py — Load GitHub Wrapped CSV data into Neo4j using the Python driver.

Reads local data/ CSV files and imports them in dependency order using
batched unwind queries (fast, no LOAD CSV remote fetch required).

Usage:
    uv run seed.py
    NEO4J_URI=neo4j+s://xxx.databases.neo4j.io NEO4J_USER=neo4j NEO4J_PASSWORD=secret uv run seed.py
    uv run seed.py --skip-touches   # skip files_touched (saves ~100k rels, fits AuraDB Free)
"""

import csv
import os
import sys
import time
from pathlib import Path

# neo4j-rust-ext is a drop-in replacement for the neo4j driver with Rust internals
from neo4j import GraphDatabase

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
NEO4J_URI      = os.getenv("NEO4J_URI",      "neo4j+s://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
DATA_DIR       = Path(__file__).parent / "data"
BATCH_SIZE     = 1000
SKIP_TOUCHES   = "--skip-touches" in sys.argv


def read_csv(filename: str) -> list[dict]:
    path = DATA_DIR / filename
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def run_batch(session, query: str, rows: list[dict], label: str):
    total = len(rows)
    done = 0
    for i in range(0, total, BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        session.run(query, rows=batch)
        done += len(batch)
        print(f"  {label}: {done}/{total}", end="\r")
    print(f"  {label}: {total}/{total} ✓")


def seed(driver):
    with driver.session(database="neo4j") as s:

        # ----------------------------------------------------------------
        # Schema — constraints and indexes
        # ----------------------------------------------------------------
        print("Creating constraints and indexes...")
        constraints = [
            "CREATE CONSTRAINT person_login IF NOT EXISTS FOR (p:Person)       REQUIRE p.login    IS UNIQUE",
            "CREATE CONSTRAINT repo_id      IF NOT EXISTS FOR (r:Repo)         REQUIRE r.repoId   IS UNIQUE",
            "CREATE CONSTRAINT pr_id        IF NOT EXISTS FOR (pr:PullRequest)  REQUIRE pr.prId    IS UNIQUE",
            "CREATE CONSTRAINT file_id      IF NOT EXISTS FOR (f:File)          REQUIRE f.fileId   IS UNIQUE",
            "CREATE CONSTRAINT label_name   IF NOT EXISTS FOR (l:Label)         REQUIRE l.name     IS UNIQUE",
        ]
        for c in constraints:
            s.run(c)
        print("  Constraints OK ✓")

        # ----------------------------------------------------------------
        # 1. Persons
        # ----------------------------------------------------------------
        print("Importing persons...")
        rows = read_csv("persons.csv")
        run_batch(s, """
            UNWIND $rows AS row
            MERGE (p:Person {login: row.login})
            SET p.url = row.url
        """, rows, "Person")

        # ----------------------------------------------------------------
        # 2. Repos
        # ----------------------------------------------------------------
        print("Importing repos...")
        rows = read_csv("repos.csv")
        run_batch(s, """
            UNWIND $rows AS row
            MERGE (r:Repo {repoId: row.repoId})
            SET r.owner = row.owner, r.name = row.name, r.url = row.url
        """, rows, "Repo")

        # ----------------------------------------------------------------
        # 3. Files + Directories
        # ----------------------------------------------------------------
        print("Importing files and directories...")
        rows = read_csv("files.csv")

        # Pass 1: directories
        run_batch(s, """
            UNWIND $rows AS row
            WITH row WHERE row.directory IS NOT NULL AND row.directory <> ''
            MERGE (d:Directory {path: row.directory, repoId: row.repoId})
        """, rows, "Directory")

        # Pass 2: files + IN_DIR
        run_batch(s, """
            UNWIND $rows AS row
            MERGE (f:File {fileId: row.fileId})
            SET f.path = row.path, f.filename = row.filename,
                f.directory = row.directory, f.repoId = row.repoId, f.url = row.url
            WITH f, row
            WHERE row.directory IS NOT NULL AND row.directory <> ''
            MERGE (d:Directory {path: row.directory, repoId: row.repoId})
            MERGE (f)-[:IN_DIR]->(d)
        """, rows, "File+IN_DIR")

        # ----------------------------------------------------------------
        # 4. Pull Requests (3 passes: nodes, labels, relationships)
        # ----------------------------------------------------------------
        print("Importing pull requests...")
        rows = read_csv("prs.csv")

        # Pass 1: PR nodes
        run_batch(s, """
            UNWIND $rows AS row
            MERGE (pr:PullRequest {prId: row.prId})
            SET pr.number       = toInteger(row.number),
                pr.title        = row.title,
                pr.url          = row.url,
                pr.state        = row.state,
                pr.isDraft      = (row.isDraft = 'true'),
                pr.createdAt    = row.createdAt,
                pr.mergedAt     = row.mergedAt,
                pr.closedAt     = row.closedAt,
                pr.additions    = toInteger(row.additions),
                pr.deletions    = toInteger(row.deletions),
                pr.changedFiles = toInteger(row.changedFiles),
                pr.baseRefName  = row.baseRefName,
                pr.commentCount = toInteger(row.commentCount)
        """, rows, "PullRequest")

        # Pass 2: Labels + HAS_LABEL
        run_batch(s, """
            UNWIND $rows AS row
            WITH row WHERE row.labels IS NOT NULL AND row.labels <> ''
            MATCH (pr:PullRequest {prId: row.prId})
            UNWIND split(row.labels, ';') AS labelName
            WITH pr, trim(labelName) AS lname WHERE lname <> ''
            MERGE (l:Label {name: lname})
            MERGE (pr)-[:HAS_LABEL]->(l)
        """, rows, "Label+HAS_LABEL")

        # Pass 3: AUTHORED + IN_REPO + MERGED
        run_batch(s, """
            UNWIND $rows AS row
            MATCH (pr:PullRequest {prId: row.prId})
            MATCH (r:Repo {repoId: row.repoId})
            MERGE (pr)-[:IN_REPO]->(r)
            WITH pr, row
            WHERE row.authorLogin IS NOT NULL AND row.authorLogin <> ''
            MERGE (author:Person {login: row.authorLogin})
            MERGE (author)-[:AUTHORED]->(pr)
            WITH pr, row
            WHERE row.mergedBy IS NOT NULL AND row.mergedBy <> ''
            MERGE (merger:Person {login: row.mergedBy})
            MERGE (merger)-[:MERGED]->(pr)
        """, rows, "AUTHORED+IN_REPO+MERGED")

        # ----------------------------------------------------------------
        # 5. Reviews
        # ----------------------------------------------------------------
        print("Importing reviews...")
        rows = read_csv("reviews.csv")
        run_batch(s, """
            UNWIND $rows AS row
            WHERE row.reviewerLogin IS NOT NULL AND row.reviewerLogin <> ''
            MERGE (reviewer:Person {login: row.reviewerLogin})
            WITH reviewer, row
            MATCH (pr:PullRequest {prId: row.prId})
            MERGE (reviewer)-[rev:REVIEWED]->(pr)
            SET rev.state        = row.state,
                rev.submittedAt  = row.submittedAt,
                rev.commentCount = toInteger(coalesce(row.commentCount, '0'))
        """, rows, "REVIEWED")

        # ----------------------------------------------------------------
        # 6. Files Touched (optional — ~206k rels, exceeds AuraDB Free)
        # ----------------------------------------------------------------
        if SKIP_TOUCHES:
            print("Skipping files_touched (--skip-touches flag set)")
            print("  Hero stat 'Great Deleter' will use PR-level deletions instead")
        else:
            print("Importing files_touched (this may exceed AuraDB Free tier)...")
            rows = read_csv("files_touched.csv")
            run_batch(s, """
                UNWIND $rows AS row
                MATCH (pr:PullRequest {prId: row.prId})
                MATCH (f:File {fileId: row.fileId})
                MERGE (pr)-[t:TOUCHES]->(f)
                SET t.additions = toInteger(row.additions),
                    t.deletions = toInteger(row.deletions)
            """, rows, "TOUCHES")


def main():
    print(f"Connecting to {NEO4J_URI} as {NEO4J_USER}...")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    try:
        driver.verify_connectivity()
        print("Connected ✓\n")
    except Exception as e:
        print(f"Connection failed: {e}")
        sys.exit(1)

    t0 = time.time()
    try:
        seed(driver)
    finally:
        driver.close()

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.1f}s")
    print("\nVerify with: import/verify.cypher")


if __name__ == "__main__":
    main()
