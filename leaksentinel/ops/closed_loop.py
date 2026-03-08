from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from leaksentinel.config import AppSettings
from leaksentinel.feedback.store import VALID_OUTCOMES, create_feedback_record
from leaksentinel.ops.coverage_optimizer import build_coverage_plan
from leaksentinel.orchestrator import run_scenario


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _simulated_time_to_action_minutes(priority_score: float) -> float:
    # Higher priority should trigger faster dispatch in this deterministic simulation.
    score = max(0.0, float(priority_score))
    return max(5.0, 50.0 - (score * 0.35))


def simulate_closed_loop(
    *,
    scenario_id: str,
    mode: str = "local",
    field_verdict: str = "rejected_false_positive",
    max_crews: int = 3,
    horizon_hours: int = 24,
) -> Dict[str, Any]:
    settings = AppSettings(mode=mode)
    timeline: List[Dict[str, Any]] = []

    base = run_scenario(
        scenario_id=scenario_id,
        mode=mode,
        write_bundle=True,
        analysis_version="v2",
        ablation="full",
    )
    timeline.append(
        {
            "step": "detect",
            "status": "completed",
            "detail": f"Initial decision={str(base.get('decision', 'UNKNOWN'))} confidence={_to_float(base.get('confidence'), 0.0):.2f}",
        }
    )
    coverage = build_coverage_plan(
        evidence_dir=settings.paths.evidence_dir,
        horizon_hours=int(max(1, horizon_hours)),
        max_crews=int(max(1, max_crews)),
        zones=[],
    )
    queue = coverage.get("dispatch_queue", []) if isinstance(coverage.get("dispatch_queue"), list) else []
    selected = None
    for q in queue:
        if str(q.get("scenario_id", "")).strip() == str(scenario_id).strip():
            selected = q
            break
    if selected is None and queue:
        selected = queue[0]
    timeline.append(
        {
            "step": "prioritize_dispatch",
            "status": "completed" if selected is not None else "skipped",
            "detail": f"queue_size={len(queue)} top_priority={_to_float((selected or {}).get('priority_score'), 0.0):.1f}",
        }
    )

    priority_score = _to_float((selected or {}).get("priority_score"), 0.0)
    time_to_action = _simulated_time_to_action_minutes(priority_score)
    feedback_applied = False
    feedback_id = ""
    post_action_outcome = "confirmed_no_feedback"

    verdict = str(field_verdict or "").strip().lower()
    if verdict in {"rejected_false_positive", "false_positive"}:
        rec = create_feedback_record(
            scenario_id=scenario_id,
            outcome=VALID_OUTCOMES[0],
            operator_note="Closed-loop simulation: dispatch rejected by operator.",
            reviewer="closed_loop_sim",
            evidence_dir=settings.paths.evidence_dir,
            feedback_dir=settings.paths.feedback_dir,
        )
        feedback_applied = True
        feedback_id = str(rec.get("feedback_id", "") or "")
        post_action_outcome = "feedback_recorded_false_positive"
        timeline.append(
            {
                "step": "field_verdict",
                "status": "completed",
                "detail": "Operator rejected alert as false positive; feedback stored.",
            }
        )
    else:
        timeline.append(
            {
                "step": "field_verdict",
                "status": "completed",
                "detail": "Field team confirmed event; no false-positive feedback stored.",
            }
        )

    after = run_scenario(
        scenario_id=scenario_id,
        mode=mode,
        write_bundle=False,
        analysis_version="v2",
        ablation="full",
    )
    before_conf = _to_float(base.get("confidence"), 0.0)
    after_conf = _to_float(after.get("confidence"), 0.0)
    feedback_effective = bool(feedback_applied and (after_conf <= before_conf or str(after.get("decision")) == "INVESTIGATE"))
    timeline.append(
        {
            "step": "rerun_after_feedback",
            "status": "completed",
            "detail": f"before={str(base.get('decision'))}/{before_conf:.2f} after={str(after.get('decision'))}/{after_conf:.2f}",
        }
    )

    return {
        "mode": "closed_loop_simulation_v1",
        "loop_completed": bool(selected is not None),
        "scenario_id": scenario_id,
        "time_to_action_min": round(time_to_action, 2),
        "post_action_outcome": post_action_outcome,
        "feedback_applied": feedback_applied,
        "feedback_effective": feedback_effective,
        "learning_record_id": feedback_id,
        "dispatch_queue_size": int(len(queue)),
        "selected_dispatch": selected or {},
        "before": {
            "decision": str(base.get("decision", "")),
            "confidence": round(before_conf, 3),
            "bundle_path": str(base.get("_bundle_path", "") or ""),
        },
        "after": {
            "decision": str(after.get("decision", "")),
            "confidence": round(after_conf, 3),
        },
        "decision_change_summary": {
            "from_decision": str(base.get("decision", "")),
            "to_decision": str(after.get("decision", "")),
            "decision_changed": str(base.get("decision", "")) != str(after.get("decision", "")),
            "confidence_delta": round(after_conf - before_conf, 3),
        },
        "timeline": timeline,
        "generated_at": datetime.utcnow().replace(microsecond=0).isoformat(),
    }
