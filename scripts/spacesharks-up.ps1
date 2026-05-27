# spacesharks-up.ps1 -- boot the full Mission Desk stack
#
# Order:
#   1. Ensure WSL Ubuntu is running
#   2. Start Ollama daemon inside WSL (background)
#   3. Wait for Ollama /api/tags to respond
#   4. Recover NemoClaw sandbox (if stopped)
#   5. Start Mission Desk server.py
#   6. Print dashboard URL + endpoints
#
# Usage:
#   .\scripts\spacesharks-up.ps1              # default port 8780
#   .\scripts\spacesharks-up.ps1 -Port 8788   # custom port
#   .\scripts\spacesharks-up.ps1 -SkipSandbox # don't touch NemoClaw

[CmdletBinding()]
param(
    [int]$Port = 8780,
    [switch]$SkipSandbox,
    [switch]$SkipBrowser,
    [string]$WslUser = "polkasharks",
    [string]$WslDistro = "Ubuntu"
)

$ErrorActionPreference = "Continue"
$RepoRoot = Split-Path -Parent $PSScriptRoot

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host " SPACESHARKS MISSION DESK - BOOTING" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan

# ----- 1. WSL up? -------------------------------------------------------------
Write-Host "[1/5] WSL Ubuntu status..." -ForegroundColor Yellow
$wsl = wsl.exe --list --running --quiet 2>$null
if (-not ($wsl -match $WslDistro)) {
    Write-Host "  starting $WslDistro..." -ForegroundColor Gray
    wsl.exe -d $WslDistro -u $WslUser -e bash -lc "echo wsl-up" | Out-Null
}
Write-Host "  OK WSL $WslDistro is running" -ForegroundColor Green

# ----- 2. Ollama daemon -------------------------------------------------------
Write-Host "[2/5] Ollama daemon on RTX 5070 (in WSL)..." -ForegroundColor Yellow
$ollamaProbe = wsl.exe -d $WslDistro -u $WslUser -e bash -lc "curl -s --max-time 3 http://127.0.0.1:11434/api/tags 2>/dev/null | head -c 50" 2>$null
if (-not $ollamaProbe) {
    Write-Host "  daemon not running -- starting in background..." -ForegroundColor Gray
    wsl.exe -d $WslDistro -u $WslUser -e bash -lc "nohup ollama serve > /tmp/ollama.log 2>&1 &" | Out-Null
    Start-Sleep -Seconds 3
}
# Wait up to 30s for the daemon to bind
$tries = 0
while ($tries -lt 15) {
    $resp = $null
    try { $resp = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 2 -ErrorAction Stop } catch {}
    if ($resp) { break }
    Start-Sleep -Seconds 2
    $tries++
}
if ($resp) {
    Write-Host "  OK Ollama daemon LIVE on 127.0.0.1:11434" -ForegroundColor Green
    Write-Host "  OK $($resp.models.Count) models loaded" -ForegroundColor Green
    $resp.models | Where-Object { $_.name -match "nemotron" } | ForEach-Object {
        Write-Host "    - $($_.name) (Nemotron)" -ForegroundColor Cyan
    }
} else {
    Write-Host "  FAIL Ollama daemon did not respond -- server will fall back to SIM mode" -ForegroundColor Red
}

