from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict

import pandas as pd


def summarize_flow_window(flow_df: pd.DataFrame, incident_ts: datetime, *, window_minutes: int) -> Dict[str, Any]:
    """
    Summarize the last point in a rolling window ending at incident_ts.
    Expects columns: timestamp, flow, expected, anomaly_score
    """
    t0 = incident_ts - timedelta(minutes=window_minutes)
    w = flow_df[(flow_df["timestamp"] <= incident_ts) & (flow_df["timestamp"] >= t0)]
    if w.empty:
        raise ValueError("flow window is empty; check timestamps and incident time")
    last = w.iloc[-1]
    return {
        "observed": float(last["flow"]),
        "expected": float(last["expected"]),
        "anomaly_score": float(last.get("anomaly_score", 0.0)),
        "window_minutes": int(window_minutes),
        "n_points": int(w.shape[0]),
    }

