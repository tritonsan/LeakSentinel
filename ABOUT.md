# LeakSentinel - About The Project (Draft)

## Inspiration
Pipeline operators get flooded with alarms, and many turn out to be false positives caused by normal conditions (maintenance, valve tests, scheduled fills). We wanted a system that acts like an experienced triage engineer: it does not panic on a single signal, it gathers corroborating evidence, checks what was planned, and then explains a decision clearly enough to act on.

Beyond industrial safety, the motivation is sustainability: faster and more accurate verification can reduce product loss, environmental harm, and unnecessary dispatch costs.

## What it does
LeakSentinel is an agentic, multimodal incident verification copilot for suspected pipeline leaks.

Given a suspicious time window and zone, it:
- Detects and summarizes flow anomalies.
- Pulls thermal and acoustic evidence (spectrogram) to confirm or refute leak-like signatures.
- Checks for planned operations in the same window to suppress preventable false alarms.
- Retrieves similar past incidents to speed up triage (incident memory).
- Produces an explainable decision and writes an "evidence bundle" that operators can review.

At a high level, LeakSentinel turns "an alarm" into "a decision with receipts."

## How we built it
We designed the workflow as an agentic orchestration with tool-style steps:
- Flow analyzer: computes an anomaly score and a short summary for the time window.
- Thermal checker: flags leak-like hotspot patterns from thermal imagery.
- Audio checker: inspects spectrograms for hiss-like leak signatures, gated by thermal confidence.
- Ops verifier: searches a planned-operations database for overlapping work orders.
- Decision synthesizer: fuses evidence into a dispatch recommendation with confidence and rationale.

For the hackathon, we built a deterministic local demo mode using synthetic scenarios and reproducible evidence bundles so judges can run it end-to-end without external dependencies. We also added a hybrid evaluation lane with a public scientific acoustic benchmark track (GPLA-12 subset) to stress-test ambiguity handling beyond fully synthetic cases. In parallel, we defined Amazon Bedrock integration points to use Amazon Nova for:
- Reasoning and decision synthesis (Nova 2 Lite).
- Similar-incident retrieval embeddings (Nova Multimodal Embeddings).
- Realtime voice interaction for the hosted demo (Nova 2 Sonic).
- Optional UI/tool automation (Nova Act).

We also built a simple UI to run scenarios, inspect evidence bundles, and browse planned operations (Ops Portal).

## Challenges we ran into
- False alarms are not just a modeling problem: you need operational context (planned work) to avoid expensive mistakes.
- Multimodal evidence is messy: files can be missing, low quality, or contradictory; the system must degrade gracefully.
- Demo reliability matters as much as model quality: we prioritized deterministic scenario replay and clear outputs.
- Voice streaming in browsers is sensitive to permissions and network conditions, so we designed push-to-talk and non-voice fallbacks.

## Accomplishments that we're proud of
- An end-to-end workflow that produces operator-readable evidence bundles (not just a single classification).
- Planned-ops suppression logic to reduce preventable dispatches.
- Ask-for-more-evidence output for uncertain cases, with concrete next capture requests.
- Counterfactual panel ("if no planned ops") and impact meter outputs to connect technical decisions to operational effect.
- Reliability card in the dashboard (fallback/Bedrock/feedback memory signals) for judge-facing robustness.
- A judge-friendly dashboard that makes the reasoning and supporting evidence easy to inspect.
- A clean path to upgrade the local heuristics into Nova-powered reasoning, embeddings, and voice for the hosted demo.

## What we learned
- "Explainability" is a product requirement: operators need a short rationale and the underlying evidence artifacts.
- Gating and uncertainty handling is crucial: when one modality is weak, the agent should request or use another.
- Building evaluation early (precision/recall and false-alarm rate on scenario packs) keeps the project honest.

## What's next for LeakSentinel
- [In Progress] Expand the scenario pack and dataset so benchmarks are statistically meaningful (more zones, more ops types, more ambiguity cases) (`data/scenarios/scenario_pack.json`, `leaksentinel/eval/benchmark.py`).
- [Done] Realtime voice path is now end-to-end for demo flows: browser push-to-talk -> FastAPI `WS /ws/voice` -> voice backend (`services/voice/`) -> Nova 2 Sonic -> streamed transcript/audio back (`services/api/main.py`, `services/web/voice_demo.html`).
- [Done] Runnable Nova Act demo path for ops verification is available as a strict command (`python -m leaksentinel act ops-check ...`) with run logs (`data/_reports/act_runs`) (`leaksentinel/act/ops_check.py`).
- [In Progress] Extend "learning from mistakes" beyond confidence downshift into richer root-cause clustering and evidence requests (`leaksentinel/feedback/`).
- [In Progress] Harden deployment on ECS Fargate (runbook, logs, and reliability checks) for a judge-safe hosted experience (`infra/cfn/ecs-fargate-leaksentinel.yaml`, `docs/DEPLOY_ECS_FARGATE.md`).
