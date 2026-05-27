---
name: spacesharks-down
description: >
  Graceful shutdown of the Spacesharks Mission Desk stack — kills all
  server.py instances, stops the Ollama daemon, stops the NemoClaw sandbox
  container without destroying its state, and releases all bound ports.
  Use this whenever the user wants to stop / shut down the satellite-ops
  dashboard. Trigger phrases: "stop spacesharks", "shut down desk",
  "kill server", "stop ollama", "spacesharks down", "turn off everything",
  "關掉 spacesharks", "關掉 server", "全部關掉", "shutdown stack".
---

# /spacesharks-down

Graceful shutdown of every Mission Desk dependency. Default behaviour:
preserve NemoClaw sandbox state (it'll restart in seconds via `recover`).

## What it does

1. Stops all `python.exe` processes running `server.py` (any port)
2. Stops the NemoClaw sandbox Docker container (does NOT `destroy`)
3. Kills any leaked `openshell-gateway` processes in WSL
4. Stops the Ollama daemon in WSL
5. Verifies the 4 critical ports are released (11434 / 18789 / 8642 / 8080)

WSL itself is left running — restarting it costs 30s and the next
`/spacesharks-up` will reuse the running distro.

## How to invoke

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:/DOT/spacesharks/scripts/spacesharks-down.ps1
```

Flags:

| Flag | Purpose |
|---|---|
| `-KeepOllama` | leave the Ollama daemon up (e.g. you have other tools using it) |
| `-DestroySandbox` | also `nemoclaw my-assistant destroy` (deletes state — next boot pulls image) |

## Output

```
SPACESHARKS · SHUTTING DOWN
[1/4] killing server.py processes... ✓ 1 stopped
[2/4] NemoClaw sandbox container...  ✓ stopped
[3/4] Ollama daemon...               ✓ stopped
[4/4] verify ports closed...         ✓ all spacesharks ports closed
```

## When to use a different approach

- To stop ONLY server.py (leave Ollama + NemoClaw running for next boot):
  `wmic process where "name='python.exe' and CommandLine like '%server.py%'" call terminate`
- To shut WSL itself down (rarely needed): `wsl --shutdown`
- To fully destroy NemoClaw state (rebuild from scratch next time):
  add `-DestroySandbox` flag.
