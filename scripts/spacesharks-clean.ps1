# spacesharks-clean.ps1 -- disk audit + safe cleanup
#
# Calls the existing desk.admin.storage_audit module, prints the audit, and
# optionally executes the recommendations (with confirmation).
#
# Usage:
#   .\scripts\spacesharks-clean.ps1                 # audit only, no changes
#   .\scripts\spacesharks-clean.ps1 -Execute        # run recommendations
#   .\scripts\spacesharks-clean.ps1 -OllamaOnly     # only the big Ollama wins

[CmdletBinding()]
param(
    [switch]$Execute,
    [switch]$OllamaOnly,
    [string]$WslUser = "polkasharks",
    [string]$WslDistro = "Ubuntu"
)

$ErrorActionPreference = "Continue"
$RepoRoot = Split-Path -Parent $PSScriptRoot

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host " SPACESHARKS - DISK AUDIT" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan

# Run the audit (uses our existing module)
Push-Location $RepoRoot
$auditJson = & python -m desk.admin.storage_audit 2>&1
Pop-Location

# Parse JSON
try {
    $audit = $auditJson | ConvertFrom-Json -ErrorAction Stop
} catch {
    Write-Host "  FAIL failed to parse audit output:" -ForegroundColor Red
    Write-Host $auditJson -ForegroundColor Gray
    return
}

Write-Host ""
Write-Host "TOTAL ON DISK: $($audit.total_human)" -ForegroundColor Yellow
Write-Host ""

foreach ($s in $audit.sections) {
    $col = if ($s.size_bytes -gt 1GB) { "Yellow" } elseif ($s.size_bytes -gt 10MB) { "Cyan" } else { "Gray" }
    Write-Host ("  [{0,10}]  {1}" -f $s.size_human, $s.category) -ForegroundColor $col
    if ($s.models) {
        $s.models | ForEach-Object { Write-Host ("              {0,8}  {1}" -f $_.size, $_.name) -ForegroundColor DarkGray }
    }
}

Write-Host ""
Write-Host "--- CLEANUP RECOMMENDATIONS ---" -ForegroundColor Cyan
foreach ($rec in $audit.recommendations) {
    if ($rec.severity -eq "INFO") { continue }
    $col = switch ($rec.severity) { "HIGH" {"Red"} "MED" {"Yellow"} default {"Gray"} }
    Write-Host ""
    Write-Host "  [$($rec.severity)] $($rec.action)  (save $($rec.estimated_saving_human))" -ForegroundColor $col
    Write-Host "  -> $($rec.reason)" -ForegroundColor Gray
    if ($rec.command_wsl)  { Write-Host "  wsl$ $($rec.command_wsl)" -ForegroundColor DarkCyan }
    if ($rec.command_bash) { Write-Host "  bash$ $($rec.command_bash)" -ForegroundColor DarkCyan }

    if ($Execute) {
        $isOllama = $rec.category -match "Ollama"
        if ($OllamaOnly -and -not $isOllama) { continue }
        Write-Host ""
        $confirm = Read-Host "Execute? [y/N]"
        if ($confirm -eq "y" -or $confirm -eq "Y") {
            if ($rec.command_wsl) {
                Write-Host "  running in WSL..." -ForegroundColor Yellow
                wsl.exe -d $WslDistro -u $WslUser -e bash -lc $rec.command_wsl 2>&1 | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray }
                Write-Host "  OK done" -ForegroundColor Green
            } elseif ($rec.command_bash) {
                Write-Host "  running locally..." -ForegroundColor Yellow
                Invoke-Expression $rec.command_bash 2>&1 | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray }
                Write-Host "  OK done" -ForegroundColor Green
            }
        } else {
            Write-Host "  skipped" -ForegroundColor DarkGray
        }
    }
}

Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
if (-not $Execute) {
    Write-Host " (read-only audit -- re-run with -Execute to apply recommendations)" -ForegroundColor DarkGray
}
Write-Host "================================================================" -ForegroundColor Cyan
