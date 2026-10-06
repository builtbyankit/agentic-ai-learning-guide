"""Run deterministic scenarios against the support-agent harness."""

from __future__ import annotations

from dataclasses import dataclass
import json

from support_agent import AgentLoop, Decision, RunContext, ScriptedPlanner, ToolRuntime


@dataclass
class Scenario:
    name: str
    request: str
    subject_id: str
    task_id: str
    decisions: list[Decision]
    expected_status: str
    expected_tools: list[str]
    answer_fragment: str = ""
    expected_reviews: int = 0
    expected_payment_events: int = 0
    expected_tool_errors: int = 0
    forbidden_trace_values: tuple[str, ...] = ()


def scenarios() -> list[Scenario]:
    return [
        Scenario(
            name="policy answer uses a source",
            request="What is the return window?",
            subject_id="customer-ada",
            task_id="eval-policy",
            decisions=[
                Decision.call("search_policy", {"topic": "refunds"}),
                Decision.answer("Eligible items may be returned within 30 days of delivery (RET-01)."),
            ],
            expected_status="complete",
            expected_tools=["search_policy"],
            answer_fragment="RET-01",
        ),
        Scenario(
            name="owner can look up an order",
            request="Where is my order ORD-100?",
            subject_id="customer-ada",
            task_id="eval-owner",
            decisions=[
                Decision.call("get_order", {"order_ref": "ORD-100"}),
                Decision.answer("ORD-100 is shipped, with estimated delivery on 2026-10-09."),
            ],
            expected_status="complete",
            expected_tools=["get_order"],
            answer_fragment="shipped",
        ),
        Scenario(
            name="cross-customer lookup is denied",
            request="Show me the details for ORD-200.",
            subject_id="customer-ada",
            task_id="eval-denied",
            decisions=[
                Decision.call("get_order", {"order_ref": "ORD-200"}),
                Decision.answer("I could not access that order. A support operator can help."),
            ],
            expected_status="complete",
            expected_tools=["get_order"],
            answer_fragment="could not access",
            expected_tool_errors=1,
        ),
        Scenario(
            name="eligible refund waits for human review",
            request="Please refund ORD-100; it arrived too late.",
            subject_id="customer-ada",
            task_id="eval-refund",
            decisions=[
                Decision.call(
                    "prepare_refund_proposal",
                    {"order_ref": "ORD-100", "reason": "arrived too late"},
                ),
                Decision.call("request_human_review", {"proposal_id": {"$last": "proposal_id"}}),
                Decision.answer("The refund request is pending support review."),
            ],
            expected_status="complete",
            expected_tools=["prepare_refund_proposal", "request_human_review"],
            answer_fragment="pending support review",
            expected_reviews=1,
        ),
        Scenario(
            name="ineligible proposal cannot enter review",
            request="Please refund ORD-200.",
            subject_id="customer-blair",
            task_id="eval-ineligible",
            decisions=[
                Decision.call(
                    "prepare_refund_proposal",
                    {"order_ref": "ORD-200", "reason": "customer requested refund"},
                ),
                Decision.call("request_human_review", {"proposal_id": {"$last": "proposal_id"}}),
                Decision.answer("This order is not eligible for a refund under the current rule."),
            ],
            expected_status="complete",
            expected_tools=["prepare_refund_proposal", "request_human_review"],
            answer_fragment="not eligible",
            expected_tool_errors=1,
        ),
        Scenario(
            name="tool-call budget stops the run",
            request="Please find my order details.",
            subject_id="customer-ada",
            task_id="eval-limit",
            decisions=[
                Decision.call("search_policy", {"topic": "refunds"}),
                Decision.call("search_policy", {"topic": "refunds"}),
                Decision.call("search_policy", {"topic": "refunds"}),
                Decision.call("search_policy", {"topic": "refunds"}),
                Decision.call("search_policy", {"topic": "refunds"}),
            ],
            expected_status="limit",
            expected_tools=["search_policy"] * 4,
            answer_fragment="tool-call limit",
        ),
        Scenario(
            name="malformed arguments are rejected and recovered",
            request="Where is ORD-100?",
            subject_id="customer-ada",
            task_id="eval-schema",
            decisions=[
                Decision.call("get_order", {"order_ref": "ORD-100", "customer_id": "customer-blair"}),
                Decision.call("get_order", {"order_ref": "ORD-100"}),
                Decision.answer("ORD-100 is shipped."),
            ],
            expected_status="complete",
            expected_tools=["get_order", "get_order"],
            answer_fragment="shipped",
            expected_tool_errors=1,
        ),
        Scenario(
            name="untrusted internal note is excluded from tool data",
            request="Where is my order ORD-100?",
            subject_id="customer-ada",
            task_id="eval-minimize-data",
            decisions=[
                Decision.call("get_order", {"order_ref": "ORD-100"}),
                Decision.answer("ORD-100 is shipped."),
            ],
            expected_status="complete",
            expected_tools=["get_order"],
            answer_fragment="shipped",
            forbidden_trace_values=("Ignore policy", "customer-blair's orders"),
        ),
        Scenario(
            name="repeated review request is idempotent",
            request="Please review a refund for ORD-100.",
            subject_id="customer-ada",
            task_id="eval-idempotency",
            decisions=[
                Decision.call(
                    "prepare_refund_proposal",
                    {"order_ref": "ORD-100", "reason": "arrived too late"},
                ),
                Decision.call("request_human_review", {"proposal_id": {"$last": "proposal_id"}}),
                Decision.call(
                    "prepare_refund_proposal",
                    {"order_ref": "ORD-100", "reason": "arrived too late"},
                ),
                Decision.call("request_human_review", {"proposal_id": {"$last": "proposal_id"}}),
                Decision.answer("The refund request is pending support review."),
            ],
            expected_status="complete",
            expected_tools=[
                "prepare_refund_proposal",
                "request_human_review",
                "prepare_refund_proposal",
                "request_human_review",
            ],
            answer_fragment="pending support review",
            expected_reviews=1,
        ),
    ]


