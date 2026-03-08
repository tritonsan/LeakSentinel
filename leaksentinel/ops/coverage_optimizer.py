from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _parse_ts(v: Any) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(v))
    except Exception:
        return None


def _priority_from_bundle(bundle: Dict[str, Any]) -> Dict[str, Any]:
    decision = str(bundle.get("decision", "INVESTIGATE")).strip().upper()
    conf = _to_float(bundle.get("confidence"), 0.0)
    base = {"LEAK_CONFIRMED": 70.0, "INVESTIGATE": 45.0, "IGNORE_PLANNED_OPS": 20.0}.get(decision, 30.0)
    score = base * (0.55 + min(1.0, conf))
    reasons: List[str] = [f"decision={decision} conf={conf:.2f}"]

    cf = bundle.get("continuous_flow_alert", {}) if isinstance(bundle.get("continuous_flow_alert"), dict) else {}
    sev = str(cf.get("severity", "")).strip().lower()
    if bool(cf.get("detected")):
        add = {"high": 20.0, "medium": 10.0, "low": 4.0}.get(sev, 6.0)
        score += add
        reasons.append(f"continuous_flow={sev or 'detected'} +{add:.0f}")

    inv_reason = str(bundle.get("investigate_reason_code", "")).strip()
    if inv_reason in {"modal_conflict", "uncertain_audio_label"}:
        score += 8.0
        reasons.append("safety_escalation +8")

    cfv2 = bundle.get("counterfactual_v2", {}) if isinstance(bundle.get("counterfactual_v2"), dict) else {}
    ddelta = cfv2.get("decision_delta", {}) if isinstance(cfv2.get("decision_delta"), dict) else {}
    if bool(ddelta.get("flipped")):
        score += 10.0
        reasons.append("counterfactual_flip +10")

    ops = (bundle.get("evidence") or {}).get("ops") if isinstance(bundle.get("evidence"), dict) else {}
    if isinstance(ops, dict) and bool(ops.get("planned_op_found")) and decision == "IGNORE_PLANNED_OPS":
        score -= 6.0
        reasons.append("planned_ops_explains_signal -6")

    ner = bundle.get("next_evidence_request_v2", {}) if isinstance(bundle.get("next_evidence_request_v2"), dict) else {}
    if isinstance(ner, dict) and ner:
        pr = str(ner.get("priority", "")).strip().lower()
        add = {"high": 8.0, "medium": 4.0, "low": 1.0}.get(pr, 2.0)
        score += add
        reasons.append(f"next_evidence_priority={pr or 'n/a'} +{add:.0f}")

    return {
        "priority_score": round(float(max(0.0, score)), 3),
        "priority_reasons": reasons,
    }


def build_coverage_plan(
    *,
    evidence_dir: Path,
    horizon_hours: int = 24,
    max_crews: int = 3,
    zones: Optional[List[str]] = None,
    now_ts: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Builds a deterministic dispatch queue from recent evidence bundles.
    """
    files = sorted(evidence_dir.glob("*.json"))
    if not files:
        return {
            "ok": True,
            "summary": {"bundles_considered": 0, "dispatch_n": 0, "unassigned_n": 0},
            "dispatch_queue": [],
            "unassigned": [],
        }

    allowed_zones = {str(z).strip() for z in (zones or []) if str(z).strip()}
    bundles: List[Dict[str, Any]] = []
    ts_candidates: List[datetime] = []
    for p in files:
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        ctx = (obj.get("evidence") or {}).get("context") if isinstance(obj.get("evidence"), dict) else {}
        if not isinstance(ctx, dict):
            continue
        z = str(ctx.get("zone", "") or "").strip()
        if allowed_zones and z not in allowed_zones:
            continue
        t = _parse_ts(ctx.get("timestamp"))
        if t:
            ts_candidates.append(t)
        obj["_bundle_file"] = p.name
        bundles.append(obj)

    if not bundles:
        return {
            "ok": True,
            "summary": {"bundles_considered": 0, "dispatch_n": 0, "unassigned_n": 0},
            "dispatch_queue": [],
            "unassigned": [],
        }

    ref_now = now_ts or (max(ts_candidates) if ts_candidates else datetime.now())
    t0 = ref_now - timedelta(hours=max(1, int(horizon_hours)))
    tasks: List[Dict[str, Any]] = []
    for b in bundles:
        ctx = (b.get("evidence") or {}).get("context") if isinstance(b.get("evidence"), dict) else {}
        ts = _parse_ts((ctx or {}).get("timestamp"))
        if ts and ts < t0:
            continue
        pr = _priority_from_bundle(b)
        task = {
            "bundle": str(b.get("_bundle_file", "")),
            "scenario_id": str((ctx or {}).get("scenario_id", "")),
            "zone": str((ctx or {}).get("zone", "")),
            "timestamp": str((ctx or {}).get("timestamp", "")),
            "decision": str(b.get("decision", "")),
            "confidence": round(_to_float(b.get("confidence"), 0.0), 3),
            "priority_score": _to_float(pr.get("priority_score"), 0.0),
            "priority_reasons": list(pr.get("priority_reasons") or []),
            "recommended_action": str(b.get("recommended_action", "")),
        }
        tasks.append(task)

    tasks.sort(key=lambda x: (-_to_float(x.get("priority_score"), 0.0), str(x.get("timestamp", ""))), reverse=False)
    # reverse=False with negative primary score keeps deterministic timestamp ordering among ties.

    queue = []
    for i, t in enumerate(tasks[: max(1, int(max_crews))], start=1):
        x = dict(t)
        x["assigned_crew"] = f"crew-{i}"
        queue.append(x)
    unassigned = [dict(t) for t in tasks[max(1, int(max_crews)) :]]

    return {
        "ok": True,
        "summary": {
            "bundles_considered": int(len(tasks)),
            "dispatch_n": int(len(queue)),
            "unassigned_n": int(len(unassigned)),
            "horizon_hours": int(max(1, int(horizon_hours))),
            "max_crews": int(max(1, int(max_crews))),
        },
        "dispatch_queue": queue,
        "unassigned": unassigned,
    }
