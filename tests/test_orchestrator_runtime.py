from __future__ import annotations

from leaksentinel.orchestrator import run_scenario


def test_runtime_exposes_evidence_memory_source_local() -> None:
    out = run_scenario(scenario_id="S02", mode="local", write_bundle=False, ablation="full")
    runtime = out.get("_runtime") or {}
    assert runtime.get("evidence_memory_source") == "local"
    assert "similar_incidents" in (out.get("evidence") or {})
