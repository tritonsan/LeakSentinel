# LeakSentinel Hackathon Winning Plan

## 0) Submission Checklist
- Keep this updated as we build: `docs/SUBMISSION_CHECKLIST.md`

## 0.1) Main Reminder - Release Critical TODO
Primary reminder file for the latest release operations:
- `docs/RELEASE_ACTION_TODO.md`

P0 items (must do):
- [ ] Fill GitHub repo `vars/secrets` according to `cicd/README.md`.
- [ ] Deploy staging with monitor mode via `.github/workflows/cd-staging.yml`.
- [ ] After jury window, deploy production via `.github/workflows/cd-prod.yml` with `AuthEnforcement=on` and `RateLimitEnforcement=on`.

## 1) Context and Non-Negotiables
- `leaksentinel-codex-plus/` is reference only (not final architecture lock-in).
- Goal: maximize chance of **overall 1st place**.
- Core requirement: solution must use Amazon Nova model(s) and/or Nova Act.
- Judging weights (Stage Two):
  - Technical Implementation: **60%**
  - Enterprise/Community Impact: **20%**
  - Creativity/Innovation: **20%**
- Key dates:
  - Submission deadline: **March 16, 2026, 5:00 PM PT**
  - Feedback deadline: **March 18, 2026, 5:00 PM PT**
  - Judging: **March 17, 2026 - April 2, 2026**
  - Winners announced around **April 8, 2026**

## 2) Winning Strategy (Score-Driven)
## 2.1 Technical (60%) - Main lever
- Build a real agentic orchestration (not only linear script):
  - Evidence planner
  - Tool-calling analysis workers (flow, thermal, audio, ops)
  - Decision synthesizer with explainable confidence
- Add closed-loop reliability: learn from operator feedback (without risky online fine-tuning)
  - When an alarm is rejected as a false positive, store a "mistake bundle" and generate likely root-cause hypotheses.
  - Use similarity retrieval against past mistakes to reduce repeat false alarms and to request additional evidence when needed.
- Show robust evaluation:
  - Scenario benchmark table (precision, recall, false alarm rate, latency)
  - Ablation: flow-only vs flow+thermal vs flow+thermal+audio+ops
- Provide stable runnable demo:
  - one-command local run
  - deterministic scenario replay
  - clear test instructions for judges

## 2.2 Impact (20%) - Must be quantified
- Define business/community outcomes with numbers:
  - false alarm reduction %
  - response time improvement
  - potential water/gas loss avoided
- Add stakeholder-facing outputs:
  - operator-ready evidence bundle
  - actionable recommendation (dispatch/ignore/investigate)

## 2.3 Innovation (20%) - Must be visible in demo
- Multimodal fusion with uncertainty-aware gating.
- Agent memory: similar incident retrieval for faster triage.
- “Challenge mode” demo: ambiguous case where agent asks for extra evidence.

## 3) Category Positioning
- Primary category candidate: **Agentic AI** (also showcasing Multimodal depth).
- Secondary narrative: “Agentic + Multimodal for industrial safety and sustainability.”
- Keep submission in one primary category, but ensure cross-category strength in narrative/video.

## 4) Scope Update vs Current Draft
- Keep from draft:
  - 3-stage verification logic (flow -> thermal -> audio)
  - planned ops suppression
  - evidence bundle output
- Add/upgrade:
  - Nova-native agent orchestration and explicit tool trace
  - measurable KPI dashboard + benchmark suite
  - stronger UX for judge in 3-minute video (problem -> live run -> measurable result)
  - submission package completeness (repo, video, testing instructions, English text)

## 5) Execution Plan (High Priority)
1. Lock product thesis and target user (operator persona + pain points).
2. Define scoring metrics + acceptance thresholds for MVP and “winner” level.
3. Upgrade architecture to agentic orchestrator with Nova integration points.
4. Build benchmarkable scenario pack with ground truth.
5. Implement judge-friendly demo flow and fallback mode.
6. Prepare submission assets:
   - Devpost text
   - 3-minute video script
   - testing guide
   - optional builder.aws.com blog draft
7. Final hardening week:
   - runbook, bug bash, performance and reliability checks.

## 6) Deliverables Checklist
- Working demo link or reproducible local demo.
- Public/Private code repo ready for judge access.
- English project description.
- 3-minute public video with `#AmazonNova`.
- Testing instructions and optional credentials if private.
- (Bonus) Builder AWS blog post for bonus credit prize.

## 7) Risk Register (Now)
- Risk: “good idea, weak proof” -> Mitigation: mandatory benchmark table.
- Risk: “looks like prototype only” -> Mitigation: end-to-end runbook + reliability logs.
- Risk: “not enough Nova visibility” -> Mitigation: explicit architecture card showing Nova usage points.
- Risk: “video too feature-heavy, no story” -> Mitigation: strict narrative arc with timed script.

