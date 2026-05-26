"""desk.physics.disaster_feed — "where in the world needs Starlink right now?"

Pulls THREE free public disaster/event feeds (no API key required):

  - USGS earthquakes M4.5+ in the last 24h
    https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson

  - NASA EONET (Earth Observatory Natural Event Tracker) open events
    https://eonet.gsfc.nasa.gov/api/v3/events?status=open

  - GDACS (Global Disaster Alert + Coordination System) RSS
    https://www.gdacs.org/xml/rss.xml

For each event we surface lat/lon + severity + age + a short headline, then
combine into a single ranked list the dashboard renders.
"""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.request
from typing import Any


_USER_AGENT = "spacesharks-mission-desk/0.1 (NEO World View / Disaster Feed)"
_TIMEOUT_S = 12.0
_TTL_S = 300

_USGS_URL  = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson"
_EONET_URL = "https://eonet.gsfc.nasa.gov/api/v3/events?status=open&limit=40"
_GDACS_URL = "https://www.gdacs.org/xml/rss.xml"

_LOCK = threading.Lock()
_CACHE = {"value": None, "ts": 0, "error": None}


def _http_get(url: str, timeout: float = _TIMEOUT_S) -> tuple[bytes | None, str | None]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(), None
    except urllib.error.URLError as e:
        return None, f"URLError: {e}"
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def _parse_usgs(payload: bytes) -> tuple[list[dict], str | None]:
    try:
        data = json.loads(payload.decode("utf-8", errors="ignore"))
    except json.JSONDecodeError as e:
        return [], f"usgs json: {e}"
    out = []
    for f in data.get("features", []):
        props = f.get("properties") or {}
        geom = f.get("geometry") or {}
        coords = geom.get("coordinates") or [None, None, None]
        if len(coords) < 2 or coords[0] is None:
            continue
        mag = props.get("mag")
        place = props.get("place") or "?"
        url = props.get("url") or ""
        ts_ms = props.get("time")
        out.append({
            "source": "usgs-quake",
            "kind": "earthquake",
            "lat": float(coords[1]),
            "lon": float(coords[0]),
            "depth_km": float(coords[2]) if len(coords) > 2 and coords[2] is not None else None,
            "magnitude": mag,
            "severity_score": float(mag or 0) * 10.0,  # M6 → 60, M7 → 70 etc.
            "headline": f"M{mag:.1f} {place}" if mag is not None else place,
            "url": url,
            "ts_ms": ts_ms,
            "iso_time": props.get("time") and time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts_ms / 1000.0)
            ) or None,
        })
    return out, None


def _parse_eonet(payload: bytes) -> tuple[list[dict], str | None]:
    try:
        data = json.loads(payload.decode("utf-8", errors="ignore"))
    except json.JSONDecodeError as e:
        return [], f"eonet json: {e}"
    out = []
    for ev in data.get("events", []):
        # Each event has a list of geometries (a track for storms). Use the
        # most recent point.
        geoms = ev.get("geometry") or []
        if not geoms:
            continue
        g = geoms[-1]
        c = g.get("coordinates")
        # EONET coords are [lon, lat] for point, polygon-arrays for storms.
        lat, lon = None, None
        if isinstance(c, list) and len(c) >= 2 and isinstance(c[0], (int, float)):
            lon, lat = c[0], c[1]
        if lat is None or lon is None:
            continue
        cats = [c.get("title", "?") for c in (ev.get("categories") or [])]
        category = cats[0] if cats else "Event"
        out.append({
            "source": "nasa-eonet",
            "kind": category.lower().replace(" ", "-"),
            "lat": float(lat),
            "lon": float(lon),
            "magnitude": None,
            "severity_score": 50.0,   # baseline; EONET doesn't quantify severity
            "headline": ev.get("title") or category,
            "url": (ev.get("sources") or [{}])[0].get("url", ""),
            "iso_time": g.get("date"),
        })
    return out, None


