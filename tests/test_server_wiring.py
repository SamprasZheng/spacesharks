"""tests/test_server_wiring.py — end-to-end checks for AI#4's server.py changes.

Tests that the Bus.copilot wiring closes review2.md's #1 critique:
  - calling BUS.copilot writes an audit row (not return None)
  - the row carries audit_log_id and policy_preset_hash
  - the row is visible via audit_tail (drives /api/audit/last10)
  - extra kwargs land on the row (action, sat_id, who_label, etc.)
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from desk.nemoclaw.audit_log import audit_clear_tail_for_tests  # noqa: E402


def test_bus_copilot_writes_audit_row(tmp_path, monkeypatch):
    import desk.nemoclaw.audit_log as audit_log
    monkeypatch.setattr(audit_log, "_DATA_DIR", tmp_path / "audit")
    monkeypatch.setattr(audit_log, "_OFFLINE_DIR", tmp_path / "audit" / "offline-batches")
    audit_clear_tail_for_tests()

    import desk.server as server

    # Bus.copilot used to be a no-op (return None). Post-AI#4 it writes audit rows.
    server.BUS.copilot("nemoclaw", "AI#4 wiring smoke test",
                       severity="INFO", action="WIRING_CHECK", sat_id="44737")

    tail = audit_log.audit_tail(10)
    assert len(tail) >= 1
    row = tail[-1]
    assert row["who"] == "nemoclaw"
    assert row["msg"] == "AI#4 wiring smoke test"
    assert row["severity"] == "INFO"
    assert row["action"] == "WIRING_CHECK"
    assert row["sat_id"] == "44737"
    assert row["audit_log_id"].startswith("nemoclaw-")
    assert row["policy_preset_hash"].startswith("sha256:")


def test_bus_copilot_log_deque_receives_row(tmp_path, monkeypatch):
    import desk.nemoclaw.audit_log as audit_log
    monkeypatch.setattr(audit_log, "_DATA_DIR", tmp_path / "audit")
    monkeypatch.setattr(audit_log, "_OFFLINE_DIR", tmp_path / "audit" / "offline-batches")
    audit_clear_tail_for_tests()

    import desk.server as server
    bus = server.BUS

    before = len(bus.copilot_log)
    bus.copilot("user", "approve recommendation", who_label="Sampras")
    after = len(bus.copilot_log)

    assert after == before + 1, "copilot_log deque should mirror audit_dispatch"
    assert bus.copilot_log[-1]["who"] == "user"
    assert bus.copilot_log[-1]["who_label"] == "Sampras"


def test_primary_models_are_nemotron_heavy():
    import desk.server as server
    vendors = [m["vendor"] for m in server.PRIMARY_MODELS]
    nemotron_count = sum(1 for v in vendors if v == "NVIDIA")
    families = set(m["family"].split("-")[0] for m in server.PRIMARY_MODELS)

    # review2.md §"PRIMARY_MODELS aren't Nemotron" critique — fix slice:
    assert nemotron_count >= 3, f"NEO needs >= 3 Nemotron specialists for Airtable form, got {nemotron_count}"

    # INVARIANTS.md §"Specialist-arbiter rule" — distinct base-model families.
    # Family-prefix dedup: "Nemotron-3-Nano" and "Nemotron-3-Super" share prefix.
    family_prefixes = set(m["family"].split("-")[0] for m in server.PRIMARY_MODELS)
    assert len(family_prefixes) >= 3, f"need >= 3 base families, got {family_prefixes}"

    # MISSION_DIRECTOR must be Nemotron per hackathon rules.
    assert server.MISSION_DIRECTOR["vendor"] == "NVIDIA"
    assert "Nemotron" in server.MISSION_DIRECTOR["family"]


def test_gpu_pressure_check_returns_tier():
    import desk.server as server
    tier, pct = server._gpu_pressure_check()
    assert tier in ("OK", "WARM", "HOT", "CRITICAL", "UNKNOWN")
    if tier != "UNKNOWN":
        assert isinstance(pct, float)


def test_gpu_pressure_react_warm_shrinks_council(tmp_path, monkeypatch):
    """Force WARM tier — council mode must step from FULL to BALANCED."""
    import desk.nemoclaw.audit_log as audit_log
    monkeypatch.setattr(audit_log, "_DATA_DIR", tmp_path / "audit")
    monkeypatch.setattr(audit_log, "_OFFLINE_DIR", tmp_path / "audit" / "offline-batches")
    audit_clear_tail_for_tests()

    import desk.server as server
    server.INFERENCE["council_mode"] = "FULL"

    result = server._gpu_pressure_react("WARM", 82.0)

    assert result["taken"] == "shrink_council:FULL->BALANCED"
    assert server.INFERENCE["council_mode"] == "BALANCED"


def test_gpu_pressure_react_critical_logs_offload_intent(tmp_path, monkeypatch):
    import desk.nemoclaw.audit_log as audit_log
    monkeypatch.setattr(audit_log, "_DATA_DIR", tmp_path / "audit")
    monkeypatch.setattr(audit_log, "_OFFLINE_DIR", tmp_path / "audit" / "offline-batches")
    audit_clear_tail_for_tests()

    import desk.server as server
    before_gated = server.INFERENCE.get("vram_gated_count", 0)

    result = server._gpu_pressure_react("CRITICAL", 95.0)

    assert result["taken"] == "block_and_offload_intent"
    assert server.INFERENCE["vram_gated_count"] == before_gated + 1

    # Audit row must record the CRITICAL event.
    tail = audit_log.audit_tail(10)
    last = tail[-1]
    assert last["action"] == "VRAM_OFFLOAD_INTENT"
    assert last["severity"] == "HIGH"
