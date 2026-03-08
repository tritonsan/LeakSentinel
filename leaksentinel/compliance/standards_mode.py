from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def load_json_or_default(path: Path, default_obj: Dict[str, Any]) -> Dict[str, Any]:
    if not path.exists():
        return dict(default_obj)
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else dict(default_obj)
    except Exception:
        return dict(default_obj)


def evaluate_standards_readiness(
    *,
    building_profile: Dict[str, Any],
    controls_catalog: Dict[str, Any],
) -> Dict[str, Any]:
    controls = controls_catalog.get("required_controls", []) if isinstance(controls_catalog, dict) else []
    if not isinstance(controls, list):
        controls = []

    missing: List[Dict[str, Any]] = []
    met_n = 0
    for c in controls:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("id", "") or "").strip()
        if not cid:
            continue
        required = bool(c.get("required", True))
        present = bool((building_profile or {}).get(cid, False))
        if required and not present:
            missing.append(
                {
                    "id": cid,
                    "title": str(c.get("title", cid)),
                    "description": str(c.get("description", "")),
                    "priority": str(c.get("priority", "medium")),
                }
            )
        elif required and present:
            met_n += 1

    required_n = max(1, sum(1 for c in controls if isinstance(c, dict) and bool(c.get("required", True))))
    score = (met_n / float(required_n)) * 100.0
    level = "red"
    if score >= 80.0:
        level = "green"
    elif score >= 50.0:
        level = "amber"

    next_actions = []
    for m in sorted(missing, key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(str(x.get("priority", "medium")), 1))[:5]:
        next_actions.append(f"Implement {m.get('title')} ({m.get('id')}).")
    if not next_actions:
        next_actions.append("Maintain current controls and verify quarterly.")

    return {
        "score": round(float(score), 2),
        "level": level,
        "required_controls_n": int(required_n),
        "met_controls_n": int(met_n),
        "missing_controls": missing,
        "next_actions": next_actions,
        "mode": "standards_readiness_v1",
    }
