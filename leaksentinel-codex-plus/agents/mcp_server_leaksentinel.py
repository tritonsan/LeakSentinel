"""LeakSentinel MCP tool contracts (skeleton).

Codex should implement an actual MCP server using the `mcp` package and register these as tools.
"""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

OPS_DB = Path("data/ops_db.json")
MANIFEST = Path("data/manifest/manifest.csv")

def get_ops_records(zone: str, start: str, end: str, op_type: Optional[str]=None) -> Dict[str, Any]:
    ops = json.loads(OPS_DB.read_text(encoding="utf-8")).get("ops", [])
    s = datetime.fromisoformat(start)
    e = datetime.fromisoformat(end)
    out=[]
    for r in ops:
        if r["zone"] != zone: continue
        if op_type and r["type"] != op_type: continue
        rs = datetime.fromisoformat(r["start"]); re = datetime.fromisoformat(r["end"])
        if rs <= e and re >= s: out.append(r)
    return {"count": len(out), "records": out}

def get_manifest_row(scenario_id: str) -> Dict[str, Any]:
    import pandas as pd
    df = pd.read_csv(MANIFEST)
    rows = df[df["scenario_id"] == scenario_id]
    return {"found": (not rows.empty), "row": (rows.iloc[0].to_dict() if not rows.empty else None)}
