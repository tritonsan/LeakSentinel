from __future__ import annotations

from pathlib import Path
from datetime import timedelta
import numpy as np
import pandas as pd


OUT = Path("data/flows")
OUT.mkdir(parents=True, exist_ok=True)


def daily_pattern(m: float) -> float:
    x = 2 * np.pi * (m / 1440.0)
    return float(50 + 25 * np.sin(x - np.pi / 2) + 10 * np.sin(2 * x))


def main() -> None:
    start = pd.to_datetime("2026-02-05 00:00:00")
    timestamps = [start + timedelta(minutes=15 * i) for i in range(192)]  # 48 hours
    expected = [daily_pattern(ts.hour * 60 + ts.minute) for ts in timestamps]
    flow = [e + float(np.random.normal(0, 2.0)) for e in expected]
    df = pd.DataFrame({"timestamp": timestamps, "expected": expected, "flow": flow})

    # Rolling z-score as a simple anomaly score.
    roll = df["flow"].rolling(window=8, min_periods=8)
    mu = roll.mean()
    sd = roll.std().replace(0, np.nan)
    df["anomaly_score"] = ((df["flow"] - mu) / sd).fillna(0.0).clip(-10, 10)

    out = OUT / "zone-1_base.csv"
    df.to_csv(out, index=False)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()

