from __future__ import annotations

from leaksentinel.orchestrator import _apply_real_challenge_audio_backup, _track_policy


def test_v1_core_track_policy_lock() -> None:
    assert _track_policy("core") == {
        "confirm_anomaly_min": 1.0,
        "strong_modal_conf_min": 0.8,
        "ignore_planned_anomaly_min": 1.0,
        "cautious_mode": False,
        "investigate_on_modal_conflict": True,
        "uncertain_audio_requires_investigate": True,
    }


def test_v1_real_challenge_track_policy_lock() -> None:
    assert _track_policy("real_challenge") == {
        "confirm_anomaly_min": 0.0,
        "strong_modal_conf_min": 0.75,
        "ignore_planned_anomaly_min": 0.85,
        "confirm_use_abs_anomaly": True,
        "cautious_mode": True,
        "investigate_on_modal_conflict": True,
        "uncertain_audio_requires_investigate": True,
    }


def test_v1_audio_backup_threshold_lock_anomaly_signal() -> None:
    base_audio = {
        "skipped": False,
        "leak_like": False,
        "confidence": 0.95,
        "_heuristic": {"leak_like": True, "confidence": 0.8},
    }
    below = _apply_real_challenge_audio_backup(
        audio=base_audio,
        flow_summary={"anomaly_score": 0.29},
        context={"audio_label_confidence": "high_confidence"},
        track="real_challenge",
        mode="bedrock",
        strong_modal_conf_min=0.75,
    )
    assert below["leak_like"] is False
    assert "fusion_rule" not in below

    at_edge = _apply_real_challenge_audio_backup(
        audio=base_audio,
        flow_summary={"anomaly_score": 0.30},
        context={"audio_label_confidence": "high_confidence"},
        track="real_challenge",
        mode="bedrock",
        strong_modal_conf_min=0.75,
    )
    assert at_edge["leak_like"] is True
    assert at_edge["fusion_rule"] == "high_confidence_audio_backup"

