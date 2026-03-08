from __future__ import annotations

import asyncio
import base64
import json
import logging
import math
import os
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest

from fastapi import FastAPI, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect, status
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from leaksentinel.config import AppSettings
from leaksentinel.feedback.store import VALID_OUTCOMES, create_feedback_record, resolve_latest_bundle_for_scenario
from leaksentinel.orchestrator import run_scenario
from leaksentinel.ops.coverage_optimizer import build_coverage_plan
from leaksentinel.ops.closed_loop import simulate_closed_loop
from leaksentinel.ops.incidents_store import (
    close_incident,
    dispatch_incident,
    field_update_incident,
    list_incidents,
    open_incident,
)
from leaksentinel.ops.risk_map import build_zone_risk_map
from leaksentinel.compliance.standards_mode import evaluate_standards_readiness, load_json_or_default
from leaksentinel.impact.proof import build_impact_compare
from leaksentinel.impact.kpis import compute_impact_kpis
from leaksentinel.integrations.bridge import export_data, ingest_event, list_connectors


logger = logging.getLogger("leaksentinel.api")
if not logger.handlers:
    logging.basicConfig(level=os.getenv("LEAKSENTINEL_LOG_LEVEL", "INFO"))


app = FastAPI(title="LeakSentinel API", version="0.1.0")


def _parse_csv(raw: str) -> list[str]:
    return [part.strip() for part in str(raw or "").split(",") if part.strip()]


def _normalized_mode(raw: str, default: str = "off") -> str:
    mode = str(raw or "").strip().lower()
    if mode in {"off", "monitor", "on"}:
        return mode
    return default


def _safe_int(raw: str | int | None, default: int, *, min_value: int = 1, max_value: int = 50_000) -> int:
    try:
        parsed = int(raw)  # type: ignore[arg-type]
    except Exception:
        parsed = default
    return max(min_value, min(max_value, parsed))


def _safe_bool(raw: str | None, default: bool = False) -> bool:
    value = str(raw or "").strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _allowed_origins() -> list[str]:
    parsed = _parse_csv(os.getenv("LEAKSENTINEL_ALLOWED_ORIGINS", "*"))
    return parsed or ["*"]


def _security_snapshot() -> dict[str, object]:
    keys = set(_parse_csv(os.getenv("LEAKSENTINEL_API_KEYS", "")))
    one_key = str(os.getenv("LEAKSENTINEL_API_KEY", "") or "").strip()
    if one_key:
        keys.add(one_key)
    return {
        "auth_mode": _normalized_mode(os.getenv("LEAKSENTINEL_AUTH_ENFORCEMENT", "monitor"), default="monitor"),
        "rate_limit_mode": _normalized_mode(os.getenv("LEAKSENTINEL_RATE_LIMIT_ENFORCEMENT", "monitor"), default="monitor"),
        "rate_limit_per_minute": _safe_int(
            os.getenv("LEAKSENTINEL_RATE_LIMIT_PER_MINUTE", "120"),
            120,
            min_value=1,
            max_value=10_000,
        ),
        "api_keys": keys,
    }


def _is_path_exempt(path: str) -> bool:
    if path in {"/health", "/health/live", "/health/ready", "/openapi.json", "/docs", "/redoc", "/favicon.ico"}:
        return True
    if path.startswith("/docs") or path.startswith("/redoc") or path.startswith("/demo"):
        return True
    return False


def _extract_api_key(x_api_key: str, authorization: str, *, fallback: str = "") -> str:
    key = str(x_api_key or "").strip()
    if key:
        return key
    auth = str(authorization or "").strip()
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        if token:
            return token
    return str(fallback or "").strip()


def _evaluate_auth(*, path: str, provided_key: str, auth_mode: str, api_keys: set[str]) -> tuple[bool, str]:
    if _is_path_exempt(path):
        return False, "exempt"
    if auth_mode == "off":
        return False, "off"
    if not api_keys:
        if auth_mode == "on":
            return True, "auth_enabled_without_keys"
        return False, "monitor_no_keys_configured"
    if provided_key in api_keys:
        return False, "ok"
    if auth_mode == "on":
        return True, "missing_or_invalid_api_key"
    return False, "monitor_missing_or_invalid_api_key"


