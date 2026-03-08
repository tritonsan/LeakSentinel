from __future__ import annotations

import json
from pathlib import Path

from leaksentinel.impact.scorecard import build_nrw_carbon_scorecard


def test_scorecard_outputs_business_metrics() -> None:
    out = build_nrw_carbon_scorecard(
        decision={"decision": "LEAK_CONFIRMED", "confidence": 0.9},
        impact_estimate_v2={"expected_total_impact_usd": 5000.0},
        impact_estimate_v1={},
        continuous_flow_alert={"detected": True, "severity": "high"},
    )
    assert float(out.get("estimated_water_saved_m3", 0.0)) > 0.0
    assert float(out.get("estimated_co2e_kg_avoided", 0.0)) > 0.0
    assert "nrw_risk_band" in out


def test_scorecard_reads_assumptions_register(tmp_path: Path) -> None:
    p = tmp_path / "assumptions.json"
    p.write_text(
        json.dumps(
            {
                "scorecard": {
                    "water_unit_cost_usd_per_m3": 2.5,
                    "co2e_kg_per_m3": 0.9,
                    "baseline_nrw_pct": 30.0,
                }
            }
        ),
        encoding="utf-8",
    )
    out = build_nrw_carbon_scorecard(
        decision={"decision": "LEAK_CONFIRMED", "confidence": 0.9},
        impact_estimate_v2={"expected_total_impact_usd": 2500.0},
        impact_estimate_v1={},
        continuous_flow_alert={},
        assumptions_path=p,
    )
    assumptions = out.get("assumptions", {})
    assert float(assumptions.get("water_unit_cost_usd_per_m3", 0.0)) == 2.5
    assert float(assumptions.get("co2e_kg_per_m3", 0.0)) == 0.9
    assert float(assumptions.get("baseline_nrw_pct", 0.0)) == 30.0
