from __future__ import annotations

from leaksentinel.orchestrator import run_scenario


def test_judge_mode_emits_compliance_block() -> None:
    out = run_scenario(
        scenario_id="S02",
        mode="local",
        write_bundle=False,
        ablation="full",
        analysis_version="v2",
        judge_mode=True,
    )
    jc = out.get("judge_compliance", {})
    assert isinstance(jc, dict)
    assert bool(jc.get("enabled")) is True
    assert "pass" in jc
    assert "missing_fields" in jc
    assert "failed_checks" in jc

