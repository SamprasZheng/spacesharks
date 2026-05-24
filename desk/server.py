"""Spacesharks Mission Desk — MVP dashboard server.

Goal (per the user's "最小MVP"): **monitor each satellite's health**.

Health is a four-state traffic light driven by:

  - sat-intrinsic factors  : age vs design life, accumulated TID, recent SEEs
  - space-weather inputs   : Kp index, X-ray class, SEP proton flux, AE index
  - regime weighting       : GEO/MEO sensitive to high-Kp;
                             LEO/SSO sensitive to X-ray + SEP

States: GREEN → YELLOW → RED → BLACK (irrecoverable).

Multiple "assessor" models vote on each sat's health every tick, mirroring
the Layer-2 ensemble in ``docs/ARCHITECTURE.md``. Different models have
different biases (pessimistic on age / radiation / weather / balanced /
optimistic). The arbiter takes the median vote, but disagreement is
surfaced to the AI Copilot pane.

The server also tracks **Nimble Cloud token usage** so the operator can see
how close they are to the daily cap (the long-term plan is to migrate to a
local GPU and become "token-free").

Pure Python stdlib. Run:  python server.py [--port 8765]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import queue
import random
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
DATA = ROOT / "data"
JSONL = DATA / "lifecycle-events.jsonl"
DATA.mkdir(exist_ok=True)


# ============================================================================
# Sat fleet — the heart of the MVP.
# ============================================================================

def _sat(norad, name, regime, operator, launched, design_life, mass, incl, alt_km,
         tid_budget=50.0, mission="comms", lifecycle="In-Orbit Operations"):
    return {
        "id": norad,
        "name": name,
        "regime": regime,
        "operator": operator,
        "launched": launched,
        "design_life_years": design_life,
        "mass_kg": mass,
        "inclination_deg": incl,
        "altitude_km": alt_km,
        "tid_budget_krad": tid_budget,    # how much total ionizing dose it can tolerate
        "tid_accumulated_krad": tid_budget * random.uniform(0.05, 0.55),
        "see_events_30d": random.randint(0, 3),
        "last_safe_mode": None,
        "mission_type": mission,
        "lifecycle_stage": lifecycle,
        # mutable health fields:
        "health": "GREEN",
        "score": 0.10,
        "trend": "stable",
        "last_assessed": None,
    }


SATS = [
    # LEO crewed / station --------------------------------------------------
    _sat("25544", "ISS",            "LEO", "NASA/Roskosmos", "1998-11-20", 35, 419725, 51.6,  418, tid_budget=80, mission="station"),
    _sat("48274", "CSS-Tiangong",   "LEO", "CMSA",          "2021-04-29", 15, 80000,  41.5,  389, tid_budget=70, mission="station"),
    # LEO comms (Starlink shell) -------------------------------------------
    _sat("48275", "STRLNK-1234",    "LEO", "SpaceX",        "2021-05-15",  5, 260,    53.0,  550, tid_budget=20, mission="comms"),
    _sat("48276", "STRLNK-2118",    "LEO", "SpaceX",        "2022-02-21",  5, 260,    53.2,  548, tid_budget=20, mission="comms"),
    _sat("48277", "STRLNK-3047",    "LEO", "SpaceX",        "2022-09-04",  5, 260,    53.2,  552, tid_budget=20, mission="comms"),
    _sat("48278", "STRLNK-4012",    "LEO", "SpaceX",        "2023-03-12",  5, 260,    43.0,  540, tid_budget=20, mission="comms"),
    _sat("48279", "STRLNK-5021",    "LEO", "SpaceX",        "2023-11-08",  5, 260,    43.0,  539, tid_budget=20, mission="comms"),
    _sat("45123", "ONEWEB-0188",    "LEO", "Eutelsat",      "2021-07-01",  7, 147,    87.4, 1200, tid_budget=30, mission="comms"),
    _sat("45124", "ONEWEB-0212",    "LEO", "Eutelsat",      "2021-12-27",  7, 147,    87.4, 1200, tid_budget=30, mission="comms"),
    _sat("43571", "IRIDIUM-167",    "LEO", "Iridium",       "2018-07-25", 15, 860,    86.4,  778, tid_budget=40, mission="comms"),
    # SSO Earth-observation -------------------------------------------------
    _sat("39084", "Landsat-8",      "SSO", "NASA/USGS",     "2013-02-11", 10, 2071,   98.2,  705, tid_budget=60, mission="EO"),
    _sat("49260", "Landsat-9",      "SSO", "NASA/USGS",     "2021-09-27", 10, 2623,   98.2,  705, tid_budget=60, mission="EO"),
    _sat("57172", "Sentinel-2C",    "SSO", "ESA/Copernicus","2024-09-04", 12, 1130,   98.6,  786, tid_budget=55, mission="EO"),
    _sat("40697", "Sentinel-2A",    "SSO", "ESA/Copernicus","2015-06-23", 12, 1130,   98.6,  786, tid_budget=55, mission="EO"),
    _sat("41335", "Sentinel-3A",    "SSO", "ESA/Copernicus","2016-02-16", 12, 1250,   98.7,  814, tid_budget=55, mission="EO"),
    _sat("43013", "NOAA-20",        "SSO", "NOAA",          "2017-11-18",  7, 2540,   98.7,  833, tid_budget=50, mission="weather"),
    _sat("28654", "NOAA-18",        "SSO", "NOAA",          "2005-05-20",  3, 1457,   98.7,  854, tid_budget=50, mission="weather", lifecycle="Event Management"),
    _sat("56217", "NOAA-21",        "SSO", "NOAA",          "2022-11-10",  7, 2930,   98.7,  833, tid_budget=50, mission="weather"),
    _sat("33591", "MetOp-A",        "SSO", "EUMETSAT",      "2006-10-19",  5, 4093,   98.7,  817, tid_budget=50, mission="weather", lifecycle="Deorbiting / Disposal"),
    # MEO navigation -------------------------------------------------------
    _sat("28474", "GPS-IIRM-5",     "MEO", "USSF",          "2006-09-25", 10, 2032,   55.0, 20180, tid_budget=120, mission="nav"),
    _sat("40294", "GLONASS-755",    "MEO", "Roskosmos",     "2014-06-14", 10, 1415,   64.8, 19140, tid_budget=110, mission="nav"),
    _sat("41859", "Galileo-22",     "MEO", "ESA/EUSPA",     "2016-11-17", 12, 730,    56.0, 23222, tid_budget=120, mission="nav"),
    _sat("44793", "Beidou-3 M22",   "MEO", "CNSA",          "2019-12-16", 12, 1014,   55.0, 21528, tid_budget=120, mission="nav"),
    # GEO ------------------------------------------------------------------
    _sat("43226", "GOES-16",        "GEO", "NOAA",          "2016-11-19", 15, 5192,    0.05, 35786, tid_budget=200, mission="weather"),
    _sat("43689", "GOES-17",        "GEO", "NOAA",          "2018-03-01", 15, 5192,    0.05, 35786, tid_budget=200, mission="weather"),
    _sat("39260", "Inmarsat-5 F1",  "GEO", "Inmarsat",      "2013-12-08", 15, 6100,    0.05, 35786, tid_budget=200, mission="comms"),
    _sat("42432", "EchoStar-23",    "GEO", "EchoStar",      "2017-03-16", 15, 5500,    0.05, 35786, tid_budget=200, mission="comms"),
]


# ============================================================================
# Space weather — the driver of health transitions.
# ============================================================================

class Weather:
    def __init__(self) -> None:
        self.kp = 2.5                # 0..9
        self.xray = 1.5e-7           # W/m^2; M-class ≥ 1e-5, X-class ≥ 1e-4
        self.sep_pfu = 0.4           # protons >10MeV per (cm^2 s sr)
        self.ae = 120                # auroral electrojet, nT
        self.regime_in_storm = None  # set during an event

    def tick(self) -> None:
        # Slow random walk with occasional storms.
        self.kp = max(0.0, min(9.0, self.kp + random.gauss(0, 0.3)))
        self.ae = max(20, min(2000, self.ae + random.gauss(0, 60)))
        self.xray = max(1e-8, self.xray * (1 + random.gauss(0, 0.15)))
        self.sep_pfu = max(0.05, self.sep_pfu + random.gauss(0, 0.2))
        # Random major event ~ every 30 ticks
        if random.random() < 0.020:
            self._spawn_event()

    def _spawn_event(self) -> None:
        kind = random.choices(
            ["solar-flare", "cme-impact", "sep-event", "geomagnetic-storm"],
            weights=[0.30, 0.25, 0.20, 0.25],
        )[0]
        if kind == "solar-flare":
            self.xray = random.uniform(1e-5, 5e-4)        # M to X
            self.regime_in_storm = "ALL"
            BUS.copilot("nemoclaw",
                f"{xray_class(self.xray)} solar flare detected — affecting comms (HF blackout) and pushing photoionization. Re-running risk assessors.")
        elif kind == "cme-impact":
            self.kp = random.uniform(6.0, 8.5)
            self.ae = random.uniform(800, 1800)
            self.regime_in_storm = "GEO"
            BUS.copilot("nemoclaw",
                f"CME impact in progress — Kp {self.kp:.1f}. GEO sats most exposed; surface-charging risk elevated.")
        elif kind == "sep-event":
            self.sep_pfu = random.uniform(50, 1500)
            self.regime_in_storm = "ALL"
            BUS.copilot("nemoclaw",
                f"SEP event — {self.sep_pfu:.0f} pfu (>10 MeV). Recommending safe-mode for crewed assets and EO payloads through south Atlantic anomaly passes.")
        else:
            self.kp = random.uniform(5.0, 7.5)
            self.regime_in_storm = "LEO"
            BUS.copilot("nemoclaw",
                f"Geomagnetic storm developing — Kp {self.kp:.1f}. LEO drag uptick expected.")

    def snapshot(self) -> dict:
        return {
            "kp": round(self.kp, 1),
            "xray": self.xray,
            "xray_class": xray_class(self.xray),
            "sep_pfu": round(self.sep_pfu, 1),
            "ae": int(self.ae),
            "storm_regime": self.regime_in_storm,
        }


def xray_class(w: float) -> str:
    if w >= 1e-4: return f"X{w / 1e-4:.1f}"
    if w >= 1e-5: return f"M{w / 1e-5:.1f}"
    if w >= 1e-6: return f"C{w / 1e-6:.1f}"
    if w >= 1e-7: return f"B{w / 1e-7:.1f}"
    return f"A{w / 1e-8:.1f}"


WEATHER = Weather()


# ============================================================================
# Assessor models — multi-model ensemble voting on each sat's health.
# Different biases so they disagree productively.
# ============================================================================

ASSESSORS = [
    {"id": "DeepProp-7B",      "family": "Nemotron-Nano",  "bias": "age",      "weight_age": 1.40, "weight_tid": 0.90, "weight_wx": 0.90, "tokens_per_call": 1100},
    {"id": "OrbitNet-13B",     "family": "Hermes-4",       "bias": "radiation","weight_age": 0.90, "weight_tid": 1.45, "weight_wx": 1.00, "tokens_per_call": 1450},
    {"id": "SatGuard-9B",      "family": "Mistral-deriv",  "bias": "weather",  "weight_age": 0.85, "weight_tid": 0.95, "weight_wx": 1.50, "tokens_per_call": 1250},
    {"id": "Astro-AI-22B",     "family": "Qwen-3",         "bias": "balanced", "weight_age": 1.00, "weight_tid": 1.00, "weight_wx": 1.00, "tokens_per_call": 1900},
    {"id": "Pathfinder-17B",   "family": "Nemotron-Super", "bias": "optimistic","weight_age": 0.80, "weight_tid": 0.80, "weight_wx": 0.85, "tokens_per_call": 1700},
]

NIMBLE_DAILY_QUOTA = 2_000_000   # synthetic daily token cap on Nimble Cloud
TOKEN_USAGE = {
    "spent": 0,
    "by_model": {a["id"]: 0 for a in ASSESSORS},
    "calls": 0,
    "window_start": time.time(),
    "history": deque(maxlen=120),   # last 120 ticks
}


def regime_weather_weight(regime: str, wx: dict) -> float:
    """How much the current weather hurts each regime."""
    kp = wx["kp"]
    xray = wx["xray"]
    sep = wx["sep_pfu"]
    if regime == "LEO":
        return 0.4 * (kp / 9.0) + 0.3 * min(1.0, xray / 1e-5) + 0.3 * min(1.0, sep / 100.0)
    if regime == "SSO":
        return 0.35 * (kp / 9.0) + 0.30 * min(1.0, xray / 1e-5) + 0.35 * min(1.0, sep / 100.0)
    if regime == "MEO":
        return 0.55 * (kp / 9.0) + 0.10 * min(1.0, xray / 1e-5) + 0.35 * min(1.0, sep / 100.0)
    if regime == "GEO":
        return 0.70 * (kp / 9.0) + 0.05 * min(1.0, xray / 1e-5) + 0.25 * min(1.0, sep / 100.0)
    return 0.0


def sat_age_years(sat: dict) -> float:
    try:
        ts = datetime.fromisoformat(sat["launched"]).replace(tzinfo=timezone.utc)
    except Exception:
        return 0.0
    return (datetime.now(timezone.utc) - ts).total_seconds() / (365.25 * 86400.0)


def base_factors(sat: dict, wx: dict) -> tuple[float, float, float, float]:
    """Returns (age, tid, see, wx) factors — each 0..>1.

    >1 means past tolerance (BLACK candidate).
    """
    age = sat_age_years(sat) / max(0.1, sat["design_life_years"])
    tid = sat["tid_accumulated_krad"] / max(0.1, sat["tid_budget_krad"])
    see = sat["see_events_30d"] / 5.0
    wxf = regime_weather_weight(sat["regime"], wx)
    return age, tid, see, wxf


def assessor_vote(model: dict, sat: dict, wx: dict) -> tuple[str, float]:
    """One model's vote: returns (label, internal score)."""
    age, tid, see, wxf = base_factors(sat, wx)
    score = (
        model["weight_age"] * age * 0.40
        + model["weight_tid"] * tid * 0.35
        + 1.0 * see * 0.10
        + model["weight_wx"] * wxf * 0.45
    )
    # small per-call noise
    score *= random.uniform(0.92, 1.08)
    # bias-driven label:
    if score >= 1.10: label = "BLACK"
    elif score >= 0.80: label = "RED"
    elif score >= 0.50: label = "YELLOW"
    else: label = "GREEN"
    return label, score


