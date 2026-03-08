from __future__ import annotations

from typing import Any, Dict


def apply_confidence_downshift(
    *,
    decision: Dict[str, Any],
    similar_mistakes: list[Dict[str, Any]],
    min_score: float = 0.82,
    base_downshift: float = 0.10,
    per_extra_match: float = 0.03,
    max_downshift: float = 0.20,
    min_confidence: float = 0.35,
) -> Dict[str, Any]:
    out = dict(decision)
    rationale = [str(x) for x in (out.get("rationale") or [])]

    qualifying = []
    for m in similar_mistakes or []:
        try:
            score = float(m.get("score", 0.0))
        except Exception:
            score = 0.0
        if score >= float(min_score):
            qualifying.append(m)

    if not qualifying:
        return {"applied": False, "decision": out, "policy": {"qualifying_n": 0, "min_score": float(min_score)}}

    try:
        old_conf = float(out.get("confidence", 0.0))
    except Exception:
        old_conf = 0.0

    down = float(base_downshift) + float(per_extra_match) * max(0, len(qualifying) - 1)
    down = min(float(max_downshift), max(0.0, down))
    new_conf = max(float(min_confidence), old_conf - down)

    applied = new_conf < old_conf
    if applied:
        out["confidence"] = float(new_conf)
        out["rationale"] = rationale + [
            (
                "Historical false-positive similarity detected "
                f"(n={len(qualifying)}, max_score={max(float(m.get('score', 0.0)) for m in qualifying):.2f}); "
                "confidence reduced pending operator confirmation."
            )
        ]

    return {
        "applied": applied,
        "decision": out,
        "policy": {
            "qualifying_n": len(qualifying),
            "min_score": float(min_score),
            "old_confidence": float(old_conf),
            "new_confidence": float(out.get("confidence", old_conf)),
            "downshift": float(old_conf - float(out.get("confidence", old_conf))),
        },
    }