_RATE_LIMIT_STATE: dict[str, deque[float]] = {}
_RATE_LIMIT_LOCK = threading.Lock()


def _rate_limit_identity(*, path: str, x_forwarded_for: str, client_host: str) -> str:
    left = str(x_forwarded_for or "").split(",")[0].strip()
    host = left or str(client_host or "unknown")
    return f"{host}:{path}"


def _check_rate_limit(*, identity: str, limit: int, now_ts: float | None = None, window_seconds: int = 60) -> tuple[bool, int, int]:
    now = float(now_ts if now_ts is not None else time.time())
    with _RATE_LIMIT_LOCK:
        bucket = _RATE_LIMIT_STATE.setdefault(identity, deque())
        cutoff = now - float(window_seconds)
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= int(limit):
            retry_after = max(1, int(math.ceil(float(window_seconds) - (now - bucket[0]))))
            return True, 0, retry_after
        bucket.append(now)
        remaining = max(0, int(limit) - len(bucket))
        return False, remaining, 0


def _reset_rate_limit_state() -> None:
    with _RATE_LIMIT_LOCK:
        _RATE_LIMIT_STATE.clear()


def _websocket_access_policy(ws: WebSocket) -> tuple[bool, dict[str, object]]:
    path = str(ws.url.path if ws.url else "/ws/voice")
    security = _security_snapshot()
    auth_mode = str(security["auth_mode"])
    rate_limit_mode = str(security["rate_limit_mode"])
    rate_limit_per_minute = int(security["rate_limit_per_minute"])
    api_keys = set(security["api_keys"])  # type: ignore[arg-type]

    provided_key = _extract_api_key(
        ws.headers.get("x-api-key", ""),
        ws.headers.get("authorization", ""),
        fallback=str(ws.query_params.get("api_key", "") or ""),
    )
    denied, auth_reason = _evaluate_auth(path=path, provided_key=provided_key, auth_mode=auth_mode, api_keys=api_keys)
    if denied:
        return False, {"close_code": status.WS_1008_POLICY_VIOLATION, "reason": auth_reason}

    warnings: dict[str, object] = {}
    if auth_reason.startswith("monitor_"):
        warnings["auth_warning"] = auth_reason

    if rate_limit_mode != "off" and not _is_path_exempt(path):
        identity = _rate_limit_identity(
            path=path,
            x_forwarded_for=ws.headers.get("x-forwarded-for", ""),
            client_host=(ws.client.host if ws.client else "unknown"),
        )
        over_limit, _, retry_after = _check_rate_limit(
            identity=identity,
            limit=rate_limit_per_minute,
        )
        if over_limit and rate_limit_mode == "on":
            return False, {"close_code": status.WS_1013_TRY_AGAIN_LATER, "reason": "rate_limit_exceeded"}
        if over_limit and rate_limit_mode == "monitor":
            warnings["rate_limit_warning"] = "monitor_rate_limit_exceeded"
            warnings["retry_after"] = int(max(1, retry_after))

    return True, warnings


allowed_origins = _allowed_origins()
# Keep credentials disabled when wildcard is used (required by browser CORS behavior).
allow_credentials = "*" not in allowed_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the voice demo static page under /demo
app.mount("/demo", StaticFiles(directory="services/web", html=True), name="demo")


