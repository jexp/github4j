// ============================================================
// 04_prs.cypher — Import PullRequest nodes, Label nodes, and relationships
// ============================================================
// Expected row count: 32,252
// Nodes created: ~32,252 PullRequest nodes + ~538 Label nodes
//                + any Person nodes not yet in graph (mergedBy persons)
// Relationships created:
//   ~32,252 AUTHORED  (:Person)-[:AUTHORED]->(:PullRequest)
//   ~32,252 IN_REPO   (:PullRequest)-[:IN_REPO]->(:Repo)
//   ~25,232 MERGED    (:Person)-[:MERGED]->(:PullRequest)  [only where mergedBy set]
//   ~65,893 HAS_LABEL (:PullRequest)-[:HAS_LABEL]->(:Label)
//
// Run AFTER: 01_persons.cypher, 02_repos.cypher
// Run BEFORE: 05_reviews.cypher, 06_files_touched.cypher
//
// NOTE: 'labels' field is semicolon-separated (e.g. "dependencies;plg").
//       Empty-string label values are skipped.
//       'mergedBy' can be empty — MERGED relationship only created when present.
//       isDraft stored as Boolean, additions/deletions/changedFiles as Integer.
//       mergedAt and closedAt stored as DateTime or null when empty string.
// ============================================================

// --- Pass 1: Create PullRequest nodes + AUTHORED + IN_REPO ---
LOAD CSV WITH HEADERS FROM 'https://raw.githubusercontent.com/neo4j-field/github-wrapped-neo4j/main/data/prs.csv' AS row
MERGE (pr:PullRequest {prId: row.prId})
SET pr.number       = toInteger(row.number),
    pr.title        = row.title,
    pr.url          = row.url,
    pr.state        = row.state,
    pr.isDraft      = (row.isDraft = 'true'),
    pr.createdAt    = datetime(row.createdAt),
    pr.mergedAt     = CASE WHEN row.mergedAt IS NOT NULL AND row.mergedAt <> ''
                          THEN datetime(row.mergedAt) ELSE null END,
    pr.closedAt     = CASE WHEN row.closedAt IS NOT NULL AND row.closedAt <> ''
                          THEN datetime(row.closedAt) ELSE null END,
    pr.additions    = toInteger(row.additions),
    pr.deletions    = toInteger(row.deletions),
    pr.changedFiles = toInteger(row.changedFiles),
    pr.baseRefName  = row.baseRefName,
    pr.commentCount = toInteger(row.commentCount)
WITH pr, row
MERGE (author:Person {login: row.authorLogin})
MERGE (author)-[:AUTHORED]->(pr)
WITH pr, row
MATCH (repo:Repo {repoId: row.repoId})
MERGE (pr)-[:IN_REPO]->(repo);

// --- Pass 2: MERGED relationships (only where mergedBy is non-empty) ---
LOAD CSV WITH HEADERS FROM 'https://raw.githubusercontent.com/neo4j-field/github-wrapped-neo4j/main/data/prs.csv' AS row
WITH row WHERE row.mergedBy IS NOT NULL AND row.mergedBy <> ''
MATCH (pr:PullRequest {prId: row.prId})
MERGE (merger:Person {login: row.mergedBy})
MERGE (merger)-[:MERGED]->(pr);

// --- Pass 3: Label nodes + HAS_LABEL relationships ---
LOAD CSV WITH HEADERS FROM 'https://raw.githubusercontent.com/neo4j-field/github-wrapped-neo4j/main/data/prs.csv' AS row
WITH row WHERE row.labels IS NOT NULL AND row.labels <> ''
MATCH (pr:PullRequest {prId: row.prId})
WITH pr, SPLIT(row.labels, ';') AS labelList
UNWIND labelList AS labelName
WITH pr, TRIM(labelName) AS labelName
WHERE labelName <> ''
MERGE (lbl:Label {name: labelName})
MERGE (pr)-[:HAS_LABEL]->(lbl);

// Verify
MATCH (pr:PullRequest)     RETURN count(pr) AS prCount;
MATCH (lbl:Label)          RETURN count(lbl) AS labelCount;
MATCH ()-[r:AUTHORED]->()  RETURN count(r) AS authoredCount;
MATCH ()-[r:IN_REPO]->()   RETURN count(r) AS inRepoCount;
MATCH ()-[r:MERGED]->()    RETURN count(r) AS mergedCount;
MATCH ()-[r:HAS_LABEL]->() RETURN count(r) AS hasLabelCount;
