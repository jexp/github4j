// ============================================================
// verify.cypher — Post-import sanity checks for GitHub Wrapped graph
// ============================================================
// Run AFTER all 6 import scripts have completed.
// Expected data: 348 persons, 14 repos, 32,252 PRs, 92,721 reviews,
//                52,996 files, ~12,701 directories, ~538 labels.
// ============================================================

// ============================================================
// SECTION 1: Node counts per label
// ============================================================

MATCH (p:Person)     RETURN 'Person'     AS label, count(p) AS nodeCount;
// Expected: 348 (from persons.csv) plus any extra persons added during PR/review import

MATCH (r:Repo)       RETURN 'Repo'       AS label, count(r) AS nodeCount;
// Expected: 14

MATCH (pr:PullRequest) RETURN 'PullRequest' AS label, count(pr) AS nodeCount;
// Expected: 32,252

MATCH (f:File)       RETURN 'File'       AS label, count(f) AS nodeCount;
// Expected: 52,996

MATCH (d:Directory)  RETURN 'Directory'  AS label, count(d) AS nodeCount;
// Expected: ~12,701

MATCH (l:Label)      RETURN 'Label'      AS label, count(l) AS nodeCount;
// Expected: ~538

// All node labels summary — run individual counts above for full picture
// (APOC dynamic query approach omitted for AuraDB compatibility)

// ============================================================
// SECTION 2: Relationship counts per type
// ============================================================

MATCH ()-[r:AUTHORED]->()   RETURN 'AUTHORED'   AS type, count(r) AS relCount;
// Expected: ~32,252 (one per PR)

MATCH ()-[r:REVIEWED]->()   RETURN 'REVIEWED'   AS type, count(r) AS relCount;
// Expected: ≤92,721 (collapsed to one per reviewer+PR pair)

MATCH ()-[r:MERGED]->()     RETURN 'MERGED'     AS type, count(r) AS relCount;
// Expected: ~25,232 (PRs where mergedBy is non-empty)

MATCH ()-[r:IN_REPO]->()    RETURN 'IN_REPO'    AS type, count(r) AS relCount;
// Expected: ~32,252 (one per PR)

MATCH ()-[r:HAS_LABEL]->()  RETURN 'HAS_LABEL'  AS type, count(r) AS relCount;
// Expected: ~65,893

MATCH ()-[r:IN_DIR]->()     RETURN 'IN_DIR'     AS type, count(r) AS relCount;
// Expected: ~52,996 (one per file that has a non-empty directory)

MATCH ()-[r:TOUCHES]->()    RETURN 'TOUCHES'    AS type, count(r) AS relCount;
// Expected: ≤206,196 (only if 06_files_touched.cypher was run; may be 0 or partial)

// ============================================================
// SECTION 3: Sample path traversals
// ============================================================

// 3a. Person → authored PR → in repo
MATCH (p:Person)-[:AUTHORED]->(pr:PullRequest)-[:IN_REPO]->(r:Repo)
RETURN p.login, pr.prId, r.name
LIMIT 5;

// 3b. Person → reviewed PR → authored by another person
MATCH (reviewer:Person)-[:REVIEWED]->(pr:PullRequest)<-[:AUTHORED]-(author:Person)
WHERE reviewer <> author
RETURN reviewer.login AS reviewer, author.login AS author, pr.prId
LIMIT 5;

// 3c. PR → has label → label name
MATCH (pr:PullRequest)-[:HAS_LABEL]->(l:Label)
RETURN pr.prId, collect(l.name) AS labels
LIMIT 5;

// 3d. File → in directory → (repoId check)
MATCH (f:File)-[:IN_DIR]->(d:Directory)
RETURN f.path, d.path AS dir, d.repoId
LIMIT 5;

// 3e. PR touches file (if files_touched imported)
MATCH (pr:PullRequest)-[t:TOUCHES]->(f:File)
RETURN pr.prId, f.path, t.additions, t.deletions
LIMIT 5;

// ============================================================
// SECTION 4: Hero stat — Great Deleter
// ============================================================
// Top 10 contributors by total lines deleted across all their PRs.
// Acceptance criterion: at least 5 results with non-zero deletions.

MATCH (p:Person)-[:AUTHORED]->(pr:PullRequest)
RETURN p.login AS contributor, sum(pr.deletions) AS linesDeleted
ORDER BY linesDeleted DESC
LIMIT 10;

// ============================================================
// SECTION 5: Hero stat — Bug Slayer
// ============================================================
// Top 10 contributors by count of merged PRs carrying the 'bug' label.
// Acceptance criterion: returns results (bug-labelled merged PRs exist).

MATCH (p:Person)-[:AUTHORED]->(pr:PullRequest)-[:HAS_LABEL]->(l:Label {name: 'bug'})
WHERE pr.state = 'MERGED'
RETURN p.login AS contributor, count(pr) AS bugsFixed
ORDER BY bugsFixed DESC
LIMIT 10;

// ============================================================
// SECTION 6: Collaboration pairs (author co-appears with reviewer on same PR)
// ============================================================
// Acceptance criterion: returns results.

