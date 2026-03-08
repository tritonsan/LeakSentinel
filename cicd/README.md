# CI/CD Variables and Secrets

This folder documents the runtime values expected by the GitHub Actions workflows.

## Repository Variables (`vars`)
- `AWS_REGION` (default: `us-east-1`)
- `AWS_ACCOUNT_ID`
- `ECR_REPOSITORY` (default: `leaksentinel`)
- `VPC_ID`
- `PUBLIC_SUBNETS` (comma-separated)
- `PRIVATE_SUBNETS` (comma-separated)
- `NOVA_REASONING_MODEL_ID`
- `NOVA_EMBEDDINGS_MODEL_ID`
- `NOVA_MULTIMODAL_MODEL_ID`
- `NOVA_SONIC_MODEL_ID`

Staging-specific:
- `STAGING_STACK_NAME`
- `STAGING_APP_NAME`
- `STAGING_VOICE_BACKEND_URL`
- `STAGING_ALLOWED_ORIGINS`
- `STAGING_DESIRED_COUNT`
- `STAGING_MIN_CAPACITY`
- `STAGING_MAX_CAPACITY`
- `STAGING_RATE_LIMIT_PER_MINUTE`
- `STAGING_VOICE_REQUIRED_FOR_READINESS`
- `STAGING_ALARM_TOPIC_ARN`

Production-specific:
- `PROD_STACK_NAME`
- `PROD_APP_NAME`
- `PROD_VOICE_BACKEND_URL`
- `PROD_ALLOWED_ORIGINS`
- `PROD_DESIRED_COUNT`
- `PROD_MIN_CAPACITY`
- `PROD_MAX_CAPACITY`
- `PROD_RATE_LIMIT_PER_MINUTE`
- `PROD_VOICE_REQUIRED_FOR_READINESS`
- `PROD_ALARM_TOPIC_ARN`

## Repository Secrets (`secrets`)
- `AWS_ROLE_TO_ASSUME_STAGING`
- `AWS_ROLE_TO_ASSUME_PROD`
- `STAGING_API_KEYS_SECRET_VALUE_FROM`
- `PROD_API_KEYS_SECRET_VALUE_FROM`

## Deployment Modes
- Staging workflow deploys with:
  - `AuthEnforcement=monitor`
  - `RateLimitEnforcement=monitor`
- Production workflow deploys with:
  - `AuthEnforcement=on`
  - `RateLimitEnforcement=on`
