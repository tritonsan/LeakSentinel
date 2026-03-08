from __future__ import annotations

from datetime import datetime

import pandas as pd

from leaksentinel.tools.continuous_flow import detect_continuous_flow


def test_detect_continuous_flow_flags_prolonged_excess() -> None:
    ts = pd.date_range("2026-02-05T00:00:00", periods=16, freq="15min")
    df = pd.DataFrame(
        {
            "timestamp": ts,
            "expected": [20.0] * len(ts),
            "flow": [21.0, 22.0, 21.5, 21.2, 27.0, 27.2, 26.9, 27.1, 27.3, 27.1, 27.0, 26.8, 22.0, 21.5, 21.0, 20.5],
        }
    )
    out = detect_continuous_flow(
        flow_df=df,
        incident_ts=datetime.fromisoformat("2026-02-05T03:45:00"),
        lookback_hours=6,
        min_flow_threshold=5.0,
        min_excess_lpm_threshold=2.0,
        continuous_hours_threshold=1.5,
    )
    assert out["detected"] is True
    assert float(out["duration_hours"]) >= 1.5


def test_detect_continuous_flow_handles_empty_series() -> None:
    df = pd.DataFrame(columns=["timestamp", "expected", "flow"])
    out = detect_continuous_flow(
        flow_df=df,
        incident_ts=datetime.fromisoformat("2026-02-05T03:45:00"),
    )
    assert out["detected"] is False
