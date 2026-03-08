# Hackathon Readiness Snapshot

- Generated (UTC): `2026-03-01 01:31:07Z`
- Source gate report: `data\_reports\benchmark_gate_latest.json`

## Overall Decision
- Decision: **ship**
- Missing required assets: `0`
- Core hard-gate failures: `no`
- Core soft-gate failures: `no`

## Root-Cause Summary (By Axis)
- `audio_pipeline`: no blocking evidence from static artifacts; voice backend must be verified during live demo boot.
- `media_generation`: no media artifact blocker detected in latest judge bundle.
- `consistency_logic`: no consistency gate failure detected.

## Core Gate Snapshot
| Set | Exists | Accuracy | Leak Recall | Planned Recall | Inv->Leak % | ECE | Issues |
|---|---|---:|---:|---:|---:|---:|---|
| tuning_latest | yes | 1.000 | 1.000 | 1.000 | 0.0% | 0.143 | - |
| holdout_v1_latest | yes | 1.000 | 1.000 | 1.000 | 0.0% | 0.139 | - |
| holdout_v2_latest | yes | 1.000 | 1.000 | 1.000 | 0.0% | 0.140 | - |

## Submission Asset Check
| Asset | Exists |
|---|---|
| `README.md` | yes |
| `ABOUT.md` | yes |
| `docs/SUBMISSION_CHECKLIST.md` | yes |
| `docs/JUDGE_DEMO_RUNBOOK.md` | yes |
| `docs/DEMO_VIDEO_SCRIPT_3MIN.md` | yes |
| `docs/DEVPOST_SUBMISSION_DRAFT.md` | yes |
| `docs/claim_evidence_map.json` | yes |

## Judge Bundle Snapshot
- Latest judge bundle: `data\evidence_bundles\S05_zone-1_2026-02-05T10-00-00.json`
- `judge_compliance.pass`: `True`
- `_runtime.bedrock.used`: `True`
- Missing fields: `-`

## Prioritized Fix List
1. Capture one hosted Bedrock judge run and preserve request IDs in evidence bundle. Expected impact: Closes judge trace gap and upgrades trust for live Q&A.
2. Keep calibration profile frozen and rerun gate report after any decision policy change. Expected impact: Protects current ECE pass status and prevents silent regression.
3. Lock submission narrative assets (video script + Devpost draft + checklist owner/timestamp). Expected impact: Reduces last-day submission risk and speeds final packaging.

## Thresholds Used
- `min_leak_recall`: `0.95`
- `min_planned_ops_recall`: `0.8`
- `max_inv_false_leak_rate`: `0.05`
- `max_ece`: `0.2`
