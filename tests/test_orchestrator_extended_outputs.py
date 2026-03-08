from __future__ import annotations

from leaksentinel.orchestrator import run_scenario


def test_extended_outputs_present_by_default() -> None:
    out = run_scenario(scenario_id="S02", mode="local", write_bundle=False, ablation="full", analysis_version="v2")
    assert "continuous_flow_alert" in out
    assert "pressure_plan" in out
    assert "audio_explain" in out
    assert "scorecard" in out
    assert "standards_readiness" in out
    assert isinstance(out.get("continuous_flow_alert"), dict)
    assert isinstance(out.get("pressure_plan"), dict)
    assert isinstance(out.get("audio_explain"), dict)
    assert isinstance(out.get("scorecard"), dict)
    assert isinstance(out.get("standards_readiness"), dict)
