from __future__ import annotations

from leaksentinel.orchestrator import run_scenario


def test_ops_timeout_uses_safe_fallback(monkeypatch) -> None:
    def fail_ops(*args, **kwargs):
        raise TimeoutError("ops source timeout")

    monkeypatch.setattr("leaksentinel.orchestrator.find_planned_ops", fail_ops)
    out = run_scenario(scenario_id="S02", mode="local", write_bundle=False, ablation="full")
    runtime = out.get("_runtime", {}) if isinstance(out.get("_runtime"), dict) else {}
    assert bool(runtime.get("ops_fallback")) is True
    assert str(out.get("decision", "")).upper() in {"INVESTIGATE", "IGNORE_PLANNED_OPS", "LEAK_CONFIRMED"}


def test_bedrock_unavailable_falls_back_safely(monkeypatch) -> None:
    def fail_client(*args, **kwargs):
        raise RuntimeError("bedrock unavailable")

    monkeypatch.setattr("leaksentinel.orchestrator.make_bedrock_runtime_client", fail_client)
    out = run_scenario(scenario_id="S02", mode="bedrock", write_bundle=False, ablation="full")
    runtime = out.get("_runtime", {}) if isinstance(out.get("_runtime"), dict) else {}
    bedrock = runtime.get("bedrock", {}) if isinstance(runtime.get("bedrock"), dict) else {}
    fallback = bedrock.get("fallback", {}) if isinstance(bedrock.get("fallback"), dict) else {}
    assert bool(fallback.get("decision")) is True
    assert str(out.get("decision", "")).strip() != ""

