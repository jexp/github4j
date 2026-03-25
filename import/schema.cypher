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
//     commentCount: Integer,
//     titleEmbedding: Float[]   -- optional: add via embedding pipeline
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

// ============================================================
// 1. UNIQUENESS CONSTRAINTS
//    (each implicitly creates a backing RANGE index)
// ============================================================

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

CREATE CONSTRAINT directory_path_repoId_unique IF NOT EXISTS
FOR (d:Directory) REQUIRE (d.path, d.repoId) IS UNIQUE;

// ============================================================
// 2. RANGE INDEXES — timeseries and numeric fields
//    Efficient for ORDER BY, range filters (>, <, BETWEEN)
// ============================================================

CREATE RANGE INDEX pr_createdAt IF NOT EXISTS
FOR (pr:PullRequest) ON (pr.createdAt);

CREATE RANGE INDEX pr_mergedAt IF NOT EXISTS
FOR (pr:PullRequest) ON (pr.mergedAt);

CREATE RANGE INDEX pr_closedAt IF NOT EXISTS
FOR (pr:PullRequest) ON (pr.closedAt);

CREATE RANGE INDEX pr_additions IF NOT EXISTS
FOR (pr:PullRequest) ON (pr.additions);

CREATE RANGE INDEX pr_deletions IF NOT EXISTS
FOR (pr:PullRequest) ON (pr.deletions);

CREATE RANGE INDEX pr_state IF NOT EXISTS
FOR (pr:PullRequest) ON (pr.state);

// For relationship property range queries (e.g. filter by review date)
CREATE RANGE INDEX reviewed_submittedAt IF NOT EXISTS
FOR ()-[r:REVIEWED]-() ON (r.submittedAt);

// ============================================================
// 3. TEXT INDEXES — string pattern matching
//    Efficient for CONTAINS, STARTS WITH, ENDS WITH
//    (much faster than RANGE index for string ops)
// ============================================================

CREATE TEXT INDEX pr_title_text IF NOT EXISTS
FOR (pr:PullRequest) ON (pr.title);

CREATE TEXT INDEX file_path_text IF NOT EXISTS
FOR (f:File) ON (f.path);

CREATE TEXT INDEX file_filename_text IF NOT EXISTS
FOR (f:File) ON (f.filename);

CREATE TEXT INDEX person_login_text IF NOT EXISTS
FOR (p:Person) ON (p.login);

CREATE TEXT INDEX label_name_text IF NOT EXISTS
FOR (l:Label) ON (l.name);

// ============================================================
// 4. FULLTEXT INDEXES — free-text search across properties
//    Query with: CALL db.index.fulltext.queryNodes('index', 'term')
// ============================================================

// Search PR titles — find "fix", "refactor", "chore", bug keywords, etc.
CREATE FULLTEXT INDEX pr_title_fulltext IF NOT EXISTS
FOR (n:PullRequest) ON EACH [n.title];

// Search file paths — find e.g. "auth", "migration", "test"
CREATE FULLTEXT INDEX file_path_fulltext IF NOT EXISTS
FOR (n:File) ON EACH [n.path, n.filename];

// Search persons by login
CREATE FULLTEXT INDEX person_login_fulltext IF NOT EXISTS
FOR (n:Person) ON EACH [n.login];

// ============================================================
// 5. VECTOR INDEX — semantic similarity search on PR titles
//    Requires titleEmbedding Float[] property to be populated.
//    Use an embedding pipeline (e.g. OpenAI text-embedding-3-small
//    or a local model) to add embeddings after import.
//
//    Query with:
//      CALL db.index.vector.queryNodes('pr_title_vector', 10, $embedding)
//      YIELD node, score
// ============================================================

CREATE VECTOR INDEX pr_title_vector IF NOT EXISTS
FOR (pr:PullRequest) ON (pr.titleEmbedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1536,
    `vector.similarity_function`: 'cosine'
  }
};

// ============================================================
// 6. VERIFY
// ============================================================

SHOW INDEXES YIELD name, type, labelsOrTypes, properties, state
ORDER BY type, name;
