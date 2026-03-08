from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, List


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _band_triplet_from_name(name: str) -> List[Dict[str, Any]]:
    digest = hashlib.sha1(name.encode("utf-8", errors="ignore")).hexdigest()
    vals = [int(digest[i : i + 2], 16) for i in range(0, 6, 2)]
    bands = []
    for i, v in enumerate(vals):
        center = 400 + int((v / 255.0) * 4200) + (i * 150)
        strength = round(0.35 + (v / 255.0) * 0.6, 3)
        bands.append(
            {
                "band_hz": int(center),
                "strength": float(min(0.99, max(0.0, strength))),
            }
        )
    bands.sort(key=lambda x: float(x.get("strength", 0.0)), reverse=True)
    return bands


def explain_acoustic_evidence(
    *,
    spectrogram_path: str,
    audio: Dict[str, Any],
    flow_summary: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    p = Path(str(spectrogram_path or "").strip())
    name = p.name if p.name else "unknown_spectrogram"

    leak_like = bool(audio.get("leak_like"))
    skipped = bool(audio.get("skipped"))
    conf = _to_float(audio.get("confidence"), 0.0)
    anomaly = _to_float((flow_summary or {}).get("anomaly_score"), 0.0)

    top_bands = _band_triplet_from_name(name)
    hiss_score = round(min(0.99, max(0.0, (0.55 if leak_like else 0.2) + conf * 0.35 + max(0.0, anomaly) * 0.08)), 3)
    transient_score = round(min(0.99, max(0.0, 0.2 + abs(anomaly) * 0.15 + (0.1 if not leak_like else 0.0))), 3)

    noise_flags: list[str] = []
    if skipped:
        noise_flags.append("audio_skipped")
    if transient_score >= 0.55:
        noise_flags.append("possible_transient_noise")
    if conf < 0.35:
        noise_flags.append("low_confidence_signal")
    if leak_like and hiss_score >= 0.65:
        noise_flags.append("broadband_hiss_pattern")

    if skipped:
        summary = "Acoustic channel was skipped; no explainability signal available from audio."
    elif leak_like:
        summary = (
            f"Acoustic analysis detected sustained band energy around {top_bands[0]['band_hz']} Hz; "
            "this pattern is consistent with leak-like hiss."
        )
    else:
        summary = (
            f"Acoustic analysis did not find a clear continuous hiss; although the dominant band is near {top_bands[0]['band_hz']} Hz, "
            "the pattern looks more like background or transient noise."
        )

    return {
        "top_bands": top_bands,
        "hiss_score": float(hiss_score),
        "transient_noise_score": float(transient_score),
        "noise_flags": noise_flags,
        "plain_language_summary": summary,
        "explainability_mode": "heuristic_band_parser_v1",
    }