def assess_sat(sat: dict, wx: dict) -> dict:
    """Run every assessor, take the median label, return assessment dossier."""
    votes = []
    scores = []
    for m in ASSESSORS:
        label, sc = assessor_vote(m, sat, wx)
        votes.append({"model": m["id"], "family": m["family"], "label": label, "score": round(sc, 3)})
        scores.append(sc)
        TOKEN_USAGE["by_model"][m["id"]] += m["tokens_per_call"]
        TOKEN_USAGE["spent"] += m["tokens_per_call"]
        TOKEN_USAGE["calls"] += 1

    # median label by score
    scores_sorted = sorted(scores)
    median_score = scores_sorted[len(scores_sorted) // 2]
    if median_score >= 1.10: median_label = "BLACK"
    elif median_score >= 0.80: median_label = "RED"
    elif median_score >= 0.50: median_label = "YELLOW"
    else: median_label = "GREEN"

    # consensus = max label-share
    counts: dict[str, int] = {}
    for v in votes:
        counts[v["label"]] = counts.get(v["label"], 0) + 1
    top_label, top_count = max(counts.items(), key=lambda kv: kv[1])
    consensus_pct = round(100.0 * top_count / len(votes), 1)

    prev = sat["health"]
    sat["health"] = median_label
    sat["score"] = round(median_score, 3)
    sat["last_assessed"] = datetime.now(timezone.utc).strftime("%H:%M:%SZ")

    transition = None
    if prev != median_label:
        transition = f"{prev} → {median_label}"

    age, tid, see, wxf = base_factors(sat, wx)
    return {
        "votes": votes,
        "median_label": median_label,
        "median_score": round(median_score, 3),
        "consensus_pct": consensus_pct,
        "transition": transition,
        "factors": {
            "age": round(age, 3),
            "tid": round(tid, 3),
            "see": round(see, 3),
            "weather": round(wxf, 3),
        },
    }


# ============================================================================
# Health degradation — apply weather to sat dossiers over time.
# ============================================================================

def degrade_sat(sat: dict, wx: dict) -> None:
    """Slowly accumulate TID and occasionally roll a SEE based on weather."""
    # baseline dose: ~ 0.0008 krad per tick for LEO; doubled by Kp / SEP
    rate = {
        "LEO": 0.0006, "SSO": 0.0006, "MEO": 0.0011, "GEO": 0.0015,
    }.get(sat["regime"], 0.0006)
    factor = 1.0 + 0.6 * wx["kp"] / 9.0 + 0.4 * min(1.0, wx["sep_pfu"] / 100.0)
    sat["tid_accumulated_krad"] = min(
        sat["tid_budget_krad"] * 1.20,  # allow slight overage for BLACK
        sat["tid_accumulated_krad"] + rate * factor,
    )
    # SEE roll
    if random.random() < 0.0005 + 0.005 * (wx["sep_pfu"] / 1000.0):
        sat["see_events_30d"] += 1
    # passive SEE decay (~one decay per 30 ticks)
    if sat["see_events_30d"] > 0 and random.random() < 0.033:
        sat["see_events_30d"] -= 1


# ============================================================================
# Telemetry simulation for the focused-sat panel.
# ============================================================================

TELEMETRY: dict[str, dict] = {}
TELEMETRY_PTS = 90


def update_telemetry(sat: dict) -> None:
    t = TELEMETRY.setdefault(sat["id"], {
        "alt": deque(maxlen=TELEMETRY_PTS),
        "vel": deque(maxlen=TELEMETRY_PTS),
        "sig": deque(maxlen=TELEMETRY_PTS),
    })
    # altitude oscillates +/-2km around design alt
    base_alt = sat["altitude_km"]
    alt = base_alt + 1.6 * math.sin(time.time() / 90 + sat["inclination_deg"])
    # velocity from circular orbit approx v = sqrt(mu/r), mu_earth = 398600
    r_km = 6378 + base_alt
    vel = math.sqrt(398600 / r_km)
    # signal strength noise + health-driven floor
    sig_base = -55 - {"GREEN": 0, "YELLOW": 8, "RED": 18, "BLACK": 32}[sat["health"]]
    sig = sig_base + random.gauss(0, 1.5)
    t["alt"].append(round(alt, 2))
    t["vel"].append(round(vel, 3))
    t["sig"].append(round(sig, 1))


def telemetry_snapshot(sat_id: str) -> dict:
    t = TELEMETRY.get(sat_id, {})
    return {
        "alt": list(t.get("alt", [])),
        "vel": list(t.get("vel", [])),
        "sig": list(t.get("sig", [])),
    }


# ============================================================================
# Pub/sub bus.
# ============================================================================

class Bus:
    def __init__(self) -> None:
        self._subs: list[queue.Queue] = []
        self._lock = threading.Lock()
        self.alerts: deque = deque(maxlen=60)
        self.copilot_log: deque = deque(maxlen=80)
        self.start_ts = time.time()
        self.focused_sat: str = SATS[0]["id"]

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=512)
        with self._lock:
            self._subs.append(q)
        q.put(self.snapshot())
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)

    def publish(self, msg: dict) -> None:
        with self._lock:
            for q in list(self._subs):
                try:
                    q.put_nowait(msg)
                except queue.Full:
                    pass

    def snapshot(self) -> dict:
        return {
            "type": "snapshot",
            "sats": [public_sat(s) for s in SATS],
            "fleet_health": fleet_health_counts(),
            "weather": WEATHER.snapshot(),
            "focused": focused_sat_view(),
            "tokens": token_view(),
            "assessors": [{"id": a["id"], "family": a["family"], "bias": a["bias"]} for a in ASSESSORS],
            "copilot": list(self.copilot_log),
            "alerts": list(self.alerts),
            "uptime_s": int(time.time() - self.start_ts),
        }

    def copilot(self, who: str, msg: str, **extra) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).strftime("%H:%M:%S"),
            "who": who,
            "msg": msg,
            **extra,
        }
        self.copilot_log.append(entry)
        self.publish({"type": "copilot", "entry": entry})

    def alert(self, severity: str, message: str, sat_id: str | None = None) -> None:
        a = {
            "ts": datetime.now(timezone.utc).strftime("%H:%M:%S"),
            "severity": severity,
            "message": message,
            "sat_id": sat_id,
        }
        self.alerts.append(a)
        self.publish({"type": "alert", "alert": a})


