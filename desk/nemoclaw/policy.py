"""desk.nemoclaw.policy — active NemoClaw policy preset for Spacesharks.

Equivalent to the openclaw-sandbox.yaml referenced in NemoClaw documentation,
written as a Python module to (a) avoid a brittle YAML parser and (b) match the
stdlib-only discipline of server.py. Operators edit this file directly; the
audit-log records the SHA-256 of this source file as `policy_preset_hash`.

Locked by INVARIANTS.md source-list-lock (4 hosts) + NEO override O1 (5th input
is local synthetic only — no new external egress). Egress allowlist adds
integrate.api.nvidia.com for T3 cloud Nemotron-Super calls under
tiered-inference.

Edit history is itself the audit trail — change one line, the policy hash
changes, every row in `data/audit/` post-change reflects the new hash, and the
nightly re-hash verifier can detect drift.
"""

from __future__ import annotations

VERSION = "1.0.0"
PROFILE = "openclaw-orbital-hermes"

# ---------------------------------------------------------------------------
# Network egress allowlist — outbound HTTP destinations the agent may reach.
# Hosts not in this list trigger a `denied_action: egress` audit row.
# ---------------------------------------------------------------------------
EGRESS_ALLOWLIST: list[str] = [
    # INVARIANTS-locked first-version hosts (INVARIANTS.md §Source-list-lock)
    "celestrak.org",
    "swpc.noaa.gov",
    "tfr.faa.gov",
    "notams.aim.faa.gov",
    # NEO Action Item 4 — tier-3 cloud Nemotron via NIM
    "integrate.api.nvidia.com",
    "build.nvidia.com",
    # Local Ollama for T1/T2 — required for the existing _model_ask_local path
    "127.0.0.1",
    "localhost",
]

EGRESS_DENY_DEFAULT = True

# ---------------------------------------------------------------------------
# Tool / output denylist — substrings that, if present in a model output, force
# the output_guard to scrub them and mark the row `denied`. Case-insensitive.
# ---------------------------------------------------------------------------
TOOL_DENYLIST: list[str] = [
    # Destructive shell — review2.md flagged these as the demo-killers.
    "rm -rf",
    "shutdown",
    "format c:",
    "del /f",
    "mkfs",
    "dd if=",
    ":(){",            # fork bomb prefix
    # NEO-specific: voltage/power override patterns for COTS-defect scenarios.
    "voltage_override",
    "set_vdd",
    "force_power",
    "disable_protection",
]

DENYLIST_MODE = "substring"  # case-insensitive substring match

# ---------------------------------------------------------------------------
# Filesystem allowlist — directories the agent may write to.
# ---------------------------------------------------------------------------
FILESYSTEM_WRITE_ALLOWLIST: list[str] = [
    "data/",
    "logs/",
    "data/audit/",
    "data/audit/offline-batches/",
    "data/evidence-blobs/",
    "data/tle/",
]

# ---------------------------------------------------------------------------
# Approval routing — INVARIANTS publish-gate § 30-min cancel window.
# `publish` and `escalate` routes require approval_first; `beam-redirect-draft`
# (NEO Action Item 3 under override O2) is locked to needs-review.
# ---------------------------------------------------------------------------
APPROVAL_FIRST_FOR: list[str] = ["publish", "escalate"]
NEEDS_REVIEW_FOR: list[str] = ["beam-redirect-draft"]

# ---------------------------------------------------------------------------
# Audit rotation policy.
# ---------------------------------------------------------------------------
AUDIT_ROTATION = "daily"
AUDIT_PATH = "data/audit"

AUDIT_REQUIRED_FIELDS: list[str] = [
    "audit_log_id",
    "ts",
    "who",
    "msg",
    "policy_preset_hash",
]

AUDIT_OPTIONAL_FIELDS: list[str] = [
    "decision_route",
    "denied_actions",
    "override_invariant",
    "severity",
]
