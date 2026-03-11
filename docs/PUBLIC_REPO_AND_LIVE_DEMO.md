# Public Repo And Live Demo

This is the final packaging runbook for making LeakSentinel judge-accessible with the fewest moving parts.

## Ship Decision
- `ship`, with one condition: only expose the hosted URL after `scripts/demo_preflight.ps1` passes against the deployed API.

## Public Repo
1. Run preflight:
   - `powershell -ExecutionPolicy Bypass -File scripts\public_repo_preflight.ps1`
2. Resolve warnings that affect judge access:
   - add a `LICENSE` file
   - configure a git remote (`origin`)
   - review uncommitted files before push
3. Create the public GitHub repo and attach the remote:
   - `git remote add origin <YOUR_GITHUB_REPO_URL>`
4. Push the release branch:
   - `git push -u origin main`
5. Confirm GitHub Actions starts:
   - `.github/workflows/ci.yml`

## Recommended Live Demo Route
- Use the hosted FastAPI API on ECS Fargate as the single public entry point.
- Give judges one base URL and one fallback page:
  - `http://<AlbDnsName>/health`
  - `http://<AlbDnsName>/demo/voice_demo.html`
- Keep the Streamlit dashboard as operator-facing support, not the primary public entry point.

## Deployment Path
1. Build and push the image described in `docs/DEPLOY_ECS_FARGATE.md`.
2. Deploy `infra/cfn/ecs-fargate-leaksentinel.yaml`.
3. Capture `AlbDnsName` from CloudFormation outputs.
4. Run live preflight:
   - `powershell -ExecutionPolicy Bypass -File scripts\demo_preflight.ps1 -ApiBase http://<AlbDnsName> -RequireVoice`
5. If you need a judge-trace artifact before the live session:
   - `powershell -ExecutionPolicy Bypass -File scripts\demo_preflight.ps1 -ApiBase http://<AlbDnsName> -RequireVoice -CaptureHostedJudgeRun -ScenarioId S05 -Mode bedrock -ApiKey <key>`

## Cut Vs Keep
- Keep:
  - `/health`
  - `/run`
  - `/demo/voice_demo.html`
  - hosted Bedrock judge capture
- Cut from the live pitch unless re-verified the same day:
  - any untested extra UI path
  - optional multimodal flourish that is not needed for the 4-minute story

## Claim-Safe Narrative
- Say confidently:
  - the repo is public and reproducible from `README.md`
  - the hosted demo exposes live health and judge-ready execution paths
  - the latest readiness snapshot is `ship`
- Qualify:
  - realtime voice is part of the live path only when preflight confirms backend reachability
  - Bedrock live evidence should be described using the captured judge-run artifact when available

## Critical References
- `README.md`
- `docs/HACKATHON_READINESS_LATEST.md`
- `docs/JUDGE_DEMO_RUNBOOK.md`
- `docs/DEPLOY_ECS_FARGATE.md`
- `docs/SECRETS_POLICY.md`
