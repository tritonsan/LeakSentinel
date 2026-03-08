from __future__ import annotations

from leaksentinel.orchestrator import run_scenario


def test_augmented_output_fields_exist() -> None:
    out = run_scenario(scenario_id="S02", mode="local", write_bundle=False, ablation="full")
    assert out.get("analysis_version") == "v2"
    assert "next_evidence_request" in out
    assert "next_evidence_request_v2" in out
    assert "counterfactual" in out
    assert "counterfactual_v2" in out
    assert "impact_estimate" in out
    assert "impact_estimate_v2" in out
    assert "historical_root_causes" in out
    assert "feedback_pattern_summary" in out
    assert isinstance(out.get("counterfactual"), dict)
    assert isinstance(out.get("counterfactual_v2"), dict)
    assert isinstance(out.get("impact_estimate"), dict)
    assert isinstance(out.get("impact_estimate_v2"), dict)
    assert isinstance(out.get("next_evidence_request_v2"), dict)
    assert isinstance(out.get("historical_root_causes"), list)
    assert isinstance(out.get("feedback_pattern_summary"), str)
    assert "decision_safety_flags" in out
    assert "investigate_reason_code" in out
    assert "assumptions" in out.get("impact_estimate", {})
    assert "expected_total_impact_usd" in out.get("impact_estimate_v2", {})
    assert "scenarios" in out.get("counterfactual_v2", {})
    assert "request_type" in out.get("next_evidence_request_v2", {})


def test_real_challenge_uses_real_track_policy() -> None:
    out = run_scenario(scenario_id="S06", mode="local", write_bundle=False, ablation="full")
    runtime = out.get("_runtime", {})
    assert runtime.get("track") == "real_challenge"
    policy = runtime.get("decision_policy", {})
    assert float(policy.get("confirm_anomaly_min", 999.0)) < 1.0
    assert bool(policy.get("confirm_use_abs_anomaly", False)) is True
    assert bool(policy.get("cautious_mode", False)) is True


def test_full_ablation_always_runs_audio(monkeypatch) -> None:
    calls = {"audio": 0}

    def fake_thermal_check(_: str) -> dict:
        return {"has_leak_signature": True, "confidence": 0.99, "explanation": "forced thermal positive"}

    def fake_audio_check(_: str) -> dict:
        calls["audio"] += 1
        return {"leak_like": True, "confidence": 0.9, "explanation": "forced audio positive"}

    monkeypatch.setattr("leaksentinel.orchestrator.local_thermal_check", fake_thermal_check)
    monkeypatch.setattr("leaksentinel.orchestrator.local_audio_check", fake_audio_check)

    out = run_scenario(scenario_id="S08", mode="local", write_bundle=False, ablation="full")
    assert calls["audio"] == 1
    assert bool(out.get("evidence", {}).get("audio", {}).get("skipped", False)) is False
