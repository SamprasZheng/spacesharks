"""desk.physics.sgp4_propagator — real SGP4 propagation for NEO Action Item 2.

Replaces the random `_orbit_seed` deterministic-but-fake propagator in
`server.py` with live SGP4 propagation. TLE strings are loaded from
`data/tle/celestrak-active.tle` (refreshed daily via Celestrak —
one of the INVARIANTS-locked four hosts, so this introduces NO new
external egress).

The module is fail-open: if Celestrak is unreachable on first start, we fall
back to a small bundled TLE set so the desk can still boot.
"""

from __future__ import annotations

import math
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple

try:
    from sgp4.api import Satrec, jday
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "desk.physics.sgp4_propagator requires the `sgp4` package. "
        "Install with `pip install sgp4`."
    ) from e


_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
_TLE_CACHE_PATH = _REPO / "data" / "tle" / "celestrak-active.tle"
_TLE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)

# Celestrak active satellites endpoint — single canonical URL per
# INVARIANTS source-list-lock.
_CELESTRAK_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle"

# Refresh cache no more often than every 6h.
_REFRESH_INTERVAL_S = 6 * 3600

_TLE_INDEX: dict[str, tuple[str, str, str]] = {}  # norad -> (name, line1, line2)
_TLE_LAST_REFRESH: float = 0.0
_TLE_LOCK = threading.Lock()

# Bundled fallback — three well-known LEO sats so we can boot offline.
_FALLBACK_TLE: list[tuple[str, str, str]] = [
    ("ISS (ZARYA)",
     "1 25544U 98067A   24131.50000000  .00010000  00000-0  19500-3 0  9999",
     "2 25544  51.6400 290.0000 0001500  30.0000 330.0000 15.50000000400000"),
    ("STARLINK-1007",
     "1 44737U 19074A   24131.50000000  .00001000  00000-0  10000-3 0  9999",
     "2 44737  53.0000  80.0000 0001000  90.0000 270.0000 15.06000000300000"),
    ("STARLINK-2118",
     "1 48276U 21037A   24131.50000000  .00001500  00000-0  12000-3 0  9999",
     "2 48276  53.2000 100.0000 0001500  60.0000 300.0000 15.30000000150000"),
]


def _parse_tle_block(text: str) -> dict[str, tuple[str, str, str]]:
    """Parse a multi-TLE blob (name line + line1 + line2 triples).

    Tolerant of leading/trailing whitespace per line and skip-over for
    comments (`#`) and noise lines that don't fit the TLE shape.
    """
    out: dict[str, tuple[str, str, str]] = {}
    # Lines for TLE matching get .strip()ed to handle indented test fixtures
    # and copy-pasted blocks.
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    # Skip leading comment lines so the name line is at index i correctly.
    lines = [ln for ln in lines if not ln.startswith("#")]
    i = 0
    while i + 2 < len(lines):
        name = lines[i]
        line1 = lines[i + 1]
        line2 = lines[i + 2]
        if line1.startswith("1 ") and line2.startswith("2 "):
            # NORAD ID is digits at column 2..7 of line1
            try:
                norad = str(int(line1[2:7].strip()))
                out[norad] = (name, line1, line2)
            except ValueError:
                pass
            i += 3
        else:
            i += 1
    return out


def _load_cache() -> None:
    global _TLE_INDEX, _TLE_LAST_REFRESH
    if _TLE_CACHE_PATH.exists():
        try:
            text = _TLE_CACHE_PATH.read_text(encoding="utf-8", errors="ignore")
            idx = _parse_tle_block(text)
            if idx:
                _TLE_INDEX = idx
                _TLE_LAST_REFRESH = _TLE_CACHE_PATH.stat().st_mtime
                return
        except (OSError, UnicodeDecodeError):
            pass
    # Fall back to bundled triples
    for name, l1, l2 in _FALLBACK_TLE:
        try:
            norad = str(int(l1[2:7].strip()))
        except ValueError:
            continue
        _TLE_INDEX.setdefault(norad, (name, l1, l2))


