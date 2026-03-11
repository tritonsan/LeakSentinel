# Deploy Voice Backend

This project's main ECS stack deploys the FastAPI API only. Realtime voice requires a second service for `services/voice/`.

## Recommended Minimal Path
- Deploy the API stack first.
- Deploy the voice backend as a separate container on ECS Fargate or App Runner.
- Set `VoiceBackendUrl` in the API stack to that service URL.
- Re-run:
  - `powershell -ExecutionPolicy Bypass -File scripts\demo_preflight.ps1 -ApiBase http://<AlbDnsName> -RequireVoice`

## Build Voice Image
From the repo root:

```powershell
docker build -f services/voice/Dockerfile -t leaksentinel-voice:latest .
docker tag leaksentinel-voice:latest <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/leaksentinel-voice:latest
docker push <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/leaksentinel-voice:latest
```

## Runtime Environment
- `AWS_REGION=us-east-1`
- `NOVA_SONIC_MODEL_ID=amazon.nova-sonic-v1:0`
- `PORT=8001`

## Health Check
- `GET /health`

## FastAPI Integration
Set:

```text
LEAKSENTINEL_VOICE_BACKEND_URL=http://<VOICE_BACKEND_HOST>:8001
```

Then redeploy the main API stack or update the task definition environment.
