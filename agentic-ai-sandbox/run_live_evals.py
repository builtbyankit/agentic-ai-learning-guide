"""Run the versioned evaluation set against Anthropic; each trial makes API calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evals.common import LiveScenario, grade_result, load_dataset
from policy_retrieval import POLICY_CATALOG_VERSION, PolicyCatalog
from support_agent import ANTHROPIC_TOOLS, AgentLoop, AnthropicPlanner, Planner, RunContext, ToolRuntime


def evaluate(
    scenario: LiveScenario,
    planner: Planner,
    trial_number: int = 1,
) -> tuple[list[str], dict[str, Any]]:
    runtime = ToolRuntime()
    task_id = f"live-eval-{scenario.scenario_id}-trial-{trial_number}"
    result = AgentLoop(runtime, max_turns=6, max_tool_calls=4).run(
        scenario.request,
        RunContext(subject_id=scenario.subject_id, task_id=task_id),
        planner,
    )
    failures, report = grade_result(scenario, result, runtime, task_id)
    report["task_id"] = task_id
    report["trial"] = trial_number
    return failures, report


def summarize_reports(reports: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for report in reports:
        grouped.setdefault(report["scenario_id"], []).append(report)

    scenario_summaries: list[dict[str, Any]] = []
    for scenario_id, trials in grouped.items():
        metric_names = (
            "model_turns",
            "input_tokens",
            "output_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
            "latency_ms",
        )
        metric_averages: dict[str, float] = {}
        metric_trial_counts: dict[str, int] = {}
        for metric in metric_names:
            values = [
                float(trial.get("model_metrics", {}).get(metric, 0))
                for trial in trials
                if trial.get("model_metrics")
            ]
            if values:
                metric_averages[metric] = round(sum(values) / len(values), 2)
                metric_trial_counts[metric] = len(values)
        failure_counts: dict[str, int] = {}
        for trial in trials:
            for failure in trial.get("failures", []):
                failure_counts[failure] = failure_counts.get(failure, 0) + 1
        passed = sum(bool(trial.get("passed")) for trial in trials)
        scenario_summaries.append(
            {
                "scenario_id": scenario_id,
                "scenario": trials[0].get("scenario", scenario_id),
                "trials": len(trials),
                "passed": passed,
                "pass_rate": round(passed / len(trials), 4),
                "failure_counts": failure_counts,
                "mean_model_metrics": metric_averages,
                "metric_trial_counts": metric_trial_counts,
            }
        )

    total = len(reports)
    passed_total = sum(bool(report.get("passed")) for report in reports)
    return {
        "scenario_count": len(grouped),
        "trials_per_scenario": min((len(trials) for trials in grouped.values()), default=0),
        "passed_trials": passed_total,
        "total_trials": total,
        "overall_pass_rate": round(passed_total / total, 4) if total else 0.0,
        "scenario_summaries": scenario_summaries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        help="Optional JSON report path. Reports include answers and traces; store them securely.",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=1,
        help="Run each case this many times (1–10); each trial makes real API requests.",
    )
    parser.add_argument(
        "--prompt-caching",
        action="store_true",
        help="Mark the stable tool/system prefix for Anthropic prompt caching; requests still make real API calls.",
    )
    parser.add_argument(
        "--prompt-cache-ttl",
        choices=("5m", "1h"),
        default="5m",
        help="Cache TTL when --prompt-caching is enabled (check current Anthropic pricing first).",
    )
    args = parser.parse_args()
    if not 1 <= args.trials <= 10:
        parser.error("--trials must be between 1 and 10")
    if args.prompt_cache_ttl != "5m" and not args.prompt_caching:
        parser.error("--prompt-cache-ttl requires --prompt-caching")
    model = os.environ.get("ANTHROPIC_MODEL")
    if not model:
        raise SystemExit("Set ANTHROPIC_MODEL to a model enabled for your Anthropic account.")
    dataset_version, scenarios = load_dataset()
    planner = AnthropicPlanner(
        model=model,
        enable_prompt_caching=args.prompt_caching,
        prompt_cache_ttl=args.prompt_cache_ttl,
    )
    reports: list[dict[str, Any]] = []
    for scenario in scenarios:
        for trial_number in range(1, args.trials + 1):
            try:
                failures, report = evaluate(scenario, planner, trial_number)
            except Exception as exc:  # Report provider/configuration failures without hiding later trials.
                failures = [f"run error: {type(exc).__name__}: {exc}"]
                report = {
                    "scenario_id": scenario.scenario_id,
                    "scenario": scenario.name,
                    "trial": trial_number,
                    "task_id": f"live-eval-{scenario.scenario_id}-trial-{trial_number}",
                    "passed": False,
                    "failures": failures,
                }
            reports.append(report)
            trial_label = f"trial {trial_number}/{args.trials}"
            if failures:
                print(f"FAIL  {trial_label} {scenario.name}: {'; '.join(failures)}")
            else:
                print(f"PASS  {trial_label} {scenario.name}")
    aggregate = summarize_reports(reports)
    for scenario_summary in aggregate["scenario_summaries"]:
        metrics = scenario_summary["mean_model_metrics"]
        print(
            f"CASE  {scenario_summary['scenario']}: "
            f"{scenario_summary['passed']}/{scenario_summary['trials']} "
            f"({scenario_summary['pass_rate']:.0%}); "
            f"mean input/output={metrics.get('input_tokens', 0):.0f}/{metrics.get('output_tokens', 0):.0f}; "
            f"cache read/write={metrics.get('cache_read_input_tokens', 0):.0f}/"
            f"{metrics.get('cache_creation_input_tokens', 0):.0f}; "
            f"model latency={metrics.get('latency_ms', 0):.0f} ms"
        )
    summary = {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "provider": "Anthropic Messages API",
        "configured_model": model,
        "dataset_version": dataset_version,
        "policy_catalog_version": POLICY_CATALOG_VERSION,
        "policy_catalog_sha256": PolicyCatalog.fingerprint(),
        "system_prompt_sha256": hashlib.sha256(
            AnthropicPlanner.SYSTEM_PROMPT.encode("utf-8")
        ).hexdigest(),
        "tool_schema_sha256": hashlib.sha256(
            json.dumps(ANTHROPIC_TOOLS, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "trials_requested_per_scenario": args.trials,
        "prompt_caching_enabled": args.prompt_caching,
        "prompt_cache_ttl": args.prompt_cache_ttl if args.prompt_caching else None,
        **aggregate,
        "scenarios": reports,
    }
    print(
        f"\n{aggregate['passed_trials']}/{aggregate['total_trials']} live trials passed "
        f"({aggregate['overall_pass_rate']:.0%}) across {aggregate['scenario_count']} cases"
    )
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Saved report to {path}")
    return 0 if aggregate["passed_trials"] == aggregate["total_trials"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
