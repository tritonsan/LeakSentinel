from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List


def extract_json_object(text: str) -> Dict[str, Any]:
    """
    Extract a JSON object from model output that may include extra text.
    Returns the first successfully parsed JSON object.
    """
    if not text:
        raise ValueError("empty text")

    s = text.strip()
    if s.startswith("{") and s.endswith("}"):
        return json.loads(s)

    # Scan for balanced braces and try parsing candidate substrings.
    start = None
    depth = 0
    for i, ch in enumerate(s):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    cand = s[start : i + 1]
                    try:
                        obj = json.loads(cand)
                        if isinstance(obj, dict):
                            return obj
                    except Exception:
                        pass
                    start = None

    raise ValueError("no JSON object found in text")


def _require_keys(obj: Dict[str, Any], keys: Iterable[str]) -> None:
    missing = [k for k in keys if k not in obj]
    if missing:
        raise ValueError(f"missing keys: {missing}")


def _as_float(x: Any) -> float:
    try:
        return float(x)
    except Exception as e:
        raise ValueError(f"expected float-like, got {type(x)}") from e


def _as_str(x: Any) -> str:
    if x is None:
        raise ValueError("expected str, got None")
    return str(x)


def _as_str_list(x: Any) -> List[str]:
    if x is None:
        return []
    if not isinstance(x, list):
        raise ValueError(f"expected list, got {type(x)}")
    return [str(v) for v in x]


def validate_decision_schema(obj: Dict[str, Any]) -> None:
    _require_keys(obj, ["decision", "confidence", "rationale", "recommended_action", "evidence_weights"])
    _as_str(obj.get("decision"))
    c = _as_float(obj.get("confidence"))
    if not (0.0 <= c <= 1.0):
        raise ValueError("confidence out of range 0..1")
    _as_str_list(obj.get("rationale"))
    _as_str(obj.get("recommended_action"))
    ew = obj.get("evidence_weights")
    if not isinstance(ew, dict):
        raise ValueError("evidence_weights must be a dict")


def validate_thermal_schema(obj: Dict[str, Any]) -> None:
    _require_keys(obj, ["has_leak_signature", "confidence", "explanation"])
    if not isinstance(obj.get("has_leak_signature"), bool):
        raise ValueError("has_leak_signature must be bool")
    c = _as_float(obj.get("confidence"))
    if not (0.0 <= c <= 1.0):
        raise ValueError("confidence out of range 0..1")
    _as_str(obj.get("explanation"))


def validate_audio_schema(obj: Dict[str, Any]) -> None:
    _require_keys(obj, ["leak_like", "confidence", "explanation"])
    if not isinstance(obj.get("leak_like"), bool):
        raise ValueError("leak_like must be bool")
    c = _as_float(obj.get("confidence"))
    if not (0.0 <= c <= 1.0):
        raise ValueError("confidence out of range 0..1")
    _as_str(obj.get("explanation"))