@app.middleware("http")
async def security_controls(request: Request, call_next):  # type: ignore[override]
    started = time.perf_counter()
    request_id = request.headers.get("x-request-id", "").strip() or str(uuid.uuid4())
    path = request.url.path
    method = request.method.upper()
    security = _security_snapshot()
    auth_mode = str(security["auth_mode"])
    rate_limit_mode = str(security["rate_limit_mode"])
    rate_limit_per_minute = int(security["rate_limit_per_minute"])
    api_keys = set(security["api_keys"])  # type: ignore[arg-type]

    auth_reason = "off"
    rate_over_limit = False
    rate_remaining = rate_limit_per_minute
    rate_retry_after = 0

    provided_key = _extract_api_key(
        request.headers.get("x-api-key", ""),
        request.headers.get("authorization", ""),
    )
    auth_denied = False
    if method != "OPTIONS":
        auth_denied, auth_reason = _evaluate_auth(path=path, provided_key=provided_key, auth_mode=auth_mode, api_keys=api_keys)

    if auth_denied:
        response: Response = JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Missing or invalid API key.", "code": auth_reason},
        )
    else:
        if method != "OPTIONS" and rate_limit_mode != "off" and not _is_path_exempt(path):
            identity = _rate_limit_identity(
                path=path,
                x_forwarded_for=request.headers.get("x-forwarded-for", ""),
                client_host=(request.client.host if request.client else "unknown"),
            )
            rate_over_limit, rate_remaining, rate_retry_after = _check_rate_limit(
                identity=identity,
                limit=rate_limit_per_minute,
            )
            if rate_over_limit and rate_limit_mode == "on":
                response = JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": "Rate limit exceeded.", "code": "rate_limit_exceeded"},
                )
            else:
                response = await call_next(request)
        else:
            response = await call_next(request)

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Auth-Mode"] = auth_mode
    response.headers["X-RateLimit-Mode"] = rate_limit_mode
    response.headers["X-Auth-Keys-Configured"] = "true" if api_keys else "false"
    if auth_reason.startswith("monitor_"):
        response.headers["X-Auth-Monitor-Warning"] = auth_reason
    if rate_limit_mode != "off" and not _is_path_exempt(path):
        response.headers["X-RateLimit-Limit"] = str(rate_limit_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(max(0, int(rate_remaining)))
        if rate_over_limit:
            response.headers["Retry-After"] = str(max(1, int(rate_retry_after)))
            if rate_limit_mode == "monitor":
                response.headers["X-RateLimit-Observed-Breach"] = "true"

    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
    logger.info(
        json.dumps(
            {
                "event": "http_request",
                "request_id": request_id,
                "method": method,
                "path": path,
                "status_code": int(response.status_code),
                "duration_ms": elapsed_ms,
                "auth_mode": auth_mode,
                "auth_result": auth_reason,
                "rate_limit_mode": rate_limit_mode,
                "rate_limit_over_limit": bool(rate_over_limit),
            }
        )
    )
    return response


def _voice_backend_base() -> str:
    return os.getenv("LEAKSENTINEL_VOICE_BACKEND_URL", "http://127.0.0.1:8001").rstrip("/")


def _post_json(url: str, payload: dict, *, timeout: int = 180, retries: int = 2, backoff_seconds: float = 0.6) -> dict:
    body = json.dumps(payload).encode("utf-8")
    last_err: Exception | None = None
    attempts = max(1, int(retries) + 1)
    for attempt in range(attempts):
        req = urlrequest.Request(url=url, data=body, method="POST")
        req.add_header("content-type", "application/json")
        try:
            with urlrequest.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw)
        except urlerror.HTTPError as e:
            status = int(getattr(e, "code", 0) or 0)
            raw = e.read().decode("utf-8", errors="replace")
            # Retry server-side failures; surface client-side failures immediately.
            if status < 500 or attempt >= attempts - 1:
                raise RuntimeError(f"Voice backend HTTP {status}: {raw or 'empty response'}") from e
            last_err = RuntimeError(f"Voice backend transient HTTP {status}")
        except Exception as e:
            last_err = e
            if attempt >= attempts - 1:
                break
        sleep_s = float(backoff_seconds) * (attempt + 1)
        time.sleep(max(0.05, sleep_s))
    raise RuntimeError(f"Voice backend request failed after {attempts} attempts: {last_err}") from last_err


def _probe_voice_backend_health(timeout: int = 2) -> dict:
    url = f"{_voice_backend_base()}/health"
    try:
        req = urlrequest.Request(url=url, method="GET")
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            payload = {"raw": raw}
        return {"reachable": True, "status": "up", "detail": payload, "url": url}
    except Exception as e:
        return {"reachable": False, "status": "down", "error": str(e), "url": url}


