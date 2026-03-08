from __future__ import annotations

import json
from pathlib import Path

from leaksentinel.eval import benchmark as bench


def test_run_benchmark_emits_track_summary(tmp_path: Path, monkeypatch) -> None:
    scenario_pack = tmp_path / "scenario_pack.json"
    scenario_pack.write_text(
        json.dumps(
            {
                "scenarios": [
                    {"scenario_id": "A1", "label": "leak", "track": "core"},
                    {"scenario_id": "A2", "label": "normal", "track": "core"},
                    {"scenario_id": "B1", "label": "leak", "track": "real_challenge"},
                    {"scenario_id": "B2", "label": "investigate", "track": "real_challenge"},
                ]
            }
        ),
        encoding="utf-8",
    )

    def fake_run_scenario(*, scenario_id: str, mode: str, write_bundle: bool, ablation: str):
        if scenario_id in {"A1", "B1"}:
            decision = "LEAK_CONFIRMED"
        else:
            decision = "INVESTIGATE"
        return {"decision": decision, "confidence": 0.8, "_runtime": {"bedrock": {"used": mode == "bedrock"}}}

    monkeypatch.setattr(bench, "run_scenario", fake_run_scenario)

    res = bench.run_benchmark(
        mode="local",
        scenario_pack_path=scenario_pack,
        ablations=["full"],
        out_dir=tmp_path / "out",
        strict=False,
    )

    assert "full" in res.summary
    by_track = res.summary["full"].get("by_track", {})
    assert "core" in by_track
    assert "real_challenge" in by_track
    assert by_track["core"]["n_total"] == 2
    assert by_track["real_challenge"]["n_total"] == 2
