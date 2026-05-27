---
name: spacesharks-demo
description: >
  Run the complete Spacesharks hackathon demo sequence — boots the stack,
  warms SWPC + first Nemotron Tactical Brief, triggers an X-class flare,
  injects an SEE anomaly on STRLNK-1007, drafts a beam-redirect to Taipei
  (real Nemotron-Nano-4B call), opens the dashboard, captures a full-screen
  screenshot, and either tears down or keeps running. Use this for a
  recorded demo or submission video. Trigger phrases: "run the demo",
  "demo spacesharks", "hackathon demo", "錄 demo", "跑展示".
---

# /spacesharks-demo

Single-command end-to-end demo. Boots the stack, exercises every NEO Action
Item, captures the dashboard, and (optionally) tears down. Designed for
recording a submission video.

## How to invoke

Full demo + auto-shutdown after 10s:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:/DOT/spacesharks/scripts/spacesharks-demo.ps1
```

Full demo + keep running for live review:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:/DOT/spacesharks/scripts/spacesharks-demo.ps1 -KeepRunning
```

Custom port:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:/DOT/spacesharks/scripts/spacesharks-demo.ps1 -Port 8788
```

## Demo sequence

1. **Boot** — calls `spacesharks-up.ps1 -SkipBrowser` to start Ollama +
   NemoClaw + server.py headless
2. **Warm up 60s** — lets SWPC poller complete first fetch and Nemotron
   Tactical Brief generate its first 60s-cached output
3. **Trigger flare** — `POST /api/storm` with `{"kind":"flare"}` (also fires
   `BUS.copilot("nemoclaw", "...solar flare...")` audit row)
4. **Inject SEE anomaly** — `POST /api/dev/inject-anomaly` on STRLNK-1007
   (NORAD 44737); JPL detector picks it up within ~2s
5. **Draft beam-redirect to Taipei** — `POST /api/decisions/beam-redirect/draft`
   targeting (24.0, 121.5). Real Nemotron call generates the justification.
   Reports llm_source, latency_ms, eval_count.
6. **Open dashboard + screenshot** — saves to
   `D:/DOT/spacesharks/screenshots/demo-<timestamp>.png`
7. **Teardown** — unless `-KeepRunning`, runs `spacesharks-down.ps1`
   after 10s grace period

## What gets demonstrated

Every NEO Action Item fires at least once:

- **AI#4** NemoClaw audit dispatch (the storm + injection + draft each write
  an audit row with SHA-256 policy_preset_hash)
- **AI#2** SGP4 + JPL detector + COTS telemetry (the SEE injection trips
  the detector)
- **AI#3** Function Calling beam-redirect draft (the Nemotron-generated
  justification + KB citations + decision_route=needs-review)
- **AI#1** COTS defect KB (the draft cites entries from `cots_defect_knowledge.json`)
- **NEO Tactical Brief** (real Nemotron exec summary cached for 60s)
- **Live SWPC** (Kp/X-ray/SEP visible in the snapshot)
- **Live Celestrak** (15,441 TLEs already cached)
- **Wiki RAG** (Nemotron prompt enriched with top-3 wiki pages)

## When to use a different approach

- Just need a screenshot of current state? Use `/spacesharks-status` or
  open the dashboard manually
- Just need the verification matrix? Use `/spacesharks-verify`
- Want to script your own demo flow? Copy `spacesharks-demo.ps1` as a
  template and rearrange the `Invoke-RestMethod` calls
