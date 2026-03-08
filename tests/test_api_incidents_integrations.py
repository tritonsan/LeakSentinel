from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import services.api.main as api_main


def _fake_settings(tmp_path: Path) -> SimpleNamespace:
    data = tmp_path / "data"
    evidence = data / "evidence_bundles"
    evidence.mkdir(parents=True, exist_ok=True)
    ops_dir = data / "ops"
    ops_dir.mkdir(parents=True, exist_ok=True)
    integrations_dir = data / "integrations"
    integrations_dir.mkdir(parents=True, exist_ok=True)
    exports_dir = data / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    connectors = integrations_dir / "connectors.json"
    connectors.write_text(json.dumps({"connectors": [{"id": "c1", "type": "webhook_in", "enabled": True}]}), encoding="utf-8")
    (ops_dir / "incidents.json").write_text("[]", encoding="utf-8")

    return SimpleNamespace(
        paths=SimpleNamespace(
            evidence_dir=evidence,
            incidents_path=ops_dir / "incidents.json",
            connectors_path=connectors,
            integration_events_path=integrations_dir / "events.jsonl",
            exports_dir=exports_dir,
        )
    )


def test_api_incidents_kpis_risk_and_integrations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _fake_settings(tmp_path)

    bundle_path = settings.paths.evidence_dir / "S201_zone-1_2026-02-10T10-00-00.json"
    bundle_path.write_text(
        json.dumps(
            {
                "decision": "INVESTIGATE",
                "confidence": 0.62,
                "impact_estimate_v2": {"expected_total_impact_usd": 1200.0},
                "scorecard": {"estimated_cost_saved_usd": 1200.0, "estimated_water_saved_m3": 60.0, "estimated_co2e_kg_avoided": 22.0},
                "continuous_flow_alert": {"detected": True},
                "evidence": {
                    "context": {"scenario_id": "S201", "zone": "zone-1", "timestamp": "2026-02-10T10:00:00"},
                    "ops": {"planned_op_found": False},
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(api_main, "AppSettings", lambda mode="local": settings)
    client = TestClient(api_main.app)

    r_open = client.post("/ops/incidents/open", json={"scenario_id": "S201", "mode": "local"})
    assert r_open.status_code == 200
    incident = r_open.json()["incident"]
    iid = str(incident["incident_id"])
    assert incident["status"] == "new"

    r_dispatch = client.post(f"/ops/incidents/{iid}/dispatch", json={"team": "crew-7", "eta_minutes": 20})
    assert r_dispatch.status_code == 200
    assert r_dispatch.json()["incident"]["status"] == "dispatched"

    r_update = client.post(f"/ops/incidents/{iid}/field-update", json={"status": "on_site", "note": "arrived", "evidence_added": True})
    assert r_update.status_code == 200
    assert r_update.json()["incident"]["status"] == "on_site"

    r_close = client.post(
        f"/ops/incidents/{iid}/close",
        json={"closure_type": "false_positive", "note": "planned work overlap", "repair_cost_usd": 0.0},
    )
    assert r_close.status_code == 200
    assert r_close.json()["incident"]["status"] == "closed_false_positive"

    r_list = client.get("/ops/incidents")
    assert r_list.status_code == 200
    assert int(r_list.json()["count"]) == 1

    r_kpi = client.get("/impact/kpis")
    assert r_kpi.status_code == 200
    assert int((r_kpi.json()["impact_kpis"] or {}).get("incidents_closed", 0)) == 1

    r_risk = client.get("/ops/risk-map", params={"window_days": 30})
    assert r_risk.status_code == 200
    zones = ((r_risk.json() or {}).get("risk_map") or {}).get("zones", [])
    assert len(zones) >= 1

    r_connectors = client.get("/integrations/connectors")
    assert r_connectors.status_code == 200
    assert int(r_connectors.json().get("count", 0)) == 1

    r_evt = client.post(
        "/integrations/events",
        json={"source": "scada", "event_type": "pressure_drop", "zone": "zone-1", "payload": {"delta": 12}},
    )
    assert r_evt.status_code == 200
    assert str((r_evt.json()["event"] or {}).get("source")) == "scada"

    r_exp = client.post(
        "/integrations/export",
        json={"format": "json", "entity": "incidents", "from_ts": "", "to_ts": "", "zone": ""},
    )
    assert r_exp.status_code == 200
    exp_path = Path((r_exp.json()["export"] or {}).get("path", ""))
    assert exp_path.exists()
