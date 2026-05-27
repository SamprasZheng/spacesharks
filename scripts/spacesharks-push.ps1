# spacesharks-push.ps1 -- auto-commit + SSH push
#
# Why this exists: HTTPS push hangs on the credential helper in this env.
# This script forces the SSH remote, stages all wiki+docs+desk+scripts,
# commits with a smart message, and pushes over SSH.
#
# Usage:
#   .\scripts\spacesharks-push.ps1                       # commit + push everything
#   .\scripts\spacesharks-push.ps1 -Message "fix: X"     # custom message
#   .\scripts\spacesharks-push.ps1 -DryRun               # show what would happen

[CmdletBinding()]
param(
    [string]$Message,
    [switch]$DryRun
)

$ErrorActionPreference = "Continue"
$RepoRoot = Split-Path -Parent $PSScriptRoot

Push-Location $RepoRoot
try {
    # 1. Force SSH remote (HTTPS hangs on this machine)
    $remote = & git remote get-url origin 2>$null
    if ($remote -notmatch "^git@github") {
        Write-Host "switching origin to SSH ($remote -> git@github.com:...)" -ForegroundColor Yellow
        $sshUrl = $remote -replace "^https://github.com/", "git@github.com:"
        if (-not $DryRun) { & git remote set-url origin $sshUrl }
    }

    # 2. Show status
    Write-Host ""
    Write-Host "=== git status ===" -ForegroundColor Cyan
    $status = & git status --short
    if (-not $status) {
        Write-Host "  nothing to commit (clean working tree)" -ForegroundColor Green
    } else {
        $status | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
    }

    # 3. Build commit message
    if (-not $Message) {
        $changed = ($status -split "`n").Count
        $Message = "chore: sync $changed file(s) -- auto-commit from spacesharks-push.ps1"
    }

    # 4. Stage + commit if anything to commit
    if ($status -and -not $DryRun) {
        Write-Host ""
        Write-Host "=== staging all changes ===" -ForegroundColor Cyan
        & git add -A
        Write-Host ""
        Write-Host "=== commit ===" -ForegroundColor Cyan
        & git commit -m $Message --signoff
    } elseif ($DryRun) {
        Write-Host ""
        Write-Host "(dry-run) would commit with message: $Message" -ForegroundColor Yellow
    }

    # 5. Push over SSH
    Write-Host ""
    Write-Host "=== git push origin main (SSH) ===" -ForegroundColor Cyan
    if ($DryRun) {
        Write-Host "(dry-run) git push origin main" -ForegroundColor Yellow
        return
    }

    $proc = Start-Process -FilePath "git" -ArgumentList "push","origin","main" `
        -WorkingDirectory $RepoRoot -RedirectStandardOutput "$env:TEMP\sp-push-out.log" `
        -RedirectStandardError "$env:TEMP\sp-push-err.log" -PassThru -NoNewWindow
    $waited = $proc.WaitForExit(60000)
    if (-not $waited) {
        Write-Host "  FAIL push timed out after 60s -- killing" -ForegroundColor Red
        $proc.Kill()
        return
    }
    Get-Content "$env:TEMP\sp-push-out.log" -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
    Get-Content "$env:TEMP\sp-push-err.log" -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
    if ($proc.ExitCode -eq 0) {
        Write-Host "  OK push complete" -ForegroundColor Green
    } else {
        Write-Host "  FAIL push exit code $($proc.ExitCode)" -ForegroundColor Red
    }
} finally {
    Pop-Location
}