BUS = Bus()


# ============================================================================
# View helpers.
# ============================================================================

HEALTH_COLOR = {"GREEN": "#3df0c8", "YELLOW": "#ffd166", "RED": "#ff6470", "BLACK": "#222"}


def public_sat(sat: dict) -> dict:
    age = sat_age_years(sat)
    return {
        "id": sat["id"],
        "name": sat["name"],
        "regime": sat["regime"],
        "operator": sat["operator"],
        "launched": sat["launched"],
        "age_years": round(age, 2),
        "design_life_years": sat["design_life_years"],
        "design_life_pct": round(100.0 * age / sat["design_life_years"], 1),
        "altitude_km": sat["altitude_km"],
        "inclination_deg": sat["inclination_deg"],
        "tid_budget_krad": sat["tid_budget_krad"],
        "tid_accumulated_krad": round(sat["tid_accumulated_krad"], 2),
        "tid_pct": round(100.0 * sat["tid_accumulated_krad"] / sat["tid_budget_krad"], 1),
        "see_events_30d": sat["see_events_30d"],
        "mission_type": sat["mission_type"],
        "lifecycle_stage": sat["lifecycle_stage"],
        "health": sat["health"],
        "score": sat["score"],
        "last_assessed": sat["last_assessed"],
    }


def fleet_health_counts() -> dict:
    counts = {"GREEN": 0, "YELLOW": 0, "RED": 0, "BLACK": 0}
    for s in SATS:
        counts[s["health"]] = counts.get(s["health"], 0) + 1
    return counts


