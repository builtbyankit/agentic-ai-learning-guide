"""Ingest a tiny Markdown/HTML corpus and query its local SQLite vector store."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rag_pipeline import HashingEmbedder, SQLiteVectorStore, load_manifest_documents


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="rag-demo.sqlite", help="SQLite file used for vectors and metadata")
    parser.add_argument("--query", default="An item arrived damaged. How long do I have to tell support?")
    parser.add_argument("--tenant", default="demo-tenant", help="Trusted tenant scope for this demo")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument(
        "--classification",
        action="append",
        choices=("public", "internal", "confidential", "restricted"),
        help="May be repeated; omit to allow internal sources in this synthetic demo",
    )
    args = parser.parse_args()

    base = Path(__file__).resolve().parent
    documents = load_manifest_documents(base / "knowledge" / "manifest.json")
    embedder = HashingEmbedder()
    store = SQLiteVectorStore(args.db, embedder)
    try:
        ingested = sum(store.ingest(document) for document in documents)
        hits = store.search(
            tenant_id=args.tenant,
            query=args.query,
            allowed_classifications=args.classification or ["internal"],
            top_k=args.top_k,
            min_score=0.05,
        )
        print(json.dumps({
            "embedding_model": embedder.model_id,
            "chunks_ingested_or_refreshed": ingested,
            "results": [
                {
                    "score": hit.score,
                    "source_id": hit.source_id,
                    "version": hit.version,
                    "effective_date": hit.effective_date,
                    "section": hit.section_path,
                    "classification": hit.classification,
                    "text": hit.text,
                }
                for hit in hits
            ],
        }, ensure_ascii=False, indent=2))
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
