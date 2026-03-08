from __future__ import annotations

import json
from pathlib import Path

from leaksentinel.eval import benchmark as bench


def test_benchmark_reports_augmented_kpis(tmp_path: Path, monkeypatch) -> None:
    scenario_pack = tmp_path / "scenario_pack.json"
    scenario_pack.write_text(
        json.dumps(
            {
                "scenarios": [
                    {"scenario_id": "A1", "label": "leak", "track": "core"},
                    {"scenario_id": "A2", "label": "planned_ops", "track": "core"},
                    {"scenario_id": "A3", "label": "investigate", "track": "real_challenge"},
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
                "next_evidence_request_v2": {"request_type": "multi_sensor_recheck"},
                "counterfactual_v2": {"decision_delta": {"flipped": False}},
                "impact_estimate_v2": {"expected_total_impact_usd": 5000.0},
                "_runtime": {"bedrock": {"used": mode == "bedrock"}},
            }
        if scenario_id == "A2":
            return {
                "decision": "IGNORE_PLANNED_OPS",
                "confidence": 0.8,
                "analysis_version": "v2",
                "next_evidence_request_v2": {"request_type": "ops_confirmation"},
                "counterfactual_v2": {"decision_delta": {"flipped": True}},
                "impact_estimate_v2": {"expected_total_impact_usd": 1200.0},
                "_runtime": {"bedrock": {"used": False}},
            }
        return {
            "decision": "INVESTIGATE",
            "confidence": 0.6,
            "analysis_version": "v2",
            "next_evidence_request_v2": {"request_type": "multi_sensor_recheck"},
            "counterfactual_v2": {"decision_delta": {"flipped": False}},
            "impact_estimate_v2": {"expected_total_impact_usd": 900.0},
            "_runtime": {"bedrock": {"used": False}},
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
    assert float(s.get("actionability_rate", 0.0)) > 0.0
    assert float(s.get("counterfactual_flip_rate", 0.0)) > 0.0
    assert float(s.get("impact_coverage_rate", 0.0)) > 0.0
    assert "impact_consistency_score" in s
