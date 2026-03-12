# Builder.aws Blog Draft

Suggested title:
LeakSentinel: Using Amazon Nova to turn noisy leak alarms into explainable incident verification

Suggested tag:
`Amazon-Nova`

Optional secondary tags:
`Amazon-Bedrock`, `Agentic-AI`, `Multimodal-AI`, `Operations`, `Voice-AI`

One-line summary:
LeakSentinel uses Amazon Nova to verify suspected pipeline leaks with flow anomalies, thermal evidence, acoustic evidence, operational context, and explainable incident bundles that operators can actually act on.

## Draft

Industrial teams do not just need more alerts. They need better decisions.

In pipeline and utility operations, a suspicious pressure drop or flow anomaly can trigger an urgent response. But many of those alerts are not real leaks. Planned maintenance, valve tests, scheduled filling operations, and noisy sensor behavior can all look dangerous at first glance. The result is expensive false dispatches, wasted time, and lower trust in monitoring systems.

We built **LeakSentinel** to solve that verification problem with Amazon Nova.

Instead of reacting to one signal, LeakSentinel behaves more like an incident engineer. It inspects multiple evidence sources, checks whether planned operations explain the event, retrieves similar historical incidents, and produces an explainable recommendation with a traceable evidence bundle. The goal is simple: reduce the time between a suspicious signal and a defensible operational decision.

## The target community

LeakSentinel is designed for pipeline operators, campus utilities teams, industrial facility managers, and field dispatch organizations that deal with high alert volume and limited response capacity.

These teams face the same operational tension:

- Missing a real leak can create safety, environmental, and financial damage.
- Overreacting to weak evidence creates unnecessary dispatches and alert fatigue.

That tradeoff is where AI can be useful, but only if the system is transparent. A black-box prediction is not enough for operations teams that need to justify sending a crew, escalating an incident, or standing down.

## What we built with Amazon Nova

LeakSentinel is an agentic, multimodal verification system built on Amazon Nova through Amazon Bedrock.

For a suspicious zone and time window, it can:

- analyze flow anomaly patterns,
- inspect thermal evidence for leak-like heat signatures,
- inspect acoustic evidence through spectrogram-derived features,
- check for overlapping planned operations,
- retrieve similar past incidents,
- produce an explainable decision with confidence, provenance, and next actions.

We used several parts of the Amazon Nova stack for distinct roles:

- **Amazon Nova 2 Lite** for reasoning and decision synthesis
- **Amazon Nova Multimodal Embeddings** for similar-incident retrieval
- **Amazon Nova 2 Sonic** for an optional realtime voice demo path
- **Nova Act** for strict operational verification flows

That split matters. We did not treat "AI" as one generic step. We assigned each Nova capability to a concrete operational job in the pipeline.

## Why explainability mattered more than raw classification

One of the most important things we learned is that leak verification is not just a classification problem. It is an operational decision problem.

A strong anomaly by itself does not always mean "dispatch now." Operators need context:

- Is there a planned tank fill?
- Did a valve test happen in the same time window?
- Does the thermal image support the flow signal?
- Does the acoustic pattern reinforce or weaken the leak hypothesis?
- Have we seen a similar pattern before, and how was it resolved?

LeakSentinel answers those questions in one flow and stores the result as an evidence bundle rather than a single label. That makes the output inspectable, shareable, and easier to trust during incident triage.

## Positive impact for the target community

The clearest benefit of this kind of system is reducing preventable false dispatches without normalizing away real risk.

For operations teams, that can mean:

- fewer unnecessary truck rolls,
- faster prioritization of the alerts that really matter,
- clearer handoff from monitoring teams to field teams,
- better post-incident review because the evidence trail is preserved,
- improved trust in AI-assisted operations because the recommendation is explainable.

There is also a sustainability angle. Faster and more reliable leak verification can reduce product loss, shorten response time, and support better environmental handling when a real incident occurs.

## Real-world application

The first practical deployment path for LeakSentinel is not full automation. It is decision support.

That is the right adoption strategy for this domain.

In a real utility or industrial workflow, LeakSentinel would sit between alert generation and field dispatch. It would enrich a suspicious event with multimodal evidence, operational context, and similar-incident memory, then produce a recommendation such as:

- likely leak, dispatch immediately,
- likely planned operation or false positive, review before dispatch,
- ambiguous case, gather additional evidence.

This keeps a human operator in the loop while making the review process faster and more consistent.

## How we approached adoption

We deliberately designed the project so adoption can happen in stages.

Stage 1 is the easiest: use LeakSentinel as a review layer for high-cost or ambiguous alerts. Teams do not need to replace existing monitoring systems. They can keep current alarms and use LeakSentinel as an explainable verification layer on top.

Stage 2 is adding operator feedback. If a field team rejects a suspected leak as a false positive, that feedback can be stored and used to improve future triage behavior.

Stage 3 is deeper integration into incident operations, including hosted APIs, dashboards, dispatch views, and voice-assisted review workflows.

This staged path matters because real adoption in industrial settings depends on reliability, traceability, and operator confidence, not just model quality.

## What made Amazon Nova a good fit

Amazon Nova was useful because the project needed multiple AI capabilities in one coherent workflow:

- cost-aware reasoning for final decisions,
- multimodal support for evidence-heavy analysis,
- embeddings for incident memory and retrieval,
- voice for accessible live demos and future operator workflows.

That let us build a system where each model or service had a clearly bounded responsibility. Instead of a monolithic prompt, we ended up with a more practical architecture: evidence collection, context verification, retrieval, decision synthesis, and explainable output.

## What is live now

We published a public repo and a live staging deployment for the project:

- Public repository: https://github.com/tritonsan/LeakSentinel
- Live dashboard: http://leakse-LoadB-r6IhrnBsGHoA-1719975109.us-east-1.elb.amazonaws.com
- Hosted API: http://leaksentinel-staging-alb-1761810252.us-east-1.elb.amazonaws.com

The live dashboard is the judge-facing surface. It is designed to make the system easier to inspect, not just easier to demo.

## What is next

The next steps are straightforward:

- expand scenario coverage and real-world evaluation,
- strengthen the closed-loop feedback path,
- deploy the full voice backend for hosted use,
- harden the hosted stack beyond hackathon staging defaults,
- keep narrowing the gap between a demo-safe workflow and a production-ready operations assistant.

## Closing

LeakSentinel is our attempt to use Amazon Nova for a problem where trust matters as much as intelligence. In operational environments, a system is only useful if people can understand why it made a recommendation and decide what to do next.

That is the direction we think practical agentic AI should take: not just generating outputs, but helping teams make better real-world decisions under uncertainty.

## Publish checklist

- Keep the `Amazon-Nova` tag on builder.aws.com.
- Add the published builder.aws.com link into the Devpost submission form.
- Make sure the blog stays materially different from the Devpost text.
- If you update URLs before publishing, prefer the dashboard link as the primary demo link.
