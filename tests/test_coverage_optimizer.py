from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from leaksentinel.ops.coverage_optimizer import build_coverage_plan


def _bundle(*, sid: str, decision: str, conf: float, score: str) -> dict:
    return {
        "decision": decision,
        "confidence": conf,
        "recommended_action": "Inspect",
        "continuous_flow_alert": {"detected": True, "severity": score},
        "evidence": {
            "context": {"scenario_id": sid, "zone": "zone-1", "timestamp": "2026-02-05T03:00:00"},
            "ops": {"planned_op_found": False},
        },
        "next_evidence_request_v2": {"priority": "high"},
        "counterfactual_v2": {"decision_delta": {"flipped": False}},
    }


def test_build_coverage_plan_ranks_and_assigns(tmp_path: Path) -> None:
    p1 = tmp_path / "b1.json"
    p2 = tmp_path / "b2.json"
    p1.write_text(json.dumps(_bundle(sid="S-high", decision="LEAK_CONFIRMED", conf=0.9, score="high")), encoding="utf-8")
    p2.write_text(json.dumps(_bundle(sid="S-mid", decision="INVESTIGATE", conf=0.6, score="low")), encoding="utf-8")

    out = build_coverage_plan(
        evidence_dir=tmp_path,
        horizon_hours=48,
        max_crews=1,
        now_ts=datetime.fromisoformat("2026-02-06T00:00:00"),
    )
    assert out["ok"] is True
    assert int(out["summary"]["dispatch_n"]) == 1
    assert len(out["dispatch_queue"]) == 1
    assert out["dispatch_queue"][0]["scenario_id"] == "S-high"
