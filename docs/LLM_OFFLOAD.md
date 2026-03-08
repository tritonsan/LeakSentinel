# LLM Offload (Token-Heavy Scans)

Purpose: offload token-heavy reading/summarization work (multi-file architecture summaries, "find stubs", "what's missing") to an external OpenAI model, while keeping implementation decisions and code changes here in the repo.

## Security
- Do **not** paste API keys into chat.
- Set `OPENAI_API_KEY` via environment variable or a local `.env` file.
- `.env` is ignored by git (`.gitignore`).

## Zero-Setup Alternative (No API Key, No Network)
If you don't want to deal with any key setup, generate a local scan report:
```powershell
python scripts\local_repo_scan_report.py
```
This produces a markdown report under `data/_llm_reports/` with stub/fallback/TODO and stack summaries.

## Install (optional)
```powershell
pip install -r requirements-llm.txt
```

## Configure
PowerShell (session only):
```powershell
$env:OPENAI_API_KEY="YOUR_KEY_HERE"
```

Optional model override:
```powershell
$env:OPENAI_MODEL="gpt-5.2-codex"
```

Reasoning effort (recommended: high):
```powershell
$env:OPENAI_REASONING_EFFORT="high"
```

Or create a local `.env` (not committed):
```text
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5.2-codex
OPENAI_REASONING_EFFORT=high
```

## Run
Dry-run (select files + build prompt, no API call):
```powershell
python scripts\llm_offload_scan.py --dry-run --query "Summarize the current architecture and list missing Bedrock pieces."
```

Note: `rg` (ripgrep) is optional. If it is not installed, the script falls back to a slower Python file walk/search.

Real call (writes report files under `data/_llm_reports/`):
```powershell
python scripts\llm_offload_scan.py --query "Find all stubs/fallbacks for bedrock mode and propose concrete implementation steps."
```

If `OPENAI_API_KEY` is not set, the script will prompt for it securely (input hidden).

### Easiest (recommended): one command with hidden key prompt
```powershell
pwsh -NoProfile -File scripts\run_llm_offload.ps1 -Query "Find all bedrock stubs/fallbacks and list implementation steps."
```

Dry-run (no key, no network):
```powershell
pwsh -NoProfile -File scripts\run_llm_offload.ps1 -DryRun -Query "Summarize architecture and list missing Bedrock pieces."
```

### Azure note
If you are using Azure OpenAI, set `OPENAI_BASE_URL` to your Azure OpenAI OpenAI-compatible endpoint, for example:
`https://<resource-name>.openai.azure.com/openai/v1/`

If you only have an Azure AI Foundry "project endpoint" that looks like:
`https://<name>.services.ai.azure.com/api/projects/<ProjectName>`
the wrapper can try to derive the OpenAI-compatible base URL from it by setting:
`AZURE_FOUNDRY_PROJECT_ENDPOINT` (or passing `-FoundryProjectEndpoint`).

If you don't want to set anything, the wrapper also accepts pasting either form into its "Optional Azure endpoint" prompt.

You can also set effort per-run:
```powershell
python scripts\llm_offload_scan.py --effort high --query "Review the repo for missing Nova integration pieces."
```

Outputs:
- `data/_llm_reports/offload_<ts>.selection.json` (what files were sent)
- `data/_llm_reports/offload_<ts>.prompt.txt` (exact prompt)
- `data/_llm_reports/offload_<ts>.out.md` (model output)

## Suggested Queries
- "List all places where bedrock mode falls back to local logic. Provide file paths and exact behaviors."
- "Propose a minimal Bedrock integration plan for Nova 2 Lite and Nova embeddings without changing the UI."
- "Review services/api for security + production readiness gaps relevant to a hackathon demo."
