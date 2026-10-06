"""Compare a fixed workflow with the model agent on the same synthetic cases."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from evals.common import create_scenario_runtime, dataset_sha256, grade_result, load_dataset, resolve_dataset_path, summarize_by_tag
from support_agent import AgentLoop, Decision, RunContext


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
        asks_eligibility = any(marker in lowered for marker in ("check eligibility", "qualify", "eligible"))
        forbids_submission = any(
            marker in lowered for marker in (
                "do not send it to support", "don't send it to support", "do not submit",
                "don't submit", "no request yet", "no review", "not for review",
                "check eligibility only", "only check eligibility",
            )
        )
        self.check_refund_only = self.wants_refund and asks_eligibility and forbids_submission
        if self.check_refund_only and self.order_ref:
            self.mode = "check_refund"
        elif self.wants_refund and self.order_ref:
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
        if self.mode == "check_refund":
            return self._check_refund_action(observations)
        return self._order_and_policy_action(observations)

    def _check_refund_action(self, observations: list[dict[str, object]]) -> Decision:
        if not observations:
            return Decision.call("check_refund_eligibility", {"order_ref": self.order_ref})
        outcome = observations[-1]
        if not outcome["ok"]:
            return Decision.answer("I could not access that order to check refund eligibility.")
        eligibility = outcome["result"]
        if eligibility["eligible"]:
            return Decision.answer(f"{self.order_ref} is eligible for a refund under the current rule. No request was submitted for review.")
        return Decision.answer(f"{self.order_ref} is not eligible for a refund under the current rule. No request was submitted for review.")

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



class ImprovedWorkflowPlanner(FixedWorkflowPlanner):
    """Bounded explicit branches; no scenario IDs or model calls in routing."""

    def __init__(self, request: str):
        super().__init__(request)
        lowered = request.lower()
        self.order_refs = list(dict.fromkeys(ref.upper() for ref in ORDER_PATTERN.findall(request)))
        self.unsupported_payment = any(term in lowered for term in (
            "ledger", "card charges", "payment charges", "settled", "pending charge",
        ))
        self.policy_topics = []
        if any(term in lowered for term in ("damaged", "damage", "broken", "defective", "crushed")):
            self.policy_topics.append("damaged item")
        if any(term in lowered for term in ("guaranteed", "guarantee", "delivery dates", "delivery estimate", "tracking", "shipping delay")):
            self.policy_topics.append("delivery estimates")
        if any(term in lowered for term in ("return window", "return policy", "send it back", "returns policy")):
            self.policy_topics.append("refunds")
        if self.wants_policy and not self.policy_topics:
            self.policy_topics.append(self.policy_topic)
        self.eligibility_only = "refund" in lowered and any(term in lowered for term in (
            "eligible", "eligibility", "qualify", "qualification",
        ))
        # The mutation route accepts an explicit, narrow request grammar.
        # Recognizing a refund-related word is never enough to create a proposal.
        clauses = re.split(r"[.!?;\n]|\band\b", lowered)
        explicit_request = any(re.match(
            r"\s*(?:please\s+refund\s+ord-\d+|refund\s+ord-\d+|"
            r"(?:can|could)\s+i\s+get\s+(?:a\s+)?refund\b|"
            r"i\s+(?:want|would like)\s+(?:a\s+)?refund\b)", clause
        ) for clause in clauses)
        self.no_mutation = bool(re.search(
            r"\b(?:don't|do not|never|not|without|no)\b[^.!?;\n]*"
            r"\b(?:refund|submit|send|review|request|create)\b", lowered
        )) or any(term in lowered for term in ("no request yet", "not for review", "no review"))
        self.refund_route = explicit_request and not self.no_mutation
        self.ambiguous_refund = (
            "refund" in lowered and not self.refund_route and not self.no_mutation
            and not self.eligibility_only
            and not any(term in lowered for term in ("policy", "window", "return rules"))
        )
        self.unsupported_investment = any(term in lowered for term in (
            "stock investment", "investment return", "stock return", "portfolio", "dividend",
        ))
        status_requested = bool(re.search(r"\b(?:where|status|delivery status|on the way|item|items)\b", lowered))
        self.read_plan = []
        for ref in self.order_refs:
            if not self.eligibility_only or status_requested:
                self.read_plan.append(("get_order", {"order_ref": ref}))
            if self.eligibility_only and not self.refund_route:
                self.read_plan.append(("check_refund_eligibility", {"order_ref": ref}))
        self.read_plan.extend(("search_policy", {"topic": topic}) for topic in self.policy_topics)

    def next_action(self, user_request: str, observations: list[dict[str, object]]) -> Decision:
        if self.refund_route:
            if len(self.order_refs) != 1:
                return Decision.handoff("Please choose one order reference for this refund request.")
            # Two mutation calls require room after requested reads. Damage reason
            # alone does not require a separate policy lookup; the proposal validates policy.
            needed_reads = [step for step in self.read_plan if step[0] == "get_order"] if re.search(r"\b(?:where|status|item|items)\b", self.request.lower()) else []
            if any(term in self.request.lower() for term in ("policy", "window", "guarantee")):
                needed_reads += [step for step in self.read_plan if step[0] == "search_policy"]
            if len(needed_reads) + 2 > 4:
                return Decision.handoff("Please narrow the lookups before submitting this refund request.")
            if len(observations) < len(needed_reads):
                tool, arguments = needed_reads[len(observations)]
                return Decision.call(tool, arguments)
            decision = self._refund_action(observations[len(needed_reads):])
            if decision.kind == "final":
                prefix = self._read_summary(needed_reads, observations[:len(needed_reads)])
                return Decision.answer(" ".join(part for part in (prefix, decision.text, self._limitations()) if part))
            return decision
        if self.ambiguous_refund:
            return Decision.handoff("Do you want an eligibility check or to submit a refund request? No request was submitted for review.")
        if len(self.read_plan) > 4:
            return Decision.handoff("Please narrow this request to at most four lookups; support can help.")
        if not self.read_plan and not self.unsupported_payment and not self.unsupported_investment:
            return Decision.handoff("Please share your order reference or a supported policy question.")
        if len(observations) < len(self.read_plan):
            tool, arguments = self.read_plan[len(observations)]
            return Decision.call(tool, arguments)
        parts = [self._read_summary(self.read_plan, observations)]
        parts.append(self._limitations())
        if self.no_mutation and not self.eligibility_only:
            parts.append("No request was submitted for review.")
        return Decision.answer(" ".join(part for part in parts if part))

    def _limitations(self):
        parts = []
        if self.unsupported_payment:
            parts.append("I do not have access to payment ledger; I cannot verify whether card charges are settled or pending.")
        if self.unsupported_investment:
            parts.append("I cannot verify investment returns; this assistant only supports store orders and policies.")
        return " ".join(parts)

    @staticmethod
    def _read_summary(plan, observations):
        parts = []
        for (tool, arguments), observation in zip(plan, observations):
            if not observation["ok"]:
                target = arguments.get("order_ref", "that policy")
                parts.append(f"I could not access {target}. Support can help.")
                continue
            result = observation["result"]
            if tool == "get_order":
                parts.append(f"{result['order_ref']} is {result['status']}, with estimated delivery on {result['estimated_delivery']}. Items: {result['items']}.")
            elif tool == "check_refund_eligibility":
                eligible = "eligible" if result["eligible"] else "not eligible"
                parts.append(f"{arguments['order_ref']} is {eligible} for a refund. No request was submitted for review.")
            else:
                matches = result.get("matches", [])
                if matches:
                    parts.extend(f"{article['text']} ({article['article_id']})." for article in matches)
                else:
                    parts.append("I could not find an approved policy for that question.")
        return " ".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="evals/live_scenarios.json", help="Versioned scenario JSON path")
    parser.add_argument("--output", help="Optional JSON report path")
    parser.add_argument("--baseline", choices=("original", "improved"), default="improved", help="Improved bounded router by default; original preserves historical comparisons")
    args = parser.parse_args()
    dataset_version, scenarios = load_dataset(args.dataset)
    dataset_path = resolve_dataset_path(args.dataset)
    passed = 0
    tool_calls = 0
    reports: list[dict[str, Any]] = []
    for scenario in scenarios:
        runtime = create_scenario_runtime(scenario)
        result = AgentLoop(runtime, max_turns=6, max_tool_calls=4).run(
            scenario.request,
            RunContext(subject_id=scenario.subject_id, task_id=f"workflow-{scenario.scenario_id}"),
            (ImprovedWorkflowPlanner if args.baseline == "improved" else FixedWorkflowPlanner)(scenario.request),
        )
        failures, report = grade_result(scenario, result, runtime, f"workflow-{scenario.scenario_id}")
        report["task_id"] = f"workflow-{scenario.scenario_id}"
        report["trial"] = 1
        reports.append(report)
        tool_calls += len(result.tool_trace)
        if failures:
            print(f"GAP   {scenario.name}: {'; '.join(failures)}")
        else:
            passed += 1
            print(f"PASS  {scenario.name}")
        print(f"      tools={len(result.tool_trace)} workflow_steps={result.turns}; answer={result.answer}")
    print(
        f"\nFixed workflow ({args.baseline}) on {dataset_version}: {passed}/{len(scenarios)} cases passed; "
        f"{tool_calls} total tool calls; 0 model calls."
    )
    print(f"Dataset SHA-256: {dataset_sha256(args.dataset)}")
    for summary in summarize_by_tag(reports):
        print(f"TAG   {summary['tag']}: {summary['passed']}/{summary['total']} ({summary['pass_rate']:.0%})")
    print("GAP means the workflow did not satisfy this case’s shared grader; it is not a code execution error.")
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps({
            "architecture": f"fixed-workflow-{args.baseline}",
            "dataset_version": dataset_version,
            "dataset_path": str(dataset_path),
            "dataset_sha256": dataset_sha256(args.dataset),
            "passed_cases": passed,
            "total_cases": len(scenarios),
            "tool_calls": tool_calls,
            "model_calls": 0,
            "tag_summaries": summarize_by_tag(reports),
            "scenarios": reports,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Saved report to {output_path}")
    return 0 if passed == len(scenarios) else 1


if __name__ == "__main__":
    raise SystemExit(main())