def focused_sat() -> dict | None:
    for s in SATS:
        if s["id"] == BUS.focused_sat:
            return s
    return SATS[0]


def focused_sat_view() -> dict:
    s = focused_sat()
    pub = public_sat(s)
    pub["telemetry"] = telemetry_snapshot(s["id"])
    # current ensemble breakdown for the focused sat
    assessment = assess_focused_snapshot(s)
    pub["assessment"] = assessment
    return pub


def assess_focused_snapshot(sat: dict) -> dict:
    """Like assess_sat but does NOT mutate state or consume tokens.
    Just for displaying current votes.
    """
    wx = WEATHER.snapshot()
    votes = []
    scores = []
    # use deterministic snapshot (no noise) so the panel doesn't dance
    age, tid, see, wxf = base_factors(sat, wx)
    for m in ASSESSORS:
        sc = (
            m["weight_age"] * age * 0.40
            + m["weight_tid"] * tid * 0.35
            + 1.0 * see * 0.10
            + m["weight_wx"] * wxf * 0.45
        )
        label = "BLACK" if sc >= 1.10 else "RED" if sc >= 0.80 else "YELLOW" if sc >= 0.50 else "GREEN"
        votes.append({"model": m["id"], "family": m["family"], "label": label, "score": round(sc, 3)})
        scores.append(sc)
    counts: dict[str, int] = {}
    for v in votes:
        counts[v["label"]] = counts.get(v["label"], 0) + 1
    top_label, top_count = max(counts.items(), key=lambda kv: kv[1])
    return {
        "votes": votes,
        "consensus_label": top_label,
        "consensus_pct": round(100.0 * top_count / len(votes), 1),
        "factors": {
            "age": round(age, 3),
            "tid": round(tid, 3),
            "see": round(see, 3),
            "weather": round(wxf, 3),
        },
    }


