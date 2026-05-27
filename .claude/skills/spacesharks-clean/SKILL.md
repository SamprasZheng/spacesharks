---
name: spacesharks-clean
description: >
  Disk audit + safe cleanup recommendations for the Spacesharks stack —
  reports Ollama model store size in WSL (often 30+ GB), per-day NemoClaw
  audit JSONL files, Celestrak TLE cache, lifecycle event log, and
  proposes specific cleanup commands (e.g. drop duplicate llama3.1:8b
  variants, drop unused qwen2.5-coder). Read-only by default; pass
  -Execute to apply. Trigger phrases: "spacesharks clean", "disk audit",
  "how much disk am I using", "電腦會不會存太多沒用的數據", "cleanup recommendations",
  "ollama model cleanup", "整理磁碟".
---

# /spacesharks-clean

Reports every place the Mission Desk writes data, computes sizes, and
proposes safe-to-execute cleanups with exact `wsl$` / `bash$` commands.

## How to invoke

Read-only audit (safe, always run first):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:/DOT/spacesharks/scripts/spacesharks-clean.ps1
```

Interactive cleanup (asks `y/N` before each recommendation):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:/DOT/spacesharks/scripts/spacesharks-clean.ps1 -Execute
```

Only the big Ollama wins (skips file-level recs):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:/DOT/spacesharks/scripts/spacesharks-clean.ps1 -Execute -OllamaOnly
```

## What it audits

| Category | Typical size | Rotation |
|---|---|---|
| Spacesharks `data/audit/` (NemoClaw audit JSONL) | < 5 MB | daily |
| Spacesharks `data/audit/offline-batches/` | < 100 KB | per-batch |
| Spacesharks `data/tle/` (Celestrak cache) | ~2.5 MB | every 6h |
| Spacesharks `data/cots_defect_knowledge.json` | 53 KB | static |
| Spacesharks `desk/data/lifecycle-events.jsonl` | grows ~2 MB/day | manual |
| `/tmp/server-*.log` | < 50 KB total | manual |
| WSL Ollama models (`~/.ollama/models/`) | **typically 30+ GB** | manual |

## Known win recommendations (this machine, 2026-05-27)

| Action | Saving | Reason |
|---|---|---|
| `ollama rm llama3.1:8b-cold && ollama rm llama3.1:8b-tight` | ~9.8 GB | duplicates of llama3.1:8b |
| `ollama rm qwen2.5-coder:7b` | ~4.7 GB | code-gen specialist, not used by the desk |

## Backed by

`desk/admin/storage_audit.py` — the Python module that walks the
directories and produces the JSON. Same module also exposed at
`GET /api/neo/storage-audit` for the dashboard's Developer tab.

## When to use a different approach

- To see live in the dashboard instead of CLI: open Developer tab on the
  running dashboard
- To clean up `data/audit/*.jsonl` older than 30 days (compress to .gz):
  `find data/audit -name '*.jsonl' -mtime +30 -exec gzip {} \;`
- To prune ALL Ollama models and re-pull only the ones the desk uses:
  `wsl ollama list | awk 'NR>1 {print $1}' | xargs -I{} wsl ollama rm {}`
  then `wsl ollama pull nemotron-3-nano:4b qwen3:4b mistral:7b`
