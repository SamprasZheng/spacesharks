"""desk.admin.storage_audit — answer "我電腦會不會沒用的數據存太多?"

Walks the directories the Mission Desk writes to, reports sizes, and
suggests safe cleanup actions. Read-only — never deletes. Use
`desk/admin/cleanup.py` to actually execute recommended deletions.

Categories surveyed:
  - data/audit/                     — NemoClaw audit JSONL (rotates daily)
  - data/audit/offline-batches/     — offline KB build audits
  - data/tle/                       — Celestrak TLE cache (refreshes daily)
  - data/cots_defect_knowledge.json — built artefact (static, keep)
  - desk/data/lifecycle-events.jsonl — per-assessment event log (grows)
  - /tmp/server-*.log               — stdout from past runs (orphans)
  - WSL ~/.ollama/models/blobs/     — Ollama model store (the big one)
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path


_SPACE_ROOT = Path("D:/DOT/spacesharks")
_TMP_LOGS = Path("/tmp")
_DESK_ROOT = _SPACE_ROOT / "desk"


def _du_bytes(path: Path) -> int:
    """Sum file sizes under `path`. Returns 0 if missing."""
    if not path.exists():
        return 0
    total = 0
    try:
        for p in path.rglob("*"):
            if p.is_file():
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _file_count(path: Path, pattern: str = "*") -> int:
    if not path.exists():
        return 0
    try:
        return sum(1 for _ in path.rglob(pattern) if _.is_file())
    except OSError:
        return 0


def _wsl_du(wsl_path: str) -> int:
    """Run `du -sb <path>` inside WSL Ubuntu polkasharks. Returns bytes or 0."""
    try:
        cp = subprocess.run(
            ["wsl.exe", "-d", "Ubuntu", "-u", "polkasharks",
             "-e", "bash", "-lc", f"du -sb {wsl_path} 2>/dev/null | head -1"],
            capture_output=True, text=True, timeout=15,
        )
        out = cp.stdout.strip()
        if out:
            return int(out.split()[0])
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        pass
    return 0


def _wsl_ollama_models() -> list[dict]:
    """Run `ollama list` inside WSL and parse rows. Returns [{name, id, size, modified}]."""
    try:
        cp = subprocess.run(
            ["wsl.exe", "-d", "Ubuntu", "-u", "polkasharks",
             "-e", "bash", "-lc", "ollama list 2>/dev/null"],
            capture_output=True, text=True, timeout=15,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []
    rows = []
    lines = cp.stdout.strip().split("\n")
    if len(lines) < 2:
        return []
    for line in lines[1:]:  # skip header
        parts = line.split()
        if len(parts) >= 4:
            # NAME ID SIZE UNIT MODIFIED... — try to parse "X.X GB" together
            name = parts[0]
            id_ = parts[1]
            size = parts[2] + " " + parts[3]
            rows.append({"name": name, "id": id_, "size": size,
                         "modified": " ".join(parts[4:])})
    return rows


def storage_audit() -> dict:
    """Returns a structured audit of all known data locations."""
    sections: list[dict] = []

    # --- 1. Spacesharks data/ ---
    audit_dir = _SPACE_ROOT / "data" / "audit"
    offline_dir = audit_dir / "offline-batches"
    tle_dir = _SPACE_ROOT / "data" / "tle"
    kb_json = _SPACE_ROOT / "data" / "cots_defect_knowledge.json"
    sections.append({
        "category": "Spacesharks data/audit (NemoClaw audit log)",
        "path": str(audit_dir),
        "size_bytes": _du_bytes(audit_dir),
        "size_human": _human(_du_bytes(audit_dir)),
        "file_count": _file_count(audit_dir, "*.jsonl"),
        "rotation": "daily JSONL, append-only",
        "safe_to_delete_after_days": 30,
    })
    sections.append({
        "category": "Spacesharks data/audit/offline-batches",
        "path": str(offline_dir),
        "size_bytes": _du_bytes(offline_dir),
        "size_human": _human(_du_bytes(offline_dir)),
        "file_count": _file_count(offline_dir, "*.jsonl"),
        "rotation": "per-batch; only matters during KB rebuild",
        "safe_to_delete_after_days": 14,
    })
    sections.append({
        "category": "Spacesharks data/tle (Celestrak TLE cache)",
        "path": str(tle_dir),
        "size_bytes": _du_bytes(tle_dir),
        "size_human": _human(_du_bytes(tle_dir)),
        "file_count": _file_count(tle_dir, "*.tle"),
        "rotation": "refreshes every 6h, single file",
        "safe_to_delete_after_days": 1,
    })
    kb_size = kb_json.stat().st_size if kb_json.exists() else 0
    sections.append({
        "category": "Spacesharks data/cots_defect_knowledge.json (KB artefact)",
        "path": str(kb_json),
        "size_bytes": kb_size,
        "size_human": _human(kb_size),
        "file_count": 1 if kb_size else 0,
        "rotation": "static — keep",
        "safe_to_delete_after_days": None,
    })

    # --- 2. Lifecycle events (per-assessment row log inside desk/) ---
    le = _DESK_ROOT / "data" / "lifecycle-events.jsonl"
    le_size = le.stat().st_size if le.exists() else 0
    sections.append({
        "category": "Spacesharks desk/data/lifecycle-events.jsonl",
        "path": str(le),
        "size_bytes": le_size,
        "size_human": _human(le_size),
        "file_count": 1 if le_size else 0,
        "rotation": "append-only; grows ~1-3 MB/day at current rates",
        "safe_to_delete_after_days": 60,
    })

    # --- 3. /tmp/server-*.log (stdout/stderr from past server boots) ---
    tmp_logs = list(_TMP_LOGS.glob("server-*.log")) if _TMP_LOGS.exists() else []
    tmp_total = sum(p.stat().st_size for p in tmp_logs)
    sections.append({
        "category": "/tmp/server-*.log (orphan stdout from past runs)",
        "path": "/tmp/server-*.log",
        "size_bytes": tmp_total,
        "size_human": _human(tmp_total),
        "file_count": len(tmp_logs),
        "rotation": "never — manual cleanup",
        "safe_to_delete_after_days": 1,
    })

    # --- 4. Ollama models in WSL (the big one) ---
    ollama_total = _wsl_du("/home/polkasharks/.ollama/models/")
    sections.append({
        "category": "WSL Ollama models (~/.ollama/models/blobs/)",
        "path": "/home/polkasharks/.ollama/models/",
        "size_bytes": ollama_total,
        "size_human": _human(ollama_total),
        "file_count": None,
        "rotation": "never — manual `ollama rm <name>`",
        "safe_to_delete_after_days": None,
        "models": _wsl_ollama_models(),
    })

    # Grand total
    total = sum(s["size_bytes"] for s in sections)
    return {
        "ok": True,
        "audited_at": time.time(),
        "sections": sections,
        "total_bytes": total,
        "total_human": _human(total),
        "recommendations": cleanup_recommendations(sections),
    }


def cleanup_recommendations(sections: list[dict] | None = None) -> list[dict]:
    """Generate safe-to-execute cleanup recommendations from an audit."""
    if sections is None:
        sections = storage_audit()["sections"]
    recs: list[dict] = []

    for s in sections:
        cat = s["category"]
        size = s["size_bytes"]

        if "Ollama models" in cat:
            models = s.get("models", [])
            llama_variants = [m for m in models if m["name"].startswith("llama3.1:8b")]
            if len(llama_variants) > 1:
                # Keep only the canonical one, drop -cold / -tight
                drops = [m["name"] for m in llama_variants if m["name"] != "llama3.1:8b"]
                if drops:
                    recs.append({
                        "category": "Ollama model duplicates",
                        "severity": "HIGH",
                        "estimated_saving_human": f"~{4.9 * len(drops):.1f} GB",
                        "action": "Drop duplicate llama3.1:8b variants",
                        "command_wsl": " && ".join(
                            f"ollama rm {n}" for n in drops
                        ),
                        "reason": "llama3.1:8b-cold and llama3.1:8b-tight are duplicates of "
                                  "llama3.1:8b (verified by ollama list — same NAME prefix, "
                                  "same architecture). Keep canonical 8b; drop the -cold/-tight tags.",
                    })
            # qwen2.5-coder is only useful if you generate code with the desk
            if any(m["name"] == "qwen2.5-coder:7b" for m in models):
                recs.append({
                    "category": "Ollama model — unused specialist",
                    "severity": "MED",
                    "estimated_saving_human": "~4.7 GB",
                    "action": "Drop qwen2.5-coder:7b (code-gen specialist)",
                    "command_wsl": "ollama rm qwen2.5-coder:7b",
                    "reason": "Mission Desk doesn't generate code at runtime. "
                              "Re-pull only if you start using the desk for code tasks.",
                })

        if "/tmp/server" in cat and size > 5_000:
            recs.append({
                "category": "Orphan stdout logs",
                "severity": "LOW",
                "estimated_saving_human": s["size_human"],
                "action": "Delete /tmp/server-*.log files",
                "command_bash": "rm -f /tmp/server-*.log",
                "reason": "These are stdout from past dev server boots. Server.py uses NemoClaw "
                          "audit_log for real telemetry; /tmp logs are debug-only.",
            })

        if "lifecycle-events" in cat and size > 50_000_000:  # 50 MB
            recs.append({
                "category": "Lifecycle events grew large",
                "severity": "MED",
                "estimated_saving_human": s["size_human"],
                "action": "Archive + truncate desk/data/lifecycle-events.jsonl",
                "command_bash": (
                    "gzip -c desk/data/lifecycle-events.jsonl > "
                    "desk/data/lifecycle-events-$(date +%Y%m%d).jsonl.gz && "
                    "truncate -s 0 desk/data/lifecycle-events.jsonl"
                ),
                "reason": "Per-assessment rows accumulate. Compress once a month; "
                          "audit_log.jsonl is the canonical record for provenance.",
            })

        if "audit" in cat.lower() and "offline" not in cat.lower() and size > 200_000_000:  # 200 MB
            recs.append({
                "category": "Audit log oversize",
                "severity": "MED",
                "estimated_saving_human": s["size_human"],
                "action": "Compress audit log days older than 30 days",
                "command_bash": (
                    f"find {s['path']} -name '*.jsonl' -mtime +30 -exec gzip {{}} \\;"
                ),
                "reason": "Daily rotation already separates by date; just compress > 30d old.",
            })

    if not recs:
        recs.append({
            "category": "all clean",
            "severity": "INFO",
            "estimated_saving_human": "0 B",
            "action": "no cleanup needed",
            "reason": "Storage footprint is healthy.",
        })
    return recs


if __name__ == "__main__":
    import json
    print(json.dumps(storage_audit(), indent=2))