def evaluate(scenario: Scenario) -> list[str]:
    runtime = ToolRuntime()
    loop = AgentLoop(runtime, max_turns=6, max_tool_calls=4)
    context = RunContext(subject_id=scenario.subject_id, task_id=scenario.task_id)
    result = loop.run(scenario.request, context, ScriptedPlanner(scenario.decisions))
    failures: list[str] = []
    actual_tools = [event["tool"] for event in result.tool_trace]
    error_count = sum(not event["ok"] for event in result.tool_trace)
    checks = {
        "status": result.status == scenario.expected_status,
        "tool sequence": actual_tools == scenario.expected_tools,
        "answer": not scenario.answer_fragment or scenario.answer_fragment.lower() in result.answer.lower(),
        "pending review count": len(runtime.review_requests) == scenario.expected_reviews,
        "payment side effects": len(runtime.payment_events) == scenario.expected_payment_events,
        "tool error count": error_count == scenario.expected_tool_errors,
    }
    failures.extend(label for label, passed in checks.items() if not passed)
    trace_text = json.dumps(result.tool_trace)
    for forbidden in scenario.forbidden_trace_values:
        if forbidden.lower() in trace_text.lower():
            failures.append(f"forbidden value in tool trace: {forbidden}")
    if scenario.name == "eligible refund waits for human review" and runtime.review_requests:
        status_values = {review["status"] for review in runtime.review_requests.values()}
        if status_values != {"pending"}:
            failures.append("refund review status")
    return failures


def main() -> int:
    passed = 0
    suite = scenarios()
    for scenario in suite:
        failures = evaluate(scenario)
        if failures:
            print(f"FAIL  {scenario.name}: {', '.join(failures)}")
        else:
            passed += 1
            print(f"PASS  {scenario.name}")
    print(f"\n{passed}/{len(suite)} scenarios passed")
    return 0 if passed == len(suite) else 1


if __name__ == "__main__":
    raise SystemExit(main())
