# LeakSentinel (Nova Hackathon MVP+) — Codex CLI Repo Pack

This repo pack is structured for **Codex CLI** to implement an agentic, multimodal leak verification MVP.

## Included
- Scenario pack + manifest binder (scripts)
- Synthetic data generation scripts (flow + thermal + audio + spectrogram)
- Streamlit UI: Dashboard + Ops Portal (search/filter using `data/ops_db.json`)
- Step Functions ASL skeleton + Lambda contracts
- Optional: Strands Agents + MCP tool skeleton
- Optional: GPLA-12 downloader (public GitHub) -> WAVs -> spectrograms

## Quickstart
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python scripts/generate_flows.py
python scripts/generate_thermal_images.py
python scripts/build_spectrograms.py
python scripts/create_manifest.py

python scripts/run_local_workflow.py --scenario_id S02
streamlit run ui/dashboard.py
```

## Optional agentic stack
```bash
pip install -r requirements-agentic.txt
```

## Optional GPLA-12 download
```bash
python scripts/download_gpla12.py --version v3 --max_files 20
python scripts/build_spectrograms.py --use_gpla12
```
