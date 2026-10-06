"""Evaluate local RAG retrievers against versioned synthetic corpora and scenarios."""

from __future__ import annotations

import hashlib
import json
import argparse
import tempfile
from pathlib import Path
from typing import Any

from rag_pipeline import HashingEmbedder, SQLiteVectorStore, load_manifest_documents, normalize_text
from voyage_embedder import VoyageEmbedder


CHUNK_MAX_WORDS = 90
CHUNK_OVERLAP_WORDS = 18


def evaluate_dataset(
    dataset: dict[str, Any],
    *,
    retriever: str = "dense",
    manifest_path: str | Path | None = None,
    embedder: Any | None = None,
) -> dict[str, Any]:
    scenarios = dataset["scenarios"]
    if not scenarios:
        raise ValueError("RAG evaluation dataset must not be empty")
    top_k = int(dataset.get("top_k", 4))
    min_score = float(dataset.get("min_score", 0.0))
    lexical_relative_score_floor = float(dataset.get("lexical_relative_score_floor", 0.0))
    if top_k < 1 or top_k > 50:
        raise ValueError("top_k must be between 1 and 50")
    if retriever not in {"dense", "lexical", "hybrid"}:
        raise ValueError("retriever must be dense, lexical, or hybrid")
    embedder = embedder or HashingEmbedder()
    if retriever == "lexical" and isinstance(embedder, VoyageEmbedder):
        raise ValueError("Lexical retrieval does not use embeddings; choose --embedding-provider hashing.")

    manifest = Path(manifest_path) if manifest_path is not None else Path("knowledge/manifest.json")
    if not manifest.is_absolute():
        manifest = Path(__file__).parent / manifest
    documents = load_manifest_documents(manifest)
    corpus_records = [
        {
            "source_id": document.source_id,
            "tenant_id": document.tenant_id,
            "version": document.version,
            "effective_date": document.effective_date,
            "status": document.status,
            "classification": document.classification,
            "content_sha256": hashlib.sha256(
                normalize_text(document.text, redact_basic_pii=document.redact_basic_pii).encode("utf-8")
            ).hexdigest(),
        }
        for document in documents
    ]
    corpus_fingerprint = hashlib.sha256(
        json.dumps(corpus_records, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    dataset_fingerprint = hashlib.sha256(
        json.dumps(dataset, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    with tempfile.TemporaryDirectory() as temporary:
        store = SQLiteVectorStore(Path(temporary) / "rag-eval.sqlite", embedder)
        store.ingest_many(documents, max_words=CHUNK_MAX_WORDS, overlap_words=CHUNK_OVERLAP_WORDS)
        query_vectors: list[list[float] | None]
        if retriever == "lexical":
            query_vectors = [None] * len(scenarios)
        else:
            batch_queries = getattr(embedder, "embed_queries", None)
            query_texts = [scenario["query"] for scenario in scenarios]
            query_vectors = (
                batch_queries(query_texts)
                if callable(batch_queries)
                else [embedder.embed(query) for query in query_texts]
            )

        reports: list[dict[str, Any]] = []
        positive = 0
        hits_at_1 = 0
        recall_sum = 0.0
        reciprocal_rank_sum = 0.0
        relevant_total = 0
        returned_total = 0
        empty_total = 0
        empty_correct = 0
        authorization_total = 0
        authorization_violations = 0
        required_source_coverage = 0
        positive_source_coverage = 0

        for scenario_index, scenario in enumerate(scenarios):
            expected = set(scenario["expected_source_ids"])
            expected_versions = scenario.get("expected_versions", {})
            case_type = scenario.get("case_type", "positive" if expected else "no_answer")
            if case_type not in {"positive", "no_answer", "authorization"}:
                raise ValueError(f"Unsupported case_type {case_type!r} in {scenario['id']}.")
            forbidden_sources = set(scenario.get("forbidden_source_ids", []))
            if case_type == "authorization" and not forbidden_sources:
                raise ValueError(f"Authorization case {scenario['id']} must name forbidden_source_ids.")
            search_options = {
                "tenant_id": scenario.get("tenant_id", "demo-tenant"),
                "query": scenario["query"],
                "allowed_classifications": scenario.get(
                    "allowed_classifications", dataset.get("allowed_classifications", ["internal"])
                ),
                "top_k": int(scenario.get("top_k", top_k)),
            }
            if retriever == "dense":
                hits = store.search(
                    **search_options,
                    min_score=float(scenario.get("min_score", min_score)),
                    query_vector=query_vectors[scenario_index],
                )
            elif retriever == "lexical":
                hits = store.search_lexical(
                    **search_options,
                    relative_score_floor=float(
                        scenario.get("lexical_relative_score_floor", lexical_relative_score_floor)
                    ),
                )
            else:
                hits = store.search_hybrid(
                    **search_options,
                    min_dense_score=float(scenario.get("min_score", min_score)),
                    query_vector=query_vectors[scenario_index],
                    lexical_relative_score_floor=float(
                        scenario.get("lexical_relative_score_floor", lexical_relative_score_floor)
                    ),
                )
            retrieved: list[str] = []
            for hit in hits:
                if hit.source_id not in retrieved:
                    retrieved.append(hit.source_id)
            retrieved_set = set(retrieved)
            retrieved_versions = {
                hit.source_id: hit.version for hit in hits if hit.source_id in retrieved_set
            }
            versions_match = all(
                retrieved_versions.get(source_id) == version
                for source_id, version in expected_versions.items()
            )
            if case_type == "positive":
                is_covered = bool(expected) and expected <= retrieved_set and versions_match
            elif case_type == "no_answer":
                is_covered = not retrieved
            else:
                authorization_total += 1
                leaked_sources = forbidden_sources & retrieved_set
                authorization_violations += int(bool(leaked_sources))
                is_covered = expected <= retrieved_set and versions_match and not leaked_sources
            required_source_coverage += int(is_covered)
            if case_type == "positive" or (case_type == "authorization" and expected):
                positive_source_coverage += int(expected <= retrieved_set and versions_match)

            if case_type == "positive" or (case_type == "authorization" and expected):
                positive += 1
                relevant_total += len(expected & retrieved_set)
                returned_total += len(retrieved)
                recall_sum += len(expected & retrieved_set) / len(expected)
                hits_at_1 += int(bool(retrieved and retrieved[0] in expected))
                reciprocal_rank_sum += next(
                    (1.0 / rank for rank, source_id in enumerate(retrieved, start=1) if source_id in expected),
                    0.0,
                )
            elif case_type == "no_answer":
                empty_total += 1
                empty_correct += int(not retrieved)

            reports.append(
                {
                    "id": scenario["id"],
                    "case_type": case_type,
                    "expected_source_ids": sorted(expected),
                    "expected_versions": dict(sorted(expected_versions.items())),
                    "forbidden_source_ids": sorted(forbidden_sources),
                    "retrieved_source_ids": retrieved,
                    "retrieved_versions": retrieved_versions,
                    "retrieved_chunks": [
                        {
                            "chunk_id": hit.chunk_id,
                            "source_id": hit.source_id,
                            "version": hit.version,
                            "effective_date": hit.effective_date,
                            "section_path": hit.section_path,
                            "classification": hit.classification,
                            "score": hit.score,
                        }
                        for hit in hits
                    ],
                    "scores": [hit.score for hit in hits],
                    "pass": is_covered,
                }
            )
        store.close()

    total = len(scenarios)
    return {
        "dataset_version": dataset["dataset_version"],
        "split": dataset.get("split", "unspecified"),
        "manifest": str(manifest.relative_to(Path(__file__).parent))
        if manifest.is_relative_to(Path(__file__).parent)
        else manifest.name,
        "retriever": retriever,
        "embedding_provider": "voyage" if isinstance(embedder, VoyageEmbedder) else "hashing",
        "embedder_model_id": embedder.model_id,
        "embedding_request_count": int(getattr(embedder, "request_count", 0)),
        "embedding_input_tokens": int(getattr(embedder, "input_tokens", 0)),
        "corpus_sha256": corpus_fingerprint,
        "dataset_sha256": dataset_fingerprint,
        "chunking": {"max_words": CHUNK_MAX_WORDS, "overlap_words": CHUNK_OVERLAP_WORDS},
        "top_k_chunks": top_k,
        "min_score": min_score,
        "lexical_relative_score_floor": lexical_relative_score_floor,
        "total_queries": total,
        "positive_queries": positive,
        "empty_queries": empty_total,
        "authorization_queries": authorization_total,
        "unauthorized_source_leaks": authorization_violations,
        "authorization_isolation_rate": round(
            (authorization_total - authorization_violations) / authorization_total, 4
        ) if authorization_total else None,
        "hit_at_1": round(hits_at_1 / positive, 4) if positive else 0.0,
        "mean_recall_at_k": round(recall_sum / positive, 4) if positive else 0.0,
        "mean_reciprocal_rank": round(reciprocal_rank_sum / positive, 4) if positive else 0.0,
        "unique_source_precision_micro": round(relevant_total / returned_total, 4) if returned_total else 0.0,
        "precision_at_k_micro": round(relevant_total / returned_total, 4) if returned_total else 0.0,
        "empty_query_accuracy": round(empty_correct / empty_total, 4) if empty_total else None,
        "scenario_pass_rate": round(required_source_coverage / total, 4),
        "required_source_coverage_rate": round(positive_source_coverage / positive, 4) if positive else 0.0,
        "queries": reports,
        "interpretation": (
            "Synthetic retrieval benchmark; provider metrics reflect this run only."
            if isinstance(embedder, VoyageEmbedder)
            else "Synthetic plumbing baseline only; feature hashing is not semantic embedding."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        default="evals/rag_holdout_scenarios.json",
        help="Dataset path relative to this folder (defaults to the holdout set)",
    )
    parser.add_argument("--retriever", choices=("dense", "lexical", "hybrid"), default="dense")
    parser.add_argument(
        "--embedding-provider",
        choices=("hashing", "voyage"),
        default="hashing",
        help="hashing is offline plumbing; voyage uses the configured VOYAGE_API_KEY and makes billable requests",
    )
    parser.add_argument("--embedding-model", default="voyage-4")
    parser.add_argument("--embedding-endpoint", help="Optional Voyage-compatible endpoint override")
    parser.add_argument(
        "--manifest",
        default="knowledge/manifest.json",
        help="Knowledge manifest path relative to this folder (defaults to the small demo corpus)",
    )
    parser.add_argument("--output", help="Optional JSON report path for review or regression storage")
    args = parser.parse_args()
    if args.retriever == "lexical" and args.embedding_provider == "voyage":
        parser.error("lexical retrieval does not use embeddings; select --embedding-provider hashing")
    dataset_path = Path(__file__).parent / args.dataset
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    embedder = (
        VoyageEmbedder(model=args.embedding_model, endpoint=args.embedding_endpoint)
        if args.embedding_provider == "voyage"
        else HashingEmbedder()
    )
    report = evaluate_dataset(
        dataset,
        retriever=args.retriever,
        manifest_path=args.manifest,
        embedder=embedder,
    )
    for query in report["queries"]:
        state = "PASS" if query["pass"] else "GAP"
        print(
            f"{state}  {query['id']}: expected={query['expected_source_ids']} "
            f"retrieved={query['retrieved_source_ids']} versions={query['retrieved_versions']} scores={query['scores']}"
        )
    print(
        f"\n{report['dataset_version']} / {report['split']} ({report['retriever']}; {report['embedder_model_id']}): "
        f"scenario pass={report['scenario_pass_rate']:.0%}; source coverage={report['required_source_coverage_rate']:.0%}; "
        f"Hit@1={report['hit_at_1']:.0%}; "
        f"Recall@{report['top_k_chunks']} sources={report['mean_recall_at_k']:.0%}; "
        f"MRR={report['mean_reciprocal_rank']:.3f}; "
        f"no-answer accuracy={report['empty_query_accuracy']:.0%}; "
        f"unique-source precision={report['unique_source_precision_micro']:.0%}; "
        f"authorization leaks={report['unauthorized_source_leaks']}/{report['authorization_queries']}"
    )
    print(report["interpretation"])
    print(
        f"embedding requests={report['embedding_request_count']} "
        f"input tokens={report['embedding_input_tokens']}"
    )
    print(f"corpus sha256={report['corpus_sha256']} dataset sha256={report['dataset_sha256']}")
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Saved RAG evaluation report to {output_path}")
    return 0 if report["scenario_pass_rate"] == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
