"""desk.physics — SGP4 orbit propagation and simulated COTS telemetry for NEO Action Item 2.

See `docs/research/space-track-cdm-api.md` and `INVARIANTS.md` for the data-source
locks. The COTS telemetry stream is an authorised override (O1) per
`docs/INVARIANTS.md` §"How to use this document".
"""

from desk.physics.sgp4_propagator import propagate, refresh_tle_cache, tle_for_norad
from desk.physics.cots_telemetry import TelemetryStream, telemetry_buffer_for

__all__ = [
    "propagate",
    "refresh_tle_cache",
    "tle_for_norad",
    "TelemetryStream",
    "telemetry_buffer_for",
]
