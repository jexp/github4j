// ============================================================
// GitHub Wrapped — Neo4j Graph Type Schema
// Neo4j 2026.02+ / AuraDB / Cypher 25 required
// ============================================================
// Run this ONCE before seed.py on a blank database.
// ALTER CURRENT GRAPH TYPE SET overwrites any previous definition.
// It enforces types and uniqueness constraints automatically.
// ============================================================

// ============================================================
// 1. GRAPH TYPE — nodes, properties, types, key constraints
// ============================================================

ALTER CURRENT GRAPH TYPE SET {

    // Person — identified by login
    (p:Person => {
        login :: STRING NOT NULL IS KEY,
        url   :: STRING
    }),

    // Repo — identified by repoId
    (r:Repo => {
        repoId :: STRING NOT NULL IS KEY,
        owner  :: STRING,
        name   :: STRING,
        url    :: STRING
    }),

    // PullRequest — all numeric/boolean/datetime fields typed explicitly
    (pr:PullRequest => {
        prId         :: STRING NOT NULL IS KEY,
        number       :: INTEGER,
        title        :: STRING,
        url          :: STRING,
        state        :: STRING,
        isDraft      :: BOOLEAN,
        createdAt    :: ZONED DATETIME,
        mergedAt     :: ZONED DATETIME,
        closedAt     :: ZONED DATETIME,
        additions    :: INTEGER,
        deletions    :: INTEGER,
        changedFiles :: INTEGER,
        baseRefName  :: STRING,
        commentCount :: INTEGER,
        // populated separately by embed.py — optional
        titleEmbedding :: LIST<FLOAT>
    }),

    // File — identified by fileId
    (f:File => {
        fileId    :: STRING NOT NULL IS KEY,
        path      :: STRING,
        filename  :: STRING,
        directory :: STRING,
        url       :: STRING
    }),

    // Directory — composite key on (path, repoId)
    (d:Directory => {
        path   :: STRING NOT NULL,
        repoId :: STRING NOT NULL
    })
      REQUIRE (d.path, d.repoId) IS KEY,

    // Label — identified by name
    (l:Label => {
        name :: STRING NOT NULL IS KEY
    }),

    // ── Relationships ────────────────────────────────────────

    (:Person)-[:AUTHORED]->(:PullRequest),

    (:Person)-[:REVIEWED => {
        state        :: STRING,
        submittedAt  :: ZONED DATETIME,
        commentCount :: INTEGER
    }]->(:PullRequest),

    (:Person)-[:MERGED]->(:PullRequest),

    (:PullRequest)-[:IN_REPO]->(:Repo),

    (:PullRequest)-[:TOUCHES => {
        additions :: INTEGER,
        deletions :: INTEGER
    }]->(:File),

    (:File)-[:IN_DIR]->(:Directory),

    (:PullRequest)-[:HAS_LABEL]->(:Label)
}

// ============================================================
// 2. RANGE INDEXES — timeseries and numeric fields
//    (Graph type does not create these automatically)
// ============================================================

CREATE RANGE INDEX pr_createdAt IF NOT EXISTS FOR (pr:PullRequest) ON (pr.createdAt);
CREATE RANGE INDEX pr_mergedAt  IF NOT EXISTS FOR (pr:PullRequest) ON (pr.mergedAt);
CREATE RANGE INDEX pr_closedAt  IF NOT EXISTS FOR (pr:PullRequest) ON (pr.closedAt);
CREATE RANGE INDEX pr_additions IF NOT EXISTS FOR (pr:PullRequest) ON (pr.additions);
CREATE RANGE INDEX pr_deletions IF NOT EXISTS FOR (pr:PullRequest) ON (pr.deletions);
CREATE RANGE INDEX pr_state     IF NOT EXISTS FOR (pr:PullRequest) ON (pr.state);
CREATE RANGE INDEX reviewed_submittedAt IF NOT EXISTS FOR ()-[r:REVIEWED]-() ON (r.submittedAt);

// ============================================================
// 3. TEXT INDEXES — fast CONTAINS / STARTS WITH
// ============================================================

CREATE TEXT INDEX pr_title_text      IF NOT EXISTS FOR (pr:PullRequest) ON (pr.title);
CREATE TEXT INDEX file_path_text     IF NOT EXISTS FOR (f:File) ON (f.path);
CREATE TEXT INDEX file_filename_text IF NOT EXISTS FOR (f:File) ON (f.filename);
CREATE TEXT INDEX person_login_text  IF NOT EXISTS FOR (p:Person) ON (p.login);
CREATE TEXT INDEX label_name_text    IF NOT EXISTS FOR (l:Label) ON (l.name);

// ============================================================
// 4. FULLTEXT INDEXES — free-text search
// ============================================================

CREATE FULLTEXT INDEX pr_title_fulltext     IF NOT EXISTS FOR (n:PullRequest) ON EACH [n.title];
CREATE FULLTEXT INDEX file_path_fulltext    IF NOT EXISTS FOR (n:File) ON EACH [n.path, n.filename];
CREATE FULLTEXT INDEX person_login_fulltext IF NOT EXISTS FOR (n:Person) ON EACH [n.login];

// ============================================================
// 5. VECTOR INDEX — semantic similarity on PR title embeddings
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

SHOW CONSTRAINTS YIELD name, type, labelsOrTypes, properties
ORDER BY type, name;

SHOW INDEXES YIELD name, type, labelsOrTypes, properties, state
ORDER BY type, name;
