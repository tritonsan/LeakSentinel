from __future__ import annotations

from typing import Any, Dict, List, Optional


def local_decision(*, evidence: Dict[str, Any], policy: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Deterministic decision policy used as a local fallback.

    Output schema is intentionally similar to the hackathon narrative:
    - decision: LEAK_CONFIRMED | INVESTIGATE | IGNORE_PLANNED_OPS
    - confidence: 0..1
    - rationale: list[str]
    """
    ctx = evidence.get("context", {})
    flow = ctx.get("flow_summary", {})
    thermal = evidence.get("thermal", {})
    audio = evidence.get("audio", {})
    ops = evidence.get("ops", {})

    rationale: List[str] = []
    policy = dict(policy or {})
    confirm_anomaly_min = float(policy.get("confirm_anomaly_min", 1.0))
    strong_modal_conf_min = float(policy.get("strong_modal_conf_min", 0.8))
    ignore_planned_anomaly_min = float(policy.get("ignore_planned_anomaly_min", 1.0))
    confirm_use_abs_anomaly = bool(policy.get("confirm_use_abs_anomaly", False))
    cautious_mode = bool(policy.get("cautious_mode", False))
    investigate_on_modal_conflict = bool(policy.get("investigate_on_modal_conflict", cautious_mode))
    uncertain_audio_requires_investigate = bool(policy.get("uncertain_audio_requires_investigate", cautious_mode))

    anomaly = float(flow.get("anomaly_score", 0.0))
    confirm_anomaly_signal = abs(anomaly) if confirm_use_abs_anomaly else anomaly
    rationale.append(f"Flow anomaly_score={anomaly:.2f} observed={flow.get('observed')} expected={flow.get('expected')}.")

    planned = bool(ops.get("planned_op_found"))
    if planned:
        rationale.append(f"Planned ops in window: {', '.join(ops.get('planned_op_ids', [])) or '(ids missing)'}")

    thermal_conf = float(thermal.get("confidence", 0.0))
    thermal_hit = bool(thermal.get("has_leak_signature"))
    rationale.append(f"Thermal: hit={thermal_hit} conf={thermal_conf:.2f}.")

    audio_conf = float(audio.get("confidence", 0.0)) if not audio.get("skipped") else 0.0
    audio_hit = bool(audio.get("leak_like")) if not audio.get("skipped") else False
    if audio.get("skipped"):
        rationale.append("Audio check skipped (thermal confidence above threshold).")
    else:
        rationale.append(f"Audio: hit={audio_hit} conf={audio_conf:.2f}.")

    audio_label_conf = str(ctx.get("audio_label_confidence", "") or "").strip().lower()
    uncertain_audio = audio_label_conf == "uncertain"
    safety_flags: List[str] = []

    # Simple policy (demo-safe):
    # - Strong leak signatures should NOT be suppressed by planned ops.
    # - Planned ops is used to suppress alerts only when evidence is weak/inconclusive.
    strong_thermal_pos = thermal_hit and thermal_conf >= strong_modal_conf_min
    strong_audio_pos = audio_hit and audio_conf >= strong_modal_conf_min
    strong_modal = strong_thermal_pos or strong_audio_pos
    # High-confidence negative from one modality against high-confidence positive from another is conflict.
    strong_thermal_neg = (not thermal_hit) and thermal_conf >= 0.9
    strong_audio_neg = (not audio.get("skipped")) and (not audio_hit) and audio_conf >= 0.9
    modal_conflict = (strong_thermal_pos and strong_audio_neg) or (strong_audio_pos and strong_thermal_neg)

    if investigate_on_modal_conflict and modal_conflict:
        safety_flags.append("modal_conflict")
        return {
            "decision": "INVESTIGATE",
            "confidence": 0.6,
            "rationale": rationale
            + ["Strong positive/negative modality conflict detected; hold dispatch and request more evidence."],
            "recommended_action": "Request additional inspection or sensors; recheck within 15 minutes.",
            "evidence_weights": {"flow": 0.35, "thermal": 0.3, "audio": 0.25, "ops_override": 0.1},
            "decision_safety_flags": safety_flags,
            "investigate_reason_code": "modal_conflict",
        }

    if (
        uncertain_audio_requires_investigate
        and uncertain_audio
        and strong_audio_pos
        and not strong_thermal_pos
    ):
        safety_flags.append("uncertain_audio_label")
        return {
            "decision": "INVESTIGATE",
            "confidence": 0.6,
            "rationale": rationale
            + ["Audio sample is marked uncertain and thermal confirmation is weak; route to operator investigation."],
            "recommended_action": "Request additional inspection or sensors; recheck within 15 minutes.",
            "evidence_weights": {"flow": 0.35, "thermal": 0.3, "audio": 0.25, "ops_override": 0.1},
            "decision_safety_flags": safety_flags,
            "investigate_reason_code": "uncertain_audio_label",
        }

    if strong_modal and confirm_anomaly_signal >= confirm_anomaly_min:
        return {
            "decision": "LEAK_CONFIRMED",
            "confidence": 0.85,
            "rationale": rationale
            + (["Planned ops present, but evidence strongly indicates a leak (override)."] if planned else [])
            + [
                (
                    "Strong evidence with meaningful flow anomaly "
                    f"(confirm_signal>={confirm_anomaly_min:.2f}, modal_conf>={strong_modal_conf_min:.2f})."
                )
            ],
            "recommended_action": "Dispatch crew and isolate segment; follow safety protocol.",
            "evidence_weights": {"flow": 0.35, "thermal": 0.3, "audio": 0.25, "ops_override": 0.1},
            "decision_safety_flags": safety_flags,
            "investigate_reason_code": "",
        }

    if planned and anomaly >= ignore_planned_anomaly_min:
        return {
            "decision": "IGNORE_PLANNED_OPS",
            "confidence": 0.75,
            "rationale": rationale
            + [
                (
                    "Evidence is weak; anomaly likely explained by planned operations "
                    f"(anomaly>={ignore_planned_anomaly_min:.2f})."
                )
            ],
            "recommended_action": "No dispatch; monitor if anomaly persists outside planned window.",
            "evidence_weights": {"flow": 0.35, "thermal": 0.25, "audio": 0.25, "ops_override": 0.15},
            "decision_safety_flags": safety_flags,
            "investigate_reason_code": "",
        }

    safety_flags.append("inconclusive_evidence")
    return {
        "decision": "INVESTIGATE",
        "confidence": 0.55,
        "rationale": rationale + ["Evidence is inconclusive; recommend operator review."],
        "recommended_action": "Request additional inspection or sensors; recheck within 15 minutes.",
        "evidence_weights": {"flow": 0.4, "thermal": 0.25, "audio": 0.25, "ops_override": 0.1},
        "decision_safety_flags": safety_flags,
        "investigate_reason_code": "inconclusive_evidence",
    }
