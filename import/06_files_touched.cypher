// ============================================================
// 06_files_touched.cypher — Import TOUCHES relationships from files_touched.csv
// ============================================================
// Expected row count: 206,196
// Nodes created: none (all PRs and Files already exist)
// Relationships created: ~206,196 TOUCHES (:PullRequest)-[:TOUCHES]->(:File)
//
// Run AFTER: 03_files.cypher, 04_prs.cypher
//
// ⚠️  AuraDB FREE TIER CAPACITY WARNING ⚠️
// Estimated total relationships after full import: ~507k
// AuraDB Free tier limit: 400k relationships
// Breakdown:
//   AUTHORED:   32,252
//   IN_REPO:    32,252
//   MERGED:     25,232
//   HAS_LABEL:  65,893
//   REVIEWED:   92,721
//   IN_DIR:     52,731
//   TOUCHES:   206,196  ← largest contributor
//   TOTAL:     507,277
//
// Options to stay within the 400k limit:
//   a) Use a paid AuraDB tier (Professional or Enterprise)
//   b) Import a subset using Option B below (restricts to one repo)
//   c) Skip TOUCHES entirely — hero stats (Great Deleter, Bug Slayer)
//      do not require TOUCHES; only hottest-files queries do.
//
// RELATIONSHIP PROPERTIES:
//   additions: Integer — lines added in this file for this PR
//   deletions: Integer — lines deleted in this file for this PR
// ============================================================

// Option A: Full import (may exceed AuraDB Free tier — use paid tier)
LOAD CSV WITH HEADERS FROM 'https://raw.githubusercontent.com/jexp/github4j/main/data/files_touched.csv' AS row
MATCH (pr:PullRequest {prId: row.prId})
MATCH (f:File {fileId: row.fileId})
MERGE (pr)-[t:TOUCHES]->(f)
SET t.additions = toInteger(row.additions),
    t.deletions = toInteger(row.deletions);

// Verify
MATCH ()-[r:TOUCHES]->() RETURN count(r) AS touchesCount;

// ============================================================
// Option B: Partial import — restrict to one repo to stay within 400k limit.
// Comment out Option A above and uncomment the block below.
// Replace 'neo4j/upx' with your target repo repoId.
// ============================================================
// LOAD CSV WITH HEADERS FROM 'https://raw.githubusercontent.com/jexp/github4j/main/data/files_touched.csv' AS row
// WITH row WHERE row.repoId = 'neo4j/upx'
// MATCH (pr:PullRequest {prId: row.prId})
// MATCH (f:File {fileId: row.fileId})
// MERGE (pr)-[t:TOUCHES]->(f)
// SET t.additions = toInteger(row.additions),
//     t.deletions = toInteger(row.deletions);
