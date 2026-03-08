# CODEX_PLAN (MVP+)

## Milestone 1 — Data pipeline
Run:
- scripts/generate_flows.py
- scripts/generate_thermal_images.py
- scripts/build_spectrograms.py
- scripts/create_manifest.py

Acceptance:
- `data/manifest/manifest.csv` exists and all referenced files exist.

## Milestone 2 — Local workflow
- scripts/run_local_workflow.py creates evidence bundle JSON in `data/evidence_bundles/`

## Milestone 3 — UI
- ui/dashboard.py includes Ops Portal with search/filter over `data/ops_db.json`

## Milestone 4 — Agentic skeleton
- agents/mcp_server_leaksentinel.py: tool contracts
- agents/decision_agent_strands.py: agent loop skeleton
