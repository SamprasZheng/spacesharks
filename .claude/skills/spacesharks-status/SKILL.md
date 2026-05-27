---
name: spacesharks-status
description: >
  One-shot status snapshot of every Spacesharks Mission Desk component —
  WSL, Ollama daemon + loaded models (highlighting Nemotron variants),
  NemoClaw sandbox container, OpenShell gateway, all server.py instances
  with their ports and live_calls counts, and disk usage. Use whenever
  the user asks "is X running?" or wants to see what's up. Trigger
  phrases: "spacesharks status", "what's running", "status check",
  "目前狀態", "看一下", "ollama status", "is the server up", "show me what's running".
---

# /spacesharks-status

A one-page snapshot of every Mission Desk component, regardless of which
session started them. Read-only — never changes any state.

## How to invoke

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:/DOT/spacesharks/scripts/spacesharks-status.ps1
```

For machine-readable JSON output:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:/DOT/spacesharks/scripts/spacesharks-status.ps1 -Json
```

## What it shows

```
SPACESHARKS · STATUS SNAPSHOT

WSL Ubuntu        ✓ running

Ollama daemon     ✓ on 127.0.0.1:11434
  models loaded:   13 total, 1 Nemotron
    ★ nemotron-3-nano:4b  (2.8 GB)
      qwen3:4b  (2.5 GB)
      mistral:7b  (4.4 GB)
      ...

NemoClaw sandbox  ✓ Up 12 minutes

OpenShell gateway ✓ 2 port(s)
    LISTEN ... 127.0.0.1:18789 ...
    LISTEN ... 127.0.0.1:8080 ...

Mission Desk      ✓ 1 instance(s)
    PID 1610 port 8780 mode=LIVE-OLLAMA calls=143 uptime=384s

Disk usage
  Ollama models:   33.6 GB (WSL)
  Audit log:       871 KB
```

## When to use a different approach

- To see fleet/satellite state (not just service state):
  `curl http://127.0.0.1:8780/api/state`
- To see what's draining VRAM: `wsl bash -lc "nvidia-smi"`
- To see audit log volume growth over time: `curl http://127.0.0.1:8780/api/neo/storage-audit`
