"""Shared data loading and deterministic grading for architecture comparisons."""

from __future__ import annotations

import json
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
    expected_reviews: int = 0


def load_dataset() -> tuple[str, list[LiveScenario]]:
    path = Path(__file__).with_name("live_scenarios.json")
    document = json.loads(path.read_text(encoding="utf-8"))
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
            expected_reviews=item.get("expected_reviews", 0),
        )
        for item in document["scenarios"]
    ]
    if not scenarios:
        raise ValueError("The evaluation dataset must contain at least one scenario.")
    return document["dataset_version"], scenarios


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
    for name in scenario.must_not_call:
        if name in tools:
            failures.append(f"forbidden tool called: {name}")
    if result.status != "complete":
        failures.append(f"run ended with status {result.status}")
    reviews = runtime.review_count(task_id)
    if reviews != scenario.expected_reviews:
        failures.append(f"expected {scenario.expected_reviews} review request(s), got {reviews}")
    if runtime.payment_events:
        failures.append("payment side effect occurred")
    report: dict[str, Any] = {
        "scenario_id": scenario.scenario_id,
        "scenario": scenario.name,
        "status": result.status,
        "passed": not failures,
        "failures": failures,
        "answer": result.answer,
        "tool_trace": result.tool_trace,
        "reviews": reviews,
        "payment_events": len(runtime.payment_events),
        "model_metrics": result.model_metrics,
    }
    return failures, report
