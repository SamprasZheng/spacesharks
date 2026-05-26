"""tests/test_sgp4_replay.py — NEO Action Item 2 SGP4 propagator verification.

Tests that the bundled fallback TLE set produces sensible lat/lon/alt for a
known epoch and that the cache loader handles malformed input gracefully.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from desk.physics.sgp4_propagator import (  # noqa: E402
    propagate,
    tle_for_norad,
    refresh_tle_cache,
    _parse_tle_block,
)


def test_fallback_iss_tle_propagation_is_sensible():
    # ISS NORAD ID = 25544; the bundled fallback covers this.
    tle = tle_for_norad("25544")
    assert tle is not None
    name, l1, l2 = tle
    assert "ISS" in name

    # Propagate at the TLE epoch (2024-05-10 12:00 UTC roughly — the fallback
    # uses 24131.5 = 2024 day 131.5 = May 10 12:00 UTC).
    result = propagate("25544", ts_utc=1715342400.0)  # 2024-05-10 12:00 UTC
    assert result is not None
    assert result["ok"] is True
    # ISS altitude band ~ 400–430 km
    assert 350.0 <= result["alt_km"] <= 500.0, f"alt out of band: {result['alt_km']}"
    # ISS inclination 51.6° → |lat| <= ~52°
    assert -55.0 <= result["lat_deg"] <= 55.0
    assert -180.0 <= result["lon_deg"] <= 180.0
    # Speed ~ 7.66 km/s for LEO
    assert 7.0 <= result["speed_km_s"] <= 8.2, f"speed out of band: {result['speed_km_s']}"


def test_starlink_propagation_at_now():
    result = propagate("44737", ts_utc=time.time())
    assert result is not None
    assert result["ok"] is True
    # Starlink shell v1.0/G1 altitude band ~ 540..560 km
    assert 400.0 <= result["alt_km"] <= 700.0


def test_unknown_norad_returns_none():
    assert propagate("99999999") is None


def test_parse_tle_block_handles_messy_input():
    text = """
    # comment line that should be skipped

    ISS (ZARYA)
    1 25544U 98067A   24131.50000000  .00010000  00000-0  19500-3 0  9999
    2 25544  51.6400 290.0000 0001500  30.0000 330.0000 15.50000000400000

    garbage line that is not a TLE
    """
    idx = _parse_tle_block(text)
    assert "25544" in idx
    assert idx["25544"][0].strip() == "ISS (ZARYA)"


def test_refresh_tle_cache_is_idempotent_offline(monkeypatch):
    """When force=False and cache is fresh, refresh returns fetched=False."""
    # Reach into the module to force the timestamp recent.
    import desk.physics.sgp4_propagator as prop
    prop._TLE_LAST_REFRESH = time.time()
    result = refresh_tle_cache(force=False)
    assert result["ok"] is True
    assert result["fetched"] is False
