"""
GitHub Wrapped — FastAPI MCP server
Exposes 6 Neo4j query tools as REST endpoints.
AuraDB credentials loaded from environment variables.
"""

from __future__ import annotations

import os
from typing import Any, Literal

import neo4j
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Database connection
# ---------------------------------------------------------------------------

NEO4J_URI = os.environ.get("NEO4J_URI", "")
NEO4J_USERNAME = os.environ.get("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "")
NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")


def get_driver() -> neo4j.Driver:
    """Return a Neo4j driver using env-var credentials."""
    if not NEO4J_URI or not NEO4J_PASSWORD:
        raise RuntimeError(
            "NEO4J_URI and NEO4J_PASSWORD environment variables must be set"
        )
    return neo4j.GraphDatabase.driver(
        NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD)
    )


# Lazy global driver (created on first request)
_driver: neo4j.Driver | None = None


def driver() -> neo4j.Driver:
    global _driver
    if _driver is None:
        _driver = get_driver()
    return _driver


def run_query(cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Execute a read query and return rows as list-of-dicts."""
    params = params or {}
    records, _, _ = driver().execute_query(
        cypher, params, database_=NEO4J_DATABASE, routing_=neo4j.RoutingControl.READ
    )
    return [dict(r) for r in records]


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="GitHub Wrapped MCP Server",
    description=(
        "Exposes GitHub repository analytics stored in Neo4j as REST endpoints "
        "compatible with the MCP tool-calling pattern. All Cypher queries are "
        "parameterised. Credentials are loaded from environment variables."
    ),
    version="0.1.0",
)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class Contributor(BaseModel):
    login: str
    score: int


class TopContributorsResponse(BaseModel):
    metric: str
    limit: int
    results: list[Contributor]


class CollaborationPair(BaseModel):
    author_login: str
    reviewer_login: str
    interaction_count: int


class CollaborationPairsResponse(BaseModel):
    limit: int
    results: list[CollaborationPair]


class HotFile(BaseModel):
    path: str
    pr_count: int
    total_changes: int


class HottestFilesResponse(BaseModel):
    limit: int
    results: list[HotFile]


class PRVelocityRow(BaseModel):
    login: str
    avg_hours: float
    merged_pr_count: int


class PRVelocityResponse(BaseModel):
    limit: int
    results: list[PRVelocityRow]


class PersonResult(BaseModel):
    login: str
    pr_count: int
    review_count: int
    community: int | None


class SearchPersonResponse(BaseModel):
    query: str
    results: list[PersonResult]


class CommunityMember(BaseModel):
    login: str
    pagerank_score: float | None


class CommunitySummary(BaseModel):
    community_id: int
    size: int
    top_label: str | None
    members: list[CommunityMember]


class CommunitySummaryResponse(BaseModel):
    total_communities: int
    communities: list[CommunitySummary]


# ---------------------------------------------------------------------------
# Health / root
# ---------------------------------------------------------------------------

@app.get("/", summary="Health check")
def root() -> dict[str, str]:
    """Returns server status."""
    return {"status": "ok", "service": "github-wrapped-mcp-server"}


# ---------------------------------------------------------------------------
# Tool 1: get_top_contributors
# ---------------------------------------------------------------------------

@app.get(
    "/tools/get_top_contributors",
    response_model=TopContributorsResponse,
    summary="Get top contributors ranked by a chosen metric",
    operation_id="get_top_contributors",
    tags=["tools"],
)
def get_top_contributors(
    metric: Literal["prs", "deletions", "bug_fixes"] = Query(
        default="prs",
        description="Ranking metric: 'prs' = PR count, 'deletions' = lines deleted, 'bug_fixes' = merged bug-labelled PRs",
    ),
    limit: int = Query(default=10, ge=1, le=50, description="Maximum rows to return"),
) -> TopContributorsResponse:
    """
    Returns the top contributors ranked by the chosen metric.

    - **prs**: authors with the most PRs opened
    - **deletions**: authors with the most lines deleted across all their TOUCHES relationships
    - **bug_fixes**: authors with the most merged PRs carrying the 'bug' label
    """
    if metric == "prs":
        cypher = """
            MATCH (p:Person)-[:AUTHORED]->(pr:PullRequest)
            RETURN p.login AS login, COUNT(DISTINCT pr) AS score
            ORDER BY score DESC
            LIMIT $limit
        """
    elif metric == "deletions":
        cypher = """
            MATCH (p:Person)-[:AUTHORED]->(pr:PullRequest)
            WHERE pr.deletions IS NOT NULL
            RETURN p.login AS login, SUM(pr.deletions) AS score
            ORDER BY score DESC
            LIMIT $limit
        """
    else:  # bug_fixes
        cypher = """
            MATCH (p:Person)-[:AUTHORED]->(pr:PullRequest)-[:HAS_LABEL]->(l:Label)
            WHERE toLower(l.name) = 'bug' AND pr.state = 'MERGED'
            RETURN p.login AS login, COUNT(DISTINCT pr) AS score
            ORDER BY score DESC
            LIMIT $limit
        """
    rows = run_query(cypher, {"limit": limit})
    return TopContributorsResponse(
        metric=metric,
        limit=limit,
        results=[Contributor(login=r["login"], score=int(r["score"])) for r in rows],
    )


# ---------------------------------------------------------------------------
# Tool 2: get_collaboration_pairs
# ---------------------------------------------------------------------------

@app.get(
    "/tools/get_collaboration_pairs",
    response_model=CollaborationPairsResponse,
    summary="Get top author-reviewer collaboration pairs",
    operation_id="get_collaboration_pairs",
    tags=["tools"],
)
def get_collaboration_pairs(
    limit: int = Query(default=20, ge=1, le=100, description="Maximum pairs to return"),
) -> CollaborationPairsResponse:
    """
    Returns the top author-reviewer pairs ranked by the number of PRs where
    the reviewer reviewed a PR authored by the author.
    """
    cypher = """
        MATCH (author:Person)-[:AUTHORED]->(pr:PullRequest)<-[:REVIEWED]-(reviewer:Person)
        WHERE author.login <> reviewer.login
        RETURN author.login AS author_login,
               reviewer.login AS reviewer_login,
               COUNT(DISTINCT pr) AS interaction_count
        ORDER BY interaction_count DESC
        LIMIT $limit
    """
    rows = run_query(cypher, {"limit": limit})
    return CollaborationPairsResponse(
        limit=limit,
        results=[
            CollaborationPair(
                author_login=r["author_login"],
                reviewer_login=r["reviewer_login"],
                interaction_count=int(r["interaction_count"]),
            )
            for r in rows
        ],
    )


# ---------------------------------------------------------------------------
# Tool 3: get_hottest_files
# ---------------------------------------------------------------------------

@app.get(
    "/tools/get_hottest_files",
    response_model=HottestFilesResponse,
    summary="Get the most frequently changed files",
    operation_id="get_hottest_files",
    tags=["tools"],
)
def get_hottest_files(
    limit: int = Query(default=10, ge=1, le=50, description="Maximum files to return"),
) -> HottestFilesResponse:
    """
    Returns files ranked by how many distinct PRs touched them (TOUCHES relationships).
    Also returns total additions + deletions across all touching PRs.
    Requires the TOUCHES relationships to have been imported (06_files_touched.cypher).
    """
    cypher = """
        MATCH (pr:PullRequest)-[t:TOUCHES]->(f:File)
        RETURN f.path AS path,
               COUNT(DISTINCT pr) AS pr_count,
               SUM(toInteger(t.additions) + toInteger(t.deletions)) AS total_changes
        ORDER BY pr_count DESC
        LIMIT $limit
    """
    rows = run_query(cypher, {"limit": limit})
    return HottestFilesResponse(
        limit=limit,
        results=[
            HotFile(
                path=r["path"],
                pr_count=int(r["pr_count"]),
                total_changes=int(r["total_changes"] or 0),
            )
            for r in rows
        ],
    )


# ---------------------------------------------------------------------------
# Tool 4: get_pr_velocity
# ---------------------------------------------------------------------------

@app.get(
    "/tools/get_pr_velocity",
    response_model=PRVelocityResponse,
    summary="Get average PR open-to-merge time per author",
    operation_id="get_pr_velocity",
    tags=["tools"],
)
def get_pr_velocity(
    limit: int = Query(default=10, ge=1, le=50, description="Maximum authors to return"),
    min_merged: int = Query(
        default=3,
        ge=1,
        description="Minimum merged PRs required to be included",
    ),
) -> PRVelocityResponse:
    """
    Returns authors ranked by average hours from PR creation to merge (ascending —
    fastest first). Only merged PRs with both createdAt and mergedAt are included.
    Authors with fewer than `min_merged` merged PRs are excluded to avoid outliers.
    """
    cypher = """
        MATCH (p:Person)-[:AUTHORED]->(pr:PullRequest)
        WHERE pr.state = 'MERGED'
          AND pr.createdAt IS NOT NULL
          AND pr.mergedAt IS NOT NULL
        WITH p.login AS login,
             AVG(duration.inSeconds(pr.createdAt, pr.mergedAt).seconds / 3600.0) AS avg_hours,
             COUNT(pr) AS merged_pr_count
        WHERE merged_pr_count >= $min_merged
        RETURN login, avg_hours, merged_pr_count
        ORDER BY avg_hours ASC
        LIMIT $limit
    """
    rows = run_query(cypher, {"limit": limit, "min_merged": min_merged})
    return PRVelocityResponse(
        limit=limit,
        results=[
            PRVelocityRow(
                login=r["login"],
                avg_hours=round(float(r["avg_hours"]), 2),
                merged_pr_count=int(r["merged_pr_count"]),
            )
            for r in rows
        ],
    )


# ---------------------------------------------------------------------------
# Tool 5: search_person
# ---------------------------------------------------------------------------

@app.get(
    "/tools/search_person",
    response_model=SearchPersonResponse,
    summary="Search for persons by login substring",
    operation_id="search_person",
    tags=["tools"],
)
def search_person(
    q: str = Query(description="Login substring to search for (case-insensitive)"),
    limit: int = Query(default=10, ge=1, le=50, description="Maximum results to return"),
) -> SearchPersonResponse:
    """
    Returns persons whose login contains the query string (case-insensitive).
    Includes their PR count, review count, and Louvain community ID (if computed).
    """
    cypher = """
        MATCH (p:Person)
        WHERE toLower(p.login) CONTAINS toLower($q)
        OPTIONAL MATCH (p)-[:AUTHORED]->(pr:PullRequest)
        OPTIONAL MATCH (p)-[:REVIEWED]->(rev:PullRequest)
        RETURN p.login AS login,
               COUNT(DISTINCT pr) AS pr_count,
               COUNT(DISTINCT rev) AS review_count,
               p.community AS community
        ORDER BY pr_count DESC
        LIMIT $limit
    """
    rows = run_query(cypher, {"q": q, "limit": limit})
    return SearchPersonResponse(
        query=q,
        results=[
            PersonResult(
                login=r["login"],
                pr_count=int(r["pr_count"]),
                review_count=int(r["review_count"]),
                community=int(r["community"]) if r["community"] is not None else None,
            )
            for r in rows
        ],
    )


# ---------------------------------------------------------------------------
# Tool 6: get_community_summary
# ---------------------------------------------------------------------------

@app.get(
    "/tools/get_community_summary",
    response_model=CommunitySummaryResponse,
    summary="Get Louvain community summaries with top members",
    operation_id="get_community_summary",
    tags=["tools"],
)
def get_community_summary(
    top_communities: int = Query(
        default=10,
        ge=1,
        le=50,
        description="Number of largest communities to return",
    ),
    members_per_community: int = Query(
        default=5,
        ge=1,
        le=20,
        description="Top members to list per community (by PageRank score if available)",
    ),
) -> CommunitySummaryResponse:
    """
    Returns the largest Louvain communities (requires task-011 community detection
    to have been run so Person.community is populated). Each community includes its
    most common GitHub label (team signal) and top members by PageRank score.
    """
    # First get communities with size and most-common label
    community_cypher = """
        MATCH (p:Person)
        WHERE p.community IS NOT NULL
        WITH p.community AS community_id, COUNT(p) AS size
        ORDER BY size DESC
        LIMIT $top_communities
        RETURN community_id, size
    """
    community_rows = run_query(community_cypher, {"top_communities": top_communities})

    if not community_rows:
        raise HTTPException(
            status_code=404,
            detail=(
                "No community data found. Run the Louvain community detection notebook "
                "(task-011) to populate Person.community properties."
            ),
        )

    total_communities_cypher = """
        MATCH (p:Person)
        WHERE p.community IS NOT NULL
        RETURN COUNT(DISTINCT p.community) AS total
    """
    total_rows = run_query(total_communities_cypher)
    total = int(total_rows[0]["total"]) if total_rows else 0

    communities: list[CommunitySummary] = []

    for row in community_rows:
        cid = int(row["community_id"])
        size = int(row["size"])

        # Most common label for this community
        label_cypher = """
            MATCH (p:Person)-[:AUTHORED]->(pr:PullRequest)-[:HAS_LABEL]->(l:Label)
            WHERE p.community = $community_id
            RETURN l.name AS label_name, COUNT(pr) AS freq
            ORDER BY freq DESC
            LIMIT 1
        """
        label_rows = run_query(label_cypher, {"community_id": cid})
        top_label = label_rows[0]["label_name"] if label_rows else None

        # Top members by pagerank_score property (written by task-012 notebook)
        members_cypher = """
            MATCH (p:Person)
            WHERE p.community = $community_id
            RETURN p.login AS login,
                   p.pagerank_score AS pagerank_score
            ORDER BY coalesce(p.pagerank_score, 0.0) DESC
            LIMIT $members_per_community
        """
        member_rows = run_query(
            members_cypher,
            {"community_id": cid, "members_per_community": members_per_community},
        )
        members = [
            CommunityMember(
                login=mr["login"],
                pagerank_score=(
                    float(mr["pagerank_score"])
                    if mr["pagerank_score"] is not None
                    else None
                ),
            )
            for mr in member_rows
        ]

        communities.append(
            CommunitySummary(
                community_id=cid,
                size=size,
                top_label=top_label,
                members=members,
            )
        )

    return CommunitySummaryResponse(
        total_communities=total,
        communities=communities,
    )
