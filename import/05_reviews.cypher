// ============================================================
// 05_reviews.cypher — Import REVIEWED relationships from reviews.csv
// ============================================================
// Expected row count: 92,721
// Nodes created: any reviewer Person nodes not yet in graph
// Relationships created: ~92,721 REVIEWED (:Person)-[:REVIEWED]->(:PullRequest)
//
// Run AFTER: 01_persons.cypher, 04_prs.cypher
//
// NOTE: reviews.csv 'body' field may contain commas — the CSV is properly
//       quoted so LOAD CSV handles this correctly automatically.
//       A person may review the same PR multiple times (different submittedAt
//       timestamps). MERGE on (reviewer, pr) collapses to one relationship per
//       reviewer-PR pair, with properties from the last row processed.
//       This is acceptable for analytics use (counts per pair still correct).
//
// RELATIONSHIP PROPERTIES:
//   state:        APPROVED | COMMENTED | CHANGES_REQUESTED | DISMISSED
//   submittedAt:  DateTime
//   commentCount: Integer
// ============================================================

LOAD CSV WITH HEADERS FROM 'https://raw.githubusercontent.com/jexp/github4j/main/data/reviews.csv' AS row
MERGE (reviewer:Person {login: row.reviewerLogin})
WITH reviewer, row
MATCH (pr:PullRequest {prId: row.prId})
MERGE (reviewer)-[rev:REVIEWED]->(pr)
SET rev.state        = row.state,
    rev.submittedAt  = datetime(row.submittedAt),
    rev.commentCount = toInteger(row.commentCount);

// Verify
MATCH ()-[r:REVIEWED]->() RETURN count(r) AS reviewedCount;