def refresh_tle_cache(force: bool = False, timeout: float = 12.0) -> dict:
    """Fetch active TLE set from Celestrak, write to cache, reload index.

    Returns `{ok, count, fetched, source}` for logging. No-op (returns
    `{ok: True, fetched: False}`) if the cache is fresher than 6h and
    `force=False`.
    """
    global _TLE_INDEX, _TLE_LAST_REFRESH
    with _TLE_LOCK:
        if not force and _TLE_LAST_REFRESH and time.time() - _TLE_LAST_REFRESH < _REFRESH_INTERVAL_S:
            return {"ok": True, "fetched": False, "count": len(_TLE_INDEX), "source": "cache"}

        try:
            req = urllib.request.Request(_CELESTRAK_URL, headers={"User-Agent": "spacesharks-mission-desk/0.1"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = resp.read().decode("utf-8", errors="ignore")
        except Exception as e:  # noqa: BLE001
            # network unreachable — keep the existing index, return ok=False
            return {"ok": False, "fetched": False, "count": len(_TLE_INDEX),
                    "source": "cache", "error": str(e)}

        idx = _parse_tle_block(payload)
        if not idx:
            return {"ok": False, "fetched": True, "count": 0, "source": "celestrak",
                    "error": "no_tle_parsed"}

        _TLE_CACHE_PATH.write_text(payload, encoding="utf-8")
        _TLE_INDEX = idx
        _TLE_LAST_REFRESH = time.time()
        return {"ok": True, "fetched": True, "count": len(idx), "source": "celestrak"}


def tle_for_norad(norad: str) -> tuple[str, str, str] | None:
    """Return (name, line1, line2) for the given NORAD id, or None.

    Lazy-loads the cache on first call. Does NOT trigger network fetch — call
    `refresh_tle_cache()` explicitly for that.
    """
    if not _TLE_INDEX:
        _load_cache()
    return _TLE_INDEX.get(str(norad))


def propagate(norad: str, ts_utc: float | None = None) -> dict | None:
    """SGP4 propagation for NORAD id at `ts_utc` (Unix seconds, default now).

    Returns a dict:
      `{ok, lat_deg, lon_deg, alt_km, speed_km_s, in_eclipse, source}`
    or `None` if no TLE is available for `norad`.
    """
    if ts_utc is None:
        ts_utc = time.time()
    tle = tle_for_norad(norad)
    if tle is None:
        return None
    _name, line1, line2 = tle

    sat = Satrec.twoline2rv(line1, line2)
    dt = datetime.fromtimestamp(ts_utc, tz=timezone.utc)
    jd, fr = jday(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second + dt.microsecond * 1e-6)
    e, pos_teme, vel_teme = sat.sgp4(jd, fr)
    if e != 0:
        return {"ok": False, "error_code": int(e), "source": "sgp4"}

    # TEME → ECEF (approximate; good enough for ground-track display +
    # eclipse detection but not for precision pointing).
    x, y, z = pos_teme
    vx, vy, vz = vel_teme
    r = math.sqrt(x * x + y * y + z * z)
    alt_km = r - 6378.137
    speed_km_s = math.sqrt(vx * vx + vy * vy + vz * vz)

    # Greenwich Mean Sidereal Time at JD (low-order)
    T = (jd + fr - 2451545.0) / 36525.0
    gmst = (
        280.46061837
        + 360.98564736629 * (jd + fr - 2451545.0)
        + 0.000387933 * T * T
        - (T * T * T) / 38710000.0
    )
    gmst_rad = math.radians(gmst % 360.0)
    cos_g = math.cos(gmst_rad)
    sin_g = math.sin(gmst_rad)
    # Rotate TEME → ECEF (z-axis spin)
    x_ecef = cos_g * x + sin_g * y
    y_ecef = -sin_g * x + cos_g * y
    z_ecef = z

    lat_rad = math.asin(z_ecef / r)
    lon_rad = math.atan2(y_ecef, x_ecef)
    lat_deg = math.degrees(lat_rad)
    lon_deg = math.degrees(lon_rad)
    if lon_deg > 180.0:
        lon_deg -= 360.0
    if lon_deg < -180.0:
        lon_deg += 360.0

    # Crude eclipse check: sun direction = +x in J2000 approx for time-of-year;
    # for the hackathon a robust enough proxy is "subsolar lon at noon UTC =
    # 180 deg E, sat in eclipse when sat lon is within ±90 of antisolar lon".
    sun_lon = ((dt.hour + dt.minute / 60.0) / 24.0) * 360.0 - 180.0
    antisolar = sun_lon + 180.0
    if antisolar > 180.0:
        antisolar -= 360.0
    dlon = abs(((lon_deg - antisolar + 540.0) % 360.0) - 180.0)
    in_eclipse = dlon < 90.0 and alt_km < 2000.0  # LEO only

    return {
        "ok": True,
        "lat_deg": lat_deg,
        "lon_deg": lon_deg,
        "alt_km": alt_km,
        "speed_km_s": speed_km_s,
        "in_eclipse": in_eclipse,
        "source": "sgp4",
        "ts_utc": ts_utc,
    }
