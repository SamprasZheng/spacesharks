---
name: spacesharks-verify
description: >
  Health-check the Spacesharks Mission Desk end-to-end — runs pytest (44
  tests), probes the Ollama daemon for a Nemotron model, hits all NEO
  endpoints (/api/state, /api/neo/tactical-brief, /api/neo/at-risk,
  /api/neo/space-weather-forecast, /api/neo/where-needs-starlink,
  /api/neo/wiki/stats, /api/audit/policy-hash), and reports pass/fail.
  Use to confirm a fresh boot is fully working or before a demo. Trigger
  phrases: "verify spacesharks", "health check", "smoke test", "validate
  the desk", "is everything working", "確認系統正常", "驗證所有功能".
---

# /spacesharks-verify

End-to-end health check. Should be run after `/spacesharks-up` to confirm
every NEO Action-Item endpoint is responding correctly.

## How to invoke

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:/DOT/spacesharks/scripts/spacesharks-verify.ps1 -Port 8780
```

Exits with `0` if all checks pass, non-zero count of failures otherwise.

## What it checks (9 sections, ~15 individual checks)

1. **pytest** — full 44-test suite green
2. **Ollama daemon** — reachable on 11434, at least one Nemotron model loaded
3. **Mission Desk server.py** — `/api/state` responds, mode=LIVE-OLLAMA,
   weather.source=swpc-live, fleet ≥ 50 sats
4. **SWPC forecast** — `/api/neo/space-weather-forecast` returns the 3-day
   forecast text + active alerts list
5. **Disaster feed** — `/api/neo/where-needs-starlink` returns USGS + EONET
   + GDACS events
6. **At-risk ranking** — `/api/neo/at-risk` returns ranked sats + band summary
7. **Tactical brief** — `/api/neo/tactical-brief` returns text with source=llm
   (not template fallback)
8. **Wiki RAG** — `/api/neo/wiki/stats` returns n_docs > 0
9. **NemoClaw policy** — `/api/audit/policy-hash` returns a valid SHA-256

## Output

```
SPACESHARKS · VERIFY (port 8780)

1. pytest suite...
  ✓ pytest passed
    44 passed in 0.41s

2. local Nemotron via Ollama...
  ✓ Ollama daemon reachable
  ✓ Nemotron model present

3. Mission Desk server.py...
  ✓ /api/state responds
  ✓ LIVE-OLLAMA mode
  ✓ SWPC live data (not simulated)
  ✓ fleet has >= 50 sats
    Kp=2.0  X-ray=B9.6  SEP=1.6 pfu
    live_calls=52 director_calls=10

...

VERIFY: ALL GREEN  (15 checks passed)
```

## When to use a different approach

- To test ONE specific endpoint quickly:
  `curl -s http://127.0.0.1:8780/api/neo/<endpoint>`
- To debug an LLM call: hit `/api/neo/tactical-brief` directly and check
  the `latency_ms` and `eval_count` fields
- To run pytest in isolation: `cd D:/DOT/spacesharks && python -m pytest tests/ -v`
