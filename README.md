# LeakSentinel (Amazon Nova Hackathon Project)

LeakSentinel is an **agentic, multimodal** incident verification system for pipeline leaks.
It detects suspicious flow anomalies, gathers **thermal** and **acoustic** evidence, checks for **planned operations**, retrieves **similar past incidents**, and produces an explainable decision with an evidence bundle.

This repository is the **main project**. The folder `leaksentinel-codex-plus/` is **reference-only draft material**.

## Hackathon Alignment
- Category (submission): Agentic AI
- Nova on AWS: Amazon Bedrock (Nova models)
- Strengths:
  - Agentic tool use + orchestration
  - Multimodal reasoning (thermal + audio spectrogram)
  - Multimodal embeddings for incident memory (similar-incident retrieval)
  - Operator feedback loop (learning from false positives)
  - Optional realtime voice interface (Nova 2 Sonic) with fallback

## Quickstart (Local Demo Mode)
1. Create venv and install deps
   - Windows PowerShell:
     - `python -m venv .venv`
     - `.\\.venv\\Scripts\\Activate.ps1`
     - `pip install -r requirements.txt`
2. Generate demo data
   - `python scripts\\generate_flows.py`
   - `python scripts\\generate_thermal_images.py`
   - `python scripts\\build_spectrograms.py`
   - `python scripts\\create_manifest.py`

### Optional: Add Limited Real Audio Sample (GPLA-12)
1. Download and convert a small subset to WAV:
   - `python scripts\\download_gpla12.py --max-files 40`
   - Optional mapping override: `python scripts\\download_gpla12.py --max-files 40 --normal-class-ids 1,2,3,4 --uncertain-class-ids 9,10,11,12`
2. Build spectrograms for that subset:
   - `python scripts\\build_spectrograms.py --use-gpla12`
3. Recreate manifest (will prefer GPLA-12 spectrograms when available):
   - `python scripts\\create_manifest.py`
4. Run benchmark with track-level summary (`core` vs `real_challenge`):
   - `python -m leaksentinel benchmark --mode local --ablation full`
   - Holdout pack v1 (frozen): `python -m leaksentinel benchmark --mode local --ablation full --scenario-pack data\\scenarios\\scenario_pack_holdout.json`
   - Holdout pack v2 (frozen): `python -m leaksentinel benchmark --mode local --ablation full --scenario-pack data\\scenarios\\scenario_pack_holdout_v2.json`
5. Validate dataset consistency:
   - `python -m leaksentinel validate-dataset --scenario-pack data\\scenarios\\scenario_pack.json`
6. Optional comparison table across tuning/holdout runs:
   - `python scripts\\benchmark_compare.py --report tuning=data\\_reports\\benchmark_local_<tuning>.csv --report holdout_v1=data\\_reports\\benchmark_local_<h1>.csv --report holdout_v2=data\\_reports\\benchmark_local_<h2>.csv`

### Investigate Safety Hardening
- Decision outputs now include:
  - `decision_safety_flags`
  - `investigate_reason_code`
- Benchmark summaries now include investigate safety metric:
  - `Inv->Leak %` (how often investigate bucket was incorrectly predicted as leak)
- Runbook: `docs\\HARDENING_PLAYBOOK.md`
- Gate-style error-detection log:
  - `python scripts\\benchmark_gate_report.py --split-ablations --report tuning_latest=<csv> --report holdout_v1_latest=<csv> --report holdout_v2_latest=<csv> --out-json data\\_reports\\benchmark_gate_latest.json --out-md data\\_reports\\benchmark_gate_latest.md`
  - Helper (core/holdout full only): `powershell -ExecutionPolicy Bypass -File scripts\\run_benchmark_gate_latest.ps1`
  - Helper (include ablations): `powershell -ExecutionPolicy Bypass -File scripts\\run_benchmark_gate_latest.ps1 -IncludeAblations`

### Voice (Nova 2 Sonic)
Voice is optional and sits on top of the core scenario pipeline.

We provide a small Nova 2 Sonic voice microservice under `services/voice/` and a demo page served by the FastAPI app:
- Voice demo page: `http://localhost:8000/demo/voice_demo.html?api=http://localhost:8000`
- See `services/api/README.md` and `docs\\VOICE_DEMO.md`.
- Quick start helper (opens both services in new PowerShell windows):
  - `powershell -ExecutionPolicy Bypass -File scripts\\start_voice_demo.ps1`
  - If `uvicorn` is not installed, the script automatically serves `services/web` with `python -m http.server` and gives a working fallback URL.
