# spacesharks-demo.ps1 -- full hackathon demo sequence
#
# Boots the stack, triggers a flare + manual anomaly, drafts a beam-redirect,
# screenshots, then optionally tears down. Designed to be runnable as a single
# command for a recorded demo.
#
# Usage:
#   .\scripts\spacesharks-demo.ps1
#   .\scripts\spacesharks-demo.ps1 -KeepRunning   # leave server up after demo
#   .\scripts\spacesharks-demo.ps1 -Port 8788

[CmdletBinding()]
param(
    [int]$Port = 8780,
    [switch]$KeepRunning,
    [string]$ScreenshotDir = $null
)

$ErrorActionPreference = "Continue"
$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $ScreenshotDir) { $ScreenshotDir = Join-Path $RepoRoot "screenshots" }
New-Item -ItemType Directory -Path $ScreenshotDir -Force | Out-Null

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host " SPACESHARKS - DEMO SEQUENCE" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan

# 1. Boot
& "$PSScriptRoot\spacesharks-up.ps1" -Port $Port -SkipBrowser

# 2. Wait a little for SWPC + telemetry + first tactical brief
Write-Host ""
Write-Host "warming up (60s) for first SWPC poll + Nemotron brief..." -ForegroundColor Yellow
Start-Sleep -Seconds 60

# 3. Trigger storm
Write-Host ""
Write-Host "-> triggering X-class flare..." -ForegroundColor Yellow
Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/storm" -Method Post -Body '{"kind":"flare"}' -ContentType "application/json" -TimeoutSec 5 | Out-Null

# 4. Inject COTS anomaly on a real sat
Write-Host "-> injecting SEE anomaly on STRLNK-1007 (44737)..." -ForegroundColor Yellow
Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/dev/inject-anomaly" -Method Post -Body '{"sat":"44737","kind":"see"}' -ContentType "application/json" -TimeoutSec 5 | Out-Null

# 5. Manual beam-redirect draft to Taipei
Write-Host "-> drafting beam-redirect to Taipei (real Nemotron call)..." -ForegroundColor Yellow
$draft = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/decisions/beam-redirect/draft" `
    -Method Post -ContentType "application/json" `
    -Body '{"sat":"25544","target_lat":24.0,"target_lon":121.5,"regime":"see","incident_summary":"Taipei demo target"}' `
    -TimeoutSec 60
Write-Host "    draft sat=$($draft.sat_id) tilt=$($draft.tilt_deg)° dur=$($draft.duration_s)s route=$($draft.decision_route)" -ForegroundColor Gray
Write-Host "    llm_source=$($draft.llm_source) latency=$($draft.llm_latency_ms)ms" -ForegroundColor Gray

# 6. Capture screenshot
Write-Host ""
Write-Host "-> opening dashboard + capturing screenshot..." -ForegroundColor Yellow
Start-Process "http://127.0.0.1:$Port/"
Start-Sleep -Seconds 6
$ts = Get-Date -Format "yyyy-MM-dd_HHmmss"
$shot = Join-Path $ScreenshotDir "demo-$ts.png"
Add-Type -AssemblyName System.Windows.Forms,System.Drawing
$screens = [System.Windows.Forms.Screen]::AllScreens
$all = New-Object System.Drawing.Rectangle 0,0,0,0
foreach ($s in $screens) { $all = [System.Drawing.Rectangle]::Union($all, $s.Bounds) }
$bmp = New-Object System.Drawing.Bitmap $all.Width, $all.Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($all.Location, [System.Drawing.Point]::Empty, $all.Size)
$bmp.Save($shot)
$bmp.Dispose(); $g.Dispose()
Write-Host "    saved $shot" -ForegroundColor Green

# 7. Print summary
Write-Host ""
Write-Host "=== DEMO COMPLETE ===" -ForegroundColor Cyan
Write-Host "  dashboard:   http://127.0.0.1:$Port/" -ForegroundColor White
Write-Host "  draft queue: http://127.0.0.1:$Port/api/decisions/beam-redirect/queue" -ForegroundColor White
Write-Host "  audit tail:  http://127.0.0.1:$Port/api/audit/last10" -ForegroundColor White
Write-Host "  screenshot:  $shot" -ForegroundColor White

if (-not $KeepRunning) {
    Write-Host ""
    Write-Host "  (run with -KeepRunning to leave server up)" -ForegroundColor DarkGray
    Write-Host "  shutting down in 10s -- Ctrl+C to abort..." -ForegroundColor Yellow
    Start-Sleep -Seconds 10
    & "$PSScriptRoot\spacesharks-down.ps1"
}