MATCH (author:Person)-[:AUTHORED]->(pr:PullRequest)<-[:REVIEWED]-(reviewer:Person)
WHERE author <> reviewer
RETURN author.login AS author, reviewer.login AS reviewer, count(pr) AS sharedPRs
ORDER BY sharedPRs DESC
LIMIT 10;

// ============================================================
// SECTION 7: Supporting stat queries — spot-check
// ============================================================

// 7a. Top contributors by PRs opened
MATCH (p:Person)-[:AUTHORED]->(pr:PullRequest)
RETURN p.login AS contributor, count(pr) AS prsOpened
ORDER BY prsOpened DESC
LIMIT 10;

// 7b. Top reviewers by review count
MATCH (p:Person)-[:REVIEWED]->(pr:PullRequest)
RETURN p.login AS reviewer, count(pr) AS reviewCount
ORDER BY reviewCount DESC
LIMIT 10;

// 7c. Hottest files by distinct PR count (requires TOUCHES rels)
MATCH (pr:PullRequest)-[:TOUCHES]->(f:File)
RETURN f.path AS filePath, count(DISTINCT pr) AS prCount
ORDER BY prCount DESC
LIMIT 10;

// 7d. Hottest directories by distinct PR count (requires TOUCHES + IN_DIR)
MATCH (pr:PullRequest)-[:TOUCHES]->(f:File)-[:IN_DIR]->(d:Directory)
RETURN d.path AS directory, d.repoId AS repo, count(DISTINCT pr) AS prCount
ORDER BY prCount DESC
LIMIT 10;

// 7e. PR velocity: average hours open-to-merge by author (merged PRs only)
// duration.inSeconds() returns a Duration where .seconds is total elapsed seconds.
MATCH (p:Person)-[:AUTHORED]->(pr:PullRequest)
WHERE pr.state = 'MERGED' AND pr.mergedAt IS NOT NULL AND pr.createdAt IS NOT NULL
WITH p.login AS author,
     avg(duration.inSeconds(pr.createdAt, pr.mergedAt).seconds / 3600.0) AS avgHoursToMerge,
     count(pr) AS mergedPRs
WHERE mergedPRs >= 5
RETURN author, round(avgHoursToMerge, 1) AS avgHoursToMerge, mergedPRs
ORDER BY avgHoursToMerge ASC
LIMIT 10;

// 7f. Label leaderboard
MATCH (pr:PullRequest)-[:HAS_LABEL]->(l:Label)
RETURN l.name AS label, count(pr) AS prCount
ORDER BY prCount DESC
LIMIT 20;

// ============================================================
// SECTION 8: Data integrity checks
// ============================================================

// 8a. PRs with no AUTHORED relationship (should be 0)
MATCH (pr:PullRequest)
WHERE NOT ()-[:AUTHORED]->(pr)
RETURN count(pr) AS prsWithNoAuthor;
// Expected: 0

// 8b. PRs with no IN_REPO relationship (should be 0)
MATCH (pr:PullRequest)
WHERE NOT (pr)-[:IN_REPO]->()
RETURN count(pr) AS prsWithNoRepo;
// Expected: 0

// 8c. Files with no IN_DIR relationship (files at repo root — directory was empty in CSV)
MATCH (f:File)
WHERE NOT (f)-[:IN_DIR]->()
RETURN count(f) AS rootLevelFiles;
// Non-zero is acceptable (root-level files exist); just informational

// 8d. Persons with no activity (no AUTHORED, no REVIEWED, no MERGED)
MATCH (p:Person)
WHERE NOT ()-[:AUTHORED]->(p)
  AND NOT (p)-[:AUTHORED]->()
  AND NOT (p)-[:REVIEWED]->()
  AND NOT (p)-[:MERGED]->()
RETURN count(p) AS inactivePersons;
// Small number acceptable; persons.csv may include org members without recent PRs

// 8e. Check for duplicate PRs (should all be 1 due to MERGE on prId)
MATCH (pr:PullRequest)
WITH pr.prId AS prId, count(*) AS cnt
WHERE cnt > 1
RETURN prId, cnt AS duplicateCount
LIMIT 10;
// Expected: empty (no results)

// 8f. Verify state values are within expected set
MATCH (pr:PullRequest)
RETURN DISTINCT pr.state AS state, count(*) AS cnt
ORDER BY cnt DESC;
// Expected states: OPEN, CLOSED, MERGED

// 8g. Sample MERGED PRs with mergedAt datetime set
MATCH (p:Person)-[:MERGED]->(pr:PullRequest)
RETURN p.login AS mergedBy, pr.prId, pr.mergedAt
LIMIT 5;
// Should show valid datetime values, not null

// ============================================================
// SECTION 9: Scale check — verify within AuraDB Free tier limits
// ============================================================

MATCH (n) RETURN count(n) AS totalNodes;
// Must be ≤200,000

MATCH ()-[r]->() RETURN count(r) AS totalRelationships;
// Must be ≤400,000 (or ≤507k if on paid tier / accepted overage for TOUCHES)
