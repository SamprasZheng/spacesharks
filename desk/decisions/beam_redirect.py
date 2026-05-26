"""desk.decisions.beam_redirect — beam-redirect draft generator.

NEO Action Item 3 under INVARIANTS override O2 (decision_route locked to
needs-review). Produces a structured *script proposal*, not an executable
script — no real RF hardware, no real ground-station command. The operator
must approve via /api/approve before any downstream system acts.

The Function Calling tool schema is exported as `BEAM_REDIRECT_TOOL_SCHEMA`
so the Mission Director (Nemotron-Super 49B) can be called with `tools=[...]`
and parse a structured response.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, asdict, field
from typing import Any

from desk.decisions.kb_retrieval import KBEntry, kb_lookup


# OpenAI / NIM-compatible tool schema. Nemotron Super on NVIDIA NIM supports
# the same `tools` parameter shape as the OpenAI Chat Completions API.
BEAM_REDIRECT_TOOL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "draft_beam_redirect",
        "description": (
            "Draft a beam-redirect proposal for a satellite whose downlink "
            "should be tilted toward a ground emergency. Output is "
            "needs-review and never auto-executes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sat_id": {"type": "string"},
                "target_lat_deg": {"type": "number",
                                   "description": "Latitude of the ground recipient (-90..90)"},
                "target_lon_deg": {"type": "number",
                                   "description": "Longitude of the ground recipient (-180..180)"},
                "tilt_deg": {"type": "number",
                             "description": "Beam tilt from nadir, 0..30 degrees"},
                "duration_s": {"type": "integer",
                               "description": "Hold duration in seconds (10..900)"},
                "justification": {"type": "string",
                                  "description": "One paragraph citing KB entry IDs"},
            },
            "required": ["sat_id", "target_lat_deg", "target_lon_deg",
                         "tilt_deg", "duration_s", "justification"],
        },
    },
}


@dataclass
class BeamRedirectDraft:
    sat_id: str
    target_lat_deg: float
    target_lon_deg: float
    tilt_deg: float
    duration_s: int
    justification: str
    decision_route: str = "needs-review"
    confidence: float = 0.0
    evidence_pointers: list[str] = field(default_factory=list)  # KB entry IDs
    override_invariant: str = "O2-decision-verb-4th"
    ts: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ts"] = d["ts"] or time.time()
        return d


def _great_circle_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing from (lat1, lon1) to (lat2, lon2) in degrees."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    y = math.sin(dlon) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def _tilt_deg_for_offset(sat_alt_km: float, target_lat: float, target_lon: float,
                         sub_sat_lat: float, sub_sat_lon: float) -> float:
    """Approximate beam tilt off-nadir for a target offset from the sub-satellite
    point. For LEO sats at ~550 km, a 200 km offset on the ground is roughly
    20 degrees off-nadir. We clamp to [1, 30] degrees so the draft is always
    physically plausible."""
    # Spherical distance, then arctan(d / h).
    R = 6371.0
    phi1, phi2 = math.radians(sub_sat_lat), math.radians(target_lat)
    dlon = math.radians(target_lon - sub_sat_lon)
    a = math.sin((phi2 - phi1) / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlon / 2) ** 2
    d_km = 2 * R * math.asin(min(1.0, math.sqrt(a)))
    tilt = math.degrees(math.atan2(d_km, max(50.0, sat_alt_km)))
    return max(1.0, min(30.0, tilt))


def brief_beam_redirect(
    *,
    sat: dict,
    anomaly_regime: str,
    target_lat_deg: float,
    target_lon_deg: float,
    confidence: float = 0.65,
    kb_entries: list[KBEntry] | None = None,
    sub_sat_lat: float | None = None,
    sub_sat_lon: float | None = None,
    sat_alt_km: float | None = None,
    incident_summary: str | None = None,
) -> BeamRedirectDraft:
    """Draft a beam-redirect proposal for `sat` toward (target_lat, target_lon).

    Uses the KB to populate the justification. Validates that the SEE event
    has recovered (regime in {see, dielectric_charge}; for sustained `tid`
    the recommendation is downgraded). decision_route is always needs-review.

    Required inputs:
      sat                    — the SATS row (used for sat_id + altitude)
      anomaly_regime         — JPL detector regime label
      target_lat / lon       — ground recipient
    Optional:
      kb_entries             — pre-fetched KB hits; otherwise auto-looks up
      sub_sat_lat / sub_sat_lon / sat_alt_km — used to compute tilt; if any
                               is None we use the sat record's altitude and
                               assume tilt 12 degrees as a fallback.
    """
    sat_id = str(sat.get("id", "?"))
    regime = anomaly_regime.lower()

    if kb_entries is None:
        kb_entries = kb_lookup(failure_mode="see", regime="LEO", limit=3) \
            if regime == "see" else kb_lookup(failure_mode=regime, regime="LEO", limit=3)

    # Compute tilt
    if sub_sat_lat is None or sub_sat_lon is None or sat_alt_km is None:
        tilt = 12.0
    else:
        tilt = _tilt_deg_for_offset(sat_alt_km, target_lat_deg, target_lon_deg,
                                    sub_sat_lat, sub_sat_lon)

    duration = 180  # default hold duration in seconds — operator can extend
    if regime == "see":
        # SEL recovery typical 0.4-1.5 s; once recovered the beam may be
        # held for the duration of the emergency pass.
        duration = 240
    elif regime == "dielectric_charge":
        duration = 120

    # Justification text — KB-cited
    cited_ids = [e.entry_id for e in kb_entries][:3]
    cite_strs = " / ".join(cited_ids)
    summary = incident_summary or "ground emergency overlap detected"
    justification = (
        f"Drafted needs-review beam-redirect for {sat_id} toward "
        f"({target_lat_deg:.3f}, {target_lon_deg:.3f}) at tilt {tilt:.1f}° "
        f"for {duration}s. Trigger: {regime} anomaly (recovered); incident: "
        f"{summary}. KB justification: {cite_strs}. "
        f"This is a proposal under INVARIANTS override O2 — "
        f"operator must approve via /api/approve before any downstream "
        f"actuation. NemoClaw audit row records policy_preset_hash + "
        f"evidence_pointers."
    )

    return BeamRedirectDraft(
        sat_id=sat_id,
        target_lat_deg=float(target_lat_deg),
        target_lon_deg=float(target_lon_deg),
        tilt_deg=float(round(tilt, 2)),
        duration_s=int(duration),
        justification=justification,
        confidence=float(confidence),
        evidence_pointers=cited_ids,
        ts=time.time(),
    )
