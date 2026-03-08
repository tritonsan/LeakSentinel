from __future__ import annotations

import html
import json
import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib import error as urlerror
from urllib import request as urlrequest

import pandas as pd
import streamlit as st

from leaksentinel.ops.coverage_optimizer import build_coverage_plan
from leaksentinel.ops.closed_loop import simulate_closed_loop
from leaksentinel.ops.incidents_store import (
    INCIDENT_STATUSES,
    close_incident,
    dispatch_incident,
    field_update_incident,
    list_incidents,
    open_incident,
)
from leaksentinel.ops.risk_map import build_zone_risk_map
from leaksentinel.impact.kpis import compute_impact_kpis


DATA = Path("data")
OPS_DB = DATA / "ops_db.json"
MANIFEST = DATA / "manifest" / "manifest.csv"
BUNDLES = DATA / "evidence_bundles"
FEEDBACK_DIR = DATA / "feedback"
INCIDENTS = DATA / "ops" / "incidents.json"


def _load_env_fallback() -> None:
    """
    Ensure Streamlit process sees project .env values even if cwd differs.
    """
    root_env = Path(__file__).resolve().parents[1] / ".env"
    if not root_env.exists():
        return
    try:
        for raw in root_env.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            key = k.strip()
            val = v.strip().strip('"').strip("'")
            if key and (key not in os.environ or not str(os.environ.get(key, "")).strip()):
                os.environ[key] = val
    except Exception:
        # UI should still render even if env fallback parsing fails.
        pass


def _inject_styles() -> None:
    st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Sans:wght@400;600;700&display=swap');
:root {
  --ls-bg-0: #071018;
  --ls-bg-1: #0b1824;
  --ls-bg-2: #112231;
  --ls-panel-0: #162634;
  --ls-panel-1: #1b2f41;
  --ls-border: #2e4c63;
  --ls-accent: #64d0ff;
  --ls-accent-2: #8ef0c2;
  --ls-alert: #f7b267;
  --ls-safe: #52d49b;
  --ls-text-0: #eef4fb;
  --ls-text-1: #c6d6e7;
  --ls-text-2: #9fb5cb;
}
html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"] {
  font-family: "Space Grotesk", "IBM Plex Sans", "Segoe UI", sans-serif;
  color: var(--ls-text-0);
}
[data-testid="stMainBlockContainer"] {
  padding-top: 1rem;
  padding-bottom: 2.4rem;
  max-width: 1520px;
}
[data-testid="stAppViewContainer"] {
  background:
    radial-gradient(1100px 640px at 0% 0%, rgba(100, 208, 255, 0.18) 0%, rgba(11, 24, 36, 0.0) 58%),
    radial-gradient(900px 550px at 100% 0%, rgba(142, 240, 194, 0.12) 0%, rgba(7, 16, 24, 0.0) 52%),
    linear-gradient(165deg, var(--ls-bg-2) 0%, var(--ls-bg-1) 48%, var(--ls-bg-0) 100%);
}
[data-testid="stSidebar"] {
  background: linear-gradient(180deg, rgba(10, 23, 35, 0.95), rgba(11, 24, 36, 0.92));
  border-right: 1px solid rgba(100, 208, 255, 0.18);
}
[data-testid="stHeader"] {
  background: transparent;
}
.ls-hero {
  border: 1px solid var(--ls-border);
  border-left: 6px solid var(--ls-accent);
  border-radius: 14px;
  background: linear-gradient(160deg, rgba(26, 45, 62, 0.96), rgba(20, 34, 48, 0.96));
  box-shadow: 0 16px 36px rgba(4, 10, 16, 0.35);
  padding: 16px 18px;
  margin-bottom: 12px;
  line-height: 1.45;
  overflow-wrap: anywhere;
  word-break: break-word;
}
.ls-hero.alert { border-left-color: var(--ls-alert); }
.ls-hero.safe { border-left-color: var(--ls-safe); }
.ls-title { color: var(--ls-text-1); text-transform: uppercase; font-size: 0.82rem; letter-spacing: 0.05em; }
.ls-value { color: var(--ls-text-0); font-size: 1.72rem; font-weight: 700; margin-top: 6px; }
.ls-sub { color: var(--ls-text-2); margin-top: 4px; }
.ls-card {
  border: 1px solid var(--ls-border);
  border-radius: 14px;
  background: linear-gradient(180deg, var(--ls-panel-1), var(--ls-panel-0));
  box-shadow: 0 10px 24px rgba(4, 10, 16, 0.28);
  padding: 12px 13px;
  margin-bottom: 12px;
  line-height: 1.45;
  overflow-wrap: anywhere;
  word-break: break-word;
}
.ls-chip {
  display: inline-block;
  border: 1px solid #4b7fa0;
  border-radius: 999px;
  padding: 3px 8px;
  margin: 0 6px 6px 0;
  font-size: 0.78rem;
  color: #dceeff;
  background: #244054;
  max-width: 100%;
  overflow-wrap: anywhere;
}
[data-testid="stMetric"] {
  border: 1px solid var(--ls-border);
  border-radius: 14px;
  background: linear-gradient(180deg, rgba(24, 41, 56, 0.96), rgba(19, 32, 45, 0.96));
  box-shadow: 0 8px 20px rgba(4, 10, 16, 0.24);
  padding: 10px 12px;
  min-height: 112px;
}
[data-testid="stMetricLabel"] {
  color: var(--ls-text-1);
}
[data-testid="stMetricValue"] {
  color: var(--ls-text-0);
  overflow-wrap: anywhere;
}
[data-testid="stDataFrame"] {
  border: 1px solid rgba(100, 208, 255, 0.24);
  border-radius: 12px;
  overflow: hidden;
}
[data-testid="column"] > div {
  gap: 12px;
}
[data-testid="stCaptionContainer"] p {
  overflow-wrap: anywhere;
  word-break: break-word;
}
button[kind="secondary"], button[kind="primary"] {
  border-radius: 11px !important;
}
[data-baseweb="tab-list"] {
  gap: 8px;
}
[data-baseweb="tab"] {
  border-radius: 10px !important;
  border: 1px solid rgba(100, 208, 255, 0.24) !important;
  background: rgba(14, 28, 40, 0.78) !important;
}
[data-baseweb="tab"][aria-selected="true"] {
  background: linear-gradient(90deg, rgba(38, 69, 94, 0.96), rgba(41, 85, 98, 0.96)) !important;
  border-color: rgba(142, 240, 194, 0.55) !important;
}
.ls-header {
  border: 1px solid rgba(100, 208, 255, 0.28);
  border-radius: 16px;
  background: linear-gradient(130deg, rgba(18, 38, 52, 0.95), rgba(14, 27, 40, 0.95));
  box-shadow: 0 14px 30px rgba(4, 10, 16, 0.34);
  padding: 14px 16px;
  margin-bottom: 12px;
}
.ls-header-title {
  font-size: 1.52rem;
  font-weight: 700;
  color: var(--ls-text-0);
  letter-spacing: 0.01em;
}
.ls-header-sub {
  color: var(--ls-text-2);
  margin-top: 4px;
}
.ls-pill {
  display: inline-block;
  margin-right: 8px;
  margin-top: 10px;
  padding: 4px 9px;
  border-radius: 999px;
  border: 1px solid rgba(142, 240, 194, 0.52);
  background: rgba(22, 55, 63, 0.85);
  color: #e6fff2;
  font-size: 0.76rem;
  letter-spacing: 0.03em;
  text-transform: uppercase;
}
.ls-flow {
  border: 1px solid rgba(142, 240, 194, 0.36);
  border-radius: 12px;
  background: linear-gradient(150deg, rgba(18, 43, 49, 0.92), rgba(16, 34, 46, 0.92));
  padding: 10px 12px;
  margin-bottom: 12px;
  color: #defff0;
}
</style>
""",
        unsafe_allow_html=True,
    )


def _safe_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _yes_no(v: Any) -> str:
    return "Yes" if bool(v) else "No"


def _humanize_key(key: str) -> str:
    raw = str(key or "").strip()
    if not raw:
        return "-"
    special = {
        "id": "ID",
        "api": "API",
        "ops": "Ops",
        "usd": "USD",
        "ai": "AI",
        "ece": "ECE",
        "kpi": "KPI",
        "nrw": "NRW",
        "co2e": "CO2e",
        "fp": "FP",
        "ws": "WS",
        "iou": "IoU",
    }
    parts = raw.replace("-", "_").split("_")
    words = []
    for p in parts:
        w = p.strip()
        if not w:
            continue
        lw = w.lower()
        words.append(special.get(lw, w.capitalize()))
    return " ".join(words) if words else raw


def _humanize_slug(value: str) -> str:
    s = str(value or "").strip()
    if not s:
        return "-"
    if ("_" not in s and "-" not in s) or any(token in s for token in ["://", "arn:", "/", "\\", ":"]):
        return s
    return _humanize_key(s).lower().capitalize()


def _friendly_text(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    if any(token in text for token in ["://", "arn:", "/", "\\"]):
        return text
    if "," in text and ("_" in text or "-" in text):
        parts = [p.strip() for p in text.split(",")]
        return ", ".join(_humanize_slug(p) for p in parts if p)
    return _humanize_slug(text)


def _friendly_reason_label(reason_code: str) -> str:
    labels = {
        "modal_conflict": "Thermal and audio disagree",
        "uncertain_audio_label": "Audio label is uncertain",
        "planned_ops_weak_evidence": "Planned ops overlap with weak evidence",
        "uncorroborated_modal_leak": "Leak-like signal lacks cross-check support",
        "inconclusive_evidence": "Evidence is inconclusive",
    }
    r = str(reason_code or "").strip().lower()
    if not r:
        return "Not specified"
    return labels.get(r, _humanize_slug(r))


def _friendly_decision_label(decision: str) -> str:
    labels = {
        "LEAK_CONFIRMED": "Leak confirmed",
        "IGNORE_PLANNED_OPS": "Ignore (planned ops)",
        "INVESTIGATE": "Investigate",
        "UNKNOWN": "Unknown",
    }
    d = str(decision or "").strip().upper()
    if not d:
        return "Unknown"
    return labels.get(d, _humanize_slug(d))


def _friendly_flag(flag: str) -> str:
    labels = {
        "no_safety_flags": "No safety flag raised",
        "modal_conflict": "Thermal and audio signals conflict",
        "uncertain_audio_label": "Audio signal certainty is low",
        "planned_ops_weak_evidence": "Planned ops can explain weak signal",
        "uncorroborated_modal_leak": "Leak signal lacks cross-check evidence",
        "inconclusive_evidence": "Evidence is not decisive",
    }
    f = str(flag or "").strip().lower()
    if not f:
        return "No safety flag raised"
    return labels.get(f, _humanize_slug(f))


def _friendly_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return _yes_no(value)
    if isinstance(value, float):
        return f"{value:.3f}"
    if isinstance(value, (int,)):
        return str(value)
    if isinstance(value, list):
        if not value:
            return "-"
        return ", ".join(_friendly_value(v) for v in value)
    text = str(value).strip()
    if not text:
        return "-"
    return _friendly_text(text)


def _readable_kv_table(
    data: dict[str, Any],
    *,
    key_label: str = "Field",
    value_label: str = "Value",
    key_alias: Optional[dict[str, str]] = None,
) -> pd.DataFrame:
    alias = key_alias or {}
    rows = []
    for k, v in data.items():
        sk = str(k)
        label = alias.get(sk, _humanize_key(sk))
        rows.append({key_label: label, value_label: _friendly_value(v)})
    return pd.DataFrame(rows)


def _prettify_dataframe(
    df: pd.DataFrame,
    *,
    humanize_columns: bool = True,
    humanize_values: bool = True,
) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame):
        return pd.DataFrame()
    out = df.copy()
    if humanize_columns:
        out = out.rename(columns={c: _humanize_key(str(c)) for c in out.columns})
    if humanize_values and not out.empty:
        for c in out.columns:
            if out[c].dtype == "object":
                out[c] = out[c].apply(_friendly_value)
    return out


def _render_header_shell() -> None:
    st.markdown(
        """
