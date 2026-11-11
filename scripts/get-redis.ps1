# get-redis.ps1 - one-time bootstrap for the vendored Windows Redis.
#
# Downloads the tporadowski/redis Windows build (~3 MB) on first use, extracts it
# into <InstallDir>, and verifies redis-server.exe runs. Idempotent: if
# redis-server.exe already exists, it does nothing and exits 0.
#
# Contract with start.bat:
#   - exit 0 = redis ready; exit 1 = failed (start.bat continues WITHOUT Redis,
#     and the app degrades: /healthz redis:false, worker retries, scans 503).
#   - writes the resolved exe path to <InstallDir>\redis-path.txt so start.bat
#     can read it with for /f (no fragile stdout parsing).
#
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/get-redis.ps1 -InstallDir "F:\C Drive Packages Dump\redis"

param(
    [Parameter(Mandatory = $true)]
    [string]$InstallDir
)

$ErrorActionPreference = "Stop"

# Some older Windows PowerShell builds default to TLS 1.0; the GitHub API needs 1.2.
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$serverExe = Join-Path $InstallDir "redis-server.exe"

if (Test-Path $serverExe) {
    Write-Host "OK  Redis already present: $serverExe"
    Set-Content -Path (Join-Path $InstallDir "redis-path.txt") -Value $serverExe -Encoding ASCII
    exit 0
}

Write-Host "Downloading Redis for Windows (tporadowski/redis)..."

$release = Invoke-RestMethod -Uri "https://api.github.com/repos/tporadowski/redis/releases/latest" -Headers @{ "User-Agent" = "sqg-setup" }
$asset = $release.assets | Where-Object { $_.name -like "*.zip" } | Select-Object -First 1
if (-not $asset) {
    Write-Error "The Redis release has no .zip asset. Skipping Redis; the worker will keep retrying and /healthz will report redis:false."
    exit 1
}

$zipPath = Join-Path $env:TEMP $asset.name
Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zipPath

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Expand-Archive -Path $zipPath -DestinationPath $InstallDir -Force
Remove-Item $zipPath -Force

# The zip nests everything one folder deep (e.g. Redis-x64-5.0.14.1/); flatten it
# so redis-server.exe sits directly in $InstallDir.
$nested = Get-ChildItem -Path $InstallDir -Directory | Select-Object -First 1
if ($nested) {
    Get-ChildItem -Path $nested.FullName | Move-Item -Destination $InstallDir -Force
    Remove-Item $nested.FullName -Recurse -Force
}

if (-not (Test-Path $serverExe)) {
    Write-Error "redis-server.exe not found after extraction. Skipping Redis; the worker will keep retrying."
    exit 1
}

# Prove it runs before declaring success.
& $serverExe --version
if ($LASTEXITCODE -ne 0) {
    Write-Error "redis-server --version failed (exit $LASTEXITCODE). Skipping Redis."
    exit 1
}

Set-Content -Path (Join-Path $InstallDir "redis-path.txt") -Value $serverExe -Encoding ASCII
Write-Host "OK  Redis ready: $serverExe"
exit 0
