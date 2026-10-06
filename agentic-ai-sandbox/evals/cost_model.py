"""Explicit, auditable token-rate calculations for Anthropic eval reports."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any


RATE_NAMES = ("input", "output", "cache_read", "cache_write_5m", "cache_write_1h")


def load_rate_card(path: str | Path, configured_model: str) -> dict[str, Any]:
    rate_path = Path(path).resolve()
    document = json.loads(rate_path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("Rate-card root must be a JSON object.")
    if document.get("configured_model") != configured_model:
        raise ValueError(
            "Rate-card configured_model must exactly match ANTHROPIC_MODEL "
            f"({configured_model!r})."
        )
    currency = document.get("currency")
    if not isinstance(currency, str) or not currency.strip():
        raise ValueError("Rate card must declare a currency code or label.")
    rates = document.get("rates_per_million_tokens")
    if not isinstance(rates, dict) or set(rates) != set(RATE_NAMES):
        raise ValueError(f"Rate card must define exactly these rates: {', '.join(RATE_NAMES)}.")
    parsed_rates: dict[str, float] = {}
    for name in RATE_NAMES:
        rate = rates[name]
        if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not math.isfinite(rate) or rate < 0:
            raise ValueError(f"Rate {name!r} must be a finite, non-negative number.")
        parsed_rates[name] = float(rate)
    return {
        "configured_model": configured_model,
        "currency": currency.strip(),
        "rates_per_million_tokens": parsed_rates,
        "source_path": str(rate_path),
        "source_sha256": hashlib.sha256(rate_path.read_bytes()).hexdigest(),
    }


def estimate_model_cost(report: dict[str, Any], rate_card: dict[str, Any]) -> dict[str, Any]:
    if "model_metrics" not in report:
        return {"status": "unavailable", "reason": "No model usage metrics were recorded."}
    metrics = report["model_metrics"]
    if not isinstance(metrics, dict):
        return {"status": "unavailable", "reason": "Model usage metrics were not an object."}
    token_counts = {
        "input": metrics.get("input_tokens", 0),
        "output": metrics.get("output_tokens", 0),
        "cache_read": metrics.get("cache_read_input_tokens", 0),
        "cache_creation": metrics.get("cache_creation_input_tokens", 0),
        "cache_creation_5m": metrics.get("cache_creation_5m_input_tokens", 0),
        "cache_creation_1h": metrics.get("cache_creation_1h_input_tokens", 0),
    }
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in token_counts.values()):
        return {"status": "unavailable", "reason": "Provider reported invalid token-count fields."}
    cached_5m = token_counts["cache_creation_5m"]
    cached_1h = token_counts["cache_creation_1h"]
    reported_creation = token_counts["cache_creation"]
    if cached_5m + cached_1h != reported_creation:
        return {
            "status": "unavailable",
            "reason": "Provider usage omitted or disagreed with the cache-write TTL breakdown.",
        }

    rates = rate_card["rates_per_million_tokens"]
    priced_token_counts = {
        "input": token_counts["input"],
        "output": token_counts["output"],
        "cache_read": token_counts["cache_read"],
        "cache_write_5m": cached_5m,
        "cache_write_1h": cached_1h,
    }
    component_costs = {
        name: priced_token_counts[name] * rates[name] / 1_000_000
        for name in RATE_NAMES
    }
    total = sum(component_costs.values())
    return {
        "status": "estimated",
        "currency": rate_card["currency"],
        "amount": round(total, 12),
        "component_amounts": {name: round(amount, 12) for name, amount in component_costs.items()},
        "token_counts": priced_token_counts,
        "scope": "model token charges only; excludes tools, infrastructure, taxes, and other provider fees",
    }


def summarize_model_costs(reports: list[dict[str, Any]], rate_card: dict[str, Any]) -> dict[str, Any]:
    estimates = [report.get("estimated_model_cost", {}) for report in reports]
    available = [estimate for estimate in estimates if estimate.get("status") == "estimated"]
    coverage = len(available)
    complete = coverage == len(reports)
    total = sum(estimate["amount"] for estimate in available) if complete else None
    successes = sum(bool(report.get("passed")) for report in reports)
    return {
        "currency": rate_card["currency"],
        "estimated_trials": coverage,
        "total_trials": len(reports),
        "coverage": round(coverage / len(reports), 4) if reports else 0.0,
        "estimated_model_cost_total": round(total, 12) if total is not None else None,
        "estimated_model_cost_per_successful_trial": (
            round(total / successes, 12) if total is not None and successes else None
        ),
        "scope": "model token charges only; excludes tools, infrastructure, taxes, and other provider fees",
    }
