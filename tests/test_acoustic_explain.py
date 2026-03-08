from __future__ import annotations

from leaksentinel.tools.acoustic_explain import explain_acoustic_evidence


def test_acoustic_explain_produces_readable_fields() -> None:
    out = explain_acoustic_evidence(
        spectrogram_path="data/spectrogram/zone-1/leak_01.png",
        audio={"leak_like": True, "confidence": 0.8, "skipped": False},
        flow_summary={"anomaly_score": 1.2},
    )
    assert isinstance(out.get("top_bands"), list)
    assert len(out.get("top_bands") or []) == 3
    assert "plain_language_summary" in out
    assert "hiss_score" in out
