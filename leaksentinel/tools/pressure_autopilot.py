from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import pandas as pd


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _clamp(v: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, float(v))))


def _load_pressure_profile(profile_path: Path) -> pd.DataFrame:
    if not profile_path.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(profile_path)
        if "hour" in df.columns:
            df["hour"] = pd.to_numeric(df["hour"], errors="coerce").fillna(0).astype(int)
        return df
    except Exception:
        return pd.DataFrame()


def build_pressure_plan(
    *,
    incident_ts: datetime,
    zone: str,
    flow_summary: Dict[str, Any],
    decision: str,
    profile_path: Path | None = None,
    min_setpoint_m: float = 35.0,
    max_setpoint_m: float = 70.0,
    target_setpoint_m: float = 52.0,
    track: str = "core",
) -> Dict[str, Any]:
    """
    Produces a deterministic PRV setpoint recommendation.
    It is intentionally transparent and policy-driven for hackathon demo reliability.
    """
    observed = _to_float(flow_summary.get("observed"), 0.0)
    expected = max(1e-6, _to_float(flow_summary.get("expected"), 1.0))
    anomaly = _to_float(flow_summary.get("anomaly_score"), 0.0)
    demand_ratio = observed / expected

    profile_used = False
    profile_notes = "No pressure profile found; fallback estimation used."
    base_pressure = float(target_setpoint_m)

    if profile_path:
        df = _load_pressure_profile(profile_path)
        if not df.empty and "hour" in df.columns:
            hh = int(incident_ts.hour)
            row = df[df["hour"] == hh]
            if not row.empty:
                r = row.iloc[0]
                base_pressure = _to_float(r.get("base_pressure_m"), target_setpoint_m)
                min_setpoint_m = _to_float(r.get("min_setpoint_m"), min_setpoint_m)
                max_setpoint_m = _to_float(r.get("max_setpoint_m"), max_setpoint_m)
                profile_used = True
                profile_notes = f"Profile-guided base pressure selected for hour={hh}."

    current_pressure = _clamp(base_pressure + (demand_ratio - 1.0) * 8.0 + anomaly * 1.8, min_setpoint_m, max_setpoint_m)
    d = str(decision or "INVESTIGATE").strip().upper()

    if d == "LEAK_CONFIRMED":
        # Reduce pressure aggressively to limit escalation while dispatch proceeds.
        adjustment = -7.0
        urgency = "high"
    elif d == "IGNORE_PLANNED_OPS":
        # Conservative tuning; avoid overreaction when planned ops explain anomalies.
        adjustment = -3.0
        urgency = "low"
    else:
        # Investigate path: moderate reduction to lower stress without under-supplying.
        adjustment = -4.5 if anomaly > 0.5 else -2.0
        urgency = "medium"

    if str(track or "").strip().lower() == "real_challenge":
        adjustment -= 1.0  # slightly more conservative for noisier track

    recommended = _clamp(current_pressure + adjustment, min_setpoint_m, max_setpoint_m)
    pressure_drop = max(0.0, current_pressure - recommended)
    expected_risk_delta_pct = _clamp((pressure_drop / max(1.0, current_pressure)) * 32.0, 0.0, 35.0)
    confidence = _clamp(0.65 + (0.1 if profile_used else 0.0) + (0.05 if d == "LEAK_CONFIRMED" else 0.0), 0.0, 0.95)

    return {
        "zone": str(zone),
        "current_pressure_m": round(current_pressure, 2),
        "recommended_setpoint_m": round(recommended, 2),
        "expected_leak_risk_delta_pct": round(expected_risk_delta_pct, 2),
        "response_urgency": urgency,
        "confidence": round(confidence, 3),
        "profile_used": bool(profile_used),
        "notes": profile_notes,
        "bounds": {
            "min_setpoint_m": float(min_setpoint_m),
            "max_setpoint_m": float(max_setpoint_m),
            "target_setpoint_m": float(target_setpoint_m),
        },
    }
