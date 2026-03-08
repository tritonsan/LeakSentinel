from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _clamp(v: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, float(v))))


def _bundle_saved_usd(bundle: Dict[str, Any]) -> float:
    b = bundle if isinstance(bundle, dict) else {}
    iv2 = b.get("impact_estimate_v2", {}) if isinstance(b.get("impact_estimate_v2"), dict) else {}
    iv1 = b.get("impact_estimate", {}) if isinstance(b.get("impact_estimate"), dict) else {}
    total = _to_float(iv2.get("expected_total_impact_usd"), float("nan"))
    if total != total:
        total = _to_float(iv1.get("avoided_false_dispatch_estimate"), 0.0) + _to_float(
            iv1.get("avoided_leak_loss_estimate"),
            0.0,
        )
    return max(0.0, float(total))


def _bundle_water_m3(bundle: Dict[str, Any], *, water_cost_usd_per_m3: float) -> float:
    sc = bundle.get("scorecard", {}) if isinstance(bundle.get("scorecard"), dict) else {}
    from_scorecard = _to_float(sc.get("estimated_water_saved_m3"), float("nan"))
    if from_scorecard == from_scorecard:
        return max(0.0, from_scorecard)
    saved_usd = _bundle_saved_usd(bundle)
    return max(0.0, saved_usd / max(1e-6, float(water_cost_usd_per_m3)))


