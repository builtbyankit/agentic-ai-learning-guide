"""Evaluate the small policy retriever against a versioned synthetic query set."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from policy_retrieval import POLICY_CATALOG_VERSION, PolicyCatalog


def evaluate_dataset(document: dict[str, Any]) -> dict[str, Any]:
    top_k = int(document.get("top_k", 2))
    if top_k < 1:
        raise ValueError("top_k must be positive")
    scenarios = document["scenarios"]
    if not scenarios:
        raise ValueError("Retrieval evaluation dataset must not be empty")

    catalog = PolicyCatalog()
    reports: list[dict[str, Any]] = []
    positive_queries = 0
    hits_at_1 = 0
    recall_at_k_sum = 0.0
    reciprocal_rank_sum = 0.0
    relevant_retrieved = 0
    returned_on_positive_queries = 0
    empty_queries = 0
    correct_empty = 0
    exact_coverage = 0

    for scenario in scenarios:
        expected = set(scenario["expected_article_ids"])
        results = catalog.search(scenario["query"])[:top_k]
        retrieved = [item["article_id"] for item in results]
        retrieved_set = set(retrieved)
        is_empty_correct = not expected and not retrieved
        if expected:
            positive_queries += 1
            relevant_retrieved += len(expected & retrieved_set)
            returned_on_positive_queries += len(retrieved)
            recall_at_k_sum += len(expected & retrieved_set) / len(expected)
            hits_at_1 += int(bool(retrieved and retrieved[0] in expected))
            reciprocal_rank = next(
                (1.0 / rank for rank, item_id in enumerate(retrieved, start=1) if item_id in expected),
                0.0,
            )
            reciprocal_rank_sum += reciprocal_rank
        else:
            empty_queries += 1
            correct_empty += int(is_empty_correct)
        is_covered = bool(expected <= retrieved_set and (expected or not retrieved))
        exact_coverage += int(is_covered)
        reports.append(
            {
                "id": scenario["id"],
                "expected_article_ids": sorted(expected),
                "retrieved_article_ids": retrieved,
                "pass": is_covered,
                "empty_query_correct": is_empty_correct if not expected else None,
            }
        )

    total = len(scenarios)
    return {
        "dataset_version": document["dataset_version"],
        "policy_catalog_version": POLICY_CATALOG_VERSION,
        "policy_catalog_sha256": PolicyCatalog.fingerprint(),
        "top_k": top_k,
        "total_queries": total,
        "positive_queries": positive_queries,
        "empty_queries": empty_queries,
        "hit_at_1": round(hits_at_1 / positive_queries, 4) if positive_queries else 0.0,
        "mean_recall_at_k": round(recall_at_k_sum / positive_queries, 4) if positive_queries else 0.0,
        "mean_reciprocal_rank": round(reciprocal_rank_sum / positive_queries, 4) if positive_queries else 0.0,
        "precision_at_k_micro": (
            round(relevant_retrieved / returned_on_positive_queries, 4)
            if returned_on_positive_queries
            else 0.0
        ),
        "empty_query_accuracy": round(correct_empty / empty_queries, 4) if empty_queries else None,
        "exact_coverage_rate": round(exact_coverage / total, 4),
        "queries": reports,
    }


def main() -> int:
    dataset_path = Path(__file__).with_name("evals") / "retrieval_scenarios.json"
    document = json.loads(dataset_path.read_text(encoding="utf-8"))
    report = evaluate_dataset(document)
    for query in report["queries"]:
        status = "PASS" if query["pass"] else "GAP"
        print(
            f"{status}  {query['id']}: expected={query['expected_article_ids']} "
            f"retrieved={query['retrieved_article_ids']}"
        )
    print(
        f"\n{report['dataset_version']}: exact coverage={report['exact_coverage_rate']:.0%}; "
        f"Hit@1={report['hit_at_1']:.0%}; Recall@{report['top_k']}={report['mean_recall_at_k']:.0%}; "
        f"MRR={report['mean_reciprocal_rank']:.3f}; "
        f"empty-query accuracy={report['empty_query_accuracy']:.0%}"
    )
    return 0 if report["exact_coverage_rate"] == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
