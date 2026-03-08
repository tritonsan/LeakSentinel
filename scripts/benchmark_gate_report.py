from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

CLASSES = ["LEAK_CONFIRMED", "IGNORE_PLANNED_OPS", "INVESTIGATE"]


def _parse_report_arg(v: str) -> tuple[str, Path]:
    if "=" not in str(v):
        raise argparse.ArgumentTypeError("Expected --report label=path/to/report.csv")
    key, raw_path = str(v).split("=", 1)
    label = key.strip()
    path = Path(raw_path.strip())
    if not label:
        raise argparse.ArgumentTypeError("Empty report label.")
    return label, path


def _safe_ratio(num: int, den: int) -> float:
    return float(num / den) if den else 0.0


def _ece_binary(df_scored: pd.DataFrame, *, bins: int = 10) -> float:
    if df_scored.empty:
        return 0.0
    x = df_scored.copy()
    x["confidence"] = pd.to_numeric(x["confidence"], errors="coerce").fillna(0.0).clip(0.0, 1.0)
    x["correct"] = (x["expected"].astype(str) == x["predicted"].astype(str)).astype(float)
    total_n = int(len(x))
    if total_n <= 0:
        return 0.0

    ece = 0.0
    for bi in range(int(bins)):
        lo = bi / bins
        hi = (bi + 1) / bins
        if bi == bins - 1:
            bucket = x[(x["confidence"] >= lo) & (x["confidence"] <= hi)]
        else:
            bucket = x[(x["confidence"] >= lo) & (x["confidence"] < hi)]
        n = int(len(bucket))
        if n <= 0:
            continue
        avg_conf = float(bucket["confidence"].mean())
        avg_acc = float(bucket["correct"].mean())
        ece += abs(avg_acc - avg_conf) * (n / total_n)
    return float(ece)


def _metrics(df: pd.DataFrame) -> dict[str, Any]:
    x = df.copy()
    x["expected"] = x["expected"].fillna("").astype(str).str.strip()
    x["predicted"] = x["predicted"].fillna("").astype(str).str.strip()

    scored = x[x["expected"] != ""]
    inv = x[x["expected"] == ""]
    total_scored = int(len(scored))

    out: dict[str, Any] = {
        "scored_n": total_scored,
        "investigate_n": int(len(inv)),
        "accuracy": float((scored["expected"] == scored["predicted"]).mean()) if total_scored else 0.0,
        "ece": _ece_binary(scored, bins=10),
        "inv_false_leak_rate": _safe_ratio(
            int((inv["predicted"] == "LEAK_CONFIRMED").sum()),
            int(len(inv)),
        ),
        "class_support": {},
        "class_recall": {},
        "class_precision": {},
        "errors": {
            "false_negatives_leak": 0,
            "false_positives_leak": 0,
            "false_negatives_planned_ops": 0,
            "false_positives_planned_ops": 0,
        },
    }

    for cls in CLASSES:
        cls_expected = scored[scored["expected"] == cls]
        cls_pred = scored[scored["predicted"] == cls]
        tp = int(((scored["expected"] == cls) & (scored["predicted"] == cls)).sum())
        support = int(len(cls_expected))
        pred_n = int(len(cls_pred))
        out["class_support"][cls] = support
        out["class_recall"][cls] = _safe_ratio(tp, support)
        out["class_precision"][cls] = _safe_ratio(tp, pred_n)

    leak_expected = scored["expected"] == "LEAK_CONFIRMED"
    leak_pred = scored["predicted"] == "LEAK_CONFIRMED"
    planned_expected = scored["expected"] == "IGNORE_PLANNED_OPS"
    planned_pred = scored["predicted"] == "IGNORE_PLANNED_OPS"
    out["errors"]["false_negatives_leak"] = int((leak_expected & (~leak_pred)).sum())
    out["errors"]["false_positives_leak"] = int(((~leak_expected) & leak_pred).sum())
    out["errors"]["false_negatives_planned_ops"] = int((planned_expected & (~planned_pred)).sum())
    out["errors"]["false_positives_planned_ops"] = int(((~planned_expected) & planned_pred).sum())
    return out


def _misclassified_rows(df: pd.DataFrame, *, max_n: int = 10) -> list[dict[str, Any]]:
    x = df.copy()
    x["expected"] = x["expected"].fillna("").astype(str).str.strip()
    x["predicted"] = x["predicted"].fillna("").astype(str).str.strip()
    scored = x[x["expected"] != ""]
    bad = scored[scored["expected"] != scored["predicted"]].copy()
    if bad.empty:
        return []
    keep_cols = [c for c in ["scenario_id", "track", "label", "ablation", "expected", "predicted", "confidence"] if c in bad.columns]
    bad = bad[keep_cols].head(int(max_n))
    out: list[dict[str, Any]] = []
    for _, row in bad.iterrows():
        item = {k: row.get(k) for k in keep_cols}
        if "confidence" in item:
            try:
                item["confidence"] = float(item["confidence"])
            except Exception:
                pass
        out.append(item)
    return out


