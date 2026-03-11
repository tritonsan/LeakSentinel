# About the project

## Inspiration

LeakSentinel was inspired by a simple but expensive operational problem: pipeline teams receive many alarms that look critical, yet a large portion of them are false positives. Routine maintenance, valve tests, scheduled filling operations, and noisy sensor behavior can all trigger alerts that send crews into the field unnecessarily.

We wanted to build a system that behaves less like a single classifier and more like an experienced incident engineer. Instead of reacting to one signal, it gathers supporting evidence, checks operational context, compares against similar historical cases, and explains *why* it recommends action.

Beyond industrial safety, the motivation is also sustainability: better verification means less product loss, lower environmental risk, and fewer unnecessary dispatches.

## What it does

**LeakSentinel** is an **agentic, multimodal leak-verification system** for suspected pipeline incidents.

For a suspicious zone and time window, it can:

- analyze flow anomalies,
- inspect thermal evidence,
- inspect acoustic evidence through spectrograms,
- verify whether planned operations overlap with the event,
- retrieve similar historical incidents,
- produce an explainable decision with confidence and supporting evidence.

Instead of returning only a label, LeakSentinel creates an **evidence bundle** that operators can review. In practice, it turns *"something looks wrong"* into *"here is the decision, the evidence behind it, and what to do next."*

## How we built it

We built LeakSentinel as an orchestration pipeline with specialized steps that work like tools inside an agent workflow:

- **Flow analyzer** to score anomaly behavior,
- **Thermal checker** to detect leak-like hotspot patterns,
- **Acoustic checker** to evaluate hiss-like signatures from spectrogram data,
- **Operations verifier** to search for overlapping planned work,
- **Decision layer** to fuse the evidence into a final recommendation.

For the hackathon demo, we focused heavily on **reproducibility**. We created deterministic local scenario packs, synthetic evidence generation scripts, and operator-readable evidence bundles so the system can run end-to-end without depending on unstable external conditions.

We also integrated **Amazon Nova** services through **Amazon Bedrock**:

- **Nova 2 Lite** for reasoning and decision synthesis,
- **Nova Multimodal Embeddings** for similar-incident retrieval,
- **Nova 2 Sonic** for realtime voice interaction in the hosted demo path,
- **Nova Act** for strict operational verification flows.

To make the demo easy to inspect, we added a dashboard and hosted API layer so judges can run scenarios, inspect evidence, and observe how each part of the system contributes to the final outcome.

## Challenges we ran into

One of the biggest challenges was that leak detection is not just a modeling problem. **Operational context matters.** A strong anomaly without context can still be a false alarm, so planned operations had to be treated as first-class evidence rather than an afterthought.

Another challenge was **multimodal reliability**. Thermal frames, spectrograms, and operational records do not always agree, and sometimes one of them is missing or weak. That forced us to design graceful fallback behavior and uncertainty-aware outputs instead of pretending every case could be cleanly classified.

We also ran into a classic hackathon issue: **demo stability matters as much as raw intelligence**. Because of that, we invested heavily in deterministic replay, reproducible scenarios, and fallback paths for voice and hosted components.

## Accomplishments that we're proud of

- We built an **end-to-end agentic workflow** that produces evidence bundles, not just a prediction.
- We added **planned-operations verification** so the system can suppress preventable false positives instead of overreacting.
- We created **uncertainty-aware outputs** that can ask for more evidence when the case is ambiguous.
- We connected technical outputs to operational impact through **scorecards, calibration, and evidence provenance**.
- We built a **judge-friendly dashboard** and hosted demo path that make the system inspectable rather than opaque.
- We established a clear **Nova-powered architecture** instead of using AI as a vague add-on.

## What we learned

We learned that **explainability is not optional** in industrial workflows. If operators cannot see why a system made a decision, they will not trust it in the moments that matter.

We also learned that multimodal AI becomes much more useful when each modality has a clear role. Flow data helps identify suspicious behavior, thermal and acoustic evidence help verify physical signs, and operational context helps prevent expensive mistakes.

Finally, we learned that evaluation needs to be part of the build from the start. A useful way to think about the problem is reducing expected incident cost, not just maximizing classification accuracy:

$$
\text{Expected Loss} = P(\text{missed leak}) \cdot C_{\text{miss}} + P(\text{false dispatch}) \cdot C_{\text{false alarm}}
$$

That framing helped us prioritize **reliability, uncertainty handling, and operator trust**.

## What's next for LeakSentinal

- Expand the scenario pack and benchmark coverage so results are stronger across more zones, operating conditions, and ambiguity cases.
- Grow the feedback loop so operator corrections improve future triage decisions more directly.
- Harden the hosted deployment path for a more production-like, judge-safe live demo.
- Improve realtime voice reliability and make voice interaction feel like a natural operational copilot.
- Continue strengthening the bridge between deterministic local evidence and Nova-powered hosted reasoning.