<div class="ls-header">
  <div class="ls-header-title">LeakSentinel - Agentic Leak Verification</div>
  <div class="ls-header-sub">Live evidence, explainable decisions, and operations-ready recommendations.</div>
  <span class="ls-pill">Agentic AI</span>
  <span class="ls-pill">Multimodal</span>
  <span class="ls-pill">Nova on Bedrock</span>
</div>
""",
        unsafe_allow_html=True,
    )


def _render_incident_flow_hint() -> None:
    st.markdown(
        """
<div class="ls-flow"><b>Suggested demo flow:</b> 1) Run a scenario, 2) review the decision, 3) validate trust checks, 4) present evidence tabs in order.</div>
""",
        unsafe_allow_html=True,
    )


def _parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _post_json(url: str, payload: dict[str, Any]) -> tuple[bool, str]:
    body = json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url=url, data=body, method="POST")
    req.add_header("content-type", "application/json")
    try:
        with urlrequest.urlopen(req, timeout=10) as resp:
            return True, resp.read().decode("utf-8", errors="replace")
    except urlerror.HTTPError as e:
        return False, e.read().decode("utf-8", errors="replace")
    except Exception as e:
        return False, str(e)


def _reliability_snapshot(labels: dict[str, str], limit: int = 20) -> dict[str, Any]:
    files = sorted(BUNDLES.glob("*.json"))[-max(1, int(limit)) :]
    if not files:
        return {"n_runs": 0}
    n = bedrock_used = fallback_any = inv_total = inv_leak = 0
    decisions = Counter()
    for p in files:
        obj = _safe_json(p)
        if not obj:
            continue
        n += 1
        decisions[str(obj.get("decision", "UNKNOWN"))] += 1
        rt = obj.get("_runtime", {}) if isinstance(obj.get("_runtime"), dict) else {}
        br = rt.get("bedrock", {}) if isinstance(rt.get("bedrock"), dict) else {}
        if bool(br.get("used")):
            bedrock_used += 1
        fb = br.get("fallback", {}) if isinstance(br.get("fallback"), dict) else {}
        if any(bool(v) for v in fb.values()):
            fallback_any += 1
        ctx = (obj.get("evidence") or {}).get("context") if isinstance(obj.get("evidence"), dict) else {}
        sid = str((ctx or {}).get("scenario_id", "") or "").strip()
        if labels.get(sid, "").lower() == "investigate":
            inv_total += 1
            if str(obj.get("decision", "")).strip().upper() == "LEAK_CONFIRMED":
                inv_leak += 1
    return {
        "n_runs": n,
        "bedrock_rate": (bedrock_used / n) if n else 0.0,
        "fallback_rate": (fallback_any / n) if n else 0.0,
        "decisions": dict(decisions),
        "inv_leak_rate": (inv_leak / inv_total) if inv_total else 0.0,
    }


def _feedback_learning_trend(limit: int = 20) -> dict[str, Any]:
    files = sorted(BUNDLES.glob("*.json"))[-max(1, int(limit)) :]
    rows: list[dict[str, Any]] = []
    for p in files:
        obj = _safe_json(p)
        if not obj:
            continue
        cls = obj.get("closed_loop_summary_v1", {}) if isinstance(obj.get("closed_loop_summary_v1"), dict) else {}
        if not cls:
            continue
        ev = obj.get("evidence", {}) if isinstance(obj.get("evidence"), dict) else {}
        ctx = ev.get("context", {}) if isinstance(ev.get("context"), dict) else {}
        rows.append(
            {
                "timestamp": str(ctx.get("timestamp", "") or ""),
                "scenario_id": str(ctx.get("scenario_id", "") or ""),
                "feedback_applied": bool(cls.get("feedback_applied")),
                "feedback_effective": bool(cls.get("feedback_effective")),
                "repeat_fp_risk_reduction_pct": _to_float(cls.get("repeat_fp_risk_reduction_pct"), 0.0),
            }
        )
    if not rows:
        return {
            "status": "insufficient_data",
            "feedback_effectiveness_rate": None,
            "repeat_fp_reduction_rate": None,
            "rows": [],
        }
    df = pd.DataFrame(rows)
    applicable = df[df["feedback_applied"] == True]  # noqa: E712
    if applicable.empty:
        return {
            "status": "insufficient_data",
            "feedback_effectiveness_rate": None,
            "repeat_fp_reduction_rate": None,
            "rows": rows,
        }
    eff_rate = float((applicable["feedback_effective"] == True).sum()) / float(len(applicable))  # noqa: E712
    rep_rate = float(applicable["repeat_fp_risk_reduction_pct"].mean()) / 100.0
    return {
        "status": "ok",
        "feedback_effectiveness_rate": eff_rate,
        "repeat_fp_reduction_rate": rep_rate,
        "rows": rows,
    }


def _bundle_status(bundle: dict[str, Any]) -> str:
    rt = bundle.get("_runtime", {}) if isinstance(bundle, dict) else {}
    br = rt.get("bedrock", {}) if isinstance(rt.get("bedrock"), dict) else {}
    mode = str(rt.get("mode", "") or "").strip().lower()
    used = bool(br.get("used"))
    fb = br.get("fallback", {}) if isinstance(br.get("fallback"), dict) else {}
    if used and any(bool(v) for v in fb.values()):
        return "Bedrock + fallback"
    if used:
        return "Bedrock live"
    if mode == "bedrock":
        return "Bedrock fallback only"
    return "Local path"


def _friendly_bedrock_status(status: str) -> str:
    mapping = {
        "Bedrock + fallback": "Bedrock active (partial fallback)",
        "Bedrock live": "Bedrock live",
        "Bedrock fallback only": "Bedrock fallback only",
        "Local path": "Local path",
        "No runs yet": "No runs yet",
    }
    s = str(status or "").strip()
    return mapping.get(s, s or "-")


def _confidence_band(confidence: float) -> str:
    c = _to_float(confidence)
    if c >= 0.85:
        return "High confidence"
    if c >= 0.65:
        return "Medium confidence"
    return "Low confidence"


def _friendly_track_label(track: str) -> str:
    mapping = {
        "core": "Core track",
        "real_challenge": "Real-world track",
    }
    t = str(track or "").strip().lower()
    if not t:
        return "-"
    return mapping.get(t, _humanize_slug(t))


def _reason_explanation(*, decision: str, reason_code: str) -> str:
    d = str(decision or "").strip().upper()
    r = str(reason_code or "").strip().lower()
    if d == "LEAK_CONFIRMED":
        return "Leak evidence crossed confirmation threshold. Dispatch path is active."
    if d == "IGNORE_PLANNED_OPS":
        return "Signal is most likely explained by planned operations. Monitor instead of dispatch."
    mapping = {
        "modal_conflict": "Thermal/audio signals strongly disagree. Escalated for manual investigation.",
        "uncertain_audio_label": "Audio label reliability is uncertain without thermal corroboration.",
        "planned_ops_weak_evidence": "Planned operations overlap with weak evidence. Manual check is safer.",
        "uncorroborated_modal_leak": "Leak signal exists but cross-checks are not strong enough for confirmation.",
        "inconclusive_evidence": "Evidence is mixed or weak. More data is required before confirmation.",
    }
    if r in mapping:
        return mapping[r]
    return "Investigation is required because evidence is not confidently confirmable."


def _render_executive_report(bundle: dict[str, Any]) -> None:
    decision = str(bundle.get("decision", "UNKNOWN")).upper()
    decision_label = _friendly_decision_label(decision)
    conf = _to_float(bundle.get("confidence"), 0.0)
    reason_code = str(bundle.get("investigate_reason_code", "") or "").strip()
    reason_label = _friendly_reason_label(reason_code)
    reason_text = _reason_explanation(decision=decision, reason_code=reason_code)
    action = _humanize_slug(str(bundle.get("recommended_action", "") or "").strip())

    ev = bundle.get("evidence", {}) if isinstance(bundle.get("evidence"), dict) else {}
    ctx = ev.get("context", {}) if isinstance(ev.get("context"), dict) else {}
    ops = ev.get("ops", {}) if isinstance(ev.get("ops"), dict) else {}
    impact_v2 = bundle.get("impact_estimate_v2", {}) if isinstance(bundle.get("impact_estimate_v2"), dict) else {}
    impact = bundle.get("impact_estimate", {}) if isinstance(bundle.get("impact_estimate"), dict) else {}
    rt = bundle.get("_runtime", {}) if isinstance(bundle.get("_runtime"), dict) else {}
    br = rt.get("bedrock", {}) if isinstance(rt.get("bedrock"), dict) else {}

    if decision == "LEAK_CONFIRMED":
        incident_line = "The system marked this event as a confirmed leak."
    elif decision == "IGNORE_PLANNED_OPS":
        incident_line = "The signal is explained by planned operations; immediate dispatch is not recommended."
    else:
        incident_line = "The system could not reach a definitive result; field verification is recommended."

    avoided_dispatch = _to_float(
        impact_v2.get("avoided_false_dispatch_usd", impact.get("avoided_false_dispatch_estimate")),
        0.0,
    )
    avoided_leak_loss = _to_float(
        impact_v2.get("avoided_leak_loss_usd", impact.get("avoided_leak_loss_estimate")),
        0.0,
    )
    scenario_id = str(ctx.get("scenario_id", "-") or "-")
    zone = str(ctx.get("zone", "-") or "-")
    ts = str(ctx.get("timestamp", "-") or "-")

    st.markdown("#### Executive Summary")
    st.markdown(
        f'<div class="ls-card"><b>What happened?</b><br>{html.escape(incident_line)}<br><br><b>Decision:</b> {html.escape(decision_label)} | <b>Confidence:</b> {conf:.2f} ({_confidence_band(conf)})</div>',
        unsafe_allow_html=True,
    )
    e1, e2 = st.columns(2)
    with e1:
        st.markdown(
            f'<div class="ls-card"><b>Why this decision?</b><br>{html.escape(reason_label)}<br><small>{html.escape(reason_text)}</small></div>',
            unsafe_allow_html=True,
        )
    with e2:
        action_text = action if action and action != "-" else "Continue monitoring until operator verification is complete."
        st.markdown(
            f'<div class="ls-card"><b>What should we do now?</b><br>{html.escape(action_text)}</div>',
            unsafe_allow_html=True,
        )
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Scenario", scenario_id)
    with m2:
        st.metric("Zone", zone)
    with m3:
        st.metric("Planned ops overlap", _yes_no(bool(ops.get("planned_op_found"))))
    with m4:
        st.metric("Bedrock live usage", _yes_no(bool(br.get("used"))))
    p1, p2, p3 = st.columns(3)
    with p1:
        st.metric("Avoided false dispatch cost (USD)", f"{avoided_dispatch:.0f}")
    with p2:
        st.metric("Avoided potential leak loss (USD)", f"{avoided_leak_loss:.0f}")
    with p3:
        st.metric("Scan time", ts)


def _render_demo_showcase(bundle: dict[str, Any]) -> None:
    rt = bundle.get("_runtime", {}) if isinstance(bundle.get("_runtime"), dict) else {}
    br = rt.get("bedrock", {}) if isinstance(rt.get("bedrock"), dict) else {}
    req = br.get("request_ids", {}) if isinstance(br.get("request_ids"), dict) else {}
    fb = br.get("fallback", {}) if isinstance(br.get("fallback"), dict) else {}

    ev = bundle.get("evidence", {}) if isinstance(bundle.get("evidence"), dict) else {}
    thermal = ev.get("thermal", {}) if isinstance(ev.get("thermal"), dict) else {}
    audio = ev.get("audio", {}) if isinstance(ev.get("audio"), dict) else {}
    decision = str(bundle.get("decision", "UNKNOWN")).upper()
    decision_label = _friendly_decision_label(decision)
    conf = _to_float(bundle.get("confidence"), 0.0)
    reason = _friendly_reason_label(str(bundle.get("investigate_reason_code", "") or "").strip())

    mm_model = str(br.get("multimodal_model_id", "-") or "-")
    rs_model = str(br.get("reasoning_model_id", "-") or "-")
    thermal_hit = bool(thermal.get("has_leak_signature"))
    thermal_conf = _to_float(thermal.get("confidence"), 0.0)
    audio_skipped = bool(audio.get("skipped"))
    audio_hit = bool(audio.get("leak_like"))
    audio_conf = _to_float(audio.get("confidence"), 0.0)
    audio_skip_reason = _humanize_slug(str(audio.get("reason", "") or "").strip())

    st.markdown("#### Demo Showcase: Model Flow")
    st.caption("Use this section as your live demo talk track.")
    s1, s2, s3 = st.columns(3)
    with s1:
        thermal_result = (
            f"Leak signature detected (confidence {thermal_conf:.2f})"
            if thermal_hit
            else f"Leak signature weak/not detected (confidence {thermal_conf:.2f})"
        )
        thermal_runtime = (
            f"Bedrock call completed (ID: {req.get('thermal', '-')})"
            if str(req.get("thermal", "") or "").strip()
            else ("Fallback path used" if bool(fb.get("thermal")) else "Not executed")
        )
        st.markdown(
            f'<div class="ls-card"><b>1) Nova Pro - Thermal Analysis</b><br><small>Model: {html.escape(mm_model)}</small><br>{html.escape(thermal_result)}<br><small>{html.escape(str(thermal_runtime))}</small></div>',
            unsafe_allow_html=True,
        )
    with s2:
        if audio_skipped:
            audio_result = f"Audio analysis skipped ({audio_skip_reason})"
        else:
            audio_result = (
                f"Leak-audio signal detected (confidence {audio_conf:.2f})"
                if audio_hit
                else f"Leak-audio signal weak/absent (confidence {audio_conf:.2f})"
            )
        audio_runtime = (
            f"Bedrock call completed (ID: {req.get('audio', '-')})"
            if str(req.get("audio", "") or "").strip()
            else ("Fallback path used" if bool(fb.get("audio")) else "Not executed")
        )
        st.markdown(
            f'<div class="ls-card"><b>2) Nova Pro - Audio Analysis</b><br><small>Model: {html.escape(mm_model)}</small><br>{html.escape(audio_result)}<br><small>{html.escape(str(audio_runtime))}</small></div>',
            unsafe_allow_html=True,
        )
    with s3:
        decision_runtime = (
            f"Bedrock decision call completed (ID: {req.get('decision', '-')})"
            if str(req.get("decision", "") or "").strip()
            else ("Fallback path used" if bool(fb.get("decision")) else "Not executed")
        )
        st.markdown(
            f'<div class="ls-card"><b>3) Nova Lite - Final Decision</b><br><small>Model: {html.escape(rs_model)}</small><br>Decision: <b>{html.escape(decision_label)}</b><br>Confidence: {conf:.2f}<br>Reason: {html.escape(reason)}<br><small>{html.escape(str(decision_runtime))}</small></div>',
            unsafe_allow_html=True,
        )

    st.markdown("#### 30-Second Talk Track")
    st.write("1. Nova Pro extracts leak signatures from thermal imagery and produces a confidence score.")
    st.write("2. Nova Pro validates the same event through audio signals or marks it weak.")
    st.write("3. Nova Lite combines both channels and applies safety checks to produce the final decision.")
    st.write("4. The suggested action can be handed to operations immediately.")

def _render_agent_pipeline(bundle: dict[str, Any]) -> None:
    rt = bundle.get("_runtime", {}) if isinstance(bundle, dict) else {}
    br = rt.get("bedrock", {}) if isinstance(rt, dict) else {}
    req = br.get("request_ids", {}) if isinstance(br.get("request_ids"), dict) else {}
    fb = br.get("fallback", {}) if isinstance(br.get("fallback"), dict) else {}
    ev = bundle.get("evidence", {}) if isinstance(bundle.get("evidence"), dict) else {}
    audio = ev.get("audio", {}) if isinstance(ev.get("audio"), dict) else {}
    used = bool(br.get("used"))
    sonic_model = str(os.getenv("NOVA_SONIC_MODEL_ID", "") or "").strip()
    mm_model = str(br.get("multimodal_model_id", "-") or "-")
    rs_model = str(br.get("reasoning_model_id", "-") or "-")
    thermal_req = str(req.get("thermal", "") or "").strip()
    audio_req = str(req.get("audio", "") or "").strip()
    decision_req = str(req.get("decision", "") or "").strip()
    audio_skipped = bool(audio.get("skipped"))
    audio_skip_reason = _humanize_slug(str(audio.get("reason", "") or "").strip())

    st.markdown("#### Agent Role Breakdown")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            '<div class="ls-card"><b>Nova 2 Sonic</b><br><small>Voice interaction with operator</small></div>',
            unsafe_allow_html=True,
        )
        st.caption(f"Model ID: {sonic_model or 'not configured'}")
        st.caption("In this scan: Not used (available for voice demo)")
    with c2:
        st.markdown(
            '<div class="ls-card"><b>Nova Pro (Multimodal)</b><br><small>Thermal and audio evidence extraction</small></div>',
            unsafe_allow_html=True,
        )
        st.caption(f"Model ID: {mm_model}")
        st.caption(f"Thermal request ID: {thermal_req or '-'}")
        if audio_skipped:
            st.caption(f"Audio request: Skipped ({audio_skip_reason})")
        else:
            st.caption(f"Audio request ID: {audio_req or '-'}")
        st.caption(f"Status: {'Bedrock active' if used else 'Fallback'}")
    with c3:
        st.markdown(
            '<div class="ls-card"><b>Nova Lite (Reasoning)</b><br><small>Final decision and safety checks</small></div>',
            unsafe_allow_html=True,
        )
        st.caption(f"Model ID: {rs_model}")
        st.caption(f"Decision request ID: {decision_req or '-'}")
        st.caption(f"Status: {'Bedrock active' if used else 'Fallback'}")

    rows = [
        {
            "Agent": "Nova 2 Sonic",
            "Agent role": "Voice intake and operator Q&A",
            "What it did in this scan": "Not used in incident scan (available for voice demo)",
        },
        {
            "Agent": "Nova Pro",
            "Agent role": "Thermal evidence analysis",
            "What it did in this scan": (
                f"Completed via Bedrock (request: {thermal_req})"
                if thermal_req
                else ("Fallback path used" if bool(fb.get("thermal")) else "Not executed")
            ),
        },
        {
            "Agent": "Nova Pro",
            "Agent role": "Audio evidence analysis",
            "What it did in this scan": (
                f"Skipped ({audio_skip_reason})"
                if audio_skipped
                else (
                    f"Completed via Bedrock (request: {audio_req})"
                    if audio_req
                    else ("Fallback path used" if bool(fb.get("audio")) else "Not executed")
                )
            ),
        },
        {
            "Agent": "Nova Lite",
            "Agent role": "Final decision synthesis and safety checks",
            "What it did in this scan": (
                f"Completed via Bedrock (request: {decision_req})"
                if decision_req
                else ("Fallback path used" if bool(fb.get("decision")) else "Not executed")
            ),
        },
    ]
    st.markdown("#### Scan Outcome - Agent Summary")
    st.dataframe(_prettify_dataframe(pd.DataFrame(rows)), width="stretch", hide_index=True)


def _quick_presets(manifest: pd.DataFrame) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    defs = [
        ("Core Leak", "leak", "core"),
        ("Planned Ops", "planned_ops", "core"),
        ("Investigate", "investigate", "core"),
        ("Real Challenge Leak", "leak", "real_challenge"),
    ]
    if manifest.empty:
        return out
    m = manifest.copy()
    m["label_n"] = m["label"].astype(str).str.lower().str.strip()
    m["track_n"] = m["track"].astype(str).str.lower().str.strip()
    for title, label, track in defs:
        r = m[(m["label_n"] == label) & (m["track_n"] == track)].sort_values("timestamp")
        if not r.empty:
            out.append({"title": title, "scenario_id": str(r.iloc[0]["scenario_id"]), "track": track})
    return out


def _latest_live_bedrock_bundle() -> Optional[str]:
    for p in sorted(BUNDLES.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        obj = _safe_json(p)
        rt = obj.get("_runtime", {}) if isinstance(obj.get("_runtime"), dict) else {}
        br = rt.get("bedrock", {}) if isinstance(rt.get("bedrock"), dict) else {}
        if str(rt.get("mode", "")).strip().lower() == "bedrock" and bool(br.get("used")):
            return p.name
    return None


def _suggest_scenario(manifest: pd.DataFrame, zone: str, start_iso: str, end_iso: str) -> Optional[str]:
    if manifest.empty:
        return None
    try:
        center = _parse_dt(start_iso) + (_parse_dt(end_iso) - _parse_dt(start_iso)) / 2
    except Exception:
        return None
    m = manifest.copy()
    m["ts_dt"] = pd.to_datetime(m["timestamp"], errors="coerce")
    m = m[m["ts_dt"].notna()]
    if m.empty:
        return None
    zone_m = m[m["zone"].astype(str) == str(zone)]
    if zone_m.empty:
        zone_m = m
    idx = (zone_m["ts_dt"] - center).abs().idxmin()
    return str(zone_m.loc[idx, "scenario_id"]) if pd.notna(idx) else None


def _run_and_refresh(scenario_id: str, mode: str, *, judge_mode: bool = False) -> None:
    from leaksentinel.orchestrator import run_scenario

    try:
        with st.spinner(f"Running {scenario_id} ({mode})..."):
            out = run_scenario(scenario_id=scenario_id, mode=mode, write_bundle=True, judge_mode=bool(judge_mode))
        bpath = str(out.get("_bundle_path", "") or "").strip()
        if bpath:
            bname = Path(bpath).name
            st.session_state["selected_bundle_name"] = bname
            st.session_state["selected_bundle_picker"] = bname
        decision_label = _friendly_decision_label(str(out.get("decision", "") or ""))
        st.session_state["run_flash"] = f"{scenario_id} -> {decision_label} ({_to_float(out.get('confidence')):.2f})"
        runtime = out.get("_runtime", {}) if isinstance(out.get("_runtime"), dict) else {}
        bedrock = runtime.get("bedrock", {}) if isinstance(runtime.get("bedrock"), dict) else {}
        note = str(out.get("note", "") or "").strip()
        if mode == "bedrock" and (not bool(bedrock.get("used"))):
            reason = note or "Bedrock path was not active for this run."
            st.session_state["run_warning"] = f"Bedrock fallback triggered: {reason}"
    except Exception as e:
        st.session_state["run_error"] = str(e)
    st.rerun()


def _render_feedback(bundle: dict[str, Any], bundle_path: Optional[Path]) -> None:
    api_base = os.getenv("LEAKSENTINEL_API_BASE", "http://127.0.0.1:8000").rstrip("/")
    st.caption(f"Feedback API: {api_base}/feedback")
    sid = str(bundle.get("evidence", {}).get("context", {}).get("scenario_id", "") or "").strip()
    root_cause_opts = {
        "": "Select",
        "planned_operation_overlap": "Planned ops overlap",
        "thermal_artifact_without_acoustic_confirmation": "Thermal artifact without acoustic confirmation",
        "acoustic_transient_without_thermal_confirmation": "Acoustic transient without thermal confirmation",
        "weak_flow_signal_near_baseline": "Weak flow signal near baseline",
        "multi_factor_ambiguous_evidence": "Multi-factor ambiguous evidence",
    }
    missing_evidence_opts = {
        "": "Select",
        "confirm_planned_ops_status_and_capture_post_window_sample": "Confirm planned ops status and capture a post-window sample",
        "collect_acoustic_sample_for_confirmation": "Collect acoustic sample for confirmation",
        "capture_followup_thermal_frame_in_10_minutes": "Capture follow-up thermal frame in 10 minutes",
        "collect_thermal_and_acoustic_recheck_pair": "Collect thermal and acoustic recheck pair",
    }
    with st.form(f"feedback_form_{sid or 'unknown'}"):
        reviewer = st.text_input("Reviewer", "")
        root_cause_guess = st.selectbox(
            "Likely root cause",
            list(root_cause_opts.keys()),
            format_func=lambda k: root_cause_opts.get(str(k), str(k)),
        )
        evidence_gap = st.selectbox(
            "Missing evidence",
            list(missing_evidence_opts.keys()),
            format_func=lambda k: missing_evidence_opts.get(str(k), str(k)),
        )
        note = st.text_area("Why was this a false positive?", "")
        submit = st.form_submit_button("Reject as False Positive")
    if submit:
        if not bundle_path:
            st.error("Bundle path missing.")
            return
        payload = {
            "bundle_path": str(bundle_path.resolve()),
            "scenario_id": sid,
            "outcome": "false_positive_rejected_by_operator",
            "operator_note": note,
            "reviewer": reviewer,
            "root_cause_guess": root_cause_guess,
            "evidence_gap": evidence_gap,
        }
        ok, raw = _post_json(f"{api_base}/feedback", payload)
        if ok:
            st.success("Feedback saved.")
            with st.expander("Technical response"):
                st.code(raw, language="json")
        else:
            st.error("Feedback save failed.")
            with st.expander("Technical response"):
                st.code(raw, language="json")


def _latest_bundle_for_scenario_local(scenario_id: str) -> Optional[Path]:
    sid = str(scenario_id or "").strip()
    if not sid:
        return None
    files = sorted(BUNDLES.glob(f"{sid}_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _render_incident_lifecycle_panel(manifest: pd.DataFrame) -> None:
    st.markdown("### Incident Lifecycle")
    rows = list_incidents(incidents_path=INCIDENTS, limit=300)

    open_rows = [r for r in rows if str(r.get("status", "")).strip().lower() not in {"closed_true_positive", "closed_false_positive"}]
    closed_rows = [r for r in rows if str(r.get("status", "")).strip().lower() in {"closed_true_positive", "closed_false_positive"}]
    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("Open incidents", int(len(open_rows)))
    with m2:
        st.metric("Closed incidents", int(len(closed_rows)))
    with m3:
        st.metric("Total incidents", int(len(rows)))

    scenarios = manifest["scenario_id"].astype(str).tolist() if not manifest.empty and "scenario_id" in manifest.columns else []
    if scenarios:
        o1, o2 = st.columns([2, 1])
        with o1:
            sid = st.selectbox("Open from scenario", scenarios, key="ops_incident_open_sid")
        with o2:
            if st.button("Open Incident", key="ops_incident_open_btn"):
                bp = _latest_bundle_for_scenario_local(sid)
                if not bp:
                    st.warning("No bundle found for scenario. Run this scenario first in Incidents page.")
                else:
                    obj = _safe_json(bp)
                    if obj:
                        open_incident(incidents_path=INCIDENTS, bundle=obj, bundle_path=str(bp))
                        st.success("Incident opened (or existing active incident reused).")
                        st.rerun()

    if rows:
        view = []
        for r in rows:
            view.append(
                {
                    "incident_id": r.get("incident_id"),
                    "scenario_id": r.get("scenario_id"),
                    "zone": r.get("zone"),
                    "status": r.get("status"),
                    "decision": r.get("decision"),
                    "confidence": r.get("confidence"),
                    "assignee_team": r.get("assignee_team"),
                    "opened_at": r.get("opened_at"),
                    "closed_at": r.get("closed_at"),
                }
            )
        st.dataframe(_prettify_dataframe(pd.DataFrame(view)), width="stretch", hide_index=True)

        ids = [str(r.get("incident_id", "")).strip() for r in rows if str(r.get("incident_id", "")).strip()]
        if ids:
            sid = st.selectbox("Incident actions", ids, key="ops_incident_action_id")
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown("#### Dispatch")
                team = st.text_input("Team", "crew-1", key="ops_incident_team")
                eta = st.number_input("ETA (min)", min_value=1, max_value=240, value=30, key="ops_incident_eta")
                if st.button("Dispatch Team", key="ops_incident_dispatch_btn"):
                    try:
                        dispatch_incident(
                            incidents_path=INCIDENTS,
                            incident_id=sid,
                            team=str(team),
                            eta_minutes=int(eta),
                        )
                        st.success("Incident dispatched.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
            with c2:
                st.markdown("#### Field Update")
                next_status = st.selectbox("Status", list(INCIDENT_STATUSES), key="ops_incident_status")
                note = st.text_input("Note", "", key="ops_incident_note")
                evidence_added = st.checkbox("Evidence added", value=False, key="ops_incident_ev")
                if st.button("Apply Update", key="ops_incident_update_btn"):
                    try:
                        field_update_incident(
                            incidents_path=INCIDENTS,
                            incident_id=sid,
                            status=str(next_status),
                            note=str(note),
                            evidence_added=bool(evidence_added),
                        )
                        st.success("Incident updated.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
            with c3:
                st.markdown("#### Close")
                closure_type = st.selectbox(
                    "Closure type",
                    ["true_positive", "false_positive"],
                    key="ops_incident_close_type",
                )
                closure_note = st.text_input("Closure note", "", key="ops_incident_close_note")
                repair_cost = st.number_input("Repair cost (USD)", min_value=0.0, value=0.0, step=10.0, key="ops_incident_repair")
                if st.button("Close Incident", key="ops_incident_close_btn"):
                    try:
                        close_incident(
                            incidents_path=INCIDENTS,
                            incident_id=sid,
                            closure_type=str(closure_type),
                            note=str(closure_note),
                            repair_cost_usd=float(repair_cost),
                        )
                        st.success("Incident closed.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
    else:
        st.info("No incidents created yet.")


def _render_ops_kpis_and_risk() -> None:
    st.markdown("### Ops KPIs")
    kpi = compute_impact_kpis(incidents_path=INCIDENTS)
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.metric("Incidents Opened", int(_to_float(kpi.get("incidents_opened"), 0)))
    with k2:
        st.metric("Incidents Closed", int(_to_float(kpi.get("incidents_closed"), 0)))
    with k3:
        st.metric("Water Saved (m3)", f"{_to_float(kpi.get('estimated_water_saved_m3_total')):.2f}")
    with k4:
        st.metric("Cost Saved (USD)", f"{_to_float(kpi.get('estimated_cost_saved_usd_total')):.0f}")
    k5, k6, k7 = st.columns(3)
    with k5:
        st.metric("CO2e Avoided (kg)", f"{_to_float(kpi.get('co2e_kg_avoided_total')):.2f}")
    with k6:
        st.metric("Avg Dispatch (min)", f"{_to_float(kpi.get('avg_time_to_dispatch_min')):.1f}")
    with k7:
        st.metric("Avg Close (hours)", f"{_to_float(kpi.get('avg_time_to_close_hours')):.1f}")

    st.markdown("### Zone Risk Map")
    risk_days = st.number_input("Risk window (days)", min_value=1, max_value=180, value=30, step=1, key="ops_risk_window_days")
    risk = build_zone_risk_map(
        evidence_dir=BUNDLES,
        incidents_path=INCIDENTS,
        window_days=int(risk_days),
    )
    zones = risk.get("zones", []) if isinstance(risk.get("zones"), list) else []
    if not zones:
        st.info("No zone risk data yet.")
        return
    df = pd.DataFrame(zones)
    st.dataframe(_prettify_dataframe(df), width="stretch", hide_index=True)
    st.markdown("#### Top Risk Zones")
    top = df.sort_values("risk_score_0_100", ascending=False).head(5)
    for _, r in top.iterrows():
        st.write(
            f"- {_friendly_value(r['zone'])}: {float(r['risk_score_0_100']):.1f} ({_friendly_value(str(r['trend']))})"
        )


def _render_ops(manifest: pd.DataFrame) -> None:
    st.header("Ops Portal")
    ops = (_safe_json(OPS_DB).get("ops", []) if OPS_DB.exists() else [])
    if not ops:
        st.warning("No ops records found.")
        return
    df = pd.DataFrame(ops)
    df["start_dt"] = pd.to_datetime(df["start"], errors="coerce")
    df["end_dt"] = pd.to_datetime(df["end"], errors="coerce")
    df = df[df["start_dt"].notna() & df["end_dt"].notna()].copy()
    if df.empty:
        st.warning("Ops records are invalid.")
        return

    zones = ["(all)"] + sorted(df["zone"].astype(str).unique().tolist())
    types = ["(all)"] + sorted(df["type"].astype(str).unique().tolist())
    c1, c2, c3, c4, c5 = st.columns([1, 1, 1.2, 1.2, 1.5])
    with c1:
        z = st.selectbox("Zone", zones)
    with c2:
        t = st.selectbox("Type", types)
    with c3:
        start = st.text_input("From (ISO)", df["start_dt"].min().replace(microsecond=0).isoformat())
    with c4:
        end = st.text_input("To (ISO)", df["end_dt"].max().replace(microsecond=0).isoformat())
    with c5:
        q = st.text_input("Search id/note", "")

    f = df.copy()
    active_filters = 0
    if z != "(all)":
        f = f[f["zone"].astype(str) == z]
        active_filters += 1
    if t != "(all)":
        f = f[f["type"].astype(str) == t]
        active_filters += 1
    try:
        sdt, edt = _parse_dt(start), _parse_dt(end)
        f = f[(f["start_dt"] <= edt) & (f["end_dt"] >= sdt)]
        active_filters += 1
    except Exception:
        st.warning("Time filter parse failed.")
    if q.strip():
        qq = q.strip().lower()
        f = f[f["planned_op_id"].astype(str).str.lower().str.contains(qq) | f["note"].astype(str).str.lower().str.contains(qq)]
        active_filters += 1

    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("Records shown", int(len(f)))
    with m2:
        st.metric("Zones in result", int(f["zone"].astype(str).nunique()) if not f.empty else 0)
    with m3:
        st.metric("Active filters", int(active_filters))
    st.dataframe(
        _prettify_dataframe(f[["planned_op_id", "zone", "start", "end", "type", "note"]].sort_values("start")),
        width="stretch",
        hide_index=True,
    )

    st.markdown("---")
    _render_incident_lifecycle_panel(manifest)
    st.markdown("---")
    _render_ops_kpis_and_risk()

    st.markdown("---")
    st.markdown("### Send Ops Context To Incidents")
    st.info("Use ops context to guide investigation, but do not suppress strong leak evidence automatically.")
    if f.empty:
        return
    selected_op = st.selectbox("Operation", f["planned_op_id"].astype(str).tolist())
    if st.button("Open In Incidents Context", type="primary"):
        row = f[f["planned_op_id"].astype(str) == str(selected_op)].iloc[0]
        sid = _suggest_scenario(manifest, str(row["zone"]), str(row["start"]), str(row["end"]))
        if not sid:
            st.warning("Could not infer matching scenario.")
            return
        st.session_state["incident_prefill_scenario"] = sid
        st.session_state["ops_context_note"] = f"Context loaded from {selected_op} ({row['zone']} {row['start']} -> {row['end']}). Suggested scenario: {sid}."
        st.session_state["page_nav"] = "Incidents"
        st.rerun()

    st.markdown("---")
    st.markdown("### Dispatch Coverage Plan")
    st.caption("Prioritize evidence bundles into a limited crew dispatch queue.")
    o1, o2, o3 = st.columns([1, 1, 2])
    with o1:
        horizon_hours = st.number_input("Horizon (hours)", min_value=1, max_value=168, value=24, step=1)
    with o2:
        max_crews = st.number_input("Max crews", min_value=1, max_value=20, value=3, step=1)
    with o3:
        zones_filter = []
        if z != "(all)":
            zones_filter = [str(z)]
            st.caption(f"Zone filter active: {z}")
        else:
            st.caption("Zone filter: all zones")

    if st.button("Generate Coverage Plan", key="generate_coverage_plan"):
        out = build_coverage_plan(
            evidence_dir=BUNDLES,
            horizon_hours=int(horizon_hours),
            max_crews=int(max_crews),
            zones=zones_filter,
        )
        summary = out.get("summary", {}) if isinstance(out.get("summary"), dict) else {}
        dispatch_queue = out.get("dispatch_queue", []) if isinstance(out.get("dispatch_queue"), list) else []
        unassigned = out.get("unassigned", []) if isinstance(out.get("unassigned"), list) else []

        p1, p2, p3 = st.columns(3)
        with p1:
            st.metric("Bundles considered", int(summary.get("bundles_considered", 0)))
        with p2:
            st.metric("Dispatch assigned", int(summary.get("dispatch_n", 0)))
        with p3:
            st.metric("Unassigned", int(summary.get("unassigned_n", 0)))

        if dispatch_queue:
            st.markdown("#### Dispatch Queue")
            df_q = pd.DataFrame(dispatch_queue)
            if not df_q.empty:
                if "priority_reasons" in df_q.columns:
                    df_q["priority_reasons"] = df_q["priority_reasons"].apply(
                        lambda x: ", ".join([str(v) for v in x]) if isinstance(x, list) else str(x)
                    )
                st.dataframe(_prettify_dataframe(df_q), width="stretch", hide_index=True)
                top_sid = str(df_q.iloc[0].get("scenario_id", "") or "").strip()
                if top_sid and st.button("Open Top Priority In Incidents", key="open_top_priority_incident"):
                    st.session_state["incident_prefill_scenario"] = top_sid
                    st.session_state["ops_context_note"] = f"Coverage plan selected top priority scenario: {top_sid}."
                    st.session_state["page_nav"] = "Incidents"
                    st.rerun()
        if unassigned:
            with st.expander("Show Unassigned Tasks"):
                df_u = pd.DataFrame(unassigned)
                if not df_u.empty:
                    if "priority_reasons" in df_u.columns:
                        df_u["priority_reasons"] = df_u["priority_reasons"].apply(
                            lambda x: ", ".join([str(v) for v in x]) if isinstance(x, list) else str(x)
                        )
                    st.dataframe(_prettify_dataframe(df_u), width="stretch", hide_index=True)

    st.markdown("---")
    st.markdown("### Closed-Loop Simulation")
    st.caption("Alarm -> dispatch -> field verdict -> feedback -> rerun timeline.")
    scenarios = manifest["scenario_id"].astype(str).tolist() if not manifest.empty and "scenario_id" in manifest.columns else []
    if scenarios:
        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            sim_sid = st.selectbox("Scenario for simulation", scenarios, key="ops_closed_loop_sid")
        with c2:
            verdict = st.selectbox(
                "Field verdict",
                ["rejected_false_positive", "confirmed"],
                key="ops_closed_loop_verdict",
                format_func=lambda x: "Rejected false positive" if x == "rejected_false_positive" else "Confirmed",
            )
        with c3:
            sim_crews = st.number_input("Crews", min_value=1, max_value=20, value=3, step=1, key="ops_closed_loop_crews")
        if st.button("Run Closed-Loop Simulation", key="run_closed_loop_sim"):
            out = simulate_closed_loop(
                scenario_id=str(sim_sid),
                mode="local",
                field_verdict=str(verdict),
                max_crews=int(sim_crews),
                horizon_hours=24,
            )
            dcs = out.get("decision_change_summary", {}) if isinstance(out.get("decision_change_summary"), dict) else {}
            s1, s2, s3 = st.columns(3)
            with s1:
                st.metric("Loop Completed", _yes_no(bool(out.get("loop_completed"))))
            with s2:
                st.metric("Time To Action (min)", f"{_to_float(out.get('time_to_action_min')):.1f}")
            with s3:
                st.metric("Feedback Applied", _yes_no(bool(out.get("feedback_applied"))))
            if dcs:
                st.dataframe(
                    _readable_kv_table(
                        dcs,
                        key_label="Decision Change",
                        value_label="Value",
                    ),
                    width="stretch",
                    hide_index=True,
                )
            timeline = out.get("timeline", []) if isinstance(out.get("timeline"), list) else []
            if timeline:
                st.markdown("#### Closed-Loop Timeline")
                st.dataframe(_prettify_dataframe(pd.DataFrame(timeline)), width="stretch", hide_index=True)


def _render_incidents(manifest: pd.DataFrame) -> None:
    st.header("Incidents")
    if manifest.empty:
        st.warning("Manifest not found. Run: python scripts/create_manifest.py")
        return

    msg = str(st.session_state.pop("run_flash", "") or "").strip()
    if msg:
        st.success(f"Run completed: {msg}")
    err = str(st.session_state.pop("run_error", "") or "").strip()
    if err:
        st.error(f"Run failed: {err}")
    warn = str(st.session_state.pop("run_warning", "") or "").strip()
    if warn:
        st.warning(f"Warning: {warn}")
    note = str(st.session_state.pop("ops_context_note", "") or "").strip()
    if note:
        st.info(note)

    BUNDLES.mkdir(parents=True, exist_ok=True)
    files = sorted(BUNDLES.glob("*.json"))
    names = [p.name for p in files]
    if names and st.session_state.get("selected_bundle_name") not in names:
        st.session_state["selected_bundle_name"] = names[-1]
    bundle_path = BUNDLES / st.session_state["selected_bundle_name"] if names else None
    bundle = _safe_json(bundle_path) if bundle_path else {}
    rt0 = bundle.get("_runtime", {}) if isinstance(bundle.get("_runtime"), dict) else {}
    br0 = rt0.get("bedrock", {}) if isinstance(rt0.get("bedrock"), dict) else {}
    if bundle and str(rt0.get("mode", "")).strip().lower() == "bedrock" and not bool(br0.get("used")):
        live_name = _latest_live_bedrock_bundle()
        if live_name and live_name != st.session_state.get("selected_bundle_name"):
            st.warning("Selected bundle is Bedrock fallback-only. You can switch to the latest live Bedrock run.")
            if st.button("Switch To Latest Live Bedrock Bundle", key="switch_live_bedrock_bundle"):
                st.session_state["selected_bundle_name"] = live_name
                st.session_state["selected_bundle_picker"] = live_name
                st.rerun()

    label_map = {str(r["scenario_id"]): str(r["label"]) for _, r in manifest.iterrows() if "scenario_id" in r and "label" in r}
    rel = _reliability_snapshot(label_map)
    a, b, c, d = st.columns(4)
    with a:
        st.metric("Active Mode", "Bedrock")
    with b:
        status_raw = _bundle_status(bundle) if bundle else "No runs yet"
        st.metric("Bedrock Status", _friendly_bedrock_status(status_raw))
    with c:
        st.metric("Investigate to leak", f"{100.0 * _to_float(rel.get('inv_leak_rate')):.1f}%")
    with d:
        ts = str(bundle.get("evidence", {}).get("context", {}).get("timestamp", "-")) if bundle else "-"
        st.metric("Last Run", ts)
    presentation_mode = st.sidebar.toggle("Presentation mode", value=True, help="Reduces technical detail and prioritizes demo storytelling.")
    st.divider()
    _render_incident_flow_hint()

    left, center, right = st.columns([1.25, 1.8, 1.25], gap="large")
    with left:
        st.markdown("### 1) Run Scenario")
        run_mode = "bedrock"
        st.caption("Scan mode is locked to Bedrock for demo consistency.")
        for p in _quick_presets(manifest):
            track_label = _friendly_track_label(str(p.get("track", "") or ""))
            st.caption(f"{p['title']} - {p['scenario_id']} ({track_label})")
            if st.button(f"Scan {p['title']}", key=f"quick_{p['scenario_id']}"):
                _run_and_refresh(p["scenario_id"], run_mode, judge_mode=bool(st.session_state.get("judge_mode_ui", False)))
        with st.expander("Advanced Run"):
            scenarios = manifest["scenario_id"].astype(str).tolist()
            prefill = str(st.session_state.pop("incident_prefill_scenario", "") or "").strip()
            if prefill in scenarios:
                st.session_state["manual_sid"] = prefill
            if "manual_sid" not in st.session_state and scenarios:
                st.session_state["manual_sid"] = scenarios[0]
            sid = st.selectbox("Scenario", scenarios, key="manual_sid")
            st.caption("Mode: bedrock")
            judge_mode_ui = st.checkbox(
                "Judge mode (strict evidence trace)",
                value=bool(st.session_state.get("judge_mode_ui", False)),
                key="judge_mode_ui",
            )
            if st.button("Run Selected Scenario", type="primary"):
                _run_and_refresh(sid, "bedrock", judge_mode=bool(judge_mode_ui))
        st.markdown("---")
        st.markdown("### Bundle Picker")
        if names:
            if "selected_bundle_picker" not in st.session_state or st.session_state["selected_bundle_picker"] not in names:
                st.session_state["selected_bundle_picker"] = st.session_state["selected_bundle_name"]
            picked = st.selectbox("Bundle", names, key="selected_bundle_picker")
            if picked != st.session_state["selected_bundle_name"]:
                st.session_state["selected_bundle_name"] = picked
                st.rerun()
        else:
            st.info("Run a scenario to create bundles.")

    with center:
        if not bundle:
            st.info("No bundle selected.")
        else:
            st.markdown("### 2) Decision Review")
            decision = str(bundle.get("decision", "UNKNOWN")).upper()
            decision_label = _friendly_decision_label(decision)
            conf = _to_float(bundle.get("confidence"), 0.0)
            reason = str(bundle.get("investigate_reason_code", "") or "").strip()
            reason_label = _friendly_reason_label(reason)
            tone = "alert" if decision == "LEAK_CONFIRMED" else ("safe" if decision == "IGNORE_PLANNED_OPS" else "")
            st.markdown(
                f'<div class="ls-hero {tone}"><div class="ls-title">Decision</div><div class="ls-value">{html.escape(decision_label)}</div><div class="ls-sub">Confidence {conf:.2f} ({_confidence_band(conf)})</div><div class="ls-sub">Reason: {html.escape(reason_label)}</div></div>',
                unsafe_allow_html=True,
            )
            reason_text = _reason_explanation(decision=decision, reason_code=reason)
            st.markdown(
                f'<div class="ls-card" style="margin-top:10px;"><b>Reason (Plain Language)</b><br>{html.escape(reason_text)}</div>',
                unsafe_allow_html=True,
            )
            action = _humanize_slug(str(bundle.get("recommended_action", "") or "").strip())
            if action:
                st.markdown(f'<div class="ls-card" style="margin-top:10px;"><b>What To Do Now</b><br>{html.escape(action)}</div>', unsafe_allow_html=True)
            rationale = [str(x) for x in (bundle.get("rationale") or [])]
            if rationale:
                st.markdown("#### Why")
                for line in rationale[:3]:
                    st.write(f"- {_humanize_slug(line)}")
                if len(rationale) > 3:
                    with st.expander("Show full rationale"):
                        for line in rationale:
                            st.write(f"- {_humanize_slug(line)}")

    with right:
        if bundle:
            st.markdown("### 3) Trust Checks")
            rt = bundle.get("_runtime", {}) if isinstance(bundle.get("_runtime"), dict) else {}
            br = rt.get("bedrock", {}) if isinstance(rt.get("bedrock"), dict) else {}
            fb = br.get("fallback", {}) if isinstance(br.get("fallback"), dict) else {}
            ev = bundle.get("evidence", {}) if isinstance(bundle.get("evidence"), dict) else {}
            audio = ev.get("audio", {}) if isinstance(ev.get("audio"), dict) else {}
            flags = [str(x) for x in (bundle.get("decision_safety_flags") or [])]
            chips = "".join([f'<span class="ls-chip">{html.escape(_friendly_flag(f))}</span>' for f in (flags or ["no_safety_flags"])])
            st.markdown(f'<div class="ls-card"><b>Safety and Trust</b><br><small>Decision safety flags</small><br>{chips}</div>', unsafe_allow_html=True)
            jc = bundle.get("judge_compliance", {}) if isinstance(bundle.get("judge_compliance"), dict) else {}
            if jc:
                jc_pass = bool(jc.get("pass"))
                jc_state = "PASS" if jc_pass else "FAIL"
                jc_color = "#4cd18f" if jc_pass else "#f5b041"
                st.markdown(
                    f'<div class="ls-card" style="margin-top:10px;"><b>Judge Compliance</b><br>'
                    f'<span style="color:{jc_color};font-weight:700;">{jc_state}</span><br>'
                    f'<small>Enabled: {_yes_no(bool(jc.get("enabled")))} | Missing fields: {len(jc.get("missing_fields", []) or [])}</small></div>',
                    unsafe_allow_html=True,
                )
            st.metric("Bedrock used", _yes_no(bool(br.get("used"))))
            st.metric("Audio ran", _yes_no(not bool(audio.get("skipped"))))
            st.metric("Fallback", _yes_no(any(bool(v) for v in fb.values())))
            st.metric("Audio fusion", _friendly_value(br.get("audio_fusion", "-")))

    st.divider()
    if not bundle:
        return
    if presentation_mode:
        st.caption("Continue in order for the clearest narrative.")
        tabs = st.tabs(["1) Executive Report", "2) Demo Showcase", "3) Agents", "4) Evidence"])
    else:
        st.caption("Continue in order for the clearest narrative.")
        tabs = st.tabs(["1) Executive Report", "2) Demo Showcase", "3) Agents", "4) Evidence", "5) Trace", "6) History", "7) Impact", "8) Feedback"])

    with tabs[0]:
        _render_executive_report(bundle)

    with tabs[1]:
        _render_demo_showcase(bundle)

    with tabs[2]:
        _render_agent_pipeline(bundle)

    with tabs[3]:
        ev = bundle.get("evidence", {}) if isinstance(bundle.get("evidence"), dict) else {}
        ctx = ev.get("context", {}) if isinstance(ev.get("context"), dict) else {}
        flow = ctx.get("flow_summary", {}) if isinstance(ctx.get("flow_summary"), dict) else {}
        thermal = ev.get("thermal", {}) if isinstance(ev.get("thermal"), dict) else {}
        audio = ev.get("audio", {}) if isinstance(ev.get("audio"), dict) else {}
        audio_explain = bundle.get("audio_explain", {}) if isinstance(bundle.get("audio_explain"), dict) else {}
        ops = ev.get("ops", {}) if isinstance(ev.get("ops"), dict) else {}
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("Flow anomaly", f"{_to_float(flow.get('anomaly_score')):.3f}")
        with m2:
            thermal_state = "Hit" if bool(thermal.get("has_leak_signature")) else "No hit"
            st.metric("Thermal", f"{thermal_state} ({_to_float(thermal.get('confidence')):.2f})")
        with m3:
            if bool(audio.get("skipped")):
                st.metric("Audio", f"Skipped ({_humanize_slug(str(audio.get('reason', '-') or '-'))})")
            else:
                audio_state = "Hit" if bool(audio.get("leak_like")) else "No hit"
                st.metric("Audio", f"{audio_state} ({_to_float(audio.get('confidence')):.2f})")
        with m4:
            st.metric("Planned ops", _yes_no(bool(ops.get("planned_op_found"))))
        i1, i2 = st.columns(2)
        with i1:
            tpath = str(ctx.get("thermal_file", "") or "")
            if tpath and Path(tpath).exists():
                st.image(tpath, width="stretch")
        with i2:
            spath = str(ctx.get("spectrogram_file", "") or "")
            if spath and Path(spath).exists():
                st.image(spath, width="stretch")
        if audio_explain:
            st.markdown("#### Acoustic Why")
            top_bands = audio_explain.get("top_bands", []) if isinstance(audio_explain.get("top_bands"), list) else []
            if top_bands:
                st.dataframe(_prettify_dataframe(pd.DataFrame(top_bands)), width="stretch", hide_index=True)
            hiss = _to_float(audio_explain.get("hiss_score"), 0.0)
            tns = _to_float(audio_explain.get("transient_noise_score"), 0.0)
            e1, e2 = st.columns(2)
            with e1:
                st.metric("Hiss Score", f"{hiss:.2f}")
            with e2:
                st.metric("Transient Noise Score", f"{tns:.2f}")
            summary = str(audio_explain.get("plain_language_summary", "") or "").strip()
            if summary:
                st.write(_friendly_text(summary))

    if presentation_mode:
        return

    with tabs[4]:
        rt = bundle.get("_runtime", {}) if isinstance(bundle.get("_runtime"), dict) else {}
        br = rt.get("bedrock", {}) if isinstance(rt.get("bedrock"), dict) else {}
        ev = bundle.get("evidence", {}) if isinstance(bundle.get("evidence"), dict) else {}
        audio = ev.get("audio", {}) if isinstance(ev.get("audio"), dict) else {}
        t1, t2, t3, t4 = st.columns(4)
        with t1:
            st.metric("Mode", _humanize_slug(str(rt.get("mode", "-") or "-")).upper())
        with t2:
            st.metric("Track", _friendly_track_label(str(rt.get("track", "-") or "-")))
        with t3:
            st.metric("Audio ran", _yes_no(not bool(audio.get("skipped"))))
        with t4:
            st.metric("Audio fusion", _friendly_value(br.get("audio_fusion", "-")))
        req = br.get("request_ids", {}) if isinstance(br.get("request_ids"), dict) else {}
        fb = br.get("fallback", {}) if isinstance(br.get("fallback"), dict) else {}
        st.markdown("#### Request Trace")
        audio_status = (
            f"Skipped ({_humanize_slug(str(audio.get('reason', '-') or '-'))})"
            if bool(audio.get("skipped"))
            else ("Completed" if str(req.get("audio", "") or "").strip() else "Not executed")
        )
        st.dataframe(
            _prettify_dataframe(
                pd.DataFrame(
                    [
                        {
                            "Step": "Thermal analysis (Nova Pro)",
                            "Request ID": str(req.get("thermal", "-") or "-"),
                            "Outcome": "Completed" if str(req.get("thermal", "") or "").strip() else "Not executed",
                        },
                        {
                            "Step": "Audio analysis (Nova Pro)",
                            "Request ID": str(req.get("audio", "-") or "-"),
                            "Outcome": audio_status,
                        },
                        {
                            "Step": "Final decision (Nova Lite)",
                            "Request ID": str(req.get("decision", "-") or "-"),
                            "Outcome": "Completed" if str(req.get("decision", "") or "").strip() else "Not executed",
                        },
                    ]
                )
            ),
            width="stretch",
            hide_index=True,
        )
        st.markdown("#### Decision Guardrails")
        guardrails = br.get("decision_guardrails", []) if isinstance(br.get("decision_guardrails"), list) else []
        if guardrails:
            st.write(", ".join(_humanize_slug(str(x)) for x in guardrails))
        else:
            st.write("No guardrail override.")
        st.markdown("#### Fallback Usage")
        if fb:
            st.dataframe(
                _prettify_dataframe(
                    pd.DataFrame(
                        [
                            {
                                "Component": _humanize_key(str(k)),
                                "Fallback used": _yes_no(bool(v)),
                            }
                            for k, v in fb.items()
                        ]
                    )
                ),
                width="stretch",
                hide_index=True,
            )
        else:
            st.write("No fallback metadata.")
        trace = bundle.get("decision_trace_v1", {}) if isinstance(bundle.get("decision_trace_v1"), dict) else {}
        quality = bundle.get("evidence_quality_v1", {}) if isinstance(bundle.get("evidence_quality_v1"), dict) else {}
        calib = bundle.get("confidence_calibration_v1", {}) if isinstance(bundle.get("confidence_calibration_v1"), dict) else {}
        provenance = bundle.get("provenance_v1", {}) if isinstance(bundle.get("provenance_v1"), dict) else {}
        if trace:
            st.markdown("#### Decision Trace V1")
            steps = trace.get("steps", []) if isinstance(trace.get("steps"), list) else []
            if steps:
                st.dataframe(_prettify_dataframe(pd.DataFrame(steps)), width="stretch", hide_index=True)
        if quality:
            st.markdown("#### Evidence Quality")
            q1, q2 = st.columns(2)
            with q1:
                st.metric("Overall Quality Score", f"{_to_float(quality.get('overall_score')):.2f}")
            with q2:
                st.metric("Issue Count", len(quality.get("issues", []) or []))
            comps = quality.get("components", []) if isinstance(quality.get("components"), list) else []
            if comps:
                st.dataframe(_prettify_dataframe(pd.DataFrame(comps)), width="stretch", hide_index=True)
        if calib:
            st.markdown("#### Confidence Calibration")
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("Raw Confidence", f"{_to_float(calib.get('raw_confidence')):.2f}")
            with c2:
                st.metric("Calibrated Confidence", f"{_to_float(calib.get('calibrated_confidence')):.2f}")
            with c3:
                st.metric("Calibration Delta", f"{_to_float(calib.get('delta')):+.2f}")
        if provenance:
            st.markdown("#### Provenance")
            st.dataframe(
                _readable_kv_table(
                    provenance,
                    key_label="Provenance Field",
                    value_label="Value",
                ),
                width="stretch",
                hide_index=True,
            )
        judge = bundle.get("judge_compliance", {}) if isinstance(bundle.get("judge_compliance"), dict) else {}
        if judge:
            st.markdown("#### Judge Compliance")
            st.dataframe(
                _readable_kv_table(
                    judge,
                    key_label="Compliance Field",
                    value_label="Value",
                ),
                width="stretch",
                hide_index=True,
            )
    with tabs[5]:
        ev = bundle.get("evidence", {}) if isinstance(bundle.get("evidence"), dict) else {}
        sim = ev.get("similar_incidents", []) or []
        sim_m = ev.get("similar_mistakes", []) or []
        hrc = bundle.get("historical_root_causes", []) or []
        if sim:
            st.markdown("#### Similar Incidents")
            df_sim = pd.DataFrame(sim)
            st.dataframe(_prettify_dataframe(df_sim), width="stretch", hide_index=True)
        if sim_m:
            st.markdown("#### Similar Past Mistakes")
            df_sim_m = pd.DataFrame(sim_m)
            st.dataframe(_prettify_dataframe(df_sim_m), width="stretch", hide_index=True)
        if hrc:
            st.markdown("#### Historical Root-Cause Hints")
            df_hrc = pd.DataFrame(hrc)
            st.dataframe(_prettify_dataframe(df_hrc), width="stretch", hide_index=True)
        cls = bundle.get("closed_loop_summary_v1", {}) if isinstance(bundle.get("closed_loop_summary_v1"), dict) else {}
        if cls:
            st.markdown("#### Innovation Proof: Learning Loop")
            l1, l2, l3 = st.columns(3)
            with l1:
                st.metric("Similar Mistakes Seen", int(_to_float(cls.get("similar_mistakes_n"))))
            with l2:
                st.metric("Feedback Applied", _yes_no(bool(cls.get("feedback_applied"))))
            with l3:
                st.metric("Repeat FP Risk Reduction", f"{_to_float(cls.get('repeat_fp_risk_reduction_pct')):.1f}%")
        trend = _feedback_learning_trend(limit=30)
        st.markdown("#### Feedback Learning Trend")
        if str(trend.get("status", "")) != "ok":
            st.info("Trend status: insufficient data")
        else:
            t1, t2 = st.columns(2)
            with t1:
                st.metric("Feedback Effectiveness Rate", f"{100.0 * _to_float(trend.get('feedback_effectiveness_rate')):.1f}%")
            with t2:
                st.metric("Repeat FP Reduction Rate", f"{100.0 * _to_float(trend.get('repeat_fp_reduction_rate')):.1f}%")
        trend_rows = trend.get("rows", []) if isinstance(trend.get("rows"), list) else []
        if trend_rows:
            df_trend = pd.DataFrame(trend_rows)
            st.dataframe(_prettify_dataframe(df_trend), width="stretch", hide_index=True)
    with tabs[6]:
        continuous_flow = bundle.get("continuous_flow_alert", {}) if isinstance(bundle.get("continuous_flow_alert"), dict) else {}
        pressure_plan = bundle.get("pressure_plan", {}) if isinstance(bundle.get("pressure_plan"), dict) else {}
        scorecard = bundle.get("scorecard", {}) if isinstance(bundle.get("scorecard"), dict) else {}
        standards = bundle.get("standards_readiness", {}) if isinstance(bundle.get("standards_readiness"), dict) else {}
        impact_v2 = bundle.get("impact_estimate_v2", {}) if isinstance(bundle.get("impact_estimate_v2"), dict) else {}
        impact = bundle.get("impact_estimate", {}) if isinstance(bundle.get("impact_estimate"), dict) else {}
        cf_v2 = bundle.get("counterfactual_v2", {}) if isinstance(bundle.get("counterfactual_v2"), dict) else {}
        cf = bundle.get("counterfactual", {}) if isinstance(bundle.get("counterfactual"), dict) else {}
        ner_v2 = bundle.get("next_evidence_request_v2", {}) if isinstance(bundle.get("next_evidence_request_v2"), dict) else {}
        ner = bundle.get("next_evidence_request", {}) if isinstance(bundle.get("next_evidence_request"), dict) else {}
        impact_proof = bundle.get("impact_proof_v1", {}) if isinstance(bundle.get("impact_proof_v1"), dict) else {}
        if impact_v2 or impact:
            avoided_false_dispatch = _to_float(
                impact_v2.get("avoided_false_dispatch_usd", impact.get("avoided_false_dispatch_estimate")),
                0.0,
            )
            avoided_leak_loss = _to_float(
                impact_v2.get("avoided_leak_loss_usd", impact.get("avoided_leak_loss_estimate")),
                0.0,
            )
            total_impact = _to_float(
                impact_v2.get("expected_total_impact_usd"),
                avoided_false_dispatch + avoided_leak_loss,
            )
            x1, x2, x3 = st.columns(3)
            with x1:
                st.metric("Avoided False Dispatch (USD)", f"{avoided_false_dispatch:.0f}")
            with x2:
                st.metric("Avoided Leak Loss (USD)", f"{avoided_leak_loss:.0f}")
            with x3:
                st.metric("Total Expected Impact (USD)", f"{total_impact:.0f}")
            y1, y2, y3 = st.columns(3)
            with y1:
                st.metric("Risk Band", _humanize_slug(str((impact_v2 or impact).get("risk_band", "unknown"))))
            with y2:
                st.metric("Response Urgency", _humanize_slug(str(impact_v2.get("response_urgency", "n/a"))))
            with y3:
                st.metric("Impact Confidence", f"{_to_float(impact_v2.get('confidence'), _to_float(bundle.get('confidence'))):.2f}")
            assumptions = (
                impact_v2.get("assumptions", {})
                if isinstance(impact_v2.get("assumptions"), dict)
                else impact.get("assumptions", {})
                if isinstance(impact.get("assumptions"), dict)
                else {}
            )
            if assumptions:
                st.markdown("#### Assumptions")
                st.dataframe(
                    _readable_kv_table(
                        assumptions,
                        key_label="Assumption",
                        value_label="Value",
                    ),
                    width="stretch",
                    hide_index=True,
                )
            impact_rationale = str(impact_v2.get("impact_rationale", "") or "").strip()
            if impact_rationale:
                st.markdown("#### Impact Rationale")
                st.write(_humanize_slug(impact_rationale))
            sensitivity = impact_v2.get("sensitivity", {}) if isinstance(impact_v2.get("sensitivity"), dict) else {}
            if sensitivity:
                st.markdown("#### Sensitivity")
                st.dataframe(
                    _readable_kv_table(
                        sensitivity,
                        key_label="Sensitivity Parameter",
                        value_label="Value",
                    ),
                    width="stretch",
                    hide_index=True,
                )
        if impact_proof:
            st.markdown("#### Impact Proof (Baseline vs LeakSentinel)")
            bvs = (
                impact_proof.get("baseline_vs_with_leaksentinel", {})
                if isinstance(impact_proof.get("baseline_vs_with_leaksentinel"), dict)
                else {}
            )
            persona_applied = impact_proof.get("persona_applied", {}) if isinstance(impact_proof.get("persona_applied"), dict) else {}
            if persona_applied:
                st.caption(
                    f"Persona applied: {str(persona_applied.get('label', persona_applied.get('persona', 'utility')))}"
                )
            i1, i2, i3 = st.columns(3)
            with i1:
                st.metric("Baseline Loss (USD)", f"{_to_float(bvs.get('baseline_expected_loss_usd')):.0f}")
            with i2:
                st.metric("With LeakSentinel (USD)", f"{_to_float(bvs.get('with_leaksentinel_expected_loss_usd')):.0f}")
            with i3:
                st.metric("Estimated Savings (USD)", f"{_to_float(bvs.get('estimated_savings_usd')):.0f}")
            baseline_loss = _to_float(bvs.get("baseline_expected_loss_usd"), 0.0)
            with_system_loss = _to_float(bvs.get("with_leaksentinel_expected_loss_usd"), 0.0)
            if baseline_loss > 0.0:
                improvement_pct = max(0.0, (baseline_loss - with_system_loss) / baseline_loss) * 100.0
                st.metric("Loss Improvement", f"{improvement_pct:.1f}%")
            sband = impact_proof.get("assumption_sensitivity", {}) if isinstance(impact_proof.get("assumption_sensitivity"), dict) else {}
            if sband:
                st.dataframe(
                    _readable_kv_table(
                        sband,
                        key_label="Assumption Band",
                        value_label="Estimated Savings (USD)",
                    ),
                    width="stretch",
                    hide_index=True,
                )
            ibands = impact_proof.get("impact_bands", {}) if isinstance(impact_proof.get("impact_bands"), dict) else {}
            if ibands:
                st.dataframe(
                    _readable_kv_table(
                        ibands,
                        key_label="Impact Band",
                        value_label="Savings (USD)",
                    ),
                    width="stretch",
                    hide_index=True,
                )
        if continuous_flow:
            st.markdown("#### Continuous Flow Alert")
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("Detected", _yes_no(bool(continuous_flow.get("detected"))))
            with c2:
                st.metric("Severity", _humanize_slug(str(continuous_flow.get("severity", "low"))))
            with c3:
                st.metric("Duration (h)", f"{_to_float(continuous_flow.get('duration_hours')):.2f}")
            st.caption(str(continuous_flow.get("recommended_action", "") or ""))
        if pressure_plan:
            st.markdown("#### Pressure Autopilot")
            p1, p2, p3 = st.columns(3)
            with p1:
                st.metric("Current Pressure (m)", f"{_to_float(pressure_plan.get('current_pressure_m')):.1f}")
            with p2:
                st.metric("Recommended Setpoint (m)", f"{_to_float(pressure_plan.get('recommended_setpoint_m')):.1f}")
            with p3:
                st.metric("Expected Leak Risk Delta", f"{_to_float(pressure_plan.get('expected_leak_risk_delta_pct')):.1f}%")
        if scorecard:
            st.markdown("#### NRW + Carbon Scorecard")
            s1, s2, s3 = st.columns(3)
            with s1:
                st.metric("Water Saved (m3)", f"{_to_float(scorecard.get('estimated_water_saved_m3')):.2f}")
            with s2:
                st.metric("Cost Saved (USD)", f"{_to_float(scorecard.get('estimated_cost_saved_usd')):.0f}")
            with s3:
                st.metric("CO2e Avoided (kg)", f"{_to_float(scorecard.get('estimated_co2e_kg_avoided')):.2f}")
            s4, s5 = st.columns(2)
            with s4:
                st.metric("NRW Risk Band", _humanize_slug(str(scorecard.get("nrw_risk_band", "unknown"))))
            with s5:
                st.metric("Projected NRW %", f"{_to_float(scorecard.get('projected_nrw_pct')):.2f}")
        if standards:
            st.markdown("#### Standards Readiness")
            r1, r2, r3 = st.columns(3)
            with r1:
                st.metric("Readiness Score", f"{_to_float(standards.get('score')):.1f}")
            with r2:
                st.metric("Level", _humanize_slug(str(standards.get("level", "red"))))
            with r3:
                st.metric("Missing Controls", str(len(standards.get("missing_controls", []) or [])))
            missing_controls = standards.get("missing_controls", []) if isinstance(standards.get("missing_controls"), list) else []
            if missing_controls:
                st.dataframe(_prettify_dataframe(pd.DataFrame(missing_controls)), width="stretch", hide_index=True)
        st.markdown("#### Next Best Evidence Request")
        if ner_v2 or ner:
            ner_view = ner_v2 if ner_v2 else ner
            st.dataframe(
                _readable_kv_table(
                    ner_view,
                    key_label="Requested Evidence",
                    value_label="Details",
                ),
                width="stretch",
                hide_index=True,
            )
        else:
            st.write("No additional evidence request.")
        st.markdown("#### Counterfactual Analysis")
        if cf_v2:
            cfd = cf_v2.get("decision_delta", {}) if isinstance(cf_v2.get("decision_delta"), dict) else {}
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("Decision Flips", _yes_no(bool(cfd.get("flipped"))))
            with c2:
                st.metric("Flip Rate", f"{100.0 * _to_float(cfd.get('flip_rate')):.1f}%")
            with c3:
                st.metric("Stability Score", f"{_to_float(cf_v2.get('stability_score')):.2f}")
            scenarios = cf_v2.get("scenarios", []) if isinstance(cf_v2.get("scenarios"), list) else []
            if scenarios:
                st.dataframe(_prettify_dataframe(pd.DataFrame(scenarios)), width="stretch", hide_index=True)
            reco = str(cf_v2.get("recommendation_if_flips", "") or "").strip()
            if reco:
                st.caption(reco)
        elif cf:
            st.dataframe(
                _readable_kv_table(
                    cf,
                    key_label="Counterfactual Field",
                    value_label="Value",
                ),
                width="stretch",
                hide_index=True,
            )
        else:
            st.write("No counterfactual output.")
    with tabs[7]:
        _render_feedback(bundle, bundle_path)


_load_env_fallback()
st.set_page_config(page_title="LeakSentinel", layout="wide")
_inject_styles()
_render_header_shell()
voice_url = os.getenv("LEAKSENTINEL_VOICE_URL", "http://127.0.0.1:8000/demo/voice_demo.html?api=http://127.0.0.1:8000")
v1, v2 = st.columns([6, 2])
with v1:
    st.caption(f"Voice demo URL: {voice_url}")
with v2:
    st.link_button("Open Voice Demo", voice_url, use_container_width=True)

if "page_nav" not in st.session_state:
    st.session_state["page_nav"] = "Incidents"
if "run_mode_select" not in st.session_state:
    st.session_state["run_mode_select"] = "bedrock"

manifest_df = pd.read_csv(MANIFEST) if MANIFEST.exists() else pd.DataFrame()
page = st.sidebar.radio("Page", ["Incidents", "Ops Portal"], key="page_nav", format_func=lambda x: "Incidents" if x == "Incidents" else "Ops Portal")

if page == "Ops Portal":
    _render_ops(manifest_df)
else:
    _render_incidents(manifest_df)