3. Run a scenario and write an evidence bundle
   - `python -m leaksentinel run --scenario-id S02 --mode local`
   - V2 analysis outputs (default): `next_evidence_request_v2`, `counterfactual_v2`, `impact_estimate_v2`
   - Extended operational outputs: `continuous_flow_alert`, `pressure_plan`, `audio_explain`, `scorecard`, `standards_readiness`
   - Decision-quality outputs: `decision_trace_v1`, `evidence_quality_v1`, `confidence_calibration_v1`, `provenance_v1`
   - Proof outputs: `impact_proof_v1`, `closed_loop_summary_v1`
   - Optional controls:
     - `python -m leaksentinel run --scenario-id S02 --mode local --analysis-version v1`
     - `python -m leaksentinel run --scenario-id S02 --mode local --no-counterfactuals --no-impact`
     - `python -m leaksentinel run --scenario-id S02 --mode local --no-flow-agent --no-pressure-plan --no-scorecard --no-standards`
     - Judge mode: `python -m leaksentinel run --scenario-id S05 --mode local --judge-mode --json`
     - Impact compare by persona: `python -m leaksentinel impact compare --mode local --scenario-ids S02,S04,S05 --persona utility`
     - Closed-loop simulation: `python -m leaksentinel ops closed-loop-simulate --scenario-id S05 --mode local --field-verdict rejected_false_positive`
     - Incident lifecycle open/list: `python -m leaksentinel ops incident-open --scenario-id S05 && python -m leaksentinel ops incident-list`
     - Zone risk map: `python -m leaksentinel ops risk-map --window-days 30`
     - Incident KPI summary: `python -m leaksentinel impact kpis`
     - Integration ingest/export: `python -m leaksentinel integrations ingest-event --source scada --event-type pressure_drop --zone zone-1 --payload-json "{\"delta\":12}"` and `python -m leaksentinel integrations export --format csv --entity incidents`
4. Launch UI
   - `streamlit run ui\\dashboard.py`

## Bedrock Mode (AWS)
Bedrock mode is wired behind flags and environment variables. It is expected to be used for the hosted demo.
See `docs\\BEDROCK_SETUP.md`.

### Hosted API `/run` (V2 options)
- Request body fields:
  - `scenario_id` (required)
  - `mode` (`local|bedrock`)
  - `analysis_version` (`v1|v2`, default `v2`)
  - `include_counterfactuals` (default `true`)
  - `include_impact` (default `true`)
  - `include_flow_agent` (default `true`)
  - `include_pressure_plan` (default `true`)
  - `include_scorecard` (default `true`)
  - `include_standards` (default `true`)
  - `judge_mode` (default `false`)

### Additional API Endpoints
- `GET /health/live`: process liveness probe.
- `GET /health/ready`: readiness probe (includes voice backend reachability).
- `POST /ops/coverage-plan`: builds dispatch priority queue from evidence bundles.
- `POST /standards/check`: evaluates building standards readiness from profile + controls catalog.
- `POST /impact/compare`: compares baseline vs LeakSentinel impact over scenario ids or bundle list (`persona`: `utility|industrial|campus`).
- `POST /ops/closed-loop-simulate`: runs alarm -> dispatch -> field verdict -> feedback loop simulation.
- Incident lifecycle:
  - `POST /ops/incidents/open`
  - `GET /ops/incidents`
  - `POST /ops/incidents/{incident_id}/dispatch`
  - `POST /ops/incidents/{incident_id}/field-update`
  - `POST /ops/incidents/{incident_id}/close`
- `GET /impact/kpis`: aggregates closed/provisional value and response-time KPIs.
- `GET /ops/risk-map`: zone-level risk scoring (`risk_score_0_100`, trend, repeat FP counts).
- Integrations:
  - `GET /integrations/connectors`
  - `POST /integrations/events`
  - `POST /integrations/export`

### Hosted Security Modes (Demo-Safe)
The API supports staged runtime enforcement:
- `LEAKSENTINEL_AUTH_ENFORCEMENT=off|monitor|on`
- `LEAKSENTINEL_RATE_LIMIT_ENFORCEMENT=off|monitor|on`
- `LEAKSENTINEL_VOICE_REQUIRED_FOR_READINESS=true|false`

