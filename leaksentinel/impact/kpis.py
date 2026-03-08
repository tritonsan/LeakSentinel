from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


CLOSED_STATUSES = {"closed_true_positive", "closed_false_positive"}


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


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


def _read_json_list(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, list):
        return []
    out: List[Dict[str, Any]] = []
    for r in obj:
        if isinstance(r, dict):
            out.append(r)
    return out


def _in_range(ts: Optional[datetime], start: Optional[datetime], end: Optional[datetime]) -> bool:
    if ts is None:
        return False
    if start and ts < start:
        return False
    if end and ts > end:
        return False
    return True


def compute_impact_kpis(
    *,
    incidents_path: Path,
    from_ts: str = "",
    to_ts: str = "",
    zone: str = "",
) -> Dict[str, Any]:
    rows = _read_json_list(incidents_path)
    start = _parse_dt(from_ts)
    end = _parse_dt(to_ts)
    zf = str(zone or "").strip()

    filtered: List[Dict[str, Any]] = []
    for r in rows:
        if zf and str(r.get("zone", "")).strip() != zf:
            continue
        opened = _parse_dt(r.get("opened_at"))
        if (start or end) and not _in_range(opened, start, end):
            continue
        filtered.append(r)

    opened_n = len(filtered)
    closed_n = 0
    provisional_n = 0
    dispatch_deltas: List[float] = []
    close_deltas: List[float] = []

    total_cost = total_water = total_co2 = 0.0
    confirmed_cost = confirmed_water = confirmed_co2 = 0.0
    provisional_cost = provisional_water = provisional_co2 = 0.0

    for r in filtered:
        status = str(r.get("status", "")).strip().lower()
        is_closed = status in CLOSED_STATUSES
        if is_closed:
            closed_n += 1
        else:
            provisional_n += 1

        impact = r.get("impact_snapshot", {}) if isinstance(r.get("impact_snapshot"), dict) else {}
        cost = max(0.0, _to_float(impact.get("cost_saved_usd"), 0.0))
        water = max(0.0, _to_float(impact.get("water_saved_m3"), 0.0))
        co2 = max(0.0, _to_float(impact.get("co2e_kg_avoided"), 0.0))

        total_cost += cost
        total_water += water
        total_co2 += co2

        is_provisional = bool(impact.get("provisional", not is_closed))
        if is_provisional:
            provisional_cost += cost
            provisional_water += water
            provisional_co2 += co2
        else:
            confirmed_cost += cost
            confirmed_water += water
            confirmed_co2 += co2

        opened = _parse_dt(r.get("opened_at"))
        dispatched = _parse_dt(r.get("dispatched_at"))
        closed = _parse_dt(r.get("closed_at"))
        if opened and dispatched and dispatched >= opened:
            dispatch_deltas.append((dispatched - opened).total_seconds() / 60.0)
        if opened and closed and closed >= opened:
            close_deltas.append((closed - opened).total_seconds() / 3600.0)

    avg_dispatch = sum(dispatch_deltas) / len(dispatch_deltas) if dispatch_deltas else 0.0
    avg_close = sum(close_deltas) / len(close_deltas) if close_deltas else 0.0

    return {
        "mode": "impact_kpis_v1",
        "from": from_ts or "",
        "to": to_ts or "",
        "zone": zf,
        "incidents_opened": int(opened_n),
        "incidents_closed": int(closed_n),
        "provisional_incidents": int(provisional_n),
        "estimated_cost_saved_usd_total": round(total_cost, 2),
        "estimated_water_saved_m3_total": round(total_water, 3),
        "co2e_kg_avoided_total": round(total_co2, 3),
        "confirmed_cost_saved_usd_total": round(confirmed_cost, 2),
        "confirmed_water_saved_m3_total": round(confirmed_water, 3),
        "confirmed_co2e_kg_avoided_total": round(confirmed_co2, 3),
        "provisional_cost_saved_usd_total": round(provisional_cost, 2),
        "provisional_water_saved_m3_total": round(provisional_water, 3),
        "provisional_co2e_kg_avoided_total": round(provisional_co2, 3),
        "avg_time_to_dispatch_min": round(avg_dispatch, 2),
        "avg_time_to_close_hours": round(avg_close, 2),
    }
