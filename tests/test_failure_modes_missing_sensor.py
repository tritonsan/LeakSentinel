from __future__ import annotations

from leaksentinel.orchestrator import run_scenario


def test_missing_audio_sensor_degrades_to_investigate(monkeypatch) -> None:
    monkeypatch.setattr(
        "leaksentinel.orchestrator.local_thermal_check",
        lambda _: {"has_leak_signature": False, "confidence": 0.2, "explanation": "weak thermal"},
    )
    monkeypatch.setattr(
        "leaksentinel.orchestrator.local_audio_check",
        lambda _: {"skipped": True, "reason": "audio_sensor_unavailable", "leak_like": False, "confidence": 0.0},
    )
    out = run_scenario(scenario_id="S02", mode="local", write_bundle=False, ablation="full")
    assert str(out.get("decision", "")).upper() in {"INVESTIGATE", "IGNORE_PLANNED_OPS"}
    assert str(out.get("decision", "")).upper() != "LEAK_CONFIRMED"


def test_missing_thermal_sensor_degrades_to_investigate(monkeypatch) -> None:
    monkeypatch.setattr(
        "leaksentinel.orchestrator.local_thermal_check",
        lambda _: {"skipped": True, "reason": "thermal_sensor_unavailable", "has_leak_signature": False, "confidence": 0.0},
    )
    monkeypatch.setattr(
        "leaksentinel.orchestrator.local_audio_check",
        lambda _: {"skipped": False, "leak_like": False, "confidence": 0.1, "explanation": "weak audio"},
    )
    out = run_scenario(scenario_id="S02", mode="local", write_bundle=False, ablation="full")
    assert str(out.get("decision", "")).upper() in {"INVESTIGATE", "IGNORE_PLANNED_OPS"}
    assert str(out.get("decision", "")).upper() != "LEAK_CONFIRMED"


def test_modal_conflict_is_safety_escalated(monkeypatch) -> None:
    monkeypatch.setattr(
        "leaksentinel.orchestrator.local_thermal_check",
        lambda _: {"has_leak_signature": True, "confidence": 0.95, "explanation": "thermal positive"},
    )
    monkeypatch.setattr(
        "leaksentinel.orchestrator.local_audio_check",
        lambda _: {
            "skipped": False,
            "leak_like": False,
            "confidence": 0.95,
            "explanation": "audio negative",
            "_heuristic": {"leak_like": False, "confidence": 0.95},
        },
    )
    out = run_scenario(scenario_id="S02", mode="local", write_bundle=False, ablation="full")
    flags = [str(x) for x in (out.get("decision_safety_flags") or [])]
    assert str(out.get("decision", "")).upper() != "LEAK_CONFIRMED"
    assert ("modal_conflict" in flags) or (str(out.get("investigate_reason_code", "")) == "modal_conflict")


def test_memory_failure_does_not_break_pipeline(monkeypatch) -> None:
    def fail_local_memory(*args, **kwargs):
        raise RuntimeError("memory unavailable")

    monkeypatch.setattr("leaksentinel.orchestrator.load_memory_local", fail_local_memory)
    out = run_scenario(scenario_id="S02", mode="local", write_bundle=False, ablation="full")
    evidence = out.get("evidence", {}) if isinstance(out.get("evidence"), dict) else {}
    assert isinstance(evidence.get("similar_incidents"), list)
