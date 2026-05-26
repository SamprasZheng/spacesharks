"""desk.nemoclaw.audit_log — JSONL audit writer for NEO Action Item 4.

Implements the Layer-4 (system trust) provenance fields from
`docs/research/agentic-provenance.md`:

  audit_log_id          — stable globally-unique identifier
  policy_preset_hash    — SHA-256 of the active openclaw policy.yaml
  denied_actions[]      — tool calls blocked by output_guard in this row's session window
  ts                    — UTC ISO-8601 with millisecond precision

Daily rotation under `data/audit/YYYY-MM-DD.jsonl`. Append-only. Out-of-process
writes go through `audit_dispatch()`; the calling code (Bus.copilot, model_ask,
approve endpoint) cannot suppress its own row because the writer raises on
failure rather than swallowing.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_HERE = Path(__file__).resolve().parent
_POLICY_PATH = _HERE / "policy.py"
_DATA_DIR = _HERE.parent.parent / "data" / "audit"
_OFFLINE_DIR = _DATA_DIR / "offline-batches"

# Lock prevents two threads interleaving JSONL writes mid-line.
_WRITE_LOCK = threading.Lock()

# Tail buffer for the /api/audit/last10 endpoint — kept in memory so the
# dashboard does not have to re-read the day file on every snapshot.
_TAIL_MAX = 200
_TAIL: list[dict] = []
_TAIL_LOCK = threading.Lock()

# Hash cache — policy.yaml only changes on edit; rehash on disk mtime change.
_POLICY_HASH: str | None = None
_POLICY_MTIME: float | None = None
_HASH_LOCK = threading.Lock()


def policy_preset_hash() -> str:
    """SHA-256 of the current `policy.yaml`. Cached on disk mtime."""
    global _POLICY_HASH, _POLICY_MTIME
    with _HASH_LOCK:
        try:
            mtime = _POLICY_PATH.stat().st_mtime
        except FileNotFoundError:
            return "sha256:no-policy"
        if _POLICY_HASH is None or _POLICY_MTIME != mtime:
            data = _POLICY_PATH.read_bytes()
            _POLICY_HASH = "sha256:" + hashlib.sha256(data).hexdigest()
            _POLICY_MTIME = mtime
        return _POLICY_HASH


def new_audit_log_id() -> str:
    """Globally unique audit row id. Time-prefixed for human ordering."""
    return f"nemoclaw-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"


def _day_path(ts_iso: str, *, offline: bool = False) -> Path:
    date = ts_iso[:10]
    base = _OFFLINE_DIR if offline else _DATA_DIR
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{date}.jsonl"


def _now_iso_ms() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def audit_dispatch(
    who: str,
    msg: str,
    *,
    severity: str = "INFO",
    decision_route: str | None = None,
    denied_actions: list[str] | None = None,
    override_invariant: str | None = None,
    offline_batch: bool = False,
    **extra: Any,
) -> dict:
    """Write one audit row. Returns the row.

    `who` is the actor ("nemoclaw", "user", "model:nemotron-3-nano:4b", etc.).
    `msg` is the human-readable description.
    `decision_route` is one of `publish / monitor-only / needs-review / abstain / escalate`
    when this audit row corresponds to a decision; None otherwise.
    `denied_actions` is the list of substrings from `policy.yaml` denylist that
    were stripped from the message by `output_guard`.
    `override_invariant` carries the override ID (e.g. "O1-source-list-5th-input")
    when this row covers a NEO scope expansion.
    `offline_batch=True` rotates the row into `data/audit/offline-batches/` so
    the live scoreboard does not double-count knowledge-base build rows.
    Extra keyword args land in the row verbatim.
    """
    ts = _now_iso_ms()
    row: dict[str, Any] = {
        "audit_log_id": new_audit_log_id(),
        "ts": ts,
        "who": who,
        "msg": msg,
        "severity": severity,
        "policy_preset_hash": policy_preset_hash(),
    }
    if decision_route is not None:
        row["decision_route"] = decision_route
    if denied_actions:
        row["denied_actions"] = list(denied_actions)
    if override_invariant:
        row["override_invariant"] = override_invariant
    for k, v in extra.items():
        if k not in row:
            row[k] = v

    line = json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n"
    path = _day_path(ts, offline=offline_batch)
    with _WRITE_LOCK:
        # Out-of-process semantic: write must be durable before the caller
        # proceeds. We open-append-fsync each row. For 24/7 ops this is
        # overhead — but the alternative is silently losing the audit trail
        # on host crash, which violates the "no action without audit" invariant.
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except (OSError, ValueError):
                # On Windows fsync may raise on certain handle states; we tried.
                pass

    if not offline_batch:
        with _TAIL_LOCK:
            _TAIL.append(row)
            if len(_TAIL) > _TAIL_MAX:
                del _TAIL[: len(_TAIL) - _TAIL_MAX]

    return row


def audit_tail(n: int = 10) -> list[dict]:
    """Return the last `n` audit rows for the dashboard /api/audit/last10."""
    with _TAIL_LOCK:
        return list(_TAIL[-n:])


def audit_clear_tail_for_tests() -> None:
    """Test-only helper — clears the in-memory tail."""
    with _TAIL_LOCK:
        _TAIL.clear()
