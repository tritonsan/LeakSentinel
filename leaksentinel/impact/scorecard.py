from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _clamp(v: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, float(v))))


def _default_assumptions_register() -> Dict[str, Any]:
    return {
        "impact": {
            "dispatch_cost_usd": 1200.0,
            "leak_loss_per_hour_usd": 5000.0,
            "default_delay_hours": 1.0,
            "investigate_dispatch_factor": 0.25,
            "investigate_leak_factor": 0.15,
        },
        "scorecard": {
            "water_unit_cost_usd_per_m3": 1.8,
            "co2e_kg_per_m3": 0.45,
            "baseline_nrw_pct": 24.0,
        },
    }


def load_assumptions_register(
    *,
    path: Path = Path("data/impact/assumptions.json"),
    default_obj: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    default_payload = default_obj if isinstance(default_obj, dict) else _default_assumptions_register()
    try:
        if Path(path).exists():
            obj = json.loads(Path(path).read_text(encoding="utf-8"))
            if isinstance(obj, dict):
                return obj
    except Exception:
        pass
    return default_payload


def _scorecard_assumptions(register: Dict[str, Any]) -> Dict[str, float]:
    reg = register if isinstance(register, dict) else {}
    score = reg.get("scorecard", {}) if isinstance(reg.get("scorecard"), dict) else {}
    return {
        "water_unit_cost_usd_per_m3": _to_float(score.get("water_unit_cost_usd_per_m3"), 1.8),
        "co2e_kg_per_m3": _to_float(score.get("co2e_kg_per_m3"), 0.45),
        "baseline_nrw_pct": _to_float(score.get("baseline_nrw_pct"), 24.0),
    }


def build_nrw_carbon_scorecard(
    *,
    decision: Dict[str, Any],
    impact_estimate_v2: Dict[str, Any] | None,
    impact_estimate_v1: Dict[str, Any] | None,
    continuous_flow_alert: Optional[Dict[str, Any]] = None,
    water_unit_cost_usd_per_m3: Optional[float] = None,
    co2e_kg_per_m3: Optional[float] = None,
    baseline_nrw_pct: Optional[float] = None,
    assumptions_register: Optional[Dict[str, Any]] = None,
    assumptions_path: Path = Path("data/impact/assumptions.json"),
) -> Dict[str, Any]:
    d = str((decision or {}).get("decision", "INVESTIGATE")).strip().upper()
    conf = _clamp(_to_float((decision or {}).get("confidence"), 0.0), 0.0, 1.0)
    v2 = impact_estimate_v2 if isinstance(impact_estimate_v2, dict) else {}
    v1 = impact_estimate_v1 if isinstance(impact_estimate_v1, dict) else {}
    register = assumptions_register if isinstance(assumptions_register, dict) else load_assumptions_register(path=assumptions_path)
    defaults = _scorecard_assumptions(register)
    water_unit_cost = max(
        1e-6,
        _to_float(
            water_unit_cost_usd_per_m3,
            _to_float(defaults.get("water_unit_cost_usd_per_m3"), 1.8),
        ),
    )
    co2_factor = max(
        0.0,
        _to_float(
            co2e_kg_per_m3,
            _to_float(defaults.get("co2e_kg_per_m3"), 0.45),
        ),
    )
    baseline_nrw = _clamp(
        _to_float(
            baseline_nrw_pct,
            _to_float(defaults.get("baseline_nrw_pct"), 24.0),
        ),
        0.0,
        100.0,
    )

    cost_saved = _to_float(v2.get("expected_total_impact_usd"), float("nan"))
    if cost_saved != cost_saved:  # NaN check
        cost_saved = _to_float(v1.get("avoided_false_dispatch_estimate"), 0.0) + _to_float(
            v1.get("avoided_leak_loss_estimate"), 0.0
        )
    cost_saved = max(0.0, cost_saved)

    water_saved_m3 = max(0.0, cost_saved / water_unit_cost)
    if d == "IGNORE_PLANNED_OPS":
        water_saved_m3 = water_saved_m3 * 0.35
    elif d == "INVESTIGATE":
        water_saved_m3 = water_saved_m3 * 0.55

    cf = continuous_flow_alert if isinstance(continuous_flow_alert, dict) else {}
    if bool(cf.get("detected")):
        sev = str(cf.get("severity", "")).strip().lower()
        mult = {"high": 1.2, "medium": 1.1, "low": 1.03}.get(sev, 1.05)
        water_saved_m3 = water_saved_m3 * mult

    co2e_avoided = max(0.0, water_saved_m3 * co2_factor)
    nrw_drop_pct = _clamp((water_saved_m3 / max(1.0, 5000.0)) * 100.0, 0.0, baseline_nrw)
    projected_nrw = _clamp(baseline_nrw - nrw_drop_pct, 0.0, 100.0)

    if projected_nrw <= max(10.0, baseline_nrw * 0.65):
        nrw_risk_band = "low"
    elif projected_nrw <= max(18.0, baseline_nrw * 0.85):
        nrw_risk_band = "medium"
    else:
        nrw_risk_band = "high"

    return {
        "estimated_water_saved_m3": round(water_saved_m3, 3),
        "estimated_cost_saved_usd": round(cost_saved, 2),
        "estimated_co2e_kg_avoided": round(co2e_avoided, 3),
        "nrw_risk_band": nrw_risk_band,
        "projected_nrw_pct": round(projected_nrw, 3),
        "confidence": round(max(0.2, conf), 3),
        "assumptions": {
            "water_unit_cost_usd_per_m3": float(water_unit_cost),
            "co2e_kg_per_m3": float(co2_factor),
            "baseline_nrw_pct": float(baseline_nrw),
        },
        "source": "deterministic_scorecard_v2",
    }
