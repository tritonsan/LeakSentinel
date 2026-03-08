from __future__ import annotations

import json

from leaksentinel.impact.kpis import compute_impact_kpis


def test_compute_impact_kpis_aggregates_and_times(tmp_path) -> None:
    incidents_path = tmp_path / "incidents.json"
    incidents = [
        {
            "incident_id": "inc-a",
            "zone": "zone-1",
            "status": "closed_true_positive",
            "opened_at": "2026-02-10T10:00:00Z",
            "dispatched_at": "2026-02-10T10:20:00Z",
            "closed_at": "2026-02-10T12:00:00Z",
            "impact_snapshot": {
                "cost_saved_usd": 2000.0,
                "water_saved_m3": 100.0,
                "co2e_kg_avoided": 50.0,
                "provisional": False,
            },
        },
        {
            "incident_id": "inc-b",
            "zone": "zone-1",
            "status": "dispatched",
            "opened_at": "2026-02-10T11:00:00Z",
            "dispatched_at": "2026-02-10T11:30:00Z",
            "closed_at": "",
            "impact_snapshot": {
                "cost_saved_usd": 500.0,
                "water_saved_m3": 20.0,
                "co2e_kg_avoided": 8.0,
                "provisional": True,
            },
        },
    ]
    incidents_path.write_text(json.dumps(incidents), encoding="utf-8")

    out = compute_impact_kpis(
        incidents_path=incidents_path,
        from_ts="2026-02-10T00:00:00Z",
        to_ts="2026-02-11T00:00:00Z",
        zone="zone-1",
    )
    assert int(out["incidents_opened"]) == 2
    assert int(out["incidents_closed"]) == 1
    assert int(out["provisional_incidents"]) == 1
    assert float(out["estimated_cost_saved_usd_total"]) == 2500.0
    assert float(out["estimated_water_saved_m3_total"]) == 120.0
    assert float(out["co2e_kg_avoided_total"]) == 58.0
    assert float(out["avg_time_to_dispatch_min"]) == 25.0
    assert float(out["avg_time_to_close_hours"]) == 2.0