# ----- 3. NemoClaw sandbox ---------------------------------------------------
if (-not $SkipSandbox) {
    Write-Host "[3/5] NemoClaw sandbox (Docker container in WSL)..." -ForegroundColor Yellow
    $sandboxState = wsl.exe -d $WslDistro -u $WslUser -e bash -lc "docker ps -a --filter name=openshell-my-assistant --format '{{.Status}}' | head -1" 2>$null
    if ($sandboxState -match "^Up") {
        Write-Host "  OK sandbox already running" -ForegroundColor Green
    } elseif ($sandboxState -match "Exited") {
        Write-Host "  sandbox exited -- running 'nemoclaw my-assistant recover'..." -ForegroundColor Gray
        # Run recover in background -- it can take 30s to pull/start
        wsl.exe -d $WslDistro -u $WslUser -e bash -lc "nohup nemoclaw my-assistant recover > /tmp/nemoclaw-recover.log 2>&1 &" | Out-Null
        Start-Sleep -Seconds 5
        Write-Host "  OK recover dispatched (logs: /tmp/nemoclaw-recover.log)" -ForegroundColor Green
    } else {
        Write-Host "  FAIL no NemoClaw sandbox 'my-assistant' configured" -ForegroundColor Yellow
        Write-Host "    bootstrap with: wsl bash -lc 'nemoclaw onboard'" -ForegroundColor Gray
    }
} else {
    Write-Host "[3/5] NemoClaw sandbox -- SKIPPED (-SkipSandbox)" -ForegroundColor DarkGray
}

# ----- 4. Mission Desk server.py ---------------------------------------------
Write-Host "[4/5] Mission Desk server.py on port $Port..." -ForegroundColor Yellow
# Kill any prior server.py on the same port
$existing = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match "server\.py" -and $_.CommandLine -match "--port\s+$Port" }
if ($existing) {
    Write-Host "  stopping existing server.py on port $Port (PID $($existing.ProcessId))..." -ForegroundColor Gray
    Stop-Process -Id $existing.ProcessId -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

$desk = Join-Path $RepoRoot "desk"
$logPath = "$env:TEMP\spacesharks-server-$Port.log"
$proc = Start-Process -FilePath "python" -ArgumentList "server.py","--port",$Port `
    -WorkingDirectory $desk -WindowStyle Hidden `
    -RedirectStandardOutput $logPath -RedirectStandardError "$logPath.err" -PassThru
Write-Host "  server.py PID=$($proc.Id), log=$logPath" -ForegroundColor Gray

# Wait for server health
$tries = 0
$serverOk = $false
while ($tries -lt 30) {
    try {
        $state = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/state" -TimeoutSec 2 -ErrorAction Stop
        $serverOk = $true
        break
    } catch {}
    Start-Sleep -Seconds 2
    $tries++
}

if ($serverOk) {
    Write-Host "  OK Mission Desk LIVE" -ForegroundColor Green
    Write-Host "    mode=$($state.inference.mode)" -ForegroundColor Cyan
    Write-Host "    weather.source=$($state.weather.source)  Kp=$($state.weather.kp)  X-ray=$($state.weather.xray_class)" -ForegroundColor Cyan
    Write-Host "    fleet=$($state.sats.Count) sats" -ForegroundColor Cyan
} else {
    Write-Host "  FAIL Mission Desk did not respond on port $Port" -ForegroundColor Red
    Write-Host "    last 5 lines of server log:" -ForegroundColor Red
    Get-Content $logPath -Tail 5 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "      $_" -ForegroundColor Red }
}

# ----- 5. Open dashboard ------------------------------------------------------
Write-Host "[5/5] Dashboard..." -ForegroundColor Yellow
Write-Host "  Dashboard URL:        http://127.0.0.1:$Port/" -ForegroundColor Green
Write-Host "  Tactical brief:       http://127.0.0.1:$Port/api/neo/tactical-brief" -ForegroundColor Gray
Write-Host "  At-risk top 10:       http://127.0.0.1:$Port/api/neo/at-risk?n=10" -ForegroundColor Gray
Write-Host "  Space weather forecast: http://127.0.0.1:$Port/api/neo/space-weather-forecast" -ForegroundColor Gray
Write-Host "  Where needs Starlink: http://127.0.0.1:$Port/api/neo/where-needs-starlink" -ForegroundColor Gray
Write-Host "  Storage audit:        http://127.0.0.1:$Port/api/neo/storage-audit" -ForegroundColor Gray

if (-not $SkipBrowser -and $serverOk) {
    Start-Process "http://127.0.0.1:$Port/"
}

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host " SPACESHARKS UP - PID $($proc.Id) on port $Port" -ForegroundColor Cyan
Write-Host " stop with:  .\scripts\spacesharks-down.ps1" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
