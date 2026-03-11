param(
    [string]$RemoteName = "origin",
    [string]$DefaultBranch = "main"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repo

$failures = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]

function Add-Failure([string]$Message) {
    $script:failures.Add($Message)
    Write-Host "FAIL: $Message"
}

function Add-Warning([string]$Message) {
    $script:warnings.Add($Message)
    Write-Host "WARN: $Message"
}

function Confirm-File([string]$Path) {
    if (Test-Path $Path) {
        Write-Host "OK:   $Path"
    } else {
        Add-Failure "Missing required file: $Path"
    }
}

function Invoke-GitQuiet([string]$ArgsLine) {
    cmd /c "git $ArgsLine 1>nul 2>nul"
    return $LASTEXITCODE
}

function Invoke-GitText([string]$ArgsLine) {
    $output = cmd /c "git $ArgsLine 2>nul"
    return @($output)
}

Write-Host "Public repo preflight"
Write-Host "Repo: $repo"

if ((Invoke-GitQuiet 'ls-files --error-unmatch .env') -eq 0) {
    Add-Failure ".env is tracked in git."
} else {
    Write-Host "OK:   .env is not tracked"
}

if ((Invoke-GitQuiet 'check-ignore .env') -eq 0) {
    Write-Host "OK:   .env is ignored by git"
} else {
    Add-Warning ".env is not currently matched by git ignore rules on this machine."
}

$statusLines = @(Invoke-GitText 'status --short')
if ($LASTEXITCODE -ne 0) {
    Add-Failure "git status failed. Verify the repo path and git access."
} elseif ($statusLines.Count -gt 0 -and $statusLines[0]) {
    Add-Warning "Working tree is not clean. Review changes before public push."
    $statusLines | ForEach-Object { Write-Host "      $_" }
} else {
    Write-Host "OK:   working tree is clean"
}

$remoteUrl = @(Invoke-GitText "remote get-url $RemoteName")
if ($LASTEXITCODE -eq 0 -and $remoteUrl.Count -gt 0 -and $remoteUrl[0]) {
    Write-Host "OK:   git remote '$RemoteName' -> $($remoteUrl[0])"
} else {
    Add-Warning "Git remote '$RemoteName' is not configured yet."
}

$currentBranch = @(Invoke-GitText 'branch --show-current')
if ($LASTEXITCODE -ne 0) {
    Add-Failure "Unable to read current git branch."
} elseif ($currentBranch.Count -gt 0 -and $currentBranch[0]) {
    Write-Host "OK:   current branch is '$($currentBranch[0])'"
    if ($currentBranch[0] -ne $DefaultBranch) {
        Add-Warning "Current branch is '$($currentBranch[0])', expected public default '$DefaultBranch'."
    }
}

@(
    "README.md",
    "ABOUT.md",
    "docs/SUBMISSION_CHECKLIST.md",
    "docs/JUDGE_DEMO_RUNBOOK.md",
    "docs/DEPLOY_ECS_FARGATE.md",
    "docs/SECRETS_POLICY.md",
    ".github/workflows/ci.yml",
    "scripts/demo_preflight.ps1",
    "scripts/start_local_recording_demo.ps1"
) | ForEach-Object { Confirm-File $_ }

if (Test-Path "LICENSE") {
    Write-Host "OK:   LICENSE"
} else {
    Add-Warning "LICENSE is missing. Add one before opening the repo publicly."
}

if ($failures.Count -gt 0) {
    Write-Host ""
    Write-Host "Public repo preflight FAILED."
    exit 2
}

Write-Host ""
if ($warnings.Count -gt 0) {
    Write-Host "Public repo preflight PASSED with warnings."
    exit 0
}

Write-Host "Public repo preflight PASSED."

