from __future__ import annotations

import json
from pathlib import Path

from leaksentinel.eval import benchmark as bench


def test_benchmark_reports_calibration_and_feedback_metrics(tmp_path: Path, monkeypatch) -> None:
    scenario_pack = tmp_path / "scenario_pack.json"
    scenario_pack.write_text(
        json.dumps(
            {
                "scenarios": [
                    {"scenario_id": "A1", "label": "leak", "track": "core"},
                    {"scenario_id": "A2", "label": "planned_ops", "track": "core"},
                ]
            }
        ),
        encoding="utf-8",
    )

    def fake_run_scenario(*, scenario_id: str, mode: str, write_bundle: bool, ablation: str):
        if scenario_id == "A1":
            return {
                "decision": "LEAK_CONFIRMED",
                "confidence": 0.9,
                "analysis_version": "v2",
                "counterfactual_v2": {"decision_delta": {"flipped": False}},
                "impact_estimate_v2": {"expected_total_impact_usd": 3200.0},
                "scorecard": {"estimated_cost_saved_usd": 3200.0, "estimated_co2e_kg_avoided": 120.0},
                "evidence": {"similar_mistakes": [{"score": 0.92}]},
                "closed_loop_summary_v1": {
                    "feedback_effective": True,
                    "repeat_fp_risk_reduction_pct": 24.0,
                },
                "_runtime": {"bedrock": {"used": False}, "feedback_memory": {"policy": {"applied": True}}},
            }
        return {
            "decision": "IGNORE_PLANNED_OPS",
            "confidence": 0.7,
            "analysis_version": "v2",
            "counterfactual_v2": {"decision_delta": {"flipped": False}},
            "impact_estimate_v2": {"expected_total_impact_usd": 900.0},
            "scorecard": {"estimated_cost_saved_usd": 900.0, "estimated_co2e_kg_avoided": 20.0},
            "evidence": {"similar_mistakes": []},
            "closed_loop_summary_v1": {
                "feedback_effective": False,
                "repeat_fp_risk_reduction_pct": 0.0,
            },
            "_runtime": {"bedrock": {"used": False}, "feedback_memory": {}},
        }

    monkeypatch.setattr(bench, "run_scenario", fake_run_scenario)
    res = bench.run_benchmark(
        mode="local",
        scenario_pack_path=scenario_pack,
        ablations=["full"],
        out_dir=tmp_path / "out",
        strict=False,
    )
    s = res.summary["full"]
    assert "brier_score" in s
    assert "ece" in s
    assert "repeat_fp_reduction_rate" in s
    assert "feedback_effectiveness_rate" in s
    assert float(s["feedback_effectiveness_rate"]) >= 0.0

