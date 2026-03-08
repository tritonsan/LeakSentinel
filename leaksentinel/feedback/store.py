from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
from uuid import uuid4


VALID_OUTCOMES = ("false_positive_rejected_by_operator",)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> Dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return obj


def resolve_latest_bundle_for_scenario(*, evidence_dir: Path, scenario_id: str) -> Path:
    candidates = []
    for p in evidence_dir.glob(f"{scenario_id}_*.json"):
        try:
            mtime = p.stat().st_mtime
        except Exception:
            mtime = 0.0
        candidates.append((mtime, p))
    if not candidates:
        raise FileNotFoundError(f"No evidence bundle found for scenario_id={scenario_id} in {evidence_dir}")
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def _fingerprint_text(bundle: Dict[str, Any], operator_note: str) -> str:
    ev = bundle.get("evidence", {})
    ctx = ev.get("context", {})
    flow = ctx.get("flow_summary", {})
    thermal = ev.get("thermal", {})
    audio = ev.get("audio", {})
    ops = ev.get("ops", {})
    parts = [
        f"zone={ctx.get('zone')}",
        f"ts={ctx.get('timestamp')}",
        f"decision={bundle.get('decision')}",
        f"confidence={bundle.get('confidence')}",
        f"anomaly={flow.get('anomaly_score')}",
        f"thermal_hit={thermal.get('has_leak_signature')} thermal_conf={thermal.get('confidence')}",
        f"audio_hit={audio.get('leak_like')} audio_conf={audio.get('confidence')} audio_skipped={audio.get('skipped')}",
        f"planned={ops.get('planned_op_found')} planned_ids={','.join(str(x) for x in (ops.get('planned_op_ids') or []))}",
    ]
    for r in (bundle.get("rationale") or [])[:4]:
        parts.append(str(r))
    note = (operator_note or "").strip()
    if note:
        parts.append(f"operator_note={note}")
    return " ".join(parts)


def _infer_root_cause_guess(bundle: Dict[str, Any]) -> str:
    ev = bundle.get("evidence", {})
    ctx = ev.get("context", {})
    flow = ctx.get("flow_summary", {})
    thermal = ev.get("thermal", {})
    audio = ev.get("audio", {})
    ops = ev.get("ops", {})

    try:
        anomaly = float(flow.get("anomaly_score", 0.0))
    except Exception:
        anomaly = 0.0
    planned = bool(ops.get("planned_op_found"))
    thermal_hit = bool(thermal.get("has_leak_signature"))
    audio_skipped = bool(audio.get("skipped"))
    audio_hit = bool(audio.get("leak_like")) if not audio_skipped else False

    if planned:
        return "planned_operation_overlap"
    if thermal_hit and not audio_hit:
        return "thermal_artifact_without_acoustic_confirmation"
    if audio_hit and not thermal_hit:
        return "acoustic_transient_without_thermal_confirmation"
    if abs(anomaly) < 0.5:
        return "weak_flow_signal_near_baseline"
    return "multi_factor_ambiguous_evidence"


def _infer_evidence_gap(bundle: Dict[str, Any]) -> str:
    ev = bundle.get("evidence", {})
    thermal = ev.get("thermal", {})
    audio = ev.get("audio", {})
    ops = ev.get("ops", {})

    planned = bool(ops.get("planned_op_found"))
    thermal_hit = bool(thermal.get("has_leak_signature"))
    thermal_conf = float(thermal.get("confidence", 0.0) or 0.0)
    audio_skipped = bool(audio.get("skipped"))
    audio_hit = bool(audio.get("leak_like")) if not audio_skipped else False
    audio_conf = float(audio.get("confidence", 0.0) or 0.0) if not audio_skipped else 0.0

    if planned:
        return "confirm_planned_ops_status_and_capture_post_window_sample"
    if audio_skipped and thermal_hit and thermal_conf >= 0.7:
        return "collect_acoustic_sample_for_confirmation"
    if audio_hit and audio_conf >= 0.7 and (not thermal_hit or thermal_conf < 0.6):
        return "capture_followup_thermal_frame_in_10_minutes"
    return "collect_thermal_and_acoustic_recheck_pair"


