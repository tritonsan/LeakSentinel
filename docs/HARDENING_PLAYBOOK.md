# LeakSentinel Hardening Playbook

This playbook is for the investigate-safety hardening cycle.

## 1) Preflight
1. Install dependencies and activate your environment.
2. Regenerate real-audio assets:
   - `python scripts/download_gpla12.py --max-files 40 --clean`
   - `python scripts/build_spectrograms.py --use-gpla12`
   - `python scripts/create_manifest.py`
3. Validate dataset:
   - `python -m leaksentinel validate-dataset --scenario-pack data/scenarios/scenario_pack.json --strict`

## 2) Safety Gate Metrics
Primary safety goal:
- Investigate false leak rate (`INVESTIGATE` bucket predicted as `LEAK_CONFIRMED`) must be in the `0-5%` band on holdout packs.

Protection goal:
- Leak recall must not drop by more than `2-3` points compared to the previous baseline.

## 3) Benchmark Runs
Run these three reports:
1. Tuning pack:
   - `python -m leaksentinel benchmark --mode local --ablation full --scenario-pack data/scenarios/scenario_pack.json --out-dir data/_reports/tuning`
2. Holdout v1:
   - `python -m leaksentinel benchmark --mode local --ablation full --scenario-pack data/scenarios/scenario_pack_holdout.json --out-dir data/_reports/holdout_v1`
3. Holdout v2:
   - `python -m leaksentinel benchmark --mode local --ablation full --scenario-pack data/scenarios/scenario_pack_holdout_v2.json --out-dir data/_reports/holdout_v2`

Create one comparison sheet:
- `python scripts/benchmark_compare.py --report tuning=<tuning_csv> --report holdout_v1=<holdout_v1_csv> --report holdout_v2=<holdout_v2_csv> --out data/_reports/benchmark_compare_latest.md`

## 4) Bedrock Live Validation
1. Preflight:
   - `python -m leaksentinel doctor`
2. Scenario smoke:
   - `python -m leaksentinel run --scenario-id S06 --mode bedrock --json`
   - Confirm `_runtime.bedrock.fallback` is mostly `false`.
3. Bedrock holdout smoke:
   - `python -m leaksentinel benchmark --mode bedrock --ablation full --scenario-pack data/scenarios/scenario_pack_holdout.json --out-dir data/_reports/bedrock_holdout_v1`

## 5) Voice Smoke
1. Start voice backend:
   - `node services/voice/server.mjs`
2. Check health:
   - `GET http://127.0.0.1:8001/health`
3. Check API bridge health:
   - `GET http://127.0.0.1:8000/health`

## 6) Fallback / Rollback Rules
Rollback this hardening batch if any of these happens:
1. Investigate false leak rate exceeds `5%` on either holdout set.
2. Leak recall drops by more than `3` points from baseline.
3. Bedrock fallback rate spikes and decision quality regresses on holdout.

## 7) Operator Notes
For every rejected false positive, submit feedback with:
- `root_cause_guess`
- `evidence_gap`

These fields directly improve decision safety and next-evidence recommendations.

## 8) V1 Decision Policy Lock (2026-02-13)
This section is frozen for V1 demo stability. Any change requires a new benchmark snapshot for:
- `holdout_v1` (bedrock + local)
- `holdout_v2` (bedrock + local)

### Track policy (locked)
- `core`
  - `confirm_anomaly_min=1.0`
  - `strong_modal_conf_min=0.8`
  - `ignore_planned_anomaly_min=1.0`
  - `cautious_mode=false`
  - `investigate_on_modal_conflict=true`
  - `uncertain_audio_requires_investigate=true`
- `real_challenge`
  - `confirm_anomaly_min=0.0`
  - `strong_modal_conf_min=0.75`
  - `ignore_planned_anomaly_min=0.85`
  - `confirm_use_abs_anomaly=true`
  - `cautious_mode=true`
  - `investigate_on_modal_conflict=true`
  - `uncertain_audio_requires_investigate=true`

### Audio behavior lock
- `full` ablation always runs audio (no thermal-based skip).
- Bedrock-only backup (`high_confidence_audio_backup`) is allowed only when all are true:
  - track is `real_challenge`
  - mode is `bedrock`
  - `audio_label_confidence=high_confidence`
  - model audio is strong negative (`leak_like=false`, `confidence>=0.90`)
  - deterministic audio is strong positive (`leak_like=true`, `confidence>=strong_modal_conf_min`)
  - `abs(anomaly_score)>=0.30`

### Safety guardrails lock
- Modal conflict requires a reliable strong negative check (heuristic-aligned when available).
- Low-trust audio labels (`"", uncertain, synthetic, low_confidence`) cannot confirm leak without corroboration in cautious mode.
- `INVESTIGATE` bucket safety target remains mandatory:
  - `Inv->Leak % <= 5%`

## 9) Runtime Security Modes (Hosted API)
Use staged enforcement so demos stay open while production remains protected.

- Demo/staging:
  - `LEAKSENTINEL_AUTH_ENFORCEMENT=monitor`
  - `LEAKSENTINEL_RATE_LIMIT_ENFORCEMENT=monitor`
- Production:
  - `LEAKSENTINEL_AUTH_ENFORCEMENT=on`
  - `LEAKSENTINEL_RATE_LIMIT_ENFORCEMENT=on`

When `monitor` mode is enabled, inspect response headers:
- `X-Auth-Monitor-Warning`
- `X-RateLimit-Observed-Breach`

## 10) Observability Baseline (Production)
Track these signals in CloudWatch dashboard/alarms:

1. Error rate:
   - `AWS/ApplicationELB HTTPCode_Target_5XX_Count`
2. Latency:
   - `AWS/ApplicationELB TargetResponseTime (p95)`
3. Saturation:
   - `AWS/ECS CPUUtilization`, `MemoryUtilization`
4. Availability:
   - `AWS/ApplicationELB UnHealthyHostCount`

Operator checks:
1. `GET /health/live` should always return `200`.
2. `GET /health/ready` should return `200` before accepting traffic.
3. Every incident analysis run should carry `X-Request-ID` in logs for traceability.

## 11) Error-Detection Gate Log (Recommended)
After benchmark runs, produce a gate-style diagnostics report:

```powershell
python scripts/benchmark_gate_report.py --split-ablations `
  --report tuning_latest=data/_reports/tuning_latest/<tuning_csv>.csv `
  --report holdout_v1_latest=data/_reports/holdout_v1_latest/<holdout_v1_csv>.csv `
  --report holdout_v2_latest=data/_reports/holdout_v2_latest/<holdout_v2_csv>.csv `
  --report holdout_v2_ablations=data/_reports/holdout_v2_ablations_*/<ablations_csv>.csv `
  --out-json data/_reports/benchmark_gate_latest.json `
  --out-md data/_reports/benchmark_gate_latest.md
```

Track these gate fields on each cycle:
1. Leak recall (`LEAK_CONFIRMED`)
2. Planned-ops recall (`IGNORE_PLANNED_OPS`)
3. Investigate false leak rate (`Inv->Leak %`)
4. Calibration error (`ECE`)

Quick helper:
- `powershell -ExecutionPolicy Bypass -File scripts/run_benchmark_gate_latest.ps1`
