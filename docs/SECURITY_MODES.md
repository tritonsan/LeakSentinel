# Security Modes (Demo-Safe to Production)

LeakSentinel API supports staged enforcement so juries can test freely during demo, while production remains locked down.

## Environment Flags
- `LEAKSENTINEL_AUTH_ENFORCEMENT=off|monitor|on`
- `LEAKSENTINEL_RATE_LIMIT_ENFORCEMENT=off|monitor|on`
- `LEAKSENTINEL_RATE_LIMIT_PER_MINUTE=<int>`
- `LEAKSENTINEL_API_KEYS=<comma-separated keys>` (or `LEAKSENTINEL_API_KEY=<single key>`)
- `LEAKSENTINEL_ALLOWED_ORIGINS=<comma-separated origins or *>`
- `LEAKSENTINEL_VOICE_REQUIRED_FOR_READINESS=true|false`

## Mode Behavior
1. `off`
   - No API key checks.
   - No rate limiting checks.
2. `monitor` (recommended for jury demos)
   - Violations are observed and exposed in response headers.
   - Requests are not blocked.
3. `on` (required for production)
   - Missing/invalid API key returns `401`.
   - Rate limit breach returns `429`.

## Client Headers
- Request:
  - `X-API-Key: <key>` (or `Authorization: Bearer <key>`)
- Response:
  - `X-Auth-Mode`
  - `X-RateLimit-Mode`
  - `X-RateLimit-Limit`
  - `X-RateLimit-Remaining`
  - `Retry-After` (when limited)
  - `X-Request-ID`

## Recommended Rollout
1. Demo/Staging:
   - `AUTH=monitor`
   - `RATE_LIMIT=monitor`
2. Production:
   - `AUTH=on`
   - `RATE_LIMIT=on`
3. Keep `/health`, `/health/live`, `/health/ready` open for probes.
4. If voice is optional for uptime, keep `LEAKSENTINEL_VOICE_REQUIRED_FOR_READINESS=false`.

## WebSocket (`/ws/voice`)
- Uses the same auth and rate-limit modes.
- API key can be passed via:
  - `X-API-Key` header
  - `Authorization: Bearer <key>`
  - `api_key` query parameter (for browser demo clients)
