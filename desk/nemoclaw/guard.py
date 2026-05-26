"""desk.nemoclaw.guard — input + output guardrails for NEO Action Item 4.

`input_guard(prompt) -> (allow, reason)` — prompt-injection gate. Scans the
prompt for known injection patterns (rule overrides, system-instruction
hijacking, label coercion). Used by `_model_ask_local` and `_model_ask_cloud`
before any model call.

`output_guard(content) -> (allow, scrubbed, reason)` — model-output gate. Scans
the LLM response for destructive shell commands and policy-denied patterns from
`desk.nemoclaw.policy`. Used by every model-output consumer and by the
`/api/approve` endpoint before promoting a draft to a real action.

Policy is imported from `desk.nemoclaw.policy` (Python module — eliminates the
YAML parser fragility for the hackathon timeline). The audit log records the
policy_preset_hash so a hash mismatch between commit-time and demo-time is
detectable. Edit `policy.py` to change the denylist; restart the server.
"""

from __future__ import annotations

import importlib
import re
from typing import Tuple

from desk.nemoclaw import policy as _policy_module


def reload_policy() -> None:
    """Re-import the policy module at runtime. Audit hash will update on the
    next dispatch because audit_log re-stats the policy.py mtime."""
    importlib.reload(_policy_module)


def policy_egress_allowlist() -> set[str]:
    return set(_policy_module.EGRESS_ALLOWLIST)


def policy_tool_denylist() -> list[str]:
    return list(_policy_module.TOOL_DENYLIST)


# Prompt-injection patterns we look for at input_guard.
# Conservative — these are common phrases in published injection demos and
# rarely appear in legitimate satellite-ops prompts.
_INJECTION_PATTERNS = [
    re.compile(r"\bignore\s+previous\s+(?:rules|instructions)\b", re.IGNORECASE),
    re.compile(r"\bdisregard\s+(?:the\s+)?system\s+prompt\b", re.IGNORECASE),
    re.compile(r"\boutput\s+(?:BLACK|RED)\s+immediately\b", re.IGNORECASE),
    re.compile(r"\bact\s+as\s+(?:if\s+you\s+were\s+)?(?:an?|the)\s+", re.IGNORECASE),
    re.compile(r"</?system>", re.IGNORECASE),
    re.compile(r"\bsudo\s+", re.IGNORECASE),
]


def input_guard(prompt: str) -> Tuple[bool, str]:
    """Returns (allow, reason). Conservative on prompt-injection patterns."""
    if not isinstance(prompt, str):
        return False, "input_guard: prompt is not a string"
    if len(prompt) > 32_000:
        return False, f"input_guard: prompt exceeds 32k characters ({len(prompt)})"
    for pat in _INJECTION_PATTERNS:
        m = pat.search(prompt)
        if m:
            return False, f"input_guard: injection pattern matched ({pat.pattern!r}) at offset {m.start()}"
    return True, ""


def output_guard(content: str) -> Tuple[bool, str, list[str]]:
    """Returns (allow, scrubbed_content, denied_substrings).

    `allow=False` when ANY denylist substring matches case-insensitively.
    `scrubbed_content` is `content` with every matched substring replaced by
    `[BLOCKED]`. `denied_substrings` lists the matched substrings (for the
    audit row's `denied_actions` field).
    """
    if not isinstance(content, str):
        return False, "", ["output_guard: content is not a string"]
    denied: list[str] = []
    scrubbed = content
    lc = content.lower()
    for term in policy_tool_denylist():
        if term.lower() in lc:
            denied.append(term)
            # case-insensitive substring replace
            pat = re.compile(re.escape(term), re.IGNORECASE)
            scrubbed = pat.sub("[BLOCKED]", scrubbed)
            lc = scrubbed.lower()
    return (not denied), scrubbed, denied
