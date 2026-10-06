"""Run the versioned evaluation set against Anthropic; each trial makes API calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evals.common import (
    LiveScenario,
    create_scenario_runtime,
    dataset_sha256,
    grade_result,
    load_dataset,
    resolve_dataset_path,
    summarize_by_tag,
    wilson_interval_95,
)
from evals.cost_model import estimate_model_cost, load_rate_card, summarize_model_costs
from policy_retrieval import POLICY_CATALOG_VERSION, PolicyCatalog
from support_agent import ANTHROPIC_TOOLS, AgentLoop, AnthropicPlanner, Planner, RunContext


def evaluate(
    scenario: LiveScenario,
    planner: Planner,
    trial_number: int = 1,
) -> tuple[list[str], dict[str, Any]]:
    runtime = create_scenario_runtime(scenario)
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
            "cache_creation_5m_input_tokens",
            "cache_creation_1h_input_tokens",
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
        cost_values = [
            float(trial["estimated_model_cost"]["amount"])
            for trial in trials
            if trial.get("estimated_model_cost", {}).get("status") == "estimated"
        ]
        interval_low, interval_high = wilson_interval_95(passed, len(trials))
        case_summary = {
            "scenario_id": scenario_id,
            "scenario": trials[0].get("scenario", scenario_id),
            "trials": len(trials),
            "passed": passed,
            "pass_rate": round(passed / len(trials), 4),
            "pass_rate_ci_95": [round(interval_low, 4), round(interval_high, 4)],
            "failure_counts": failure_counts,
            "mean_model_metrics": metric_averages,
            "metric_trial_counts": metric_trial_counts,
        }
        if cost_values:
            case_summary["mean_estimated_model_cost"] = round(sum(cost_values) / len(cost_values), 12)
            case_summary["priced_trials"] = len(cost_values)
        scenario_summaries.append(case_summary)

    total = len(reports)
    passed_total = sum(bool(report.get("passed")) for report in reports)
    overall_interval = wilson_interval_95(passed_total, total) if total else None
    return {
        "scenario_count": len(grouped),
        "trials_per_scenario": min((len(trials) for trials in grouped.values()), default=0),
        "passed_trials": passed_total,
        "total_trials": total,
        "overall_pass_rate": round(passed_total / total, 4) if total else 0.0,
        "overall_pass_rate_ci_95": (
            [round(overall_interval[0], 4), round(overall_interval[1], 4)]
            if overall_interval is not None else None
        ),
        "pass_rate_interval_method": "95% Wilson score interval",
        "scenario_summaries": scenario_summaries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        default="evals/live_scenarios.json",
        help="Versioned scenario JSON path (default: evals/live_scenarios.json)",
    )
    parser.add_argument(
        "--output",
        help="Optional JSON report path. Reports include answers and traces; store them securely.",
    )
    parser.add_argument(
        "--rate-card",
        help="Optional JSON rate card for token-cost estimates; provide current prices for the configured model.",
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
    rate_card = None
    if args.rate_card:
        try:
            rate_card = load_rate_card(args.rate_card, model)
        except (OSError, ValueError) as exc:
            parser.error(f"invalid --rate-card: {exc}")
    dataset_version, scenarios = load_dataset(args.dataset)
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
                    "tags": list(scenario.tags),
                    "expected_statuses": list(scenario.expected_statuses),
                }
            if rate_card is not None:
                report["estimated_model_cost"] = estimate_model_cost(report, rate_card)
            reports.append(report)
            trial_label = f"trial {trial_number}/{args.trials}"
            if failures:
                print(f"FAIL  {trial_label} {scenario.name}: {'; '.join(failures)}")
            else:
                print(f"PASS  {trial_label} {scenario.name}")
    aggregate = summarize_reports(reports)
    tag_summaries = summarize_by_tag(reports)
    for scenario_summary in aggregate["scenario_summaries"]:
        metrics = scenario_summary["mean_model_metrics"]
        print(
            f"CASE  {scenario_summary['scenario']}: "
            f"{scenario_summary['passed']}/{scenario_summary['trials']} "
            f"({scenario_summary['pass_rate']:.0%}; 95% CI "
            f"{scenario_summary['pass_rate_ci_95'][0]:.0%}–{scenario_summary['pass_rate_ci_95'][1]:.0%}); "
            f"mean input/output={metrics.get('input_tokens', 0):.0f}/{metrics.get('output_tokens', 0):.0f}; "
            f"cache read/write={metrics.get('cache_read_input_tokens', 0):.0f}/"
            f"{metrics.get('cache_creation_input_tokens', 0):.0f}; "
            f"model latency={metrics.get('latency_ms', 0):.0f} ms"
            + (
                f"; estimated model cost={scenario_summary['mean_estimated_model_cost']:.8f} "
                f"{rate_card['currency']} per trial"
                if "mean_estimated_model_cost" in scenario_summary else ""
            )
        )
    model_cost_summary = summarize_model_costs(reports, rate_card) if rate_card is not None else None
    summary = {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "provider": "Anthropic Messages API",
        "configured_model": model,
        "dataset_version": dataset_version,
        "dataset_path": str(resolve_dataset_path(args.dataset)),
        "dataset_sha256": dataset_sha256(args.dataset),
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
        "rate_card": rate_card,
        "model_cost_summary": model_cost_summary,
        "tag_summaries": tag_summaries,
        **aggregate,
        "scenarios": reports,
    }
    print(
        f"\n{aggregate['passed_trials']}/{aggregate['total_trials']} live trials passed "
        f"({aggregate['overall_pass_rate']:.0%}; 95% CI "
        f"{aggregate['overall_pass_rate_ci_95'][0]:.0%}–{aggregate['overall_pass_rate_ci_95'][1]:.0%}) "
        f"across {aggregate['scenario_count']} cases"
    )
    for tag_summary in tag_summaries:
        print(f"TAG   {tag_summary['tag']}: {tag_summary['passed']}/{tag_summary['total']} ({tag_summary['pass_rate']:.0%})")
    if model_cost_summary is not None:
        if model_cost_summary["estimated_model_cost_total"] is None:
            print(
                f"MODEL COST  total unavailable because coverage is incomplete; priced "
                f"{model_cost_summary['estimated_trials']}/{model_cost_summary['total_trials']} trials"
            )
        else:
            cost_per_success = model_cost_summary["estimated_model_cost_per_successful_trial"]
            success_cost_label = (
                f"{cost_per_success:.8f} {rate_card['currency']}"
                if cost_per_success is not None else "unavailable (no successful trials)"
            )
            print(
                f"MODEL COST  estimated total={model_cost_summary['estimated_model_cost_total']:.8f} "
                f"{rate_card['currency']}; per successful trial={success_cost_label}"
            )
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Saved report to {path}")
    return 0 if aggregate["passed_trials"] == aggregate["total_trials"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
