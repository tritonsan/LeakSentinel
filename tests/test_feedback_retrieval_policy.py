from __future__ import annotations

from leaksentinel.feedback.policy import apply_confidence_downshift
from leaksentinel.feedback.retrieval import summarize_root_causes, top_k_similar_mistakes


def test_top_k_similar_mistakes_returns_ranked_rows() -> None:
    records = [
        {
            "feedback_id": "fb-1",
            "outcome": "false_positive_rejected_by_operator",
            "fingerprint_text": "zone=zone-1 anomaly=1.5 thermal_hit=True planned=False",
            "root_cause_guess": "thermal_artifact_without_acoustic_confirmation",
            "evidence_gap": "collect_acoustic_sample_for_confirmation",
            "scenario_id": "S1",
            "zone": "zone-1",
            "timestamp": "2026-02-05T03:00:00",
            "decision": "LEAK_CONFIRMED",
            "confidence": 0.9,
        },
        {
            "feedback_id": "fb-2",
            "outcome": "false_positive_rejected_by_operator",
            "fingerprint_text": "zone=zone-9 anomaly=0.2 thermal_hit=False planned=True",
            "root_cause_guess": "planned_operation_overlap",
            "evidence_gap": "confirm_planned_ops_status_and_capture_post_window_sample",
            "scenario_id": "S9",
            "zone": "zone-9",
            "timestamp": "2026-02-07T03:00:00",
            "decision": "IGNORE_PLANNED_OPS",
            "confidence": 0.7,
        },
    ]
    out = top_k_similar_mistakes(
        query_text="zone=zone-1 anomaly=1.4 thermal_hit=True",
        feedback_records=records,
        k=2,
        dim=256,
        min_score=0.0,
    )
    assert len(out) == 2
    assert out[0]["feedback_id"] == "fb-1"
    assert out[0]["score"] >= out[1]["score"]
    assert out[0]["root_cause_guess"]
    summ = summarize_root_causes(out, top_n=2)
    assert "top_causes" in summ
    assert isinstance(summ["top_causes"], list)


def test_apply_confidence_downshift_applies_without_flipping_decision() -> None:
    decision = {
        "decision": "LEAK_CONFIRMED",
        "confidence": 0.9,
        "rationale": ["Strong thermal signal."],
        "recommended_action": "Dispatch.",
    }
    similar = [
        {"score": 0.91, "feedback_id": "fb-1", "outcome": "false_positive_rejected_by_operator"},
        {"score": 0.84, "feedback_id": "fb-2", "outcome": "false_positive_rejected_by_operator"},
    ]

    out = apply_confidence_downshift(decision=decision, similar_mistakes=similar, min_score=0.82)
    assert out["applied"] is True
    assert out["decision"]["decision"] == "LEAK_CONFIRMED"
    assert out["decision"]["confidence"] < 0.9
    assert out["decision"]["confidence"] >= 0.35
    assert any("Historical false-positive similarity detected" in x for x in out["decision"]["rationale"])


def test_apply_confidence_downshift_no_match_no_change() -> None:
    decision = {"decision": "INVESTIGATE", "confidence": 0.55, "rationale": ["Evidence is weak."]}
    out = apply_confidence_downshift(
        decision=decision,
        similar_mistakes=[{"score": 0.2, "feedback_id": "fb-x"}],
        min_score=0.82,
    )
    assert out["applied"] is False
    assert out["decision"]["confidence"] == 0.55