## 8) Skills and Agents Plan (If Needed)
- We will create custom skill/agent assets only if they increase speed and quality.
- Candidate internal agents:
  - `Research Agent`: rule compliance and submission completeness
  - `Architecture Agent`: orchestration and tool contracts
  - `Evaluation Agent`: metric harness and benchmark reporting
  - `Story Agent`: video script + Devpost copy consistency
- Candidate skill packs to author later:
  - `hackathon-submission-checker`
  - `nova-demo-storyliner`
  - `benchmark-qa-runner`

## 9) Q&A Start (Decision Questions)
We will proceed with these first decisions before implementation:
1. Team submitter type: Student / Professional / Organization?
2. Primary category choice: Agentic AI (recommended) or another?
3. MVP deadline (internal): which exact date before March 16, 2026?
4. Demo environment: local reproducible run vs hosted web demo vs both?
5. Real data ambition: synthetic-only for MVP, or limited real-world sample integration?

### Current Answers (Feb 7, 2026)
1. Submitter type: Professional Developer (Individual).
2. Primary category: Agentic AI (selected for submission), while still building a holistic system (multimodal, optional voice/UI automation).
3. Internal MVP freeze: not date-locked yet (note: still recommended to set at least a feature-freeze date to protect submission quality).
4. Demo environment: BOTH (hosted demo + local reproducible fallback).
5. Data strategy: synthetic + limited real sample (real sample must be clearly licensed/authorized; avoid PII).
6. Hosted target: AWS.
7. Nova access: Amazon Bedrock.
7.1 AWS region: us-east-1.
8. Embeddings: YES (Nova multimodal embeddings for incident memory + similar-incident retrieval).
9. Voice: YES (Nova 2 Sonic realtime voice demo), but with a non-voice fallback path to reduce demo risk.
10. Framework approach: Strands for primary agent orchestration + minimal LangChain for retrieval plumbing (only where it helps).

## 10) Data Strategy (Real + Synthetic)
- Baseline: synthetic flows + synthetic thermal + synthetic audio placeholders for deterministic runs.
- Limited real sample (selected): use an open-license public dataset (preferred vs collecting PII/field data).
  - Constraints:
    - Must be legally usable for hackathon + repo instructions (license/attribution).
    - Prefer "download at build/run time" rather than committing large files to repo.
    - Keep a small, reproducible subset for evaluation (e.g., N=20 clips).
  - Current choice:
    - Dataset: GPLA-12 (audio)
    - Subset size: 40 files (download + convert)

## 11) Voice Demo Strategy (Nova 2 Sonic)
- Goal: realtime voice interaction that is demo-safe.
- UI approach (hosted):
  - Push-to-talk microphone capture (short clips) -> stream to backend -> Sonic -> audio response.
  - Fallback 1: audio file upload (no mic permission needed).
  - Fallback 2: text-only input (always available).
- Local dev:
  - Voice is not required locally; keep a text-only path for deterministic tests.

## 12) Learning From Mistakes (Operator Feedback Loop)
Goal: reduce repeat false alarms and improve explainability by using human feedback, without weight updates.

Definition: a "mistake" is when LeakSentinel emits an alert/decision and operators later reject it (false positive).

What we store (Mistake Bundle):
- Original evidence bundle (flow summary, thermal/audio artifacts, planned ops context, similar incidents used)
- Model outputs: decision, confidence, rationale, evidence weights, and Bedrock request IDs (if any)
- Outcome label: `false_positive_rejected_by_operator` (future: also `missed_leak_confirmed`, etc.)
- Operator note (free text) if available

What we generate on rejection:
- A ranked list of plausible failure hypotheses, e.g.:
  - planned operations causing thermal hotspots
  - non-leak thermal artifacts (sun/ambient/insulation effects)
  - sensor drift / calibration error
  - flow anomaly within expected variance for the zone
  - audio contamination / missing audio evidence
- A "pattern fingerprint" (embeddings + key structured features) for clustering and retrieval.

How it affects future decisions (guarded):
- At run time, retrieve top-K similar past mistakes and attach them as a separate context block:
  - "similar_false_positives": [{score, timestamp, zone, short_reason}]
- Decision policy:
  - Similar-mistake signal must NOT automatically downgrade a strong leak (avoid dangerous suppression).
  - It can:
    - lower confidence
    - shift outcome to `INVESTIGATE`
    - ask for additional evidence (e.g., require audio if thermal is ambiguous)

Hackathon positioning:
- "Human-in-the-loop continuous improvement" with auditable, explainable memory (not black-box fine-tuning).
