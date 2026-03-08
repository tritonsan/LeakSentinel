from __future__ import annotations

import pytest

from leaksentinel.ops.incidents_store import (
    close_incident,
    dispatch_incident,
    field_update_incident,
    get_incident,
    open_incident,
)


def _bundle(*, scenario_id: str, zone: str, decision: str = "LEAK_CONFIRMED") -> dict:
    return {
        "decision": decision,
        "confidence": 0.9,
        "impact_estimate_v2": {"expected_total_impact_usd": 2400.0},
        "scorecard": {
            "estimated_cost_saved_usd": 2400.0,
            "estimated_water_saved_m3": 110.0,
            "estimated_co2e_kg_avoided": 55.0,
        },
        "evidence": {"context": {"scenario_id": scenario_id, "zone": zone}},
    }


def test_incident_lifecycle_true_positive(tmp_path) -> None:
    incidents = tmp_path / "incidents.json"
    inc = open_incident(incidents_path=incidents, bundle=_bundle(scenario_id="S100", zone="zone-1"))
    iid = str(inc["incident_id"])
    assert inc["status"] == "new"

    inc = dispatch_incident(incidents_path=incidents, incident_id=iid, team="crew-1", eta_minutes=25)
    assert inc["status"] == "dispatched"
    assert inc["assignee_team"] == "crew-1"

    inc = field_update_incident(incidents_path=incidents, incident_id=iid, status="on_site", note="arrived")
    assert inc["status"] == "on_site"
    inc = field_update_incident(incidents_path=incidents, incident_id=iid, status="repaired")
    assert inc["status"] == "repaired"
    inc = field_update_incident(incidents_path=incidents, incident_id=iid, status="verification_pending")
    assert inc["status"] == "verification_pending"
    inc = close_incident(incidents_path=incidents, incident_id=iid, closure_type="true_positive", note="fixed", repair_cost_usd=320.0)
    assert inc["status"] == "closed_true_positive"
    assert inc["closure_type"] == "true_positive"
    assert float((inc.get("impact_snapshot") or {}).get("provisional")) == 0.0


def test_incident_invalid_transition_rejected(tmp_path) -> None:
    incidents = tmp_path / "incidents.json"
    inc = open_incident(incidents_path=incidents, bundle=_bundle(scenario_id="S101", zone="zone-2"))
    iid = str(inc["incident_id"])
    inc = dispatch_incident(incidents_path=incidents, incident_id=iid, team="crew-2", eta_minutes=20)
    assert inc["status"] == "dispatched"

    with pytest.raises(ValueError):
        close_incident(incidents_path=incidents, incident_id=iid, closure_type="true_positive", note="too early")


def test_incident_false_positive_close_from_triage(tmp_path) -> None:
    incidents = tmp_path / "incidents.json"
    inc = open_incident(incidents_path=incidents, bundle=_bundle(scenario_id="S102", zone="zone-3", decision="INVESTIGATE"))
    iid = str(inc["incident_id"])
    inc = field_update_incident(incidents_path=incidents, incident_id=iid, status="triage")
    assert inc["status"] == "triage"
    inc = close_incident(incidents_path=incidents, incident_id=iid, closure_type="false_positive", note="planned op")
    assert inc["status"] == "closed_false_positive"
    loaded = get_incident(incidents_path=incidents, incident_id=iid)
    assert loaded["status"] == "closed_false_positive"
