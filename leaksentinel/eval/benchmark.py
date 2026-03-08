from __future__ import annotations

import csv
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np

from leaksentinel.orchestrator import run_scenario
from leaksentinel.tools.ops import find_planned_ops


CLASSES = ["LEAK_CONFIRMED", "IGNORE_PLANNED_OPS", "INVESTIGATE"]


def _utc_ts() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _ops_bounds(incident_timestamp: str, window_minutes: int) -> tuple[str, str]:
    """
    Must match the orchestrator's window convention: total window length centered on ts.
    """
    ts = datetime.fromisoformat(incident_timestamp)
    half = max(1, int(window_minutes) // 2)
    # Keep as naive ISO like other parts of the repo (no tz suffix).
    start = (ts - timedelta(minutes=half)).replace(microsecond=0).isoformat()
    end = (ts + timedelta(minutes=half)).replace(microsecond=0).isoformat()
    return start, end


def validate_dataset(
    *,
    scenario_pack_path: Path,
    ops_db_path: Path,
    manifest_path: Path,
) -> List[str]:
    """
    Returns a list of warnings about dataset / label inconsistencies.

    This is intentionally "best effort" and should never block local experimentation unless strict mode is enabled.
    """
    warnings: List[str] = []
    pack = json.loads(scenario_pack_path.read_text(encoding="utf-8"))
    scenarios = pack.get("scenarios", [])

    # Load manifest once.
    manifest_rows: Dict[str, Dict[str, Any]] = {}
    if manifest_path.exists():
        try:
            import pandas as pd

            df = pd.read_csv(manifest_path)
            for _, r in df.iterrows():
                manifest_rows[str(r.get("scenario_id"))] = dict(r)
        except Exception as e:
            warnings.append(f"manifest_read_failed: {manifest_path} error={e}")
    else:
        warnings.append(f"manifest_missing: {manifest_path}")

    pack_ids: list[str] = []
    for s in scenarios:
        sid = str(s.get("scenario_id"))
        pack_ids.append(sid)
        label = str(s.get("label") or "")
        planned_id = str(s.get("planned_op_id") or "").strip()
        ts = str(s.get("incident_timestamp") or "")
        wm = int(s.get("window_minutes") or 0)

        if not ts or wm <= 0:
            warnings.append(f"{sid}: invalid incident_timestamp/window_minutes (ts={ts!r}, window_minutes={wm})")
            continue

        # Planned-ops label should have an explicit planned op id.
        if label.strip().lower() == "planned_ops" and not planned_id:
            warnings.append(f"{sid}: label=planned_ops but planned_op_id is empty in scenario_pack.json")

        # Manifest existence and artifact checks.
        m = manifest_rows.get(sid)
        if not m:
            warnings.append(f"{sid}: missing manifest row in {manifest_path}")
        else:
            v = m.get("planned_op_id")
            if isinstance(v, float) and math.isnan(v):
                v = ""
            m_planned = str(v or "").strip()
            if m_planned != planned_id:
                warnings.append(f"{sid}: planned_op_id mismatch (scenario_pack={planned_id!r}, manifest={m_planned!r})")
            for k in ("flow_file", "thermal_file", "spectrogram_file"):
                vv = m.get(k)
                if isinstance(vv, float) and math.isnan(vv):
                    vv = ""
                p = str(vv or "").strip()
                if p and not Path(p).exists():
                    warnings.append(f"{sid}: missing artifact file: {k}={p}")

        # Ops DB overlap consistency.
        start, end = _ops_bounds(ts, wm)
        ops = find_planned_ops(ops_db_path=ops_db_path, zone=str(s.get("zone")), start=start, end=end)
        found = bool(ops.get("planned_op_found"))
        found_ids = set(str(x) for x in (ops.get("planned_op_ids") or []) if x)

        if planned_id:
            if not found or planned_id not in found_ids:
                warnings.append(
                    f"{sid}: planned_op_id={planned_id} but ops_db has no overlap in window {start}..{end} (found_ids={sorted(found_ids)})"
                )
        else:
            # A leak can occur during planned ops; that's one of the core product stories (ops suppression vs override).
            # For non-leak labels, an overlap is usually a dataset inconsistency.
            if found and label.strip().lower() != "leak":
                warnings.append(
                    f"{sid}: planned_op_id is empty but ops_db overlaps window {start}..{end} (found_ids={sorted(found_ids)})"
                )

    # Diversity checks: repeated artifacts can inflate benchmark confidence.
    try:
        spec_counter: Dict[str, int] = {}
        for sid in pack_ids:
            m = manifest_rows.get(sid) or {}
            vv = m.get("spectrogram_file")
            if isinstance(vv, float) and math.isnan(vv):
                vv = ""
            sp = str(vv or "").strip()
            if sp:
                spec_counter[sp] = int(spec_counter.get(sp, 0)) + 1
        repeated = sorted([(k, v) for k, v in spec_counter.items() if v > 1], key=lambda x: x[1], reverse=True)
        if repeated:
            top = ", ".join([f"{Path(k).name}x{v}" for k, v in repeated[:5]])
            warnings.append(
                "dataset_diversity_warning: repeated spectrogram artifacts detected in current pack "
                f"(examples: {top})"
            )
    except Exception:
        pass

    return warnings


def expected_decision_from_label(label: str) -> Optional[str]:
    """
    Returns expected decision for benchmark 3-class task.
    Investigate scenarios are excluded from primary accuracy (return None).
    """
    lab = (label or "").strip().lower()
    if lab == "leak":
        return "LEAK_CONFIRMED"
    if lab == "planned_ops":
        return "IGNORE_PLANNED_OPS"
    if lab == "normal":
        return "INVESTIGATE"
    if lab == "investigate":
        return None
    return None


def _confusion_matrix(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    cm = {e: {p: 0 for p in CLASSES} for e in CLASSES}
    for r in rows:
        e = r.get("expected")
        p = r.get("predicted")
        if e in cm and p in cm[e]:
            cm[e][p] += 1
    return cm


def _precision_recall(cm: Dict[str, Dict[str, int]]) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    for cls in CLASSES:
        tp = cm[cls][cls]
        fp = sum(cm[e][cls] for e in CLASSES if e != cls)
        fn = sum(cm[cls][p] for p in CLASSES if p != cls)
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) else 0.0
        out[cls] = {"precision": float(prec), "recall": float(rec), "f1": float(f1), "support": float(tp + fn)}
    return out


def _latency_stats(ms: List[float]) -> Dict[str, float]:
    if not ms:
        return {"mean_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0}
    arr = np.asarray(ms, dtype=np.float64)
    return {
        "mean_ms": float(arr.mean()),
        "p50_ms": float(np.percentile(arr, 50)),
        "p95_ms": float(np.percentile(arr, 95)),
    }


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _clamp(v: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, float(v))))