Recommended:
- Demo/staging: `monitor` + `monitor`
- Production: `on` + `on`

Request auth headers:
- `X-API-Key: <key>` or `Authorization: Bearer <key>`

Response control headers:
- `X-Auth-Mode`, `X-RateLimit-Mode`, `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `Retry-After`, `X-Request-ID`

## Learning From Mistakes (Operator Feedback)
- Save operator rejection feedback for a bundle:
  - `python -m leaksentinel feedback add --bundle-path data\\evidence_bundles\\S02_zone-1_2026-02-05T03-00-00.json --outcome false_positive_rejected_by_operator --note "Planned tank fill heat artifact" --root-cause-guess planned_operation_overlap --evidence-gap confirm_planned_ops_status_and_capture_post_window_sample`
- List feedback:
  - `python -m leaksentinel feedback list --limit 20`
- Hosted API:
  - `POST /feedback` (see `services/api/README.md`)

## Nova Act (Strict)
- `python -m leaksentinel act ops-check --zone zone-1 --start 2026-02-05T02:00:00 --end 2026-02-05T04:00:00`
- The command is strict: if Nova Act fails, it returns non-zero and does **not** fall back to local ops query.

## Hosted Mode Dependencies
This repo includes a hosted API in `services/api/`. It requires extra packages:
- `pip install -r requirements-hosted.txt`
Note: In this environment, network restrictions may prevent installing new dependencies.

## Deploy (ECS Fargate)
Recommended for realtime voice + WebSocket streaming:
- See `docs\\DEPLOY_ECS_FARGATE.md`.
- GitHub Actions workflows:
  - `.github/workflows/ci.yml`
  - `.github/workflows/cd-staging.yml`
  - `.github/workflows/cd-dashboard-staging.yml`
  - `.github/workflows/cd-prod.yml`
  - Variable/secret map: `cicd/README.md`

## Repo Structure
- `leaksentinel/`: core library (orchestrator, tools, clients, evaluation)
- `scripts/`: demo data generators and manifest creation
- `ui/`: Streamlit judge-friendly dashboard
- `services/api/`: FastAPI API for hosted demo + websocket voice bridge
- `services/voice/`: Nova 2 Sonic voice microservice (Bedrock bidirectional streaming)
- `docs/`: submission/testing/video/runbook assets

## Dataset Tracks
- `core`: deterministic synthetic scenarios (stable CI/regression signal)
- `real_challenge`: real-audio preference scenarios backed by GPLA-12 spectrogram evidence
- Real-audio labeling policy:
  - High-confidence samples can feed leak/normal lanes
  - Uncertain samples are routed to `investigate`-style usage (not direct leak confirmation)

## Submission Docs
- About (Devpost draft): `ABOUT.md`
- Submission checklist: `docs/SUBMISSION_CHECKLIST.md`
- Judge demo runbook: `docs/JUDGE_DEMO_RUNBOOK.md`
- Readiness snapshot (latest): `docs/HACKATHON_READINESS_LATEST.md`
- Devpost form draft: `docs/DEVPOST_SUBMISSION_DRAFT.md`
- 3-minute demo script: `docs/DEMO_VIDEO_SCRIPT_3MIN.md`
- Claim/evidence map: `docs/claim_evidence_map.json`
- Security modes: `docs/SECURITY_MODES.md`
- Secrets policy: `docs/SECRETS_POLICY.md`
- Voice backend deploy: `docs/DEPLOY_VOICE_BACKEND.md`
- Snapshot generator: `python scripts/hackathon_readiness_snapshot.py`
- Claim lint: `python scripts/claim_lint.py`
- Hosted judge run capture: `python scripts/capture_hosted_judge_run.py --api-base http://<AlbDnsName> --scenario-id S05 --mode bedrock --api-key <key>`
- Demo preflight: `powershell -ExecutionPolicy Bypass -File scripts\\demo_preflight.ps1 -ApiBase http://<AlbDnsName> -RequireVoice`
- Public repo preflight: `powershell -ExecutionPolicy Bypass -File scripts\\public_repo_preflight.ps1`
- Public repo + live demo runbook: `docs/PUBLIC_REPO_AND_LIVE_DEMO.md`

## Optional: LLM Offload
If you want to offload token-heavy repo scans (multi-file summaries, stub finding) to an external OpenAI model, see:
- `docs/LLM_OFFLOAD.md`
