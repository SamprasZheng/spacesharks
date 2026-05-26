"""tests/test_cots_kb_schema.py — NEO Action Item 1 schema verification.

Tests that:
  - build_kb produces a valid payload with no schema issues
  - the payload has >= 50 entries (cut-list floor from the plan)
  - at least one entry per (failure_mode ∈ {tid, see, dielectric_charge}, regime=LEO)
  - the built JSON on disk validates against the same schema
  - AI#3's kb_retrieval picks up the primary JSON when it lands
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from desk.knowledge.build_cots_kb import build_kb  # noqa: E402
from desk.knowledge.schema import validate_kb_payload  # noqa: E402


def test_build_kb_produces_valid_payload():
    payload = build_kb(seed_only=True)
    ok, issues, summary = validate_kb_payload(payload)
    assert ok, f"schema issues:\n" + "\n".join(f"  - {i.entry_id}.{i.field}: {i.error}" for i in issues[:20])
    assert summary["unique_ids"] == summary["total_entries"], "duplicate entry_ids present"


def test_payload_meets_cut_list_floor():
    payload = build_kb(seed_only=True)
    n = payload["entry_count"]
    assert n >= 50, f"cut-list floor is 50 entries; got {n}"


def test_required_failure_modes_present_for_leo():
    payload = build_kb(seed_only=True)
    seen = {(e["failure_mode"], e["regime"]) for e in payload["entries"]}
    for mode in ("tid", "see", "dielectric_charge"):
        assert (mode, "LEO") in seen, f"missing ({mode}, LEO) coverage"


def test_built_json_round_trips_through_schema(tmp_path):
    payload = build_kb(seed_only=True)
    p = tmp_path / "kb.json"
    p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    loaded = json.loads(p.read_text(encoding="utf-8"))
    ok, issues, _summary = validate_kb_payload(loaded)
    assert ok, f"round-trip issues: {[(i.entry_id, i.field, i.error) for i in issues[:10]]}"


def test_repo_kb_json_validates_if_present():
    """If `data/cots_defect_knowledge.json` exists in the repo, it must validate."""
    p = _REPO_ROOT / "data" / "cots_defect_knowledge.json"
    if not p.exists():
        return  # AI#1 not yet run — skip silently
    loaded = json.loads(p.read_text(encoding="utf-8"))
    ok, issues, summary = validate_kb_payload(loaded)
    assert ok, f"on-disk KB has issues: {[(i.entry_id, i.field, i.error) for i in issues[:10]]}"
    assert summary["unique_ids"] == summary["total_entries"]
    # When the on-disk JSON exists, AI#3's kb_retrieval should prefer it.
    from desk.decisions.kb_retrieval import kb_load, _KB_CACHE  # noqa: F401
    import desk.decisions.kb_retrieval as kr
    kr._KB_CACHE = None  # invalidate the cache for this test
    entries, source = kb_load()
    assert source == "primary", f"expected primary source, got {source}"
    assert len(entries) == summary["total_entries"]
