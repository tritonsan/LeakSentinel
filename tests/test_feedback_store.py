from __future__ import annotations

import json
from pathlib import Path

import pytest

from leaksentinel.feedback.store import (
    create_feedback_record,
    list_feedback_records,
    resolve_latest_bundle_for_scenario,
)


def _write_bundle(path: Path, *, scenario_id: str, zone: str = "zone-1", ts: str = "2026-02-05T03:00:00") -> None:
    obj = {
        "decision": "LEAK_CONFIRMED",
        "confidence": 0.9,
        "rationale": ["test rationale"],
        "evidence": {
            "context": {
                "scenario_id": scenario_id,
                "zone": zone,
                "timestamp": ts,
                "flow_summary": {"anomaly_score": 1.5},
            },
            "thermal": {"has_leak_signature": True, "confidence": 0.9},
            "audio": {"skipped": False, "leak_like": True, "confidence": 0.8},
            "ops": {"planned_op_found": False, "planned_op_ids": []},
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def test_create_and_list_feedback_record(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "evidence"
    feedback_dir = tmp_path / "feedback"
    bundle = evidence_dir / "S99_zone-1_2026-02-05T03-00-00.json"
    _write_bundle(bundle, scenario_id="S99")

    rec = create_feedback_record(
        bundle_path=bundle,
        outcome="false_positive_rejected_by_operator",
        operator_note="planned heat artifact",
        reviewer="op-1",
        evidence_dir=evidence_dir,
        feedback_dir=feedback_dir,
    )
    assert rec["feedback_id"]
    assert rec["outcome"] == "false_positive_rejected_by_operator"
    assert "planned heat artifact" in rec["fingerprint_text"]
    assert rec["root_cause_guess"]
    assert rec["evidence_gap"]
    assert Path(rec["_stored_path"]).exists()

    rows = list_feedback_records(feedback_dir=feedback_dir, limit=10)
    assert len(rows) == 1
    assert rows[0]["feedback_id"] == rec["feedback_id"]
    assert rows[0]["zone"] == "zone-1"
    assert rows[0]["root_cause_guess"] == rec["root_cause_guess"]


def test_resolve_latest_bundle_for_scenario(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "evidence"
    b1 = evidence_dir / "S11_zone-1_2026-02-05T03-00-00.json"
    b2 = evidence_dir / "S11_zone-1_2026-02-06T03-00-00.json"
    _write_bundle(b1, scenario_id="S11", ts="2026-02-05T03:00:00")
    _write_bundle(b2, scenario_id="S11", ts="2026-02-06T03:00:00")
    # Touch b2 later.
    b2.write_text(b2.read_text(encoding="utf-8"), encoding="utf-8")
    resolved = resolve_latest_bundle_for_scenario(evidence_dir=evidence_dir, scenario_id="S11")
    assert resolved == b2


def test_create_feedback_invalid_outcome(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "evidence"
    feedback_dir = tmp_path / "feedback"
    bundle = evidence_dir / "S00_zone-1_2026-02-05T03-00-00.json"
    _write_bundle(bundle, scenario_id="S00")

    with pytest.raises(ValueError):
        create_feedback_record(
            bundle_path=bundle,
            outcome="invalid_outcome",
            evidence_dir=evidence_dir,
            feedback_dir=feedback_dir,
        )


def test_create_feedback_manual_root_cause_fields(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "evidence"
    feedback_dir = tmp_path / "feedback"
    bundle = evidence_dir / "S55_zone-1_2026-02-05T03-00-00.json"
    _write_bundle(bundle, scenario_id="S55")

    rec = create_feedback_record(
        bundle_path=bundle,
        outcome="false_positive_rejected_by_operator",
        root_cause_guess="planned_operation_overlap",
        evidence_gap="confirm_planned_ops_status_and_capture_post_window_sample",
        evidence_dir=evidence_dir,
        feedback_dir=feedback_dir,
    )
    assert rec["root_cause_guess"] == "planned_operation_overlap"
    assert rec["evidence_gap"] == "confirm_planned_ops_status_and_capture_post_window_sample"
