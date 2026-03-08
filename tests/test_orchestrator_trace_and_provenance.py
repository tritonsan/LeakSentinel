from __future__ import annotations

from leaksentinel.orchestrator import run_scenario


def test_orchestrator_emits_trace_quality_calibration_and_provenance() -> None:
    out = run_scenario(
        scenario_id="S02",
        mode="local",
        write_bundle=False,
        ablation="full",
        analysis_version="v2",
    )
    assert isinstance(out.get("decision_trace_v1"), dict)
    assert isinstance(out.get("evidence_quality_v1"), dict)
    assert isinstance(out.get("confidence_calibration_v1"), dict)
    assert isinstance(out.get("provenance_v1"), dict)
    calib = out.get("confidence_calibration_v1", {})
    assert "raw_confidence" in calib
    assert "calibrated_confidence" in calib
    assert float(out.get("confidence", 0.0)) == float(calib.get("calibrated_confidence", 0.0))


def test_orchestrator_emits_closed_loop_and_impact_proof() -> None:
    out = run_scenario(
        scenario_id="S02",
        mode="local",
        write_bundle=False,
        ablation="full",
        analysis_version="v2",
    )
    assert isinstance(out.get("closed_loop_summary_v1"), dict)
    assert isinstance(out.get("impact_proof_v1"), dict)
    impact_proof = out.get("impact_proof_v1", {})
    assert "baseline_vs_with_leaksentinel" in impact_proof

