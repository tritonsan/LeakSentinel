from __future__ import annotations

from datetime import datetime
from pathlib import Path

from leaksentinel.tools.pressure_autopilot import build_pressure_plan


def test_pressure_plan_uses_profile_and_respects_bounds(tmp_path: Path) -> None:
    p = tmp_path / "zone-1_profile.csv"
    p.write_text(
        "hour,base_pressure_m,min_setpoint_m,max_setpoint_m\n3,55,35,65\n",
        encoding="utf-8",
    )
    out = build_pressure_plan(
        incident_ts=datetime.fromisoformat("2026-02-05T03:00:00"),
        zone="zone-1",
        flow_summary={"observed": 42.0, "expected": 35.0, "anomaly_score": 1.1},
        decision="LEAK_CONFIRMED",
        profile_path=p,
        min_setpoint_m=35.0,
        max_setpoint_m=70.0,
        target_setpoint_m=52.0,
    )
    assert bool(out["profile_used"]) is True
    assert float(out["recommended_setpoint_m"]) <= float(out["current_pressure_m"])
    assert 35.0 <= float(out["recommended_setpoint_m"]) <= 65.0
