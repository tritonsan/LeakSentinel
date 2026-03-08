# LeakSentinel Hosted API (FastAPI)

## Run locally
- `pip install -r requirements.txt`
- `uvicorn services.api.main:app --reload --port 8000`
  - Voice demo page: `http://localhost:8000/demo/voice_demo.html?api=http://localhost:8000`

## Voice service (Nova 2 Sonic)
- `cd services/voice`
- `npm install`
- `AWS_REGION=us-east-1 NOVA_SONIC_MODEL_ID=amazon.nova-sonic-v1:0 npm run dev`

## Endpoints
- `GET /health`
  - Returns API status + voice backend probe (`voice_backend.reachable`, `voice_backend.status`).
  - Voice backend probe is used by the hardening runbook to catch bridge outages early.
- `GET /health/live`
  - Liveness probe for process uptime.
- `GET /health/ready`
  - Readiness probe.
  - Returns `503` if voice backend is down **and** `LEAKSENTINEL_VOICE_REQUIRED_FOR_READINESS=true`.
- `POST /run` body: `{ "scenario_id": "S02", "mode": "local", "judge_mode": false }`
- `POST /ops/coverage-plan` body:
  - `{ "horizon_hours": 24, "max_crews": 3, "zones": ["zone-1"], "evidence_dir": "data/evidence_bundles" }`
- `POST /standards/check` body:
  - `{ "building_profile": {...}, "controls_catalog": {...} }`
- `POST /impact/compare` body:
  - `{ "mode": "local", "persona": "utility", "scenario_ids": ["S02"], "bundle_paths": [], "bundles": [] }`
  - Returns `impact_proof_v1` with `impact_bands` and `persona_applied`.
- `POST /ops/closed-loop-simulate` body:
  - `{ "scenario_id": "S02", "mode": "local", "field_verdict": "rejected_false_positive", "max_crews": 3, "horizon_hours": 24 }`
  - Returns `closed_loop_summary_v1` with `timeline` and `decision_change_summary`.
- `POST /ops/incidents/open` body:
  - `{ "scenario_id": "S02", "mode": "local" }` or `{ "bundle_path": "data/evidence_bundles/....json" }`
- `GET /ops/incidents?status=&zone=&limit=100`
- `POST /ops/incidents/{incident_id}/dispatch` body:
  - `{ "team": "crew-1", "eta_minutes": 30 }`
- `POST /ops/incidents/{incident_id}/field-update` body:
  - `{ "status": "on_site", "note": "Crew arrived", "evidence_added": true }`
- `POST /ops/incidents/{incident_id}/close` body:
  - `{ "closure_type": "true_positive", "note": "Leak repaired", "repair_cost_usd": 420 }`
- `GET /impact/kpis?from=2026-02-01T00:00:00&to=2026-02-15T00:00:00&zone=zone-1`
- `GET /ops/risk-map?window_days=30`
- `GET /integrations/connectors`
- `POST /integrations/events` body:
  - `{ "source": "scada", "event_type": "pressure_drop", "zone": "zone-1", "timestamp": "...", "payload": {...} }`
- `POST /integrations/export` body:
  - `{ "format": "csv", "entity": "incidents", "from_ts": "...", "to_ts": "...", "zone": "zone-1" }`
- `POST /feedback` body:
  - `{ "bundle_path": "data/evidence_bundles/...", "outcome": "false_positive_rejected_by_operator", "operator_note": "...", "reviewer": "...", "root_cause_guess": "...", "evidence_gap": "..." }`
  - or `{ "scenario_id": "S02", ... }` (uses latest bundle for that scenario)
- `WS /ws/voice` (voice bridge to `LEAKSENTINEL_VOICE_BACKEND_URL`, default `http://127.0.0.1:8001`)
  - Bridge calls use retry/backoff for transient backend failures before returning a final error.
  - Client events:
    - `{"type":"start","sampleRateHertz":16000,"userText":"...","systemText":"..."}`
    - `{"type":"audio_chunk","audioPcm16Base64":"..."}`
    - `{"type":"end"}`
  - Server events:
    - `ready`, `started`, `processing`, `transcript_partial`, `transcript_final`, `audio_chunk`, `error`, `done`

## Security Controls
Environment flags:
- `LEAKSENTINEL_ALLOWED_ORIGINS`
- `LEAKSENTINEL_AUTH_ENFORCEMENT=off|monitor|on`
- `LEAKSENTINEL_RATE_LIMIT_ENFORCEMENT=off|monitor|on`
- `LEAKSENTINEL_RATE_LIMIT_PER_MINUTE`
- `LEAKSENTINEL_API_KEYS` (or `LEAKSENTINEL_API_KEY`)
- `LEAKSENTINEL_VOICE_REQUIRED_FOR_READINESS=true|false`

Auth headers:
- `X-API-Key: <key>`
- or `Authorization: Bearer <key>`

Control/trace headers returned:
- `X-Auth-Mode`
- `X-RateLimit-Mode`
- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `Retry-After` (when throttled)
- `X-Request-ID`