def token_view() -> dict:
    pct = 100.0 * TOKEN_USAGE["spent"] / NIMBLE_DAILY_QUOTA
    return {
        "spent": TOKEN_USAGE["spent"],
        "quota": NIMBLE_DAILY_QUOTA,
        "pct": round(pct, 2),
        "calls": TOKEN_USAGE["calls"],
        "by_model": dict(TOKEN_USAGE["by_model"]),
        "rate_tokens_per_min": estimated_token_rate(),
        "history": list(TOKEN_USAGE["history"]),
    }


def estimated_token_rate() -> int:
    if not TOKEN_USAGE["history"]:
        return 0
    return int((TOKEN_USAGE["spent"] / max(1.0, (time.time() - BUS.start_ts))) * 60)


# ============================================================================
# Background loops.
# ============================================================================

_RUN_FLAG = {"value": True}


def assessment_loop() -> None:
    """Every ~2s: tick weather, degrade sats, run assessors, broadcast."""
    while True:
        if _RUN_FLAG["value"]:
            WEATHER.tick()
            for s in SATS:
                degrade_sat(s, WEATHER.snapshot())
                update_telemetry(s)
            wx = WEATHER.snapshot()

            # assess one sat per tick (round-robin) — keeps token usage modest
            sat = SATS[assessment_loop._idx % len(SATS)]  # type: ignore[attr-defined]
            assessment_loop._idx += 1                     # type: ignore[attr-defined]
            assessment = assess_sat(sat, wx)

            # surface transitions to copilot + alerts
            if assessment["transition"]:
                sev = {"GREEN": "INFO", "YELLOW": "MED", "RED": "HIGH", "BLACK": "HIGH"}[sat["health"]]
                BUS.alert(sev, f"{sat['name']} {assessment['transition']} (consensus {assessment['consensus_pct']}%)", sat["id"])
                if sat["health"] in ("RED", "BLACK"):
                    BUS.copilot("nemoclaw",
                        f"{sat['name']} now {sat['health']} (consensus {assessment['consensus_pct']}%). "
                        f"Driver: age {assessment['factors']['age']:.2f} · TID {assessment['factors']['tid']:.2f} · "
                        f"weather {assessment['factors']['weather']:.2f}. "
                        f"Recommend operator review.",
                        sat_id=sat["id"],
                        recommendation=("RETIRE" if sat["health"] == "BLACK" else "SAFE-MODE"))

            # write event row matching docs/EVENT_SCHEMA.md
            ev = {
                "schema_version": "v1.0",
                "event_id": f"on-orbit-ops-{sat['id']}-{int(time.time())}",
                "sat_id": sat["id"],
                "phase": "on-orbit-ops",
                "event_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "source_type": "derived",
                "source_url": None,
                "confidence": {"GREEN": "high", "YELLOW": "medium", "RED": "medium", "BLACK": "low"}[sat["health"]],
                "evidence_hash": hashlib.sha256(json.dumps(assessment, sort_keys=True).encode()).hexdigest(),
                "parser_version": "0.2.0",
                "recommendation": None,
                "review_status": "internal-log-only",
                "_health": sat["health"],
                "_consensus_pct": assessment["consensus_pct"],
            }
            with JSONL.open("a", encoding="utf-8") as f:
                f.write(json.dumps({k: v for k, v in ev.items() if not k.startswith("_")}) + "\n")

            # broadcast new fleet snapshot
            BUS.publish({
                "type": "fleet_update",
                "fleet_health": fleet_health_counts(),
                "weather": wx,
                "tokens": token_view(),
                "sats": [public_sat(s) for s in SATS],
                "focused": focused_sat_view(),
                "last_assessed": {"sat_id": sat["id"], "assessment": assessment, "health": sat["health"]},
            })
        time.sleep(1.8)


