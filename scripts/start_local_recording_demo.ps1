param(
    [ValidateSet("local", "bedrock")]
    [string]$Mode = "bedrock",
    [string]$ApiHost = "127.0.0.1",
    [int]$ApiPort = 8000,
    [int]$UiPort = 8501,
    [switch]$WithVoice
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$stateRoot = Join-Path $env:TEMP "leaksentinel-local-demo"
$evidenceDir = Join-Path $stateRoot "evidence_bundles"
$feedbackDir = Join-Path $stateRoot "feedback"
$opsDir = Join-Path $stateRoot "ops"
$incidentsPath = Join-Path $opsDir "incidents.json"
$integrationsDir = Join-Path $stateRoot "integrations"
$exportsDir = Join-Path $stateRoot "exports"

New-Item -ItemType Directory -Force -Path $stateRoot | Out-Null
New-Item -ItemType Directory -Force -Path $evidenceDir | Out-Null
New-Item -ItemType Directory -Force -Path $feedbackDir | Out-Null
New-Item -ItemType Directory -Force -Path $opsDir | Out-Null
New-Item -ItemType Directory -Force -Path $integrationsDir | Out-Null
New-Item -ItemType Directory -Force -Path $exportsDir | Out-Null
if (!(Test-Path $incidentsPath)) {
    Set-Content -Path $incidentsPath -Value "[]" -Encoding UTF8
}

$envPrefix = @(
    "`$env:PYTHONPATH='$repo'",
    "`$env:LEAKSENTINEL_MODE='$Mode'",
    "`$env:LEAKSENTINEL_EVIDENCE_DIR='$evidenceDir'",
    "`$env:LEAKSENTINEL_FEEDBACK_DIR='$feedbackDir'",
    "`$env:LEAKSENTINEL_OPS_DIR='$opsDir'",
    "`$env:LEAKSENTINEL_INCIDENTS_PATH='$incidentsPath'",
    "`$env:LEAKSENTINEL_INTEGRATIONS_DIR='$integrationsDir'",
    "`$env:LEAKSENTINEL_EXPORTS_DIR='$exportsDir'"
)

$apiCmd = @(
    "Set-Location '$repo'",
    $envPrefix
    "python -m uvicorn services.api.main:app --host $ApiHost --port $ApiPort --reload"
) -join "; "

$uiCmd = @(
    "Set-Location '$repo'",
    $envPrefix
    "streamlit run ui\dashboard.py --server.address $ApiHost --server.port $UiPort"
) -join "; "

Start-Process powershell -ArgumentList "-NoExit", "-Command", $apiCmd | Out-Null
Start-Process powershell -ArgumentList "-NoExit", "-Command", $uiCmd | Out-Null

if ($WithVoice) {
    $voiceCmd = "Set-Location '$repo\services\voice'; if (!(Test-Path node_modules)) { npm install }; npm run dev"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $voiceCmd | Out-Null
}

Write-Host "API: http://${ApiHost}:$ApiPort"
Write-Host "UI:  http://${ApiHost}:$UiPort"
Write-Host "Voice demo page: http://${ApiHost}:$ApiPort/demo/voice_demo.html?api=http://${ApiHost}:$ApiPort"
Write-Host "Writable local state: $stateRoot"
Write-Host "Mode: $Mode"
