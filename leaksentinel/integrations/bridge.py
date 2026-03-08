from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from leaksentinel.impact.kpis import compute_impact_kpis


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_dt(v: Any) -> Optional[datetime]:
    s = str(v or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _read_json(path: Path, default_obj: Any) -> Any:
    if not path.exists():
        return default_obj
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default_obj


def _read_json_list(path: Path) -> List[Dict[str, Any]]:
    obj = _read_json(path, [])
    if not isinstance(obj, list):
        return []
    out: List[Dict[str, Any]] = []
    for r in obj:
        if isinstance(r, dict):
            out.append(r)
    return out


def list_connectors(*, connectors_path: Path) -> List[Dict[str, Any]]:
    obj = _read_json(connectors_path, {})
    if isinstance(obj, dict):
        rows = obj.get("connectors", [])
    elif isinstance(obj, list):
        rows = obj
    else:
        rows = []
    out: List[Dict[str, Any]] = []
    for r in rows:
        if isinstance(r, dict):
            out.append(r)
    return out


def ingest_event(
    *,
    events_path: Path,
    source: str,
    event_type: str,
    zone: str = "",
    timestamp: str = "",
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    src = str(source or "").strip()
    et = str(event_type or "").strip()
    if not src:
        raise ValueError("source is required")
    if not et:
        raise ValueError("event_type is required")
    ts = str(timestamp or "").strip() or _utc_now()
    normalized = {
        "normalized_event_id": f"evt-{uuid4().hex[:12]}",
        "ingested_at": _utc_now(),
        "source": src,
        "event_type": et,
        "zone": str(zone or "").strip(),
        "timestamp": ts,
        "payload": dict(payload or {}),
    }
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with events_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(normalized, ensure_ascii=True) + "\n")
    return normalized


def _rows_in_range(rows: List[Dict[str, Any]], *, from_ts: str = "", to_ts: str = "", zone: str = "") -> List[Dict[str, Any]]:
    start = _parse_dt(from_ts)
    end = _parse_dt(to_ts)
    zf = str(zone or "").strip()
    out: List[Dict[str, Any]] = []
    for r in rows:
        if zf and str(r.get("zone", "")).strip() != zf:
            continue
        opened = _parse_dt(r.get("opened_at"))
        if start and (opened is None or opened < start):
            continue
        if end and (opened is None or opened > end):
            continue
        out.append(r)
    return out


def _flat_csv_row(obj: Dict[str, Any]) -> Dict[str, Any]:
    row: Dict[str, Any] = {}
    for k, v in obj.items():
        if isinstance(v, (dict, list)):
            row[str(k)] = json.dumps(v, ensure_ascii=True)
        else:
            row[str(k)] = v
    return row


def export_data(
    *,
    export_format: str,
    entity: str,
    from_ts: str,
    to_ts: str,
    zone: str,
    incidents_path: Path,
    exports_dir: Path,
) -> Dict[str, Any]:
    fmt = str(export_format or "json").strip().lower()
    ent = str(entity or "incidents").strip().lower()
    if fmt not in {"json", "csv"}:
        raise ValueError("format must be csv or json")
    if ent not in {"incidents", "kpis"}:
        raise ValueError("entity must be incidents or kpis")

    exports_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = exports_dir / f"{ent}_{ts}.{fmt}"

    if ent == "incidents":
        rows = _rows_in_range(_read_json_list(incidents_path), from_ts=from_ts, to_ts=to_ts, zone=zone)
        if fmt == "json":
            out_path.write_text(json.dumps({"items": rows}, indent=2), encoding="utf-8")
        else:
            csv_rows = [_flat_csv_row(r) for r in rows]
            cols: List[str] = sorted({k for r in csv_rows for k in r.keys()})
            with out_path.open("w", newline="", encoding="utf-8") as f:
                wr = csv.DictWriter(f, fieldnames=cols)
                wr.writeheader()
                for r in csv_rows:
                    wr.writerow(r)
        return {
            "ok": True,
            "entity": ent,
            "format": fmt,
            "rows": int(len(rows)),
            "path": str(out_path),
        }

    kpis = compute_impact_kpis(
        incidents_path=incidents_path,
        from_ts=from_ts,
        to_ts=to_ts,
        zone=zone,
    )
    if fmt == "json":
        out_path.write_text(json.dumps({"impact_kpis": kpis}, indent=2), encoding="utf-8")
    else:
        row = _flat_csv_row(kpis)
        with out_path.open("w", newline="", encoding="utf-8") as f:
            wr = csv.DictWriter(f, fieldnames=list(row.keys()))
            wr.writeheader()
            wr.writerow(row)
    return {
        "ok": True,
        "entity": ent,
        "format": fmt,
        "rows": 1,
        "path": str(out_path),
    }