assessment_loop._idx = 0  # type: ignore[attr-defined]


def copilot_loop() -> None:
    """Inject the occasional operator command and proactive recommendation."""
    operator_commands = [
        "Status report for the worst-health sat.",
        "Any LEO drag concerns this hour?",
        "Token burn looking reasonable?",
        "Run conjunction triage on Starlink shell.",
        "What's the consensus on NOAA-18?",
    ]
    time.sleep(4)
    while True:
        if _RUN_FLAG["value"]:
            cmd = random.choice(operator_commands)
            BUS.copilot("user", cmd, who_label="S. Chen")
            time.sleep(random.uniform(2, 5))
            # synthesize a response based on current state
            worst = sorted(SATS, key=lambda s: -s["score"])[0]
            wx = WEATHER.snapshot()
            BUS.copilot("nemoclaw",
                f"Worst-health: {worst['name']} ({worst['health']}, score {worst['score']:.2f}). "
                f"Kp {wx['kp']}, X-ray {wx['xray_class']}, SEP {wx['sep_pfu']} pfu. "
                f"Fleet: {fleet_health_counts()}.",
                sat_id=worst["id"])
        time.sleep(random.uniform(20, 35))


def token_history_loop() -> None:
    """Every 5s push a token-rate sample for the gauge sparkline."""
    last = TOKEN_USAGE["spent"]
    while True:
        time.sleep(5)
        delta = TOKEN_USAGE["spent"] - last
        last = TOKEN_USAGE["spent"]
        TOKEN_USAGE["history"].append({"t": int(time.time()), "delta": delta, "spent": TOKEN_USAGE["spent"]})
        BUS.publish({"type": "tokens", "tokens": token_view()})


