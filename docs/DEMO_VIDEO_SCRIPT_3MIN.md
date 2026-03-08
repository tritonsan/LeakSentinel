# 3-Minute Demo Video Script (Final Recording Cut)

Goal: present problem -> live Bedrock proof -> product depth -> measurable impact, with no over-claims.

Total target: 2:55 to 3:00.
Execution checklist: `docs/DEMO_SHOT_CHECKLIST.md`

## Scene 1 (0:00 - 0:12) Cold Open: Real Signal
- First visual asset: `D:\Amazon Hackathon\Su_Sızıntısı_Sesiyle_Video_Oluşturma.mp4`
- On-screen:
  - Play a short leak-sound segment from the file.
  - Overlay title: `LeakSentinel | Agentic Leak Verification`
- Voiceover (English):
  - "This is the sound of uncertainty in pipeline operations."
  - "LeakSentinel turns uncertain alerts into explainable, auditable decisions."

## Scene 2 (0:12 - 0:32) Problem and Stakes
- On-screen:
  - One slide with three bullets: false dispatch cost, missed leak risk, operator overload.
- Voiceover (English):
  - "Operators face two expensive failures: dispatching for false alarms and missing real leaks."
  - "Single-sensor alerts are not enough for reliable action."
  - "We built LeakSentinel to verify incidents before crews are sent."

## Scene 3 (0:32 - 0:50) Architecture in One Frame
- On-screen:
  - Pipeline diagram: flow + thermal + audio + planned-ops + memory -> decision + evidence bundle.
  - Nova labels: Nova Pro, Nova 2 Lite, Nova Embeddings, Nova 2 Sonic.
- Voiceover (English):
  - "LeakSentinel fuses flow anomalies, thermal and acoustic evidence, planned-operations context, and incident memory."
  - "It uses Nova Pro for multimodal analysis, Nova 2 Lite for decision synthesis, Nova Embeddings for retrieval, and Nova 2 Sonic for voice interaction."

## Scene 4 (0:50 - 1:15) Hard Proof: Live Bedrock Connectivity
- On-screen terminal:
  - `python -m leaksentinel.doctor --as-json`
  - Show `ready_for_bedrock_demo: true` and request IDs in output.
  - `python scripts/capture_hosted_judge_run.py --api-base http://127.0.0.1:8000 --scenario-id S05 --mode bedrock --strict`
  - Show checks:
    - `judge_compliance.pass: True`
    - `_runtime.bedrock.used: True`
    - `_runtime.bedrock.request_ids non-empty: True`
- Voiceover (English):
  - "Before demoing outcomes, we prove live Bedrock connectivity."
  - "This run confirms active Bedrock usage and non-empty request IDs for auditability."
  - "No hidden stubs, no unverifiable claims."

## Scene 5 (1:15 - 1:55) Incident Run + Decision Story
- On-screen UI:
  - `streamlit run ui\dashboard.py`
  - In `Incidents`, run scenario `S05` in `bedrock` mode.
  - Show:
    - `Decision` card
    - `Reason (Plain Language)`
    - `What To Do Now`
    - `Safety and Trust` + `Judge Compliance`
- Voiceover (English):
  - "Now we run a live incident in Bedrock mode."
  - "The system outputs a decision, confidence, plain-language reasoning, and a recommended action."
  - "Safety guardrails are explicit, and judge compliance is visible in the same screen."

## Scene 6 (1:55 - 2:25) Evidence, Traceability, and Learning
- On-screen tabs:
  - `Evidence`: thermal, spectrogram, acoustic explanation.
  - `Trace`: request trace, fallback usage, decision trace, provenance.
  - `History`: similar incidents, similar past mistakes, feedback trend.
- Voiceover (English):
  - "Every decision is backed by concrete evidence artifacts."
  - "Trace view shows request lineage, fallback status, calibration, and provenance."
  - "History view closes the loop with similar incidents and operator feedback learning."

## Scene 7 (2:25 - 2:43) Operational Value
- On-screen:
  - `Impact` tab: avoided false dispatch, avoided leak loss, total expected impact.
  - Counterfactual and next-best-evidence request panels.
  - Quick jump to `Ops Portal`: coverage plan or closed-loop simulation card.
- Voiceover (English):
  - "LeakSentinel does not stop at labels."
  - "It quantifies operational impact, runs counterfactual checks, and recommends next best evidence."
  - "Ops views convert model output into dispatch-ready decisions."

## Scene 8 (2:43 - 2:55) Voice Interaction (Short)
- On-screen:
  - `http://127.0.0.1:8000/demo/voice_demo.html?api=http://127.0.0.1:8000`
  - One push-to-talk question and one short response.
- Voiceover (English):
  - "For field workflows, we also provide a realtime voice path with Nova 2 Sonic."
  - "This keeps operator interaction fast in high-pressure environments."

## Scene 9 (2:55 - 3:00) Closing Frame
- On-screen end card:
  - `LeakSentinel`
  - `Agentic AI Category`
  - `Auditable Bedrock evidence + explainable incident decisions`
  - `#AmazonNova`
- Voiceover (English):
  - "LeakSentinel is an agentic, explainable, and operations-ready leak verification system built on Amazon Nova."

## Recording Guardrails
- Keep all narration in English.
- Show only features visible in the recording.
- Keep terminal font size large enough for request IDs and pass/fail checks.
- If a voice segment fails live, skip voice and continue with UI; do not pause the story arc.
