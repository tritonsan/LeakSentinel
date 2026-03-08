from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4


INCIDENT_STATUSES = (
    "new",
    "triage",
    "dispatched",
    "on_site",
    "repaired",
    "verification_pending",
    "closed_true_positive",
    "closed_false_positive",
)

CLOSED_STATUSES = {"closed_true_positive", "closed_false_positive"}

ALLOWED_TRANSITIONS = {
    "new": {"triage", "dispatched", "closed_false_positive"},
    "triage": {"dispatched", "closed_false_positive"},
    "dispatched": {"on_site", "closed_false_positive"},
    "on_site": {"repaired", "closed_false_positive"},
    "repaired": {"verification_pending"},
    "verification_pending": {"closed_true_positive"},
    "closed_true_positive": set(),
    "closed_false_positive": set(),
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _read_json_list(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, list):
        raise ValueError(f"Incidents file root must be array: {path}")
    out: List[Dict[str, Any]] = []
    for r in obj:
        if isinstance(r, dict):
            out.append(r)
    return out


def _write_json_list(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    tmp.replace(path)


def _build_impact_snapshot(bundle: Dict[str, Any]) -> Dict[str, Any]:
    v2 = bundle.get("impact_estimate_v2", {}) if isinstance(bundle.get("impact_estimate_v2"), dict) else {}
    v1 = bundle.get("impact_estimate", {}) if isinstance(bundle.get("impact_estimate"), dict) else {}
    sc = bundle.get("scorecard", {}) if isinstance(bundle.get("scorecard"), dict) else {}

    total = _to_float(v2.get("expected_total_impact_usd"), float("nan"))
    if total != total:  # NaN
        total = _to_float(v1.get("avoided_false_dispatch_estimate"), 0.0) + _to_float(v1.get("avoided_leak_loss_estimate"), 0.0)
    total = max(0.0, total)

    cost_saved = max(0.0, _to_float(sc.get("estimated_cost_saved_usd"), total))
    water_saved = max(0.0, _to_float(sc.get("estimated_water_saved_m3"), 0.0))
    co2_saved = max(0.0, _to_float(sc.get("estimated_co2e_kg_avoided"), 0.0))

    return {
        "cost_saved_usd": round(cost_saved, 2),
        "water_saved_m3": round(water_saved, 3),
        "co2e_kg_avoided": round(co2_saved, 3),
        "provisional": True,
    }


def _validate_transition(current_status: str, new_status: str) -> None:
    cur = str(current_status or "").strip().lower()
    nxt = str(new_status or "").strip().lower()
    if cur not in ALLOWED_TRANSITIONS:
        raise ValueError(f"Unknown current status: {current_status}")
    if nxt not in ALLOWED_TRANSITIONS:
        raise ValueError(f"Unknown target status: {new_status}")
    if cur == nxt:
        return
    if nxt not in ALLOWED_TRANSITIONS[cur]:
        raise ValueError(f"Invalid status transition: {cur} -> {nxt}")


def _incident_index(rows: List[Dict[str, Any]], incident_id: str) -> int:
    iid = str(incident_id or "").strip()
    for i, r in enumerate(rows):
        if str(r.get("incident_id") or "").strip() == iid:
            return i
    return -1


def get_incident(*, incidents_path: Path, incident_id: str) -> Dict[str, Any]:
    rows = _read_json_list(incidents_path)
    idx = _incident_index(rows, incident_id)
    if idx < 0:
        raise FileNotFoundError(f"Incident not found: {incident_id}")
    return rows[idx]


def list_incidents(
    *,
    incidents_path: Path,
    status: str = "",
    zone: str = "",
    limit: int = 100,
) -> List[Dict[str, Any]]:
    rows = _read_json_list(incidents_path)
    st = str(status or "").strip().lower()
    zn = str(zone or "").strip()
    if st:
        rows = [r for r in rows if str(r.get("status", "")).strip().lower() == st]
    if zn:
        rows = [r for r in rows if str(r.get("zone", "")).strip() == zn]
    rows.sort(key=lambda x: str(x.get("opened_at", "")), reverse=True)
    if int(limit) > 0:
        rows = rows[: int(limit)]
    return rows


def open_incident(
    *,
    incidents_path: Path,
    bundle: Dict[str, Any],
    bundle_path: str = "",
) -> Dict[str, Any]:
    rows = _read_json_list(incidents_path)

    ev = bundle.get("evidence", {}) if isinstance(bundle.get("evidence"), dict) else {}
    ctx = ev.get("context", {}) if isinstance(ev.get("context"), dict) else {}
    scenario_id = str(ctx.get("scenario_id", "") or "").strip()
    zone = str(ctx.get("zone", "") or "").strip()

    # Reuse active incident if not yet closed for the same scenario+zone.
    for r in rows:
        if str(r.get("scenario_id", "")).strip() == scenario_id and str(r.get("zone", "")).strip() == zone:
            if str(r.get("status", "")).strip().lower() not in CLOSED_STATUSES:
                return r

    opened_at = _utc_now()
    status = "new"
    incident: Dict[str, Any] = {
        "incident_id": f"inc-{uuid4().hex[:12]}",
        "scenario_id": scenario_id,
        "bundle_path": str(bundle_path or "").strip(),
        "zone": zone,
        "decision": str(bundle.get("decision", "") or ""),
        "confidence": round(_to_float(bundle.get("confidence"), 0.0), 3),
        "status": status,
        "opened_at": opened_at,
        "dispatched_at": "",
        "closed_at": "",
        "assignee_team": "",
        "eta_minutes": None,
        "closure_type": "",
        "closure_note": "",
        "repair_cost_usd": 0.0,
        "impact_snapshot": _build_impact_snapshot(bundle),
        "events": [
            {
                "at": opened_at,
                "type": "opened",
                "status": status,
                "note": "Incident opened from evidence bundle.",
            }
        ],
    }
    rows.append(incident)
    _write_json_list(incidents_path, rows)
    return incident


def transition_incident(
    *,
    incidents_path: Path,
    incident_id: str,
    new_status: str,
    note: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    rows = _read_json_list(incidents_path)
    idx = _incident_index(rows, incident_id)
    if idx < 0:
        raise FileNotFoundError(f"Incident not found: {incident_id}")

    row = dict(rows[idx])
    cur = str(row.get("status", "new") or "new").strip().lower()
    nxt = str(new_status or "").strip().lower()
    _validate_transition(cur, nxt)

    now = _utc_now()
    row["status"] = nxt
    if nxt == "dispatched" and not str(row.get("dispatched_at", "")).strip():
        row["dispatched_at"] = now
    if nxt in CLOSED_STATUSES:
        row["closed_at"] = now
        impact = row.get("impact_snapshot", {}) if isinstance(row.get("impact_snapshot"), dict) else {}
        impact["provisional"] = False
        row["impact_snapshot"] = impact
    evt = {
        "at": now,
        "type": "status_update",
        "status": nxt,
        "note": str(note or "").strip(),
    }
    if isinstance(extra, dict) and extra:
        evt["extra"] = dict(extra)
        for k, v in extra.items():
            row[str(k)] = v
    events = row.get("events", []) if isinstance(row.get("events"), list) else []
    events.append(evt)
    row["events"] = events

    rows[idx] = row
    _write_json_list(incidents_path, rows)
    return row


def dispatch_incident(
    *,
    incidents_path: Path,
    incident_id: str,
    team: str,
    eta_minutes: int = 30,
) -> Dict[str, Any]:
    return transition_incident(
        incidents_path=incidents_path,
        incident_id=incident_id,
        new_status="dispatched",
        note="Dispatch assigned.",
        extra={
            "assignee_team": str(team or "").strip(),
            "eta_minutes": int(max(1, int(eta_minutes))),
        },
    )


def field_update_incident(
    *,
    incidents_path: Path,
    incident_id: str,
    status: str,
    note: str = "",
    evidence_added: bool = False,
) -> Dict[str, Any]:
    return transition_incident(
        incidents_path=incidents_path,
        incident_id=incident_id,
        new_status=status,
        note=note,
        extra={"evidence_added": bool(evidence_added)},
    )


def close_incident(
    *,
    incidents_path: Path,
    incident_id: str,
    closure_type: str,
    note: str = "",
    repair_cost_usd: float = 0.0,
) -> Dict[str, Any]:
    c = str(closure_type or "").strip().lower()
    if c not in {"true_positive", "false_positive"}:
        raise ValueError("closure_type must be true_positive or false_positive")
    target = "closed_true_positive" if c == "true_positive" else "closed_false_positive"
    return transition_incident(
        incidents_path=incidents_path,
        incident_id=incident_id,
        new_status=target,
        note=note,
        extra={
            "closure_type": c,
            "closure_note": str(note or "").strip(),
            "repair_cost_usd": round(max(0.0, _to_float(repair_cost_usd, 0.0)), 2),
        },
    )
