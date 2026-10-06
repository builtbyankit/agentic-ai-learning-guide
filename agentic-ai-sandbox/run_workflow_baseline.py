"""Compare a fixed workflow with the model agent on the same synthetic cases."""

from __future__ import annotations

import re

from evals.common import grade_result, load_dataset
from support_agent import AgentLoop, Decision, RunContext, ToolRuntime


ORDER_PATTERN = re.compile(r"\bORD-\d+\b", re.IGNORECASE)


class FixedWorkflowPlanner:
    """Small deterministic router for the known support intents in the dataset."""

    def __init__(self, request: str):
        self.request = request
        lowered = request.lower()
        match = ORDER_PATTERN.search(request)
        self.order_ref = match.group(0).upper() if match else ""
        policy_terms = (
            "policy",
            "return window",
            "reporting window",
            "delivery estimate",
            "tracking status",
            "shipping delay",
            "damaged",
            "broken on arrival",
            "defective",
        )
        self.wants_policy = any(term in lowered for term in policy_terms)
        if any(term in lowered for term in ("damaged", "damage", "broken", "defective")):
            self.policy_topic = "broken on arrival" if "broken" in lowered else "damaged item"
        elif any(term in lowered for term in ("delivery", "tracking", "shipping")):
            self.policy_topic = "delivery estimates"
        else:
            self.policy_topic = "refunds"
        self.wants_refund = "refund" in lowered and not self.wants_policy
        if self.wants_refund and self.order_ref:
            self.mode = "refund"
        elif self.order_ref and self.wants_policy:
            self.mode = "order_and_policy"
        elif self.order_ref:
            self.mode = "order"
        elif self.wants_policy:
            self.mode = "policy"
        else:
            self.mode = "handoff"
        reason_match = re.search(r"\b(?:because|since)\s+(.+?)[.!?]*$", request, re.IGNORECASE)
        self.reason = reason_match.group(1).strip() if reason_match else "customer request"

    def next_action(self, user_request: str, observations: list[dict[str, object]]) -> Decision:
        del user_request
        if self.mode == "handoff":
            return Decision.handoff("Please share your order reference so support can help.")
        if self.mode == "policy":
            return self._policy_action(observations)
        if self.mode == "order":
            return self._order_action(observations)
        if self.mode == "refund":
            return self._refund_action(observations)
        return self._order_and_policy_action(observations)

    def _policy_action(self, observations: list[dict[str, object]]) -> Decision:
        if not observations:
            return Decision.call("search_policy", {"topic": self.policy_topic})
        result = observations[-1]["result"]
        matches = result.get("matches", []) if isinstance(result, dict) else []
        if not matches:
            return Decision.answer("I could not find an approved return policy for that question.")
        article = matches[0]
        return Decision.answer(f"{article['text']} ({article['article_id']}).")

    def _order_action(self, observations: list[dict[str, object]]) -> Decision:
        if not observations:
            return Decision.call("get_order", {"order_ref": self.order_ref})
        last = observations[-1]
        if not last["ok"]:
            return Decision.answer("I could not access that order. A support operator can help.")
        order = last["result"]
        return Decision.answer(
            f"{order['order_ref']} is {order['status']}, with estimated delivery on {order['estimated_delivery']}."
        )

    def _refund_action(self, observations: list[dict[str, object]]) -> Decision:
        if not observations:
            return Decision.call(
                "prepare_refund_proposal",
                {"order_ref": self.order_ref, "reason": self.reason},
            )
        proposal_result = observations[0]
        if not proposal_result["ok"]:
            return Decision.answer("I could not access that order. A support operator can help.")
        proposal = proposal_result["result"]
        if not proposal["eligible"]:
            return Decision.answer(f"{self.order_ref} is not eligible for a refund under the current rule.")
        if len(observations) == 1:
            return Decision.call("request_human_review", {"proposal_id": proposal["proposal_id"]})
        review = observations[-1]
        if review["ok"]:
            return Decision.answer("Your refund request is pending support review; no refund has been issued.")
        return Decision.handoff("I could not submit this request for review. Support can help.")

    def _order_and_policy_action(self, observations: list[dict[str, object]]) -> Decision:
        if not observations:
            return Decision.call("get_order", {"order_ref": self.order_ref})
        if not observations[0]["ok"]:
            return Decision.answer("I could not access that order. A support operator can help.")
        if len(observations) == 1:
            return Decision.call("search_policy", {"topic": self.policy_topic})
        order = observations[0]["result"]
        matches = observations[1]["result"].get("matches", [])
        if not matches:
            return Decision.answer(f"{order['order_ref']} is {order['status']}; I could not find the return policy.")
        article = matches[0]
        return Decision.answer(
            f"{order['order_ref']} is {order['status']}. {article['text']} ({article['article_id']})."
        )


def main() -> int:
    dataset_version, scenarios = load_dataset()
    passed = 0
    tool_calls = 0
    for scenario in scenarios:
        runtime = ToolRuntime()
        result = AgentLoop(runtime, max_turns=6, max_tool_calls=4).run(
            scenario.request,
            RunContext(subject_id=scenario.subject_id, task_id=f"workflow-{scenario.scenario_id}"),
            FixedWorkflowPlanner(scenario.request),
        )
        failures, report = grade_result(scenario, result, runtime, f"workflow-{scenario.scenario_id}")
        tool_calls += len(result.tool_trace)
        if failures:
            print(f"GAP   {scenario.name}: {'; '.join(failures)}")
        else:
            passed += 1
            print(f"PASS  {scenario.name}")
        print(f"      tools={len(result.tool_trace)} workflow_steps={result.turns}; answer={result.answer}")
    print(
        f"\nFixed workflow on {dataset_version}: {passed}/{len(scenarios)} cases passed; "
        f"{tool_calls} total tool calls; 0 model calls."
    )
    print("GAP means the workflow did not satisfy this case’s shared grader; it is not a code execution error.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
