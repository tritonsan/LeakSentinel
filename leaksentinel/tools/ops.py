from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def find_planned_ops(*, ops_db_path: Path, zone: str, start: str, end: str, op_type: Optional[str] = None) -> Dict[str, Any]:
    if not ops_db_path.exists():
        return {"planned_op_found": False, "planned_op_ids": [], "records": [], "summary": "Ops DB missing."}

    ops = json.loads(ops_db_path.read_text(encoding="utf-8")).get("ops", [])
    s = _dt(start)
    e = _dt(end)

    out = []
    for r in ops:
        if r.get("zone") != zone:
            continue
        if op_type and r.get("type") != op_type:
            continue
        rs = _dt(r["start"])
        re = _dt(r["end"])
        if rs <= e and re >= s:
            out.append(r)

    return {
        "planned_op_found": bool(out),
        "planned_op_ids": [r.get("planned_op_id") for r in out if r.get("planned_op_id")],
        "records": out,
        "summary": "Planned ops found." if out else "No planned ops in time window.",
        "query": {"zone": zone, "start": start, "end": end, "op_type": op_type},
    }

