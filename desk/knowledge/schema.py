"""desk.knowledge.schema — Pydantic-shape validator (stdlib-only) for the
COTS defect knowledge JSON. Matches `desk.decisions.kb_retrieval.KBEntry`
field-for-field.

We avoid Pydantic to keep the dependency footprint identical to the rest
of `server.py` (stdlib-only). Validation surfaces field-level errors so the
test can pinpoint the offending entry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


VALID_FAILURE_MODES = {"see", "tid", "dielectric_charge"}
VALID_REGIMES = {"LEO", "MEO", "GEO", "HEO"}
VALID_COMPONENT_CLASSES = {
    "cpu", "gpu", "fpga", "memory", "power-rail", "mixed-signal",
    "sensor", "transceiver", "voltage-regulator",
}


@dataclass
class ValidationIssue:
    entry_id: str
    field: str
    error: str


@dataclass
class KBEntrySchema:
    entry_id: str
    failure_mode: str
    component_class: str
    regime: str
    question: str
    answer: str
    authority_score: float
    citations: list[dict]

    @classmethod
    def from_dict(cls, d: dict) -> "KBEntrySchema":
        return cls(
            entry_id=str(d.get("entry_id", "")),
            failure_mode=str(d.get("failure_mode", "")).lower(),
            component_class=str(d.get("component_class", "")).lower(),
            regime=str(d.get("regime", "")),
            question=str(d.get("question", "")),
            answer=str(d.get("answer", "")),
            authority_score=float(d.get("authority_score", 0.0)),
            citations=list(d.get("citations", [])),
        )

    def issues(self) -> list[ValidationIssue]:
        out: list[ValidationIssue] = []
        if not self.entry_id:
            out.append(ValidationIssue(self.entry_id, "entry_id", "missing"))
        if self.failure_mode not in VALID_FAILURE_MODES:
            out.append(ValidationIssue(self.entry_id, "failure_mode",
                                       f"not in {sorted(VALID_FAILURE_MODES)}"))
        if self.component_class not in VALID_COMPONENT_CLASSES:
            out.append(ValidationIssue(self.entry_id, "component_class",
                                       f"not in {sorted(VALID_COMPONENT_CLASSES)}"))
        if self.regime not in VALID_REGIMES:
            out.append(ValidationIssue(self.entry_id, "regime",
                                       f"not in {sorted(VALID_REGIMES)}"))
        if len(self.question) < 10:
            out.append(ValidationIssue(self.entry_id, "question", "shorter than 10 chars"))
        if len(self.answer) < 50:
            out.append(ValidationIssue(self.entry_id, "answer", "shorter than 50 chars"))
        if not (0.0 <= self.authority_score <= 1.0):
            out.append(ValidationIssue(self.entry_id, "authority_score", "not in [0, 1]"))
        if not self.citations:
            out.append(ValidationIssue(self.entry_id, "citations", "empty"))
        else:
            for i, c in enumerate(self.citations):
                if not isinstance(c, dict):
                    out.append(ValidationIssue(self.entry_id, f"citations[{i}]",
                                               "not a dict"))
                    continue
                if not c.get("title"):
                    out.append(ValidationIssue(self.entry_id, f"citations[{i}].title",
                                               "missing"))
                if not c.get("url"):
                    out.append(ValidationIssue(self.entry_id, f"citations[{i}].url",
                                               "missing"))
        return out


def validate_kb_payload(payload: dict | list) -> tuple[bool, list[ValidationIssue], dict]:
    """Validate a KB JSON payload. Returns (ok, issues, summary).

    Summary contains entry counts by (failure_mode, regime) pairs so callers
    can verify coverage matrices.
    """
    entries = payload if isinstance(payload, list) else payload.get("entries", [])
    issues: list[ValidationIssue] = []
    seen_ids: dict[str, int] = {}
    summary: dict[tuple[str, str], int] = {}

    for raw in entries:
        if not isinstance(raw, dict):
            issues.append(ValidationIssue("?", "entry", "not a dict"))
            continue
        e = KBEntrySchema.from_dict(raw)
        issues.extend(e.issues())
        if e.entry_id in seen_ids:
            issues.append(ValidationIssue(e.entry_id, "entry_id", "duplicate"))
        else:
            seen_ids[e.entry_id] = 1
        key = (e.failure_mode, e.regime)
        summary[key] = summary.get(key, 0) + 1

    ok = not issues
    return ok, issues, {
        "total_entries": len(entries),
        "unique_ids": len(seen_ids),
        "by_failure_mode_regime": {f"{m}|{r}": n for (m, r), n in summary.items()},
    }
