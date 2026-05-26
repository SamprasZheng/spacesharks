"""desk.physics — SGP4 orbit propagation, real SWPC space-weather, and
simulated COTS telemetry for NEO Action Item 2.

See `docs/research/space-track-cdm-api.md` and `INVARIANTS.md` for the data-source
locks. The COTS telemetry stream is an authorised override (O1) per
`docs/INVARIANTS.md` §"How to use this document".
"""

from desk.physics.sgp4_propagator import propagate, refresh_tle_cache, tle_for_norad
from desk.physics.cots_telemetry import TelemetryStream, telemetry_buffer_for
from desk.physics.swpc_poller import (
    fetch_all as swpc_fetch_all,
    latest_snapshot as swpc_latest_snapshot,
    is_real_data_available as swpc_is_real_data_available,
)

__all__ = [
    "propagate",
    "refresh_tle_cache",
    "tle_for_norad",
    "TelemetryStream",
    "telemetry_buffer_for",
    "swpc_fetch_all",
    "swpc_latest_snapshot",
    "swpc_is_real_data_available",
]
