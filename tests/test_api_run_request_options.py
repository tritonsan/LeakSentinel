from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import services.api.main as api_main


def test_run_endpoint_passes_analysis_options(monkeypatch) -> None:
    captured: dict = {}

    def fake_run_scenario(
        *,
        scenario_id: str,
        mode: str,
        write_bundle: bool,
        analysis_version: str,
        include_counterfactuals: bool,
        include_impact: bool,
        include_flow_agent: bool,
        include_pressure_plan: bool,
        include_scorecard: bool,
        include_standards: bool,
        judge_mode: bool,
    ) -> dict:
        captured.update(
            {
                "scenario_id": scenario_id,
                "mode": mode,
                "write_bundle": write_bundle,
                "analysis_version": analysis_version,
                "include_counterfactuals": include_counterfactuals,
                "include_impact": include_impact,
                "include_flow_agent": include_flow_agent,
                "include_pressure_plan": include_pressure_plan,
                "include_scorecard": include_scorecard,
                "include_standards": include_standards,
                "judge_mode": judge_mode,
            }
        )
        return {"ok": True, "decision": "INVESTIGATE", "confidence": 0.5}

    monkeypatch.setattr(api_main, "run_scenario", fake_run_scenario)
    client = TestClient(api_main.app)
    resp = client.post(
        "/run",
        json={
            "scenario_id": "S02",
            "mode": "local",
            "analysis_version": "v1",
            "include_counterfactuals": False,
            "include_impact": False,
            "include_flow_agent": False,
            "include_pressure_plan": False,
            "include_scorecard": False,
            "include_standards": False,
        },
    )
    assert resp.status_code == 200
    assert captured == {
        "scenario_id": "S02",
        "mode": "local",
        "write_bundle": True,
        "analysis_version": "v1",
        "include_counterfactuals": False,
        "include_impact": False,
        "include_flow_agent": False,
        "include_pressure_plan": False,
        "include_scorecard": False,
        "include_standards": False,
        "judge_mode": False,
    }


def test_run_endpoint_passes_judge_mode(monkeypatch) -> None:
    captured: dict = {}

    def fake_run_scenario(**kwargs) -> dict:
        captured.update(kwargs)
        return {"ok": True, "judge_compliance": {"enabled": True, "pass": True}}

    monkeypatch.setattr(api_main, "run_scenario", fake_run_scenario)
    client = TestClient(api_main.app)
    resp = client.post(
        "/run",
        json={
            "scenario_id": "S02",
            "mode": "local",
            "judge_mode": True,
        },
    )
    assert resp.status_code == 200
    assert bool(captured.get("judge_mode")) is True
