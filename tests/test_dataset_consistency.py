from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from leaksentinel.eval.benchmark import validate_dataset
from leaksentinel.orchestrator import _ops_window
from leaksentinel.tools.ops import find_planned_ops


def test_scenario_pack_ops_consistency() -> None:
    """
    Minimum consistency rules:
    - planned_ops scenarios must overlap a planned op id.
    - normal/investigate scenarios should not overlap planned ops (otherwise the "normal" label is ambiguous).
    - leak scenarios are allowed to overlap planned ops (leak override case).
    """
    scenarios_path = Path("data/scenarios/scenario_pack.json")
    ops_db_path = Path("data/ops_db.json")

    pack = json.loads(scenarios_path.read_text(encoding="utf-8"))
    scenarios = pack.get("scenarios", [])
    assert scenarios, "scenario_pack.json must contain scenarios"

    for s in scenarios:
        sid = str(s.get("scenario_id"))
        zone = str(s.get("zone"))
        ts = str(s.get("incident_timestamp"))
        wm = int(s.get("window_minutes"))
        planned_id = str(s.get("planned_op_id") or "").strip()

        start, end = _ops_window(datetime.fromisoformat(ts), wm)
        out = find_planned_ops(ops_db_path=ops_db_path, zone=zone, start=start, end=end)
        found = bool(out.get("planned_op_found"))
        found_ids = set(str(x) for x in (out.get("planned_op_ids") or []) if x)

        lab = str(s.get("label") or "").strip().lower()
        if planned_id:
            assert found, f"{sid}: expected planned ops overlap for planned_op_id={planned_id}"
            assert planned_id in found_ids, f"{sid}: expected planned_op_id={planned_id} in found_ids={sorted(found_ids)}"
        elif lab in ("normal", "investigate"):
            assert not found, f"{sid}: label={lab} should not overlap planned ops, but found_ids={sorted(found_ids)}"


def test_holdout_v3_is_consistent_and_new_real_challenge_specs_are_unique() -> None:
    scenario_pack = Path("data/scenarios/scenario_pack_holdout_v3.json")
    manifest = Path("data/manifest/manifest_holdout_v3.csv")
    ops_db = Path("data/ops_db.json")

    warnings = validate_dataset(
        scenario_pack_path=scenario_pack,
        manifest_path=manifest,
        ops_db_path=ops_db,
    )
    assert warnings == []

    pack = json.loads(scenario_pack.read_text(encoding="utf-8"))
    new_ids = {f"S{i}" for i in range(18, 42)}
    spec_names = []
    with manifest.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sid = str(row.get("scenario_id") or "")
            if sid in new_ids:
                spec_names.append(Path(str(row.get("spectrogram_file") or "")).name)
    assert len(spec_names) == len(new_ids)
    assert len(set(spec_names)) == len(spec_names)
