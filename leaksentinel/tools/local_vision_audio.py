from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


def local_thermal_check(image_path: str) -> Dict[str, Any]:
    """
    Local heuristic thermal check.
    For demo data: if filename contains 'leak_' -> high confidence.
    """
    p = Path(image_path)
    if not image_path or not p.exists():
        return {"has_leak_signature": False, "confidence": 0.0, "explanation": "Thermal image missing."}
    name = p.name.lower()
    if "leak_" in name:
        return {"has_leak_signature": True, "confidence": 0.85, "explanation": "Leak-like hotspot pattern (heuristic)."}
    return {"has_leak_signature": False, "confidence": 0.2, "explanation": "No hotspot detected (heuristic)."}


def local_audio_check(spec_path: str) -> Dict[str, Any]:
    """
    Local heuristic audio check from spectrogram filename.
    For demo data: if filename contains 'leak_' -> high confidence.
    """
    p = Path(spec_path)
    if not spec_path or not p.exists():
        return {"leak_like": False, "confidence": 0.0, "explanation": "Spectrogram missing."}
    name = p.name.lower()
    if "leak_" in name:
        return {"leak_like": True, "confidence": 0.8, "explanation": "Broadband hiss-like signature (heuristic)."}
    return {"leak_like": False, "confidence": 0.2, "explanation": "No leak-like banding (heuristic)."}

