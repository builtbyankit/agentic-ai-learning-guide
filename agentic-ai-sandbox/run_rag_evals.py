"""Evaluate the local RAG baseline against a small, versioned synthetic set."""

from __future__ import annotations

import hashlib
import json
import argparse
import tempfile
from pathlib import Path
from typing import Any

from rag_pipeline import HashingEmbedder, SQLiteVectorStore, load_manifest_documents, normalize_text


CHUNK_MAX_WORDS = 90
CHUNK_OVERLAP_WORDS = 18


def evaluate_dataset(dataset: dict[str, Any], *, retriever: str = "dense") -> dict[str, Any]:
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

    documents = load_manifest_documents(Path(__file__).with_name("knowledge") / "manifest.json")
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
    embedder = HashingEmbedder()
    with tempfile.TemporaryDirectory() as temporary:
        store = SQLiteVectorStore(Path(temporary) / "rag-eval.sqlite", embedder)
        for document in documents:
            store.ingest(document, max_words=CHUNK_MAX_WORDS, overlap_words=CHUNK_OVERLAP_WORDS)

        reports: list[dict[str, Any]] = []
        positive = 0
        hits_at_1 = 0
        recall_sum = 0.0
        reciprocal_rank_sum = 0.0
        relevant_total = 0
        returned_total = 0
        empty_total = 0
        empty_correct = 0
        required_source_coverage = 0

        for scenario in scenarios:
            expected = set(scenario["expected_source_ids"])
            search_options = {
                "tenant_id": scenario.get("tenant_id", "demo-tenant"),
                "query": scenario["query"],
                "allowed_classifications": scenario.get(
                    "allowed_classifications", dataset.get("allowed_classifications", ["internal"])
                ),
                "top_k": int(scenario.get("top_k", top_k)),
            }
            if retriever == "dense":
                hits = store.search(**search_options, min_score=float(scenario.get("min_score", min_score)))
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
                    lexical_relative_score_floor=float(
                        scenario.get("lexical_relative_score_floor", lexical_relative_score_floor)
                    ),
                )
            retrieved: list[str] = []
            for hit in hits:
                if hit.source_id not in retrieved:
                    retrieved.append(hit.source_id)
            retrieved_set = set(retrieved)
            is_covered = expected <= retrieved_set if expected else not retrieved
            required_source_coverage += int(is_covered)

            if expected:
                positive += 1
                relevant_total += len(expected & retrieved_set)
                returned_total += len(retrieved)
                recall_sum += len(expected & retrieved_set) / len(expected)
                hits_at_1 += int(bool(retrieved and retrieved[0] in expected))
                reciprocal_rank_sum += next(
                    (1.0 / rank for rank, source_id in enumerate(retrieved, start=1) if source_id in expected),
                    0.0,
                )
            else:
                empty_total += 1
                empty_correct += int(not retrieved)

            reports.append(
                {
                    "id": scenario["id"],
                    "expected_source_ids": sorted(expected),
                    "retrieved_source_ids": retrieved,
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
        "retriever": retriever,
        "embedder_model_id": embedder.model_id,
        "corpus_sha256": corpus_fingerprint,
        "dataset_sha256": dataset_fingerprint,
        "chunking": {"max_words": CHUNK_MAX_WORDS, "overlap_words": CHUNK_OVERLAP_WORDS},
        "top_k_chunks": top_k,
        "min_score": min_score,
        "lexical_relative_score_floor": lexical_relative_score_floor,
        "total_queries": total,
        "positive_queries": positive,
        "empty_queries": empty_total,
        "hit_at_1": round(hits_at_1 / positive, 4) if positive else 0.0,
        "mean_recall_at_k": round(recall_sum / positive, 4) if positive else 0.0,
        "mean_reciprocal_rank": round(reciprocal_rank_sum / positive, 4) if positive else 0.0,
        "precision_at_k_micro": round(relevant_total / returned_total, 4) if returned_total else 0.0,
        "empty_query_accuracy": round(empty_correct / empty_total, 4) if empty_total else None,
        "required_source_coverage_rate": round(required_source_coverage / total, 4),
        "queries": reports,
        "interpretation": "Synthetic plumbing baseline only; feature hashing is not semantic embedding.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        default="evals/rag_holdout_scenarios.json",
        help="Dataset path relative to this folder (defaults to the holdout set)",
    )
    parser.add_argument("--retriever", choices=("dense", "lexical", "hybrid"), default="dense")
    parser.add_argument("--output", help="Optional JSON report path for review or regression storage")
    args = parser.parse_args()
    dataset_path = Path(__file__).parent / args.dataset
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    report = evaluate_dataset(dataset, retriever=args.retriever)
    for query in report["queries"]:
        state = "PASS" if query["pass"] else "GAP"
        print(
            f"{state}  {query['id']}: expected={query['expected_source_ids']} "
            f"retrieved={query['retrieved_source_ids']} scores={query['scores']}"
        )
    print(
        f"\n{report['dataset_version']} / {report['split']} ({report['retriever']}; {report['embedder_model_id']}): "
        f"required-source coverage={report['required_source_coverage_rate']:.0%}; Hit@1={report['hit_at_1']:.0%}; "
        f"Recall@{report['top_k_chunks']} sources={report['mean_recall_at_k']:.0%}; "
        f"MRR={report['mean_reciprocal_rank']:.3f}; "
        f"empty-query accuracy={report['empty_query_accuracy']:.0%}; "
        f"precision={report['precision_at_k_micro']:.0%}"
    )
    print(report["interpretation"])
    print(f"corpus sha256={report['corpus_sha256']} dataset sha256={report['dataset_sha256']}")
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Saved RAG evaluation report to {output_path}")
    return 0 if report["required_source_coverage_rate"] == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
