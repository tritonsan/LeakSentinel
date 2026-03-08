param(
    [string]$ApiHost = "127.0.0.1",
    [int]$ApiPort = 8000,
    [int]$VoicePort = 8001
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Write-Host "Repo: $repo"

$hasUvicorn = $false
try {
    python -c "import uvicorn" *> $null
    $hasUvicorn = $true
} catch {
    $hasUvicorn = $false
}

if ($hasUvicorn) {
    $apiCmd = "cd `"$repo`"; python -m uvicorn services.api.main:app --host $ApiHost --port $ApiPort --reload"
} else {
    # Fallback static server so voice demo HTML can still be opened without uvicorn.
    $apiCmd = "cd `"$repo\services\web`"; python -m http.server $ApiPort --bind $ApiHost"
}

$voiceCmd = "cd `"$repo\services\voice`"; if (!(Test-Path node_modules)) { npm install }; npm run dev"

Start-Process powershell -ArgumentList "-NoExit", "-Command", $apiCmd | Out-Null
Start-Process powershell -ArgumentList "-NoExit", "-Command", $voiceCmd | Out-Null

$demoPath = if ($hasUvicorn) { "/demo/voice_demo.html" } else { "/voice_demo.html" }
$url = if ($hasUvicorn) {
    "http://${ApiHost}:$ApiPort${demoPath}?api=http://${ApiHost}:$ApiPort"
} else {
    "http://${ApiHost}:$ApiPort${demoPath}?api=http://${ApiHost}:$VoicePort&transport=http"
}
Write-Host "Started API and voice service in new terminals."
if (-not $hasUvicorn) {
    Write-Host "uvicorn not found: using python -m http.server fallback for demo page."
}
Write-Host "Open: $url"
