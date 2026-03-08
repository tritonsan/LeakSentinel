from __future__ import annotations

from leaksentinel.orchestrator import _calibrate_confidence_v1


def test_calibration_applies_track_temperature_and_table() -> None:
    decision = {
        "decision": "IGNORE_PLANNED_OPS",
        "confidence": 0.78,
        "decision_safety_flags": [],
    }
    evidence_quality = {"overall_score": 0.92, "issues": []}
    runtime = {"bedrock": {"used": False, "fallback": {}}, "track": "real_challenge"}
    profile = {
        "version": "temperature_scaling_v1",
        "default": {
            "temperature": 1.0,
            "decision_temperatures": {"IGNORE_PLANNED_OPS": 1.0},
            "confidence_table": [
                {"raw": 0.05, "calibrated": 0.06},
                {"raw": 0.5, "calibrated": 0.48},
                {"raw": 0.95, "calibrated": 0.88},
            ],
        },
        "tracks": {
            "real_challenge": {
                "temperature": 1.3,
                "decision_temperatures": {"IGNORE_PLANNED_OPS": 1.2},
            }
        },
    }

    out = _calibrate_confidence_v1(
        decision=decision,
        evidence_quality=evidence_quality,
        runtime=runtime,
        track="real_challenge",
        calibration_profile=profile,
    )
    assert out["method"] == "temperature_scaling_table_v1"
    assert out["track"] == "real_challenge"
    assert float(out["effective_temperature"]) > 1.0
    assert bool(out["table_applied"]) is True
    assert float(out["calibrated_confidence"]) != float(out["raw_confidence"])


def test_calibration_preserves_confidence_range() -> None:
    decision = {
        "decision": "LEAK_CONFIRMED",
        "confidence": 0.99,
        "decision_safety_flags": ["modal_conflict"],
    }
    evidence_quality = {"overall_score": 0.1, "issues": ["audio_signal_missing"]}
    runtime = {"bedrock": {"used": True, "fallback": {"thermal": False, "audio": False}}, "track": "core"}

    out = _calibrate_confidence_v1(
        decision=decision,
        evidence_quality=evidence_quality,
        runtime=runtime,
        track="core",
        calibration_profile=None,
    )
    assert 0.05 <= float(out["calibrated_confidence"]) <= 0.99
