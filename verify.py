#!/usr/bin/env python3
"""
verify.py — Post-import sanity checks for the GitHub Wrapped graph.

Runs the same queries as import/verify.cypher and prints formatted results
with pass/fail indicators against expected values.

Usage:
    uv run verify.py
    NEO4J_URI=neo4j+s://xxx.databases.neo4j.io NEO4J_USER=neo4j NEO4J_PASSWORD=secret uv run verify.py
"""

import os
import sys

from neo4j import GraphDatabase

NEO4J_URI      = os.getenv("NEO4J_URI",      "neo4j+s://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

# ── terminal colours ──────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):    print(f"  {GREEN}✓{RESET}  {msg}")
def fail(msg):  print(f"  {RED}✗{RESET}  {msg}")
def info(msg):  print(f"  {YELLOW}→{RESET}  {msg}")
def header(msg): print(f"\n{BOLD}{CYAN}{'─'*60}{RESET}\n{BOLD}{CYAN}{msg}{RESET}\n{'─'*60}")

def q(session, cypher, **params):
    result = session.run(cypher, **params)
    return [dict(r) for r in result]

def fmt_table(rows, max_col=40):
    """Print a list of dicts as a simple table."""
    if not rows:
        info("(no results)")
        return
    cols = list(rows[0].keys())
    widths = {c: max(len(c), max(len(str(r.get(c, ""))[:max_col]) for r in rows)) for c in cols}
    sep = "  ".join(f"{'─'*widths[c]}" for c in cols)
    hdr = "  ".join(f"{c:<{widths[c]}}" for c in cols)
    print(f"  {BOLD}{hdr}{RESET}")
    print(f"  {sep}")
    for r in rows:
        print("  " + "  ".join(f"{str(r.get(c,''))[:max_col]:<{widths[c]}}" for c in cols))

def check_count(label, actual, expected_min, expected_max=None):
    hi = expected_max or expected_min
    if expected_min <= actual <= hi:
        ok(f"{label}: {actual:,}  (expected {expected_min:,}{'–'+str(hi) if expected_max else ''})")
    else:
        fail(f"{label}: {actual:,}  (expected {expected_min:,}{'–'+str(hi) if expected_max else ''})")

def check_zero(label, actual):
    if actual == 0:
        ok(f"{label}: 0")
    else:
        fail(f"{label}: {actual:,}  (expected 0)")


def run_verify(driver):
    with driver.session(database="neo4j") as s:

        # ── Section 1: Node counts ────────────────────────────────────────────
        header("1 · Node counts")
        check_count("Person",      q(s, "MATCH (n:Person)      RETURN count(n) AS c")[0]["c"], 348, 500)
        check_count("Repo",        q(s, "MATCH (n:Repo)        RETURN count(n) AS c")[0]["c"], 14,  14)
        check_count("PullRequest", q(s, "MATCH (n:PullRequest) RETURN count(n) AS c")[0]["c"], 32252, 32252)
        check_count("File",        q(s, "MATCH (n:File)        RETURN count(n) AS c")[0]["c"], 52996, 52996)
        check_count("Directory",   q(s, "MATCH (n:Directory)   RETURN count(n) AS c")[0]["c"], 12000, 13000)
        check_count("Label",       q(s, "MATCH (n:Label)       RETURN count(n) AS c")[0]["c"], 500,  600)

        # ── Section 2: Relationship counts ───────────────────────────────────
        header("2 · Relationship counts")
        check_count("AUTHORED",  q(s, "MATCH ()-[r:AUTHORED]->()  RETURN count(r) AS c")[0]["c"], 32000, 32300)
        check_count("REVIEWED",  q(s, "MATCH ()-[r:REVIEWED]->()  RETURN count(r) AS c")[0]["c"], 50000, 92722)
        check_count("MERGED",    q(s, "MATCH ()-[r:MERGED]->()    RETURN count(r) AS c")[0]["c"], 20000, 32000)
        check_count("IN_REPO",   q(s, "MATCH ()-[r:IN_REPO]->()   RETURN count(r) AS c")[0]["c"], 32000, 32300)
        check_count("HAS_LABEL", q(s, "MATCH ()-[r:HAS_LABEL]->() RETURN count(r) AS c")[0]["c"], 60000, 70000)
        check_count("IN_DIR",    q(s, "MATCH ()-[r:IN_DIR]->()    RETURN count(r) AS c")[0]["c"], 40000, 53000)
        touches = q(s, "MATCH ()-[r:TOUCHES]->() RETURN count(r) AS c")[0]["c"]
        if touches == 0:
            info(f"TOUCHES: 0  (files_touched not imported — run seed.py without --skip-touches)")
        else:
            check_count("TOUCHES", touches, 100000, 206200)

        # ── Section 3: Sample path traversals ────────────────────────────────
        header("3 · Sample path traversals")

        print("\n  Person → PR → Repo:")
        rows = q(s, """
            MATCH (p:Person)-[:AUTHORED]->(pr:PullRequest)-[:IN_REPO]->(r:Repo)
            RETURN p.login AS person, pr.prId AS prId, r.name AS repo LIMIT 5
        """)
        fmt_table(rows)

        print("\n  Reviewer → PR ← Author:")
        rows = q(s, """
            MATCH (rv:Person)-[:REVIEWED]->(pr:PullRequest)<-[:AUTHORED]-(au:Person)
            WHERE rv <> au
            RETURN rv.login AS reviewer, au.login AS author, pr.prId AS prId LIMIT 5
        """)
        fmt_table(rows)

        print("\n  PR → Labels:")
        rows = q(s, """
            MATCH (pr:PullRequest)-[:HAS_LABEL]->(l:Label)
            RETURN pr.prId AS prId, collect(l.name) AS labels LIMIT 5
        """)
        fmt_table(rows)

        print("\n  File → Directory:")
        rows = q(s, """
            MATCH (f:File)-[:IN_DIR]->(d:Directory)
            RETURN f.filename AS file, d.path AS dir, d.repoId AS repo LIMIT 5
        """)
        fmt_table(rows)

        # ── Section 4: Hero stats ─────────────────────────────────────────────
        header("4 · Hero stat — Great Deleter (top 10 by lines deleted)")
        rows = q(s, """
            MATCH (p:Person)-[:AUTHORED]->(pr:PullRequest)
            RETURN p.login AS contributor, sum(pr.deletions) AS linesDeleted
            ORDER BY linesDeleted DESC LIMIT 10
        """)
        fmt_table(rows)
        if len(rows) >= 5 and rows[0]["linesDeleted"] > 0:
            ok("At least 5 results with non-zero deletions")
        else:
            fail("Expected at least 5 contributors with deletions")

        header("5 · Hero stat — Bug Slayer (top 10 by merged bug PRs)")
        rows = q(s, """
            MATCH (p:Person)-[:AUTHORED]->(pr:PullRequest)-[:HAS_LABEL]->(l:Label {name:'bug'})
            WHERE pr.state = 'MERGED'
            RETURN p.login AS contributor, count(pr) AS bugsFixed
            ORDER BY bugsFixed DESC LIMIT 10
        """)
        fmt_table(rows)
        if rows:
            ok(f"Bug Slayer data present ({len(rows)} contributors)")
        else:
            fail("No merged bug-labelled PRs found")

        # ── Section 5: Collaboration pairs ───────────────────────────────────
        header("6 · Collaboration pairs (top 10)")
        rows = q(s, """
            MATCH (au:Person)-[:AUTHORED]->(pr:PullRequest)<-[:REVIEWED]-(rv:Person)
            WHERE au <> rv
            RETURN au.login AS author, rv.login AS reviewer, count(pr) AS sharedPRs
            ORDER BY sharedPRs DESC LIMIT 10
        """)
        fmt_table(rows)
        if rows:
            ok("Collaboration pairs found")
        else:
            fail("No collaboration pairs — check AUTHORED + REVIEWED relationships")

        # ── Section 6: Supporting stats spot-check ────────────────────────────
        header("7 · Supporting stats spot-check")

        print("\n  Top contributors by PRs opened:")
        fmt_table(q(s, """
            MATCH (p:Person)-[:AUTHORED]->(pr:PullRequest)
            RETURN p.login AS contributor, count(pr) AS prsOpened
            ORDER BY prsOpened DESC LIMIT 10
        """))

        print("\n  Top reviewers:")
        fmt_table(q(s, """
            MATCH (p:Person)-[:REVIEWED]->(pr:PullRequest)
            RETURN p.login AS reviewer, count(pr) AS reviewCount
            ORDER BY reviewCount DESC LIMIT 10
        """))

        print("\n  PR velocity (avg hours to merge, ≥5 merged PRs):")
        fmt_table(q(s, """
            MATCH (p:Person)-[:AUTHORED]->(pr:PullRequest)
            WHERE pr.state = 'MERGED' AND pr.mergedAt IS NOT NULL AND pr.createdAt IS NOT NULL
            WITH p.login AS author,
                 avg(duration.inSeconds(datetime(toString(pr.createdAt)), datetime(toString(pr.mergedAt))).seconds / 3600.0) AS avgHrs,
                 count(pr) AS mergedPRs
            WHERE mergedPRs >= 5
            RETURN author, round(avgHrs, 1) AS avgHoursToMerge, mergedPRs
            ORDER BY avgHoursToMerge ASC LIMIT 10
        """))

        print("\n  Label leaderboard (top 10):")
        fmt_table(q(s, """
            MATCH (pr:PullRequest)-[:HAS_LABEL]->(l:Label)
            RETURN l.name AS label, count(pr) AS prCount
            ORDER BY prCount DESC LIMIT 10
        """))

        # ── Section 7: Data integrity ─────────────────────────────────────────
        header("8 · Data integrity")
        check_zero("PRs with no author",  q(s, "MATCH (pr:PullRequest) WHERE NOT ()-[:AUTHORED]->(pr) RETURN count(pr) AS c")[0]["c"])
        check_zero("PRs with no repo",    q(s, "MATCH (pr:PullRequest) WHERE NOT (pr)-[:IN_REPO]->()  RETURN count(pr) AS c")[0]["c"])
        check_zero("Duplicate prIds",     q(s, "MATCH (pr:PullRequest) WITH pr.prId AS id, count(*) AS c WHERE c > 1 RETURN count(*) AS c")[0]["c"])
        root = q(s, "MATCH (f:File) WHERE NOT (f)-[:IN_DIR]->() RETURN count(f) AS c")[0]["c"]
        info(f"Root-level files (no directory): {root:,}  (non-zero is normal)")

        print("\n  PR state distribution:")
        fmt_table(q(s, "MATCH (pr:PullRequest) RETURN pr.state AS state, count(*) AS cnt ORDER BY cnt DESC"))

        # ── Section 8: Scale check ────────────────────────────────────────────
        header("9 · AuraDB Free tier scale check")
        total_nodes = q(s, "MATCH (n) RETURN count(n) AS c")[0]["c"]
        total_rels  = q(s, "MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"]
        check_count("Total nodes",         total_nodes, 0, 200_000)
        check_count("Total relationships", total_rels,  0, 400_000)
        if total_rels > 400_000:
            info("Over Free tier rel limit — acceptable on paid tier or if TOUCHES imported")


def main():
    print(f"{BOLD}GitHub Wrapped — Import Verification{RESET}")
    print(f"Connecting to {NEO4J_URI} as {NEO4J_USER}...")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        driver.verify_connectivity()
        print(f"{GREEN}Connected ✓{RESET}\n")
    except Exception as e:
        print(f"{RED}Connection failed: {e}{RESET}")
        sys.exit(1)

    try:
        run_verify(driver)
    finally:
        driver.close()

    print(f"\n{BOLD}Verification complete.{RESET}\n")


if __name__ == "__main__":
    main()
