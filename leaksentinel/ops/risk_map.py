from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


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
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _read_json(path: Path, default_obj: Any) -> Any:
    if not path.exists():
        return default_obj
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default_obj


def _read_bundle_rows(*, evidence_dir: Path, t0: datetime) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for p in sorted(evidence_dir.glob("*.json")):
        obj = _read_json(p, {})
        if not isinstance(obj, dict):
            continue
        ev = obj.get("evidence", {}) if isinstance(obj.get("evidence"), dict) else {}
        ctx = ev.get("context", {}) if isinstance(ev.get("context"), dict) else {}
        ops = ev.get("ops", {}) if isinstance(ev.get("ops"), dict) else {}
        ts = _parse_dt(ctx.get("timestamp"))
        if not ts or ts < t0:
            continue
        v2 = obj.get("impact_estimate_v2", {}) if isinstance(obj.get("impact_estimate_v2"), dict) else {}
        v1 = obj.get("impact_estimate", {}) if isinstance(obj.get("impact_estimate"), dict) else {}
        impact = _to_float(v2.get("expected_total_impact_usd"), float("nan"))
        if impact != impact:  # NaN
            impact = _to_float(v1.get("avoided_false_dispatch_estimate"), 0.0) + _to_float(v1.get("avoided_leak_loss_estimate"), 0.0)
        rows.append(
            {
                "zone": str(ctx.get("zone", "")).strip(),
                "timestamp": ts,
                "decision": str(obj.get("decision", "")).strip().upper(),
                "confidence": _to_float(obj.get("confidence"), 0.0),
                "impact_usd": max(0.0, impact),
                "continuous_flow_detected": bool((obj.get("continuous_flow_alert") or {}).get("detected"))
                if isinstance(obj.get("continuous_flow_alert"), dict)
                else False,
                "planned_ops_explained": bool(str(obj.get("decision", "")).strip().upper() == "IGNORE_PLANNED_OPS" and bool(ops.get("planned_op_found"))),
            }
        )
    return rows


def _risk_formula(
    *,
    confirmed_rate: float,
    investigate_rate: float,
    continuous_flow_rate: float,
    avg_impact_norm: float,
    planned_ops_explained_rate: float,
) -> float:
    raw = (
        (0.35 * max(0.0, confirmed_rate))
        + (0.20 * max(0.0, investigate_rate))
        + (0.20 * max(0.0, continuous_flow_rate))
        + (0.15 * max(0.0, avg_impact_norm))
        - (0.10 * max(0.0, planned_ops_explained_rate))
    )
    return max(0.0, min(100.0, 100.0 * raw))


def _window_zone_score(
    *,
    rows: List[Dict[str, Any]],
    zone: str,
    start: datetime,
    end: datetime,
    max_impact: float,
) -> float:
    zrows = [r for r in rows if r.get("zone") == zone and start <= r.get("timestamp") <= end]
    if not zrows:
        return 0.0
    n = float(len(zrows))
    leak_n = float(sum(1 for r in zrows if str(r.get("decision")) == "LEAK_CONFIRMED"))
    inv_n = float(sum(1 for r in zrows if str(r.get("decision")) == "INVESTIGATE"))
    cf_n = float(sum(1 for r in zrows if bool(r.get("continuous_flow_detected"))))
    planned_n = float(sum(1 for r in zrows if bool(r.get("planned_ops_explained"))))
    avg_impact = sum(_to_float(r.get("impact_usd"), 0.0) for r in zrows) / n
    impact_norm = avg_impact / max(1.0, max_impact)
    return _risk_formula(
        confirmed_rate=leak_n / n,
        investigate_rate=inv_n / n,
        continuous_flow_rate=cf_n / n,
        avg_impact_norm=impact_norm,
        planned_ops_explained_rate=planned_n / n,
    )


