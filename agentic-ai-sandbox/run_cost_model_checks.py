"""Check explicit model-token rate cards and conservative cost estimates offline."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from evals.cost_model import estimate_model_cost, load_rate_card, summarize_model_costs
from run_live_evals import summarize_reports


def main() -> int:
    rates = {
        "configured_model": "fake-model",
        "currency": "USD",
        "rates_per_million_tokens": {
            "input": 1.0,
            "output": 2.0,
            "cache_read": 0.1,
            "cache_write_5m": 1.25,
            "cache_write_1h": 2.0,
        },
    }
    with tempfile.TemporaryDirectory(prefix="agentic-cost-model-") as temp_dir:
        rate_path = Path(temp_dir) / "rates.json"
        rate_path.write_text(json.dumps(rates), encoding="utf-8")
        rate_card = load_rate_card(rate_path, "fake-model")
        assert len(rate_card["source_sha256"]) == 64
        try:
            load_rate_card(rate_path, "different-model")
        except ValueError as exc:
            assert "must exactly match" in str(exc)
        else:
            raise AssertionError("rate cards must be bound to the configured model")
        print("PASS  rate card validates model identity and records its fingerprint")

        report = {
            "passed": True,
            "model_metrics": {
                "input_tokens": 100,
                "output_tokens": 10,
                "cache_read_input_tokens": 20,
                "cache_creation_input_tokens": 30,
                "cache_creation_5m_input_tokens": 10,
                "cache_creation_1h_input_tokens": 20,
            },
        }
        estimate = estimate_model_cost(report, rate_card)
        assert estimate["status"] == "estimated"
        assert estimate["amount"] == 0.0001745
        assert estimate["component_amounts"]["cache_write_1h"] == 0.00004
        assert estimate["scope"].startswith("model token charges only")
        print("PASS  input, output, cache-read, 5-minute-write, and 1-hour-write rates are priced separately")

        missing_breakdown = {
            "model_metrics": {
                "input_tokens": 100,
                "output_tokens": 10,
                "cache_creation_input_tokens": 30,
            },
        }
        unavailable = estimate_model_cost(missing_breakdown, rate_card)
        assert unavailable["status"] == "unavailable"
        assert "TTL breakdown" in unavailable["reason"]
        assert estimate_model_cost({"passed": False}, rate_card)["status"] == "unavailable"
        print("PASS  incomplete usage stays unpriced instead of assuming a cache-write TTL")

        reports = [
            {"passed": True, "estimated_model_cost": estimate},
            {"passed": False, "estimated_model_cost": estimate},
        ]
        summary = summarize_model_costs(reports, rate_card)
        assert summary["estimated_model_cost_total"] == 0.000349
        assert summary["estimated_model_cost_per_successful_trial"] == 0.000349
        trial_summary = summarize_reports([
            {
                "scenario_id": "priced-case",
                "scenario": "priced case",
                "passed": True,
                "estimated_model_cost": estimate,
                "model_metrics": {},
            }
        ])
        assert trial_summary["scenario_summaries"][0]["mean_estimated_model_cost"] == 0.0001745
        assert trial_summary["scenario_summaries"][0]["priced_trials"] == 1
        partial = summarize_model_costs([reports[0], {"passed": False}], rate_card)
        assert partial["estimated_model_cost_total"] is None
        assert partial["coverage"] == 0.5
        print("PASS  case averages and report cost totals require explicit token-cost coverage")

        rates["rates_per_million_tokens"]["input"] = -1
        rate_path.write_text(json.dumps(rates), encoding="utf-8")
        try:
            load_rate_card(rate_path, "fake-model")
        except ValueError as exc:
            assert "non-negative" in str(exc)
        else:
            raise AssertionError("negative rate must be rejected")
        print("PASS  invalid negative pricing is rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
