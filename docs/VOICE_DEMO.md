# Voice Demo (Nova 2 Sonic) - Design Notes

## Why Push-to-Talk
Browser microphone permissions can be flaky in judge environments. Push-to-talk reduces:
- continuous streaming complexity
- user confusion (explicit start/stop)
- accidental background capture

## Fallbacks
1. Audio file upload (WAV/MP3) -> backend -> Sonic -> audio response
2. Text-only input -> reasoning model -> text response

## Hosted Architecture
Current implementation:
- UI (web) captures mic audio, converts to 16kHz PCM16 in-browser, and streams events to FastAPI `WS /ws/voice`.
- FastAPI forwards the collected audio to the voice service (`services/voice/`) via HTTP (`/v1/voice/sonic`).
- Voice service forwards audio to Nova 2 Sonic via Bedrock bidirectional streaming.
- FastAPI streams transcript/audio events back to the browser.

Notes:
- `voice_demo.html` query params:
  - `?api=http://localhost:8000` (default, WS bridge mode)
  - `?api=http://localhost:8001&transport=http` (direct HTTP fallback mode)
- FastAPI voice backend URL is configurable via `LEAKSENTINEL_VOICE_BACKEND_URL` (default `http://127.0.0.1:8001`).
- Voice service health endpoint `GET /health` returns configured Sonic model + candidate fallback list.

## Demo Script Tip
Keep voice segment to ~20-30 seconds in the 3-minute video:
- 1 question: "What happened in zone-1 at 03:00?"
- 1 answer: decision + 1-2 evidence points + next action
