# Deploy (ECS Fargate, us-east-1)

This is the recommended deployment path for **realtime voice** + WebSocket streaming (Nova 2 Sonic).

## 0) Prereqs
- AWS CLI configured for `us-east-1`
- Docker installed locally
- An existing VPC with:
  - 2+ public subnets (for ALB)
  - 2+ private subnets (for ECS tasks)
- Permissions to:
  - create ECR repo and push images
  - create CloudFormation stacks
  - create ECS/ALB/IAM resources
- A reachable voice backend (`services/voice`) URL for the FastAPI WS bridge (`LEAKSENTINEL_VOICE_BACKEND_URL`)

## 1) Build and Push Image to ECR
1. Create an ECR repo (one-time):
   - `aws ecr create-repository --repository-name leaksentinel --region us-east-1`
2. Login Docker to ECR:
   - `aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com`
3. Build:
   - `docker build -t leaksentinel:latest .`
4. Tag:
   - `docker tag leaksentinel:latest <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/leaksentinel:latest`
5. Push:
   - `docker push <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/leaksentinel:latest`

## 2) Deploy CloudFormation Stack
Template: `infra/cfn/ecs-fargate-leaksentinel.yaml`

You must provide:
- `VpcId`
- `PublicSubnets` (comma-separated)
- `PrivateSubnets` (comma-separated)
- `ImageUri`
- Nova model ids (optional at first, but required for real Bedrock mode)
- `VoiceBackendUrl` (URL of `services/voice` backend for `WS /ws/voice` bridge)
- `AssignPublicIp` (recommended for hackathon budget control)
- `AllowedOrigins`
- `AuthEnforcement` (`off|monitor|on`)
- `RateLimitEnforcement` (`off|monitor|on`)
- `RateLimitPerMinute`
- `VoiceRequiredForReadiness` (`true|false`)
- `ApiKeysSecretValueFrom` (optional, strongly recommended for prod)
- `MinCapacity` / `MaxCapacity` / `CpuScaleTarget` / `MemoryScaleTarget`
- `AlarmTopicArn` (optional SNS topic)

Example:
```powershell
aws cloudformation deploy `
  --region us-east-1 `
  --stack-name leaksentinel `
  --template-file infra/cfn/ecs-fargate-leaksentinel.yaml `
  --capabilities CAPABILITY_NAMED_IAM `
  --parameter-overrides `
    AppName=leaksentinel `
    ImageUri=<ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/leaksentinel:latest `
    VpcId=vpc-xxxxxxxx `
    PublicSubnets=subnet-a,subnet-b `
    PrivateSubnets=subnet-c,subnet-d `
    AssignPublicIp=ENABLED `
    AwsRegion=us-east-1 `
    NovaReasoningModelId=<YOUR_NOVA_REASONING_MODEL_ID> `
    NovaEmbeddingsModelId=<YOUR_NOVA_EMBEDDINGS_MODEL_ID> `
    NovaMultimodalModelId=<YOUR_NOVA_MULTIMODAL_MODEL_ID> `
    NovaSonicModelId=<YOUR_NOVA_SONIC_MODEL_ID> `
    VoiceBackendUrl=http://<VOICE_BACKEND_HOST>:8001 `
    AllowedOrigins=https://<YOUR_DEMO_DOMAIN> `
    AuthEnforcement=monitor `
    RateLimitEnforcement=monitor `
    RateLimitPerMinute=120 `
    VoiceRequiredForReadiness=false `
    ApiKeysSecretValueFrom=arn:aws:secretsmanager:us-east-1:<ACCOUNT_ID>:secret:leaksentinel/staging/api-keys `
    MinCapacity=2 `
    MaxCapacity=6 `
    CpuScaleTarget=60 `
    MemoryScaleTarget=70 `
    AlarmTopicArn=arn:aws:sns:us-east-1:<ACCOUNT_ID>:leaksentinel-alerts
```

After deploy, CloudFormation outputs `AlbDnsName`.

## 3) URLs to Test
Assuming output is `http://<AlbDnsName>`:
- Health: `http://<AlbDnsName>/health`
- Voice demo page: `http://<AlbDnsName>/demo/voice_demo.html`
- WebSocket: `ws://<AlbDnsName>/ws/voice`
- Liveness: `http://<AlbDnsName>/health/live`
- Readiness: `http://<AlbDnsName>/health/ready`

## 4) Streamlit UI Link
Set this env var in Streamlit runtime:
- `LEAKSENTINEL_VOICE_URL=http://<AlbDnsName>/demo/voice_demo.html`

## 5) Autoscaling and Alarms
Template provisions:
- ECS target-tracking autoscaling on CPU and memory.
- ALB alarms:
  - target 5xx count
  - p95 latency
  - unhealthy host count
- ECS CPU high alarm.
- Optional CloudWatch dashboard (`EnableDashboard=true`).

If `AlarmTopicArn` is set, alarms publish notifications to SNS.

## Notes
- `/ws/voice` is a FastAPI WebSocket bridge. It forwards audio to `LEAKSENTINEL_VOICE_BACKEND_URL` (`services/voice`) and streams transcript/audio events back to the browser.
- For TLS (https/wss), add ACM cert + ALB HTTPS listener (recommended for browser mic in production).

### Budget note (important)
If your ECS tasks run in private subnets, they typically need a NAT Gateway for outbound access to Bedrock endpoints.
NAT Gateways have hourly + data processing costs and can exhaust a small credit budget quickly.

For hackathon demos, a low-cost option is:
- Place tasks in public subnets (you can pass public subnet ids into `PrivateSubnets` for the template)
- Set `AssignPublicIp=ENABLED`
- Keep inbound locked down so only the ALB can reach the tasks (security groups already enforce this)
