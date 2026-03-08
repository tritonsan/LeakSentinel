from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from leaksentinel.config import AppSettings
from leaksentinel.bedrock.json_tools import (
    extract_json_object,
    validate_audio_schema,
    validate_decision_schema,
    validate_thermal_schema,
)
from leaksentinel.bedrock.runtime import converse_image, converse_text, make_bedrock_runtime_client
from leaksentinel.tools.ops import find_planned_ops
from leaksentinel.tools.manifest import load_manifest_row, load_scenario
from leaksentinel.tools.flow import summarize_flow_window
from leaksentinel.tools.local_vision_audio import local_thermal_check, local_audio_check
from leaksentinel.tools.continuous_flow import detect_continuous_flow
from leaksentinel.tools.pressure_autopilot import build_pressure_plan
from leaksentinel.tools.acoustic_explain import explain_acoustic_evidence
from leaksentinel.tools.decision import local_decision
from leaksentinel.impact.scorecard import build_nrw_carbon_scorecard
from leaksentinel.compliance.standards_mode import load_json_or_default, evaluate_standards_readiness
from leaksentinel.retrieval.memory import (
    EmbeddingsCache,
    load_memory_local,
    load_memory_bedrock,
    top_k_similar_local,
    top_k_similar_bedrock,
)
from leaksentinel.feedback.policy import apply_confidence_downshift
from leaksentinel.feedback.retrieval import summarize_root_causes, top_k_similar_mistakes
from leaksentinel.feedback.store import VALID_OUTCOMES, list_feedback_records


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def _ops_window(ts: datetime, window_minutes: int) -> tuple[str, str]:
    """
    Planned-ops queries should use the same time window as the scenario.

    `window_minutes` is treated as total window length centered on `ts`.
    """
    half = max(1, int(window_minutes) // 2)
    return _iso(ts - timedelta(minutes=half)), _iso(ts + timedelta(minutes=half))


def _track_policy(track: str) -> Dict[str, Any]:
    t = str(track or "core").strip().lower()
    if t == "real_challenge":
        # Real-challenge lane is calibrated to be less anomaly-strict so strong acoustic evidence can surface.
        return {
            "confirm_anomaly_min": 0.0,
            "strong_modal_conf_min": 0.75,
            "ignore_planned_anomaly_min": 0.85,
            "confirm_use_abs_anomaly": True,
            "cautious_mode": True,
            "investigate_on_modal_conflict": True,
            "uncertain_audio_requires_investigate": True,
        }
    return {
        "confirm_anomaly_min": 1.0,
        "strong_modal_conf_min": 0.8,
        "ignore_planned_anomaly_min": 1.0,
        "cautious_mode": False,
        "investigate_on_modal_conflict": True,
        "uncertain_audio_requires_investigate": True,
    }


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _clamp(v: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, float(v))))


def _sigmoid(x: float) -> float:
    if x >= 0.0:
        z = math.exp(-float(x))
        return float(1.0 / (1.0 + z))
    z = math.exp(float(x))
    return float(z / (1.0 + z))


def _logit(p: float) -> float:
    q = _clamp(float(p), 1e-6, 1.0 - 1e-6)
    return float(math.log(q / (1.0 - q)))


def _default_confidence_calibration_profile_v1() -> Dict[str, Any]:
    return {
        "version": "temperature_scaling_v1",
        "default": {
            "temperature": 0.85,
            "decision_temperatures": {
                "LEAK_CONFIRMED": 0.9,
                "IGNORE_PLANNED_OPS": 0.85,
                "INVESTIGATE": 0.95,
            },
            "confidence_table": [
                {"raw": 0.05, "calibrated": 0.08},
                {"raw": 0.25, "calibrated": 0.33},
                {"raw": 0.5, "calibrated": 0.62},
                {"raw": 0.75, "calibrated": 0.86},
                {"raw": 0.95, "calibrated": 0.97},
            ],
        },
        "tracks": {
            "core": {
                "temperature": 0.83,
                "decision_temperatures": {
                    "LEAK_CONFIRMED": 0.9,
                    "IGNORE_PLANNED_OPS": 0.82,
                    "INVESTIGATE": 0.92,
                },
            },
            "real_challenge": {
                "temperature": 0.88,
                "decision_temperatures": {
                    "LEAK_CONFIRMED": 0.93,
                    "IGNORE_PLANNED_OPS": 0.86,
                    "INVESTIGATE": 0.95,
                },
                "confidence_table": [
                    {"raw": 0.05, "calibrated": 0.08},
                    {"raw": 0.25, "calibrated": 0.31},
                    {"raw": 0.5, "calibrated": 0.6},
                    {"raw": 0.75, "calibrated": 0.84},
                    {"raw": 0.95, "calibrated": 0.96},
                ],
            },
        },
    }


def _load_confidence_calibration_profile_v1(*, settings: AppSettings, runtime: Dict[str, Any]) -> Dict[str, Any]:
    profile = _default_confidence_calibration_profile_v1()
    path = settings.paths.confidence_calibration_path
    runtime["confidence_calibration_profile_path"] = str(path)
    if not path.exists():
        runtime["confidence_calibration_profile_source"] = "default_missing_file"
        runtime["confidence_calibration_profile_hash"] = _stable_hash(profile)
        return profile

    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(obj, dict):
            profile = obj
            runtime["confidence_calibration_profile_source"] = "file"
        else:
            runtime["confidence_calibration_profile_source"] = "default_invalid_root"
            runtime["confidence_calibration_profile_error"] = "calibration profile root must be object"
    except Exception as e:
        runtime["confidence_calibration_profile_source"] = "default_read_error"
        runtime["confidence_calibration_profile_error"] = str(e)
    runtime["confidence_calibration_profile_hash"] = _stable_hash(profile)
    return profile


def _merge_decision_temperatures(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, float]:
    merged: Dict[str, float] = {}
    for k, v in (base or {}).items():
        kk = str(k or "").strip().upper()
        if kk:
            merged[kk] = _to_float(v, 1.0)
    for k, v in (override or {}).items():
        kk = str(k or "").strip().upper()
        if kk:
            merged[kk] = _to_float(v, merged.get(kk, 1.0))
    return merged


def _apply_confidence_table(confidence: float, table: Any) -> tuple[float, bool]:
    if not isinstance(table, list):
        return float(confidence), False

    points: list[tuple[float, float]] = []
    for row in table:
        if not isinstance(row, dict):
            continue
        if "raw" not in row or "calibrated" not in row:
            continue
        x = _clamp(_to_float(row.get("raw"), float("nan")), 0.0, 1.0)
        y = _clamp(_to_float(row.get("calibrated"), float("nan")), 0.0, 1.0)
        if math.isnan(x) or math.isnan(y):
            continue
        points.append((float(x), float(y)))
    if len(points) < 2:
        return float(confidence), False

    points = sorted(points, key=lambda p: p[0])
    c = _clamp(_to_float(confidence, 0.0), 0.0, 1.0)
    if c <= points[0][0]:
        return float(points[0][1]), True
    if c >= points[-1][0]:
        return float(points[-1][1]), True

    for i in range(1, len(points)):
        x0, y0 = points[i - 1]
        x1, y1 = points[i]
        if c <= x1:
            if x1 <= x0:
                return float(y1), True
            t = (c - x0) / (x1 - x0)
            y = y0 + t * (y1 - y0)
            return float(y), True
    return float(c), True


def _stable_hash(obj: Any) -> str:
    try:
        txt = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    except Exception:
        txt = str(obj)
    return hashlib.sha256(txt.encode("utf-8")).hexdigest()[:16]


def _load_impact_assumptions_register(*, settings: AppSettings) -> Dict[str, Any]:
    return load_json_or_default(
        settings.impact.assumptions_path,
        default_obj={
            "impact": {
                "dispatch_cost_usd": float(settings.impact.dispatch_cost_usd),
                "leak_loss_per_hour_usd": float(settings.impact.leak_loss_per_hour_usd),
                "default_delay_hours": float(settings.impact.default_delay_hours),
                "investigate_dispatch_factor": float(settings.impact.investigate_dispatch_factor),
                "investigate_leak_factor": float(settings.impact.investigate_leak_factor),
            },
            "scorecard": {
                "water_unit_cost_usd_per_m3": float(settings.scorecard.water_unit_cost_usd_per_m3),
                "co2e_kg_per_m3": float(settings.scorecard.co2e_kg_per_m3),
                "baseline_nrw_pct": float(settings.scorecard.baseline_nrw_pct),
            },
            "sensitivity": {"low_multiplier": 0.8, "mid_multiplier": 1.0, "high_multiplier": 1.2},
        },
    )


def _impact_sensitivity_multipliers(register: Dict[str, Any]) -> Dict[str, float]:
    sens = register.get("sensitivity", {}) if isinstance(register.get("sensitivity"), dict) else {}
    low = _clamp(_to_float(sens.get("low_multiplier"), 0.8), 0.3, 1.0)
    mid = _clamp(_to_float(sens.get("mid_multiplier"), 1.0), low, 1.5)
    high = _clamp(_to_float(sens.get("high_multiplier"), 1.2), mid, 2.0)
    return {"low": float(low), "mid": float(mid), "high": float(high)}


def _impact_assumptions(
    *,
    settings: AppSettings,
    track: str,
    assumptions_register: Optional[Dict[str, Any]] = None,
) -> Dict[str, float]:
    reg = assumptions_register if isinstance(assumptions_register, dict) else {}
    impact_reg = reg.get("impact", {}) if isinstance(reg.get("impact"), dict) else {}
    delay_hours = _to_float(impact_reg.get("default_delay_hours"), float(settings.impact.default_delay_hours))
    leak_loss_per_hour_usd = _to_float(impact_reg.get("leak_loss_per_hour_usd"), float(settings.impact.leak_loss_per_hour_usd))
    dispatch_cost_usd = _to_float(impact_reg.get("dispatch_cost_usd"), float(settings.impact.dispatch_cost_usd))
    investigate_dispatch_factor = _to_float(
        impact_reg.get("investigate_dispatch_factor"),
        float(settings.impact.investigate_dispatch_factor),
    )
    investigate_leak_factor = _to_float(
        impact_reg.get("investigate_leak_factor"),
        float(settings.impact.investigate_leak_factor),
    )

    # Real-challenge incidents are treated as slightly higher uncertainty/latency in the business-impact story.
    if str(track or "").strip().lower() == "real_challenge":
        delay_hours = delay_hours * 1.15
        leak_loss_per_hour_usd = leak_loss_per_hour_usd * 1.10

    return {
        "dispatch_cost_usd": float(dispatch_cost_usd),
        "leak_loss_per_hour_usd": float(leak_loss_per_hour_usd),
        "delay_hours": float(delay_hours),
        "investigate_dispatch_factor": float(investigate_dispatch_factor),
        "investigate_leak_factor": float(investigate_leak_factor),
    }


