param(
  [string]$OutJson = "data/_reports/benchmark_gate_latest.json",
  [string]$OutMd = "data/_reports/benchmark_gate_latest.md",
  [switch]$IncludeAblations
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-LatestCsv([string]$DirPath) {
  if (-not (Test-Path $DirPath)) {
    throw "Missing directory: $DirPath"
  }
  $csv = Get-ChildItem -Path $DirPath -Filter "*.csv" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if (-not $csv) {
    throw "No CSV file found in: $DirPath"
  }
  return $csv.FullName
}

$tuning = Get-LatestCsv "data/_reports/tuning_latest"
$h1 = Get-LatestCsv "data/_reports/holdout_v1_latest"
$h2 = Get-LatestCsv "data/_reports/holdout_v2_latest"
$args = @(
  "scripts/benchmark_gate_report.py",
  "--report", "tuning_latest=$tuning",
  "--report", "holdout_v1_latest=$h1",
  "--report", "holdout_v2_latest=$h2",
  "--out-json", $OutJson,
  "--out-md", $OutMd
)
if ($IncludeAblations) {
  $h2ab = Get-LatestCsv "data/_reports/holdout_v2_ablations_2026-02-16"
  $args += @("--split-ablations", "--report", "holdout_v2_ablations=$h2ab")
}

python @args

Write-Output "Wrote gate report:"
Write-Output "  $OutJson"
Write-Output "  $OutMd"
