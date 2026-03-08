from __future__ import annotations
from pathlib import Path
import numpy as np, pandas as pd
from datetime import timedelta

OUT = Path("data/flows"); OUT.mkdir(parents=True, exist_ok=True)

def daily_pattern(m):
    x = 2*np.pi*(m/1440.0)
    return 50 + 25*np.sin(x - np.pi/2) + 10*np.sin(2*x)

def main():
    start = pd.to_datetime("2026-02-05 00:00:00")
    timestamps = [start + timedelta(minutes=15*i) for i in range(192)]
    expected = [daily_pattern(ts.hour*60+ts.minute) for ts in timestamps]
    flow = [e + np.random.normal(0,2.0) for e in expected]
    df = pd.DataFrame({"timestamp":timestamps,"expected":expected,"flow":flow})
    roll = df["flow"].rolling(window=8, min_periods=8)
    mu, sd = roll.mean(), roll.std().replace(0,np.nan)
    df["anomaly_score"] = ((df["flow"]-mu)/sd).fillna(0.0).clip(-10,10)
    df.to_csv(OUT/"zone-1_base.csv", index=False)
    print("Wrote", OUT/"zone-1_base.csv")

if __name__ == "__main__":
    main()