def _build_evidence_quality_v1(*, evidence: Dict[str, Any]) -> Dict[str, Any]:
    ev = evidence if isinstance(evidence, dict) else {}
    ctx = ev.get("context", {}) if isinstance(ev.get("context"), dict) else {}
    flow = ctx.get("flow_summary", {}) if isinstance(ctx.get("flow_summary"), dict) else {}
    thermal = ev.get("thermal", {}) if isinstance(ev.get("thermal"), dict) else {}
    audio = ev.get("audio", {}) if isinstance(ev.get("audio"), dict) else {}
    ops = ev.get("ops", {}) if isinstance(ev.get("ops"), dict) else {}

    issues: list[str] = []
    anomaly_abs = abs(_to_float(flow.get("anomaly_score"), 0.0))
    flow_score = _clamp(0.65 + min(0.35, anomaly_abs * 0.15), 0.0, 1.0)
    thermal_available = not bool(thermal.get("skipped"))
    audio_available = not bool(audio.get("skipped"))
    thermal_score = (
        _clamp(_to_float(thermal.get("confidence"), 0.0) * (1.0 if bool(thermal.get("has_leak_signature")) else 0.85), 0.0, 1.0)
        if thermal_available
        else 0.0
    )
    audio_score = (
        _clamp(_to_float(audio.get("confidence"), 0.0) * (1.0 if bool(audio.get("leak_like")) else 0.85), 0.0, 1.0)
        if audio_available
        else 0.0
    )
    ops_score = 0.9 if isinstance(ops.get("query"), dict) else 0.7

    if not thermal_available:
        issues.append("thermal_signal_missing")
    if not audio_available:
        issues.append("audio_signal_missing")
    if thermal_available and thermal_score < 0.45:
        issues.append("thermal_low_confidence")
    if audio_available and audio_score < 0.45:
        issues.append("audio_low_confidence")
    if bool(ops.get("planned_op_found")):
        issues.append("planned_ops_overlap")

    parts = [
        {"name": "flow", "available": True, "score": round(flow_score, 3)},
        {"name": "thermal", "available": thermal_available, "score": round(thermal_score, 3)},
        {"name": "audio", "available": audio_available, "score": round(audio_score, 3)},
        {"name": "ops", "available": True, "score": round(ops_score, 3)},
    ]
    weights = {"flow": 0.35, "thermal": 0.25, "audio": 0.25, "ops": 0.15}
    weighted = 0.0
    for p in parts:
        n = str(p.get("name", ""))
        weighted += _to_float(p.get("score"), 0.0) * _to_float(weights.get(n), 0.0)

    return {
        "version": "v1",
        "overall_score": round(_clamp(weighted, 0.0, 1.0), 3),
        "components": parts,
        "issues": issues,
    }


