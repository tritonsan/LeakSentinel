from __future__ import annotations

from leaksentinel.tools.decision import local_decision


def _base_evidence() -> dict:
    return {
        "context": {"flow_summary": {"anomaly_score": 0.5, "observed": 42.0, "expected": 40.0}},
        "thermal": {"has_leak_signature": False, "confidence": 0.2},
        "audio": {"skipped": False, "leak_like": True, "confidence": 0.8},
        "ops": {"planned_op_found": False, "planned_op_ids": []},
    }


def test_default_policy_requires_higher_anomaly_for_confirmation() -> None:
    out = local_decision(evidence=_base_evidence())
    assert out["decision"] == "INVESTIGATE"


def test_relaxed_policy_confirms_with_strong_modal_even_lower_anomaly() -> None:
    out = local_decision(
        evidence=_base_evidence(),
        policy={"confirm_anomaly_min": 0.35, "strong_modal_conf_min": 0.75, "ignore_planned_anomaly_min": 0.85},
    )
    assert out["decision"] == "LEAK_CONFIRMED"


def test_real_challenge_policy_can_use_abs_anomaly_signal() -> None:
    ev = _base_evidence()
    ev["context"]["flow_summary"]["anomaly_score"] = -0.4
    out = local_decision(
        evidence=ev,
        policy={
            "confirm_anomaly_min": 0.0,
            "strong_modal_conf_min": 0.75,
            "ignore_planned_anomaly_min": 0.85,
            "confirm_use_abs_anomaly": True,
        },
    )
    assert out["decision"] == "LEAK_CONFIRMED"


def test_cautious_policy_investigates_modal_conflict() -> None:
    ev = {
        "context": {"flow_summary": {"anomaly_score": 1.2, "observed": 45.0, "expected": 40.0}},
        "thermal": {"has_leak_signature": True, "confidence": 0.85},
        "audio": {"skipped": False, "leak_like": False, "confidence": 0.95},
        "ops": {"planned_op_found": False, "planned_op_ids": []},
    }
    out = local_decision(
        evidence=ev,
        policy={
            "confirm_anomaly_min": 0.0,
            "strong_modal_conf_min": 0.75,
            "ignore_planned_anomaly_min": 0.85,
            "cautious_mode": True,
            "investigate_on_modal_conflict": True,
        },
    )
    assert out["decision"] == "INVESTIGATE"
    assert out["investigate_reason_code"] == "modal_conflict"


def test_cautious_policy_uses_uncertain_audio_guardrail() -> None:
    ev = {
        "context": {
            "flow_summary": {"anomaly_score": 0.8, "observed": 44.0, "expected": 40.0},
            "audio_label_confidence": "uncertain",
        },
        "thermal": {"has_leak_signature": False, "confidence": 0.2},
        "audio": {"skipped": False, "leak_like": True, "confidence": 0.9},
        "ops": {"planned_op_found": False, "planned_op_ids": []},
    }
    out = local_decision(
        evidence=ev,
        policy={
            "confirm_anomaly_min": 0.0,
            "strong_modal_conf_min": 0.75,
            "ignore_planned_anomaly_min": 0.85,
            "cautious_mode": True,
            "uncertain_audio_requires_investigate": True,
        },
    )
    assert out["decision"] == "INVESTIGATE"
    assert out["investigate_reason_code"] == "uncertain_audio_label"
