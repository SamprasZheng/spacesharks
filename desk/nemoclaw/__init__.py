"""desk.nemoclaw — Spacesharks Mission Desk NemoClaw guardrail and audit module.

Closes the review2.md #1 critique that `BUS.copilot` returns None. Exports:

- `audit_dispatch(who, msg, **extra)` — JSONL audit writer with audit_log_id +
  policy_preset_hash. Replaces the no-op `Bus.copilot()` body.
- `input_guard(prompt)` -> (allow, reason) — prompt-injection sanity gate.
- `output_guard(content)` -> (allow, scrubbed_content, reason) — denylist /
  destructive-command sanity gate.
- `policy_preset_hash()` -> str — SHA-256 of the active policy.yaml.
- `policy_egress_allowlist()` / `policy_tool_denylist()` -> set[str].

See `docs/research/agentic-provenance.md` Layer 4 for the audit schema and
`docs/INVARIANTS.md` §"Fail-closed invariants" for the operational rules.
"""

from desk.nemoclaw.audit_log import (
    audit_dispatch,
    audit_tail,
    policy_preset_hash,
    new_audit_log_id,
)
from desk.nemoclaw.guard import (
    input_guard,
    output_guard,
    policy_egress_allowlist,
    policy_tool_denylist,
)

__all__ = [
    "audit_dispatch",
    "audit_tail",
    "policy_preset_hash",
    "new_audit_log_id",
    "input_guard",
    "output_guard",
    "policy_egress_allowlist",
    "policy_tool_denylist",
]