def _impact_consistency_score(rows_all: List[Dict[str, Any]]) -> float:
    grouped: Dict[str, List[float]] = {}
    any_covered = False
    for r in rows_all:
        if not bool(r.get("impact_covered")):
            continue
        any_covered = True
        cls = str(r.get("predicted") or "UNKNOWN")
        val = abs(_to_float(r.get("impact_expected_total_usd"), 0.0))
        if val <= 0.0:
            continue
        grouped.setdefault(cls, []).append(val)

    scores: List[float] = []
    for vals in grouped.values():
        if len(vals) < 2:
            continue
        arr = np.asarray(vals, dtype=np.float64)
        mean_v = float(arr.mean())
        if mean_v <= 1e-9:
            continue
        cv = float(arr.std() / mean_v)
        scores.append(float(1.0 / (1.0 + cv)))
    if scores:
        return float(np.mean(np.asarray(scores, dtype=np.float64)))
    return 1.0 if any_covered else 0.0


def _confidence_calibration_metrics(rows: List[Dict[str, Any]], *, bins: int = 10) -> Dict[str, Any]:
    scored = [r for r in rows if str(r.get("expected") or "").strip().upper() in CLASSES]
    if not scored:
        return {"brier_score": 0.0, "ece": 0.0, "bins": []}

    n_bins = max(2, int(bins))
    brier_vals: List[float] = []
    bin_acc: List[float] = [0.0] * n_bins
    bin_conf: List[float] = [0.0] * n_bins
    bin_cnt: List[int] = [0] * n_bins

    for r in scored:
        pred = str(r.get("predicted") or "")
        exp = str(r.get("expected") or "")
        conf = _clamp(_to_float(r.get("confidence"), 0.0), 0.0, 1.0)
        # Approximate class distribution from top-1 confidence.
        rem = max(0.0, 1.0 - conf)
        p = {c: rem / float(max(1, len(CLASSES) - 1)) for c in CLASSES}
        if pred in p:
            p[pred] = conf
        y = {c: 1.0 if c == exp else 0.0 for c in CLASSES}
        brier_vals.append(float(sum((p[c] - y[c]) ** 2 for c in CLASSES)))

        idx = min(n_bins - 1, int(conf * n_bins))
        bin_cnt[idx] += 1
        bin_conf[idx] += conf
        bin_acc[idx] += 1.0 if pred == exp else 0.0

    n = float(len(scored))
    ece = 0.0
    bins_out: List[Dict[str, Any]] = []
    for i in range(n_bins):
        c = bin_cnt[i]
        if c <= 0:
            continue
        lo = float(i) / float(n_bins)
        hi = float(i + 1) / float(n_bins)
        avg_conf = bin_conf[i] / float(c)
        avg_acc = bin_acc[i] / float(c)
        ece += (float(c) / n) * abs(avg_acc - avg_conf)
        bins_out.append(
            {
                "bin": i,
                "range": f"[{lo:.1f}, {hi:.1f})",
                "count": int(c),
                "avg_confidence": float(avg_conf),
                "avg_accuracy": float(avg_acc),
                "abs_gap": float(abs(avg_acc - avg_conf)),
            }
        )

    return {
        "brier_score": float(np.mean(np.asarray(brier_vals, dtype=np.float64))),
        "ece": float(ece),
        "bins": bins_out,
    }


