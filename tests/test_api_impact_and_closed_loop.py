from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import services.api.main as api_main


def test_impact_compare_endpoint_inline_bundle() -> None:
    client = TestClient(api_main.app)
    resp = client.post(
        "/impact/compare",
        json={
            "persona": "utility",
            "bundles": [
                {
                    "impact_estimate_v2": {"expected_total_impact_usd": 2500.0},
                    "scorecard": {"estimated_water_saved_m3": 120.0, "estimated_co2e_kg_avoided": 54.0},
                    "evidence": {"context": {"scenario_id": "S-impact-1"}},
                }
            ]
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "impact_proof_v1" in body
    proof = body["impact_proof_v1"]
    assert proof["mode"] == "impact_compare_v1"
    assert str((proof.get("persona_applied") or {}).get("persona")) == "utility"
    assert "impact_bands" in proof
    assert float(proof["cost_saved_usd"]) >= 2500.0


def test_closed_loop_simulate_endpoint(monkeypatch) -> None:
    def fake_simulate_closed_loop(*, scenario_id: str, mode: str, field_verdict: str, max_crews: int, horizon_hours: int):
        return {
            "mode": "closed_loop_simulation_v1",
            "scenario_id": scenario_id,
            "loop_completed": True,
            "time_to_action_min": 12.0,
            "feedback_applied": field_verdict == "rejected_false_positive",
            "feedback_effective": True,
            "timeline": [{"step": "detect", "status": "completed"}],
            "decision_change_summary": {"decision_changed": True},
        }

    monkeypatch.setattr(api_main, "simulate_closed_loop", fake_simulate_closed_loop)
    client = TestClient(api_main.app)
    resp = client.post(
        "/ops/closed-loop-simulate",
        json={"scenario_id": "S02", "mode": "local", "field_verdict": "rejected_false_positive"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    summary = body["closed_loop_summary_v1"]
    assert summary["loop_completed"] is True
    assert summary["feedback_applied"] is True
    assert isinstance(summary.get("timeline"), list)