def _chunk_b64_from_bytes(data: bytes, *, chunk_size: int = 12_000) -> list[str]:
    out: list[str] = []
    for i in range(0, len(data), chunk_size):
        out.append(base64.b64encode(data[i : i + chunk_size]).decode("ascii"))
    return out


class RunRequest(BaseModel):
    scenario_id: str
    mode: str = "local"  # local|bedrock
    analysis_version: str = "v2"  # v1|v2
    include_counterfactuals: bool = True
    include_impact: bool = True
    include_flow_agent: bool = True
    include_pressure_plan: bool = True
    include_scorecard: bool = True
    include_standards: bool = True
    judge_mode: bool = False


class CoveragePlanRequest(BaseModel):
    horizon_hours: int = 24
    max_crews: int = 3
    zones: list[str] = []
    evidence_dir: str = ""


class StandardsCheckRequest(BaseModel):
    building_profile: dict = {}
    controls_catalog: dict = {}


class ImpactCompareRequest(BaseModel):
    mode: str = "local"
    persona: str = "utility"
    scenario_ids: list[str] = []
    bundle_paths: list[str] = []
    bundles: list[dict] = []


class ClosedLoopSimRequest(BaseModel):
    scenario_id: str
    mode: str = "local"
    field_verdict: str = "rejected_false_positive"
    max_crews: int = 3
    horizon_hours: int = 24


class FeedbackRequest(BaseModel):
    bundle_path: str = ""
    scenario_id: str = ""
    outcome: str = VALID_OUTCOMES[0]
    operator_note: str = ""
    reviewer: str = ""
    root_cause_guess: str = ""
    evidence_gap: str = ""


class IncidentOpenRequest(BaseModel):
    scenario_id: str = ""
    bundle_path: str = ""
    mode: str = "local"


class IncidentDispatchRequest(BaseModel):
    team: str
    eta_minutes: int = 30


class IncidentFieldUpdateRequest(BaseModel):
    status: str
    note: str = ""
    evidence_added: bool = False


class IncidentCloseRequest(BaseModel):
    closure_type: str
    note: str = ""
    repair_cost_usd: float = 0.0


class IntegrationEventRequest(BaseModel):
    source: str
    event_type: str
    zone: str = ""
    timestamp: str = ""
    payload: dict = {}


class IntegrationExportRequest(BaseModel):
    format: str = "json"
    entity: str = "incidents"
    from_ts: str = ""
    to_ts: str = ""
    zone: str = ""


@app.get("/health/live")
def health_live() -> dict:
    return {"ok": True, "status": "live"}


@app.get("/health/ready")
def health_ready(response: Response) -> dict:
    vb = _probe_voice_backend_health(timeout=2)
    security = _security_snapshot()
    voice_required = _safe_bool(os.getenv("LEAKSENTINEL_VOICE_REQUIRED_FOR_READINESS", "false"), default=False)
    ready = bool(vb.get("reachable")) if voice_required else True
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "ok": ready,
        "status": "ready" if ready else "degraded",
        "voice_backend_url": _voice_backend_base(),
        "voice_backend": vb,
        "security": {
            "auth_mode": security["auth_mode"],
            "rate_limit_mode": security["rate_limit_mode"],
            "api_keys_configured": bool(security["api_keys"]),
        },
        "voice_required_for_readiness": voice_required,
    }


@app.get("/health")
def health() -> dict:
    vb = _probe_voice_backend_health(timeout=2)
    security = _security_snapshot()
    voice_required = _safe_bool(os.getenv("LEAKSENTINEL_VOICE_REQUIRED_FOR_READINESS", "false"), default=False)
    return {
        "ok": True,
        "voice_backend_url": _voice_backend_base(),
        "voice_backend": vb,
        "security": {
            "auth_mode": security["auth_mode"],
            "rate_limit_mode": security["rate_limit_mode"],
            "api_keys_configured": bool(security["api_keys"]),
        },
        "voice_required_for_readiness": voice_required,
    }