# ============================================================================
# Terminal commands.
# ============================================================================

TERMINAL_HELP = """available commands:
  help                this text
  status              fleet health + worst sat + Kp / X-ray / SEP
  list [color]        list sats, optionally filter by GREEN|YELLOW|RED|BLACK
  focus <name|id>     focus a satellite (drives the right-side panel)
  show <name|id>      same as focus
  weather             dump current space-weather inputs
  storm [kind]        manually trigger a storm (flare|cme|sep|geomag)
  tokens              show Nimble Cloud token usage
  models              list assessor models and their biases
  events [N]          tail N event rows
  alerts [N]          tail N alerts
  approve             approve the latest copilot recommendation (simulated)
  start | stop        resume / pause the assessor loop
  clear               clear local terminal (UI only)
"""


def find_sat(needle: str) -> dict | None:
    needle = needle.upper()
    for s in SATS:
        if s["id"] == needle or s["name"].upper() == needle or needle in s["name"].upper():
            return s
    return None


def run_terminal_command(line: str) -> str:
    line = line.strip()
    if not line: return ""
    parts = line.split()
    cmd = parts[0].lower()
    args = parts[1:]

    if cmd in ("help", "?"): return TERMINAL_HELP
    if cmd == "clear": return "__CLEAR__"
    if cmd == "status":
        wx = WEATHER.snapshot()
        worst = sorted(SATS, key=lambda s: -s["score"])[0]
        return (f"fleet : {fleet_health_counts()}\n"
                f"worst : {worst['name']} ({worst['health']} score {worst['score']:.2f})\n"
                f"wx    : Kp {wx['kp']}  X-ray {wx['xray_class']}  SEP {wx['sep_pfu']} pfu  AE {wx['ae']} nT\n"
                f"focus : {focused_sat()['name']}  uptime {int(time.time() - BUS.start_ts)}s")
    if cmd == "list":
        color = args[0].upper() if args else None
        lines = []
        for s in SATS:
            if color and s["health"] != color: continue
            lines.append(f"  {s['health']:6s} {s['name']:18s} {s['regime']:3s}  "
                         f"age {sat_age_years(s):5.1f}/{s['design_life_years']}y  "
                         f"TID {s['tid_accumulated_krad']:6.2f}/{s['tid_budget_krad']:.0f}  "
                         f"score {s['score']:.2f}")
        return "\n".join(lines) or "(no sats matched)"
    if cmd in ("focus", "show"):
        if not args: return "usage: focus <name|id>"
        sat = find_sat(args[0])
        if not sat: return f"no sat matching '{args[0]}'"
        BUS.focused_sat = sat["id"]
        BUS.publish({"type": "focus_change", "focused": focused_sat_view()})
        return f"focused on {sat['name']} (id {sat['id']})"
    if cmd == "weather":
        wx = WEATHER.snapshot()
        return (f"Kp        : {wx['kp']}\n"
                f"X-ray     : {wx['xray_class']} ({wx['xray']:.2e} W/m²)\n"
                f"SEP > 10MeV : {wx['sep_pfu']} pfu\n"
                f"AE        : {wx['ae']} nT\n"
                f"storm     : {wx['storm_regime'] or 'none'}")
    if cmd == "storm":
        kind = args[0].lower() if args else random.choice(["flare", "cme", "sep", "geomag"])
        mapping = {
            "flare": "solar-flare", "cme": "cme-impact",
            "sep": "sep-event", "geomag": "geomagnetic-storm",
        }
        if kind not in mapping: return "usage: storm [flare|cme|sep|geomag]"
        WEATHER._spawn_event = (lambda _orig=WEATHER._spawn_event, kk=mapping[kind]:
                                _trigger_named_storm(kk))
        WEATHER._spawn_event()
        return f"triggered {mapping[kind]}"
    if cmd == "tokens":
        t = token_view()
        per_model = "\n".join(f"  {m:18s} {n:>10,}" for m, n in t["by_model"].items())
        return (f"Nimble Cloud daily quota : {t['quota']:,}\n"
                f"spent                    : {t['spent']:,} ({t['pct']:.1f}%)\n"
                f"calls                    : {t['calls']:,}\n"
                f"rate                     : ~{t['rate_tokens_per_min']:,}/min\n"
                f"per model:\n{per_model}")
    if cmd == "models":
        return "\n".join(f"  {a['id']:18s} {a['family']:18s} bias={a['bias']}" for a in ASSESSORS)
    if cmd == "events":
        n = int(args[0]) if args else 5
        try:
            with JSONL.open("r", encoding="utf-8") as f:
                lines = f.readlines()[-n:]
            return "".join(lines).rstrip()
        except FileNotFoundError:
            return "(no events yet)"
    if cmd == "alerts":
        n = int(args[0]) if args else 5
        return "\n".join(f"[{a['ts']}] {a['severity']:4s} {a['message']}" for a in list(BUS.alerts)[-n:]) or "(none)"
    if cmd == "approve":
        BUS.copilot("user", "approve recommendation", who_label="S. Chen")
        BUS.copilot("nemoclaw", "Approved — command sent to NemoClaw audit.", action="APPROVED")
        return "approved"
    if cmd == "start":
        _RUN_FLAG["value"] = True
        return "assessor loop resumed"
    if cmd == "stop":
        _RUN_FLAG["value"] = False
        return "assessor loop paused"
    return f"unknown command: {cmd}  (try `help`)"


