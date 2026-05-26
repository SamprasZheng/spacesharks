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
from desk.decisions.llm_justification import llm_justify_beam_redirect
from desk.decisions.tactical_brief import (
    get_tactical_brief,
    refresh_tactical_brief,
)
from desk.decisions.at_risk_ranking import (
    rank_fleet_by_risk,
    fleet_risk_summary,
    compute_sat_risk,
)

__all__ = [
    "BeamRedirectDraft",
    "brief_beam_redirect",
    "BEAM_REDIRECT_TOOL_SCHEMA",
    "kb_lookup",
    "kb_load",
    "KBEntry",
    "llm_justify_beam_redirect",
    "get_tactical_brief",
    "refresh_tactical_brief",
    "rank_fleet_by_risk",
    "fleet_risk_summary",
    "compute_sat_risk",
]
