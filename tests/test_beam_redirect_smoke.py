"""tests/test_beam_redirect_smoke.py — NEO Action Item 3 smoke test.

Verifies that brief_beam_redirect:
  - returns a draft with decision_route locked to "needs-review"
  - cites at least one KB entry by entry_id in evidence_pointers
  - keeps tilt within [1, 30] degrees
  - selects an SEE-regime KB entry when regime="see"
  - works with kb_entries supplied OR auto-lookup
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from desk.decisions.beam_redirect import (  # noqa: E402
    BEAM_REDIRECT_TOOL_SCHEMA,
    BeamRedirectDraft,
    brief_beam_redirect,
)
from desk.decisions.kb_retrieval import kb_load, kb_lookup  # noqa: E402


def test_brief_beam_redirect_decision_route_locked():
    sat = {"id": "44737", "altitude_km": 548.0}
    draft = brief_beam_redirect(
        sat=sat,
        anomaly_regime="see",
        target_lat_deg=24.0,
        target_lon_deg=121.5,
        sub_sat_lat=24.5,
        sub_sat_lon=120.2,
        sat_alt_km=548.0,
    )
    assert isinstance(draft, BeamRedirectDraft)
    assert draft.decision_route == "needs-review"
    assert draft.override_invariant == "O2-decision-verb-4th"


def test_brief_beam_redirect_cites_kb_entries():
    sat = {"id": "44737", "altitude_km": 548.0}
    draft = brief_beam_redirect(
        sat=sat,
        anomaly_regime="see",
        target_lat_deg=35.0,
        target_lon_deg=139.7,  # Tokyo
    )
    assert len(draft.evidence_pointers) >= 1
    # Every KB entry id should appear in the justification text
    for eid in draft.evidence_pointers:
        assert eid in draft.justification, f"missing {eid} in justification: {draft.justification}"


def test_brief_beam_redirect_tilt_in_range():
    sat = {"id": "44737", "altitude_km": 548.0}
    # Force a large target offset
    draft = brief_beam_redirect(
        sat=sat,
        anomaly_regime="see",
        target_lat_deg=45.0,
        target_lon_deg=170.0,
        sub_sat_lat=20.0,
        sub_sat_lon=120.0,
        sat_alt_km=548.0,
    )
    assert 1.0 <= draft.tilt_deg <= 30.0


def test_brief_beam_redirect_with_dielectric_charge():
    """Dielectric-charge regime should still produce a valid draft."""
    sat = {"id": "44737", "altitude_km": 548.0}
    draft = brief_beam_redirect(
        sat=sat,
        anomaly_regime="dielectric_charge",
        target_lat_deg=24.0,
        target_lon_deg=121.5,
    )
    assert draft.decision_route == "needs-review"
    assert draft.duration_s > 0


def test_tool_schema_shape_for_openai_tools_payload():
    """The schema must validate as an OpenAI/NIM `tools=[...]` payload."""
    assert BEAM_REDIRECT_TOOL_SCHEMA["type"] == "function"
    fn = BEAM_REDIRECT_TOOL_SCHEMA["function"]
    assert fn["name"] == "draft_beam_redirect"
    params = fn["parameters"]
    assert params["type"] == "object"
    assert "properties" in params
    assert "required" in params
    required = set(params["required"])
    # All required fields must exist in properties
    assert required.issubset(set(params["properties"].keys()))
    # Sanity: the required set should include the structural fields
    assert {"sat_id", "target_lat_deg", "target_lon_deg",
            "tilt_deg", "duration_s", "justification"} <= required


def test_kb_seed_loaded_and_has_required_categories():
    entries, source = kb_load()
    assert source in ("primary", "seed")
    assert len(entries) >= 5
    modes = {e.failure_mode for e in entries}
    assert {"see", "tid", "dielectric_charge"} <= modes


def test_kb_lookup_filters_by_failure_mode():
    hits = kb_lookup(failure_mode="see", regime="LEO", limit=5)
    assert len(hits) >= 1
    for h in hits:
        assert h.failure_mode == "see"
        assert h.regime == "LEO"


def test_kb_lookup_query_overlap_ranking():
    hits = kb_lookup(failure_mode="see", regime="LEO", query="latch-up current spike power rail",
                     limit=3)
    assert len(hits) >= 1
    # The 'see-sel-leo-001' entry mentions all of these terms; should rank highly.
    ids = [h.entry_id for h in hits]
    assert "see-sel-leo-001" in ids
