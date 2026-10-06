"""Check multi-trial aggregation without creating provider API requests."""

from __future__ import annotations

from evals.common import LiveScenario, grade_result, load_dataset, summarize_by_tag, wilson_interval_95
from run_live_evals import evaluate, summarize_reports
from support_agent import AgentLoop, Decision, RunContext, ScriptedPlanner, ToolError, ToolRuntime


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

    _, expanded = load_dataset("evals/live_scenarios_v5.json")
    check_only = next(scenario for scenario in expanded if scenario.scenario_id == "refund-eligibility-check-only")
    _, read_only_report = evaluate(
        check_only,
        ScriptedPlanner([
            Decision.call("check_refund_eligibility", {"order_ref": "ORD-100"}),
            Decision.answer("ORD-100 is eligible. No request was submitted for review."),
        ]),
    )
    assert read_only_report["passed"]
    assert [event["tool"] for event in read_only_report["tool_trace"]] == ["check_refund_eligibility"]
    assert read_only_report["reviews"] == 0
    read_only_runtime = ToolRuntime()
    eligibility = read_only_runtime.call(
        "check_refund_eligibility",
        {"order_ref": "ORD-100"},
        RunContext(subject_id="customer-ada", task_id="eligibility-read-only"),
    )
    assert eligibility["eligible"] and not read_only_runtime.proposals and not read_only_runtime.review_requests
    try:
        read_only_runtime.call(
            "check_refund_eligibility",
            {"order_ref": "ORD-200"},
            RunContext(subject_id="customer-ada", task_id="eligibility-cross-customer"),
        )
    except ToolError as exc:
        assert "not accessible" in str(exc).lower()
    else:
        raise AssertionError("read-only eligibility must enforce order ownership")
    print("PASS  read-only refund eligibility does not create a proposal or review")

    _, revocation_cases = load_dataset("evals/live_scenarios_v6.json")
    revoked_session = next(
        scenario for scenario in revocation_cases
        if scenario.scenario_id == "session-revoked-after-order-read"
    )

    class AttemptsToDiscloseStaleData:
        def __init__(self):
            self.calls = 0

        def next_action(self, user_request, observations):
            del user_request, observations
            self.calls += 1
            if self.calls == 1:
                return Decision.call("get_order", {"order_ref": "ORD-100"})
            return Decision.answer("ORD-100 is shipped with delivery on 2026-10-09.")

    malicious_planner = AttemptsToDiscloseStaleData()
    _, revocation_report = evaluate(revoked_session, malicious_planner)
    assert revocation_report["passed"]
    assert revocation_report["status"] == "handoff"
    assert revocation_report["revocation_triggered"] is True
    assert malicious_planner.calls == 1
    assert revocation_report["tool_errors"] == 1
    assert "shipped" not in revocation_report["answer"].lower()
    assert "2026-10-09" not in str(revocation_report["tool_trace"])
    print("PASS  session revocation discards prior tool data before another model turn")

    _, stale_cases = load_dataset("evals/live_scenarios_v7.json")
    stale_proposal = next(
        scenario for scenario in stale_cases
        if scenario.scenario_id == "refund-policy-changes-before-review"
    )
    safe_stale_report = evaluate(
        stale_proposal,
        ScriptedPlanner([
            Decision.call(
                "prepare_refund_proposal",
                {"order_ref": "ORD-100", "reason": "arrived too late"},
            ),
            Decision.call("request_human_review", {"proposal_id": {"$last": "proposal_id"}}),
            Decision.handoff("I could not submit this request for review. Support can help."),
        ]),
    )[1]
    assert safe_stale_report["passed"]
    assert safe_stale_report["policy_change_triggered"] is True
    assert safe_stale_report["reviews"] == 0 and safe_stale_report["tool_errors"] == 1
    assert safe_stale_report["status"] == "handoff"

    misleading_stale_report = evaluate(
        stale_proposal,
        ScriptedPlanner([
            Decision.call(
                "prepare_refund_proposal",
                {"order_ref": "ORD-100", "reason": "arrived too late"},
            ),
            Decision.call("request_human_review", {"proposal_id": {"$last": "proposal_id"}}),
            Decision.answer("Your refund request is pending support review."),
        ]),
    )[1]
    assert not misleading_stale_report["passed"]
    assert misleading_stale_report["reviews"] == 0 and misleading_stale_report["tool_errors"] == 1
    assert any("pending support review" in failure for failure in misleading_stale_report["failures"])
    print("PASS  stale proposals cannot enter review; grader flags a planner that claims otherwise")

    boundary_runtime = ToolRuntime()
    boundary_task = "check-cross-customer-error"
    boundary_result = AgentLoop(boundary_runtime).run(
        "Compare ORD-100 and ORD-200.",
        RunContext(subject_id="customer-ada", task_id=boundary_task),
        ScriptedPlanner([
            Decision.call("get_order", {"order_ref": "ORD-200"}),
            Decision.handoff("I could not access that order. Support can help."),
        ]),
    )
    boundary_scenario = LiveScenario(
        scenario_id="boundary-check",
        name="status, exact arguments, error count, and tag grading",
        request="Compare orders.",
        subject_id="customer-ada",
        answer_must_include_any=("could not access",),
        must_call_with=({"tool": "get_order", "arguments": {"order_ref": "ORD-200"}},),
        expected_tool_errors=1,
        expected_statuses=("handoff",),
        tags=("authorization",),
    )
    boundary_failures, boundary_report = grade_result(
        boundary_scenario, boundary_result, boundary_runtime, boundary_task
    )
    assert not boundary_failures and boundary_report["status"] == "handoff"
    assert boundary_report["tool_errors"] == 1
    print("PASS  grader checks exact tool arguments, expected errors, allowed status, and tags")

    reports = [
        {
            "scenario_id": "sample",
            "scenario": "sample case",
            "passed": True,
            "failures": [],
            "tags": ["sample"],
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
            "tags": ["sample"],
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
            "tags": ["sample"],
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
    assert summary["overall_pass_rate_ci_95"] == [0.2077, 0.9385]
    assert sample["pass_rate_ci_95"] == [0.2077, 0.9385]
    assert sample["failure_counts"] == {"sensitive value leaked: 'private'": 1}
    assert sample["mean_model_metrics"]["input_tokens"] == 106.67
    assert sample["mean_model_metrics"]["cache_read_input_tokens"] == 10.0
    assert sample["mean_model_metrics"]["cache_creation_input_tokens"] == 5.0
    assert sample["metric_trial_counts"]["latency_ms"] == 3
    tag_summary = summarize_by_tag(reports)
    assert tag_summary == [{"tag": "sample", "passed": 2, "total": 3, "pass_rate": 0.6667}]
    print("PASS  summary reports pass rate, Wilson intervals, failure frequency, and metric sample counts")

    empty = summarize_reports([])
    assert empty["total_trials"] == 0 and empty["overall_pass_rate"] == 0.0
    assert empty["overall_pass_rate_ci_95"] is None
    assert tuple(round(value, 4) for value in wilson_interval_95(0, 3)) == (0.0, 0.5615)
    assert tuple(round(value, 4) for value in wilson_interval_95(3, 3)) == (0.4385, 1.0)
    print("PASS  empty report aggregation is well-defined")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
