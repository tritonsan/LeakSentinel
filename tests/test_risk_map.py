from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from leaksentinel.ops.risk_map import build_zone_risk_map


def _write_bundle(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj), encoding="utf-8")


def test_build_zone_risk_map_outputs_sorted_zones(tmp_path) -> None:
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    incidents_path = tmp_path / "incidents.json"
    incidents_path.write_text(
        json.dumps(
            [
                {
                    "incident_id": "inc-1",
                    "zone": "zone-a",
                    "status": "closed_false_positive",
                    "opened_at": "2026-02-10T10:00:00Z",
                }
            ]
        ),
        encoding="utf-8",
    )

    _write_bundle(
        evidence_dir / "S1_zone-a_2026-02-10T10-00-00.json",
        {
            "decision": "LEAK_CONFIRMED",
            "confidence": 0.92,
            "impact_estimate_v2": {"expected_total_impact_usd": 4000.0},
            "continuous_flow_alert": {"detected": True},
            "evidence": {
                "context": {"scenario_id": "S1", "zone": "zone-a", "timestamp": "2026-02-10T10:00:00"},
                "ops": {"planned_op_found": False},
            },
        },
    )
    _write_bundle(
        evidence_dir / "S2_zone-b_2026-02-10T09-00-00.json",
        {
            "decision": "IGNORE_PLANNED_OPS",
            "confidence": 0.55,
            "impact_estimate_v2": {"expected_total_impact_usd": 1000.0},
            "continuous_flow_alert": {"detected": False},
            "evidence": {
                "context": {"scenario_id": "S2", "zone": "zone-b", "timestamp": "2026-02-10T09:00:00"},
                "ops": {"planned_op_found": True},
            },
        },
    )

    out = build_zone_risk_map(
        evidence_dir=evidence_dir,
        incidents_path=incidents_path,
        window_days=30,
        now_ts=datetime.fromisoformat("2026-02-12T00:00:00"),
    )
    assert out["ok"] is True
    zones = out["zones"]
    assert len(zones) >= 2
    assert zones[0]["zone"] == "zone-a"
    assert float(zones[0]["risk_score_0_100"]) >= float(zones[1]["risk_score_0_100"])
    assert "trend" in zones[0]