@app.post("/run")
def run(req: RunRequest) -> dict:
    return run_scenario(
        scenario_id=req.scenario_id,
        mode=req.mode,
        write_bundle=True,
        analysis_version=req.analysis_version,
        include_counterfactuals=bool(req.include_counterfactuals),
        include_impact=bool(req.include_impact),
        include_flow_agent=bool(req.include_flow_agent),
        include_pressure_plan=bool(req.include_pressure_plan),
        include_scorecard=bool(req.include_scorecard),
        include_standards=bool(req.include_standards),
        judge_mode=bool(req.judge_mode),
    )


@app.post("/ops/coverage-plan")
def coverage_plan(req: CoveragePlanRequest) -> dict:
    settings = AppSettings()
    evidence_dir = Path(str(req.evidence_dir).strip()) if str(req.evidence_dir).strip() else settings.paths.evidence_dir
    return build_coverage_plan(
        evidence_dir=evidence_dir,
        horizon_hours=int(max(1, req.horizon_hours)),
        max_crews=int(max(1, req.max_crews)),
        zones=[str(z) for z in (req.zones or []) if str(z).strip()],
    )


@app.post("/ops/incidents/open")
def incidents_open(req: IncidentOpenRequest) -> dict:
    settings = AppSettings(mode=req.mode)
    bp = Path(str(req.bundle_path).strip()) if str(req.bundle_path).strip() else None
    bundle: dict | None = None
    if bp:
        if not bp.exists():
            raise HTTPException(status_code=400, detail=f"Bundle path not found: {bp}")
        try:
            obj = json.loads(bp.read_text(encoding="utf-8"))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid bundle JSON: {e}") from e
        if not isinstance(obj, dict):
            raise HTTPException(status_code=400, detail="Bundle JSON must be an object.")
        bundle = obj
    else:
        sid = str(req.scenario_id or "").strip()
        if not sid:
            raise HTTPException(status_code=400, detail="Provide scenario_id or bundle_path.")
        try:
            latest = resolve_latest_bundle_for_scenario(evidence_dir=settings.paths.evidence_dir, scenario_id=sid)
            bp = latest
            obj = json.loads(latest.read_text(encoding="utf-8"))
            if isinstance(obj, dict):
                bundle = obj
        except FileNotFoundError:
            out = run_scenario(
                scenario_id=sid,
                mode=req.mode,
                write_bundle=True,
                analysis_version="v2",
                ablation="full",
            )
            if isinstance(out, dict):
                bundle = out
                bpath = str(out.get("_bundle_path", "") or "").strip()
                if bpath:
                    bp = Path(bpath)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to resolve scenario bundle: {e}") from e

    if not isinstance(bundle, dict):
        raise HTTPException(status_code=400, detail="Failed to load incident bundle.")
    try:
        inc = open_incident(
            incidents_path=settings.paths.incidents_path,
            bundle=bundle,
            bundle_path=str(bp) if bp else "",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "incident": inc}


@app.get("/ops/incidents")
def incidents_list(status: str = "", zone: str = "", limit: int = 100) -> dict:
    settings = AppSettings()
    rows = list_incidents(
        incidents_path=settings.paths.incidents_path,
        status=status,
        zone=zone,
        limit=max(1, int(limit)),
    )
    return {"ok": True, "count": len(rows), "items": rows}


@app.post("/ops/incidents/{incident_id}/dispatch")
def incidents_dispatch(incident_id: str, req: IncidentDispatchRequest) -> dict:
    settings = AppSettings()
    try:
        out = dispatch_incident(
            incidents_path=settings.paths.incidents_path,
            incident_id=incident_id,
            team=req.team,
            eta_minutes=int(max(1, req.eta_minutes)),
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "incident": out}


@app.post("/ops/incidents/{incident_id}/field-update")
def incidents_field_update(incident_id: str, req: IncidentFieldUpdateRequest) -> dict:
    settings = AppSettings()
    try:
        out = field_update_incident(
            incidents_path=settings.paths.incidents_path,
            incident_id=incident_id,
            status=req.status,
            note=req.note,
            evidence_added=bool(req.evidence_added),
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "incident": out}


@app.post("/ops/incidents/{incident_id}/close")
def incidents_close(incident_id: str, req: IncidentCloseRequest) -> dict:
    settings = AppSettings()
    try:
        out = close_incident(
            incidents_path=settings.paths.incidents_path,
            incident_id=incident_id,
            closure_type=req.closure_type,
            note=req.note,
            repair_cost_usd=req.repair_cost_usd,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "incident": out}


