# Judge Demo Runbook

This runbook gives a deterministic 5-minute flow for judge review.

## 1) Run Judge Demo Benchmark
- Command:
  - `python -m leaksentinel benchmark --mode local --ablation full --scenario-pack data\scenarios\scenario_pack_judge_demo.json`
- Expected:
  - Report files under `data\_reports\`
  - Summary table includes:
    - `Brier`
    - `ECE`
    - `Repeat FP Red. %`
    - `Feedback Eff. %`

## 2) Run a Judge-Mode Scenario
- Command:
  - `python -m leaksentinel run --scenario-id S05 --mode local --judge-mode --json`
- Expected keys in output:
  - `judge_compliance`
  - `decision_trace_v1`
  - `confidence_calibration_v1`
  - `provenance_v1`

## 3) Impact Comparison (Persona View)
- Utility:
  - `python -m leaksentinel impact compare --mode local --scenario-ids S02,S04,S05 --persona utility`
- Industrial:
  - `python -m leaksentinel impact compare --mode local --scenario-ids S02,S04,S05 --persona industrial`
- Expected:
  - `persona_applied`
  - `impact_bands` (`conservative`, `expected`, `aggressive`)
  - `baseline_vs_with_leaksentinel`

## 4) Closed-Loop Simulation
- Command:
  - `python -m leaksentinel ops closed-loop-simulate --scenario-id S05 --mode local --field-verdict rejected_false_positive`
- Expected:
  - `timeline`
  - `decision_change_summary`
  - `feedback_applied`

## 5) UI Walkthrough
- Launch:
  - `streamlit run ui\dashboard.py`
- In UI:
  1. Open a recent bundle from `Incidents`.
  2. Check `Trace` tab for judge evidence.
  3. Check `History` tab for learning-loop and trend.
  4. Check `Impact` tab for baseline vs with-system comparison.
  5. Use `Ops Portal` to run closed-loop simulation block.

## 6) Hosted Judge Trace Capture (Bedrock)
- Purpose: produce judge evidence with live Bedrock request IDs.
- Command:
  - `python scripts/capture_hosted_judge_run.py --api-base http://<AlbDnsName> --scenario-id S05 --mode bedrock --api-key <key>`
- Expected:
  - Output JSON under `data/_reports/judge_runs/`
  - `judge_compliance.pass=true`
  - `_runtime.bedrock.used=true`
  - `_runtime.bedrock.request_ids` is non-empty

## 7) Demo Preflight (Before Recording/Live)
- API-only preflight:
  - `powershell -ExecutionPolicy Bypass -File scripts\\demo_preflight.ps1 -ApiBase http://<AlbDnsName>`
- Strict preflight with hosted judge capture:
  - `powershell -ExecutionPolicy Bypass -File scripts\\demo_preflight.ps1 -ApiBase http://<AlbDnsName> -RequireVoice -CaptureHostedJudgeRun -ScenarioId S05 -Mode bedrock -ApiKey <key>`
