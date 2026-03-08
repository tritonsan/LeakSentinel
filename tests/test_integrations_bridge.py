from __future__ import annotations

import json
from pathlib import Path

from leaksentinel.integrations.bridge import export_data, ingest_event, list_connectors


def test_list_connectors_and_ingest_event(tmp_path: Path) -> None:
    connectors = tmp_path / "connectors.json"
    connectors.write_text(
        json.dumps(
            {
                "connectors": [
                    {"id": "c1", "type": "webhook_in", "enabled": True},
                    {"id": "c2", "type": "csv_drop", "enabled": False},
                ]
            }
        ),
        encoding="utf-8",
    )
    rows = list_connectors(connectors_path=connectors)
    assert len(rows) == 2

    events = tmp_path / "events.jsonl"
    evt = ingest_event(
        events_path=events,
        source="scada",
        event_type="pressure_drop",
        zone="zone-1",
        payload={"delta": 12},
    )
    assert str(evt.get("source")) == "scada"
    assert events.exists()
    lines = [x for x in events.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(lines) == 1


def test_export_data_incidents_and_kpis(tmp_path: Path) -> None:
    incidents = tmp_path / "incidents.json"
    incidents.write_text(
        json.dumps(
            [
                {
                    "incident_id": "inc-1",
                    "zone": "zone-1",
                    "status": "closed_true_positive",
                    "opened_at": "2026-02-10T10:00:00Z",
                    "dispatched_at": "2026-02-10T10:10:00Z",
                    "closed_at": "2026-02-10T12:00:00Z",
                    "impact_snapshot": {
                        "cost_saved_usd": 1500.0,
                        "water_saved_m3": 70.0,
                        "co2e_kg_avoided": 30.0,
                        "provisional": False,
                    },
                }
            ]
        ),
        encoding="utf-8",
    )
    exports = tmp_path / "exports"

    out_inc = export_data(
        export_format="csv",
        entity="incidents",
        from_ts="",
        to_ts="",
        zone="",
        incidents_path=incidents,
        exports_dir=exports,
    )
    assert out_inc["ok"] is True
    assert Path(out_inc["path"]).exists()

    out_kpi = export_data(
        export_format="json",
        entity="kpis",
        from_ts="",
        to_ts="",
        zone="zone-1",
        incidents_path=incidents,
        exports_dir=exports,
    )
    assert out_kpi["ok"] is True
    payload = json.loads(Path(out_kpi["path"]).read_text(encoding="utf-8"))
    assert "impact_kpis" in payload
