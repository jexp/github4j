#!/usr/bin/env python3
"""
embed.py — Embed PR titles and populate the pr_title_vector index in AuraDB.

Reads all PullRequest nodes that lack a titleEmbedding property, calls an
embedding model (OpenAI text-embedding-3-small by default, or a local
sentence-transformers model), and writes the resulting Float[1536] vector
back to each PullRequest node.

Usage:
    uv run embed.py                         # OpenAI, batch=100
    uv run embed.py --batch 50              # smaller batches
    uv run embed.py --model st              # sentence-transformers (local)
    uv run embed.py --force                 # re-embed all PRs (overwrite existing)

Environment:
    NEO4J_URI        AuraDB URI (e.g. neo4j+s://xxxxx.databases.neo4j.io)
    NEO4J_USER       AuraDB username (default: neo4j)
    NEO4J_PASSWORD   AuraDB password
    NEO4J_DATABASE   database name (default: neo4j)
    OPENAI_API_KEY   required for --model openai (default)

After running, verify with:
    MATCH (pr:PullRequest) WHERE pr.titleEmbedding IS NOT NULL RETURN COUNT(pr)
    CALL db.index.vector.queryNodes('pr_title_vector', 5, $vec) YIELD node, score
        RETURN node.title, score
    -- or use the /tools/search_similar_prs endpoint if MCP server is deployed.

Example similarity query (from Python or Neo4j Browser):
    # 1. Embed your query string with the same model
    # 2. CALL db.index.vector.queryNodes('pr_title_vector', 10, $queryVec)
    #    YIELD node, score
    #    RETURN node.prId, node.title, score ORDER BY score DESC
"""

import argparse
import os
import sys
import time
from pathlib import Path

# neo4j-rust-ext is a drop-in replacement for the neo4j package
from neo4j import GraphDatabase


# ---------------------------------------------------------------------------
# Env helpers
# ---------------------------------------------------------------------------

def _load_env_file() -> None:
    """Load key=value pairs from integration.env (cwd or parent) without python-dotenv."""
    for candidate in [Path.cwd() / "integration.env", Path.cwd().parent / "integration.env"]:
        if candidate.exists():
            with candidate.open() as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip()
                    if key and key not in os.environ:   # don't override real env
                        os.environ[key] = val
            break


# ---------------------------------------------------------------------------
# Embedding providers
# ---------------------------------------------------------------------------

OPENAI_DIMENSION = 1536
ST_DIMENSION = 1536   # all-mpnet-base-v2 is 768; we use all-MiniLM-L12-v2 → 384
                       # For 1536-dim match we use text-embedding-3-small output
                       # For ST fallback we allow mismatched dims (user configures index)


def embed_openai(texts: list[str], model: str = "text-embedding-3-small") -> list[list[float]]:
    """Call OpenAI Embeddings API; returns list of float vectors."""
    try:
        from openai import OpenAI  # type: ignore
    except ImportError:
        print("ERROR: openai package not installed. Run: uv add openai", file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    client = OpenAI(api_key=api_key)
    response = client.embeddings.create(input=texts, model=model)
    return [item.embedding for item in response.data]


def embed_sentence_transformers(texts: list[str], model_name: str = "all-MiniLM-L6-v2") -> list[list[float]]:
    """Embed using a local sentence-transformers model."""
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
    except ImportError:
        print(
            "ERROR: sentence-transformers not installed. Run: uv add sentence-transformers",
            file=sys.stderr,
        )
        sys.exit(1)

    st_model = SentenceTransformer(model_name)
    vecs = st_model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return [v.tolist() for v in vecs]


# ---------------------------------------------------------------------------
# Neo4j helpers
# ---------------------------------------------------------------------------

def get_driver():
    uri  = os.environ.get("NEO4J_URI", "neo4j+s://localhost:7687")
    user = os.environ.get("NEO4J_USER") or os.environ.get("NEO4J_USERNAME", "neo4j")
    pw   = os.environ.get("NEO4J_PASSWORD", "")
    drv  = GraphDatabase.driver(uri, auth=(user, pw))
    drv.verify_connectivity()
    return drv


def fetch_prs(session, force: bool) -> list[dict]:
    """Return list of {prId, title} for PRs that still need embedding."""
    if force:
        cypher = "MATCH (pr:PullRequest) WHERE pr.title IS NOT NULL RETURN pr.prId AS prId, pr.title AS title"
    else:
        cypher = (
            "MATCH (pr:PullRequest) WHERE pr.title IS NOT NULL "
            "AND pr.titleEmbedding IS NULL "
            "RETURN pr.prId AS prId, pr.title AS title"
        )
    result = session.run(cypher)
    return [{"prId": r["prId"], "title": r["title"]} for r in result]


def write_embeddings(session, db: str, batch: list[dict]) -> int:
    """Write titleEmbedding vectors back to PullRequest nodes. Returns count written."""
    result = session.run(
        """
        UNWIND $rows AS row
        MATCH (pr:PullRequest {prId: row.prId})
        SET pr.titleEmbedding = row.embedding
        """,
        rows=batch,
    )
    summary = result.consume()
    return summary.counters.properties_set


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Embed PR titles and write vectors to AuraDB pr_title_vector index."
    )
    parser.add_argument(
        "--model",
        choices=["openai", "st"],
        default="openai",
        help="Embedding provider: 'openai' (text-embedding-3-small, 1536-dim, default) "
             "or 'st' (sentence-transformers local model, 384-dim — requires separate vector index config).",
    )
    parser.add_argument(
        "--openai-model",
        default="text-embedding-3-small",
        help="OpenAI embedding model name (default: text-embedding-3-small).",
    )
    parser.add_argument(
        "--st-model",
        default="all-MiniLM-L6-v2",
        help="sentence-transformers model name (default: all-MiniLM-L6-v2).",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=100,
        help="Number of PR titles to embed per API call (default: 100).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-embed and overwrite PRs that already have titleEmbedding set.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch PRs and show count but do not call embedding API or write to AuraDB.",
    )
    return parser.parse_args()


