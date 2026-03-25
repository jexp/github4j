// ============================================================
// 02_repos.cypher — Import Repo nodes from repos.csv
// ============================================================
// Expected row count: 14
// Nodes created: ~14 Repo nodes
// Relationships created: none
//
// Run AFTER: schema.cypher
// Run BEFORE: 04_prs.cypher
// ============================================================

LOAD CSV WITH HEADERS FROM 'https://raw.githubusercontent.com/jexp/github4j/main/data/repos.csv' AS row
MERGE (r:Repo {repoId: row.repoId})
SET r.owner = row.owner,
    r.name  = row.name,
    r.url   = row.url;

// Verify
MATCH (r:Repo) RETURN count(r) AS repoCount;