def _parse_gdacs_rss(payload: bytes) -> tuple[list[dict], str | None]:
    """Tolerant RSS parser — GDACS uses gdacs:* namespaces. Stdlib only."""
    text = payload.decode("utf-8", errors="ignore")
    out = []
    item_blocks = re.findall(r"<item>(.+?)</item>", text, re.DOTALL)
    for blk in item_blocks[:40]:
        title = _re1(blk, r"<title>(.+?)</title>")
        link  = _re1(blk, r"<link>(.+?)</link>")
        # GDACS often has <geo:lat> / <geo:long> or <georss:point>lat lon</georss:point>
        lat = _re1(blk, r"<geo:lat>([\-\d.]+)</geo:lat>") or _re1(blk, r"<geoLat>([\-\d.]+)</geoLat>")
        lon = _re1(blk, r"<geo:long>([\-\d.]+)</geo:long>") or _re1(blk, r"<geoLon>([\-\d.]+)</geoLon>")
        gp = _re1(blk, r"<georss:point>([\-\d.\s]+)</georss:point>")
        if gp:
            parts = gp.split()
            if len(parts) >= 2:
                lat = lat or parts[0]
                lon = lon or parts[1]
        if not lat or not lon:
            continue
        sev = _re1(blk, r"<gdacs:severity[^>]*>(.+?)</gdacs:severity>") or "GREEN"
        kind = _re1(blk, r"<gdacs:eventtype>(.+?)</gdacs:eventtype>") or "alert"
        pubdate = _re1(blk, r"<pubDate>(.+?)</pubDate>")
        sev_score = {"RED": 80.0, "ORANGE": 65.0, "GREEN": 40.0}.get(sev.upper(), 50.0)
        out.append({
            "source": "gdacs",
            "kind": kind.lower(),
            "lat": float(lat),
            "lon": float(lon),
            "magnitude": None,
            "severity_score": sev_score,
            "severity_label": sev,
            "headline": title or "GDACS event",
            "url": link,
            "iso_time": pubdate,
        })
    return out, None


def _re1(haystack: str, pattern: str) -> str | None:
    m = re.search(pattern, haystack, re.DOTALL)
    if not m:
        return None
    return m.group(1).strip()


def fetch_combined(force: bool = False) -> dict:
    with _LOCK:
        age = time.time() - _CACHE["ts"]
        if not force and _CACHE["value"] and age < _TTL_S:
            return {**_CACHE, "age_s": int(age), "from_cache": True}

    now = time.time()
    all_events: list[dict] = []
    errors: list[str] = []

    for label, url, parser in [
        ("usgs",  _USGS_URL,  _parse_usgs),
        ("eonet", _EONET_URL, _parse_eonet),
        ("gdacs", _GDACS_URL, _parse_gdacs_rss),
    ]:
        body, err = _http_get(url)
        if err:
            errors.append(f"{label}: {err}")
            continue
        events, perr = parser(body)
        if perr:
            errors.append(f"{label} parse: {perr}")
        all_events.extend(events)

    # Sort by severity score DESC, then by lat band importance (boost equatorial
    # and populated bands lightly so a M7 quake in remote sea doesn't crowd out
    # a M5.5 near a city — we don't have city data, so just severity-sort).
    all_events.sort(key=lambda e: -float(e.get("severity_score", 0)))

    snapshot = {
        "events": all_events[:40],
        "total_count": len(all_events),
        "errors": errors,
        "ts": now,
        "iso_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "sources": [
            {"label": "USGS quakes M4.5+ 24h",   "url": _USGS_URL},
            {"label": "NASA EONET open events", "url": _EONET_URL},
            {"label": "GDACS RSS",              "url": _GDACS_URL},
        ],
    }
    with _LOCK:
        _CACHE.update(value=snapshot, ts=now, error=("; ".join(errors) if errors else None))
    return {"value": snapshot, "ts": now, "error": errors, "from_cache": False}