def build_zone_risk_map(
    *,
    evidence_dir: Path,
    incidents_path: Path,
    window_days: int = 30,
    now_ts: Optional[datetime] = None,
) -> Dict[str, Any]:
    if now_ts is None:
        now = datetime.now(timezone.utc)
    else:
        now = now_ts if now_ts.tzinfo else now_ts.replace(tzinfo=timezone.utc)
        now = now.astimezone(timezone.utc)
    wd = max(1, int(window_days))
    t0 = now - timedelta(days=wd)

    rows = _read_bundle_rows(evidence_dir=evidence_dir, t0=t0)
    incident_rows = _read_json(incidents_path, [])
    if not isinstance(incident_rows, list):
        incident_rows = []

    if not rows and not incident_rows:
        return {"ok": True, "window_days": wd, "zones": []}

    zones = set()
    for r in rows:
        z = str(r.get("zone", "")).strip()
        if z:
            zones.add(z)
    for r in incident_rows:
        if not isinstance(r, dict):
            continue
        z = str(r.get("zone", "")).strip()
        if z:
            zones.add(z)

    max_impact = max([_to_float(r.get("impact_usd"), 0.0) for r in rows] or [1.0])
    out_zones: List[Dict[str, Any]] = []

    for z in sorted(zones):
        zrows = [r for r in rows if str(r.get("zone", "")).strip() == z]
        n = len(zrows)
        leak_n = sum(1 for r in zrows if str(r.get("decision", "")) == "LEAK_CONFIRMED")
        inv_n = sum(1 for r in zrows if str(r.get("decision", "")) == "INVESTIGATE")
        cf_n = sum(1 for r in zrows if bool(r.get("continuous_flow_detected")))
        planned_n = sum(1 for r in zrows if bool(r.get("planned_ops_explained")))
        avg_conf = (sum(_to_float(r.get("confidence"), 0.0) for r in zrows) / float(n)) if n > 0 else 0.0
        avg_impact = (sum(_to_float(r.get("impact_usd"), 0.0) for r in zrows) / float(n)) if n > 0 else 0.0
        impact_norm = avg_impact / max(1.0, max_impact)

        score = _risk_formula(
            confirmed_rate=(float(leak_n) / float(n)) if n else 0.0,
            investigate_rate=(float(inv_n) / float(n)) if n else 0.0,
            continuous_flow_rate=(float(cf_n) / float(n)) if n else 0.0,
            avg_impact_norm=impact_norm,
            planned_ops_explained_rate=(float(planned_n) / float(n)) if n else 0.0,
        )

        last_start = now - timedelta(days=7)
        prev_start = now - timedelta(days=14)
        prev_end = now - timedelta(days=7)
        last_score = _window_zone_score(rows=rows, zone=z, start=last_start, end=now, max_impact=max_impact)
        prev_score = _window_zone_score(rows=rows, zone=z, start=prev_start, end=prev_end, max_impact=max_impact)
        delta = last_score - prev_score
        if delta > 5.0:
            trend = "up"
        elif delta < -5.0:
            trend = "down"
        else:
            trend = "flat"

        incident_n = 0
        repeat_fp_n = 0
        for ir in incident_rows:
            if not isinstance(ir, dict):
                continue
            if str(ir.get("zone", "")).strip() != z:
                continue
            opened = _parse_dt(ir.get("opened_at"))
            if opened and opened < t0:
                continue
            incident_n += 1
            if str(ir.get("status", "")).strip().lower() == "closed_false_positive":
                repeat_fp_n += 1

        out_zones.append(
            {
                "zone": z,
                "risk_score_0_100": round(score, 2),
                "trend": trend,
                "incidents_n": int(incident_n),
                "leak_confirmed_n": int(leak_n),
                "repeat_fp_n": int(repeat_fp_n),
                "avg_confidence": round(avg_conf, 3),
            }
        )

    out_zones.sort(key=lambda x: (-_to_float(x.get("risk_score_0_100"), 0.0), str(x.get("zone", ""))))
    return {"ok": True, "window_days": wd, "zones": out_zones}
