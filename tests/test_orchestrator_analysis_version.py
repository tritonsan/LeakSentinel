from __future__ import annotations

from leaksentinel.orchestrator import run_scenario


def test_analysis_version_v1_omits_v2_fields() -> None:
    out = run_scenario(
        scenario_id="S02",
        mode="local",
        write_bundle=False,
        ablation="full",
        analysis_version="v1",
    )
    assert out.get("analysis_version") == "v1"
    assert "next_evidence_request" in out
    assert "impact_estimate" in out
    assert "counterfactual" in out
    assert "next_evidence_request_v2" not in out
    assert "impact_estimate_v2" not in out
    assert "counterfactual_v2" not in out


def test_include_flags_can_disable_counterfactual_and_impact() -> None:
    out = run_scenario(
        scenario_id="S02",
        mode="local",
        write_bundle=False,
        ablation="full",
        analysis_version="v2",
        include_counterfactuals=False,
        include_impact=False,
    )
    assert out.get("analysis_version") == "v2"
    assert out.get("counterfactual") == {}
    assert out.get("impact_estimate") == {}
    assert out.get("counterfactual_v2") == {}
    assert out.get("impact_estimate_v2") == {}
    assert isinstance(out.get("next_evidence_request_v2"), dict)