def main() -> None:
    _load_env_file()
    args = parse_args()

    db = os.environ.get("NEO4J_DATABASE", "neo4j")

    print(f"Connecting to {os.environ.get('NEO4J_URI', 'neo4j+s://localhost:7687')} …")
    driver = get_driver()
    print("Connected ✓\n")

    try:
        with driver.session(database=db) as session:

            # ----------------------------------------------------------
            # 1. Fetch PRs that need embedding
            # ----------------------------------------------------------
            print("Fetching PRs" + (" (all, --force)" if args.force else " (without titleEmbedding)") + " …")
            prs = fetch_prs(session, force=args.force)
            total = len(prs)
            print(f"  Found {total} PR(s) to embed.\n")

            if total == 0:
                print("Nothing to do — all PR titles are already embedded.")
                print("Use --force to re-embed everything.")
                return

            if args.dry_run:
                print(f"[dry-run] Would embed {total} PRs with model={args.model!r}, batch={args.batch}.")
                return

            # ----------------------------------------------------------
            # 2. Embed in batches
            # ----------------------------------------------------------
            embed_fn = (
                (lambda texts: embed_openai(texts, model=args.openai_model))
                if args.model == "openai"
                else (lambda texts: embed_sentence_transformers(texts, model_name=args.st_model))
            )

            model_label = args.openai_model if args.model == "openai" else args.st_model
            print(f"Embedding with model={model_label!r}, batch_size={args.batch} …")

            total_written = 0
            t_start = time.time()

            for batch_start in range(0, total, args.batch):
                chunk = prs[batch_start : batch_start + args.batch]
                titles = [r["title"] for r in chunk]

                # Call embedding provider
                try:
                    vectors = embed_fn(titles)
                except Exception as exc:
                    print(f"\nERROR calling embedding API: {exc}", file=sys.stderr)
                    sys.exit(1)

                # Build write payload
                rows = [
                    {"prId": chunk[i]["prId"], "embedding": vectors[i]}
                    for i in range(len(chunk))
                ]

                # Write back to AuraDB
                with driver.session(database=db) as write_session:
                    written = write_embeddings(write_session, db, rows)
                    total_written += written

                done = min(batch_start + args.batch, total)
                elapsed = time.time() - t_start
                rate = done / elapsed if elapsed > 0 else 0
                print(f"  Embedded {done}/{total} PRs  ({rate:.1f} PR/s)", end="\r")

            print(f"\n  Wrote titleEmbedding to {total_written} PullRequest node(s). ✓")
            elapsed = time.time() - t_start
            print(f"  Total time: {elapsed:.1f}s\n")

            # ----------------------------------------------------------
            # 3. Smoke-test: verify vector index returns results
            # ----------------------------------------------------------
            print("Verifying vector index …")
            # Use the first PR's embedding as a test query vector
            with driver.session(database=db) as verify_session:
                sample = verify_session.run(
                    "MATCH (pr:PullRequest) WHERE pr.titleEmbedding IS NOT NULL "
                    "RETURN pr.titleEmbedding AS vec LIMIT 1"
                ).single()

                if sample is None:
                    print("  WARNING: No nodes with titleEmbedding found after write — check AuraDB connection.")
                else:
                    similar = verify_session.run(
                        """
                        CALL db.index.vector.queryNodes('pr_title_vector', 5, $vec)
                        YIELD node, score
                        RETURN node.title AS title, score
                        """,
                        vec=sample["vec"],
                    ).data()
                    if similar:
                        print(f"  Vector index returns {len(similar)} result(s) ✓")
                        print("  Top match:", similar[0]["title"][:80])
                    else:
                        print("  WARNING: Vector index query returned 0 results — index may still be building.")

    finally:
        driver.close()

    print(
        "\nExample similarity search (Neo4j Browser / Cypher):\n"
        "  CALL db.index.vector.queryNodes('pr_title_vector', 10, $vec)\n"
        "  YIELD node, score\n"
        "  RETURN node.prId, node.title, score ORDER BY score DESC\n"
        "\n"
        "  -- replace $vec with the embedding of your query string\n"
        "  -- e.g. embed 'fix authentication bug' and use that vector"
    )


if __name__ == "__main__":
    main()