def _summary_from_rows(
    *,
    scored_rows: List[Dict[str, Any]],
    rows_all: List[Dict[str, Any]],
    inv_bucket: List[Dict[str, Any]],
    lat_ms: List[float],
    n_total: int,
) -> Dict[str, Any]:
    cm = _confusion_matrix(scored_rows)
    pr = _precision_recall(cm)
    acc = 0.0
    if scored_rows:
        acc = sum(1 for r in scored_rows if r["expected"] == r["predicted"]) / float(len(scored_rows))
    inv_leak_n = int(sum(1 for r in inv_bucket if str(r.get("predicted")) == "LEAK_CONFIRMED"))
    inv_total = int(len(inv_bucket))
    inv_leak_rate = float(inv_leak_n / inv_total) if inv_total > 0 else 0.0
    actionability_n = int(sum(1 for r in rows_all if bool(r.get("actionable"))))
    counterfactual_flip_n = int(sum(1 for r in rows_all if bool(r.get("counterfactual_flipped"))))
    impact_covered_n = int(sum(1 for r in rows_all if bool(r.get("impact_covered"))))
    biz_impact_covered_n = int(sum(1 for r in rows_all if bool(r.get("business_impact_covered"))))
    co2e_covered_n = int(sum(1 for r in rows_all if bool(r.get("co2e_covered"))))
    feedback_applicable_n = int(sum(1 for r in rows_all if int(r.get("similar_mistakes_n") or 0) > 0))
    feedback_effective_n = int(sum(1 for r in rows_all if bool(r.get("feedback_effective"))))
    repeat_fp_reduction_sum = float(
        sum(_to_float(r.get("repeat_fp_risk_reduction_pct"), 0.0) for r in rows_all if int(r.get("similar_mistakes_n") or 0) > 0)
    )
    n_all = max(1, int(len(rows_all)))
    calib = _confidence_calibration_metrics(scored_rows)
    return {
        "n_total": int(n_total),
        "n_scored": int(len(scored_rows)),
        "n_investigate_bucket": int(len(inv_bucket)),
        "accuracy": float(acc),
        "confusion_matrix": cm,
        "per_class": pr,
        "latency": _latency_stats(lat_ms),
        "actionability_rate": float(actionability_n / n_all),
        "counterfactual_flip_rate": float(counterfactual_flip_n / n_all),
        "impact_coverage_rate": float(impact_covered_n / n_all),
        "business_impact_coverage_rate": float(biz_impact_covered_n / n_all),
        "co2e_estimation_coverage_rate": float(co2e_covered_n / n_all),
        "impact_consistency_score": float(_impact_consistency_score(rows_all)),
        "repeat_fp_reduction_rate": float(repeat_fp_reduction_sum / (100.0 * feedback_applicable_n)) if feedback_applicable_n > 0 else 0.0,
        "feedback_effectiveness_rate": float(feedback_effective_n / feedback_applicable_n) if feedback_applicable_n > 0 else 0.0,
        "brier_score": float(calib.get("brier_score", 0.0)),
        "ece": float(calib.get("ece", 0.0)),
        "confidence_calibration_bins": list(calib.get("bins") or []),
        "investigate_bucket": {
            "predicted_counts": {c: int(sum(1 for r in inv_bucket if r["predicted"] == c)) for c in CLASSES},
            "leak_confirmed_n": inv_leak_n,
            "leak_confirmed_rate": inv_leak_rate,
        },
    }


