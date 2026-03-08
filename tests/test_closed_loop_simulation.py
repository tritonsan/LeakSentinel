from __future__ import annotations

from leaksentinel.ops import closed_loop as cls


def test_closed_loop_simulate_runs_and_returns_summary(monkeypatch) -> None:
    calls = {"n": 0}

    def fake_run_scenario(*, scenario_id: str, mode: str, write_bundle: bool, analysis_version: str, ablation: str):
        calls["n"] += 1
        return {
            "decision": "LEAK_CONFIRMED",
            "confidence": 0.85 if calls["n"] == 1 else 0.7,
            "_bundle_path": "data/evidence_bundles/fake.json",
        }

    def fake_coverage_plan(*, evidence_dir, horizon_hours: int, max_crews: int, zones):
        return {
            "dispatch_queue": [
                {
                    "scenario_id": "S02",
                    "priority_score": 90.0,
                }
            ]
        }

    def fake_feedback(**kwargs):
        return {"feedback_id": "fb-test"}

    monkeypatch.setattr(cls, "run_scenario", fake_run_scenario)
    monkeypatch.setattr(cls, "build_coverage_plan", fake_coverage_plan)
    monkeypatch.setattr(cls, "create_feedback_record", fake_feedback)

    out = cls.simulate_closed_loop(scenario_id="S02", mode="local", field_verdict="rejected_false_positive")
    assert out["mode"] == "closed_loop_simulation_v1"
    assert out["loop_completed"] is True
    assert out["feedback_applied"] is True
    assert out["learning_record_id"] == "fb-test"
    assert isinstance(out.get("timeline"), list)
    assert isinstance(out.get("decision_change_summary"), dict)
