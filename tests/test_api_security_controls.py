from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import services.api.main as api_main


def _stub_run_scenario(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_main, "run_scenario", lambda **kwargs: {"ok": True, "scenario_id": kwargs.get("scenario_id", "")})


def test_auth_monitor_allows_request_and_marks_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_run_scenario(monkeypatch)
    monkeypatch.setenv("LEAKSENTINEL_AUTH_ENFORCEMENT", "monitor")
    monkeypatch.setenv("LEAKSENTINEL_API_KEYS", "demo-key")
    monkeypatch.setenv("LEAKSENTINEL_RATE_LIMIT_ENFORCEMENT", "off")
    api_main._reset_rate_limit_state()

    client = TestClient(api_main.app)
    resp = client.post("/run", json={"scenario_id": "S02", "mode": "local"})
    assert resp.status_code == 200
    assert resp.headers.get("X-Auth-Mode") == "monitor"
    assert resp.headers.get("X-Auth-Monitor-Warning") == "monitor_missing_or_invalid_api_key"


def test_auth_on_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_run_scenario(monkeypatch)
    monkeypatch.setenv("LEAKSENTINEL_AUTH_ENFORCEMENT", "on")
    monkeypatch.setenv("LEAKSENTINEL_API_KEYS", "demo-key")
    monkeypatch.setenv("LEAKSENTINEL_RATE_LIMIT_ENFORCEMENT", "off")
    api_main._reset_rate_limit_state()

    client = TestClient(api_main.app)
    denied = client.post("/run", json={"scenario_id": "S02", "mode": "local"})
    assert denied.status_code == 401
    assert denied.json().get("code") == "missing_or_invalid_api_key"

    allowed = client.post("/run", json={"scenario_id": "S02", "mode": "local"}, headers={"X-API-Key": "demo-key"})
    assert allowed.status_code == 200
    assert allowed.headers.get("X-Auth-Mode") == "on"


def test_rate_limit_on_returns_429(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_run_scenario(monkeypatch)
    monkeypatch.setenv("LEAKSENTINEL_AUTH_ENFORCEMENT", "off")
    monkeypatch.setenv("LEAKSENTINEL_RATE_LIMIT_ENFORCEMENT", "on")
    monkeypatch.setenv("LEAKSENTINEL_RATE_LIMIT_PER_MINUTE", "1")
    api_main._reset_rate_limit_state()

    client = TestClient(api_main.app)
    first = client.post("/run", json={"scenario_id": "S02", "mode": "local"})
    second = client.post("/run", json={"scenario_id": "S02", "mode": "local"})
    assert first.status_code == 200
    assert second.status_code == 429
    assert second.headers.get("X-RateLimit-Limit") == "1"
    assert second.headers.get("Retry-After") is not None


def test_rate_limit_monitor_observes_without_blocking(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_run_scenario(monkeypatch)
    monkeypatch.setenv("LEAKSENTINEL_AUTH_ENFORCEMENT", "off")
    monkeypatch.setenv("LEAKSENTINEL_RATE_LIMIT_ENFORCEMENT", "monitor")
    monkeypatch.setenv("LEAKSENTINEL_RATE_LIMIT_PER_MINUTE", "1")
    api_main._reset_rate_limit_state()

    client = TestClient(api_main.app)
    _ = client.post("/run", json={"scenario_id": "S02", "mode": "local"})
    second = client.post("/run", json={"scenario_id": "S02", "mode": "local"})
    assert second.status_code == 200
    assert second.headers.get("X-RateLimit-Observed-Breach") == "true"


def test_health_ready_is_503_when_voice_backend_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEAKSENTINEL_VOICE_REQUIRED_FOR_READINESS", "true")
    monkeypatch.setattr(
        api_main,
        "_probe_voice_backend_health",
        lambda timeout=2: {"reachable": False, "status": "down", "error": "offline", "url": "http://x/health"},
    )
    client = TestClient(api_main.app)
    resp = client.get("/health/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["ok"] is False
    assert body["status"] == "degraded"
