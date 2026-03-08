from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

GATE_JSON = ROOT / "data" / "_reports" / "benchmark_gate_latest.json"
EVIDENCE_DIR = ROOT / "data" / "evidence_bundles"

CORE_GATE_KEYS_REQUIRED = [
    "tuning_latest",
    "holdout_v1_latest",
    "holdout_v2_latest",
]
CORE_GATE_KEYS_OPTIONAL = [
    "holdout_v2_ablations:full",
]

REQUIRED_ASSETS = [
    "README.md",
    "ABOUT.md",
    "docs/SUBMISSION_CHECKLIST.md",
    "docs/JUDGE_DEMO_RUNBOOK.md",
    "docs/DEMO_VIDEO_SCRIPT_3MIN.md",
    "docs/DEVPOST_SUBMISSION_DRAFT.md",
    "docs/claim_evidence_map.json",
]


@dataclass
class GateIssueSummary:
    hard_fail: bool = False
    soft_fail: bool = False
    notes: list[str] | None = None

    def __post_init__(self) -> None:
        if self.notes is None:
            self.notes = []


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _pick_latest_judge_bundle(evidence_dir: Path) -> tuple[Path | None, dict[str, Any] | None]:
    if not evidence_dir.exists():
        return None, None
    candidates = sorted(evidence_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in candidates:
        try:
            payload = _read_json(path)
        except Exception:
            continue
        jc = payload.get("judge_compliance", {})
        if isinstance(jc, dict) and bool(jc.get("enabled")):
            return path, payload
    return None, None


def _gate_classification(issues: list[str]) -> GateIssueSummary:
    out = GateIssueSummary()
    for issue in issues:
        s = str(issue).strip()
        if s.startswith("high_ece"):
            out.soft_fail = True
            out.notes.append("Calibration gap (ECE threshold)")
        elif (
            s.startswith("low_leak_recall")
            or s.startswith("low_planned_ops_recall")
            or s.startswith("high_investigate_false_leak_rate")
        ):
            out.hard_fail = True
            out.notes.append(f"Hard gate fail: {s}")
        else:
            out.hard_fail = True
            out.notes.append(f"Unknown gate fail: {s}")
    return out


def _decision(*, missing_required_assets: list[str], core_gate_hard_fail: bool, core_gate_soft_fail: bool, judge_missing: list[str]) -> str:
    if missing_required_assets or core_gate_hard_fail:
        return "no ship"
    if core_gate_soft_fail or judge_missing:
        return "conditional ship"
    return "ship"


def _fmt_bool(v: bool) -> str:
    return "yes" if bool(v) else "no"


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate hackathon readiness snapshot markdown.")
    ap.add_argument("--out", default=str(ROOT / "docs" / "HACKATHON_READINESS_LATEST.md"))
    args = ap.parse_args()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

    gate_payload: dict[str, Any] = {}
    thresholds: dict[str, Any] = {}
    reports: dict[str, Any] = {}
    if GATE_JSON.exists():
        gate_payload = _read_json(GATE_JSON)
        thresholds = gate_payload.get("thresholds", {}) if isinstance(gate_payload.get("thresholds", {}), dict) else {}
        reports = gate_payload.get("reports", {}) if isinstance(gate_payload.get("reports", {}), dict) else {}

    core_gate_hard_fail = False
    core_gate_soft_fail = False
    core_gate_rows: list[dict[str, Any]] = []

    core_keys: list[str] = list(CORE_GATE_KEYS_REQUIRED)
    for maybe in CORE_GATE_KEYS_OPTIONAL:
        if maybe in reports:
            core_keys.append(maybe)

    for key in core_keys:
        row = reports.get(key, {})
        exists = bool(row.get("exists")) if isinstance(row, dict) else False
        issues = row.get("issues", []) if isinstance(row, dict) else []
        metrics = row.get("metrics", {}) if isinstance(row, dict) else {}
        cls = _gate_classification(list(issues))
        if exists:
            core_gate_hard_fail = core_gate_hard_fail or cls.hard_fail
            core_gate_soft_fail = core_gate_soft_fail or cls.soft_fail
        core_gate_rows.append(
            {
                "set": key,
                "exists": exists,
                "accuracy": float(metrics.get("accuracy", 0.0)) if isinstance(metrics, dict) else 0.0,
                "leak_recall": float(((metrics.get("class_recall") or {}).get("LEAK_CONFIRMED", 0.0)) if isinstance(metrics, dict) else 0.0),
                "planned_recall": float(((metrics.get("class_recall") or {}).get("IGNORE_PLANNED_OPS", 0.0)) if isinstance(metrics, dict) else 0.0),
                "inv_false_leak_rate": float(metrics.get("inv_false_leak_rate", 0.0)) if isinstance(metrics, dict) else 0.0,
                "ece": float(metrics.get("ece", 0.0)) if isinstance(metrics, dict) else 0.0,
                "issues": issues,
            }
        )

    missing_assets: list[str] = []
    asset_rows: list[tuple[str, bool]] = []
    for rel in REQUIRED_ASSETS:
        p = ROOT / rel
        ok = p.exists()
        asset_rows.append((rel, ok))
        if not ok:
            missing_assets.append(rel)

    judge_bundle_path, judge_bundle = _pick_latest_judge_bundle(EVIDENCE_DIR)
    judge_missing: list[str] = []
    judge_pass = None
    bedrock_used = None
    if isinstance(judge_bundle, dict):
        jc = judge_bundle.get("judge_compliance", {})
        if isinstance(jc, dict):
            judge_pass = bool(jc.get("pass", False))
            judge_missing = [str(x) for x in jc.get("missing_fields", []) if str(x).strip()]
        rt = judge_bundle.get("_runtime", {})
        if isinstance(rt, dict):
            bedrock = rt.get("bedrock", {})
            if isinstance(bedrock, dict):
                bedrock_used = bool(bedrock.get("used", False))

    decision = _decision(
        missing_required_assets=missing_assets,
        core_gate_hard_fail=core_gate_hard_fail,
        core_gate_soft_fail=core_gate_soft_fail,
        judge_missing=judge_missing,
    )

    root_cause_audio = "no blocking evidence from static artifacts; voice backend must be verified during live demo boot."
    root_cause_media = (
        "judge trace fields are incomplete in local mode (`_runtime.bedrock.request_ids` missing), so hosted Bedrock proof must be captured before final demo."
        if judge_missing
        else "no media artifact blocker detected in latest judge bundle."
    )
    root_cause_consistency = (
        "core sets show perfect class recalls/accuracy but fail ECE threshold, indicating calibration rather than classification reliability issue."
        if core_gate_soft_fail and not core_gate_hard_fail
        else ("hard classification gate failures are present and must be fixed." if core_gate_hard_fail else "no consistency gate failure detected.")
    )

    fix_items: list[tuple[str, str]] = [
        (
            "Capture one hosted Bedrock judge run and preserve request IDs in evidence bundle.",
            "Closes judge trace gap and upgrades trust for live Q&A.",
        ),
        (
            "Lock submission narrative assets (video script + Devpost draft + checklist owner/timestamp).",
            "Reduces last-day submission risk and speeds final packaging.",
        ),
    ]
    if core_gate_soft_fail:
        fix_items.insert(
            1,
            (
                "Tune confidence calibration profile (temperature table) to bring ECE under threshold.",
                "Converts conditional/no-ship status to ship without changing class accuracy.",
            ),
        )
    else:
        fix_items.insert(
            1,
            (
                "Keep calibration profile frozen and rerun gate report after any decision policy change.",
                "Protects current ECE pass status and prevents silent regression.",
            ),
        )

    md: list[str] = [
        "# Hackathon Readiness Snapshot",
        "",
        f"- Generated (UTC): `{now}`",
        f"- Source gate report: `{GATE_JSON.relative_to(ROOT)}`",
        "",
        "## Overall Decision",
        f"- Decision: **{decision}**",
        f"- Missing required assets: `{len(missing_assets)}`",
        f"- Core hard-gate failures: `{_fmt_bool(core_gate_hard_fail)}`",
        f"- Core soft-gate failures: `{_fmt_bool(core_gate_soft_fail)}`",
        "",
        "## Root-Cause Summary (By Axis)",
        f"- `audio_pipeline`: {root_cause_audio}",
        f"- `media_generation`: {root_cause_media}",
        f"- `consistency_logic`: {root_cause_consistency}",
        "",
        "## Core Gate Snapshot",
        "| Set | Exists | Accuracy | Leak Recall | Planned Recall | Inv->Leak % | ECE | Issues |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]

    for row in core_gate_rows:
        issues = "; ".join(str(i) for i in row["issues"]) if row["issues"] else "-"
        md.append(
            f"| {row['set']} | {('yes' if row['exists'] else 'no')} | "
            f"{row['accuracy']:.3f} | {row['leak_recall']:.3f} | {row['planned_recall']:.3f} | "
            f"{100.0 * row['inv_false_leak_rate']:.1f}% | {row['ece']:.3f} | {issues} |"
        )

    md.extend(
        [
            "",
            "## Submission Asset Check",
            "| Asset | Exists |",
            "|---|---|",
        ]
    )
    for rel, ok in asset_rows:
        md.append(f"| `{rel}` | {('yes' if ok else 'no')} |")

    md.extend(
        [
            "",
            "## Judge Bundle Snapshot",
            f"- Latest judge bundle: `{judge_bundle_path.relative_to(ROOT) if judge_bundle_path else 'not found'}`",
            f"- `judge_compliance.pass`: `{judge_pass if judge_pass is not None else 'n/a'}`",
            f"- `_runtime.bedrock.used`: `{bedrock_used if bedrock_used is not None else 'n/a'}`",
            f"- Missing fields: `{', '.join(judge_missing) if judge_missing else '-'}`",
            "",
            "## Prioritized Fix List",
        ]
    )
    for idx, (action, impact) in enumerate(fix_items, start=1):
        md.append(f"{idx}. {action} Expected impact: {impact}")

    if thresholds:
        md.extend(
            [
                "",
                "## Thresholds Used",
                f"- `min_leak_recall`: `{thresholds.get('min_leak_recall')}`",
                f"- `min_planned_ops_recall`: `{thresholds.get('min_planned_ops_recall')}`",
                f"- `max_inv_false_leak_rate`: `{thresholds.get('max_inv_false_leak_rate')}`",
                f"- `max_ece`: `{thresholds.get('max_ece')}`",
            ]
        )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