@app.post("/standards/check")
def standards_check(req: StandardsCheckRequest) -> dict:
    settings = AppSettings()
    profile = req.building_profile if isinstance(req.building_profile, dict) and req.building_profile else load_json_or_default(
        settings.standards.default_profile_path,
        default_obj={},
    )
    catalog = req.controls_catalog if isinstance(req.controls_catalog, dict) and req.controls_catalog else load_json_or_default(
        settings.standards.controls_catalog_path,
        default_obj={"required_controls": []},
    )
    out = evaluate_standards_readiness(building_profile=profile, controls_catalog=catalog)
    return {"ok": True, "standards_readiness": out}


@app.post("/impact/compare")
def impact_compare(req: ImpactCompareRequest) -> dict:
    settings = AppSettings(mode=req.mode)
    assumptions_register = load_json_or_default(
        settings.impact.assumptions_path,
        default_obj={},
    )
    bundles: list[dict] = [b for b in (req.bundles or []) if isinstance(b, dict)]

    for p in (req.bundle_paths or []):
        path = Path(str(p).strip())
        if not path.exists():
            raise HTTPException(status_code=400, detail=f"Bundle path not found: {path}")
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON at bundle path: {path} error={e}") from e
        if isinstance(obj, dict):
            bundles.append(obj)

    for sid_raw in (req.scenario_ids or []):
        sid = str(sid_raw or "").strip()
        if not sid:
            continue
        try:
            out = run_scenario(
                scenario_id=sid,
                mode=req.mode,
                write_bundle=False,
                analysis_version="v2",
                ablation="full",
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Scenario run failed for {sid}: {e}") from e
        if isinstance(out, dict):
            bundles.append(out)

    if not bundles:
        raise HTTPException(status_code=400, detail="Provide at least one scenario_id, bundle_path, or inline bundle.")

    out = build_impact_compare(
        bundles=bundles,
        assumptions_register=assumptions_register,
        persona=req.persona,
        personas_path=settings.impact.personas_path,
    )
    return {"ok": True, "impact_proof_v1": out}


@app.get("/impact/kpis")
def impact_kpis(
    from_ts: str = Query(default="", alias="from"),
    to_ts: str = Query(default="", alias="to"),
    zone: str = "",
) -> dict:
    settings = AppSettings()
    out = compute_impact_kpis(
        incidents_path=settings.paths.incidents_path,
        from_ts=from_ts,
        to_ts=to_ts,
        zone=zone,
    )
    return {"ok": True, "impact_kpis": out}


@app.get("/ops/risk-map")
def risk_map(window_days: int = 30) -> dict:
    settings = AppSettings()
    out = build_zone_risk_map(
        evidence_dir=settings.paths.evidence_dir,
        incidents_path=settings.paths.incidents_path,
        window_days=max(1, int(window_days)),
    )
    return {"ok": True, "risk_map": out}


@app.get("/integrations/connectors")
def integrations_connectors() -> dict:
    settings = AppSettings()
    rows = list_connectors(connectors_path=settings.paths.connectors_path)
    return {"ok": True, "connectors": rows, "count": len(rows)}


@app.post("/integrations/events")
def integrations_events(req: IntegrationEventRequest) -> dict:
    settings = AppSettings()
    try:
        out = ingest_event(
            events_path=settings.paths.integration_events_path,
            source=req.source,
            event_type=req.event_type,
            zone=req.zone,
            timestamp=req.timestamp,
            payload=req.payload if isinstance(req.payload, dict) else {},
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "event": out}


@app.post("/integrations/export")
def integrations_export(req: IntegrationExportRequest) -> dict:
    settings = AppSettings()
    try:
        out = export_data(
            export_format=req.format,
            entity=req.entity,
            from_ts=req.from_ts,
            to_ts=req.to_ts,
            zone=req.zone,
            incidents_path=settings.paths.incidents_path,
            exports_dir=settings.paths.exports_dir,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "export": out}


@app.post("/ops/closed-loop-simulate")
def closed_loop_simulate(req: ClosedLoopSimRequest) -> dict:
    sid = str(req.scenario_id or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="scenario_id is required.")
    out = simulate_closed_loop(
        scenario_id=sid,
        mode=req.mode,
        field_verdict=req.field_verdict,
        max_crews=int(max(1, req.max_crews)),
        horizon_hours=int(max(1, req.horizon_hours)),
    )
    return {"ok": True, "closed_loop_summary_v1": out}


@app.post("/feedback")
def feedback(req: FeedbackRequest) -> dict:
    if req.outcome not in VALID_OUTCOMES:
        raise HTTPException(status_code=400, detail=f"Invalid outcome. Allowed: {', '.join(VALID_OUTCOMES)}")
    if not str(req.bundle_path).strip() and not str(req.scenario_id).strip():
        raise HTTPException(status_code=400, detail="Provide bundle_path or scenario_id.")

    settings = AppSettings()
    try:
        rec = create_feedback_record(
            bundle_path=req.bundle_path.strip() or None,
            scenario_id=req.scenario_id.strip() or None,
            outcome=req.outcome,
            operator_note=req.operator_note,
            reviewer=req.reviewer,
            root_cause_guess=req.root_cause_guess,
            evidence_gap=req.evidence_gap,
            evidence_dir=settings.paths.evidence_dir,
            feedback_dir=settings.paths.feedback_dir,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return {
        "ok": True,
        "feedback_id": rec.get("feedback_id"),
        "stored_path": rec.get("_stored_path"),
        "bundle_path": rec.get("bundle_path"),
        "scenario_id": rec.get("scenario_id"),
        "outcome": rec.get("outcome"),
        "root_cause_guess": rec.get("root_cause_guess"),
        "evidence_gap": rec.get("evidence_gap"),
    }


@app.websocket("/ws/voice")
async def voice_ws(ws: WebSocket) -> None:
    """
    Realtime voice bridge.

    Client -> server event protocol:
    - {"type":"start","sampleRateHertz":16000,"userText":"...","systemText":"..."}
    - {"type":"audio_chunk","audioPcm16Base64":"..."}
    - {"type":"end"}

    Server -> client events:
    - ready|started|processing|transcript_partial|transcript_final|audio_chunk|error|done
    """
    allowed, ws_access = _websocket_access_policy(ws)
    if not allowed:
        await ws.close(
            code=int(ws_access.get("close_code", status.WS_1008_POLICY_VIOLATION)),
            reason=str(ws_access.get("reason", "policy_denied")),
        )
        return

    await ws.accept()
    ready_payload = {"type": "ready", "voice_backend_url": _voice_backend_base()}
    if ws_access.get("auth_warning"):
        ready_payload["auth_warning"] = str(ws_access["auth_warning"])
    if ws_access.get("rate_limit_warning"):
        ready_payload["rate_limit_warning"] = str(ws_access["rate_limit_warning"])
        ready_payload["retry_after"] = int(ws_access.get("retry_after", 1))
    await ws.send_json(ready_payload)

    started = False
    sample_rate_hz = 16000
    user_text = ""
    system_text = ""
    audio_chunks: list[bytes] = []

    def _reset() -> None:
        nonlocal started, sample_rate_hz, user_text, system_text, audio_chunks
        started = False
        sample_rate_hz = 16000
        user_text = ""
        system_text = ""
        audio_chunks = []

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                await ws.send_json({"type": "error", "code": "invalid_json", "message": "Expected JSON text frame."})
                continue

            if not isinstance(msg, dict):
                await ws.send_json({"type": "error", "code": "invalid_event", "message": "Event must be a JSON object."})
                continue

            et = str(msg.get("type", "")).strip().lower()
            if et == "ping":
                await ws.send_json({"type": "pong"})
                continue

            if et in {"cancel", "reset"}:
                _reset()
                await ws.send_json({"type": "reset"})
                continue

            if et == "start":
                _reset()
                started = True
                try:
                    sample_rate_hz = max(8_000, min(48_000, int(msg.get("sampleRateHertz", 16000))))
                except Exception:
                    sample_rate_hz = 16000
                user_text = str(msg.get("userText", "") or "")
                system_text = str(msg.get("systemText", "") or "")
                await ws.send_json({"type": "started", "sampleRateHertz": sample_rate_hz})
                continue

            if et == "audio_chunk":
                if not started:
                    await ws.send_json(
                        {"type": "error", "code": "session_not_started", "message": "Send start before audio_chunk."}
                    )
                    continue
                b64 = str(msg.get("audioPcm16Base64") or msg.get("content") or "").strip()
                if not b64:
                    await ws.send_json(
                        {"type": "error", "code": "missing_audio_chunk", "message": "audioPcm16Base64 is required."}
                    )
                    continue
                try:
                    audio_chunks.append(base64.b64decode(b64))
                except Exception:
                    await ws.send_json(
                        {"type": "error", "code": "invalid_base64", "message": "audioPcm16Base64 must be valid base64."}
                    )
                continue

            if et == "end":
                if not started:
                    await ws.send_json(
                        {"type": "error", "code": "session_not_started", "message": "Send start before end."}
                    )
                    continue
                if not audio_chunks:
                    await ws.send_json(
                        {"type": "error", "code": "no_audio", "message": "No audio_chunk received before end."}
                    )
                    _reset()
                    continue

                await ws.send_json({"type": "processing", "audioBytes": int(sum(len(x) for x in audio_chunks))})

                audio_bytes = b"".join(audio_chunks)
                req_payload = {
                    "audioPcm16Base64": base64.b64encode(audio_bytes).decode("ascii"),
                    "sampleRateHertz": sample_rate_hz,
                    "userText": user_text,
                    "systemText": system_text,
                }
                try:
                    out = await asyncio.to_thread(
                        _post_json,
                        f"{_voice_backend_base()}/v1/voice/sonic",
                        req_payload,
                        timeout=180,
                    )
                except urlerror.HTTPError as e:
                    err_raw = e.read().decode("utf-8", errors="replace")
                    await ws.send_json({"type": "error", "code": "voice_backend_http_error", "message": err_raw})
                    await ws.send_json({"type": "done", "ok": False})
                    _reset()
                    continue
                except Exception as e:
                    await ws.send_json({"type": "error", "code": "voice_backend_error", "message": str(e)})
                    await ws.send_json({"type": "done", "ok": False})
                    _reset()
                    continue

                if not bool(out.get("ok")):
                    await ws.send_json(
                        {"type": "error", "code": "voice_backend_not_ok", "message": str(out.get("error", "unknown"))}
                    )
                    await ws.send_json({"type": "done", "ok": False})
                    _reset()
                    continue

                transcript = str(out.get("transcript", "") or "").strip()
                if transcript:
                    partial = transcript[: min(160, len(transcript))]
                    await ws.send_json({"type": "transcript_partial", "text": partial})
                    await ws.send_json({"type": "transcript_final", "text": transcript})

                wav_b64 = str(out.get("response_audio_wav_base64", "") or "")
                if wav_b64:
                    try:
                        wav_bytes = base64.b64decode(wav_b64)
                    except Exception:
                        wav_bytes = b""
                    if wav_bytes:
                        chunks = _chunk_b64_from_bytes(wav_bytes, chunk_size=12_000)
                        for i, ch in enumerate(chunks):
                            await ws.send_json(
                                {
                                    "type": "audio_chunk",
                                    "format": "audio/wav;base64",
                                    "content": ch,
                                    "seq": i,
                                    "last": bool(i == len(chunks) - 1),
                                }
                            )

                await ws.send_json(
                    {
                        "type": "done",
                        "ok": True,
                        "model_id_used": out.get("model_id_used"),
                        "transcript": transcript,
                    }
                )
                _reset()
                continue

            await ws.send_json(
                {
                    "type": "error",
                    "code": "unknown_event",
                    "message": f"Unknown event type: {msg.get('type')!r}",
                }
            )
    except WebSocketDisconnect:
        return
    except Exception as e:
        try:
            await ws.send_json({"type": "error", "code": "server_error", "message": str(e)})
        except Exception:
            pass
        return
