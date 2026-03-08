from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import services.api.main as api_main


def test_ops_coverage_plan_endpoint(tmp_path: Path) -> None:
    bundle = {
        "decision": "LEAK_CONFIRMED",
        "confidence": 0.9,
        "recommended_action": "Dispatch",
        "continuous_flow_alert": {"detected": True, "severity": "high"},
        "evidence": {"context": {"scenario_id": "S1", "zone": "zone-1", "timestamp": "2026-02-05T03:00:00"}, "ops": {"planned_op_found": False}},
        "next_evidence_request_v2": {"priority": "high"},
        "counterfactual_v2": {"decision_delta": {"flipped": False}},
    }
    (tmp_path / "b1.json").write_text(json.dumps(bundle), encoding="utf-8")

    client = TestClient(api_main.app)
    resp = client.post(
        "/ops/coverage-plan",
        json={"horizon_hours": 48, "max_crews": 1, "evidence_dir": str(tmp_path)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert int(body["summary"]["dispatch_n"]) == 1


def test_standards_check_endpoint() -> None:
    client = TestClient(api_main.app)
    resp = client.post(
        "/standards/check",
        json={
            "building_profile": {"leak_sensor_network": True, "auto_shutoff_valve": False},
            "controls_catalog": {
                "required_controls": [
                    {"id": "leak_sensor_network", "required": True, "title": "Leak Sensor Network"},
                    {"id": "auto_shutoff_valve", "required": True, "title": "Automatic Shutoff Valve"},
                ]
            },
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "standards_readiness" in body
