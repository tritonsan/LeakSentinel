from __future__ import annotations

from leaksentinel.compliance.standards_mode import evaluate_standards_readiness


def test_standards_readiness_reports_missing_controls() -> None:
    out = evaluate_standards_readiness(
        building_profile={
            "leak_sensor_network": True,
            "auto_shutoff_valve": False,
            "remote_valve_control": True,
        },
        controls_catalog={
            "required_controls": [
                {"id": "leak_sensor_network", "required": True, "title": "Leak Sensor Network"},
                {"id": "auto_shutoff_valve", "required": True, "title": "Automatic Shutoff Valve"},
                {"id": "remote_valve_control", "required": True, "title": "Remote Valve Control"},
            ]
        },
    )
    assert float(out.get("score", 0.0)) < 100.0
    assert len(out.get("missing_controls") or []) == 1
