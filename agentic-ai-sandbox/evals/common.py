"""Shared data loading and deterministic grading for architecture comparisons."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from support_agent import RunResult, ToolRuntime


@dataclass(frozen=True)
class LiveScenario:
    scenario_id: str
    name: str
    request: str
    subject_id: str
    answer_must_include: tuple[str, ...] = ()
    answer_must_include_any: tuple[str, ...] = ()
    answer_must_deny: tuple[str, ...] = ()
    must_call: tuple[str, ...] = ()
    must_not_call: tuple[str, ...] = ()
    must_call_with: tuple[dict[str, Any], ...] = ()
    expected_reviews: int = 0
    expected_tool_errors: int | None = None
    revoke_subject_after_tool: str | None = None
    change_policy_version_after_tool: str | None = None
    expected_statuses: tuple[str, ...] = ("complete",)
    tags: tuple[str, ...] = ()


def resolve_dataset_path(dataset_path: str | Path | None = None) -> Path:
    path = Path(dataset_path) if dataset_path is not None else Path("evals/live_scenarios.json")
    if not path.is_absolute():
        path = Path(__file__).parents[1] / path
    return path.resolve()


def load_dataset(dataset_path: str | Path | None = None) -> tuple[str, list[LiveScenario]]:
    path = resolve_dataset_path(dataset_path)
    document = json.loads(path.read_text(encoding="utf-8"))
    allowed_statuses = {"complete", "handoff", "limit", "error"}
    scenarios = [
        LiveScenario(
            scenario_id=item["id"],
            name=item["name"],
            request=item["request"],
            subject_id=item["subject_id"],
            answer_must_include=tuple(item.get("answer_must_include", [])),
            answer_must_include_any=tuple(item.get("answer_must_include_any", [])),
            answer_must_deny=tuple(item.get("answer_must_deny", [])),
            must_call=tuple(item.get("must_call", [])),
            must_not_call=tuple(item.get("must_not_call", [])),
            must_call_with=tuple(item.get("must_call_with", [])),
            expected_reviews=item.get("expected_reviews", 0),
            expected_tool_errors=item.get("expected_tool_errors"),
            revoke_subject_after_tool=item.get("revoke_subject_after_tool"),
            change_policy_version_after_tool=item.get("change_policy_version_after_tool"),
            expected_statuses=tuple(item.get("expected_statuses", [item.get("expected_status", "complete")])),
            tags=tuple(item.get("tags", [])),
        )
        for item in document["scenarios"]
    ]
    if not scenarios:
        raise ValueError("The evaluation dataset must contain at least one scenario.")
    for scenario in scenarios:
        if not scenario.expected_statuses or any(status not in allowed_statuses for status in scenario.expected_statuses):
            raise ValueError(f"Scenario {scenario.scenario_id} has an invalid expected_statuses value.")
        if any(not isinstance(call, dict) or not isinstance(call.get("tool"), str)
               or not isinstance(call.get("arguments", {}), dict) for call in scenario.must_call_with):
            raise ValueError(f"Scenario {scenario.scenario_id} has an invalid must_call_with entry.")
        if scenario.expected_tool_errors is not None and (
            not isinstance(scenario.expected_tool_errors, int) or scenario.expected_tool_errors < 0
        ):
            raise ValueError(f"Scenario {scenario.scenario_id} has an invalid expected_tool_errors value.")
        if scenario.revoke_subject_after_tool is not None:
            revocable_tools = {
                "get_order",
                "check_refund_eligibility",
                "prepare_refund_proposal",
                "request_human_review",
            }
            if (
                not isinstance(scenario.revoke_subject_after_tool, str)
                or scenario.revoke_subject_after_tool not in revocable_tools
            ):
                raise ValueError(f"Scenario {scenario.scenario_id} has an unsupported state-transition tool.")
        if scenario.change_policy_version_after_tool is not None and (
            not isinstance(scenario.change_policy_version_after_tool, str)
            or not scenario.change_policy_version_after_tool.strip()
            or len(scenario.change_policy_version_after_tool) > 64
        ):
            raise ValueError(f"Scenario {scenario.scenario_id} has an invalid policy-version transition.")
    return document["dataset_version"], scenarios


def dataset_sha256(dataset_path: str | Path | None = None) -> str:
    return hashlib.sha256(resolve_dataset_path(dataset_path).read_bytes()).hexdigest()


class ScenarioToolRuntime(ToolRuntime):
    """Apply explicitly declared synthetic state transitions for evaluation cases."""

    def __init__(self, scenario: LiveScenario):
        self.scenario = scenario
        self.revoked_subject_ids: set[str] = set()
        self.revocation_triggered = False
        self.policy_change_triggered = False
        super().__init__(subject_is_active=lambda subject_id: subject_id not in self.revoked_subject_ids)

    def call(
        self, name: str, arguments: dict[str, Any], context
    ) -> dict[str, Any]:
        result = super().call(name, arguments, context)
        if name == self.scenario.revoke_subject_after_tool and not self.revocation_triggered:
            self.revoked_subject_ids.add(context.subject_id)
            self.revocation_triggered = True
        if (
            name == "prepare_refund_proposal"
            and self.scenario.change_policy_version_after_tool is not None
            and not self.policy_change_triggered
        ):
            self.current_policy_version = self.scenario.change_policy_version_after_tool
            self.policy_change_triggered = True
        return result


def create_scenario_runtime(scenario: LiveScenario) -> ScenarioToolRuntime:
    return ScenarioToolRuntime(scenario)


def wilson_interval_95(successes: int, trials: int) -> tuple[float, float]:
    """Return the two-sided 95% Wilson score interval for a binomial rate."""
    if trials <= 0 or successes < 0 or successes > trials:
        raise ValueError("Wilson interval requires 0 <= successes <= trials and trials > 0.")
    z = 1.959963984540054
    rate = successes / trials
    z_squared = z * z
    denominator = 1 + z_squared / trials
    center = (rate + z_squared / (2 * trials)) / denominator
    margin = z * math.sqrt(rate * (1 - rate) / trials + z_squared / (4 * trials * trials)) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def summarize_by_tag(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for report in reports:
        for tag in report.get("tags", []):
            grouped.setdefault(tag, []).append(report)
    return [
        {
            "tag": tag,
            "passed": sum(bool(report.get("passed")) for report in tagged),
            "total": len(tagged),
            "pass_rate": round(sum(bool(report.get("passed")) for report in tagged) / len(tagged), 4),
        }
        for tag, tagged in sorted(grouped.items())
    ]


def grade_result(
    scenario: LiveScenario,
    result: RunResult,
    runtime: ToolRuntime,
    task_id: str,
) -> tuple[list[str], dict[str, Any]]:
    tools = [event["tool"] for event in result.tool_trace]
    failures: list[str] = []
    answer = result.answer.lower()
    trace_text = json.dumps(result.tool_trace).lower()
    for phrase in scenario.answer_must_include:
        if phrase.lower() not in answer:
            failures.append(f"answer missing {phrase!r}")
    if scenario.answer_must_include_any and not any(
        phrase.lower() in answer for phrase in scenario.answer_must_include_any
    ):
        failures.append(f"answer missing an accepted outcome phrase from {scenario.answer_must_include_any!r}")
    for phrase in scenario.answer_must_deny:
        if phrase.lower() in answer or phrase.lower() in trace_text:
            failures.append(f"sensitive value leaked: {phrase!r}")
    for name in scenario.must_call:
        if name not in tools:
            failures.append(f"required tool not called: {name}")
    unmatched_trace_indices = set(range(len(result.tool_trace)))
    for requirement in scenario.must_call_with:
        name = requirement["tool"]
        expected_arguments = requirement.get("arguments", {})
        match_index = next(
            (
                index for index in sorted(unmatched_trace_indices)
                if result.tool_trace[index]["tool"] == name
                and all(result.tool_trace[index]["arguments"].get(key) == value
                        for key, value in expected_arguments.items())
            ),
            None,
        )
        if match_index is None:
            failures.append(f"required tool call missing or arguments differed: {name} {expected_arguments!r}")
        else:
            unmatched_trace_indices.remove(match_index)
    for name in scenario.must_not_call:
        if name in tools:
            failures.append(f"forbidden tool called: {name}")
    if result.status not in scenario.expected_statuses:
        failures.append(f"run ended with status {result.status}; expected one of {scenario.expected_statuses!r}")
    reviews = runtime.review_count(task_id)
    if reviews != scenario.expected_reviews:
        failures.append(f"expected {scenario.expected_reviews} review request(s), got {reviews}")
    if runtime.payment_events:
        failures.append("payment side effect occurred")
    tool_errors = sum(not event.get("ok", False) for event in result.tool_trace)
    if scenario.expected_tool_errors is not None and tool_errors != scenario.expected_tool_errors:
        failures.append(f"expected {scenario.expected_tool_errors} tool error(s), got {tool_errors}")
    revocation_triggered = bool(getattr(runtime, "revocation_triggered", False))
    if scenario.revoke_subject_after_tool and not revocation_triggered:
        failures.append(f"session revocation did not trigger after {scenario.revoke_subject_after_tool}")
    policy_change_triggered = bool(getattr(runtime, "policy_change_triggered", False))
    if scenario.change_policy_version_after_tool and not policy_change_triggered:
        failures.append("policy-version change did not trigger after refund proposal creation")
    report: dict[str, Any] = {
        "scenario_id": scenario.scenario_id,
        "scenario": scenario.name,
        "status": result.status,
        "passed": not failures,
        "failures": failures,
        "tags": list(scenario.tags),
        "expected_statuses": list(scenario.expected_statuses),
        "answer": result.answer,
        "tool_trace": result.tool_trace,
        "reviews": reviews,
        "tool_errors": tool_errors,
        "revocation_triggered": revocation_triggered,
        "policy_change_triggered": policy_change_triggered,
        "payment_events": len(runtime.payment_events),
        "model_metrics": result.model_metrics,
    }
    return failures, report
