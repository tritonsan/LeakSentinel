from __future__ import annotations

import json
from pathlib import Path

from leaksentinel.eval import benchmark as bench


def test_benchmark_reports_investigate_false_leak_rate(tmp_path: Path, monkeypatch) -> None:
    scenario_pack = tmp_path / "scenario_pack.json"
    scenario_pack.write_text(
        json.dumps(
            {
                "scenarios": [
                    {"scenario_id": "L1", "label": "leak", "track": "core"},
                    {"scenario_id": "I1", "label": "investigate", "track": "core"},
                ]
            }
        ),
        encoding="utf-8",
    )

    def fake_run_scenario(*, scenario_id: str, mode: str, write_bundle: bool, ablation: str):
        if scenario_id == "L1":
            decision = "LEAK_CONFIRMED"
        else:
            decision = "LEAK_CONFIRMED"  # false leak on investigate bucket
        return {"decision": decision, "confidence": 0.9, "_runtime": {"bedrock": {"used": False}}}

    monkeypatch.setattr(bench, "run_scenario", fake_run_scenario)

    res = bench.run_benchmark(
        mode="local",
        scenario_pack_path=scenario_pack,
        ablations=["full"],
        out_dir=tmp_path / "out",
        strict=False,
    )
    s = res.summary["full"]
    inv = s["investigate_bucket"]
    assert inv["leak_confirmed_n"] == 1
    assert float(inv["leak_confirmed_rate"]) == 1.0
