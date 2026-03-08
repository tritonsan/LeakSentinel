# Devpost Submission Draft

Use this as the editable base for final Devpost form fields.

## Project Name
LeakSentinel

## One-Line Tagline (<=200 chars)
Agentic multimodal leak verification with Nova: flow + thermal + audio + ops context, producing explainable decisions and evidence bundles for reliable incident triage.

## Primary Category
Agentic AI

## Amazon Nova Usage
- Primary: Nova 2 Lite (reasoning + decision synthesis in Bedrock mode)
- Also used:
  - Nova Multimodal Embeddings (similar-incident retrieval)
  - Nova 2 Sonic (realtime voice demo path)
  - Nova Act (strict ops-check command path)

## Problem
Pipeline operators face high alert volume and costly false positives. A single sensor anomaly is not enough for safe action; teams need corroboration and context before dispatching field crews.

## Solution
LeakSentinel is an agentic multimodal verification system that:
1. analyzes flow anomalies,
2. checks thermal and acoustic evidence,
3. verifies planned operations in the same time window,
4. retrieves similar historical incidents,
5. returns an explainable decision with confidence and an evidence bundle.

## What Is Novel
- Multimodal fusion with operational guardrails (planned ops cannot hide strong leak evidence).
- Judge-oriented explainability outputs: decision trace, calibration, provenance, and compliance blocks.
- Human feedback loop for reducing repeated false positives.

## Demo / Testing Instructions
- Reproducible local demo steps are in `README.md`.
- Judge runbook is in `docs/JUDGE_DEMO_RUNBOOK.md`.
- Optional hosted voice demo path documented in `docs/VOICE_DEMO.md`.

## Tech Stack
- Python, FastAPI, Streamlit
- Amazon Bedrock (Nova models)
- Optional Node.js voice microservice for Nova 2 Sonic
- Deterministic scenario packs + evidence bundles for reproducible review

## Impact
- Reduces preventable false dispatches by combining planned-ops context with multimodal evidence.
- Improves operator trust by showing decision rationale and artifacts, not only final labels.
- Supports sustainability goals via faster leak verification and lower waste risk.

## Repo Access Note (If Private)
Share access with:
- `testing@devpost.com`
- `Amazon-Nova-hackathon@amazon.com`

## Video Note
- Keep the video around 3 minutes.
- Include hashtag `#AmazonNova`.
- Use the script in `docs/DEMO_VIDEO_SCRIPT_3MIN.md` for consistency with live behavior.