def _trigger_named_storm(kind: str) -> None:
    if kind == "solar-flare":
        WEATHER.xray = random.uniform(1e-5, 5e-4)
    elif kind == "cme-impact":
        WEATHER.kp = random.uniform(6.5, 8.8); WEATHER.ae = random.uniform(1000, 2000)
    elif kind == "sep-event":
        WEATHER.sep_pfu = random.uniform(200, 2000)
    elif kind == "geomagnetic-storm":
        WEATHER.kp = random.uniform(6.0, 8.0)
    WEATHER.regime_in_storm = "ALL"
    BUS.copilot("nemoclaw", f"Operator-triggered {kind}.")


# ============================================================================
# HTTP.
# ============================================================================

class Handler(BaseHTTPRequestHandler):
    server_version = "Spacesharks/0.2"

    def log_message(self, *a, **kw):  # quiet
        pass

    def _send_json(self, obj, status=200) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try: self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError): pass

    def _send_file(self, path: Path, ctype: str) -> None:
        if not path.exists(): self.send_error(404); return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try: self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError): pass

    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"): self._send_file(WEB / "index.html", "text/html; charset=utf-8"); return
        if path == "/styles.css":         self._send_file(WEB / "styles.css", "text/css; charset=utf-8"); return
        if path == "/app.js":             self._send_file(WEB / "app.js", "application/javascript; charset=utf-8"); return
        if path == "/api/state":          self._send_json(BUS.snapshot()); return
        if path == "/api/stream":         self._serve_sse(); return
        self.send_error(404)

    def _serve_sse(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        q = BUS.subscribe()
        last_ping = time.time()
        try:
            while True:
                try:
                    msg = q.get(timeout=10)
                    self.wfile.write(f"data: {json.dumps(msg)}\n\n".encode("utf-8"))
                    self.wfile.flush()
                except queue.Empty:
                    pass
                if time.time() - last_ping > 15:
                    self.wfile.write(b": ping\n\n"); self.wfile.flush()
                    last_ping = time.time()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            BUS.unsubscribe(q)

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        try: body = json.loads(raw)
        except json.JSONDecodeError: self._send_json({"error": "bad json"}, status=400); return

        if self.path == "/api/exec":
            self._send_json({"cmd": body.get("cmd", ""), "output": run_terminal_command(body.get("cmd", ""))})
            return
        if self.path == "/api/focus":
            sat = find_sat(str(body.get("sat", "")))
            if not sat:
                self._send_json({"error": "sat not found"}, status=404); return
            BUS.focused_sat = sat["id"]
            BUS.publish({"type": "focus_change", "focused": focused_sat_view()})
            self._send_json({"focused": sat["id"]})
            return
        if self.path == "/api/approve":
            BUS.copilot("user", "approve recommendation", who_label="S. Chen")
            BUS.copilot("nemoclaw", "Approved — command queued to NemoClaw audit.", action="APPROVED")
            self._send_json({"ok": True}); return
        if self.path == "/api/storm":
            kind = body.get("kind", "flare")
            run_terminal_command(f"storm {kind}")
            self._send_json({"ok": True}); return
        self.send_error(404)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")))
    p.add_argument("--host", default="127.0.0.1")
    args = p.parse_args()

    # Seed initial telemetry so the focused panel isn't empty.
    for s in SATS:
        for _ in range(20):
            update_telemetry(s)

    threading.Thread(target=assessment_loop, daemon=True).start()
    threading.Thread(target=copilot_loop, daemon=True).start()
    threading.Thread(target=token_history_loop, daemon=True).start()

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[spacesharks-desk] http://{args.host}:{args.port}/  (writing {JSONL})", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("[spacesharks-desk] shutting down", file=sys.stderr)


if __name__ == "__main__":
    main()
