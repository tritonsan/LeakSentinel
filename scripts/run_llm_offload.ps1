param(
  [Parameter(Mandatory = $true)]
  [string]$Query,

  [string]$Model = $env:OPENAI_MODEL,
  [string]$BaseUrl = $env:OPENAI_BASE_URL,
  [string]$FoundryProjectEndpoint = $env:AZURE_FOUNDRY_PROJECT_ENDPOINT,
  [ValidateSet("low","medium","high")]
  [string]$Effort = $(if ($env:OPENAI_REASONING_EFFORT) { $env:OPENAI_REASONING_EFFORT } else { "high" }),

  [int]$MaxOutputTokens = 1200,
  [int]$MaxFiles = 20,
  [int]$MaxFileBytes = 24000,
  [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $Model -or $Model.Trim().Length -eq 0) {
  $Model = "gpt-5.2-codex"
}

function Get-BaseUrlFromFoundryProjectEndpoint([string]$Endpoint) {
  # Accepts:
  #   https://<name>.services.ai.azure.com/api/projects/<Project>
  # Derives an OpenAI-compatible Azure OpenAI base URL:
  #   https://<name>.openai.azure.com/openai/v1/
  try {
    $u = [Uri]$Endpoint
    $host = $u.Host # e.g. narrativenode.services.ai.azure.com
    if ($host -match "^(?<name>[^.]+)\\.services\\.ai\\.azure\\.com$") {
      $name = $Matches["name"]
      return "https://$name.openai.azure.com/openai/v1/"
    }
  } catch {}
  return ""
}

function Convert-SecureStringToPlainText([SecureString]$Secure) {
  $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secure)
  try {
    return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
  } finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
  }
}

$hadKey = [bool]$env:OPENAI_API_KEY
if (-not $hadKey -and -not $DryRun) {
  $sec = Read-Host "Enter OPENAI_API_KEY (input hidden)" -AsSecureString
  $plain = Convert-SecureStringToPlainText $sec
  if (-not $plain -or $plain.Trim().Length -eq 0) {
    throw "OPENAI_API_KEY is required."
  }
  $env:OPENAI_API_KEY = $plain
}

$hadBaseUrl = [bool]$env:OPENAI_BASE_URL
if (-not $BaseUrl -or $BaseUrl.Trim().Length -eq 0) {
  if ($FoundryProjectEndpoint -and $FoundryProjectEndpoint.Trim().Length -gt 0) {
    $BaseUrl = Get-BaseUrlFromFoundryProjectEndpoint $FoundryProjectEndpoint
  }
}
if (-not $BaseUrl -or $BaseUrl.Trim().Length -eq 0) {
  $ep = Read-Host "Optional Azure endpoint (paste Foundry project endpoint or Azure OpenAI base URL; Enter = default OpenAI)"
  if ($ep -and $ep.Trim().Length -gt 0) {
    if ($ep -match "\\.services\\.ai\\.azure\\.com\\/api\\/projects\\/") {
      $BaseUrl = Get-BaseUrlFromFoundryProjectEndpoint $ep
    } else {
      $BaseUrl = $ep
    }
  }
}
if ($BaseUrl -and $BaseUrl.Trim().Length -gt 0) {
  $env:OPENAI_BASE_URL = $BaseUrl.Trim()
}

$env:OPENAI_MODEL = $Model
$env:OPENAI_REASONING_EFFORT = $Effort

try {
  $pyArgs = @(
    "scripts\llm_offload_scan.py",
    "--model", "$Model",
    "--effort", "$Effort",
    "--max-output-tokens", "$MaxOutputTokens",
    "--max-files", "$MaxFiles",
    "--max-file-bytes", "$MaxFileBytes"
  )
  if ($DryRun) {
    $pyArgs += "--dry-run"
  }
  $pyArgs += @("--query", "$Query")

  python @pyArgs
} finally {
  if (-not $hadKey) {
    Remove-Item Env:\OPENAI_API_KEY -ErrorAction SilentlyContinue
  }
  if (-not $hadBaseUrl) {
    Remove-Item Env:\OPENAI_BASE_URL -ErrorAction SilentlyContinue
  }
}
