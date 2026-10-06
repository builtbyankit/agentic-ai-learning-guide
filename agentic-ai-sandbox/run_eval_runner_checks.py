"""Check multi-trial aggregation without creating provider API requests."""

from __future__ import annotations

from evals.common import load_dataset
from run_live_evals import evaluate, summarize_reports
from support_agent import Decision, ScriptedPlanner


def main() -> int:
    _, scenarios = load_dataset()
    own_order = next(scenario for scenario in scenarios if scenario.scenario_id == "own-order")
    successful_decisions = [
        Decision.call("get_order", {"order_ref": "ORD-100"}),
        Decision.answer("ORD-100 is shipped; estimated delivery is October 9."),
    ]
    _, first = evaluate(own_order, ScriptedPlanner(successful_decisions), trial_number=1)
    _, second = evaluate(own_order, ScriptedPlanner(successful_decisions), trial_number=2)
    assert first["passed"] and second["passed"]
    assert first["task_id"] != second["task_id"]
    assert first["trial"] == 1 and second["trial"] == 2
    print("PASS  repeated cases receive isolated task IDs and pass through the normal grader")

    reports = [
        {
            "scenario_id": "sample",
            "scenario": "sample case",
            "passed": True,
            "failures": [],
            "model_metrics": {
                "model_turns": 2, "input_tokens": 100, "output_tokens": 20, "latency_ms": 900,
                "cache_read_input_tokens": 10, "cache_creation_input_tokens": 5,
            },
        },
        {
            "scenario_id": "sample",
            "scenario": "sample case",
            "passed": False,
            "failures": ["sensitive value leaked: 'private'"],
            "model_metrics": {
                "model_turns": 3, "input_tokens": 130, "output_tokens": 28, "latency_ms": 1100,
                "cache_read_input_tokens": 20, "cache_creation_input_tokens": 0,
            },
        },
        {
            "scenario_id": "sample",
            "scenario": "sample case",
            "passed": True,
            "failures": [],
            "model_metrics": {
                "model_turns": 2, "input_tokens": 90, "output_tokens": 18, "latency_ms": 1000,
                "cache_read_input_tokens": 0, "cache_creation_input_tokens": 10,
            },
        },
    ]
    summary = summarize_reports(reports)
    sample = summary["scenario_summaries"][0]
    assert summary["passed_trials"] == 2
    assert summary["total_trials"] == 3
    assert summary["overall_pass_rate"] == 0.6667
    assert sample["failure_counts"] == {"sensitive value leaked: 'private'": 1}
    assert sample["mean_model_metrics"]["input_tokens"] == 106.67
    assert sample["mean_model_metrics"]["cache_read_input_tokens"] == 10.0
    assert sample["mean_model_metrics"]["cache_creation_input_tokens"] == 5.0
    assert sample["metric_trial_counts"]["latency_ms"] == 3
    print("PASS  summary reports pass rate, failure frequency, and metric sample counts")

    empty = summarize_reports([])
    assert empty["total_trials"] == 0 and empty["overall_pass_rate"] == 0.0
    print("PASS  empty report aggregation is well-defined")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
