# Submission Checklist (Devpost + Amazon Nova Hackathon)

This file is the "do not forget" list for final submission. You can submit early and keep editing until the deadline.

## Key Dates (from plan)
- Submission deadline: March 16, 2026, 5:00 PM PT
- Feedback deadline: March 18, 2026, 5:00 PM PT
- Judging: March 17, 2026 - April 2, 2026
- Winners announced (approx.): April 8, 2026

## Required For Submission
- Text description: brief summary, purpose, and how we leverage Amazon Nova (Bedrock).
- Demo video: ~3 minutes, shows the project in action, includes hashtag `#AmazonNova`.
- Code repo: accessible to judges.
  - If private: share with `testing@devpost.com` and `Amazon-Nova-hackathon@amazon.com`.

## Optional (Bonus)
- Builder AWS blog post (builder.aws.com): positive impact on target community, potential benefits, real-world application, adoption plans.

## Our "Minimum Submit" (so we can submit early)
- Elevator pitch tagline is <= 200 characters.
- "Which Amazon Nova model/service did you use?" gallery field: pick `Nova 2 Lite` as the primary.
- "Also used" (in description): Nova Multimodal Embeddings, Nova 2 Sonic, Nova Act.
- About page content exists in Markdown: `ABOUT.md` (keep updated as we build).

## Final QA Before Deadline
- Local demo run works from clean env using `README.md` steps.
- Hosted API health endpoint works (`/health`) and `/run` produces an evidence bundle.
- Operator feedback endpoint works (`/feedback`) and stores false-positive records.
- Bedrock mode is clearly described (and implemented if we claim it in the demo).
- Video narration matches what actually runs (avoid claiming features that are still stubs).

## Readiness Snapshot Workflow
- Generate latest snapshot:
  - `python scripts/hackathon_readiness_snapshot.py`
- Review:
  - `docs/HACKATHON_READINESS_LATEST.md`
- Ensure these packaging assets are up to date:
  - `docs/DEVPOST_SUBMISSION_DRAFT.md`
  - `docs/DEMO_VIDEO_SCRIPT_3MIN.md`
- Run claim/evidence lint:
  - `python scripts/claim_lint.py`
- Before live demo recording, run preflight:
  - `powershell -ExecutionPolicy Bypass -File scripts\\demo_preflight.ps1 -ApiBase http://<AlbDnsName> -RequireVoice`
