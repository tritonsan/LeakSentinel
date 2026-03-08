from __future__ import annotations

from leaksentinel.impact.proof import build_impact_compare


def test_impact_compare_builds_baseline_and_sensitivity() -> None:
    out = build_impact_compare(
        bundles=[
            {
                "impact_estimate_v2": {"expected_total_impact_usd": 1800.0},
                "scorecard": {"estimated_water_saved_m3": 80.0},
                "evidence": {"context": {"scenario_id": "S1"}},
            },
            {
                "impact_estimate_v1": {
                    "avoided_false_dispatch_estimate": 500.0,
                    "avoided_leak_loss_estimate": 700.0,
                },
                "evidence": {"context": {"scenario_id": "S2"}},
            },
        ],
        assumptions_register={
            "impact": {"dispatch_cost_usd": 1000.0, "leak_loss_per_hour_usd": 4000.0, "default_delay_hours": 1.0},
            "scorecard": {"water_unit_cost_usd_per_m3": 2.0, "co2e_kg_per_m3": 0.5},
            "sensitivity": {"low_multiplier": 0.8, "mid_multiplier": 1.0, "high_multiplier": 1.2},
        },
        persona="industrial",
    )
    assert out["mode"] == "impact_compare_v1"
    assert str((out.get("persona_applied") or {}).get("persona")) == "industrial"
    assert float(out["cost_saved_usd"]) > 0.0
    assert float(out["baseline_vs_with_leaksentinel"]["estimated_savings_usd"]) > 0.0
    s = out.get("assumption_sensitivity", {})
    assert float(s.get("min", 0.0)) <= float(s.get("median", 0.0)) <= float(s.get("max", 0.0))
    bands = out.get("impact_bands", {})
    assert float(bands.get("conservative", 0.0)) <= float(bands.get("expected", 0.0)) <= float(bands.get("aggressive", 0.0))