def _features(bundle: Dict[str, Any]) -> Dict[str, Any]:
    ev = bundle.get("evidence", {})
    ctx = ev.get("context", {})
    flow = ctx.get("flow_summary", {})
    thermal = ev.get("thermal", {})
    audio = ev.get("audio", {})
    ops = ev.get("ops", {})
    return {
        "zone": ctx.get("zone"),
        "timestamp": ctx.get("timestamp"),
        "anomaly_score": flow.get("anomaly_score"),
        "thermal_hit": bool(thermal.get("has_leak_signature")),
        "thermal_conf": float(thermal.get("confidence", 0.0) or 0.0),
        "audio_hit": bool(audio.get("leak_like")) if not audio.get("skipped") else False,
        "audio_conf": float(audio.get("confidence", 0.0) or 0.0) if not audio.get("skipped") else 0.0,
        "audio_skipped": bool(audio.get("skipped")),
        "planned_op_found": bool(ops.get("planned_op_found")),
        "planned_op_ids": [str(x) for x in (ops.get("planned_op_ids") or []) if x],
    }


def _iter_feedback_files(feedback_dir: Path) -> Iterable[Path]:
    if not feedback_dir.exists():
        return []
    return sorted(feedback_dir.glob("feedback_*.json"))


def create_feedback_record(
    *,
    outcome: str,
    operator_note: str = "",
    reviewer: str = "",
    bundle_path: str | Path | None = None,
    scenario_id: str | None = None,
    root_cause_guess: str = "",
    evidence_gap: str = "",
    evidence_dir: Path = Path("data/evidence_bundles"),
    feedback_dir: Path = Path("data/feedback"),
) -> Dict[str, Any]:
    out = str(outcome or "").strip()
    if out not in VALID_OUTCOMES:
        raise ValueError(f"Invalid outcome={out!r}. Allowed: {', '.join(VALID_OUTCOMES)}")

    if bundle_path:
        bp = Path(bundle_path)
    elif scenario_id:
        bp = resolve_latest_bundle_for_scenario(evidence_dir=evidence_dir, scenario_id=str(scenario_id))
    else:
        raise ValueError("Provide either bundle_path or scenario_id.")

    if not bp.exists():
        raise FileNotFoundError(f"Bundle not found: {bp}")

    bundle = _read_json(bp)
    ev = bundle.get("evidence", {})
    ctx = ev.get("context", {})
    root_cause = str(root_cause_guess or "").strip() or _infer_root_cause_guess(bundle)
    gap = str(evidence_gap or "").strip() or _infer_evidence_gap(bundle)
    fingerprint_text = _fingerprint_text(bundle, str(operator_note or ""))
    if root_cause:
        fingerprint_text += f" root_cause_guess={root_cause}"
    if gap:
        fingerprint_text += f" evidence_gap={gap}"

    feedback_id = f"fb-{uuid4().hex[:12]}"
    created_at = _utc_now()
    rec: Dict[str, Any] = {
        "feedback_id": feedback_id,
        "created_at": created_at,
        "outcome": out,
        "reviewer": str(reviewer or "").strip(),
        "operator_note": str(operator_note or "").strip(),
        "bundle_path": str(bp),
        "scenario_id": ctx.get("scenario_id"),
        "zone": ctx.get("zone"),
        "timestamp": ctx.get("timestamp"),
        "decision": bundle.get("decision"),
        "confidence": bundle.get("confidence"),
        "root_cause_guess": root_cause,
        "evidence_gap": gap,
        "fingerprint_text": fingerprint_text,
        "features": _features(bundle),
    }

    feedback_dir.mkdir(parents=True, exist_ok=True)
    safe_ts = created_at.replace(":", "-")
    out_path = feedback_dir / f"feedback_{safe_ts}_{feedback_id}.json"
    out_path.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    rec["_stored_path"] = str(out_path)
    return rec


def list_feedback_records(
    *,
    feedback_dir: Path = Path("data/feedback"),
    zone: Optional[str] = None,
    outcome: Optional[str] = None,
    limit: int = 100,
) -> list[Dict[str, Any]]:
    rows: list[Dict[str, Any]] = []
    for p in _iter_feedback_files(feedback_dir):
        try:
            obj = _read_json(p)
            obj["_stored_path"] = str(p)
            rows.append(obj)
        except Exception:
            continue

    if zone:
        z = str(zone).strip()
        rows = [r for r in rows if str(r.get("zone") or "") == z]
    if outcome:
        o = str(outcome).strip()
        rows = [r for r in rows if str(r.get("outcome") or "") == o]

    rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    if limit > 0:
        rows = rows[: int(limit)]
    return rows
