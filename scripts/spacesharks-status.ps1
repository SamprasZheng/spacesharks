# spacesharks-status.ps1 -- one-shot status of every component
#
# Reports: WSL - Ollama - models - NemoClaw sandbox - OpenShell gateway - server.py ports - disk
#
# Usage:
#   .\scripts\spacesharks-status.ps1
#   .\scripts\spacesharks-status.ps1 -Json     # machine-readable

[CmdletBinding()]
param(
    [switch]$Json,
    [string]$WslUser = "polkasharks",
    [string]$WslDistro = "Ubuntu"
)

$ErrorActionPreference = "Continue"
$status = @{}

# ----- WSL -------------------------------------------------------------------
# wsl --list --running --quiet emits UTF-16; positive test is more reliable
$wslPing = wsl.exe -d $WslDistro -u $WslUser -e bash -lc "echo up" 2>$null
$status.wsl = @{
    running = ($wslPing -match "up")
    distros = @($WslDistro)
}

# ----- Ollama ----------------------------------------------------------------
$ollama = $null
try { $ollama = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 3 -ErrorAction Stop } catch {}
$status.ollama = @{
    daemon_up = $ollama -ne $null
    models = if ($ollama) { @($ollama.models | ForEach-Object { @{ name = $_.name; size_gb = [math]::Round($_.size / 1GB, 2) } }) } else { @() }
    nemotron_count = if ($ollama) { @($ollama.models | Where-Object { $_.name -match "nemotron" }).Count } else { 0 }
}

# ----- NemoClaw + OpenShell (combined into ONE wsl call to avoid cold-boot delay) -----
$wslProbe = ""
if ($status.wsl.running) {
    $wslScript = "echo '###SANDBOX###'; docker ps -a --filter name=openshell-my-assistant --format '{{.Status}}' | head -1; echo '###PORTS###'; ss -tlnp 2>/dev/null | grep -E ':(18789|8080)\s' | head -3; echo '###OLLAMADU###'; du -sb ~/.ollama/models/ 2>/dev/null | awk '{print \$1}' | head -1"
    $wslProbe = wsl.exe -d $WslDistro -u $WslUser -e bash -lc $wslScript 2>$null
}
$sb_section = ($wslProbe -split "###SANDBOX###")[1] -split "###PORTS###"
$sb_status = if ($sb_section) { $sb_section[0].Trim() } else { "" }
$status.nemoclaw = @{
    container_status = if ($sb_status) { $sb_status } else { "not present" }
    running = $sb_status -match "^Up"
}
$ports_section = ($wslProbe -split "###PORTS###")[1] -split "###OLLAMADU###"
$gw_ports = if ($ports_section) { $ports_section[0] } else { "" }
$status.openshell = @{
    listening = if ($gw_ports) { @($gw_ports -split "`n" | Where-Object { $_.Trim() }) } else { @() }
}
$ollama_section = ($wslProbe -split "###OLLAMADU###")[1]
$ollama_gb_raw = if ($ollama_section) { $ollama_section.Trim() } else { "" }

# ----- Mission Desk server.py ports -----------------------------------------
$desk = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match "server\.py" } |
    ForEach-Object {
        $port = if ($_.CommandLine -match "--port\s+(\d+)") { $Matches[1] } else { "?" }
        @{ pid = $_.ProcessId; port = $port }
    }
$status.mission_desk = @{
    instances = @($desk)
}
# Probe each for state
foreach ($d in $status.mission_desk.instances) {
    try {
        $st = Invoke-RestMethod -Uri "http://127.0.0.1:$($d.port)/api/state" -TimeoutSec 2 -ErrorAction Stop
        $d.mode = $st.inference.mode
        $d.live_calls = $st.inference.live_calls
        $d.uptime_s = $st.uptime_s
    } catch { $d.mode = "unreachable" }
}

# ----- Disk ------------------------------------------------------------------
$status.disk = @{
    ollama_models_gb = if ($ollama_gb_raw -match "^\d+$") { [math]::Round([int64]$ollama_gb_raw / 1GB, 2) } else { $null }
    data_audit_kb = if (Test-Path "D:/DOT/spacesharks/data/audit") { [math]::Round((Get-ChildItem "D:/DOT/spacesharks/data/audit" -Recurse | Measure-Object Length -Sum).Sum / 1KB, 1) } else { 0 }
}

if ($Json) {
    $status | ConvertTo-Json -Depth 5
    return
}

# ----- pretty print ----------------------------------------------------------
function Tick($b) { if ($b) { return "OK" } else { return "FAIL" } }
function Col($b)  { if ($b) { return "Green" } else { return "Red" } }

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host " SPACESHARKS - STATUS SNAPSHOT" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan

Write-Host ""
Write-Host "WSL Ubuntu        $(Tick $status.wsl.running) running" -ForegroundColor (Col $status.wsl.running)

Write-Host ""
Write-Host "Ollama daemon     $(Tick $status.ollama.daemon_up) on 127.0.0.1:11434" -ForegroundColor (Col $status.ollama.daemon_up)
if ($status.ollama.daemon_up) {
    Write-Host "  models loaded:   $($status.ollama.models.Count) total, $($status.ollama.nemotron_count) Nemotron" -ForegroundColor Cyan
    $status.ollama.models | ForEach-Object {
        $tag = if ($_.name -match "nemotron") { "* " } else { "  " }
        Write-Host "    $tag$($_.name)  ($($_.size_gb) GB)" -ForegroundColor Gray
    }
}

Write-Host ""
$nemoOk = $status.nemoclaw.running
Write-Host "NemoClaw sandbox  $(Tick $nemoOk) $($status.nemoclaw.container_status)" -ForegroundColor (Col $nemoOk)

Write-Host ""
Write-Host "OpenShell gateway $(Tick ($status.openshell.listening.Count -gt 0)) $($status.openshell.listening.Count) port(s)" -ForegroundColor (Col ($status.openshell.listening.Count -gt 0))
$status.openshell.listening | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray }

Write-Host ""
$deskOk = $status.mission_desk.instances.Count -gt 0
Write-Host "Mission Desk      $(Tick $deskOk) $($status.mission_desk.instances.Count) instance(s)" -ForegroundColor (Col $deskOk)
$status.mission_desk.instances | ForEach-Object {
    Write-Host "    PID $($_.pid) port $($_.port) mode=$($_.mode) calls=$($_.live_calls) uptime=$($_.uptime_s)s" -ForegroundColor Gray
}

Write-Host ""
Write-Host "Disk usage" -ForegroundColor Cyan
Write-Host "  Ollama models:   $($status.disk.ollama_models_gb) GB (WSL)" -ForegroundColor Gray
Write-Host "  Audit log:       $($status.disk.data_audit_kb) KB" -ForegroundColor Gray

Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
