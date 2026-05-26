"""desk.decisions — agent decision verbs that DO things (not just classify).

NEO Action Item 3 — closes review2.md's "read-only classifier" critique by
adding Function Calling on the Nemotron-Super 49B path. The agent now drafts
*executable proposals* (beam-redirect scripts) instead of only emitting
GREEN/YELLOW/RED labels.

`decision_route` is locked to `needs-review` on every draft under INVARIANTS
override O2 — never auto-publish, never auto-execute. Approval flows through
the existing /api/approve endpoint which writes an audit_log_id-bearing row.
"""

from desk.decisions.beam_redirect import (
    BeamRedirectDraft,
    brief_beam_redirect,
    BEAM_REDIRECT_TOOL_SCHEMA,
)
from desk.decisions.kb_retrieval import kb_lookup, kb_load, KBEntry

__all__ = [
    "BeamRedirectDraft",
    "brief_beam_redirect",
    "BEAM_REDIRECT_TOOL_SCHEMA",
    "kb_lookup",
    "kb_load",
    "KBEntry",
]
