// ============================================================
// 03_files.cypher — Import File and Directory nodes from files.csv
// ============================================================
// Expected row count: 52,996
// Nodes created: ~52,996 File nodes + ~12,701 Directory nodes
// Relationships created: ~52,731 IN_DIR relationships
//
// Run AFTER: 02_repos.cypher
// Run BEFORE: 06_files_touched.cypher
//
// NOTE: files.csv has a 'directory' field that may be empty (file at repo root).
//       Directory nodes are only created when directory is non-empty.
//       Directory uniqueness is composite: (path, repoId).
// ============================================================

// --- Pass 1: Create File nodes ---
LOAD CSV WITH HEADERS FROM 'https://raw.githubusercontent.com/jexp/github4j/main/data/files.csv' AS row
MERGE (f:File {fileId: row.fileId})
SET f.path      = row.path,
    f.filename  = row.filename,
    f.directory = row.directory,
    f.url       = row.url;

// --- Pass 2: Create Directory nodes and IN_DIR relationships ---
// Only for files that have a non-empty directory field
LOAD CSV WITH HEADERS FROM 'https://raw.githubusercontent.com/jexp/github4j/main/data/files.csv' AS row
WITH row WHERE row.directory IS NOT NULL AND row.directory <> ''
MERGE (d:Directory {path: row.directory, repoId: row.repoId})
WITH d, row
MATCH (f:File {fileId: row.fileId})
MERGE (f)-[:IN_DIR]->(d);

// Verify
MATCH (f:File)      RETURN count(f) AS fileCount;
MATCH (d:Directory) RETURN count(d) AS directoryCount;
MATCH ()-[r:IN_DIR]->() RETURN count(r) AS inDirRelCount;
