"""desk.physics.swpc_forecast — NOAA SWPC 3-day forecast + active alerts.

Answers the user question "太陽風暴或高能粒子是否會出現?" with REAL data.
Both endpoints are public, no API key, already on the NemoClaw egress
allowlist (swpc.noaa.gov).
"""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.request
from typing import Any


_USER_AGENT = "spacesharks-mission-desk/0.1 (NEO World View)"
_TIMEOUT_S = 10.0
_FORECAST_TTL_S = 300        # 5 min cache (NOAA updates 3x/day)
_ALERTS_TTL_S = 120          # 2 min cache (alerts can fire any time)

_FORECAST_URL = "https://services.swpc.noaa.gov/text/3-day-forecast.txt"
_ALERTS_URL   = "https://services.swpc.noaa.gov/products/alerts.json"

_LOCK = threading.Lock()
_FORECAST_CACHE: dict = {"value": None, "ts": 0, "error": None}
_ALERTS_CACHE:   dict = {"value": None, "ts": 0, "error": None}


def _http_get(url: str, timeout: float = _TIMEOUT_S) -> tuple[bytes | None, str | None]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(), None
    except urllib.error.URLError as e:
        return None, f"URLError: {e}"
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# 3-day forecast — plain text product. Parse the three sections:
#   - Geomagnetic Activity Observation and Forecast (Kp per 3h slot, 3 days)
#   - Solar Radiation Activity Observation and Forecast (S1-S5 prob)
#   - Radio Blackout Activity and Forecast (R1-R2, R3+ probability)
# ---------------------------------------------------------------------------

def _parse_3day_forecast(text: str) -> dict:
    """Very tolerant parser — NOAA's text format is consistent but varies in
    whitespace. We just extract daily summaries + the probability blocks."""
    out: dict[str, Any] = {
        "raw_length": len(text),
        "issued_at": None,
        "geomagnetic_kp_table": [],
        "solar_radiation_prob": [],
        "radio_blackout_prob": [],
        "rationale": None,
    }
    # Issued line
    m = re.search(r":Issued:\s*([0-9]{4}\s+\w+\s+\w+\s+[0-9:]+\s+UTC)", text)
    if m:
        out["issued_at"] = m.group(1).strip()

    # Geomagnetic Kp table — actual section heading is "NOAA Kp index breakdown"
    # not "Geomagnetic Activity Probabilities" (that's a different section).
    geo_section = re.search(
        r"NOAA Kp index breakdown[^\n]*\n(.+?)(?:Rationale:|Solar Radiation Activity|$)",
        text, re.DOTALL,
    )
    if geo_section:
        for row in re.finditer(r"([0-9]{2}-[0-9]{2}UT)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)",
                               geo_section.group(1)):
            out["geomagnetic_kp_table"].append({
                "slot": row.group(1),
                "day1": float(row.group(2)),
                "day2": float(row.group(3)),
                "day3": float(row.group(4)),
            })

    # Solar radiation storm probabilities (S1+ etc.)
    sr_section = re.search(
        r"Solar Radiation Activity Observation and Forecast(.+?)(?:Radio Blackout|$)",
        text, re.DOTALL,
    )
    if sr_section:
        for row in re.finditer(r"(S\d \(.+?\))\s+(\d+)\s+(\d+)\s+(\d+)",
                               sr_section.group(1)):
            out["solar_radiation_prob"].append({
                "level": row.group(1),
                "day1_pct": int(row.group(2)),
                "day2_pct": int(row.group(3)),
                "day3_pct": int(row.group(4)),
            })

    # Radio blackout
    rb_section = re.search(
        r"Radio Blackout Activity Observation and Forecast(.+?)$",
        text, re.DOTALL,
    )
    if rb_section:
        for row in re.finditer(r"(R1-R2|R3.*|\(R1-R2\)|\(R3.*\))\s+(\d+)\s+(\d+)\s+(\d+)",
                               rb_section.group(1)):
            out["radio_blackout_prob"].append({
                "level": row.group(1),
                "day1_pct": int(row.group(2)),
                "day2_pct": int(row.group(3)),
                "day3_pct": int(row.group(4)),
            })

    # Rationale snippet
    rationale = re.search(r"Rationale:(.+?)(?:Solar Radiation|Geomagnetic|$)", text, re.DOTALL)
    if rationale:
        out["rationale"] = " ".join(rationale.group(1).split())[:500]

    return out


def fetch_3day_forecast(force: bool = False) -> dict:
    with _LOCK:
        age = time.time() - _FORECAST_CACHE["ts"]
        if not force and _FORECAST_CACHE["value"] and age < _FORECAST_TTL_S:
            return {**_FORECAST_CACHE, "age_s": int(age), "from_cache": True}

    payload, err = _http_get(_FORECAST_URL)
    now = time.time()
    if payload is None:
        with _LOCK:
            _FORECAST_CACHE["error"] = err
            _FORECAST_CACHE["ts"] = now
        return {"value": _FORECAST_CACHE["value"], "error": err, "ts": now, "from_cache": False}

    text = payload.decode("utf-8", errors="ignore")
    parsed = _parse_3day_forecast(text)
    with _LOCK:
        _FORECAST_CACHE.update(value=parsed, ts=now, error=None, raw_url=_FORECAST_URL)
    return {"value": parsed, "ts": now, "error": None, "from_cache": False}


# ---------------------------------------------------------------------------
# Active alerts — JSON list. Format:
#   [{"product_id":"K04","issue_datetime":"2025-...","message":"..."}, ...]
# We keep the last 20 alerts so the dashboard panel has enough to scroll.
# ---------------------------------------------------------------------------

def fetch_active_alerts(force: bool = False) -> dict:
    with _LOCK:
        age = time.time() - _ALERTS_CACHE["ts"]
        if not force and _ALERTS_CACHE["value"] and age < _ALERTS_TTL_S:
            return {**_ALERTS_CACHE, "age_s": int(age), "from_cache": True}

    payload, err = _http_get(_ALERTS_URL)
    now = time.time()
    if payload is None:
        return {"value": _ALERTS_CACHE["value"], "error": err, "ts": now, "from_cache": False}

    try:
        records = json.loads(payload.decode("utf-8", errors="ignore"))
    except json.JSONDecodeError as e:
        with _LOCK:
            _ALERTS_CACHE["error"] = f"json decode: {e}"
        return {"value": None, "error": str(e), "ts": now, "from_cache": False}

    # Normalise + keep last 20
    out = []
    for rec in records[:50]:
        msg = (rec.get("message") or "").strip()
        # First non-empty line is the alert headline
        headline = next((ln.strip() for ln in msg.split("\n") if ln.strip()), msg[:100])
        out.append({
            "product_id":     rec.get("product_id"),
            "issue_datetime": rec.get("issue_datetime"),
            "headline":       headline[:160],
            "message":        msg[:1200],
        })
    # Sort newest first
    out.sort(key=lambda r: r.get("issue_datetime") or "", reverse=True)
    out = out[:20]

    with _LOCK:
        _ALERTS_CACHE.update(value=out, ts=now, error=None)
    return {"value": out, "ts": now, "error": None, "from_cache": False}


def combined_forecast_snapshot() -> dict:
    f = fetch_3day_forecast()
    a = fetch_active_alerts()
    return {
        "forecast": f.get("value"),
        "forecast_ts": f.get("ts"),
        "forecast_error": f.get("error"),
        "alerts": a.get("value") or [],
        "alerts_ts": a.get("ts"),
        "alerts_error": a.get("error"),
        "source": "https://services.swpc.noaa.gov/",
    }
