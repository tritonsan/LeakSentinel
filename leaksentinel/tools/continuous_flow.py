from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict

import pandas as pd


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _longest_streak(mask: list[bool]) -> tuple[int, int]:
    """
    Returns (best_start_idx, best_len) for the longest contiguous True streak.
    """
    best_start = 0
    best_len = 0
    cur_start = 0
    cur_len = 0
    for i, ok in enumerate(mask):
        if ok:
            if cur_len == 0:
                cur_start = i
            cur_len += 1
            if cur_len > best_len:
                best_len = cur_len
                best_start = cur_start
        else:
            cur_len = 0
    return best_start, best_len


def detect_continuous_flow(
    *,
    flow_df: pd.DataFrame,
    incident_ts: datetime,
    lookback_hours: int = 24,
    min_flow_threshold: float = 5.0,
    min_excess_lpm_threshold: float = 2.5,
    continuous_hours_threshold: float = 2.0,
) -> Dict[str, Any]:
    """
    Detects prolonged elevated flow in a lookback window ending at incident_ts.
    This is a practical "continuous-flow risk" proxy for demo data without raw meter-state signals.
    """
    if flow_df.empty:
        return {
            "detected": False,
            "severity": "low",
            "duration_hours": 0.0,
            "min_flow_lpm": 0.0,
            "mean_excess_lpm": 0.0,
            "confidence": 0.0,
            "recommended_action": "No action; flow series unavailable.",
            "rule": "empty_series",
        }

    t0 = incident_ts - timedelta(hours=max(1, int(lookback_hours)))
    w = flow_df[(flow_df["timestamp"] <= incident_ts) & (flow_df["timestamp"] >= t0)].copy()
    if w.empty:
        return {
            "detected": False,
            "severity": "low",
            "duration_hours": 0.0,
            "min_flow_lpm": 0.0,
            "mean_excess_lpm": 0.0,
            "confidence": 0.0,
            "recommended_action": "No action; no samples in analysis window.",
            "rule": "empty_window",
        }

    w = w.sort_values("timestamp")
    # Fall back gracefully when expected/anomaly columns are missing.
    if "expected" not in w.columns:
        w["expected"] = 0.0
    w["flow"] = pd.to_numeric(w.get("flow"), errors="coerce").fillna(0.0)
    w["expected"] = pd.to_numeric(w.get("expected"), errors="coerce").fillna(0.0)
    w["excess"] = (w["flow"] - w["expected"]).clip(lower=0.0)

    # Estimate point interval in minutes from timestamps.
    if w.shape[0] >= 2:
        step_min = float(
            max(
                1.0,
                (
                    pd.to_datetime(w["timestamp"]).diff().dt.total_seconds().dropna().median()
                    / 60.0
                ),
            )
        )
    else:
        step_min = 15.0

    mask = [
        bool((_to_float(f) >= float(min_flow_threshold)) and (_to_float(ex) >= float(min_excess_lpm_threshold)))
        for f, ex in zip(w["flow"].tolist(), w["excess"].tolist())
    ]
    s_idx, s_len = _longest_streak(mask)
    duration_h = float((s_len * step_min) / 60.0)
    detected = bool(duration_h >= float(continuous_hours_threshold))

    if s_len > 0:
        streak = w.iloc[s_idx : s_idx + s_len]
        min_flow = _to_float(streak["flow"].min(), 0.0)
        mean_excess = _to_float(streak["excess"].mean(), 0.0)
    else:
        min_flow = 0.0
        mean_excess = 0.0

    severity = "low"
    if detected:
        if duration_h >= max(6.0, float(continuous_hours_threshold) * 2.0):
            severity = "high"
        elif duration_h >= max(3.0, float(continuous_hours_threshold) * 1.3):
            severity = "medium"
        else:
            severity = "low"
    confidence = min(0.95, max(0.1, (duration_h / max(0.1, float(continuous_hours_threshold))) * 0.6))

    if not detected:
        action = "No immediate continuous-flow alarm; keep passive monitoring."
    elif severity == "high":
        action = "High continuous-flow risk: prioritize field verification and meter/valve check."
    elif severity == "medium":
        action = "Moderate continuous-flow risk: schedule same-shift inspection."
    else:
        action = "Low continuous-flow risk: validate with secondary evidence."

    return {
        "detected": bool(detected),
        "severity": severity,
        "duration_hours": round(duration_h, 2),
        "min_flow_lpm": round(min_flow, 3),
        "mean_excess_lpm": round(mean_excess, 3),
        "confidence": round(float(confidence), 3),
        "recommended_action": action,
        "rule": "flow>=threshold AND excess>=threshold streak",
    }
