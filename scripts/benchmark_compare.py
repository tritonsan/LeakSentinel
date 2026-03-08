from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def _stats(df: pd.DataFrame, track: str | None = None) -> tuple[float, int, int, float]:
    x = df.copy()
    if track is not None:
        x = x[x["track"].fillna("core").astype(str).str.lower() == str(track).lower()]
    scored = x[x["expected"].fillna("").astype(str).str.strip() != ""]
    inv_rows = x[x["expected"].fillna("").astype(str).str.strip() == ""]
    inv_n = int(len(inv_rows))
    inv_leak_n = int((inv_rows["predicted"].astype(str) == "LEAK_CONFIRMED").sum()) if inv_n else 0
    inv_leak_rate = float(inv_leak_n / inv_n) if inv_n else 0.0
    if scored.empty:
        return 0.0, 0, inv_n, inv_leak_rate
    acc = float((scored["expected"].astype(str) == scored["predicted"].astype(str)).mean())
    return acc, int(len(scored)), inv_n, inv_leak_rate


def _parse_report_arg(v: str) -> tuple[str, Path]:
    if "=" not in str(v):
        raise argparse.ArgumentTypeError("Expected --report label=path/to/report.csv")
    k, p = str(v).split("=", 1)
    key = str(k).strip()
    path = Path(str(p).strip())
    if not key:
        raise argparse.ArgumentTypeError("Empty report label.")
    return key, path


def main() -> None:
    ap = argparse.ArgumentParser(description="Compare multiple benchmark CSV reports in one markdown table.")
    ap.add_argument(
        "--report",
        action="append",
        required=True,
        help="Repeatable: label=path/to/benchmark.csv (e.g. tuning=data/_reports/xxx.csv)",
    )
    ap.add_argument("--out", default="data/_reports/benchmark_compare.md")
    args = ap.parse_args()

    pairs = [_parse_report_arg(v) for v in (args.report or [])]
    rows: list[str] = []
    rows.append("# LeakSentinel Benchmark Comparison")
    rows.append("")
    rows.append("| Set | Overall Acc | Core Acc | Real Challenge Acc | Scored N | Investigate N | Inv->Leak % |")
    rows.append("|---|---:|---:|---:|---:|---:|---:|")

    for label, path in pairs:
        if not path.exists():
            rows.append(f"| {label} | n/a | n/a | n/a | 0 | 0 | n/a |")
            continue
        df = pd.read_csv(path)
        overall_acc, scored_n, inv_n, inv_leak_rate = _stats(df, track=None)
        core_acc, _, _, _ = _stats(df, track="core")
        real_acc, _, _, _ = _stats(df, track="real_challenge")
        rows.append(
            f"| {label} | {overall_acc:.3f} | {core_acc:.3f} | {real_acc:.3f} | {scored_n} | {inv_n} | {100.0 * inv_leak_rate:.1f}% |"
        )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(rows), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
