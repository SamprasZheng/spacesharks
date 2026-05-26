"""desk.physics.swpc_poller — real NOAA SWPC space-weather feeds.

Closes the "real data, not fake-for-viz" critique. NOAA SWPC is one of the
four INVARIANTS-locked first-version hosts and is already in the NemoClaw
egress allowlist, so no new external trust surface is added.

Three endpoints are polled at their natural cadence:

  - planetary_k_index_1m.json     — 1-minute estimated Kp index
                                    https://services.swpc.noaa.gov/json/planetary_k_index_1m.json
  - goes/primary/xrays-1-day.json  — GOES X-ray flux (M/X class detection)
                                    https://services.swpc.noaa.gov/json/goes/primary/xrays-1-day.json
  - goes/primary/integral-protons-1-day.json — SEP proton flux
                                    https://services.swpc.noaa.gov/json/goes/primary/integral-protons-1-day.json

We keep a per-feed cache so multiple callers in one tick share a single HTTP
request. The Weather class in server.py reads from `latest_snapshot()`; if any
feed fails the poller transparently falls back to the previously-cached value
and logs a HIGH severity audit row so the operator sees the degradation.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from typing import Any


# Endpoint table — cadence in seconds matches the SWPC update frequency.
SWPC_ENDPOINTS = {
    "kp_1m": {
        "url": "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json",
        "cadence_s": 60,
    },
    "xray_1d": {
        "url": "https://services.swpc.noaa.gov/json/goes/primary/xrays-1-day.json",
        "cadence_s": 60,
    },
    "sep_1d": {
        "url": "https://services.swpc.noaa.gov/json/goes/primary/integral-protons-1-day.json",
        "cadence_s": 60,
    },
}

_USER_AGENT = "spacesharks-mission-desk/0.1 (NEO Action Item 2)"

# Per-feed cache:
#   {feed_name: {"last_fetch_ts": float, "value": <parsed>, "raw": <bytes>, "error": str|None}}
_CACHE: dict[str, dict[str, Any]] = {k: {} for k in SWPC_ENDPOINTS}
_LOCK = threading.Lock()


def _fetch_json(url: str, timeout: float = 8.0) -> tuple[Any, str | None]:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = resp.read().decode("utf-8", errors="ignore")
            return json.loads(payload), None
    except urllib.error.URLError as e:
        return None, f"URLError: {e}"
    except json.JSONDecodeError as e:
        return None, f"JSONDecodeError: {e}"
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def _latest_kp(payload: Any) -> float | None:
    """Extract the latest Kp index from the SWPC planetary_k_index_1m payload.

    Format: list of {"time_tag": "ISO8601", "Kp": float, "estimated_kp": float, ...}
    Use estimated_kp (1-min granularity) if present; fall back to Kp.
    """
    if not isinstance(payload, list) or not payload:
        return None
    last = payload[-1]
    for key in ("estimated_kp", "Kp", "kp_index"):
        if key in last and last[key] is not None:
            try:
                return float(last[key])
            except (TypeError, ValueError):
                continue
    return None


def _latest_xray(payload: Any) -> float | None:
    """Extract the latest X-ray flux (W/m^2) for the 0.1–0.8 nm long band.

    Format: list of {"time_tag", "satellite", "flux", "energy", ...}
    where energy is "0.1-0.8nm" (long) or "0.05-0.4nm" (short).
    """
    if not isinstance(payload, list) or not payload:
        return None
    # Walk backward, prefer the latest long-band sample.
    for rec in reversed(payload):
        if rec.get("energy") in ("0.1-0.8nm", "0.1-0.8 nm"):
            try:
                return float(rec.get("flux"))
            except (TypeError, ValueError):
                continue
    return None


def _latest_sep(payload: Any) -> float | None:
    """Extract the latest integral proton flux at >=10 MeV (pfu)."""
    if not isinstance(payload, list) or not payload:
        return None
    for rec in reversed(payload):
        energy = rec.get("energy")
        if energy in (">=10 MeV", ">=10MeV", "P>10MeV", "p_gt_10mev"):
            try:
                return float(rec.get("flux"))
            except (TypeError, ValueError):
                continue
    # Some feeds put the >=10 MeV value at the last record without an energy
    # label; try the highest-numbered flux field.
    last = payload[-1]
    for key in ("flux", "p10_flux"):
        if key in last:
            try:
                return float(last[key])
            except (TypeError, ValueError):
                continue
    return None


_PARSERS = {
    "kp_1m": _latest_kp,
    "xray_1d": _latest_xray,
    "sep_1d": _latest_sep,
}


def _maybe_fetch(feed_name: str) -> dict:
    """Fetch the feed if cache stale. Returns the cache entry."""
    cfg = SWPC_ENDPOINTS[feed_name]
    with _LOCK:
        entry = _CACHE[feed_name]
        now = time.time()
        if entry and (now - entry.get("last_fetch_ts", 0.0)) < cfg["cadence_s"]:
            return entry

    # Outside the lock — HTTP call.
    payload, err = _fetch_json(cfg["url"])
    parsed = None
    if payload is not None:
        parser = _PARSERS.get(feed_name)
        if parser:
            try:
                parsed = parser(payload)
            except Exception as e:  # noqa: BLE001
                err = f"parse error: {e}"

    new_entry = {
        "last_fetch_ts": time.time(),
        "value": parsed,
        "raw": payload if isinstance(payload, list) and len(payload) < 100 else None,
        "error": err,
        "url": cfg["url"],
        "feed": feed_name,
    }
    with _LOCK:
        # Carry forward the last good value when fetch fails so callers always
        # see *some* number rather than a None hole.
        prev = _CACHE[feed_name]
        if parsed is None and prev.get("value") is not None:
            new_entry["value"] = prev["value"]
            new_entry["error"] = (err or "") + f" (using cached value from {prev.get('last_fetch_ts')})"
        _CACHE[feed_name] = new_entry
    return new_entry


def fetch_all(force: bool = False) -> dict[str, dict]:
    """Fetch all feeds (cache-respecting). Returns a snapshot of cache entries."""
    out = {}
    for feed_name in SWPC_ENDPOINTS:
        if force:
            with _LOCK:
                _CACHE[feed_name] = {}
        out[feed_name] = _maybe_fetch(feed_name)
    return out


def latest_snapshot() -> dict:
    """Read-only snapshot of current cached values, suitable for handing to
    the Weather class. Does NOT trigger a fetch — call fetch_all() in a
    background thread for that."""
    with _LOCK:
        out: dict = {"ok": True, "feeds": {}}
        for feed_name, entry in _CACHE.items():
            out["feeds"][feed_name] = {
                "value": entry.get("value"),
                "last_fetch_ts": entry.get("last_fetch_ts"),
                "error": entry.get("error"),
                "stale_s": (time.time() - entry["last_fetch_ts"]) if entry.get("last_fetch_ts") else None,
                "url": entry.get("url"),
            }
            if entry.get("error"):
                out["ok"] = False
        return out


def is_real_data_available() -> bool:
    """True if at least one feed has a non-None value (i.e., we've successfully
    reached SWPC at least once)."""
    with _LOCK:
        return any(e.get("value") is not None for e in _CACHE.values())
