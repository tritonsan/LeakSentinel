# Bedrock Setup

This project is designed to run in two modes:
- `local`: no AWS calls (demo heuristics)
- `bedrock`: calls Amazon Nova models via Amazon Bedrock (hosted demo mode)

## Environment Variables
Set these in your AWS runtime environment (and optionally in `.env` for local testing):
- `AWS_REGION` (or `AWS_DEFAULT_REGION`)
- `NOVA_REASONING_MODEL_ID` (Nova 2 Lite inference profile ARN/ID in your account, or a model id if on-demand is supported)
- `NOVA_EMBEDDINGS_MODEL_ID` (Nova multimodal embeddings model)
- `NOVA_MULTIMODAL_MODEL_ID` (Nova Pro or another multimodal-capable Nova model for image checks)
- `NOVA_SONIC_MODEL_ID` (Nova 2 Sonic model for realtime voice)
- `NOVA_ACT_MODEL_ID` (optional; defaults to `nova-act-v1.0` for the Nova Act demo command)
- `LEAKSENTINEL_ALLOWED_ORIGINS` (comma-separated CORS allowlist or `*`)
- `LEAKSENTINEL_AUTH_ENFORCEMENT` (`off|monitor|on`)
- `LEAKSENTINEL_RATE_LIMIT_ENFORCEMENT` (`off|monitor|on`)
- `LEAKSENTINEL_RATE_LIMIT_PER_MINUTE` (integer)
- `LEAKSENTINEL_API_KEYS` (comma-separated API keys; use secrets manager for hosted environments)
- `LEAKSENTINEL_VOICE_REQUIRED_FOR_READINESS` (`true|false`)

## Notes
- Exact request/response schemas vary by model id and Bedrock API flavor.
- Bedrock mode will fall back to local heuristics if AWS credentials, model ids, or `boto3` are not available.
- For voice: prefer `amazon.nova-sonic-v1:0`. If you configure `amazon.nova-2-sonic-v1:0`, the voice service also tries `amazon.nova-sonic-v1:0` as a fallback candidate.
- For Nova Act (`leaksentinel act ops-check`): strict mode is enabled; failures return non-zero (no local fallback).
- For staged hardening, use:
  - Staging/demo: `AUTH=monitor`, `RATE_LIMIT=monitor`
  - Production: `AUTH=on`, `RATE_LIMIT=on`
- In staging/production, inject `LEAKSENTINEL_API_KEYS` from AWS Secrets Manager / SSM, not from checked-in files.

## Example `.env` (local dev)
See `.env.example`.