def _evaluate_gates(
    metrics: dict[str, Any],
    *,
    min_leak_recall: float,
    min_planned_ops_recall: float,
    max_inv_false_leak_rate: float,
    max_ece: float,
) -> list[str]:
    issues: list[str] = []
    leak_recall = float(metrics["class_recall"].get("LEAK_CONFIRMED", 0.0))
    planned_recall = float(metrics["class_recall"].get("IGNORE_PLANNED_OPS", 0.0))
    inv_leak = float(metrics["inv_false_leak_rate"])
    ece = float(metrics["ece"])

    if leak_recall < min_leak_recall:
        issues.append(f"low_leak_recall: {leak_recall:.3f} < {min_leak_recall:.3f}")
    if planned_recall < min_planned_ops_recall:
        issues.append(f"low_planned_ops_recall: {planned_recall:.3f} < {min_planned_ops_recall:.3f}")
    if inv_leak > max_inv_false_leak_rate:
        issues.append(f"high_investigate_false_leak_rate: {inv_leak:.3f} > {max_inv_false_leak_rate:.3f}")
    if ece > max_ece:
        issues.append(f"high_ece: {ece:.3f} > {max_ece:.3f}")
    return issues


def _fmt_pct(v: float) -> str:
    return f"{100.0 * float(v):.1f}%"


def main() -> None:
    ap = argparse.ArgumentParser(description="Gate-oriented benchmark summary for realistic error tracking.")
    ap.add_argument("--report", action="append", required=True, help="Repeatable: label=path/to/benchmark.csv")
    ap.add_argument("--out-json", default="data/_reports/benchmark_gate_latest.json")
    ap.add_argument("--out-md", default="data/_reports/benchmark_gate_latest.md")
    ap.add_argument(
        "--split-ablations",
        action="store_true",
        help="If a report CSV contains multiple ablation values, evaluate each ablation as a separate gate row.",
    )
    ap.add_argument("--min-leak-recall", type=float, default=0.95)
    ap.add_argument("--min-planned-ops-recall", type=float, default=0.80)
    ap.add_argument("--max-inv-false-leak-rate", type=float, default=0.05)
    ap.add_argument("--max-ece", type=float, default=0.20)
    args = ap.parse_args()

    pairs = [_parse_report_arg(v) for v in (args.report or [])]
    payload: dict[str, Any] = {
        "thresholds": {
            "min_leak_recall": float(args.min_leak_recall),
            "min_planned_ops_recall": float(args.min_planned_ops_recall),
            "max_inv_false_leak_rate": float(args.max_inv_false_leak_rate),
            "max_ece": float(args.max_ece),
        },
        "reports": {},
    }

    md_lines = [
        "# LeakSentinel Benchmark Gate Report",
        "",
        "## Thresholds",
        f"- min leak recall: `{args.min_leak_recall:.3f}`",
        f"- min planned-ops recall: `{args.min_planned_ops_recall:.3f}`",
        f"- max investigate false leak rate: `{args.max_inv_false_leak_rate:.3f}`",
        f"- max ECE: `{args.max_ece:.3f}`",
        "",
        "| Set | Accuracy | Leak Recall | Planned-Ops Recall | Inv->Leak % | ECE | Gate |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    md_issue_lines: list[str] = []

    for label, path in pairs:
        if not path.exists():
            item = {"exists": False, "issues": [f"missing_report: {path}"], "metrics": {}}
            payload["reports"][label] = item
            md_lines.append(f"| {label} | n/a | n/a | n/a | n/a | n/a | FAIL (missing) |")
            continue

        df_all = pd.read_csv(path)
        ablations = sorted({str(v).strip() for v in df_all.get("ablation", pd.Series([], dtype=str)).fillna("").tolist() if str(v).strip()})
        slices: list[tuple[str, pd.DataFrame, str]] = []
        if bool(args.split_ablations) and len(ablations) > 1:
            for abl in ablations:
                dfx = df_all[df_all["ablation"].astype(str) == abl].copy()
                slices.append((f"{label}:{abl}", dfx, abl))
        else:
            slices.append((label, df_all, "all"))

        for out_label, dfx, ablation_name in slices:
            metrics = _metrics(dfx)
            misclassified = _misclassified_rows(dfx, max_n=10)
            issues = _evaluate_gates(
                metrics,
                min_leak_recall=float(args.min_leak_recall),
                min_planned_ops_recall=float(args.min_planned_ops_recall),
                max_inv_false_leak_rate=float(args.max_inv_false_leak_rate),
                max_ece=float(args.max_ece),
            )
            ok = not issues
            payload["reports"][out_label] = {
                "exists": True,
                "path": str(path),
                "ablation": ablation_name,
                "ok": ok,
                "issues": issues,
                "metrics": metrics,
                "misclassified_examples": misclassified,
            }
            md_lines.append(
                "| "
                f"{out_label} | "
                f"{metrics['accuracy']:.3f} | "
                f"{metrics['class_recall'].get('LEAK_CONFIRMED', 0.0):.3f} | "
                f"{metrics['class_recall'].get('IGNORE_PLANNED_OPS', 0.0):.3f} | "
                f"{_fmt_pct(metrics['inv_false_leak_rate'])} | "
                f"{metrics['ece']:.3f} | "
                f"{'PASS' if ok else 'FAIL'} |"
            )
            if issues:
                md_lines.append(f"| {out_label} issues | - | - | - | - | - | `{'; '.join(issues)}` |")
            if misclassified:
                md_issue_lines.append(f"### Misclassified: {out_label}")
                md_issue_lines.append("")
                for row in misclassified:
                    md_issue_lines.append(
                        "- "
                        f"scenario=`{row.get('scenario_id', '')}` "
                        f"track=`{row.get('track', '')}` "
                        f"expected=`{row.get('expected', '')}` "
                        f"predicted=`{row.get('predicted', '')}` "
                        f"confidence=`{row.get('confidence', '')}`"
                    )
                md_issue_lines.append("")

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    out_md.write_text("\n".join([*md_lines, *md_issue_lines]), encoding="utf-8")
    print(f"Wrote {out_json}")
    print(f"Wrote {out_md}")


if __name__ == "__main__":
    main()
