<#
.SYNOPSIS
    Prove the scanner's accuracy, and scan anything you like with it.

.DESCRIPTION
    Two questions, one command:

      1. "Is it accurate?"  -> runs the ground-truth corpus and reports measured
         precision and recall per rule. The corpus lives in
         tests/fixtures/proof_corpus and its expected answers, with the date each
         registry fact was verified, are in tests/proof_ground_truth.py.

      2. "What does it say about MY code?" -> pass -Path and it scans that folder,
         printing which checks ran, which could not, and why.

    Needs no Redis, no worker, no database.

.EXAMPLE
    ./scripts/prove.ps1
    Runs the accuracy gate only.

.EXAMPLE
    ./scripts/prove.ps1 -Path "D:\my\repo"
    Runs the accuracy gate, then scans that folder.

.EXAMPLE
    ./scripts/prove.ps1 -Path "D:\my\repo" -Offline -FailOnCertain
    Scans with no network (registry checks report inconclusive) and exits 3 if any
    CERTAIN finding is present, for use in a pipeline.
#>
[CmdletBinding()]
param(
    [string]$Path,
    [switch]$Offline,
    [switch]$FailOnCertain,
    [switch]$SkipAccuracy
)

$ErrorActionPreference = "Stop"

# Run from api/ regardless of where this was invoked, so PYTHONPATH="." resolves
# app/ and the relative corpus paths hold.
$apiRoot = Split-Path -Parent $PSScriptRoot
Push-Location $apiRoot
$env:PYTHONPATH = "."
# Findings and coverage detail contain em dashes; without this PowerShell mangles them.
$env:PYTHONIOENCODING = "utf-8"

$exitCode = 0
try {
    if (-not $SkipAccuracy) {
        Write-Host ""
        Write-Host "=== Accuracy: measured against known answers ===" -ForegroundColor Cyan
        Write-Host "Corpus: tests/fixtures/proof_corpus   Expectations: tests/proof_ground_truth.py"
        Write-Host ""
        python -m pytest tests/test_accuracy.py -v --no-header -p no:cacheprovider -W "ignore::DeprecationWarning"
        if ($LASTEXITCODE -ne 0) {
            Write-Host ""
            Write-Host "ACCURACY GATE FAILED - a rule has regressed. Do not trust scan output until this is green." -ForegroundColor Red
            $exitCode = 4
            return
        }
        Write-Host ""
        Write-Host "Accuracy gate passed: every asserted fact was detected, and no clean fixture produced a finding." -ForegroundColor Green
    }

    if ($Path) {
        if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
            Write-Host "Not a directory: $Path" -ForegroundColor Red
            $exitCode = 2
            return
        }
        Write-Host ""
        Write-Host "=== Scanning: $Path ===" -ForegroundColor Cyan

        $scanArgs = @("-m", "app.cli_scan", $Path)
        if ($Offline)       { $scanArgs += "--offline" }
        if ($FailOnCertain) { $scanArgs += "--fail-on-certain" }

        python @scanArgs
        $scanExit = $LASTEXITCODE

        Write-Host ""
        switch ($scanExit) {
            0 { Write-Host "No findings in what was scanned. Check the coverage table above for what was NOT scanned." -ForegroundColor Green }
            1 { Write-Host "Findings present - see above." -ForegroundColor Yellow }
            3 { Write-Host "CERTAIN findings present." -ForegroundColor Red }
            default { Write-Host "Scan failed (exit $scanExit)." -ForegroundColor Red }
        }
        $exitCode = $scanExit
    }
}
finally {
    Pop-Location
}

exit $exitCode
