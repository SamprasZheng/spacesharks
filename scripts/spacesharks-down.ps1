# spacesharks-down.ps1 -- graceful shutdown of the full stack
#
# By default keeps WSL itself running (cheap), only stops:
#   - server.py (Mission Desk)
#   - Ollama daemon
#   - NemoClaw sandbox container (stops, not destroys -- preserves state)
#   - OpenShell gateway
#
# Usage:
#   .\scripts\spacesharks-down.ps1            # graceful, preserves NemoClaw state
#   .\scripts\spacesharks-down.ps1 -KeepOllama  # leave Ollama running (for other tools)
#   .\scripts\spacesharks-down.ps1 -DestroySandbox  # also delete NemoClaw container

[CmdletBinding()]
param(
    [switch]$KeepOllama,
    [switch]$DestroySandbox,
    [string]$WslUser = "polkasharks",
    [string]$WslDistro = "Ubuntu"
)

$ErrorActionPreference = "Continue"

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host " SPACESHARKS MISSION DESK - SHUTTING DOWN" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan

# ----- 1. server.py (every port) ---------------------------------------------
Write-Host "[1/4] killing server.py processes..." -ForegroundColor Yellow
$servers = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match "server\.py" }
if ($servers) {
    $servers | ForEach-Object {
        $port = if ($_.CommandLine -match "--port\s+(\d+)") { $Matches[1] } else { "?" }
        Write-Host "  killing PID $($_.ProcessId) (port $port)..." -ForegroundColor Gray
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 1
    Write-Host "  OK $($servers.Count) server.py processes stopped" -ForegroundColor Green
} else {
    Write-Host "  OK no server.py running" -ForegroundColor Green
}

# ----- 2. NemoClaw sandbox container -----------------------------------------
Write-Host "[2/4] NemoClaw sandbox container..." -ForegroundColor Yellow
$cid = wsl.exe -d $WslDistro -u $WslUser -e bash -lc "docker ps --filter name=openshell-my-assistant -q | head -1" 2>$null
if ($cid -and $cid.Trim()) {
    if ($DestroySandbox) {
        Write-Host "  destroying sandbox (--DestroySandbox)..." -ForegroundColor Gray
        wsl.exe -d $WslDistro -u $WslUser -e bash -lc "nemoclaw my-assistant destroy --yes" 2>&1 | Out-Null
        Write-Host "  OK sandbox destroyed" -ForegroundColor Green
    } else {
        Write-Host "  stopping container (state preserved)..." -ForegroundColor Gray
        wsl.exe -d $WslDistro -u $WslUser -e bash -lc "docker stop $cid" 2>&1 | Out-Null
        Write-Host "  OK sandbox stopped" -ForegroundColor Green
    }
} else {
    Write-Host "  OK no running sandbox container" -ForegroundColor Green
}

# Also kill openshell-gateway if it leaked
wsl.exe -d $WslDistro -u $WslUser -e bash -lc "pkill -f openshell-gateway 2>/dev/null || true" 2>&1 | Out-Null

# ----- 3. Ollama daemon ------------------------------------------------------
Write-Host "[3/4] Ollama daemon..." -ForegroundColor Yellow
if ($KeepOllama) {
    Write-Host "  OK left running (--KeepOllama)" -ForegroundColor DarkGray
} else {
    $pid_ollama = wsl.exe -d $WslDistro -u $WslUser -e bash -lc "pgrep -f '^ollama serve' | head -1" 2>$null
    if ($pid_ollama -and $pid_ollama.Trim()) {
        wsl.exe -d $WslDistro -u $WslUser -e bash -lc "pkill -f '^ollama serve'" 2>&1 | Out-Null
        Start-Sleep -Seconds 1
        Write-Host "  OK ollama serve stopped" -ForegroundColor Green
    } else {
        Write-Host "  OK no ollama daemon running" -ForegroundColor Green
    }
}

# ----- 4. final verify -------------------------------------------------------
Write-Host "[4/4] verify ports closed..." -ForegroundColor Yellow
$leftover = wsl.exe -d $WslDistro -u $WslUser -e bash -lc "ss -tlnp 2>/dev/null | grep -E ':(11434|18789|8642|8080)\s' | head -5" 2>$null
if ($leftover -and $leftover.Trim()) {
    Write-Host "  WARN leftover listeners (may be unrelated):" -ForegroundColor Yellow
    $leftover -split "`n" | ForEach-Object { if ($_.Trim()) { Write-Host "    $_" -ForegroundColor Gray } }
} else {
    Write-Host "  OK all spacesharks ports closed (11434/18789/8642/8080)" -ForegroundColor Green
}

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host " SPACESHARKS DOWN" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
