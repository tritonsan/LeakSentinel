# Secrets Policy

This project supports local `.env` for developer convenience, but staging/production secrets must not be stored in the repository.

## Rules
1. Do not commit `.env`.
2. Keep only placeholder values in `.env.example`.
3. Store runtime secrets in:
   - AWS Secrets Manager, or
   - AWS Systems Manager Parameter Store.
4. Inject secrets into ECS tasks using CloudFormation `Secrets` (`valueFrom`).

## Minimum Required Secret Controls
1. API keys:
   - Store as one secret value mapped to `LEAKSENTINEL_API_KEYS`.
   - Pass secret reference via CloudFormation parameter `ApiKeysSecretValueFrom`.
2. CI checks:
   - Workflow blocks tracked `.env`.
   - Gitleaks and Bandit run on each PR/push.
3. Rotation:
   - Rotate keys immediately if accidental disclosure is suspected.
   - Keep old + new key overlap window short (for safe cutover).

## Example (Secrets Manager)
1. Create secret:
   - Name: `leaksentinel/staging/api-keys`
   - Value: `key-a,key-b`
2. Use in deployment:
   - `ApiKeysSecretValueFrom=arn:aws:secretsmanager:...:secret:leaksentinel/staging/api-keys`

## Incident Response (If Secret Leaks)
1. Revoke/rotate leaked secret.
2. Redeploy service with new secret reference/value.
3. Review CloudWatch logs and access patterns using `X-Request-ID`.
4. Document incident timeline and remediation.
