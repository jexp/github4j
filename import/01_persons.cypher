// ============================================================
// 01_persons.cypher — Import Person nodes from persons.csv
// ============================================================
// Expected row count: 348
// Nodes created: ~348 Person nodes
// Relationships created: none
//
// Run AFTER: schema.cypher
// Run BEFORE: 04_prs.cypher, 05_reviews.cypher
//
// Usage: Paste into Neo4j Browser / Aura Query Editor.
// Update the URL below to point to your hosted CSV location.
// ============================================================

LOAD CSV WITH HEADERS FROM 'https://raw.githubusercontent.com/jexp/github4j/main/data/persons.csv' AS row
MERGE (p:Person {login: row.login})
SET p.url = row.url;

// Verify
MATCH (p:Person) RETURN count(p) AS personCount;