def _assumptions(assumptions_register: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    reg = assumptions_register if isinstance(assumptions_register, dict) else {}
    impact = reg.get("impact", {}) if isinstance(reg.get("impact"), dict) else {}
    score = reg.get("scorecard", {}) if isinstance(reg.get("scorecard"), dict) else {}
    sens = reg.get("sensitivity", {}) if isinstance(reg.get("sensitivity"), dict) else {}
    low = _clamp(_to_float(sens.get("low_multiplier"), 0.8), 0.3, 1.0)
    mid = _clamp(_to_float(sens.get("mid_multiplier"), 1.0), low, 1.5)
    high = _clamp(_to_float(sens.get("high_multiplier"), 1.2), mid, 2.0)
    return {
        "impact": {
            "dispatch_cost_usd": _to_float(impact.get("dispatch_cost_usd"), 1200.0),
            "leak_loss_per_hour_usd": _to_float(impact.get("leak_loss_per_hour_usd"), 5000.0),
            "default_delay_hours": _to_float(impact.get("default_delay_hours"), 1.0),
        },
        "scorecard": {
            "water_unit_cost_usd_per_m3": _to_float(score.get("water_unit_cost_usd_per_m3"), 1.8),
            "co2e_kg_per_m3": _to_float(score.get("co2e_kg_per_m3"), 0.45),
        },
        "sensitivity": {"low": low, "mid": mid, "high": high},
    }


def _default_personas() -> Dict[str, Any]:
    return {
        "utility": {
            "label": "Municipal Utility",
            "impact_multiplier": 1.0,
            "delay_multiplier": 1.0,
            "water_cost_multiplier": 1.0,
            "co2e_multiplier": 1.0,
        },
        "industrial": {
            "label": "Industrial Plant",
            "impact_multiplier": 1.15,
            "delay_multiplier": 1.2,
            "water_cost_multiplier": 1.25,
            "co2e_multiplier": 1.05,
        },
        "campus": {
            "label": "Campus / Facility",
            "impact_multiplier": 0.9,
            "delay_multiplier": 0.95,
            "water_cost_multiplier": 0.9,
            "co2e_multiplier": 0.95,
        },
    }


def _load_personas(path: Path) -> Dict[str, Any]:
    defaults = _default_personas()
    try:
        if Path(path).exists():
            obj = json.loads(Path(path).read_text(encoding="utf-8"))
            if isinstance(obj, dict):
                return obj
    except Exception:
        pass
    return defaults


def _persona_profile(persona: str, personas: Dict[str, Any]) -> Dict[str, Any]:
    pnorm = str(persona or "utility").strip().lower()
    src = personas if isinstance(personas, dict) else _default_personas()
    prof = src.get(pnorm) if isinstance(src.get(pnorm), dict) else src.get("utility", {})
    out = {
        "persona": pnorm if pnorm in src else "utility",
        "label": str(prof.get("label", pnorm.title())),
        "impact_multiplier": _clamp(_to_float(prof.get("impact_multiplier"), 1.0), 0.5, 2.0),
        "delay_multiplier": _clamp(_to_float(prof.get("delay_multiplier"), 1.0), 0.5, 2.0),
        "water_cost_multiplier": _clamp(_to_float(prof.get("water_cost_multiplier"), 1.0), 0.5, 2.0),
        "co2e_multiplier": _clamp(_to_float(prof.get("co2e_multiplier"), 1.0), 0.5, 2.0),
    }
    return out


def build_impact_compare(
    *,
    bundles: List[Dict[str, Any]],
    assumptions_register: Optional[Dict[str, Any]] = None,
    persona: str = "utility",
    personas_path: Path = Path("data/impact/personas.json"),
) -> Dict[str, Any]:
    rows = [b for b in (bundles or []) if isinstance(b, dict)]
    a = _assumptions(assumptions_register)
    personas = _load_personas(personas_path)
    pp = _persona_profile(persona, personas)
    dispatch_cost = _to_float(a["impact"]["dispatch_cost_usd"], 1200.0) * _to_float(pp.get("impact_multiplier"), 1.0)
    leak_per_h = _to_float(a["impact"]["leak_loss_per_hour_usd"], 5000.0) * _to_float(pp.get("impact_multiplier"), 1.0)
    delay_h = _to_float(a["impact"]["default_delay_hours"], 1.0) * _to_float(pp.get("delay_multiplier"), 1.0)
    water_cost = _to_float(a["scorecard"]["water_unit_cost_usd_per_m3"], 1.8) * _to_float(pp.get("water_cost_multiplier"), 1.0)
    co2_factor = _to_float(a["scorecard"]["co2e_kg_per_m3"], 0.45) * _to_float(pp.get("co2e_multiplier"), 1.0)

    total_saved_usd = 0.0
    total_water_m3 = 0.0
    scenario_ids: List[str] = []
    for b in rows:
        total_saved_usd += _bundle_saved_usd(b)
        total_water_m3 += _bundle_water_m3(b, water_cost_usd_per_m3=water_cost)
        ctx = (b.get("evidence") or {}).get("context") if isinstance(b.get("evidence"), dict) else {}
        if isinstance(ctx, dict):
            sid = str(ctx.get("scenario_id", "") or "").strip()
            if sid:
                scenario_ids.append(sid)

    baseline_unit_loss = (leak_per_h * max(0.1, delay_h)) + (dispatch_cost * 0.5)
    baseline_total_loss = max(total_saved_usd, baseline_unit_loss * max(1, len(rows)))
    with_system_loss = max(0.0, baseline_total_loss - total_saved_usd)
    sens = a.get("sensitivity", {}) if isinstance(a.get("sensitivity"), dict) else {}
    sensitivity = {
        "min": round(total_saved_usd * _to_float(sens.get("low"), 0.8), 2),
        "median": round(total_saved_usd * _to_float(sens.get("mid"), 1.0), 2),
        "max": round(total_saved_usd * _to_float(sens.get("high"), 1.2), 2),
    }
    impact_bands = {
        "conservative": sensitivity["min"],
        "expected": sensitivity["median"],
        "aggressive": sensitivity["max"],
    }

    return {
        "mode": "impact_compare_v1",
        "persona_applied": {
            "persona": str(pp.get("persona", "utility")),
            "label": str(pp.get("label", "Municipal Utility")),
        },
        "bundle_count": int(len(rows)),
        "scenario_ids": sorted(set(scenario_ids)),
        "baseline_vs_with_leaksentinel": {
            "baseline_expected_loss_usd": round(baseline_total_loss, 2),
            "with_leaksentinel_expected_loss_usd": round(with_system_loss, 2),
            "estimated_savings_usd": round(total_saved_usd, 2),
        },
        "water_saved_m3": round(total_water_m3, 3),
        "cost_saved_usd": round(total_saved_usd, 2),
        "co2e_avoided_kg": round(total_water_m3 * max(0.0, co2_factor), 3),
        "assumption_sensitivity": sensitivity,
        "impact_bands": impact_bands,
        "assumptions_used": {
            "dispatch_cost_usd": dispatch_cost,
            "leak_loss_per_hour_usd": leak_per_h,
            "default_delay_hours": delay_h,
            "water_unit_cost_usd_per_m3": water_cost,
            "co2e_kg_per_m3": co2_factor,
        },
    }
