# Demo Shot Checklist and Short Recording Plan

Use with: `docs/DEMO_VIDEO_SCRIPT_3MIN.md`
Target length: `2:55 - 3:00`

## 1) Pre-Recording Setup (5-7 min)
- [ ] Confirm services are up:
  - `http://127.0.0.1:8000/health`
  - `http://127.0.0.1:8001/health`
  - `http://127.0.0.1:8501`
- [ ] Run Bedrock connectivity proof:
  - `python -m leaksentinel.doctor --as-json`
- [ ] Capture hosted judge proof:
  - `python scripts/capture_hosted_judge_run.py --api-base http://127.0.0.1:8000 --scenario-id S05 --mode bedrock --strict`
- [ ] Keep these files ready to show:
  - `data/_reports/bedrock_doctor_latest.json`
  - `data/_reports/judge_runs/latest.md`
  - `data/_reports/judge_runs/latest.json`
- [ ] Open all required windows before recording:
  - terminal (large font)
  - Streamlit dashboard
  - voice demo page
  - first media file: `D:\Amazon Hackathon\Su_Sızıntısı_Sesiyle_Video_Oluşturma.mp4`

## 2) Shot Checklist (Timecoded)

| Time | Shot | Must Show | Done |
|---|---|---|---|
| 0:00-0:12 | Cold open media | `Su_Sızıntısı_Sesiyle_Video_Oluşturma.mp4` + title overlay | [ ] |
| 0:12-0:32 | Problem slide | false dispatch cost, missed leak risk, operator overload | [ ] |
| 0:32-0:50 | Architecture slide | flow + thermal + audio + planned-ops + memory -> decision bundle | [ ] |
| 0:50-1:15 | Terminal proof | `doctor --as-json` + `capture_hosted_judge_run --strict` with PASS checks | [ ] |
| 1:15-1:55 | Incidents UI | run `S05` in `bedrock`, Decision card, Reason, What To Do Now, Judge Compliance | [ ] |
| 1:55-2:25 | Evidence and Trace | Evidence tab + Trace tab + History tab | [ ] |
| 2:25-2:43 | Impact and Ops | Impact metrics + Counterfactual + Ops Portal quick view | [ ] |
| 2:43-2:55 | Voice | one push-to-talk utterance + one short response | [ ] |
| 2:55-3:00 | End card | Agentic AI + `#AmazonNova` + closing line | [ ] |

## 3) Critical On-Screen Proof Points
- [ ] `judge_compliance.pass: True`
- [ ] `_runtime.bedrock.used: True`
- [ ] `_runtime.bedrock.request_ids` non-empty
- [ ] Fallback indicators visible in Trace/Runtime section
- [ ] Impact numbers visible in Impact tab

## 4) Fallback Rules During Recording
- [ ] If voice demo is unstable, skip voice segment and move directly to closing.
- [ ] If a command output is delayed, narrate the previous verified artifact (`latest.md` / `latest.json`) and continue.
- [ ] Do not claim any feature that is not currently visible on screen.

## 5) Short Recording Plan (30 min)

| Minute | Task |
|---|---|
| 0-5 | Open windows, set zoom/font size, clear desktop clutter |
| 5-10 | Run preflight commands and verify PASS outputs |
| 10-18 | Record take 1 (full 3-minute flow) |
| 18-24 | Review take 1 quickly; mark weak transitions |
| 24-30 | Record take 2 with tighter pacing and cleaner tab transitions |

## 6) Final Quality Gate Before Export
- [ ] Total duration between `2:55` and `3:00`
- [ ] Narration is fully English
- [ ] No Turkish text visible in UI artifacts
- [ ] Terminal lines are readable in video resolution
- [ ] End card includes `#AmazonNova`
