---
name: spacesharks-up
description: >
  Boot the full Spacesharks Mission Desk stack — WSL Ubuntu, Ollama daemon
  on RTX 5070, NemoClaw sandbox container, and the Python Mission Desk
  server.py — then open the dashboard. Use this whenever the user wants
  to start the local satellite-ops dashboard. Trigger phrases:
  "start spacesharks", "boot the desk", "start the dashboard", "boot ollama",
  "spacesharks up", "啟動 spacesharks", "打開 server", "打開 dashboard",
  "啟動 ollama 跟 nemoclaw", "start the demo stack".
---

# /spacesharks-up

Boot the entire Spacesharks Mission Desk stack in one command. Replaces the
manual sequence of starting WSL → Ollama → NemoClaw → server.py → opening
browser.

## What it does

1. Confirms WSL Ubuntu is running (starts it if not)
2. Starts the Ollama daemon inside WSL if not already serving on 11434
3. Waits up to 30s for `/api/tags` to confirm Ollama is healthy
4. Recovers the NemoClaw sandbox container if it's exited
5. Boots `desk/server.py` on the requested port (default 8780)
6. Waits for `/api/state` to confirm the server is responding
7. Opens the dashboard in the default browser

## How to invoke

Run the wrapping PowerShell script directly — it does all the orchestration
including error handling and health probes:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:/DOT/spacesharks/scripts/spacesharks-up.ps1
```

Options the script accepts:

| Flag | Purpose |
|---|---|
| `-Port 8788` | use a non-default port (default 8780) |
| `-SkipSandbox` | don't touch NemoClaw — just Ollama + server |
| `-SkipBrowser` | don't auto-open the dashboard |

## Output the user will see

Coloured status lines per step, each marked ✓ (green) or ✗ (red):

```
SPACESHARKS MISSION DESK · BOOTING
[1/5] WSL Ubuntu status...     ✓ running
[2/5] Ollama daemon...         ✓ LIVE on 127.0.0.1:11434
                               ✓ 13 models loaded
                                 · nemotron-3-nano:4b (Nemotron)
[3/5] NemoClaw sandbox...      ✓ already running
[4/5] Mission Desk server.py.. ✓ Mission Desk LIVE  mode=LIVE-OLLAMA
[5/5] Dashboard URL:           http://127.0.0.1:8780/
```

## When to use a different approach

- If only Ollama is needed (no dashboard) → just `wsl bash -lc "ollama serve &"`
- If only the server is needed (Ollama already running) →
  `cd desk && python server.py --port 8780`
- If you want to debug a startup failure, run the script and inspect
  `$env:TEMP\spacesharks-server-<port>.log` for the server stdout/stderr.

## What it does NOT do

- Does not pull any new models. If `nemotron-3-nano:4b` isn't pulled the
  server falls back to SIM mode. Pull with: `wsl ollama pull nemotron-3-nano:4b`.
- Does not run pytest — use `/spacesharks-verify` for that.
- Does not commit or push — use `/spacesharks-push` for that.
- Does not configure NVIDIA_API_KEY for NIM cloud (keeps the $0-cloud
  guarantee). Set the env var manually if you ever want tier-3 cloud calls.
