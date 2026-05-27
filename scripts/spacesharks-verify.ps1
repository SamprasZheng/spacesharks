# spacesharks-verify.ps1 -- health check + smoke test
#
# Runs:
#   - pytest suite
#   - Ollama probe (real Nemotron call)
#   - SWPC live data check
#   - Celestrak TLE cache check
#   - Server /api/state endpoint
#   - Wiki RAG retrieval sanity
#
# Usage:
#   .\scripts\spacesharks-verify.ps1                  # default port 8780
#   .\scripts\spacesharks-verify.ps1 -Port 8788

[CmdletBinding()]
param(
    [int]$Port = 8780,
    [string]$WslUser = "polkasharks",
    [string]$WslDistro = "Ubuntu"
)

$ErrorActionPreference = "Continue"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$pass = 0; $fail = 0
function Check($label, [scriptblock]$test) {
    try {
        $r = & $test
        if ($r) {
            Write-Host "  OK $label" -ForegroundColor Green
            $script:pass++
        } else {
            Write-Host "  FAIL $label" -ForegroundColor Red
            $script:fail++
        }
    } catch {
        Write-Host "  FAIL $label  ($($_.Exception.Message))" -ForegroundColor Red
        $script:fail++
    }
}

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host " SPACESHARKS - VERIFY (port $Port)" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan

# 1. pytest suite
Write-Host ""
Write-Host "1. pytest suite (44 tests expected)..." -ForegroundColor Yellow
Push-Location $RepoRoot
$pytestOut = & python -m pytest tests/ -q --no-header --tb=no 2>&1 | Select-Object -Last 1
Pop-Location
Check "pytest passed" { $pytestOut -match "passed" -and $pytestOut -notmatch "failed" }
Write-Host "    $pytestOut" -ForegroundColor Gray

# 2. Ollama daemon
Write-Host ""
Write-Host "2. local Nemotron via Ollama..." -ForegroundColor Yellow
$ollama = $null
try { $ollama = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 3 -ErrorAction Stop } catch {}
Check "Ollama daemon reachable" { $ollama -ne $null }
if ($ollama) {
    $hasNemotron = ($ollama.models | Where-Object { $_.name -match "nemotron" }).Count -gt 0
    Check "Nemotron model present" { $hasNemotron }
}

# 3. Server /api/state
Write-Host ""
Write-Host "3. Mission Desk server.py on port $Port..." -ForegroundColor Yellow
$state = $null
try { $state = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/state" -TimeoutSec 5 -ErrorAction Stop } catch {}
Check "/api/state responds" { $state -ne $null }
if ($state) {
    Check "LIVE-OLLAMA mode" { $state.inference.mode -eq "LIVE-OLLAMA" }
    Check "SWPC live data (not simulated)" { $state.weather.source -eq "swpc-live" -or $state.weather.source -eq "swpc-stale" }
    Check "fleet has >= 50 sats" { $state.sats.Count -ge 50 }
    Write-Host "    Kp=$($state.weather.kp)  X-ray=$($state.weather.xray_class)  SEP=$($state.weather.sep_pfu) pfu" -ForegroundColor Gray
    Write-Host "    live_calls=$($state.inference.live_calls) director_calls=$($state.inference.director_calls)" -ForegroundColor Gray
}

# 4. SWPC forecast
Write-Host ""
Write-Host "4. SWPC 3-day forecast + alerts..." -ForegroundColor Yellow
$f = $null
try { $f = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/neo/space-weather-forecast" -TimeoutSec 8 -ErrorAction Stop } catch {}
Check "forecast endpoint responds" { $f -ne $null }
if ($f) {
    Check "active alerts > 0" { @($f.alerts).Count -gt 0 }
    Write-Host "    issued $($f.forecast.issued_at)  alerts=$(@($f.alerts).Count)" -ForegroundColor Gray
}

# 5. Disaster feed
Write-Host ""
Write-Host "5. Where-needs-Starlink disaster feed..." -ForegroundColor Yellow
$d = $null
try { $d = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/neo/where-needs-starlink" -TimeoutSec 12 -ErrorAction Stop } catch {}
Check "disaster feed responds" { $d -ne $null }
if ($d) {
    Check "events > 0" { @($d.events).Count -gt 0 }
    Write-Host "    $(@($d.events).Count) events, top: $($d.events[0].headline)" -ForegroundColor Gray
}

# 6. At-risk ranking
Write-Host ""
Write-Host "6. At-risk satellite ranking..." -ForegroundColor Yellow
$r = $null
try { $r = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/neo/at-risk?n=5" -TimeoutSec 5 -ErrorAction Stop } catch {}
Check "at-risk endpoint responds" { $r -ne $null }
if ($r) {
    Check "top sats present" { @($r.top).Count -gt 0 }
    Write-Host "    bands: B=$($r.summary.bands.BLACK) R=$($r.summary.bands.RED) Y=$($r.summary.bands.YELLOW) G=$($r.summary.bands.GREEN)" -ForegroundColor Gray
}

# 7. Tactical brief (real Nemotron)
Write-Host ""
Write-Host "7. Tactical brief (real Nemotron call)..." -ForegroundColor Yellow
$tb = $null
try { $tb = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/neo/tactical-brief" -TimeoutSec 8 -ErrorAction Stop } catch {}
Check "brief endpoint responds" { $tb -ne $null }
if ($tb) {
    Check "brief source=llm (not template)" { $tb.source -eq "llm" }
    Write-Host "    latency=$($tb.latency_ms)ms eval=$($tb.eval_count) tokens" -ForegroundColor Gray
}

# 8. Wiki RAG
Write-Host ""
Write-Host "8. Wiki RAG retrieval (D:/DOT/yxz/wiki)..." -ForegroundColor Yellow
$w = $null
try { $w = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/neo/wiki/stats" -TimeoutSec 5 -ErrorAction Stop } catch {}
Check "wiki index built" { $w -ne $null -and $w.n_docs -gt 0 }
if ($w) {
    Write-Host "    $($w.n_docs) pages indexed, $($w.unique_terms) terms, build_ms=$($w.build_ms)" -ForegroundColor Gray
}

# 9. Policy hash + NemoClaw audit log
Write-Host ""
Write-Host "9. NemoClaw audit log + policy hash..." -ForegroundColor Yellow
$ph = $null
try { $ph = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/audit/policy-hash" -TimeoutSec 3 -ErrorAction Stop } catch {}
Check "policy hash returned" { $ph.policy_preset_hash -match "^sha256:" }
if ($ph) {
    Write-Host "    $($ph.policy_preset_hash.Substring(0, 40))..." -ForegroundColor Gray
}

# Summary
Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
if ($fail -eq 0) {
    Write-Host " VERIFY: ALL GREEN  ($pass checks passed)" -ForegroundColor Green
} else {
    Write-Host " VERIFY: $pass passed, $fail FAILED" -ForegroundColor Red
}
Write-Host "================================================================" -ForegroundColor Cyan
exit $fail
