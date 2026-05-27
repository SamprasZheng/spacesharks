# scripts/

Day-to-day operator scripts for the Spacesharks Mission Desk. Each one is a
standalone PowerShell script that does the orchestration; the matching Claude
Skills under `.claude/skills/` are thin wrappers that trigger them by natural
language.

## Quick reference

| Script | Skill | What |
|---|---|---|
| `spacesharks-up.ps1` | `/spacesharks-up` | Boot WSL + Ollama + NemoClaw + server + open browser |
| `spacesharks-down.ps1` | `/spacesharks-down` | Graceful shutdown, preserve NemoClaw state |
| `spacesharks-status.ps1` | `/spacesharks-status` | One-shot status of every component |
| `spacesharks-verify.ps1` | `/spacesharks-verify` | pytest + endpoint health checks |
| `spacesharks-clean.ps1` | `/spacesharks-clean` | Disk audit + cleanup recommendations |
| `spacesharks-push.ps1` | `/spacesharks-push` | Auto-commit + SSH push (HTTPS hangs) |
| `spacesharks-demo.ps1` | `/spacesharks-demo` | Full demo sequence + screenshot |

## Quick start (PowerShell)

```powershell
cd D:\DOT\spacesharks
.\scripts\spacesharks-up.ps1          # boot everything
.\scripts\spacesharks-verify.ps1      # confirm green
# ... do stuff ...
.\scripts\spacesharks-down.ps1        # shutdown
```

## Quick start (from any Claude Code session in this repo)

The skills are auto-discovered from `.claude/skills/`. Just say:

- "start spacesharks" → `/spacesharks-up`
- "status check" → `/spacesharks-status`
- "verify everything works" → `/spacesharks-verify`
- "disk audit" → `/spacesharks-clean`
- "commit and push" → `/spacesharks-push`
- "run the demo" → `/spacesharks-demo`
- "shut down spacesharks" → `/spacesharks-down`

## How the stack lives on disk

```
Windows host
├── D:/DOT/spacesharks/desk/server.py        ← Mission Desk Python server
├── D:/DOT/spacesharks/data/                 ← audit logs, TLE cache, KB
└── D:/DOT/spacesharks/scripts/              ← these scripts

WSL Ubuntu (user: polkasharks)
├── /home/polkasharks/.local/bin/ollama       ← Ollama runtime
├── /home/polkasharks/.ollama/models/         ← model store (~30 GB)
├── /home/polkasharks/.local/bin/nemoclaw     ← Node CLI
├── /home/polkasharks/.local/bin/openshell    ← sandbox runtime
├── /home/polkasharks/.local/bin/openshell-gateway
├── /home/polkasharks/.nemoclaw/              ← sandbox config + state
└── Docker container: openshell-my-assistant-...
```

## Ports we use

| Port | Service |
|---|---|
| 8780 (default) | Mission Desk server.py — dashboard + API |
| 11434 | Ollama daemon (in WSL, mirrored to Windows localhost) |
| 18789 | OpenShell SSH proxy to NemoClaw sandbox |
| 8080 | OpenShell gateway HTTP |
| 8642 | (reserved — sandbox-internal NemoClaw API) |
| 44301 | (Ollama inside the sandbox container) |

## Cost guarantee

All scripts use 100 % local services:

- Ollama runs on the local RTX 5070
- NemoClaw / OpenShell are local binaries
- Only outbound HTTP is to **free public feeds** (celestrak.org,
  swpc.noaa.gov, earthquake.usgs.gov, eonet.gsfc.nasa.gov, gdacs.org)
- `NVIDIA_API_KEY` is intentionally unset — the cloud NIM tier-3 path is
  wired but never invoked (verify with `/spacesharks-status` — should show
  `0 NIM calls`)