@dataclass
class BenchmarkResult:
    meta: Dict[str, Any]
    rows: List[Dict[str, Any]]
    summary: Dict[str, Any]


def run_benchmark(
    *,
    mode: str,
    scenario_pack_path: Path,
    ablations: List[str],
    out_dir: Path,
    manifest_path: Optional[Path] = None,
    ops_db_path: Optional[Path] = None,
    strict: bool = False,
) -> BenchmarkResult:
    pack = json.loads(scenario_pack_path.read_text(encoding="utf-8"))
    scenarios = pack.get("scenarios", [])
    manifest_path_resolved = Path(manifest_path) if manifest_path is not None else Path(
        os.getenv("LEAKSENTINEL_MANIFEST_PATH", "data/manifest/manifest.csv")
    )
    ops_db_path_resolved = Path(ops_db_path) if ops_db_path is not None else Path(
        os.getenv("LEAKSENTINEL_OPS_DB_PATH", "data/ops_db.json")
    )

    warnings = validate_dataset(
        scenario_pack_path=scenario_pack_path,
        ops_db_path=ops_db_path_resolved,
        manifest_path=manifest_path_resolved,
    )
    blocking_warnings = [w for w in warnings if not str(w).startswith("dataset_diversity_warning:")]
    if blocking_warnings and strict:
        raise ValueError("dataset validation failed:\n" + "\n".join(warnings))

    all_rows: List[Dict[str, Any]] = []
    summaries: Dict[str, Any] = {}

    prev_scenarios_env = os.environ.get("LEAKSENTINEL_SCENARIOS_PATH")
    prev_manifest_env = os.environ.get("LEAKSENTINEL_MANIFEST_PATH")
    try:
        os.environ["LEAKSENTINEL_SCENARIOS_PATH"] = str(scenario_pack_path)
        os.environ["LEAKSENTINEL_MANIFEST_PATH"] = str(manifest_path_resolved)

        for ablation in ablations:
            rows: List[Dict[str, Any]] = []
            rows_all: List[Dict[str, Any]] = []
            lat_ms: List[float] = []
            inv_bucket: List[Dict[str, Any]] = []

            for s in scenarios:
                sid = str(s.get("scenario_id"))
                label = str(s.get("label"))
                track = str(s.get("track") or "core").strip().lower()
                expected = expected_decision_from_label(label)

                t0 = time.perf_counter()
                out = run_scenario(scenario_id=sid, mode=mode, write_bundle=False, ablation=ablation)
                dt = (time.perf_counter() - t0) * 1000.0
                lat_ms.append(float(dt))

                pred = str(out.get("decision"))
                conf = float(out.get("confidence", 0.0))
                ner_v2 = out.get("next_evidence_request_v2", {}) if isinstance(out.get("next_evidence_request_v2"), dict) else {}
                ner_v1 = out.get("next_evidence_request", {}) if isinstance(out.get("next_evidence_request"), dict) else {}
                actionable = bool(ner_v2) or bool(ner_v1)
                cf_v2 = out.get("counterfactual_v2", {}) if isinstance(out.get("counterfactual_v2"), dict) else {}
                cf_v1 = out.get("counterfactual", {}) if isinstance(out.get("counterfactual"), dict) else {}
                cf_v2_delta = cf_v2.get("decision_delta", {}) if isinstance(cf_v2.get("decision_delta"), dict) else {}
                cf_flipped = bool(cf_v2_delta.get("flipped")) if cf_v2 else False
                if not cf_flipped and cf_v1:
                    cf_flipped = str(cf_v1.get("decision", "")).strip().upper() not in {"", pred}
                impact_v2 = out.get("impact_estimate_v2", {}) if isinstance(out.get("impact_estimate_v2"), dict) else {}
                impact_v1 = out.get("impact_estimate", {}) if isinstance(out.get("impact_estimate"), dict) else {}
                impact_covered = bool(impact_v2) or bool(impact_v1)
                impact_total = _to_float(impact_v2.get("expected_total_impact_usd"), float("nan"))
                if math.isnan(impact_total):
                    impact_total = _to_float(impact_v1.get("avoided_false_dispatch_estimate"), 0.0) + _to_float(
                        impact_v1.get("avoided_leak_loss_estimate"), 0.0
                    )
                scorecard = out.get("scorecard", {}) if isinstance(out.get("scorecard"), dict) else {}
                business_impact_covered = bool(scorecard) and ("estimated_cost_saved_usd" in scorecard)
                co2e_covered = bool(scorecard) and ("estimated_co2e_kg_avoided" in scorecard)
                analysis_version = str(out.get("analysis_version", "v1") or "v1")
                ev = out.get("evidence", {}) if isinstance(out.get("evidence"), dict) else {}
                similar_mistakes_n = int(len(ev.get("similar_mistakes", []) or [])) if isinstance(ev.get("similar_mistakes"), list) else 0
                closed_loop = out.get("closed_loop_summary_v1", {}) if isinstance(out.get("closed_loop_summary_v1"), dict) else {}
                repeat_fp_risk_reduction_pct = _to_float(closed_loop.get("repeat_fp_risk_reduction_pct"), 0.0)
                feedback_effective = bool(closed_loop.get("feedback_effective")) or (
                    bool((out.get("_runtime") or {}).get("feedback_memory", {}).get("policy")) and similar_mistakes_n > 0
                )

                row = {
                    "scenario_id": sid,
                    "label": label,
                    "expected": expected or "",
                    "predicted": pred,
                    "confidence": conf,
                    "latency_ms": float(dt),
                    "mode": mode,
                    "ablation": ablation,
                    "bedrock_used": bool((out.get("_runtime") or {}).get("bedrock", {}).get("used")),
                    "track": track,
                    "analysis_version": analysis_version,
                    "actionable": bool(actionable),
                    "counterfactual_flipped": bool(cf_flipped),
                    "impact_covered": bool(impact_covered),
                    "impact_expected_total_usd": float(impact_total),
                    "business_impact_covered": bool(business_impact_covered),
                    "co2e_covered": bool(co2e_covered),
                    "similar_mistakes_n": int(similar_mistakes_n),
                    "repeat_fp_risk_reduction_pct": float(repeat_fp_risk_reduction_pct),
                    "feedback_effective": bool(feedback_effective),
                }
                all_rows.append(row)
                rows_all.append(row)

                if expected is None:
                    inv_bucket.append(row)
                else:
                    rows.append(row)

            summary = _summary_from_rows(
                scored_rows=rows,
                rows_all=rows_all,
                inv_bucket=inv_bucket,
                lat_ms=lat_ms,
                n_total=len(scenarios),
            )
            tracks = sorted({str(r.get("track") or "core") for r in rows_all})
            by_track: Dict[str, Any] = {}
            for tr in tracks:
                tr_rows_all = [r for r in rows_all if str(r.get("track") or "core") == tr]
                tr_rows = [r for r in rows if str(r.get("track") or "core") == tr]
                tr_inv = [r for r in inv_bucket if str(r.get("track") or "core") == tr]
                tr_lat = [float(r.get("latency_ms", 0.0)) for r in tr_rows_all]
                by_track[tr] = _summary_from_rows(
                    scored_rows=tr_rows,
                    rows_all=tr_rows_all,
                    inv_bucket=tr_inv,
                    lat_ms=tr_lat,
                    n_total=len(tr_rows_all),
                )
            summary["by_track"] = by_track
            summaries[ablation] = summary
    finally:
        if prev_scenarios_env is None:
            os.environ.pop("LEAKSENTINEL_SCENARIOS_PATH", None)
        else:
            os.environ["LEAKSENTINEL_SCENARIOS_PATH"] = prev_scenarios_env
        if prev_manifest_env is None:
            os.environ.pop("LEAKSENTINEL_MANIFEST_PATH", None)
        else:
            os.environ["LEAKSENTINEL_MANIFEST_PATH"] = prev_manifest_env

    ts = _utc_ts().replace(":", "-")
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"benchmark_{mode}_{ts}.csv"
    md_path = out_dir / f"benchmark_{mode}_{ts}.md"

    # Write CSV
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(
            f,
            fieldnames=[
                "scenario_id",
                "label",
                "expected",
                "predicted",
                "confidence",
                "latency_ms",
                "mode",
                "ablation",
                "bedrock_used",
                "track",
                "analysis_version",
                "actionable",
                "counterfactual_flipped",
                "impact_covered",
                "impact_expected_total_usd",
                "business_impact_covered",
                "co2e_covered",
                "similar_mistakes_n",
                "repeat_fp_risk_reduction_pct",
                "feedback_effective",
            ],
        )
        wr.writeheader()
        wr.writerows(all_rows)

    # Write Markdown summary
    lines: List[str] = []
    lines.append(f"# LeakSentinel Benchmark Report")
    lines.append("")
    lines.append(f"- Timestamp (UTC): `{_utc_ts()}`")
    lines.append(f"- Mode: `{mode}`")
    lines.append(f"- Ablations: `{', '.join(ablations)}`")
    lines.append("")

    if warnings:
        lines.append("## Dataset Validation Warnings")
        lines.append("")
        for w in warnings[:50]:
            lines.append(f"- {w}")
        if len(warnings) > 50:
            lines.append(f"- ... {len(warnings) - 50} more")
        lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append(
        "| Ablation | Accuracy | Mean ms | P50 ms | P95 ms | Scored N | Investigate N | Inv->Leak % | Actionability % | CF Flip % | Impact Cov % | Biz Impact Cov % | CO2e Cov % | Repeat FP Red. % | Feedback Eff. % | Brier | ECE | Impact Consistency |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for ab in ablations:
        s = summaries[ab]
        lat = s["latency"]
        inv_leak_rate = float((s.get("investigate_bucket") or {}).get("leak_confirmed_rate", 0.0))
        lines.append(
            f"| `{ab}` | {s['accuracy']:.3f} | {lat['mean_ms']:.1f} | {lat['p50_ms']:.1f} | {lat['p95_ms']:.1f} | {s['n_scored']} | {s['n_investigate_bucket']} | {100.0 * inv_leak_rate:.1f}% | {100.0 * float(s.get('actionability_rate', 0.0)):.1f}% | {100.0 * float(s.get('counterfactual_flip_rate', 0.0)):.1f}% | {100.0 * float(s.get('impact_coverage_rate', 0.0)):.1f}% | {100.0 * float(s.get('business_impact_coverage_rate', 0.0)):.1f}% | {100.0 * float(s.get('co2e_estimation_coverage_rate', 0.0)):.1f}% | {100.0 * float(s.get('repeat_fp_reduction_rate', 0.0)):.1f}% | {100.0 * float(s.get('feedback_effectiveness_rate', 0.0)):.1f}% | {float(s.get('brier_score', 0.0)):.3f} | {float(s.get('ece', 0.0)):.3f} | {float(s.get('impact_consistency_score', 0.0)):.3f} |"
        )
    lines.append("")

    for ab in ablations:
        s = summaries[ab]
        bt = s.get("by_track", {})
        if bt:
            lines.append(f"## Track Summary: `{ab}`")
            lines.append("")
            lines.append(
                "| Track | Accuracy | Mean ms | P50 ms | P95 ms | Scored N | Investigate N | Inv->Leak % | Actionability % | CF Flip % | Impact Cov % | Biz Impact Cov % | CO2e Cov % | Repeat FP Red. % | Feedback Eff. % | Brier | ECE | Impact Consistency | Total N |"
            )
            lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
            for tr, ts in bt.items():
                tlat = ts["latency"]
                tinv_rate = float((ts.get("investigate_bucket") or {}).get("leak_confirmed_rate", 0.0))
                lines.append(
                    f"| `{tr}` | {ts['accuracy']:.3f} | {tlat['mean_ms']:.1f} | {tlat['p50_ms']:.1f} | {tlat['p95_ms']:.1f} | {ts['n_scored']} | {ts['n_investigate_bucket']} | {100.0 * tinv_rate:.1f}% | {100.0 * float(ts.get('actionability_rate', 0.0)):.1f}% | {100.0 * float(ts.get('counterfactual_flip_rate', 0.0)):.1f}% | {100.0 * float(ts.get('impact_coverage_rate', 0.0)):.1f}% | {100.0 * float(ts.get('business_impact_coverage_rate', 0.0)):.1f}% | {100.0 * float(ts.get('co2e_estimation_coverage_rate', 0.0)):.1f}% | {100.0 * float(ts.get('repeat_fp_reduction_rate', 0.0)):.1f}% | {100.0 * float(ts.get('feedback_effectiveness_rate', 0.0)):.1f}% | {float(ts.get('brier_score', 0.0)):.3f} | {float(ts.get('ece', 0.0)):.3f} | {float(ts.get('impact_consistency_score', 0.0)):.3f} | {ts['n_total']} |"
                )
            lines.append("")

        lines.append(f"## Confusion Matrix: `{ab}`")
        lines.append("")
        cm = s["confusion_matrix"]
        lines.append("| expected \\ predicted | " + " | ".join(CLASSES) + " |")
        lines.append("|---|" + "|".join(["---:"] * len(CLASSES)) + "|")
        for e in CLASSES:
            lines.append("| " + e + " | " + " | ".join(str(cm[e][p]) for p in CLASSES) + " |")
        lines.append("")

        lines.append(f"## Per-Class Precision/Recall/F1: `{ab}`")
        lines.append("")
        lines.append("| Class | Precision | Recall | F1 | Support |")
        lines.append("|---|---:|---:|---:|---:|")
        for cls in CLASSES:
            pr = s["per_class"][cls]
            lines.append(
                f"| {cls} | {pr['precision']:.3f} | {pr['recall']:.3f} | {pr['f1']:.3f} | {int(pr['support'])} |"
            )
        lines.append("")

        ib = s["investigate_bucket"]["predicted_counts"]
        lines.append(f"## Investigate Bucket (excluded from scoring): `{ab}`")
        lines.append("")
        lines.append("| Predicted | Count |")
        lines.append("|---|---:|")
        for cls in CLASSES:
            lines.append(f"| {cls} | {ib.get(cls, 0)} |")
        lines.append("")
        lines.append(f"- Investigate false leak rate: `{100.0 * float(s['investigate_bucket'].get('leak_confirmed_rate', 0.0)):.1f}%`")
        lines.append("")
        c_bins = s.get("confidence_calibration_bins", []) if isinstance(s.get("confidence_calibration_bins"), list) else []
        if c_bins:
            lines.append(f"## Confidence Calibration Bins: `{ab}`")
            lines.append("")
            lines.append("| Bin | Range | Count | Avg Conf | Avg Acc | |Acc-Conf| |")
            lines.append("|---:|---|---:|---:|---:|---:|")
            for b in c_bins:
                lines.append(
                    f"| {int(b.get('bin', 0))} | {str(b.get('range', '-'))} | {int(b.get('count', 0))} | {float(b.get('avg_confidence', 0.0)):.3f} | {float(b.get('avg_accuracy', 0.0)):.3f} | {float(b.get('abs_gap', 0.0)):.3f} |"
                )
            lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")

    meta = {
        "csv": str(csv_path),
        "md": str(md_path),
        "ts": _utc_ts(),
        "mode": mode,
        "analysis_versions": sorted({str(r.get("analysis_version") or "v1") for r in all_rows}),
        "scenario_pack": str(scenario_pack_path),
        "manifest": str(manifest_path_resolved),
        "ops_db": str(ops_db_path_resolved),
        "scenarios_n": int(len(scenarios)),
        "ablations": ablations,
        "dataset_warnings_n": int(len(warnings)),
    }
    return BenchmarkResult(meta=meta, rows=all_rows, summary=summaries)
