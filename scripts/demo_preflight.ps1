param(
    [string]$ApiBase = "http://127.0.0.1:8000",
    [switch]$RequireVoice,
    [switch]$CaptureHostedJudgeRun,
    [string]$ScenarioId = "S05",
    [string]$Mode = "bedrock",
    [string]$ApiKey = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-JsonOrThrow([string]$Url) {
    try {
        return Invoke-RestMethod -Method GET -Uri $Url -TimeoutSec 20
    } catch {
        throw "Request failed: $Url`n$($_.Exception.Message)"
    }
}

function To-Bool($v) {
    return [bool]$v
}

Write-Host "Preflight start"
Write-Host "API base: $ApiBase"

$liveUrl = "$($ApiBase.TrimEnd('/'))/health/live"
$readyUrl = "$($ApiBase.TrimEnd('/'))/health/ready"
$healthUrl = "$($ApiBase.TrimEnd('/'))/health"

$live = Get-JsonOrThrow -Url $liveUrl
$ready = Get-JsonOrThrow -Url $readyUrl
$health = Get-JsonOrThrow -Url $healthUrl

$ok = $true
if (-not (To-Bool $live.ok)) {
    Write-Host "FAIL: /health/live ok=false"
    $ok = $false
}
if (-not (To-Bool $ready.ok)) {
    Write-Host "FAIL: /health/ready ok=false"
    $ok = $false
}
if (-not (To-Bool $health.ok)) {
    Write-Host "FAIL: /health ok=false"
    $ok = $false
}

$voiceReachable = $false
if ($health.voice_backend -and ($health.voice_backend.PSObject.Properties.Name -contains "reachable")) {
    $voiceReachable = To-Bool $health.voice_backend.reachable
}
Write-Host "Voice backend reachable: $voiceReachable"
if ($RequireVoice -and -not $voiceReachable) {
    Write-Host "FAIL: voice backend is required but unreachable."
    $ok = $false
}

if ($CaptureHostedJudgeRun) {
    Write-Host "Capturing hosted judge run..."
    $cmd = @(
        "python",
        "scripts/capture_hosted_judge_run.py",
        "--api-base", $ApiBase,
        "--scenario-id", $ScenarioId,
        "--mode", $Mode
    )
    if ($ApiKey) {
        $cmd += @("--api-key", $ApiKey)
    }
    & $cmd[0] $cmd[1..($cmd.Length - 1)]
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAIL: hosted judge run capture failed."
        $ok = $false
    }
}

if (-not $ok) {
    Write-Host "Preflight FAILED."
    exit 2
}

Write-Host "Preflight PASSED."
