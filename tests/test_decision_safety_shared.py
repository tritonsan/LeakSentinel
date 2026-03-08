from __future__ import annotations

from leaksentinel.orchestrator import _apply_real_challenge_audio_backup, _apply_shared_decision_safety


def test_shared_safety_keeps_leak_when_no_conflict_or_uncertain_audio() -> None:
    decision = {
        "decision": "LEAK_CONFIRMED",
        "confidence": 0.9,
        "rationale": ["model says leak"],
        "decision_safety_flags": [],
    }
    evidence = {
        "context": {"audio_label_confidence": "high_confidence", "flow_summary": {"anomaly_score": 0.8}},
        "thermal": {
            "has_leak_signature": True,
            "confidence": 0.95,
            "_heuristic": {"has_leak_signature": False, "confidence": 0.95},
        },
        "audio": {
            "skipped": False,
            "leak_like": True,
            "confidence": 0.95,
            "_heuristic": {"leak_like": False, "confidence": 0.95},
        },
        "ops": {"planned_op_found": False},
    }
    policy = {
        "strong_modal_conf_min": 0.75,
        "cautious_mode": True,
        "investigate_on_modal_conflict": True,
        "uncertain_audio_requires_investigate": True,
    }
    out = _apply_shared_decision_safety(decision=decision, evidence=evidence, policy=policy)
    assert out["decision"] == "LEAK_CONFIRMED"
    assert out["investigate_reason_code"] == ""
    assert "uncorroborated_modal_leak" not in out["decision_safety_flags"]


def test_shared_safety_demotes_leak_on_modal_conflict() -> None:
    decision = {
        "decision": "LEAK_CONFIRMED",
        "confidence": 0.9,
        "rationale": ["model says leak"],
        "decision_safety_flags": [],
    }
    evidence = {
        "context": {"audio_label_confidence": "high_confidence", "flow_summary": {"anomaly_score": 1.3}},
        "thermal": {"has_leak_signature": True, "confidence": 0.9},
        "audio": {"skipped": False, "leak_like": False, "confidence": 0.95},
        "ops": {"planned_op_found": False},
    }
    policy = {
        "strong_modal_conf_min": 0.75,
        "cautious_mode": True,
        "investigate_on_modal_conflict": True,
        "uncertain_audio_requires_investigate": True,
    }
    out = _apply_shared_decision_safety(decision=decision, evidence=evidence, policy=policy)
    assert out["decision"] == "INVESTIGATE"
    assert out["investigate_reason_code"] == "modal_conflict"
    assert "modal_conflict" in out["decision_safety_flags"]


def test_shared_safety_does_not_force_conflict_when_negative_is_not_corroborated() -> None:
    decision = {
        "decision": "LEAK_CONFIRMED",
        "confidence": 0.9,
        "rationale": ["model says leak"],
        "decision_safety_flags": [],
    }
    evidence = {
        "context": {"audio_label_confidence": "high_confidence", "flow_summary": {"anomaly_score": 1.3}},
        "thermal": {"has_leak_signature": True, "confidence": 0.9, "_heuristic": {"has_leak_signature": False, "confidence": 0.2}},
        "audio": {
            "skipped": False,
            "leak_like": False,
            "confidence": 0.95,
            "_heuristic": {"leak_like": True, "confidence": 0.9},
        },
        "ops": {"planned_op_found": False},
    }
    policy = {
        "strong_modal_conf_min": 0.75,
        "cautious_mode": True,
        "investigate_on_modal_conflict": True,
        "uncertain_audio_requires_investigate": True,
    }
    out = _apply_shared_decision_safety(decision=decision, evidence=evidence, policy=policy)
    assert out["decision"] == "LEAK_CONFIRMED"
    assert out["investigate_reason_code"] == ""


def test_shared_safety_demotes_low_trust_audio_without_corroboration() -> None:
    decision = {
        "decision": "LEAK_CONFIRMED",
        "confidence": 0.9,
        "rationale": ["model says leak"],
        "decision_safety_flags": [],
    }
    evidence = {
        "context": {"audio_label_confidence": "synthetic", "flow_summary": {"anomaly_score": 0.7}},
        "thermal": {
            "has_leak_signature": False,
            "confidence": 0.8,
            "_heuristic": {"has_leak_signature": False, "confidence": 0.95},
        },
        "audio": {
            "skipped": False,
            "leak_like": True,
            "confidence": 0.9,
            "_heuristic": {"leak_like": False, "confidence": 0.9},
        },
        "ops": {"planned_op_found": False},
    }
    policy = {
        "strong_modal_conf_min": 0.75,
        "cautious_mode": True,
        "investigate_on_modal_conflict": True,
        "uncertain_audio_requires_investigate": True,
    }
    out = _apply_shared_decision_safety(decision=decision, evidence=evidence, policy=policy)
    assert out["decision"] == "INVESTIGATE"
    assert out["investigate_reason_code"] == "uncorroborated_modal_leak"
    assert "uncorroborated_modal_leak" in out["decision_safety_flags"]


def test_real_challenge_audio_backup_applies_on_high_conflict() -> None:
    audio = {
        "skipped": False,
        "leak_like": False,
        "confidence": 0.95,
        "explanation": "model negative",
        "_heuristic": {"leak_like": True, "confidence": 0.8, "explanation": "heuristic positive"},
    }
    out = _apply_real_challenge_audio_backup(
        audio=audio,
        flow_summary={"anomaly_score": 0.9},
        context={"audio_label_confidence": "high_confidence"},
        track="real_challenge",
        mode="bedrock",
        strong_modal_conf_min=0.75,
    )
    assert out["leak_like"] is True
    assert float(out["confidence"]) >= 0.8
    assert out["fusion_rule"] == "high_confidence_audio_backup"
    assert isinstance(out.get("_model"), dict)


def test_real_challenge_audio_backup_does_not_apply_for_uncertain_label() -> None:
    audio = {
        "skipped": False,
        "leak_like": False,
        "confidence": 0.95,
        "_heuristic": {"leak_like": True, "confidence": 0.8},
    }
    out = _apply_real_challenge_audio_backup(
        audio=audio,
        flow_summary={"anomaly_score": 1.2},
        context={"audio_label_confidence": "uncertain"},
        track="real_challenge",
        mode="bedrock",
        strong_modal_conf_min=0.75,
    )
    assert out["leak_like"] is False
    assert "fusion_rule" not in out


def test_shared_safety_realigns_investigate_to_ignore_for_strong_planned_ops_pattern() -> None:
    decision = {
        "decision": "INVESTIGATE",
        "confidence": 0.55,
        "rationale": ["initial investigate"],
        "decision_safety_flags": [],
    }
    evidence = {
        "context": {"audio_label_confidence": "uncertain", "flow_summary": {"anomaly_score": 1.7}},
        "thermal": {"has_leak_signature": False, "confidence": 0.2},
        "audio": {"skipped": False, "leak_like": False, "confidence": 0.2},
        "ops": {"planned_op_found": True, "planned_op_ids": ["OP-001"]},
    }
    policy = {
        "strong_modal_conf_min": 0.75,
        "ignore_planned_anomaly_min": 0.85,
        "confirm_use_abs_anomaly": False,
        "cautious_mode": True,
        "investigate_on_modal_conflict": True,
        "uncertain_audio_requires_investigate": True,
    }
    out = _apply_shared_decision_safety(decision=decision, evidence=evidence, policy=policy)
    assert out["decision"] == "IGNORE_PLANNED_OPS"
    assert out["investigate_reason_code"] == ""
    assert "planned_ops_realign_ignore" in out["decision_safety_flags"]
