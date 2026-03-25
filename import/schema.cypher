// ============================================================
// GitHub Wrapped — Neo4j Property Graph Schema
// ============================================================
//
// NODE LABELS
// -----------
// (:Person   {login: String, url: String})
// (:Repo     {repoId: String, owner: String, name: String, url: String})
// (:PullRequest {
//     prId: String,
//     number: Integer,
//     title: String,
//     url: String,
//     state: String,            -- OPEN | CLOSED | MERGED
//     isDraft: Boolean,
//     createdAt: DateTime,
//     mergedAt: DateTime,       -- null if not merged
//     closedAt: DateTime,       -- null if still open
//     additions: Integer,
//     deletions: Integer,
//     changedFiles: Integer,
//     baseRefName: String,
//     commentCount: Integer
// })
// (:File {fileId: String, path: String, filename: String, directory: String, url: String})
// (:Directory {path: String, repoId: String})
// (:Label {name: String})
//
// RELATIONSHIP TYPES
// ------------------
// (:Person)-[:AUTHORED]->(:PullRequest)
// (:Person)-[:REVIEWED {state: String, submittedAt: DateTime, commentCount: Integer}]->(:PullRequest)
// (:Person)-[:MERGED]->(:PullRequest)
// (:PullRequest)-[:IN_REPO]->(:Repo)
// (:PullRequest)-[:TOUCHES {additions: Integer, deletions: Integer}]->(:File)
// (:File)-[:IN_DIR]->(:Directory)
// (:PullRequest)-[:HAS_LABEL]->(:Label)
//
// ============================================================
// CONSTRAINTS & INDEXES
// ============================================================

// Uniqueness constraints (also create backing index automatically)
CREATE CONSTRAINT person_login_unique IF NOT EXISTS
FOR (p:Person) REQUIRE p.login IS UNIQUE;

CREATE CONSTRAINT repo_repoId_unique IF NOT EXISTS
FOR (r:Repo) REQUIRE r.repoId IS UNIQUE;

CREATE CONSTRAINT pr_prId_unique IF NOT EXISTS
FOR (pr:PullRequest) REQUIRE pr.prId IS UNIQUE;

CREATE CONSTRAINT file_fileId_unique IF NOT EXISTS
FOR (f:File) REQUIRE f.fileId IS UNIQUE;

CREATE CONSTRAINT label_name_unique IF NOT EXISTS
FOR (l:Label) REQUIRE l.name IS UNIQUE;

CREATE CONSTRAINT directory_path_unique IF NOT EXISTS
FOR (d:Directory) REQUIRE (d.path, d.repoId) IS UNIQUE;

// Additional indexes for common query patterns
CREATE INDEX pr_state IF NOT EXISTS
FOR (pr:PullRequest) ON (pr.state);

CREATE INDEX pr_createdAt IF NOT EXISTS
FOR (pr:PullRequest) ON (pr.createdAt);

CREATE INDEX pr_mergedAt IF NOT EXISTS
FOR (pr:PullRequest) ON (pr.mergedAt);

// Verify indexes
SHOW INDEXES;
