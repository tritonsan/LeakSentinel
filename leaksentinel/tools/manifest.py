from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd


def load_scenario(scenarios_path: Path, scenario_id: str) -> Dict[str, Any]:
    pack = json.loads(scenarios_path.read_text(encoding="utf-8"))
    for s in pack.get("scenarios", []):
        if s.get("scenario_id") == scenario_id:
            return s
    raise ValueError(f"scenario_id not found in scenario pack: {scenario_id}")


def load_manifest_row(manifest_path: Path, scenario_id: str) -> Optional[Dict[str, Any]]:
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest not found: {manifest_path}")
    df = pd.read_csv(manifest_path)
    rows = df[df["scenario_id"] == scenario_id]
    if rows.empty:
        return None
    return rows.iloc[0].to_dict()

