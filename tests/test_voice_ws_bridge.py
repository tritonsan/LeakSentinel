from __future__ import annotations

import base64

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import services.api.main as api_main


def test_voice_ws_bridge_stream_flow(monkeypatch) -> None:
    def fake_post_json(url: str, payload: dict, *, timeout: int = 180) -> dict:
        assert url.endswith("/v1/voice/sonic")
        assert payload.get("sampleRateHertz") == 16000
        assert payload.get("audioPcm16Base64")
        wav_bytes = b"RIFF____WAVEfmt "  # minimal bytes; client only relays chunks.
        return {
            "ok": True,
            "transcript": "zone-1 likely planned operation",
            "response_audio_wav_base64": base64.b64encode(wav_bytes).decode("ascii"),
            "model_id_used": "amazon.nova-sonic-v1:0",
        }

    monkeypatch.setattr(api_main, "_post_json", fake_post_json)
    client = TestClient(api_main.app)

    with client.websocket_connect("/ws/voice") as ws:
        ready = ws.receive_json()
        assert ready["type"] == "ready"

        ws.send_json({"type": "start", "sampleRateHertz": 16000, "userText": "what happened?"})
        ws.send_json({"type": "audio_chunk", "audioPcm16Base64": base64.b64encode(b"\x00\x01" * 200).decode("ascii")})
        ws.send_json({"type": "end"})

        events = []
        for _ in range(12):
            msg = ws.receive_json()
            events.append(msg["type"])
            if msg["type"] == "done":
                assert msg["ok"] is True
                assert msg["model_id_used"] == "amazon.nova-sonic-v1:0"
                break

    assert "started" in events
    assert "processing" in events
    assert "transcript_final" in events
    assert "audio_chunk" in events
    assert "done" in events


def test_voice_ws_bridge_requires_start() -> None:
    client = TestClient(api_main.app)
    with client.websocket_connect("/ws/voice") as ws:
        _ = ws.receive_json()  # ready
        ws.send_json({"type": "audio_chunk", "audioPcm16Base64": base64.b64encode(b"abc").decode("ascii")})
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["code"] == "session_not_started"


def test_health_includes_voice_backend_probe(monkeypatch) -> None:
    monkeypatch.setattr(
        api_main,
        "_probe_voice_backend_health",
        lambda timeout=2: {"reachable": True, "status": "up", "detail": {"ok": True}, "url": "http://x/health"},
    )
    client = TestClient(api_main.app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["voice_backend"]["reachable"] is True