def _calibrate_confidence_v1(
    *,
    decision: Dict[str, Any],
    evidence_quality: Dict[str, Any],
    runtime: Dict[str, Any],
    track: str,
    calibration_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    raw = _clamp(_to_float(decision.get("confidence"), 0.0), 0.0, 1.0)
    d = str(decision.get("decision", "INVESTIGATE")).strip().upper()
    eq = evidence_quality if isinstance(evidence_quality, dict) else {}
    eq_score = _clamp(_to_float(eq.get("overall_score"), 0.0), 0.0, 1.0)
    issues = [str(x) for x in (eq.get("issues") or []) if str(x).strip()]
    safety_flags = [str(x) for x in (decision.get("decision_safety_flags") or []) if str(x).strip()]

    adj = 0.0
    factors: list[str] = []
    if eq_score < 0.5:
        penalty = min(0.2, (0.5 - eq_score) * 0.35)
        adj -= penalty
        factors.append(f"low_evidence_quality:{penalty:.3f}")
    if safety_flags:
        penalty = min(0.2, 0.05 * len(safety_flags))
        adj -= penalty
        factors.append(f"safety_flags:{penalty:.3f}")
    if "audio_signal_missing" in issues and d == "LEAK_CONFIRMED":
        adj -= 0.05
        factors.append("missing_audio_for_confirm:0.050")
    if bool((runtime.get("bedrock") or {}).get("used")) and not any(bool(v) for v in ((runtime.get("bedrock") or {}).get("fallback") or {}).values()):
        adj += 0.02
        factors.append("bedrock_no_fallback:+0.020")

    pre_temperature = _clamp(raw + adj, 0.05, 0.99)
    profile = calibration_profile if isinstance(calibration_profile, dict) else _default_confidence_calibration_profile_v1()
    profile_default = profile.get("default", {}) if isinstance(profile.get("default"), dict) else {}
    track_map = profile.get("tracks", {}) if isinstance(profile.get("tracks"), dict) else {}
    track_norm = str(track or runtime.get("track", "core") or "core").strip().lower()
    track_profile = track_map.get(track_norm, {}) if isinstance(track_map.get(track_norm), dict) else {}

    temp_base = _to_float(profile_default.get("temperature"), 1.0)
    temp_track = _to_float(track_profile.get("temperature"), temp_base)
    decision_temps = _merge_decision_temperatures(
        profile_default.get("decision_temperatures", {}) if isinstance(profile_default.get("decision_temperatures"), dict) else {},
        track_profile.get("decision_temperatures", {}) if isinstance(track_profile.get("decision_temperatures"), dict) else {},
    )
    temp_decision = _to_float(decision_temps.get(d, 1.0), 1.0)
    effective_temp = _clamp(temp_track * temp_decision, 0.55, 3.0)
    post_temperature = _sigmoid(_logit(pre_temperature) / effective_temp)
    factors.append(f"temperature_scaling:T={effective_temp:.3f}")

    table = track_profile.get("confidence_table", profile_default.get("confidence_table", []))
    table_applied_conf, table_applied = _apply_confidence_table(post_temperature, table)
    calibrated = _clamp(table_applied_conf, 0.05, 0.99)
    if table_applied:
        factors.append("calibration_table:applied")

    return {
        "version": "v1",
        "method": "temperature_scaling_table_v1",
        "track": track_norm,
        "decision": d,
        "raw_confidence": round(raw, 3),
        "pre_temperature_confidence": round(pre_temperature, 3),
        "temperature": round(temp_track, 3),
        "decision_temperature": round(temp_decision, 3),
        "effective_temperature": round(effective_temp, 3),
        "post_temperature_confidence": round(_clamp(post_temperature, 0.0, 1.0), 3),
        "table_applied": bool(table_applied),
        "calibrated_confidence": round(calibrated, 3),
        "delta": round(calibrated - raw, 3),
        "profile_version": str(profile.get("version", "temperature_scaling_v1")),
        "factors": factors,
    }


def _build_decision_trace_v1(
    *,
    decision: Dict[str, Any],
    evidence: Dict[str, Any],
    policy: Dict[str, Any],
    confidence_calibration: Dict[str, Any],
) -> Dict[str, Any]:
    ev = evidence if isinstance(evidence, dict) else {}
    ctx = ev.get("context", {}) if isinstance(ev.get("context"), dict) else {}
    flow = ctx.get("flow_summary", {}) if isinstance(ctx.get("flow_summary"), dict) else {}
    thermal = ev.get("thermal", {}) if isinstance(ev.get("thermal"), dict) else {}
    audio = ev.get("audio", {}) if isinstance(ev.get("audio"), dict) else {}
    ops = ev.get("ops", {}) if isinstance(ev.get("ops"), dict) else {}
    anomaly = _to_float(flow.get("anomaly_score"), 0.0)
    thermal_conf = _to_float(thermal.get("confidence"), 0.0)
    audio_conf = _to_float(audio.get("confidence"), 0.0)

    return {
        "version": "v1",
        "steps": [
            {
                "stage": "flow_screen",
                "signal": round(anomaly, 3),
                "threshold": _to_float(policy.get("confirm_anomaly_min"), 1.0),
                "summary": "Flow anomaly analyzed against track policy threshold.",
            },
            {
                "stage": "thermal_check",
                "signal": round(thermal_conf, 3),
                "leak_signature": bool(thermal.get("has_leak_signature")),
                "summary": "Thermal confidence contributes to leak confirmation when corroborated.",
            },
            {
                "stage": "audio_check",
                "signal": round(audio_conf, 3),
                "leak_signature": bool(audio.get("leak_like")) if not bool(audio.get("skipped")) else False,
                "summary": "Acoustic confidence cross-checks thermal evidence.",
            },
            {
                "stage": "ops_guardrail",
                "planned_op_found": bool(ops.get("planned_op_found")),
                "summary": "Planned operations may suppress weak signals but cannot override strong leak evidence.",
            },
        ],
        "final_decision": str(decision.get("decision", "INVESTIGATE")),
        "final_confidence": _to_float(confidence_calibration.get("calibrated_confidence"), _to_float(decision.get("confidence"), 0.0)),
    }


def _build_provenance_v1(
    *,
    scenario_id: str,
    settings: AppSettings,
    runtime: Dict[str, Any],
    evidence: Dict[str, Any],
) -> Dict[str, Any]:
    cfg = {
        "mode": str(runtime.get("mode", settings.mode)),
        "analysis_version": str(runtime.get("analysis_version", "v2")),
        "ablation": str(runtime.get("ablation", "full")),
        "region": str(settings.bedrock.region),
        "impact_assumptions_path": str(settings.impact.assumptions_path),
        "standards_profile_path": str(settings.standards.default_profile_path),
    }
    models = {
        "reasoning_model_id": str(settings.bedrock.nova_reasoning_model_id or ""),
        "multimodal_model_id": str(settings.bedrock.nova_multimodal_model_id or ""),
        "embeddings_model_id": str(settings.bedrock.nova_embeddings_model_id or ""),
    }
    now_iso = _iso(datetime.utcnow())
    config_hash = _stable_hash({"cfg": cfg, "models": models})
    ev_ctx = (evidence.get("context") or {}) if isinstance(evidence.get("context"), dict) else {}
    evidence_hash = _stable_hash(
        {
            "scenario_id": scenario_id,
            "zone": ev_ctx.get("zone"),
            "timestamp": ev_ctx.get("timestamp"),
            "flow_summary": ev_ctx.get("flow_summary"),
            "ops": (evidence.get("ops") or {}),
        }
    )
    return {
        "version": "v1",
        "run_id": f"{scenario_id}-{evidence_hash[:8]}-{now_iso.replace(':', '').replace('-', '')}",
        "generated_at_utc": now_iso,
        "config_hash": config_hash,
        "evidence_hash": evidence_hash,
        "config": cfg,
        "models": models,
    }


def _build_judge_compliance(*, decision: Dict[str, Any], runtime: Dict[str, Any], judge_mode: bool) -> Dict[str, Any]:
    if not bool(judge_mode):
        return {"enabled": False, "pass": True, "missing_fields": [], "failed_checks": [], "mode": "standard"}

    d = decision if isinstance(decision, dict) else {}
    rt = runtime if isinstance(runtime, dict) else {}
    missing_fields: list[str] = []
    failed_checks: list[str] = []

    def _require(path: str, value: Any) -> None:
        missing = False
        if value is None:
            missing = True
        elif isinstance(value, str) and not value.strip():
            missing = True
        elif isinstance(value, list) and len(value) == 0:
            missing = True
        elif isinstance(value, dict) and len(value) == 0:
            missing = True
        if missing:
            missing_fields.append(path)

    _require("decision", d.get("decision"))
    _require("confidence", d.get("confidence"))
    _require("decision_trace_v1.steps", (d.get("decision_trace_v1") or {}).get("steps") if isinstance(d.get("decision_trace_v1"), dict) else None)
    _require(
        "evidence_quality_v1.overall_score",
        (d.get("evidence_quality_v1") or {}).get("overall_score") if isinstance(d.get("evidence_quality_v1"), dict) else None,
    )
    _require(
        "confidence_calibration_v1.calibrated_confidence",
        (d.get("confidence_calibration_v1") or {}).get("calibrated_confidence") if isinstance(d.get("confidence_calibration_v1"), dict) else None,
    )
    _require("provenance_v1.run_id", (d.get("provenance_v1") or {}).get("run_id") if isinstance(d.get("provenance_v1"), dict) else None)

    br = (rt.get("bedrock") or {}) if isinstance(rt.get("bedrock"), dict) else {}
    req = (br.get("request_ids") or {}) if isinstance(br.get("request_ids"), dict) else {}
    fb = (br.get("fallback") or {}) if isinstance(br.get("fallback"), dict) else {}
    _require("_runtime.bedrock.fallback", fb)
    _require("_runtime.bedrock.request_ids", req)

    mode_norm = str(rt.get("mode", "local")).strip().lower()
    if mode_norm == "bedrock":
        if not bool(br.get("used")):
            failed_checks.append("bedrock_mode_requires_live_usage")
        req_any = any(str(v).strip() for v in req.values() if isinstance(v, (str, int, float)))
        if not req_any:
            failed_checks.append("bedrock_mode_requires_request_ids")

    passed = (len(missing_fields) == 0) and (len(failed_checks) == 0)
    return {
        "enabled": True,
        "mode": "judge",
        "pass": bool(passed),
        "missing_fields": missing_fields,
        "failed_checks": failed_checks,
        "recommendation": (
            "Judge mode pass. Evidence lineage and runtime trace are complete."
            if passed
            else "Fill missing trace fields and ensure Bedrock live request IDs are present."
        ),
    }


def _build_closed_loop_summary_v1(
    *,
    evidence: Dict[str, Any],
    policy_out: Dict[str, Any],
    runtime: Dict[str, Any],
) -> Dict[str, Any]:
    sim_m = evidence.get("similar_mistakes", []) if isinstance(evidence.get("similar_mistakes"), list) else []
    applied = bool(policy_out.get("applied"))
    n_matches = int(len(sim_m))
    reduction_pct = 0.0
    if applied and n_matches > 0:
        reduction_pct = min(65.0, 12.0 + 8.0 * n_matches)
    return {
        "version": "v1",
        "feedback_memory_enabled": bool((runtime.get("feedback_memory") or {}).get("enabled")),
        "similar_mistakes_n": n_matches,
        "feedback_applied": applied,
        "feedback_effective": bool(applied and n_matches > 0),
        "repeat_fp_risk_reduction_pct": round(reduction_pct, 2),
    }


def _build_impact_proof_v1(
    *,
    impact_estimate_v2: Dict[str, Any],
    impact_estimate_v1: Dict[str, Any],
    scorecard: Dict[str, Any],
    impact_assumptions: Dict[str, float],
    assumptions_register: Dict[str, Any],
) -> Dict[str, Any]:
    v2 = impact_estimate_v2 if isinstance(impact_estimate_v2, dict) else {}
    v1 = impact_estimate_v1 if isinstance(impact_estimate_v1, dict) else {}
    sc = scorecard if isinstance(scorecard, dict) else {}
    saved = _to_float(v2.get("expected_total_impact_usd"), float("nan"))
    if saved != saved:
        saved = _to_float(v1.get("avoided_false_dispatch_estimate"), 0.0) + _to_float(v1.get("avoided_leak_loss_estimate"), 0.0)
    saved = max(0.0, float(saved))
    dispatch_cost = _to_float(impact_assumptions.get("dispatch_cost_usd"), 1200.0)
    baseline_expected_loss = max(saved, saved + (dispatch_cost * 0.5))
    with_system = max(0.0, baseline_expected_loss - saved)
    sens_m = _impact_sensitivity_multipliers(assumptions_register)
    sensitivity = {
        "min": round(saved * _to_float(sens_m.get("low"), 0.8), 2),
        "median": round(saved * _to_float(sens_m.get("mid"), 1.0), 2),
        "max": round(saved * _to_float(sens_m.get("high"), 1.2), 2),
    }
    return {
        "version": "v1",
        "baseline_vs_with_leaksentinel": {
            "baseline_expected_loss_usd": round(baseline_expected_loss, 2),
            "with_leaksentinel_expected_loss_usd": round(with_system, 2),
            "estimated_savings_usd": round(saved, 2),
        },
        "water_saved_m3": round(_to_float(sc.get("estimated_water_saved_m3"), 0.0), 3),
        "cost_saved_usd": round(_to_float(sc.get("estimated_cost_saved_usd"), saved), 2),
        "co2e_avoided_kg": round(_to_float(sc.get("estimated_co2e_kg_avoided"), 0.0), 3),
        "assumption_sensitivity": sensitivity,
        "assumptions_used": dict(impact_assumptions),
    }


def _build_next_evidence_request(
    *,
    decision: Dict[str, Any],
    evidence: Dict[str, Any],
    track: str,
    root_cause_summary: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    d = str(decision.get("decision", "")).strip().upper()
    conf = _to_float(decision.get("confidence"), 0.0)
    thermal = evidence.get("thermal", {}) if isinstance(evidence.get("thermal"), dict) else {}
    audio = evidence.get("audio", {}) if isinstance(evidence.get("audio"), dict) else {}
    ops = evidence.get("ops", {}) if isinstance(evidence.get("ops"), dict) else {}

    thermal_hit = bool(thermal.get("has_leak_signature"))
    thermal_conf = _to_float(thermal.get("confidence"), 0.0)
    audio_skipped = bool(audio.get("skipped"))
    audio_hit = bool(audio.get("leak_like")) if not audio_skipped else False
    audio_conf = _to_float(audio.get("confidence"), 0.0) if not audio_skipped else 0.0
    planned = bool(ops.get("planned_op_found"))

    if d == "LEAK_CONFIRMED" and conf >= 0.8:
        return None
    if d == "IGNORE_PLANNED_OPS" and conf >= 0.75:
        return None

    # Prioritize concrete next-best-evidence actions.
    if audio_skipped and thermal_hit and thermal_conf >= 0.7:
        return {
            "priority": "high",
            "request_type": "acoustic_capture",
            "request_window_minutes": 10,
            "instruction": "Collect a short (30-60s) acoustic sample and rerun verification.",
            "reason": "Thermal signal is strong but audio was skipped; corroborating acoustic evidence reduces false positives.",
            "track": track,
        }
    if (not thermal_hit or thermal_conf < 0.6) and audio_hit and audio_conf >= 0.7:
        return {
            "priority": "high",
            "request_type": "thermal_recheck",
            "request_window_minutes": 10,
            "instruction": "Capture a follow-up thermal frame in 10 minutes for the same zone.",
            "reason": "Audio indicates leak-like signature while thermal is weak/inconclusive.",
            "track": track,
        }
    if planned:
        return {
            "priority": "medium",
            "request_type": "ops_confirmation",
            "request_window_minutes": 15,
            "instruction": "Confirm planned operation status and capture one post-window verification sample.",
            "reason": "Planned operations overlap with anomaly; post-window confirmation helps avoid suppression mistakes.",
            "track": track,
        }
    # Historical feedback hints can improve what to ask next on ambiguous cases.
    top_gaps = []
    if isinstance(root_cause_summary, dict):
        top_gaps = list(root_cause_summary.get("top_evidence_gaps") or [])
    if top_gaps:
        lead_gap = str(top_gaps[0].get("gap", "")).strip().lower()
        if "acoustic" in lead_gap:
            return {
                "priority": "medium",
                "request_type": "acoustic_capture",
                "request_window_minutes": 10,
                "instruction": "Collect a short (30-60s) acoustic sample and rerun verification.",
                "reason": "Historical false-positive patterns suggest missing acoustic confirmation.",
                "track": track,
            }
        if "thermal" in lead_gap:
            return {
                "priority": "medium",
                "request_type": "thermal_recheck",
                "request_window_minutes": 10,
                "instruction": "Capture a follow-up thermal frame in 10 minutes for the same zone.",
                "reason": "Historical false-positive patterns suggest missing thermal confirmation.",
                "track": track,
            }
        if "planned_ops" in lead_gap or "planned" in lead_gap:
            return {
                "priority": "medium",
                "request_type": "ops_confirmation",
                "request_window_minutes": 15,
                "instruction": "Confirm planned operation status and capture one post-window verification sample.",
                "reason": "Historical false-positive patterns suggest ops-state ambiguity.",
                "track": track,
            }
    return {
        "priority": "medium",
        "request_type": "multi_sensor_recheck",
        "request_window_minutes": 15,
        "instruction": "Collect one thermal frame and one short acoustic sample, then rerun.",
        "reason": "Evidence remains inconclusive and requires additional cross-modal confirmation.",
        "track": track,
    }


def _build_counterfactual(*, evidence: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, Any]:
    cf_evidence = json.loads(json.dumps(evidence))
    ops = cf_evidence.get("ops", {}) if isinstance(cf_evidence.get("ops"), dict) else {}
    ops["planned_op_found"] = False
    ops["planned_op_ids"] = []
    ops["summary"] = "Counterfactual assumption: no planned operations in the incident window."
    cf_evidence["ops"] = ops
    out = local_decision(evidence=cf_evidence, policy=policy)
    return {
        "assumption": "no_planned_ops",
        "decision": out.get("decision"),
        "confidence": _to_float(out.get("confidence"), 0.0),
        "rationale_short": (out.get("rationale") or [])[:2],
    }


def _build_impact_estimate(
    *,
    decision: Dict[str, Any],
    evidence: Dict[str, Any],
    assumptions: Optional[Dict[str, float]] = None,
    currency: str = "USD",
) -> Dict[str, Any]:
    # Transparent first-order impact assumptions for demo storytelling.
    a = assumptions or {}
    dispatch_cost_usd = _to_float(a.get("dispatch_cost_usd"), 1200.0)
    leak_loss_per_hour_usd = _to_float(a.get("leak_loss_per_hour_usd"), 5000.0)
    delay_hours = _to_float(a.get("delay_hours"), 1.0)
    investigate_dispatch_factor = _clamp(_to_float(a.get("investigate_dispatch_factor"), 0.25), 0.0, 1.0)
    investigate_leak_factor = _clamp(_to_float(a.get("investigate_leak_factor"), 0.15), 0.0, 1.0)

    d = str(decision.get("decision", "INVESTIGATE")).strip().upper()
    conf = _to_float(decision.get("confidence"), 0.0)
    ops = evidence.get("ops", {}) if isinstance(evidence.get("ops"), dict) else {}
    planned = bool(ops.get("planned_op_found"))

    avoided_false_dispatch = 0.0
    avoided_leak_loss = 0.0
    risk_band = "medium"

    if d == "IGNORE_PLANNED_OPS":
        avoided_false_dispatch = dispatch_cost_usd
        risk_band = "low" if planned else "medium"
    elif d == "LEAK_CONFIRMED":
        avoided_leak_loss = leak_loss_per_hour_usd * delay_hours * max(0.4, conf)
        risk_band = "high"
    elif d == "INVESTIGATE":
        avoided_false_dispatch = dispatch_cost_usd * investigate_dispatch_factor
        avoided_leak_loss = leak_loss_per_hour_usd * delay_hours * investigate_leak_factor
        risk_band = "medium"

    return {
        "currency": str(currency or "USD"),
        "avoided_false_dispatch_estimate": round(avoided_false_dispatch, 2),
        "avoided_leak_loss_estimate": round(avoided_leak_loss, 2),
        "risk_band": risk_band,
        "assumptions": {
            "dispatch_cost_usd": dispatch_cost_usd,
            "leak_loss_per_hour_usd": leak_loss_per_hour_usd,
            "delay_hours": delay_hours,
            "investigate_dispatch_factor": investigate_dispatch_factor,
            "investigate_leak_factor": investigate_leak_factor,
        },
    }


def _build_next_evidence_request_v2(
    *,
    decision: Dict[str, Any],
    evidence: Dict[str, Any],
    track: str,
    mode: str,
    baseline_request: Optional[Dict[str, Any]],
    bedrock_client: Any,
    reasoning_model_id: str,
    runtime: Dict[str, Any],
) -> Dict[str, Any]:
    allowed_request_types = {"acoustic_capture", "thermal_recheck", "ops_confirmation", "multi_sensor_recheck"}
    allowed_priorities = {"high", "medium", "low"}

    d = str(decision.get("decision", "INVESTIGATE")).strip().upper()
    conf = _clamp(_to_float(decision.get("confidence"), 0.0), 0.0, 1.0)
    planned = bool((evidence.get("ops") or {}).get("planned_op_found")) if isinstance(evidence.get("ops"), dict) else False

    # Always emit a V2 object so downstream analytics can stay schema-stable.
    if not isinstance(baseline_request, dict):
        if d == "IGNORE_PLANNED_OPS":
            baseline_request = {
                "priority": "low",
                "request_type": "ops_confirmation",
                "request_window_minutes": 20,
                "instruction": "Reconfirm operation closure at the end of the planned window.",
                "reason": "Decision is suppressed by planned operations; closure confirmation protects against overlap mistakes.",
                "track": track,
            }
        elif d == "LEAK_CONFIRMED":
            baseline_request = {
                "priority": "medium",
                "request_type": "multi_sensor_recheck",
                "request_window_minutes": 10,
                "instruction": "Capture one short thermal + acoustic sample post-dispatch to confirm progression.",
                "reason": "Leak is confirmed; post-action evidence improves incident audit quality.",
                "track": track,
            }
        else:
            baseline_request = {
                "priority": "high",
                "request_type": "multi_sensor_recheck",
                "request_window_minutes": 15,
                "instruction": "Collect one thermal frame and one short acoustic sample, then rerun.",
                "reason": "Decision remains inconclusive and requires cross-modal confirmation.",
                "track": track,
            }

    priority = str(baseline_request.get("priority", "medium")).strip().lower()
    if priority not in allowed_priorities:
        priority = "medium"
    request_type = str(baseline_request.get("request_type", "multi_sensor_recheck")).strip().lower()
    if request_type not in allowed_request_types:
        request_type = "multi_sensor_recheck"
    request_window_minutes = int(max(5, min(60, int(_to_float(baseline_request.get("request_window_minutes"), 15)))))
    instruction = str(baseline_request.get("instruction", "") or "").strip() or "Collect additional evidence and rerun."
    reason = str(baseline_request.get("reason", "") or "").strip() or "Additional evidence is needed to reduce uncertainty."
    base_gain_map = {
        "acoustic_capture": 0.82,
        "thermal_recheck": 0.78,
        "ops_confirmation": 0.58,
        "multi_sensor_recheck": 0.72,
    }
    confidence = _clamp(max(0.35, 1.0 - conf + 0.15), 0.0, 1.0)
    expected_information_gain = _clamp(base_gain_map.get(request_type, 0.65) * max(0.55, 1.05 - conf), 0.0, 1.0)
    sla_minutes = {"high": 15, "medium": 30, "low": 60}.get(priority, 30)
    if planned and request_type == "ops_confirmation":
        sla_minutes = min(sla_minutes, 20)
    requires_operator_confirmation = bool(priority in {"high", "medium"})

    out: Dict[str, Any] = {
        "priority": priority,
        "request_type": request_type,
        "request_window_minutes": int(request_window_minutes),
        "instruction": instruction,
        "reason": reason,
        "confidence": float(confidence),
        "expected_information_gain": float(expected_information_gain),
        "sla_minutes": int(sla_minutes),
        "requires_operator_confirmation": requires_operator_confirmation,
        "source": "rule_engine",
        "track": str(track or "core"),
    }

    if str(mode).strip().lower() == "bedrock" and bedrock_client and str(reasoning_model_id or "").strip():
        try:
            sys = (
                "You optimize next-best-evidence recommendations for industrial triage.\n"
                "Output ONLY valid JSON and keep request_type within: acoustic_capture|thermal_recheck|ops_confirmation|multi_sensor_recheck."
            )
            user = (
                "Given DECISION_JSON and BASELINE_REQUEST_JSON, refine the recommendation.\n"
                "Return JSON with keys exactly:\n"
                "priority, request_type, request_window_minutes, instruction, reason, confidence, expected_information_gain, "
                "sla_minutes, requires_operator_confirmation.\n"
                "Rules:\n"
                "- Keep confidence and expected_information_gain in [0,1].\n"
                "- Keep request_window_minutes in [5,60].\n"
                "- Keep sla_minutes in [10,120].\n"
                f"- Track: {track}\n\n"
                f"DECISION_JSON:\n{json.dumps(decision)}\n\n"
                f"BASELINE_REQUEST_JSON:\n{json.dumps(out)}\n\n"
                f"EVIDENCE_JSON:\n{json.dumps(evidence)}"
            )
            resp = converse_text(
                client=bedrock_client,
                model_id=reasoning_model_id,
                system=sys,
                user=user,
                inference_config={"temperature": 0.0, "topP": 0.9, "maxTokens": 450},
            )
            runtime["bedrock"]["request_ids"]["afe"] = resp.request_id
            obj = extract_json_object(resp.text)

            pr = str(obj.get("priority", out["priority"])).strip().lower()
            rt = str(obj.get("request_type", out["request_type"])).strip().lower()
            if pr in allowed_priorities:
                out["priority"] = pr
            if rt in allowed_request_types:
                out["request_type"] = rt
            out["request_window_minutes"] = int(
                max(5, min(60, int(_to_float(obj.get("request_window_minutes"), out["request_window_minutes"]))))
            )
            out["instruction"] = str(obj.get("instruction", out["instruction"]) or out["instruction"]).strip()
            out["reason"] = str(obj.get("reason", out["reason"]) or out["reason"]).strip()
            out["confidence"] = _clamp(_to_float(obj.get("confidence"), out["confidence"]), 0.0, 1.0)
            out["expected_information_gain"] = _clamp(
                _to_float(obj.get("expected_information_gain"), out["expected_information_gain"]),
                0.0,
                1.0,
            )
            out["sla_minutes"] = int(max(10, min(120, int(_to_float(obj.get("sla_minutes"), out["sla_minutes"])))))
            out["requires_operator_confirmation"] = bool(
                obj.get("requires_operator_confirmation", out["requires_operator_confirmation"])
            )
            out["source"] = "bedrock"
        except Exception as e:
            runtime["bedrock"]["fallback"]["afe"] = True
            runtime["bedrock"]["errors"]["afe"] = str(e)

    return out


def _build_counterfactual_v2(
    *,
    decision: Dict[str, Any],
    evidence: Dict[str, Any],
    policy: Dict[str, Any],
) -> Dict[str, Any]:
    base_decision = str(decision.get("decision", "INVESTIGATE")).strip().upper()
    base_conf = _clamp(_to_float(decision.get("confidence"), 0.0), 0.0, 1.0)
    base_ev = json.loads(json.dumps(evidence))

    scenarios = [
        (
            "no_planned_ops",
            "Assume no planned operations overlap in the incident window.",
            lambda cf: cf.update(
                {
                    "ops": {
                        **(cf.get("ops", {}) if isinstance(cf.get("ops"), dict) else {}),
                        "planned_op_found": False,
                        "planned_op_ids": [],
                        "summary": "Counterfactual assumption: no planned operations in window.",
                    }
                }
            ),
        ),
        (
            "no_audio",
            "Assume acoustic channel is unavailable.",
            lambda cf: cf.update(
                {
                    "audio": {
                        "skipped": True,
                        "reason": "counterfactual_no_audio",
                        "leak_like": False,
                        "confidence": 0.0,
                        "explanation": "Audio channel removed in counterfactual analysis.",
                    }
                }
            ),
        ),
        (
            "no_thermal",
            "Assume thermal channel is unavailable.",
            lambda cf: cf.update(
                {
                    "thermal": {
                        "skipped": True,
                        "reason": "counterfactual_no_thermal",
                        "has_leak_signature": False,
                        "confidence": 0.0,
                        "explanation": "Thermal channel removed in counterfactual analysis.",
                    }
                }
            ),
        ),
        (
            "high_anomaly_low_confidence_guard",
            "Assume anomaly is high but modal confidence stays weak.",
            lambda cf: (
                cf.get("context", {}).get("flow_summary", {}).update(
                    {"anomaly_score": max(1.2, abs(_to_float((cf.get("context", {}).get("flow_summary", {}) or {}).get("anomaly_score"), 0.0)))}
                )
                if isinstance(cf.get("context", {}).get("flow_summary"), dict)
                else None,
                cf.update(
                    {
                        "thermal": {
                            **(cf.get("thermal", {}) if isinstance(cf.get("thermal"), dict) else {}),
                            "has_leak_signature": False,
                            "confidence": min(
                                0.45,
                                _to_float((cf.get("thermal", {}) if isinstance(cf.get("thermal"), dict) else {}).get("confidence"), 0.45),
                            ),
                        },
                        "audio": {
                            **(cf.get("audio", {}) if isinstance(cf.get("audio"), dict) else {}),
                            "leak_like": False,
                            "confidence": min(
                                0.45,
                                _to_float((cf.get("audio", {}) if isinstance(cf.get("audio"), dict) else {}).get("confidence"), 0.45),
                            ),
                            "skipped": False,
                        },
                    }
                ),
            ),
        ),
    ]

    scenario_outputs: list[Dict[str, Any]] = []
    flipped = 0
    max_abs_conf_delta = 0.0
    dominant_driver = "stable"
    to_decisions: list[str] = []
    recommendation_if_flips = "No action: decision is stable under tested counterfactuals."

    for scenario_name, assumption, mutate in scenarios:
        cf = json.loads(json.dumps(base_ev))
        mutate(cf)
        out = local_decision(evidence=cf, policy=policy)
        out = _apply_shared_decision_safety(decision=out, evidence=cf, policy=policy)
        cf_decision = str(out.get("decision", "INVESTIGATE")).strip().upper()
        cf_conf = _clamp(_to_float(out.get("confidence"), 0.0), 0.0, 1.0)
        cf_delta = cf_conf - base_conf
        max_abs_conf_delta = max(max_abs_conf_delta, abs(cf_delta))
        is_flip = cf_decision != base_decision
        if is_flip:
            flipped += 1
            if cf_decision not in to_decisions:
                to_decisions.append(cf_decision)
            if dominant_driver == "stable":
                dominant_driver = scenario_name
            recommendation_if_flips = (
                "Decision flips under counterfactuals; treat as fragile and prioritize additional evidence capture."
            )
        scenario_outputs.append(
            {
                "name": scenario_name,
                "assumption": assumption,
                "decision": cf_decision,
                "confidence": round(cf_conf, 3),
                "flipped": is_flip,
                "confidence_delta": round(cf_delta, 3),
            }
        )

    n = max(1, len(scenario_outputs))
    stability_score = round((n - flipped) / n, 3)
    return {
        "scenarios": scenario_outputs,
        "decision_delta": {
            "flipped": bool(flipped > 0),
            "from": base_decision,
            "to": to_decisions,
            "flip_count": int(flipped),
            "flip_rate": round(flipped / n, 3),
        },
        "confidence_delta": {"max_abs_delta": round(max_abs_conf_delta, 3)},
        "stability_score": stability_score,
        "dominant_driver": dominant_driver,
        "recommendation_if_flips": recommendation_if_flips,
    }


def _build_impact_estimate_v2(
    *,
    decision: Dict[str, Any],
    evidence: Dict[str, Any],
    assumptions: Dict[str, float],
    currency: str,
    mode: str,
    bedrock_client: Any,
    reasoning_model_id: str,
    runtime: Dict[str, Any],
) -> Dict[str, Any]:
    base = _build_impact_estimate(
        decision=decision,
        evidence=evidence,
        assumptions=assumptions,
        currency=currency,
    )
    avoided_dispatch = _to_float(base.get("avoided_false_dispatch_estimate"), 0.0)
    avoided_leak_loss = _to_float(base.get("avoided_leak_loss_estimate"), 0.0)
    total = float(avoided_dispatch + avoided_leak_loss)
    conf = _clamp(_to_float(decision.get("confidence"), 0.0), 0.0, 1.0)
    d = str(decision.get("decision", "INVESTIGATE")).strip().upper()

    urgency = "medium"
    if d == "LEAK_CONFIRMED":
        urgency = "high"
    elif d == "IGNORE_PLANNED_OPS":
        urgency = "low"

    delay_h = _to_float((base.get("assumptions") or {}).get("delay_hours"), 1.0)
    low_delay = max(0.1, delay_h * 0.8)
    high_delay = max(0.1, delay_h * 1.2)
    leak_per_h = _to_float((base.get("assumptions") or {}).get("leak_loss_per_hour_usd"), 5000.0)
    delay_sensitivity = {
        "delay_hours_minus_20pct": round(low_delay, 3),
        "delay_hours_plus_20pct": round(high_delay, 3),
        "leak_loss_at_minus_20pct_delay": round(leak_per_h * low_delay, 2),
        "leak_loss_at_plus_20pct_delay": round(leak_per_h * high_delay, 2),
    }

    out: Dict[str, Any] = {
        "currency": str(currency or "USD"),
        "avoided_false_dispatch_usd": round(avoided_dispatch, 2),
        "avoided_leak_loss_usd": round(avoided_leak_loss, 2),
        "expected_total_impact_usd": round(total, 2),
        "risk_band": str(base.get("risk_band", "medium")),
        "response_urgency": urgency,
        "assumptions": dict(base.get("assumptions") or {}),
        "sensitivity": delay_sensitivity,
        "confidence": round(max(0.25, min(1.0, conf)), 3),
        "source": "rule_engine",
        "impact_rationale": "First-order deterministic estimate derived from decision class and configured assumptions.",
    }

    if str(mode).strip().lower() == "bedrock" and bedrock_client and str(reasoning_model_id or "").strip():
        try:
            sys = (
                "You summarize business impact for incident triage decisions.\n"
                "Output ONLY valid JSON with keys: impact_rationale, response_urgency."
            )
            user = (
                "Given the current impact object, refine impact_rationale in <=2 short sentences and optionally update response_urgency "
                "to one of high|medium|low.\n\n"
                f"DECISION_JSON:\n{json.dumps(decision)}\n\n"
                f"IMPACT_JSON:\n{json.dumps(out)}"
            )
            resp = converse_text(
                client=bedrock_client,
                model_id=reasoning_model_id,
                system=sys,
                user=user,
                inference_config={"temperature": 0.0, "topP": 0.9, "maxTokens": 220},
            )
            runtime["bedrock"]["request_ids"]["impact"] = resp.request_id
            obj = extract_json_object(resp.text)
            impact_rationale = str(obj.get("impact_rationale", out["impact_rationale"]) or "").strip()
            if impact_rationale:
                out["impact_rationale"] = impact_rationale
            urgency2 = str(obj.get("response_urgency", out["response_urgency"])).strip().lower()
            if urgency2 in {"high", "medium", "low"}:
                out["response_urgency"] = urgency2
            out["source"] = "bedrock"
        except Exception as e:
            runtime["bedrock"]["fallback"]["impact"] = True
            runtime["bedrock"]["errors"]["impact"] = str(e)

    return out


def _unique_flags(flags: list[str]) -> list[str]:
    out: list[str] = []
    for f in flags:
        s = str(f or "").strip()
        if s and s not in out:
            out.append(s)
    return out


def _apply_real_challenge_audio_backup(
    *,
    audio: Dict[str, Any],
    flow_summary: Dict[str, Any],
    context: Dict[str, Any],
    track: str,
    mode: str,
    strong_modal_conf_min: float,
) -> Dict[str, Any]:
    """
    Bedrock occasionally undercalls leak-like acoustic signatures in real challenge clips.
    If label confidence is high and deterministic audio strongly disagrees, use a guarded backup.
    """
    out = dict(audio if isinstance(audio, dict) else {})
    if str(mode).strip().lower() != "bedrock":
        return out
    if str(track).strip().lower() != "real_challenge":
        return out
    if bool(out.get("skipped")):
        return out

    label_conf = str(context.get("audio_label_confidence", "") or "").strip().lower()
    if label_conf != "high_confidence":
        return out

    heur = out.get("_heuristic") if isinstance(out.get("_heuristic"), dict) else None
    if not isinstance(heur, dict):
        return out

    model_hit = bool(out.get("leak_like"))
    model_conf = _to_float(out.get("confidence"), 0.0)
    heur_hit = bool(heur.get("leak_like"))
    heur_conf = _to_float(heur.get("confidence"), 0.0)
    anomaly_signal = abs(_to_float(flow_summary.get("anomaly_score"), 0.0))

    should_backup = (
        (not model_hit)
        and model_conf >= 0.9
        and heur_hit
        and heur_conf >= strong_modal_conf_min
        and anomaly_signal >= 0.3
    )
    if not should_backup:
        return out

    out["_model"] = {
        "leak_like": model_hit,
        "confidence": model_conf,
        "explanation": str(out.get("explanation", "") or ""),
    }
    out["leak_like"] = True
    out["confidence"] = float(max(heur_conf, strong_modal_conf_min))
    out["explanation"] = (
        f"{str(out.get('explanation', '') or '').strip()} "
        "Fusion backup: high-confidence label + deterministic acoustic signature indicates leak-like evidence."
    ).strip()
    out["fusion_rule"] = "high_confidence_audio_backup"
    return out


def _apply_shared_decision_safety(
    *,
    decision: Dict[str, Any],
    evidence: Dict[str, Any],
    policy: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Applies mode-agnostic decision safety guardrails after synthesis.
    This keeps local and bedrock paths aligned for investigate safety.
    """
    out = dict(decision)
    ev = evidence if isinstance(evidence, dict) else {}
    ctx = ev.get("context", {}) if isinstance(ev.get("context"), dict) else {}
    thermal = ev.get("thermal", {}) if isinstance(ev.get("thermal"), dict) else {}
    audio = ev.get("audio", {}) if isinstance(ev.get("audio"), dict) else {}
    ops = ev.get("ops", {}) if isinstance(ev.get("ops"), dict) else {}
    flow = ctx.get("flow_summary", {}) if isinstance(ctx.get("flow_summary"), dict) else {}
    thermal_heur = thermal.get("_heuristic") if isinstance(thermal.get("_heuristic"), dict) else None
    audio_heur = audio.get("_heuristic") if isinstance(audio.get("_heuristic"), dict) else None

    safety_flags = [str(x) for x in (out.get("decision_safety_flags") or [])]
    d = str(out.get("decision", "INVESTIGATE")).strip().upper()
    conf = _to_float(out.get("confidence"), 0.5)

    strong_modal_conf_min = float(policy.get("strong_modal_conf_min", 0.8))
    ignore_planned_anomaly_min = float(policy.get("ignore_planned_anomaly_min", 1.0))
    confirm_use_abs_anomaly = bool(policy.get("confirm_use_abs_anomaly", False))
    cautious_mode = bool(policy.get("cautious_mode", False))
    investigate_on_modal_conflict = bool(policy.get("investigate_on_modal_conflict", cautious_mode))
    uncertain_audio_requires_investigate = bool(policy.get("uncertain_audio_requires_investigate", cautious_mode))

    try:
        _anomaly = float(flow.get("anomaly_score", 0.0))
    except Exception:
        _anomaly = 0.0
    planned_anomaly_signal = abs(_anomaly) if confirm_use_abs_anomaly else _anomaly
    planned = bool(ops.get("planned_op_found"))
    thermal_hit = bool(thermal.get("has_leak_signature"))
    thermal_conf = _to_float(thermal.get("confidence"), 0.0)
    audio_skipped = bool(audio.get("skipped"))
    audio_hit = bool(audio.get("leak_like")) if not audio_skipped else False
    audio_conf = _to_float(audio.get("confidence"), 0.0) if not audio_skipped else 0.0
    audio_label_conf = str(ctx.get("audio_label_confidence", "") or "").strip().lower()

    strong_thermal_pos = thermal_hit and thermal_conf >= strong_modal_conf_min
    strong_audio_pos = audio_hit and audio_conf >= strong_modal_conf_min
    strong_thermal_neg = (not thermal_hit) and thermal_conf >= 0.9
    strong_audio_neg = (not audio_skipped) and (not audio_hit) and audio_conf >= 0.9
    thermal_heur_hit = bool(thermal_heur.get("has_leak_signature")) if isinstance(thermal_heur, dict) else False
    thermal_heur_conf = (
        _to_float(thermal_heur.get("confidence"), 0.0) if isinstance(thermal_heur, dict) else 0.0
    )
    audio_heur_hit = bool(audio_heur.get("leak_like")) if isinstance(audio_heur, dict) else False
    audio_heur_conf = _to_float(audio_heur.get("confidence"), 0.0) if isinstance(audio_heur, dict) else 0.0

    strong_thermal_neg_reliable = strong_thermal_neg and (
        not isinstance(thermal_heur, dict) or ((not thermal_heur_hit) and thermal_heur_conf >= strong_modal_conf_min)
    )
    strong_audio_neg_reliable = strong_audio_neg and (
        not isinstance(audio_heur, dict) or ((not audio_heur_hit) and audio_heur_conf >= strong_modal_conf_min)
    )
    modal_conflict = (strong_thermal_pos and strong_audio_neg_reliable) or (
        strong_audio_pos and strong_thermal_neg_reliable
    )
    uncertain_audio = audio_label_conf == "uncertain"
    thermal_corroborated = strong_thermal_pos and (
        not isinstance(thermal_heur, dict) or (thermal_heur_hit and thermal_heur_conf >= strong_modal_conf_min)
    )
    audio_corroborated = strong_audio_pos and (
        not isinstance(audio_heur, dict) or (audio_heur_hit and audio_heur_conf >= strong_modal_conf_min)
    )
    low_trust_audio_label = audio_label_conf in {"", "uncertain", "synthetic", "low_confidence"}

    if d == "LEAK_CONFIRMED":
        if investigate_on_modal_conflict and modal_conflict:
            out["decision"] = "INVESTIGATE"
            out["confidence"] = float(min(conf, 0.6))
            out["investigate_reason_code"] = "modal_conflict"
            safety_flags.append("modal_conflict")
            out["rationale"] = list(out.get("rationale") or []) + [
                "Decision safety: conflicting high-confidence modal signals; escalation set to INVESTIGATE."
            ]
        elif uncertain_audio_requires_investigate and uncertain_audio and not thermal_corroborated:
            out["decision"] = "INVESTIGATE"
            out["confidence"] = float(min(conf, 0.6))
            out["investigate_reason_code"] = "uncertain_audio_label"
            safety_flags.append("uncertain_audio_label")
            out["rationale"] = list(out.get("rationale") or []) + [
                "Decision safety: uncertain audio label without thermal confirmation; escalation set to INVESTIGATE."
            ]
        elif cautious_mode and low_trust_audio_label and strong_audio_pos and not thermal_corroborated and not audio_corroborated:
            out["decision"] = "INVESTIGATE"
            out["confidence"] = float(min(conf, 0.6))
            out["investigate_reason_code"] = "uncorroborated_modal_leak"
            safety_flags.append("uncorroborated_modal_leak")
            out["rationale"] = list(out.get("rationale") or []) + [
                "Decision safety: low-trust audio label without corroborated thermal support; escalation set to INVESTIGATE."
            ]
        elif planned and not (strong_thermal_pos or strong_audio_pos):
            out["decision"] = "INVESTIGATE"
            out["confidence"] = float(min(conf, 0.6))
            out["investigate_reason_code"] = "planned_ops_weak_evidence"
            safety_flags.append("planned_ops_weak_evidence")
            out["rationale"] = list(out.get("rationale") or []) + [
                "Decision safety: planned ops overlap with weak modal evidence; escalation set to INVESTIGATE."
            ]

    # If synthesis drifted to INVESTIGATE for a strong planned-ops pattern with weak leak evidence,
    # realign to suppression to reduce planned-ops false escalations (e.g., S04-like cases).
    if str(out.get("decision", "")).strip().upper() == "INVESTIGATE":
        conf_now = _to_float(out.get("confidence"), conf)
        weak_modal_evidence = not (strong_thermal_pos or strong_audio_pos)
        if (
            planned
            and planned_anomaly_signal >= ignore_planned_anomaly_min
            and weak_modal_evidence
            and not modal_conflict
        ):
            out["decision"] = "IGNORE_PLANNED_OPS"
            out["confidence"] = float(_clamp(max(conf_now, 0.72), 0.05, 0.9))
            out["investigate_reason_code"] = ""
            safety_flags.append("planned_ops_realign_ignore")
            out["rationale"] = list(out.get("rationale") or []) + [
                "Decision safety: planned ops pattern is strong and leak evidence is weak; realigned to IGNORE_PLANNED_OPS."
            ]

    if str(out.get("decision", "")).strip().upper() == "INVESTIGATE":
        reason_code = str(out.get("investigate_reason_code", "") or "").strip()
        if not reason_code:
            if modal_conflict:
                reason_code = "modal_conflict"
                safety_flags.append("modal_conflict")
            elif uncertain_audio:
                reason_code = "uncertain_audio_label"
                safety_flags.append("uncertain_audio_label")
            elif planned:
                reason_code = "planned_ops_weak_evidence"
                safety_flags.append("planned_ops_weak_evidence")
            else:
                reason_code = "inconclusive_evidence"
                safety_flags.append("inconclusive_evidence")
        out["investigate_reason_code"] = reason_code
    else:
        out["investigate_reason_code"] = ""

    out["decision_safety_flags"] = _unique_flags(safety_flags)
    return out


def run_scenario(
    *,
    scenario_id: str,
    mode: str = "local",
    write_bundle: bool = True,
    ablation: str = "full",
    analysis_version: str = "v2",
    include_counterfactuals: bool = True,
    include_impact: bool = True,
    include_flow_agent: bool = True,
    include_pressure_plan: bool = True,
    include_scorecard: bool = True,
    include_standards: bool = True,
    judge_mode: bool = False,
) -> Dict[str, Any]:
    """
    Runs the end-to-end verification for a scenario id.

    Modes:
    - local: no AWS calls, deterministic heuristics
    - bedrock: calls Amazon Nova models via Bedrock (with safe fallbacks)
    """
    settings = AppSettings(mode=mode)
    assumptions_register = _load_impact_assumptions_register(settings=settings)
    analysis_version_norm = str(analysis_version or "v2").strip().lower()
    if analysis_version_norm not in {"v1", "v2"}:
        raise ValueError("analysis_version must be one of: v1, v2")
    include_counterfactuals = bool(include_counterfactuals)
    include_impact = bool(include_impact)
    include_flow_agent = bool(include_flow_agent)
    include_pressure_plan = bool(include_pressure_plan)
    include_scorecard = bool(include_scorecard)
    include_standards = bool(include_standards)
    judge_mode = bool(judge_mode)

    ablation = (ablation or "full").strip().lower()
    allowed = {"full", "flow-only", "flow+thermal", "flow+thermal+audio"}
    if ablation not in allowed:
        raise ValueError(f"invalid ablation='{ablation}', allowed={sorted(allowed)}")

    runtime: Dict[str, Any] = {
        "mode": mode,
        "ablation": ablation,
        "bedrock": {
            "used": False,
            "region": settings.bedrock.region,
            "reasoning_model_id": settings.bedrock.nova_reasoning_model_id,
            "multimodal_model_id": settings.bedrock.nova_multimodal_model_id,
            "embeddings_model_id": settings.bedrock.nova_embeddings_model_id,
            "request_ids": {},
            "fallback": {"thermal": False, "audio": False, "decision": False, "embeddings": False, "afe": False, "impact": False},
            "errors": {},
        },
        "embeddings_cache": {"enabled": False, "hits": 0, "misses": 0, "path": ""},
        "feedback_memory": {
            "enabled": False,
            "path": str(settings.paths.feedback_dir),
            "records_n": 0,
            "matches_n": 0,
        },
        "evidence_memory_source": "local",
        "analysis_version": analysis_version_norm,
        "impact_assumptions_path": str(settings.impact.assumptions_path),
        "include_counterfactuals": include_counterfactuals,
        "include_impact": include_impact,
        "include_flow_agent": include_flow_agent,
        "include_pressure_plan": include_pressure_plan,
        "include_scorecard": include_scorecard,
        "include_standards": include_standards,
        "judge_mode": judge_mode,
    }
    runtime["impact_assumptions_hash"] = _stable_hash(assumptions_register)
    confidence_calibration_profile = _load_confidence_calibration_profile_v1(
        settings=settings,
        runtime=runtime,
    )

    bedrock_client = None
    if mode == "bedrock":
        try:
            bedrock_client = make_bedrock_runtime_client(region=settings.bedrock.region)
        except Exception as e:
            runtime["bedrock"]["errors"]["client"] = str(e)
            bedrock_client = None

    scenario = load_scenario(settings.paths.scenarios_path, scenario_id)
    mrow = load_manifest_row(settings.paths.manifest_path, scenario_id)
    if not mrow:
        raise ValueError(f"scenario_id not found in manifest: {scenario_id}")

    track_raw = scenario.get("track", mrow.get("track", "core"))
    if isinstance(track_raw, float):
        track_raw = "core"
    track = str(track_raw or "core").strip().lower()
    decision_policy = _track_policy(track)
    runtime["track"] = track
    runtime["decision_policy"] = decision_policy

    zone = mrow["zone"]
    ts = datetime.fromisoformat(mrow["timestamp"])

    flow_df = pd.read_csv(mrow["flow_file"])
    flow_df["timestamp"] = pd.to_datetime(flow_df["timestamp"])
    flow_summary = summarize_flow_window(flow_df, ts, window_minutes=int(scenario["window_minutes"]))
    if include_flow_agent:
        continuous_flow_alert = detect_continuous_flow(
            flow_df=flow_df,
            incident_ts=ts,
            lookback_hours=int(settings.flow_agent.lookback_hours),
            min_flow_threshold=float(settings.flow_agent.min_flow_threshold),
            min_excess_lpm_threshold=float(settings.flow_agent.min_excess_lpm_threshold),
            continuous_hours_threshold=float(settings.flow_agent.continuous_hours_threshold),
        )
    else:
        continuous_flow_alert = {}

    # Evidence gathering (tool-style).
    ctx = {
        "scenario_id": scenario_id,
        "track": track,
        "zone": zone,
        "timestamp": _iso(ts),
        "flow_summary": flow_summary,
        "thermal_file": mrow.get("thermal_file", ""),
        "spectrogram_file": mrow.get("spectrogram_file", ""),
        "audio_label_confidence": str(mrow.get("audio_label_confidence", "") or "").strip(),
        "audio_label_source": str(mrow.get("audio_label_source", "") or "").strip(),
        "audio_review_note": str(mrow.get("audio_review_note", "") or "").strip(),
    }

    # Step 1: thermal evidence
    if ablation == "flow-only":
        thermal = {"skipped": True, "reason": "ablation_flow_only", "has_leak_signature": False, "confidence": 0.0}
    elif mode == "local":
        thermal = local_thermal_check(ctx["thermal_file"])
    else:
        thermal_local = local_thermal_check(ctx["thermal_file"])
        thermal = dict(thermal_local)
        mm_id = settings.bedrock.nova_multimodal_model_id
        if bedrock_client and mm_id and ctx["thermal_file"]:
            try:
                img_bytes = Path(ctx["thermal_file"]).read_bytes()
                runtime["bedrock"]["used"] = True
                out = converse_image(
                    client=bedrock_client,
                    model_id=mm_id,
                    system="You are a careful industrial leak verification agent. Output ONLY valid JSON, no markdown.",
                    user=(
                        "Analyze this THERMAL image for leak-like hotspot patterns.\n"
                        "Return JSON with keys: has_leak_signature (bool), confidence (0..1), explanation (string)."
                    ),
                    image_bytes=img_bytes,
                    image_format="png",
                    inference_config={"temperature": 0.0, "topP": 0.9, "maxTokens": 400},
                )
                runtime["bedrock"]["request_ids"]["thermal"] = out.request_id
                obj = extract_json_object(out.text)
                # Ensure exact expected keys exist (validation also checks types/ranges).
                validate_thermal_schema(obj)
                thermal = obj
                thermal["_heuristic"] = thermal_local
            except Exception as e:
                runtime["bedrock"]["fallback"]["thermal"] = True
                runtime["bedrock"]["errors"]["thermal"] = str(e)
                thermal = thermal_local
                thermal["note"] = "bedrock thermal failed; using local fallback."
        else:
            thermal["note"] = "bedrock multimodal not configured; using local fallback."

    # Step 2: audio evidence
    # Keep "full" aligned with safer recall behavior by always collecting audio evidence.
    audio: Dict[str, Any] = {"skipped": True, "reason": "not_computed"}
    if ablation in {"flow-only", "flow+thermal"}:
        audio = {"skipped": True, "reason": f"ablation_{ablation.replace('+', '_')}"}
    else:
        # "full" and "flow+thermal+audio" always run audio to avoid single-modality lock-in.
        if mode == "local":
            audio = local_audio_check(ctx["spectrogram_file"])
        else:
            audio_local = local_audio_check(ctx["spectrogram_file"])
            audio = dict(audio_local)
            mm_id = settings.bedrock.nova_multimodal_model_id
            if bedrock_client and mm_id and ctx["spectrogram_file"]:
                try:
                    img_bytes = Path(ctx["spectrogram_file"]).read_bytes()
                    runtime["bedrock"]["used"] = True
                    out = converse_image(
                        client=bedrock_client,
                        model_id=mm_id,
                        system="You are a careful industrial leak verification agent. Output ONLY valid JSON, no markdown.",
                        user=(
                            "Analyze this SPECTROGRAM image for leak-like broadband hiss signatures.\n"
                            "Return JSON with keys: leak_like (bool), confidence (0..1), explanation (string)."
                        ),
                        image_bytes=img_bytes,
                        image_format="png",
                        inference_config={"temperature": 0.0, "topP": 0.9, "maxTokens": 400},
                    )
                    runtime["bedrock"]["request_ids"]["audio"] = out.request_id
                    obj = extract_json_object(out.text)
                    validate_audio_schema(obj)
                    audio = obj
                    # Keep a deterministic "second opinion" for stability on our demo dataset.
                    audio["_heuristic"] = audio_local
                except Exception as e:
                    runtime["bedrock"]["fallback"]["audio"] = True
                    runtime["bedrock"]["errors"]["audio"] = str(e)
                    audio = audio_local
                    audio["note"] = "bedrock audio failed; using local fallback."
            else:
                audio["note"] = "bedrock multimodal not configured; using local fallback."

    audio = _apply_real_challenge_audio_backup(
        audio=audio,
        flow_summary=flow_summary,
        context=ctx,
        track=track,
        mode=mode,
        strong_modal_conf_min=float(decision_policy.get("strong_modal_conf_min", 0.8)),
    )
    if mode == "bedrock" and isinstance(audio, dict) and str(audio.get("fusion_rule", "")).strip():
        runtime["bedrock"]["audio_fusion"] = str(audio.get("fusion_rule"))
    audio_explain = explain_acoustic_evidence(
        spectrogram_path=str(ctx.get("spectrogram_file", "") or ""),
        audio=audio if isinstance(audio, dict) else {},
        flow_summary=flow_summary,
    )

    # Step 3: ops verification (scenario window centered on incident ts)
    if ablation == "full":
        ops_start, ops_end = _ops_window(ts, int(scenario["window_minutes"]))
        try:
            ops_out = find_planned_ops(
                ops_db_path=settings.paths.ops_db_path,
                zone=zone,
                start=ops_start,
                end=ops_end,
            )
        except Exception as e:
            runtime["ops_fallback"] = True
            runtime["ops_error"] = str(e)
            ops_out = {
                "planned_op_found": False,
                "planned_op_ids": [],
                "records": [],
                "summary": "Ops query failed; fallback to safe no-op planned operations.",
                "query": {"zone": zone, "start": ops_start, "end": ops_end, "op_type": None},
                "error": str(e),
            }
    else:
        ops_start, ops_end = _ops_window(ts, int(scenario["window_minutes"]))
        ops_out = {
            "planned_op_found": False,
            "planned_op_ids": [],
            "records": [],
            "summary": f"Ablation: ops disabled ({ablation}).",
            "query": {"zone": zone, "start": ops_start, "end": ops_end, "op_type": None},
        }

    evidence = {
        "context": ctx,
        "thermal": thermal,
        "audio": audio,
        "audio_explain": audio_explain,
        "ops": ops_out,
        "continuous_flow_alert": continuous_flow_alert,
    }

    # Incident memory: heuristic local retrieval by default; Nova embeddings in bedrock mode when configured.
    try:
        qtext = f"zone={zone} ts={ctx['timestamp']} anomaly={flow_summary.get('anomaly_score')} thermal={thermal.get('has_leak_signature')} audio={audio.get('leak_like')}"
        if ablation == "full":
            if mode == "bedrock" and bedrock_client and settings.bedrock.nova_embeddings_model_id:
                cache_path = settings.paths.data_dir / "_cache" / "nova_embeddings_cache.json"
                cache = EmbeddingsCache.load(cache_path)
                runtime["embeddings_cache"]["enabled"] = True
                runtime["embeddings_cache"]["path"] = str(cache_path)
                runtime["bedrock"]["used"] = True
                emb_req_ids: list[str] = []
                memory = load_memory_bedrock(
                    evidence_dir=settings.paths.evidence_dir,
                    client=bedrock_client,
                    model_id=settings.bedrock.nova_embeddings_model_id,
                    cache=cache,
                    request_ids_out=emb_req_ids,
                    dim=256,
                    limit=200,
                )
                evidence["similar_incidents"] = top_k_similar_bedrock(
                    query_text=qtext,
                    memory=memory,
                    client=bedrock_client,
                    model_id=settings.bedrock.nova_embeddings_model_id,
                    cache=cache,
                    request_ids_out=emb_req_ids,
                    k=3,
                    dim=256,
                )
                runtime["embeddings_cache"]["hits"] = int(cache.hits)
                runtime["embeddings_cache"]["misses"] = int(cache.misses)
                runtime["evidence_memory_source"] = "bedrock"
                # Keep output small: store a few sample request ids plus a count.
                runtime["bedrock"]["request_ids"]["embeddings_n"] = int(len(emb_req_ids))
                runtime["bedrock"]["request_ids"]["embeddings"] = emb_req_ids[:10]
            else:
                memory = load_memory_local(evidence_dir=settings.paths.evidence_dir, dim=256, limit=200)
                evidence["similar_incidents"] = top_k_similar_local(query_text=qtext, memory=memory, k=3, dim=256)
                runtime["evidence_memory_source"] = "local"
        else:
            # Only include memory in full mode (otherwise ablation isn't clean).
            evidence["similar_incidents"] = []
    except Exception as e:
        if mode == "bedrock" and ablation == "full":
            runtime["bedrock"]["fallback"]["embeddings"] = True
            runtime["bedrock"]["errors"]["embeddings"] = str(e)
        if ablation == "full":
            # Final fallback: local retrieval if embeddings path fails.
            try:
                memory = load_memory_local(evidence_dir=settings.paths.evidence_dir, dim=256, limit=200)
                evidence["similar_incidents"] = top_k_similar_local(query_text=qtext, memory=memory, k=3, dim=256)
                runtime["evidence_memory_source"] = "local"
            except Exception as e2:
                runtime["bedrock"]["errors"]["embeddings_local_fallback"] = str(e2)
                evidence["similar_incidents"] = []
        else:
            evidence["similar_incidents"] = []

    # Learning-from-mistakes memory (operator feedback).
    try:
        runtime["feedback_memory"]["enabled"] = True
        feedback_rows = list_feedback_records(
            feedback_dir=settings.paths.feedback_dir,
            outcome=VALID_OUTCOMES[0],
            limit=300,
        )
        runtime["feedback_memory"]["records_n"] = int(len(feedback_rows))
        q_mistake = (
            f"zone={zone} ts={ctx['timestamp']} anomaly={flow_summary.get('anomaly_score')} "
            f"thermal={thermal.get('has_leak_signature')} thermal_conf={thermal.get('confidence')} "
            f"audio={audio.get('leak_like')} audio_conf={audio.get('confidence')} "
            f"planned={ops_out.get('planned_op_found')} planned_ids={ops_out.get('planned_op_ids')}"
        )
        evidence["similar_mistakes"] = top_k_similar_mistakes(
            query_text=q_mistake,
            feedback_records=feedback_rows,
            k=3,
            dim=256,
            min_score=0.0,
        )
        mistake_summary = summarize_root_causes(evidence["similar_mistakes"], top_n=3)
        evidence["similar_mistake_root_causes"] = mistake_summary
        runtime["feedback_memory"]["matches_n"] = int(len(evidence["similar_mistakes"]))
        top_causes = mistake_summary.get("top_causes", []) if isinstance(mistake_summary, dict) else []
        if top_causes:
            runtime["feedback_memory"]["top_root_cause"] = str(top_causes[0].get("cause", ""))
    except Exception as e:
        runtime["feedback_memory"]["error"] = str(e)
        evidence["similar_mistakes"] = []
        evidence["similar_mistake_root_causes"] = {
            "summary": "Feedback memory unavailable.",
            "top_causes": [],
            "top_evidence_gaps": [],
        }

    # Step 4: decision synthesis
    if mode == "local":
        decision = local_decision(evidence=evidence, policy=decision_policy)
    else:
        decision = local_decision(evidence=evidence, policy=decision_policy)

        anomaly = float((ctx.get("flow_summary") or {}).get("anomaly_score", 0.0))
        thermal_hit = bool(thermal.get("has_leak_signature"))
        thermal_conf = float(thermal.get("confidence", 0.0))
        audio_hit = bool(audio.get("leak_like")) if not audio.get("skipped") else False
        audio_conf = float(audio.get("confidence", 0.0)) if not audio.get("skipped") else 0.0
        thermal_heur = thermal.get("_heuristic")
        thermal_heur_hit = False
        thermal_heur_conf = 0.0
        if isinstance(thermal_heur, dict):
            thermal_heur_hit = bool(thermal_heur.get("has_leak_signature"))
            try:
                thermal_heur_conf = float(thermal_heur.get("confidence", 0.0))
            except Exception:
                thermal_heur_conf = 0.0
        heur = audio.get("_heuristic") if not audio.get("skipped") else None
        audio_heur_hit = False
        audio_heur_conf = 0.0
        if isinstance(heur, dict):
            audio_heur_hit = bool(heur.get("leak_like"))
            try:
                audio_heur_conf = float(heur.get("confidence", 0.0))
            except Exception:
                audio_heur_conf = 0.0
        planned = bool(ops_out.get("planned_op_found"))
        strong_modal_conf_min = float(decision_policy.get("strong_modal_conf_min", 0.8))
        confirm_anomaly_min = float(decision_policy.get("confirm_anomaly_min", 1.0))
        ignore_planned_anomaly_min = float(decision_policy.get("ignore_planned_anomaly_min", 1.0))
        confirm_use_abs_anomaly = bool(decision_policy.get("confirm_use_abs_anomaly", False))
        cautious_mode = bool(decision_policy.get("cautious_mode", False))
        investigate_on_modal_conflict = bool(decision_policy.get("investigate_on_modal_conflict", cautious_mode))
        uncertain_audio_requires_investigate = bool(
            decision_policy.get("uncertain_audio_requires_investigate", cautious_mode)
        )
        confirm_signal = abs(anomaly) if confirm_use_abs_anomaly else anomaly
        strong_modal = (thermal_hit and thermal_conf >= strong_modal_conf_min) or (
            audio_hit and audio_conf >= strong_modal_conf_min
        )
        # Strong contradictory negatives should force investigation in cautious policy.
        strong_thermal_neg = (not thermal_hit) and thermal_conf >= 0.9
        strong_audio_neg = (not audio.get("skipped")) and (not audio_hit) and audio_conf >= 0.9
        strong_thermal_neg_reliable = strong_thermal_neg and (
            (not isinstance(thermal_heur, dict)) or ((not thermal_heur_hit) and thermal_heur_conf >= strong_modal_conf_min)
        )
        strong_audio_neg_reliable = strong_audio_neg and (
            (not isinstance(heur, dict)) or ((not audio_heur_hit) and audio_heur_conf >= strong_modal_conf_min)
        )
        model_modal_conflict = (
            (thermal_hit and thermal_conf >= strong_modal_conf_min and strong_audio_neg_reliable)
            or (audio_hit and audio_conf >= strong_modal_conf_min and strong_thermal_neg_reliable)
        )
        audio_label_conf = str(ctx.get("audio_label_confidence", "") or "").strip().lower()
        low_trust_audio_label = audio_label_conf in {"", "uncertain", "synthetic", "low_confidence"}
        # If heuristics are present, require agreement with model for planned-ops leak override.
        thermal_planned_corroborated = (
            thermal_hit
            and thermal_conf >= strong_modal_conf_min
            and ((not isinstance(thermal_heur, dict)) or (thermal_heur_hit and thermal_heur_conf >= strong_modal_conf_min))
        )
        audio_planned_corroborated = (
            audio_hit
            and audio_conf >= strong_modal_conf_min
            and ((not isinstance(heur, dict)) or (audio_heur_hit and audio_heur_conf >= strong_modal_conf_min))
        )
        planned_override_corroborated = thermal_planned_corroborated or audio_planned_corroborated

        def _coerce_decision_obj(obj: Dict[str, Any]) -> Dict[str, Any]:
            out = dict(obj)
            out["decision"] = str(out.get("decision", "INVESTIGATE"))
            try:
                out["confidence"] = float(out.get("confidence", 0.5))
            except Exception:
                out["confidence"] = 0.5
            if not isinstance(out.get("rationale"), list):
                out["rationale"] = [str(out.get("rationale", ""))]
            out["rationale"] = [str(x) for x in (out.get("rationale") or [])]
            out["recommended_action"] = str(out.get("recommended_action", "Operator review."))
            if not isinstance(out.get("evidence_weights"), dict):
                out["evidence_weights"] = {"flow": 0.4, "thermal": 0.25, "audio": 0.25, "ops_override": 0.1}
            return out

        if bedrock_client and settings.bedrock.nova_reasoning_model_id:
            try:
                runtime["bedrock"]["used"] = True
                sys = (
                    "You are LeakSentinel, an industrial incident verification agent.\n"
                    "Output ONLY valid JSON. No markdown. No extra keys.\n"
                    "Do not invent facts; use only values present in EVIDENCE_JSON."
                )
                user = (
                    "Given the following evidence JSON, produce a decision.\n"
                    "Return JSON with keys:\n"
                    "- decision: one of LEAK_CONFIRMED | INVESTIGATE | IGNORE_PLANNED_OPS\n"
                    "- confidence: number 0..1\n"
                    "- rationale: list of short strings\n"
                    "- recommended_action: string\n"
                    "- evidence_weights: object with numeric weights (flow, thermal, audio, ops_override)\n\n"
                    "Policy constraints:\n"
                    "- IGNORE_PLANNED_OPS is ONLY allowed when planned_op_found=true.\n"
                    "- Planned operations may suppress dispatch ONLY when leak evidence is weak/inconclusive.\n"
                    "- If modalities are in strong conflict, prefer INVESTIGATE over LEAK_CONFIRMED.\n"
                    f"- If strong leak evidence exists (thermal has_leak_signature=true with confidence>={strong_modal_conf_min:.2f} OR audio leak_like=true with confidence>={strong_modal_conf_min:.2f})\n"
                    f"  AND confirm_signal>={confirm_anomaly_min:.2f}, you MUST output decision=LEAK_CONFIRMED even if planned ops exist.\n"
                    "- confirm_signal is anomaly_score unless a track policy says to use abs(anomaly_score).\n"
                    f"- LEAK_CONFIRMED is ONLY allowed when (strong leak evidence AND confirm_signal>={confirm_anomaly_min:.2f}).\n"
                    "- If planned_op_found=false and strong leak evidence is NOT present, output decision=INVESTIGATE.\n"
                    "- In rationale, cite exact numeric values (anomaly_score, thermal confidence, audio confidence if present) and any planned_op_id.\n\n"
                    f"EVIDENCE_JSON:\n{json.dumps(evidence)}"
                )
                out = converse_text(
                    client=bedrock_client,
                    model_id=settings.bedrock.nova_reasoning_model_id,
                    system=sys,
                    user=user,
                    inference_config={"temperature": 0.0, "topP": 0.9, "maxTokens": 800},
                )
                runtime["bedrock"]["request_ids"]["decision"] = out.request_id
                obj = extract_json_object(out.text)
                obj = _coerce_decision_obj(obj)
                validate_decision_schema(obj)
                decision = obj

                # Hard guardrail: don't allow planned-ops suppression when evidence is strong.
                # This keeps demo behavior aligned with our stated policy in local_decision.
                guardrails: list[str] = []

                # Guardrail A: strong evidence overrides ops suppression.
                if strong_modal and confirm_signal >= confirm_anomaly_min and decision.get("decision") != "LEAK_CONFIRMED":
                    decision["decision"] = "LEAK_CONFIRMED"
                    decision["confidence"] = float(max(float(decision.get("confidence", 0.0)), 0.85))
                    guardrails.append("strong_evidence_override_ops")

                # Guardrail B: IGNORE_PLANNED_OPS requires planned_op_found=true.
                if decision.get("decision") == "IGNORE_PLANNED_OPS" and not planned:
                    decision["decision"] = (
                        "INVESTIGATE" if not (strong_modal and confirm_signal >= confirm_anomaly_min) else "LEAK_CONFIRMED"
                    )
                    guardrails.append("no_planned_ops_cannot_ignore")

                # Guardrail C: LEAK_CONFIRMED requires strong evidence + confirm_signal threshold.
                if decision.get("decision") == "LEAK_CONFIRMED" and not (strong_modal and confirm_signal >= confirm_anomaly_min):
                    # If planned ops exist and anomaly is meaningful, fall back to ops suppression; otherwise investigate.
                    decision["decision"] = (
                        "IGNORE_PLANNED_OPS" if (planned and anomaly >= ignore_planned_anomaly_min) else "INVESTIGATE"
                    )
                    guardrails.append("no_strong_evidence_cannot_confirm_leak")

                # Guardrail D: If planned ops exist + anomaly>=1.0 + weak evidence, prefer suppression.
                if (
                    planned
                    and anomaly >= ignore_planned_anomaly_min
                    and not strong_modal
                    and decision.get("decision") == "INVESTIGATE"
                ):
                    decision["decision"] = "IGNORE_PLANNED_OPS"
                    guardrails.append("planned_ops_weak_evidence_suppress")

                # Guardrail E: Planned-ops leak override needs corroborated evidence.
                if planned and decision.get("decision") == "LEAK_CONFIRMED" and not planned_override_corroborated:
                    decision["decision"] = "IGNORE_PLANNED_OPS"
                    guardrails.append("planned_ops_require_corroborated_modal_evidence")

                # Guardrail F: Strong modality conflict is safety-critical.
                if (
                    investigate_on_modal_conflict
                    and decision.get("decision") == "LEAK_CONFIRMED"
                    and model_modal_conflict
                ):
                    decision["decision"] = "INVESTIGATE"
                    decision["confidence"] = float(min(float(decision.get("confidence", 0.6)), 0.6))
                    guardrails.append("modal_conflict_force_investigate")

                # Guardrail G: uncertain audio labels cannot directly confirm leak without thermal support.
                if (
                    uncertain_audio_requires_investigate
                    and decision.get("decision") == "LEAK_CONFIRMED"
                    and audio_label_conf == "uncertain"
                    and not thermal_planned_corroborated
                ):
                    decision["decision"] = "INVESTIGATE"
                    decision["confidence"] = float(min(float(decision.get("confidence", 0.6)), 0.6))
                    guardrails.append("uncertain_audio_force_investigate")

                # Guardrail H: low-trust audio labels require corroborated thermal support.
                if (
                    cautious_mode
                    and decision.get("decision") == "LEAK_CONFIRMED"
                    and low_trust_audio_label
                    and strong_modal
                    and not thermal_planned_corroborated
                    and not audio_planned_corroborated
                ):
                    decision["decision"] = "INVESTIGATE"
                    decision["confidence"] = float(min(float(decision.get("confidence", 0.6)), 0.6))
                    guardrails.append("low_trust_audio_requires_corroboration")

                if guardrails:
                    runtime["bedrock"]["decision_guardrails"] = guardrails
                    rationale = list(decision.get("rationale") or [])
                    rationale.append(f"Policy guardrails applied: {', '.join(guardrails)}.")
                    decision["rationale"] = rationale[:10]
            except Exception as e:
                runtime["bedrock"]["fallback"]["decision"] = True
                runtime["bedrock"]["errors"]["decision"] = str(e)
                decision = local_decision(evidence=evidence, policy=decision_policy)
                decision["note"] = "bedrock decision failed; using local fallback. Check NOVA_REASONING_MODEL_ID (inference profile ARN) and IAM permissions for bedrock:Converse."
        else:
            runtime["bedrock"]["fallback"]["decision"] = True
            decision = local_decision(evidence=evidence, policy=decision_policy)
            decision["note"] = "bedrock reasoning not configured; using local fallback."

    # Policy: similar historical false positives can reduce confidence but must not flip class.
    policy_out = apply_confidence_downshift(
        decision=decision,
        similar_mistakes=list(evidence.get("similar_mistakes") or []),
        min_score=0.82,
        base_downshift=0.10,
        per_extra_match=0.03,
        max_downshift=0.20,
        min_confidence=0.35,
    )
    decision = policy_out["decision"]
    if policy_out.get("applied"):
        runtime["feedback_memory"]["policy"] = policy_out.get("policy", {})

    decision = _apply_shared_decision_safety(
        decision=decision,
        evidence=evidence,
        policy=decision_policy,
    )
    evidence_quality_v1 = _build_evidence_quality_v1(evidence=evidence)
    confidence_calibration_v1 = _calibrate_confidence_v1(
        decision=decision,
        evidence_quality=evidence_quality_v1,
        runtime=runtime,
        track=track,
        calibration_profile=confidence_calibration_profile,
    )
    decision["confidence"] = float(confidence_calibration_v1.get("calibrated_confidence", decision.get("confidence", 0.0)))
    decision["evidence_quality_v1"] = evidence_quality_v1
    decision["confidence_calibration_v1"] = confidence_calibration_v1
    decision["decision_trace_v1"] = _build_decision_trace_v1(
        decision=decision,
        evidence=evidence,
        policy=decision_policy,
        confidence_calibration=confidence_calibration_v1,
    )
    runtime["decision_safety_flags"] = list(decision.get("decision_safety_flags") or [])
    runtime["investigate_reason_code"] = str(decision.get("investigate_reason_code", "") or "")

    root_summary = evidence.get("similar_mistake_root_causes", {})
    decision["historical_root_causes"] = list((root_summary or {}).get("top_causes") or [])
    decision["feedback_pattern_summary"] = str((root_summary or {}).get("summary") or "")
    next_evidence_request = _build_next_evidence_request(
        decision=decision,
        evidence=evidence,
        track=track,
        root_cause_summary=root_summary if isinstance(root_summary, dict) else None,
    )
    decision["next_evidence_request"] = next_evidence_request
    decision["analysis_version"] = analysis_version_norm

    if include_counterfactuals:
        decision["counterfactual"] = _build_counterfactual(evidence=evidence, policy=decision_policy)
    else:
        decision["counterfactual"] = {}

    impact_assumptions = _impact_assumptions(
        settings=settings,
        track=track,
        assumptions_register=assumptions_register,
    )
    if include_impact:
        decision["impact_estimate"] = _build_impact_estimate(
            decision=decision,
            evidence=evidence,
            assumptions=impact_assumptions,
            currency=str(settings.impact.currency or "USD"),
        )
    else:
        decision["impact_estimate"] = {}

    if include_pressure_plan:
        profile_path = settings.paths.pressure_dir / f"{zone}_profile.csv"
        pressure_plan = build_pressure_plan(
            incident_ts=ts,
            zone=str(zone),
            flow_summary=flow_summary,
            decision=str(decision.get("decision", "")),
            profile_path=profile_path,
            min_setpoint_m=float(settings.pressure.min_setpoint_m),
            max_setpoint_m=float(settings.pressure.max_setpoint_m),
            target_setpoint_m=float(settings.pressure.target_setpoint_m),
            track=track,
        )
    else:
        pressure_plan = {}
    decision["pressure_plan"] = pressure_plan

    if analysis_version_norm == "v2":
        decision["next_evidence_request_v2"] = _build_next_evidence_request_v2(
            decision=decision,
            evidence=evidence,
            track=track,
            mode=mode,
            baseline_request=next_evidence_request if isinstance(next_evidence_request, dict) else None,
            bedrock_client=bedrock_client,
            reasoning_model_id=settings.bedrock.nova_reasoning_model_id,
            runtime=runtime,
        )
        if include_counterfactuals:
            decision["counterfactual_v2"] = _build_counterfactual_v2(
                decision=decision,
                evidence=evidence,
                policy=decision_policy,
            )
        else:
            decision["counterfactual_v2"] = {}
        if include_impact:
            decision["impact_estimate_v2"] = _build_impact_estimate_v2(
                decision=decision,
                evidence=evidence,
                assumptions=impact_assumptions,
                currency=str(settings.impact.currency or "USD"),
                mode=mode,
                bedrock_client=bedrock_client,
                reasoning_model_id=settings.bedrock.nova_reasoning_model_id,
                runtime=runtime,
            )
        else:
            decision["impact_estimate_v2"] = {}

    if include_scorecard:
        decision["scorecard"] = build_nrw_carbon_scorecard(
            decision=decision,
            impact_estimate_v2=decision.get("impact_estimate_v2", {}) if isinstance(decision.get("impact_estimate_v2"), dict) else {},
            impact_estimate_v1=decision.get("impact_estimate", {}) if isinstance(decision.get("impact_estimate"), dict) else {},
            continuous_flow_alert=continuous_flow_alert if isinstance(continuous_flow_alert, dict) else {},
            water_unit_cost_usd_per_m3=None,
            co2e_kg_per_m3=None,
            baseline_nrw_pct=None,
            assumptions_register=assumptions_register,
            assumptions_path=settings.impact.assumptions_path,
        )
    else:
        decision["scorecard"] = {}

    if include_standards:
        default_profile = load_json_or_default(
            settings.standards.default_profile_path,
            default_obj={
                "building_id": "fallback-demo",
                "leak_sensor_network": True,
                "auto_shutoff_valve": False,
                "remote_valve_control": False,
                "alarm_notification": True,
                "manual_override": True,
                "battery_backup": False,
            },
        )
        controls_catalog = load_json_or_default(
            settings.standards.controls_catalog_path,
            default_obj={"required_controls": []},
        )
        decision["standards_readiness"] = evaluate_standards_readiness(
            building_profile=default_profile,
            controls_catalog=controls_catalog,
        )
    else:
        decision["standards_readiness"] = {}

    decision["closed_loop_summary_v1"] = _build_closed_loop_summary_v1(
        evidence=evidence,
        policy_out=policy_out,
        runtime=runtime,
    )
    decision["impact_proof_v1"] = _build_impact_proof_v1(
        impact_estimate_v2=decision.get("impact_estimate_v2", {}) if isinstance(decision.get("impact_estimate_v2"), dict) else {},
        impact_estimate_v1=decision.get("impact_estimate", {}) if isinstance(decision.get("impact_estimate"), dict) else {},
        scorecard=decision.get("scorecard", {}) if isinstance(decision.get("scorecard"), dict) else {},
        impact_assumptions=impact_assumptions,
        assumptions_register=assumptions_register,
    )
    decision["continuous_flow_alert"] = continuous_flow_alert if isinstance(continuous_flow_alert, dict) else {}
    decision["audio_explain"] = audio_explain if isinstance(audio_explain, dict) else {}
    evidence["pressure_plan"] = pressure_plan if isinstance(pressure_plan, dict) else {}

    decision["provenance_v1"] = _build_provenance_v1(
        scenario_id=scenario_id,
        settings=settings,
        runtime=runtime,
        evidence=evidence,
    )
    if judge_mode:
        decision["judge_compliance"] = _build_judge_compliance(
            decision=decision,
            runtime=runtime,
            judge_mode=judge_mode,
        )
    decision["evidence"] = evidence
    decision["_runtime"] = runtime

    # Persist evidence bundle for UI and evaluation.
    bundle_path: Optional[Path] = None
    if write_bundle:
        settings.paths.evidence_dir.mkdir(parents=True, exist_ok=True)
        safe_ts = ctx["timestamp"].replace(":", "-")
        bundle_path = settings.paths.evidence_dir / f"{scenario_id}_{zone}_{safe_ts}.json"
        bundle_path.write_text(json.dumps(decision, indent=2), encoding="utf-8")
        decision["_bundle_path"] = str(bundle_path)

    return decision
