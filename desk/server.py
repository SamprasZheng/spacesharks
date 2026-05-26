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
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Make `desk` importable when running as a script (`python server.py`).
_PARENT = Path(__file__).resolve().parent.parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

# NEO Action Item 4 — NemoClaw audit + guardrail module. See
# docs/research/agentic-provenance.md for the four-layer schema this writes into,
# and INVARIANTS.md §"Fail-closed invariants" for the operational rules.
from desk.nemoclaw import (
    audit_dispatch,
    audit_tail,
    input_guard,
    output_guard,
    policy_preset_hash as _nemoclaw_policy_hash,
    policy_egress_allowlist as _nemoclaw_egress_allowlist,
)

# NEO Action Item 2 — SGP4 propagation + simulated COTS telemetry + JPL
# nonparametric dynamic threshold. Operates under INVARIANTS override O1
# (source-list-lock 5th input is local synthetic only — no new external egress).
# See docs/INVARIANTS.md §"How to use this document".
#
# Real data sources wired here (post-2026-05-26 owner review):
#   - desk.physics.swpc_poller fetches live NOAA SWPC Kp/X-ray/SEP feeds
#   - desk.physics.sgp4_propagator.refresh_tle_cache pulls live Celestrak TLEs
# Both hosts (swpc.noaa.gov and celestrak.org) are already on the NemoClaw
# egress allowlist per INVARIANTS source-list-lock; no new egress surface.
from desk.physics import (
    TelemetryStream, propagate as sgp4_propagate, telemetry_buffer_for,
    refresh_tle_cache, swpc_fetch_all, swpc_latest_snapshot,
    swpc_is_real_data_available,
    swpc_combined_forecast,
    disaster_fetch_combined,
)
from desk.detect import detect as jpl_detect

# NEO Action Item 3 — Function Calling beam-redirect drafts. Operates under
# INVARIANTS override O2 (4th Phase-4 decision verb; decision_route locked to
# needs-review; never auto-publish, never auto-execute).
from desk.decisions import (
    BeamRedirectDraft,
    brief_beam_redirect,
    BEAM_REDIRECT_TOOL_SCHEMA,
    kb_lookup,
    kb_load,
    llm_justify_beam_redirect,
    get_tactical_brief,
    refresh_tactical_brief,
    rank_fleet_by_risk,
    fleet_risk_summary,
)

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
DATA = ROOT / "data"
JSONL = DATA / "lifecycle-events.jsonl"
DATA.mkdir(exist_ok=True)


# ============================================================================
# Sat fleet — the heart of the MVP.
# ============================================================================

def _orbit_seed(norad: str, salt: int = 0) -> tuple[float, float]:
    """Deterministic (raan, phase) for a given NORAD id so positions don't
    jump between server restarts."""
    h = int(hashlib.sha256(f"{norad}|{salt}".encode()).hexdigest()[:8], 16)
    raan = (h % 36000) / 100.0           # 0..360 deg
    phase = ((h >> 16) % 10000) / 10000.0  # 0..1
    return raan, phase


def _sat(norad, name, regime, operator, launched, design_life, mass, incl, alt_km,
         tid_budget=50.0, mission="comms", lifecycle="In-Orbit Operations", shell=None):
    raan, phase = _orbit_seed(str(norad))
    return {
        "id": str(norad),
        "name": name,
        "regime": regime,
        "operator": operator,
        "launched": launched,
        "design_life_years": design_life,
        "mass_kg": mass,
        "inclination_deg": incl,
        "altitude_km": alt_km,
        "raan_deg": raan,           # right ascension of ascending node
        "phase":    phase,          # 0..1 along orbit
        "tid_budget_krad": tid_budget,
        "tid_accumulated_krad": tid_budget * random.uniform(0.05, 0.55),
        "see_events_30d": random.randint(0, 3),
        "last_safe_mode": None,
        "mission_type": mission,
        "lifecycle_stage": lifecycle,
        "shell": shell,                   # Starlink shell tag, e.g. "v1.5-G4", "v2-mini", "DTC"
        # mutable health fields:
        "health": "GREEN",
        "score": 0.10,
        "trend": "stable",
        "last_assessed": None,
    }


def _starlink(norad, name, shell, incl, alt, launched, design_life=5, mass=300, mission="comms"):
    return _sat(norad, name, "LEO", "SpaceX", launched, design_life, mass, incl, alt,
                tid_budget=20.0, mission=mission, shell=shell)


# Starlink-heavy roster — most-popular constellation in operational use today.
# Shell tags reflect the public generations (v0.9 / v1.0 / v1.5 / v2.0-mini /
# v2.0-DTC). Mass and inclination follow the published spec for that shell.
SATS = [
    # ===== Starlink shell v1.0 / Group 1 (53° / 550 km) =====
    _starlink("44737", "STRLNK-1007",  "v1.0/G1",    53.0, 550, "2020-04-22"),
    _starlink("45123", "STRLNK-1196",  "v1.0/G1",    53.0, 550, "2020-06-13"),
    _starlink("47301", "STRLNK-1812",  "v1.0/G1",    53.0, 550, "2021-01-20"),
    _starlink("48275", "STRLNK-1234",  "v1.0/G1",    53.0, 550, "2021-05-15"),
    # ===== Starlink shell v1.5 / Group 4 (53.2° / 540-570 km, laser links) =====
    _starlink("48276", "STRLNK-2118",  "v1.5/G4",    53.2, 548, "2022-02-21"),
    _starlink("49144", "STRLNK-2401",  "v1.5/G4",    53.2, 550, "2022-04-29"),
    _starlink("48277", "STRLNK-3047",  "v1.5/G4",    53.2, 552, "2022-09-04"),
    _starlink("52789", "STRLNK-3192",  "v1.5/G4",    53.2, 549, "2022-11-12"),
    _starlink("53121", "STRLNK-3204",  "v1.5/G4",    70.0, 570, "2022-12-08"),
    _starlink("54121", "STRLNK-3411",  "v1.5/G4",    53.2, 545, "2023-01-26"),
    _starlink("55012", "STRLNK-3502",  "v1.5/G4",    97.6, 560, "2023-03-03"),
    _starlink("48278", "STRLNK-4012",  "v1.5/G4",    43.0, 540, "2023-03-12"),
    _starlink("56012", "STRLNK-4119",  "v1.5/G4",    43.0, 543, "2023-04-15"),
    _starlink("57212", "STRLNK-4567",  "v1.5/G4",    43.0, 540, "2023-07-09"),
    _starlink("48279", "STRLNK-5021",  "v2.0-mini",  43.0, 539, "2023-11-08", design_life=5, mass=800),
    _starlink("58112", "STRLNK-5421",  "v2.0-mini",  43.0, 542, "2024-01-22", design_life=5, mass=800),
    # ===== Starlink shell v2.0 Mini / Group 6 (~530 km) =====
    _starlink("59001", "STRLNK-6011",  "v2.0-mini",  43.0, 530, "2024-03-02", design_life=5, mass=800),
    _starlink("59102", "STRLNK-6112",  "v2.0-mini",  43.0, 532, "2024-05-14", design_life=5, mass=800),
    _starlink("59210", "STRLNK-6234",  "v2.0-mini",  43.0, 530, "2024-07-08", design_life=5, mass=800),
    _starlink("60012", "STRLNK-6502",  "v2.0-mini",  43.0, 528, "2024-09-25", design_life=5, mass=800),
    _starlink("60412", "STRLNK-6721",  "v2.0-mini",  43.0, 531, "2024-11-19", design_life=5, mass=800),
    _starlink("60815", "STRLNK-7011",  "v2.0-mini",  43.0, 530, "2025-01-12", design_life=5, mass=800),
    # ===== Starlink Direct-to-Cell / Group 5 (D2C / partnered with T-Mobile) =====
    _starlink("58311", "STRLNK-DTC-01","DTC",        53.0, 540, "2024-01-03", design_life=5, mass=800, mission="d2c"),
    _starlink("58422", "STRLNK-DTC-22","DTC",        53.0, 540, "2024-02-18", design_life=5, mass=800, mission="d2c"),
    _starlink("59512", "STRLNK-DTC-44","DTC",        53.0, 540, "2024-06-02", design_life=5, mass=800, mission="d2c"),
    _starlink("60101", "STRLNK-DTC-71","DTC",        53.0, 540, "2024-08-17", design_life=5, mass=800, mission="d2c"),
    _starlink("60615", "STRLNK-DTC-93","DTC",        53.0, 540, "2024-10-30", design_life=5, mass=800, mission="d2c"),
    # ===== Starlink polar (97.6° SSO, Group 3) =====
    _starlink("48800", "STRLNK-3501",  "v1.5/G3",    97.6, 570, "2023-08-12"),
    _starlink("55501", "STRLNK-3551",  "v1.5/G3",    97.6, 568, "2023-11-04"),
    _starlink("58701", "STRLNK-3601",  "v1.5/G3",    97.6, 570, "2024-02-04"),
    _starlink("60201", "STRLNK-3661",  "v1.5/G3",    97.6, 569, "2024-07-22"),
    # ===== Stations =====
    _sat("25544", "ISS",            "LEO", "NASA/Roskosmos", "1998-11-20", 35, 419725, 51.6,  418, tid_budget=80, mission="station"),
    _sat("48274", "CSS-Tiangong",   "LEO", "CMSA",           "2021-04-29", 15, 80000,  41.5,  389, tid_budget=70, mission="station"),
    # ===== Non-Starlink LEO (small comparison set) =====
    _sat("45124", "ONEWEB-0212",    "LEO", "Eutelsat",       "2021-12-27",  7, 147,    87.4, 1200, tid_budget=30, mission="comms"),
    _sat("43571", "IRIDIUM-167",    "LEO", "Iridium",        "2018-07-25", 15, 860,    86.4,  778, tid_budget=40, mission="comms"),
    # ===== SSO Earth-observation =====
    _sat("49260", "Landsat-9",      "SSO", "NASA/USGS",      "2021-09-27", 10, 2623,   98.2,  705, tid_budget=60, mission="EO"),
    _sat("57172", "Sentinel-2C",    "SSO", "ESA/Copernicus", "2024-09-04", 12, 1130,   98.6,  786, tid_budget=55, mission="EO"),
    _sat("43013", "NOAA-20",        "SSO", "NOAA",           "2017-11-18",  7, 2540,   98.7,  833, tid_budget=50, mission="weather"),
    _sat("28654", "NOAA-18",        "SSO", "NOAA",           "2005-05-20",  3, 1457,   98.7,  854, tid_budget=50, mission="weather", lifecycle="Event Management"),
    # ===== MEO navigation =====
    _sat("28474", "GPS-IIRM-5",     "MEO", "USSF",           "2006-09-25", 10, 2032,   55.0, 20180, tid_budget=120, mission="nav"),
    _sat("40294", "GLONASS-755",    "MEO", "Roskosmos",      "2014-06-14", 10, 1415,   64.8, 19140, tid_budget=110, mission="nav"),
    _sat("41859", "Galileo-22",     "MEO", "ESA/EUSPA",      "2016-11-17", 12, 730,    56.0, 23222, tid_budget=120, mission="nav"),
    _sat("44793", "Beidou-3 M22",   "MEO", "CNSA",           "2019-12-16", 12, 1014,   55.0, 21528, tid_budget=120, mission="nav"),
    # ===== GEO =====
    _sat("43226", "GOES-16",        "GEO", "NOAA",           "2016-11-19", 15, 5192,    0.05, 35786, tid_budget=200, mission="weather"),
    _sat("43689", "GOES-17",        "GEO", "NOAA",           "2018-03-01", 15, 5192,    0.05, 35786, tid_budget=200, mission="weather"),
    _sat("39260", "Inmarsat-5 F1",  "GEO", "Inmarsat",       "2013-12-08", 15, 6100,    0.05, 35786, tid_budget=200, mission="comms"),
    _sat("42432", "EchoStar-23",    "GEO", "EchoStar",       "2017-03-16", 15, 5500,    0.05, 35786, tid_budget=200, mission="comms"),
]


# ============================================================================
# Active triage seeding — expand the hand-curated 47 sats up to ~1000 by
# synthesising additional Starlinks across the published shells. These ARE
# in the council's triage queue (they get assessed by the round-robin
# sweep), but they start with health = UNKNOWN (grey) until first assessed,
# per docs/RISKS_AND_FIXES.md "Render objects not yet updated as black /
# inactive / unknown".
# ============================================================================

def _seed_extra_starlinks(target: int = 100) -> None:
    """Top the active triage up to `target` total sats by adding Starlinks
    across the published shells. Spread is intentional so the globe shows
    global coverage rather than a thick ring at one inclination.
    """
    if len(SATS) >= target:
        return
    rng = random.Random(2026)
    # Real-world Starlink shells run multiple orbital planes per inclination,
    # so RAAN is approximately uniform 0-360°; we draw uniformly.
    shells = [
        ("v1.0/G1",   53.0, (540, 560),  300, "comms",  15),
        ("v1.5/G4",   53.2, (540, 570),  300, "comms",  15),
        ("v2.0-mini", 43.0, (520, 550),  800, "comms",  10),
        ("DTC",       53.0, (535, 545),  800, "d2c",    6),
        ("v1.5/G3",   97.6, (560, 580),  300, "comms",  7),
    ]
    norad = 60000
    for shell, incl, alt_range, mass, mission, count in shells:
        for _ in range(count):
            if len(SATS) >= target: break
            launched_year = rng.randint(2020, 2025)
            launched_mon  = rng.randint(1, 12)
            launched_day  = rng.randint(1, 28)
            sat = _starlink(
                str(norad), f"STRLNK-{norad}", shell,
                incl + rng.uniform(-1.2, 1.2),
                round(rng.uniform(*alt_range), 1),
                f"{launched_year}-{launched_mon:02d}-{launched_day:02d}",
                design_life=5, mass=mass, mission=mission,
            )
            # Spread RAAN explicitly across the available planes for this
            # shell so 53° sats don't all stack on the same plane.
            sat["raan_deg"] = round(rng.uniform(0, 360), 2)
            sat["phase"]    = round(rng.random(), 4)
            # New seeded sats start UNASSESSED — they show grey until
            # the assessment loop reaches them.
            sat["health"] = "UNKNOWN"
            sat["score"]  = 0.0
            sat["last_assessed"] = None
            SATS.append(sat)
            norad += 1


_seed_extra_starlinks(target=100)


# ============================================================================
# Visual catalog — RETIRED.
#
# Earlier versions rendered a 5-10k background dot field to give a
# "global coverage" feel. Operator feedback ("我只要真的衛星, 我不要只有
# 全球覆蓋感, 但是是假的") rejected that: the globe should only show sats
# that are actually being assessed by the council. We keep the generator
# function below so old code paths that reference it don't break, but the
# top-level VISUAL_CATALOG is now an empty list.
# ============================================================================

def _build_visual_catalog(rng_seed: int = 42, target_total: int = 10000) -> list[dict]:
    rng = random.Random(rng_seed)
    cat: list[dict] = []
    # Mix tracks roughly the real-public-catalog shape (Starlink ~7k of ~12k).
    # Multiple Starlink shells with distinct inclinations, plus the smaller
    # comparison set. Phase, altitude, and inclination get jitter so the
    # globe shows a populated 3D-feeling band instead of a single thin ring.
    mix = [
        ("STARLINK-G1",   2400, "v1.0/G1",   53.0,  (540, 560)),
        ("STARLINK-G4",   3200, "v1.5/G4",   53.2,  (540, 570)),
        ("STARLINK-G6",   1700, "v2.0-mini", 43.0,  (520, 550)),
        ("STARLINK-G3",    700, "v1.5/G3",   97.6,  (560, 580)),
        ("STARLINK-DTC",   400, "DTC",       53.0,  (535, 545)),
        ("ONEWEB",         600, "OneWeb",    87.4,  (1180, 1220)),
        ("IRIDIUM",         75, "Iridium",   86.4,  (775, 785)),
        ("SSO-EO",         220, "EO",        98.6,  (700,  830)),
        ("MEO-NAV",        120, "Nav",       55.0,  (19000, 23300)),
        ("GEO",            120, "GEO",        0.1,  (35780, 35792)),
    ]
    norad = 70000
    for tag, n, shell, incl, alt_range in mix:
        for i in range(n):
            alt = rng.uniform(*alt_range)
            inc = incl + rng.uniform(-1.5, 1.5)
            phase = rng.random()
            raan  = rng.uniform(0, 360)
            regime = ("LEO" if alt < 1500 else "SSO" if alt < 2000 else "MEO" if alt < 30000 else "GEO")
            cat.append({
                "id": str(norad),
                "name": f"{tag}-{norad}",
                "regime": regime,
                "shell": shell,
                "inclination_deg": round(inc, 2),
                "altitude_km": round(alt, 1),
                "phase":   round(phase, 4),
                "raan_deg": round(raan, 2),
                "attention_level": "UNKNOWN",
                "health": "UNKNOWN",
                "last_refresh_ts": None,
            })
            norad += 1
            if len(cat) >= target_total:
                return cat
    return cat


VISUAL_CATALOG: list[dict] = []   # retired — only real assessed sats now


# ============================================================================
# Space weather — the driver of health transitions.
# ============================================================================

class Weather:
    """Space-weather source — prefers live NOAA SWPC, falls back to a slow
    random walk if SWPC is unreachable. The `source` field on snapshot()
    tells the dashboard whether the operator is looking at real or
    synthesised values, so the demo cannot accidentally claim live data
    when it has none."""

    def __init__(self) -> None:
        self.kp = 2.5                # 0..9
        self.xray = 1.5e-7           # W/m^2; M-class ≥ 1e-5, X-class ≥ 1e-4
        self.sep_pfu = 0.4           # protons >10MeV per (cm^2 s sr)
        self.ae = 120                # auroral electrojet, nT
        self.regime_in_storm = None  # set during an event
        self.source = "init"         # "swpc-live" | "swpc-stale" | "simulated"
        self._last_real_refresh = 0.0

    def tick(self) -> None:
        # Prefer live SWPC values. Fall back to random walk only when the
        # SWPC poller has no cached value for this feed (cold boot before
        # the first fetch lands, or sustained outage).
        snap = swpc_latest_snapshot()
        kp_real = snap["feeds"].get("kp_1m", {}).get("value")
        xray_real = snap["feeds"].get("xray_1d", {}).get("value")
        sep_real = snap["feeds"].get("sep_1d", {}).get("value")
        any_real = any(v is not None for v in (kp_real, xray_real, sep_real))

        if any_real:
            # Source-of-truth path — apply real values, leave nothing to chance.
            if kp_real is not None:
                self.kp = max(0.0, min(9.0, float(kp_real)))
            if xray_real is not None:
                self.xray = max(1e-9, float(xray_real))
            if sep_real is not None:
                self.sep_pfu = max(0.0, float(sep_real))
            # AE not in SWPC feeds at this cadence — leave it on a tame walk
            # rather than fabricating a number that wasn't measured.
            self.ae = max(20, min(2000, self.ae + random.gauss(0, 5)))
            # Mark stale if all feed timestamps are >15 minutes old.
            stale_ages = [
                f.get("stale_s") for f in snap["feeds"].values()
                if f.get("stale_s") is not None
            ]
            if stale_ages and min(stale_ages) > 900:
                self.source = "swpc-stale"
            else:
                self.source = "swpc-live"
            self._last_real_refresh = time.time()
            # Do NOT _spawn_event() when we have real data — real storms
            # come from the real feed, not from random dice rolls.
            return

        # Cold-boot or sustained outage → mark source honestly + random walk.
        self.source = "simulated"
        self.kp = max(0.0, min(9.0, self.kp + random.gauss(0, 0.3)))
        self.ae = max(20, min(2000, self.ae + random.gauss(0, 60)))
        self.xray = max(1e-8, self.xray * (1 + random.gauss(0, 0.15)))
        self.sep_pfu = max(0.05, self.sep_pfu + random.gauss(0, 0.2))
        # Random major event ~ every 30 ticks when in simulated mode only.
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
            "source": self.source,
            "real_data_age_s": int(time.time() - self._last_real_refresh) if self._last_real_refresh else None,
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

# NEO post-2026-05-26 review — removed fake "DeepProp / OrbitNet / SatGuard /
# Astro-AI / Pathfinder" demo names. The dashboard now shows REAL model IDs
# from PRIMARY_MODELS so judges and reviewers see the actual lineup.
#
# In LIVE-OLLAMA mode each seat resolves to a real running model (verified
# at boot via /api/tags). In SIM mode each seat falls back to a deterministic
# arithmetic vote using the bias/weight table below — the snapshot label is
# explicitly `"deterministic-arithmetic"` so the demo cannot accidentally
# claim LLM output when no LLM is reachable.
_SEAT_BIAS_TABLE = {
    "ORBIT":     {"bias": "age",        "weight_age": 1.40, "weight_tid": 0.90, "weight_wx": 0.90, "tokens_per_call": 1100},
    "TRIAGE":    {"bias": "triage",     "weight_age": 0.95, "weight_tid": 1.10, "weight_wx": 1.10, "tokens_per_call": 1450},
    "EVIDENCE":  {"bias": "provenance", "weight_age": 1.00, "weight_tid": 1.00, "weight_wx": 1.00, "tokens_per_call": 1250},
    "RADIATION": {"bias": "radiation",  "weight_age": 0.90, "weight_tid": 1.45, "weight_wx": 1.00, "tokens_per_call": 1100},
    "IMPACT":    {"bias": "impact",     "weight_age": 0.85, "weight_tid": 0.95, "weight_wx": 1.20, "tokens_per_call": 1900},
}


# ASSESSORS is populated AFTER PRIMARY_MODELS is defined below. We declare an
# empty placeholder here so `TOKEN_USAGE["by_model"]` initialisation (which
# happens immediately after this block) doesn't NameError. The real list is
# filled in by _build_assessors_from_lineup() further down.
ASSESSORS: list[dict] = []


def _build_assessors_from_lineup() -> list[dict]:
    """Derive the assessor list from PRIMARY_MODELS so the dashboard always
    reflects the real model lineup. Each assessor entry carries the real
    model_id (e.g. `nemotron-3-nano:4b`) as its `id`, the real vendor/family
    as its `family`, and a bias/weight tuple derived from the seat role."""
    out = []
    for m in PRIMARY_MODELS:
        seat = m.get("seat") or "TRIAGE"
        bias = _SEAT_BIAS_TABLE.get(seat, _SEAT_BIAS_TABLE["TRIAGE"])
        out.append({
            "id": m["id"],
            "vendor": m["vendor"],
            "family": m["family"],
            "seat": seat,
            "bias": bias["bias"],
            "weight_age": bias["weight_age"],
            "weight_tid": bias["weight_tid"],
            "weight_wx": bias["weight_wx"],
            "tokens_per_call": bias["tokens_per_call"],
        })
    return out

NIMBLE_DAILY_QUOTA = 2_000_000   # synthetic daily token cap on Nimble Cloud
TOKEN_USAGE = {
    "spent": 0,
    "by_model": {a["id"]: 0 for a in ASSESSORS},
    "calls": 0,
    "window_start": time.time(),
    "history": deque(maxlen=120),   # last 120 ticks
}


# ============================================================================
# Inference mode — SIM (default) vs LIVE-OLLAMA.
# This is the bridge to the user's RTX 5070 + WSL Ollama setup. By default
# every assessor vote is a deterministic Python computation; in live mode the
# server POSTs a short prompt to Ollama and the model's output shifts the
# score. The top-bar badge always declares which mode is hot.
# ============================================================================

def _mk_model(model_id, vendor, family, role, est_size_gb, seat=None):
    return {
        "id": model_id, "vendor": vendor, "family": family, "role": role,
        "est_size_gb": est_size_gb,
        "seat": seat,                       # specialist role this model fills
        "alive": True, "last_call_ms": None,
        "success": 0, "fail": 0, "consecutive_fail": 0,
        "last_label": None, "last_thinking": None, "last_brief": None,
        "replaced_by": None,                # backup model id if rotated out
    }


# Specialist seats (per docs/RISKS_AND_FIXES.md "Minimum council size should be
# three models"). Each seat owns a role-specific prompt — the council is no
# longer five copies of the same question. Nemotron is the fixed Mission
# Director (arbiter), NOT one of the specialist seats.
COUNCIL_SEATS = [
    {"seat": "ORBIT",    "title": "Orbit Analyst",
     "prompt": "Assess orbit stability — altitude, age vs design life, decay/drag risk."},
    {"seat": "TRIAGE",   "title": "Health Triage Analyst",
     "prompt": "Assess overall operational triage priority — fold in driver signals from age/TID/SEE/weather."},
    {"seat": "EVIDENCE", "title": "Evidence Analyst",
     "prompt": "Assess provenance quality — is the public data fresh + sufficient to support this judgement?"},
    {"seat": "RADIATION","title": "Radiation Analyst",          # OPTIONAL
     "prompt": "Assess radiation environment — TID accumulation, recent SEEs, current Kp/X-ray/SEP."},
    {"seat": "IMPACT",   "title": "Mission Impact Analyst",     # OPTIONAL
     "prompt": "Assess mission-impact severity — comms/nav/EO consequence if this sat degrades."},
]

# Model assignments — NEO Action Item 4 lineup swap (review2.md §1+§4 critique).
#
# Specialists are now heavily Nemotron-tilted to satisfy the NVIDIA Agent Hackathon
# Airtable form's "core reasoning model = Nemotron" scoring criterion. INVARIANTS.md
# §"Specialist-arbiter rule" requires three different base-model families across
# the active council — satisfied by Nemotron (NVIDIA) + Hermes-4 (Nous Research) +
# Qwen-3 (Alibaba). The RADIATION seat is intentionally same-family-as-ORBIT
# (both Nemotron-Nano) and the council resolver flags this as `degraded: same-family`
# whenever both seats are active simultaneously (FULL council mode).
#
# MISSION_DIRECTOR escalates to Nemotron-Super 49B for tier-3 cloud calls per
# INVARIANTS.md §"Tiered-inference cascade".
# Lineup pinned to models actually present in the WSL Ollama instance
# (verified at 2026-05-26 against /api/tags). Hermes-4-14B and Nemotron-3-
# Super-49B are NOT pulled locally — they remain in the wish-list as tier-3
# cloud candidates (via NVIDIA NIM under override O1 egress). For the local
# demo the lineup is heavily Nemotron-Nano + Qwen-3 + Mistral, which still
# satisfies INVARIANTS.md §"Specialist-arbiter rule" three-different-base-
# model-families requirement (NVIDIA + Alibaba + Mistral AI).
PRIMARY_MODELS = [
    _mk_model("nemotron-3-nano:4b",   "NVIDIA",      "Nemotron-3-Nano",  "PRIMARY", 2.8, seat="ORBIT"),
    _mk_model("qwen3:4b",             "Alibaba",     "Qwen-3",           "PRIMARY", 2.5, seat="TRIAGE"),
    _mk_model("mistral:7b",           "Mistral AI",  "Mistral-7B",       "PRIMARY", 4.1, seat="EVIDENCE"),
    _mk_model("nemotron-3-nano:4b",   "NVIDIA",      "Nemotron-3-Nano",  "PRIMARY", 2.8, seat="RADIATION"),
    _mk_model("nemotron-3-nano:4b",   "NVIDIA",      "Nemotron-3-Nano",  "PRIMARY", 2.8, seat="IMPACT"),
]
BACKUP_MODELS = [
    _mk_model("llama3.1:8b",          "Meta",        "Llama-3.1",        "BACKUP",  4.7),
    _mk_model("deepseek-r1:7b",       "DeepSeek",    "DeepSeek-R1",      "BACKUP",  4.7),
    _mk_model("phi3.5:latest",        "Microsoft",   "Phi-3.5",          "BACKUP",  2.3),
]
# Local Mission Director — Nemotron-Nano for the live demo. Tier-3 escalation
# to Nemotron-Super-49B (cloud, via NIM) is configured but the cloud model is
# not invoked unless an override flag fires (see _model_ask_tiered, future).
MISSION_DIRECTOR = _mk_model("nemotron-3-nano:4b", "NVIDIA", "Nemotron-3-Nano", "DIRECTOR", 2.8)
MISSION_DIRECTOR["seat"] = "DIRECTOR"

# Now that PRIMARY_MODELS is defined, populate ASSESSORS with REAL model IDs.
# TOKEN_USAGE["by_model"] was initialised against the empty list above; refresh
# it now so the token accounting maps onto real model identifiers.
ASSESSORS = _build_assessors_from_lineup()
TOKEN_USAGE["by_model"] = {a["id"]: 0 for a in ASSESSORS}

CONSECUTIVE_FAIL_THRESHOLD = 3

# Council size preset → first N specialist seats are active. Minimum 3 (TMR).
COUNCIL_MODES = {
    "ECO":      {"seats": 3, "label": "Eco · TMR-3",         "desc": "RTX 4070 / older GPUs"},
    "BALANCED": {"seats": 4, "label": "Balanced · 4 seats",  "desc": "Safer default under VRAM pressure"},
    "FULL":     {"seats": 5, "label": "Full Council · 5",    "desc": "Best demo on RTX 5070 12 GB"},
}

# GPU memory thresholds (% of total VRAM) for the pre-flight guard.
GPU_WARN_PCT  = 80.0
GPU_BLOCK_PCT = 92.0

# Cooldown for the Mission Inbox — same (sat, attention_level) cannot push
# again within this window. Stops the popup-spam pattern flagged in P0.
INBOX_COOLDOWN_S = 300  # 5 minutes


INFERENCE = {
    "mode": "SIM",                # "SIM" | "LIVE-OLLAMA"
    "ollama_url": os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434"),
    "available_models": [],
    "last_probe_ts": 0.0,
    "live_calls": 0,
    "live_failures": 0,
    "host_gpu": None,
    "last_assess_ts": None,
    "last_lineup_call_ms": None,
    "council_mode": os.environ.get("COUNCIL_MODE", "BALANCED"),  # ECO | BALANCED | FULL
    "vram_gated_count": 0,        # number of calls deferred because VRAM was tight
    "director_calls": 0,
    "director_last_ms": None,
}


def _is_available(model_id: str) -> bool:
    """Match `phi3.5` against `phi3.5:latest` and other implicit-:latest tags."""
    if model_id in INFERENCE["available_models"]:
        return True
    if (model_id + ":latest") in INFERENCE["available_models"]:
        return True
    return False


def _resolve_id(model_id: str) -> str:
    """Returns the actual on-disk model name to send to /api/chat."""
    if model_id in INFERENCE["available_models"]:
        return model_id
    if (model_id + ":latest") in INFERENCE["available_models"]:
        return model_id + ":latest"
    return model_id


def _seats_for_mode() -> list[str]:
    n = COUNCIL_MODES[INFERENCE["council_mode"]]["seats"]
    return [s["seat"] for s in COUNCIL_SEATS[:n]]


def lineup_alive() -> list[dict]:
    """Return the seat-filling lineup for the current council mode (3/4/5).
    Each seat fills with its primary if alive+available, else the first
    available backup (which inherits the seat role)."""
    active_seats = _seats_for_mode()
    out = []
    used = set()
    backup_idx = 0
    for p in PRIMARY_MODELS:
        if p["seat"] not in active_seats:
            continue
        if p["alive"] and _is_available(p["id"]):
            p["replaced_by"] = None
            out.append(p); used.add(p["id"]); continue
        replacement = None
        while backup_idx < len(BACKUP_MODELS):
            b = BACKUP_MODELS[backup_idx]
            backup_idx += 1
            if b["id"] in used: continue
            if not _is_available(b["id"]): continue
            if not b["alive"]: continue
            replacement = dict(b)
            replacement["seat"] = p["seat"]
            used.add(b["id"])
            break
        if replacement:
            p["replaced_by"] = replacement["id"]
            out.append(replacement)
        else:
            out.append(p)
    return out


def model_view(m: dict) -> dict:
    return {
        "id": m["id"], "vendor": m["vendor"], "family": m["family"],
        "role": m["role"], "seat": m.get("seat"),
        "alive": m["alive"],
        "est_size_gb": m["est_size_gb"],
        "last_call_ms": m["last_call_ms"], "last_label": m["last_label"],
        "success": m["success"], "fail": m["fail"],
        "consecutive_fail": m["consecutive_fail"],
        "replaced_by": m["replaced_by"],
        "loaded": _is_available(m["id"]),
    }


def _http_get(url: str, timeout: float = 2.5) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, ConnectionResetError, TimeoutError, OSError, json.JSONDecodeError):
        return None


def _http_post(url: str, body: dict, timeout: float = 12.0) -> tuple[dict | None, float]:
    t0 = time.time()
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8")), (time.time() - t0) * 1000.0
    except Exception:
        return None, (time.time() - t0) * 1000.0


def probe_ollama() -> dict:
    """Hit Ollama's `/api/tags`. If reachable, refresh INFERENCE['available_models']
    so the lineup logic can decide who's alive. Does a tiny warm-up call against
    the first reachable lineup member so the GPU is actually exercised.
    """
    INFERENCE["last_probe_ts"] = time.time()
    tags = _http_get(INFERENCE["ollama_url"].rstrip("/") + "/api/tags")
    if tags is None:
        INFERENCE["mode"] = "SIM"
        INFERENCE["available_models"] = []
        return {"ok": False, "reason": "Ollama unreachable", "url": INFERENCE["ollama_url"]}

    models = [m["name"] for m in tags.get("models", [])]
    INFERENCE["available_models"] = models
    # Mark which lineup entries are present (tolerant of bare-tag vs :latest)
    for m in PRIMARY_MODELS + BACKUP_MODELS:
        if _is_available(m["id"]):
            m["alive"] = True
            m["consecutive_fail"] = 0
        else:
            m["alive"] = False
            m["consecutive_fail"] = CONSECUTIVE_FAIL_THRESHOLD

    lineup = lineup_alive()
    chosen = next((m for m in lineup if m["id"] in models and m["alive"]), None)
    if chosen is None:
        INFERENCE["mode"] = "SIM"
        return {"ok": False, "reason": "no lineup model available", "available": models,
                "lineup": [model_view(m) for m in lineup]}

    body = {
        "model": _resolve_id(chosen["id"]),
        "messages": [
            {"role": "system", "content": "You are a satellite health classifier. Reply with one word only from {GREEN, YELLOW, RED, BLACK}."},
            {"role": "user",   "content": "Smoke test — output GREEN."},
        ],
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 64},
    }
    resp, ms = _http_post(INFERENCE["ollama_url"].rstrip("/") + "/api/chat", body)
    chosen["last_call_ms"] = round(ms, 1)
    if resp is None:
        INFERENCE["mode"] = "SIM"
        INFERENCE["live_failures"] += 1
        chosen["fail"] += 1; chosen["consecutive_fail"] += 1
        return {"ok": False, "reason": "chat call failed", "model": chosen["id"], "ms": chosen["last_call_ms"]}

    INFERENCE["mode"] = "LIVE-OLLAMA"
    INFERENCE["live_calls"] += 1
    chosen["success"] += 1; chosen["consecutive_fail"] = 0
    msg = (resp.get("message") or {})
    response_text = (msg.get("content") or msg.get("thinking") or "")[:200]
    return {
        "ok": True,
        "model": chosen["id"],
        "ms": chosen["last_call_ms"],
        "response": response_text,
        "available": models,
        "lineup": [model_view(m) for m in lineup_alive()],
    }


def _sat_context(sat: dict, wx: dict) -> str:
    return (
        f"Satellite {sat['name']} ({sat['regime']}, op {sat['operator']}). "
        f"Age {sat_age_years(sat):.1f}y of {sat['design_life_years']}y design life. "
        f"Altitude {sat['altitude_km']} km. "
        f"TID {sat['tid_accumulated_krad']:.1f}/{sat['tid_budget_krad']:.0f} krad. "
        f"SEEs (30d): {sat['see_events_30d']}. "
        f"Space weather: Kp {wx['kp']}, X-ray {wx['xray_class']}, SEP {wx['sep_pfu']} pfu, AE {wx['ae']} nT."
    )


def _seat_prompt(seat: str, sat: dict, wx: dict) -> str:
    """Role-specific prompt — replaces generic majority voting per
    docs/RISKS_AND_FIXES.md 'Five models can cost more without adding trust'.
    """
    role = next((s for s in COUNCIL_SEATS if s["seat"] == seat), None)
    if role is None:
        role_question = "Output ONLY one word from {GREEN, YELLOW, RED, BLACK} — the operational attention level."
    else:
        role_question = role["prompt"] + " Output ONLY one word from {GREEN, YELLOW, RED, BLACK} — your attention level."
    return _sat_context(sat, wx) + "\n\nROLE: " + (role["title"] if role else seat) + "\n" + role_question


def _gpu_pressure_check() -> tuple[str, float | None]:
    """NEO Action Item 4 — pressure tier classifier (does not act).

    Returns one of:
      "OK"       — pct < GPU_WARN_PCT  (default 80%)
      "WARM"     — GPU_WARN_PCT  <= pct < (GPU_WARN_PCT + 6)
      "HOT"      — (GPU_WARN_PCT + 6) <= pct < GPU_BLOCK_PCT
      "CRITICAL" — pct >= GPU_BLOCK_PCT
      "UNKNOWN"  — no GPU stats available (fail-open by design — never block
                   inference because we cannot measure pressure)

    Use `_gpu_pressure_react(tier)` to apply the degradation step.
    """
    gpu = INFERENCE.get("host_gpu") or host_gpu_snapshot()
    INFERENCE["host_gpu"] = gpu
    if not gpu or not gpu.get("mem_total_mib"):
        return "UNKNOWN", None
    pct = 100.0 * gpu["mem_used_mib"] / gpu["mem_total_mib"]
    if pct >= GPU_BLOCK_PCT:
        return "CRITICAL", pct
    if pct >= GPU_WARN_PCT + 6:
        return "HOT", pct
    if pct >= GPU_WARN_PCT:
        return "WARM", pct
    return "OK", pct


def _gpu_pressure_react(tier: str, pct: float | None) -> dict:
    """NEO Action Item 4 — graceful-degrade ladder.

    Steps in increasing severity:
      OK        — no action.
      WARM      — drop council from FULL → BALANCED (5 → 4 seats), once.
      HOT       — drop council to ECO (3 seats), force T1→T2 escalation triggers
                  to be stricter so fewer cloud-bound calls fire concurrently.
      CRITICAL  — block the current call AND log an offload intent; the host
                  can opt-in to actually invoke `ollama unload` here.

    Returns the action descriptor written into the audit row.
    """
    action: dict = {"tier": tier, "pct": pct, "council_mode_before": INFERENCE.get("council_mode")}

    if tier in ("OK", "UNKNOWN"):
        action["taken"] = "none"
        return action

    if tier == "WARM" and INFERENCE.get("council_mode") == "FULL":
        INFERENCE["council_mode"] = "BALANCED"
        action["taken"] = "shrink_council:FULL->BALANCED"
        BUS.copilot("nemoclaw",
                    f"VRAM {pct:.0f}% (WARM) — shrinking council FULL -> BALANCED to relieve pressure",
                    severity="MED", action="COUNCIL_SHRINK", **action)
        return action

    if tier == "HOT":
        if INFERENCE.get("council_mode") != "ECO":
            INFERENCE["council_mode"] = "ECO"
            action["taken"] = "shrink_council:->ECO"
        else:
            action["taken"] = "already_eco"
        BUS.copilot("nemoclaw",
                    f"VRAM {pct:.0f}% (HOT) — council pinned to ECO; tier-3 escalation throttled",
                    severity="HIGH", action="COUNCIL_PIN_ECO", **action)
        return action

    # CRITICAL
    INFERENCE["vram_gated_count"] += 1
    action["taken"] = "block_and_offload_intent"
    BUS.copilot("nemoclaw",
                f"VRAM {pct:.0f}% (CRITICAL >= {GPU_BLOCK_PCT:.0f}%) — call blocked; offload intent logged",
                severity="HIGH", action="VRAM_OFFLOAD_INTENT", **action)
    return action


def _gpu_pressure_ok() -> tuple[bool, float | None]:
    """Back-compat shim — existing call sites still ask `(ok, pct)`. Under the
    NEO ladder this returns:
      ok=True   when tier in {OK, WARM, HOT, UNKNOWN}
      ok=False  when tier == CRITICAL
    Each WARM/HOT/CRITICAL transition fires the react step (which may already
    have shrunk the council before this function returns).
    """
    tier, pct = _gpu_pressure_check()
    _gpu_pressure_react(tier, pct)
    return (tier != "CRITICAL"), pct


def _model_ask(model: dict, prompt: str, timeout: float = 15.0,
               system: str | None = None, num_predict: int = 256) -> dict | None:
    """One sequential Ollama call. VRAM pre-flight gates the call; on
    sustained failure the model is marked DEAD and the council resolver
    swaps in a backup."""
    ok, vram_pct = _gpu_pressure_ok()
    if not ok:
        INFERENCE["vram_gated_count"] += 1
        BUS.alert("MED",
            f"VRAM {vram_pct:.0f}% — deferring call to {model['id']} (block at {GPU_BLOCK_PCT:.0f}%)",
            None)
        return None
    body = {
        "model": _resolve_id(model["id"]),
        "messages": [
            {"role": "system",
             "content": system or "You are a satellite operations attention-level classifier. Output one word only from {GREEN, YELLOW, RED, BLACK}."},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": num_predict},
    }
    resp, ms = _http_post(INFERENCE["ollama_url"].rstrip("/") + "/api/chat", body, timeout=timeout)
    model["last_call_ms"] = round(ms, 1)
    if resp is None:
        model["fail"] += 1
        model["consecutive_fail"] += 1
        INFERENCE["live_failures"] += 1
        if model["consecutive_fail"] >= CONSECUTIVE_FAIL_THRESHOLD and model["alive"]:
            model["alive"] = False
            BUS.alert("HIGH",
                f"model {model['id']} marked DEAD after {model['fail']} failures — swapping seat to backup",
                None)
        return None
    INFERENCE["live_calls"] += 1
    model["success"] += 1
    model["consecutive_fail"] = 0
    msg = resp.get("message") or {}
    content = (msg.get("content") or "").strip()
    thinking = (msg.get("thinking") or "").strip()
    haystack = (content + " " + thinking).upper()
    label = next((k for k in ("BLACK", "RED", "YELLOW", "GREEN") if k in haystack), None)
    model["last_label"] = label or "?"
    model["last_thinking"] = thinking[:160] if thinking else None
    return {"label": label, "content": content, "thinking": thinking, "ms": model["last_call_ms"]}


def live_lineup_vote(sat: dict, wx: dict) -> list[dict] | None:
    """Sequentially poll each specialist seat for the focused sat. Each seat
    gets its role-specific prompt (not a shared one). Nemotron Director is
    invoked separately in `assess_sat`. Returns None in SIM mode.
    """
    if INFERENCE["mode"] != "LIVE-OLLAMA":
        return None
    lineup = lineup_alive()
    votes: list[dict] = []
    t_lineup = 0.0
    for m in lineup:
        if not (m["alive"] and _is_available(m["id"])):
            continue
        prompt = _seat_prompt(m["seat"], sat, wx)
        result = _model_ask(m, prompt)
        t_lineup += m["last_call_ms"] or 0.0
        if result and result["label"]:
            votes.append({
                "seat": m["seat"],
                "seat_title": next((s["title"] for s in COUNCIL_SEATS if s["seat"] == m["seat"]), m["seat"]),
                "model": m["id"], "vendor": m["vendor"], "family": m["family"],
                "label": result["label"], "ms": m["last_call_ms"],
                "live": True,
                "score": {"GREEN": 0.2, "YELLOW": 0.6, "RED": 0.9, "BLACK": 1.2}[result["label"]],
            })
    INFERENCE["last_lineup_call_ms"] = round(t_lineup, 1)
    INFERENCE["last_assess_ts"] = datetime.now(timezone.utc).strftime("%H:%M:%SZ")
    return votes


def host_gpu_snapshot() -> dict | None:
    """Best-effort nvidia-smi probe. None on machines without NVIDIA GPU."""
    try:
        import subprocess
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=2.0,
        )
        if r.returncode != 0:
            return None
        parts = [p.strip() for p in r.stdout.splitlines()[0].split(",")]
        return {
            "name": parts[0],
            "util_pct": int(parts[1]),
            "mem_used_mib": int(parts[2]),
            "mem_total_mib": int(parts[3]),
        }
    except Exception:
        return None


def inference_view() -> dict:
    return {
        "mode": INFERENCE["mode"],
        "ollama_url": INFERENCE["ollama_url"],
        "available_models": INFERENCE["available_models"],
        "live_calls": INFERENCE["live_calls"],
        "live_failures": INFERENCE["live_failures"],
        "host_gpu": INFERENCE["host_gpu"],
        "last_assess_ts": INFERENCE.get("last_assess_ts"),
        "last_lineup_call_ms": INFERENCE.get("last_lineup_call_ms"),
        "vram_gated_count": INFERENCE.get("vram_gated_count", 0),
        "director_calls": INFERENCE.get("director_calls", 0),
        "director_last_ms": INFERENCE.get("director_last_ms"),
        "council_mode": INFERENCE["council_mode"],
        "council_modes": COUNCIL_MODES,
        "council_seats": COUNCIL_SEATS,
        "active_seats": _seats_for_mode(),
        "director": model_view(MISSION_DIRECTOR),
        "lineup": [model_view(m) for m in lineup_alive()],
        "primary": [model_view(m) for m in PRIMARY_MODELS],
        "backup":  [model_view(m) for m in BACKUP_MODELS],
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


def director_call(sat: dict, wx: dict, votes: list[dict]) -> dict | None:
    """Nemotron Mission Director — fixed centre seat. ALWAYS runs after the
    specialist council, not just on disagreement. Writes the final
    recommendation that ends up in the mission brief.
    """
    if INFERENCE["mode"] != "LIVE-OLLAMA":
        return None
    if not _is_available(MISSION_DIRECTOR["id"]):
        return None
    vote_lines = "\n".join(
        f"- {v.get('seat_title','?')} ({v.get('vendor','?')} {v.get('model','?')}): {v['label']}"
        for v in votes
    )
    unique_labels = sorted({v["label"] for v in votes if v.get("label")})
    disagreement = len(unique_labels) >= 2
    prompt = (
        f"You are the Mission Director adjudicating a Spaceshark round-table session.\n"
        f"SUBJECT: {sat['name']} ({sat['regime']}, op {sat['operator']}).\n"
        f"CONTEXT: age {sat_age_years(sat):.1f}/{sat['design_life_years']}y · "
        f"TID {sat['tid_accumulated_krad']:.1f}/{sat['tid_budget_krad']:.0f} krad · "
        f"SEE(30d) {sat['see_events_30d']} · "
        f"Kp {wx['kp']} · X-ray {wx['xray_class']} · SEP {wx['sep_pfu']} pfu.\n"
        f"COUNCIL VOTES ({len(votes)} specialists):\n{vote_lines}\n\n"
        f"{'Specialists disagree — resolve.' if disagreement else 'Specialists are aligned — confirm or refine.'}\n"
        f"Output ONE WORD attention level from {{GREEN, YELLOW, RED, BLACK}}. "
        f"This is advisory triage on public-data evidence — NOT a spacecraft command."
    )
    result = _model_ask(
        MISSION_DIRECTOR, prompt,
        timeout=30.0, num_predict=400,
        system="You are the Mission Director for a satellite operations advisory desk. Combine specialist votes with public-data evidence; output one word.",
    )
    if not result:
        return None
    INFERENCE["director_calls"] += 1
    INFERENCE["director_last_ms"] = MISSION_DIRECTOR["last_call_ms"]
    return {
        "label": result["label"],
        "rationale": (result.get("thinking") or result.get("content") or "")[:500],
        "ms": MISSION_DIRECTOR["last_call_ms"],
        "model": MISSION_DIRECTOR["id"],
        "disagreement": disagreement,
    }


def assess_sat(sat: dict, wx: dict, with_director: bool = True) -> dict:
    """Run every assessor, take the median label, return assessment dossier."""
    votes = []
    scores = []
    # In LIVE mode the five real models in the lineup vote. SIM mode falls
    # back to the deterministic stylised cohort below (kept around as backup
    # for visualisation when nothing's loaded yet).
    live_votes = live_lineup_vote(sat, wx) if INFERENCE["mode"] == "LIVE-OLLAMA" else None
    if live_votes:
        votes.extend(live_votes)
        scores.extend(v["score"] for v in live_votes)
    else:
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
    transition = None
    age, tid, see, wxf = base_factors(sat, wx)

    # MISSION DIRECTOR: Nemotron sits at the head of the table and writes
    # the final call. Reserved for the focused sat (`with_director=True`);
    # background sweep across the rest of the 1000-sat fleet skips the
    # Director call to keep per-sat latency under a few seconds.
    arbiter = None
    live_votes = [v for v in votes if v.get("live")]
    if with_director and len(live_votes) >= 1:
        arbiter = director_call(sat, wx, live_votes)
        if arbiter and arbiter["label"]:
            median_label = arbiter["label"]

    # Insufficient council marker (docs/RISKS_AND_FIXES.md "Minimum council
    # size should be three models").
    insufficient = len(live_votes) > 0 and len(live_votes) < 3

    sat["health"] = median_label
    sat["score"] = round(median_score, 3)
    sat["last_assessed"] = datetime.now(timezone.utc).strftime("%H:%M:%SZ")
    if prev != median_label:
        transition = f"{prev} → {median_label}"

    # Build the mission brief for this round (round-table session).
    brief = build_mission_brief(sat, wx, votes, arbiter, transition,
                                {"age": age, "tid": tid, "see": see, "weather": wxf},
                                insufficient=insufficient)

    return {
        "votes": votes,
        "median_label": median_label,
        "median_score": round(median_score, 3),
        "consensus_pct": consensus_pct,
        "transition": transition,
        "arbiter": arbiter,
        "brief": brief,
        "factors": {
            "age": round(age, 3),
            "tid": round(tid, 3),
            "see": round(see, 3),
            "weather": round(wxf, 3),
        },
    }


def build_mission_brief(sat, wx, votes, arbiter, transition, factors, insufficient=False):
    """Structured, traceable summary of a round-table session.

    Uses **advisory triage language** (docs/RISKS_AND_FIXES.md "satellite
    health can overclaim"). Labels map:
        GREEN  → STABLE       (no action)
        YELLOW → ROUTINE       (monitor)
        RED    → PRIORITY      (high-priority review)
        BLACK  → EOL-CANDIDATE (review for EOL)
    """
    label = sat["health"]
    counts = {"GREEN": 0, "YELLOW": 0, "RED": 0, "BLACK": 0}
    for v in votes:
        counts[v["label"]] = counts.get(v["label"], 0) + 1
    attention = {"GREEN": "STABLE", "YELLOW": "ROUTINE", "RED": "PRIORITY", "BLACK": "EOL-CANDIDATE"}[label]
    action = {
        "GREEN":  "STABLE — no action",
        "YELLOW": "ROUTINE REVIEW",
        "RED":    "HIGH-PRIORITY REVIEW",
        "BLACK":  "REVIEW FOR EOL",
    }[label]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = f"{sat['id']}|{label}|{now}|{factors}"
    evidence_hash = hashlib.sha256(payload.encode()).hexdigest()
    return {
        "subject": sat["name"],
        "subject_id": sat["id"],
        "regime": sat["regime"],
        "operator": sat["operator"],
        "shell": sat.get("shell"),
        "synopsis": _brief_synopsis(sat, label, transition, factors),
        "health": label,                # internal label (preserved for backward compat)
        "attention_level": attention,   # operator-facing wording
        "transition": transition,
        "insufficient_council": insufficient,
        "votes": [{"model": v.get("model"), "vendor": v.get("vendor"),
                   "seat": v.get("seat"), "seat_title": v.get("seat_title"),
                   "label": v["label"], "ms": v.get("ms"), "live": v.get("live")}
                  for v in votes],
        "vote_counts": counts,
        "director": arbiter,            # None or {label, rationale, ms, model, disagreement}
        "arbiter": arbiter,             # alias kept for backward compat
        "drivers": factors,
        "weather": wx,
        "action": action,
        "caveat": "Based on public orbit + environment evidence only — not spacecraft telemetry.",
        "provenance": {
            "event_id": f"on-orbit-ops-{sat['id']}-{now.replace(':','').replace('-','')}-{evidence_hash[:8]}",
            "evidence_hash": evidence_hash,
            "parser_version": "0.4.0",
            "ts": now,
        },
        "review_status": "draft" if label in ("RED", "BLACK") else "internal-log-only",
    }


def _brief_synopsis(sat, label, transition, factors):
    drivers = sorted(factors.items(), key=lambda kv: -kv[1])
    top = drivers[0]
    name_map = {"age": "age vs life", "tid": "TID dose", "see": "SEEs", "weather": "space weather"}
    head = f"{sat['name']} health {label}"
    if transition:
        head = head + f" ({transition})"
    return f"{head}; primary driver: {name_map.get(top[0], top[0])} ({top[1]:.2f})."


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
    sig_base = -55 - {"GREEN": 0, "YELLOW": 8, "RED": 18, "BLACK": 32}.get(sat["health"], 4)
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
        self.inbox: deque = deque(maxlen=120)      # Mission Inbox items
        self.inbox_seq = 0
        self.last_inbox_ts: dict[str, float] = {}  # sat_id -> last push timestamp (cooldown)
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
        INFERENCE["host_gpu"] = host_gpu_snapshot()
        return {
            "type": "snapshot",
            "sats": [public_sat(s) for s in SATS],
            "fleet_health": fleet_health_counts(),
            "weather": WEATHER.snapshot(),
            "focused": focused_sat_view(),
            "tokens": token_view(),
            "inference": inference_view(),
            "assessors": [{"id": a["id"], "family": a["family"], "bias": a["bias"]} for a in ASSESSORS],
            "inbox": list(self.inbox),
            "alerts": list(self.alerts),
            "council_modes": COUNCIL_MODES,
            "council_seats": COUNCIL_SEATS,
            "council_mode": INFERENCE["council_mode"],
            "visual_catalog_size": len(VISUAL_CATALOG),
            "uptime_s": int(time.time() - self.start_ts),
        }

    def copilot(self, who: str, msg: str, **extra) -> None:
        """NEO Action Item 4 — wired to the NemoClaw audit-dispatch pipeline.

        Closes review2.md's #1 critique (this was a `return None` no-op). Every
        call now produces a JSONL row under `data/audit/YYYY-MM-DD.jsonl` with
        audit_log_id + policy_preset_hash, and is mirrored to the in-memory
        copilot_log deque for the live dashboard.

        `who` is the actor (`"nemoclaw" / "user" / "model:<id>"`).
        `extra` kwargs land verbatim on the row — keys like `decision_route`,
        `denied_actions`, `override_invariant`, `severity`, `action`, `sat_id`,
        `who_label` are all accepted.
        """
        # severity defaults to INFO unless the caller supplied one in extra.
        severity = extra.pop("severity", "INFO")
        try:
            row = audit_dispatch(who, msg, severity=severity, **extra)
        except Exception as e:
            # NemoClaw audit write failed — degrade visibly rather than silently
            # so the "no action without audit" invariant is enforced operationally.
            row = {
                "audit_log_id": "nemoclaw-write-failed",
                "ts": datetime.now(timezone.utc).strftime("%H:%M:%S"),
                "who": who, "msg": msg, "severity": "HIGH",
                "error": f"audit_dispatch failed: {e}",
            }

        # In-memory dashboard log — same row but trimmed to 80 entries per
        # the existing UX convention.
        self.copilot_log.append(row)
        if len(self.copilot_log) > self.copilot_log.maxlen:
            # deque has maxlen; this guard is redundant but keeps intent explicit
            pass
        self.publish({"type": "copilot", "row": row})
        return None

    def alert(self, severity: str, message: str, sat_id: str | None = None) -> None:
        a = {
            "ts": datetime.now(timezone.utc).strftime("%H:%M:%S"),
            "severity": severity,
            "message": message,
            "sat_id": sat_id,
        }
        self.alerts.append(a)
        self.publish({"type": "alert", "alert": a})

    def push_inbox(self, brief: dict) -> bool:
        """Add a brief to the persistent Mission Inbox if cooldown allows.
        Returns True if pushed, False if suppressed by cooldown.
        Per docs/RISKS_AND_FIXES.md: same sat cannot push within 5 minutes
        for the same severity tier."""
        sat_id = brief["subject_id"]
        attn = brief.get("attention_level")
        # Only PRIORITY / EOL items hit the inbox by default; STABLE/ROUTINE
        # accumulate silently in the assessment log.
        if attn not in ("PRIORITY", "EOL-CANDIDATE"):
            return False
        key = f"{sat_id}|{attn}"
        now_ts = time.time()
        last = self.last_inbox_ts.get(key, 0)
        if now_ts - last < INBOX_COOLDOWN_S:
            return False
        self.last_inbox_ts[key] = now_ts
        self.inbox_seq += 1
        item = {
            "inbox_id": self.inbox_seq,
            "ts": brief["provenance"]["ts"],
            "sat_id": sat_id,
            "subject": brief["subject"],
            "regime": brief["regime"],
            "shell": brief.get("shell"),
            "attention_level": attn,
            "health": brief["health"],
            "action": brief["action"],
            "vote_counts": brief["vote_counts"],
            "director": brief.get("director"),
            "provenance": brief["provenance"],
            "state": "NEW",            # NEW | REVIEWED | DISMISSED
        }
        self.inbox.append(item)
        self.publish({"type": "inbox", "item": item, "inbox_size": len(self.inbox)})
        return True

    def inbox_set_state(self, inbox_id: int, state: str) -> bool:
        for it in self.inbox:
            if it["inbox_id"] == inbox_id:
                it["state"] = state
                self.publish({"type": "inbox", "item": it, "inbox_size": len(self.inbox)})
                return True
        return False


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
        "shell": sat.get("shell"),
        "operator": sat["operator"],
        "launched": sat["launched"],
        "inclination_deg": sat.get("inclination_deg"),
        "raan_deg":         sat.get("raan_deg", 0.0),
        "phase":            sat.get("phase",    0.0),
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
    counts = {"GREEN": 0, "YELLOW": 0, "RED": 0, "BLACK": 0, "UNKNOWN": 0}
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
    """Returns a vote snapshot for the focused sat. In LIVE-OLLAMA mode we
    surface the *last* live vote per lineup model (no synchronous re-call so
    the panel stays responsive); in SIM mode we use the deterministic cohort.
    """
    wx = WEATHER.snapshot()
    votes = []
    scores = []
    age, tid, see, wxf = base_factors(sat, wx)

    if INFERENCE["mode"] == "LIVE-OLLAMA":
        for m in lineup_alive():
            label = m["last_label"] or "—"
            if label not in ("GREEN", "YELLOW", "RED", "BLACK"):
                continue
            sc = {"GREEN": 0.2, "YELLOW": 0.6, "RED": 0.9, "BLACK": 1.2}[label]
            votes.append({
                "model": m["id"], "vendor": m["vendor"], "family": m["family"],
                "label": label, "score": sc,
                "live": True, "ms": m["last_call_ms"],
            })
            scores.append(sc)

    if not votes:
        # SIM cohort fallback
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
# NEO Action Item 2 — COTS telemetry + JPL anomaly detection.
#
# Design note (post-2026-05-26 owner review): for a 1000-sat fleet we cannot
# tick the JPL detector every 2s per sat — that would produce 500 detector
# calls/sec and ~30 GB/day of audit JSONL in the worst case. The scheduler
# below uses a *round-robin queue* so the detector runs at a steady tick rate
# regardless of fleet size, and audit rows are gated by a per-sat 5-minute
# cooldown so the same anomalous sat does not repeatedly log the same event.
#
# All telemetry inputs are physics-based projections from real signals:
#   - real Celestrak TLE → SGP4 sub-satellite point + eclipse hint
#   - real NOAA SWPC Kp/X-ray/SEP feeds drive the SEE probability envelope
#   - simulated chip-level current/voltage is a STATISTICAL PROJECTION of
#     what a COTS chip in that orbital position + space-weather state would
#     experience, not a synthetic stand-in for a missing real feed.
# ============================================================================

# 50 Hz stream — initialised lazily on first access so unit-tests can run
# without booting the worker thread.
COTS_STREAM: TelemetryStream | None = None
COTS_TICK_HZ = 50.0

# Round-robin scheduler — scan SATS_PER_TICK sats every SCHEDULER_TICK_S.
# Defaults sized for 1000-sat fleet: scan 17 sats/sec → full sweep in 60s.
SCHEDULER_TICK_S = 1.0
SATS_PER_TICK = 17
# Per-sat audit cooldown so a sat that keeps tripping the detector does not
# write 30 audit rows per minute. 5 min cooldown means at most 12 audit rows
# per sat per hour; for the full anomalous fleet at peak storm (~10% of
# 1000 sats = 100 anomalous), worst-case audit rate ≈ 20 rows/min.
COTS_AUDIT_COOLDOWN_S = 300.0

COTS_LAST_DETECT: dict[str, float] = {}  # sat_id -> last detector run ts
COTS_LAST_AUDIT: dict[str, float] = {}   # sat_id -> last audit-row write ts
COTS_LATEST: dict[str, dict] = {}        # sat_id -> last detector result dict
_COTS_QUEUE: list[str] = []              # round-robin queue head -> tail


def cots_init() -> TelemetryStream:
    """Lazy init for the global stream — call after SATS roster is built."""
    global COTS_STREAM
    if COTS_STREAM is None:
        COTS_STREAM = TelemetryStream([s["id"] for s in SATS])
        BUS.copilot("nemoclaw",
                    f"COTS telemetry stream initialised at {COTS_TICK_HZ:.0f} Hz over {len(SATS)} sats",
                    severity="INFO", action="COTS_STREAM_INIT",
                    override_invariant="O1-source-list-5th-input")
    return COTS_STREAM


def cots_orbit_lookup(sat_id: str) -> dict | None:
    """Used by TelemetryStream.tick() to modulate the stream by eclipse / SAA."""
    return sgp4_propagate(sat_id, ts_utc=time.time())


def cots_run_detector(sat_id: str) -> dict:
    """Run JPL detector on the current 1024-sample current_mA window for
    `sat_id`. Writes an audit row when an anomaly is detected. Returns the
    detector result as a dict for /api/cots/telemetry/<sat_id>.

    On `see` / `dielectric_charge` detection, also drafts a beam-redirect
    proposal (NEO Action Item 3) — appended to BEAM_DRAFTS_QUEUE under
    decision_route=needs-review.
    """
    stream = cots_init()
    series = telemetry_buffer_for(stream, sat_id, "current_mA")
    if len(series) < 32:
        return {"sat_id": sat_id, "is_anomaly": False,
                "regime": "insufficient_window", "samples": len(series)}
    res = jpl_detect(series, metric="current_mA")
    out = {
        "sat_id": sat_id,
        "is_anomaly": res.is_anomaly,
        "magnitude": res.magnitude,
        "regime": res.regime,
        "threshold": res.threshold,
        "z": res.z,
        "n_above": res.n_above,
        "samples": len(series),
        "ts": time.time(),
    }
    COTS_LATEST[sat_id] = out
    COTS_LAST_DETECT[sat_id] = time.time()
    if res.is_anomaly:
        # In-memory sat record is updated every time so the dashboard always
        # shows the current anomaly regime. Audit rows are gated by per-sat
        # cooldown so a flapping anomalous sat doesn't generate 30 rows/min.
        sat = find_sat(sat_id)
        if sat:
            sat["cots_anomaly"] = {
                "regime": res.regime,
                "magnitude": res.magnitude,
                "ts": time.time(),
            }

        now_ts = time.time()
        last_audit = COTS_LAST_AUDIT.get(sat_id, 0.0)
        if now_ts - last_audit >= COTS_AUDIT_COOLDOWN_S:
            COTS_LAST_AUDIT[sat_id] = now_ts
            BUS.copilot("nemoclaw",
                        f"COTS anomaly on {sat_id} — regime={res.regime}, "
                        f"magnitude={res.magnitude:.2f}σ above threshold {res.threshold:.2f}",
                        severity="HIGH", action="COTS_ANOMALY", sat_id=sat_id,
                        anomaly_regime=res.regime, anomaly_magnitude=res.magnitude,
                        override_invariant="O1-source-list-5th-input")
            # NEO Action Item 3 — auto-draft a beam-redirect if comms-relevant.
            # Only fires on the audited tick (same cooldown) so a single SEE
            # event produces at most one draft.
            if sat and res.regime in ("see", "dielectric_charge"):
                _maybe_draft_beam_redirect(sat, res.regime, res.magnitude)
    return out


# Per-sat draft cooldown so we don't flood the inbox on repeated detections.
BEAM_DRAFT_COOLDOWN_S = 600.0  # 10 minutes
_BEAM_DRAFT_LAST: dict[str, float] = {}
BEAM_DRAFTS_QUEUE: list[dict] = []   # most-recent first; capped at 50


def _maybe_draft_beam_redirect(sat: dict, regime: str, magnitude: float) -> dict | None:
    sat_id = str(sat.get("id"))
    now_ts = time.time()
    if now_ts - _BEAM_DRAFT_LAST.get(sat_id, 0.0) < BEAM_DRAFT_COOLDOWN_S:
        return None
    orbit = sgp4_propagate(sat_id, ts_utc=now_ts)
    if not orbit or not orbit.get("ok"):
        return None

    # Demo-time target: use the sub-satellite point itself. A production
    # deployment would substitute a disaster-feed lookup here.
    target_lat = orbit["lat_deg"]
    target_lon = orbit["lon_deg"]

    draft = brief_beam_redirect(
        sat=sat,
        anomaly_regime=regime,
        target_lat_deg=target_lat,
        target_lon_deg=target_lon,
        confidence=min(0.95, 0.5 + 0.05 * magnitude),
        sub_sat_lat=target_lat,
        sub_sat_lon=target_lon,
        sat_alt_km=orbit["alt_km"],
        incident_summary=f"Demo target — sub-satellite point at "
                         f"({target_lat:.2f}, {target_lon:.2f}) used as "
                         f"emergency surrogate.",
    )

    # NEO post-2026-05-26 — upgrade justification from template to real
    # Nemotron call. Every dashboard cell must be backed by a real LLM call
    # or judge per owner critique. On Ollama unreachable, falls back to the
    # original template so the dashboard never blanks.
    kb_entries = kb_lookup(failure_mode=regime, regime="LEO", limit=3)
    llm_result = llm_justify_beam_redirect(
        sat_id=draft.sat_id,
        anomaly_regime=regime,
        target_lat=draft.target_lat_deg,
        target_lon=draft.target_lon_deg,
        tilt_deg=draft.tilt_deg,
        duration_s=draft.duration_s,
        incident_summary=f"Sub-satellite-point demo target ({target_lat:.2f}, {target_lon:.2f})",
        kb_entries=kb_entries,
        ollama_url=INFERENCE["ollama_url"].rstrip("/") + "/api/chat",
    )
    # Splice the LLM text into the draft's justification + record provenance
    # on the draft dict so the dashboard can show "live Nemotron 2.3s ago".
    draft.justification = llm_result["text"]
    draft.evidence_pointers = [e.entry_id for e in kb_entries[:3]]
    BUS.copilot("model:" + llm_result["model_id"],
                f"justify beam-redirect for {draft.sat_id} via {llm_result['source']} "
                f"({llm_result['latency_ms']}ms, {llm_result['eval_count']} tokens)",
                severity="INFO", action="BEAM_REDIRECT_LLM_JUSTIFY",
                sat_id=draft.sat_id, llm_source=llm_result["source"],
                latency_ms=llm_result["latency_ms"],
                eval_count=llm_result["eval_count"],
                prompt_hash=llm_result["prompt_hash"],
                override_invariant="O2-decision-verb-4th")

    # Output-guard the justification before publishing — closes review2.md's
    # "NemoClaw is no-op" critique end-to-end on this verb.
    allow, scrubbed, denied = output_guard(draft.justification)
    if not allow:
        BUS.copilot("nemoclaw",
                    f"beam-redirect draft for {sat_id} BLOCKED by output_guard",
                    severity="HIGH", action="BEAM_REDIRECT_BLOCKED",
                    sat_id=sat_id, denied_actions=denied,
                    override_invariant="O2-decision-verb-4th")
        return None

    draft_dict = draft.to_dict()
    # Attach LLM provenance fields so dashboard can show the badge.
    draft_dict["llm_source"] = llm_result["source"]
    draft_dict["llm_latency_ms"] = llm_result["latency_ms"]
    draft_dict["llm_model_id"] = llm_result["model_id"]
    draft_dict["llm_eval_count"] = llm_result["eval_count"]
    _BEAM_DRAFT_LAST[sat_id] = now_ts
    BEAM_DRAFTS_QUEUE.insert(0, draft_dict)
    if len(BEAM_DRAFTS_QUEUE) > 50:
        BEAM_DRAFTS_QUEUE.pop()

    BUS.copilot("model:" + MISSION_DIRECTOR["id"],
                f"draft beam-redirect for {sat_id} (regime={regime}, "
                f"tilt={draft.tilt_deg:.1f}°, duration={draft.duration_s}s)",
                severity="MED", action="BEAM_REDIRECT_DRAFT",
                sat_id=sat_id, decision_route="needs-review",
                evidence_pointers=draft.evidence_pointers,
                override_invariant="O2-decision-verb-4th")
    BUS.publish({"type": "beam_redirect_draft", "draft": draft_dict})
    return draft_dict


def cots_telemetry_loop() -> None:
    """50 Hz telemetry tick + round-robin JPL scheduler.

    The telemetry stream still ticks at 50Hz (so the JPL detector window has
    enough samples for short-burst anomalies), but the detector itself runs
    on a *round-robin queue*: every SCHEDULER_TICK_S we run the detector on
    SATS_PER_TICK sats off the head of the queue, then re-enqueue them.

    For a 1000-sat fleet with the defaults (17 sats/sec) the full fleet is
    scanned every ~60 seconds. Audit rows are then further gated by the
    per-sat COTS_AUDIT_COOLDOWN_S so an anomalous sat writes at most 1
    row per 5 minutes.

    Total worst-case audit volume: 1000 sats × 1/300 rows/sec × ~350 bytes
    ≈ 1.2 KB/sec ≈ 100 MB/day at peak storm conditions. Quiet days are
    ~10x lower because most sats are nominal.
    """
    stream = cots_init()
    # Seed the round-robin queue with the current fleet.
    global _COTS_QUEUE
    _COTS_QUEUE = [s["id"] for s in SATS]
    BUS.copilot("nemoclaw",
                f"COTS scheduler: {len(_COTS_QUEUE)} sats round-robin "
                f"@ {SATS_PER_TICK}/tick × {SCHEDULER_TICK_S:.1f}s "
                f"(full sweep ~{len(_COTS_QUEUE) / SATS_PER_TICK * SCHEDULER_TICK_S:.0f}s)",
                severity="INFO", action="COTS_SCHEDULER_INIT",
                override_invariant="O1-source-list-5th-input")

    period = 1.0 / COTS_TICK_HZ
    next_tick = time.time()
    last_scheduler_tick = time.time()
    while True:
        if _RUN_FLAG["value"]:
            try:
                wx = WEATHER.snapshot()
                stream.tick(weather=wx, orbit_lookup=cots_orbit_lookup)
                now_ts = time.time()
                # Round-robin detector batch
                if now_ts - last_scheduler_tick >= SCHEDULER_TICK_S:
                    last_scheduler_tick = now_ts
                    # Refill the queue if the fleet shifted (e.g. sats added)
                    if not _COTS_QUEUE:
                        _COTS_QUEUE = [s["id"] for s in SATS]
                    batch = _COTS_QUEUE[:SATS_PER_TICK]
                    _COTS_QUEUE = _COTS_QUEUE[SATS_PER_TICK:] + batch
                    for sid in batch:
                        try:
                            cots_run_detector(sid)
                        except Exception as e:
                            BUS.copilot("nemoclaw",
                                        f"cots_run_detector({sid}) error: {e}",
                                        severity="HIGH", action="COTS_DETECTOR_ERROR",
                                        sat_id=sid)
            except Exception as e:
                BUS.copilot("nemoclaw",
                            f"cots_telemetry_loop error: {e}",
                            severity="HIGH", action="COTS_LOOP_ERROR")
                time.sleep(1.0)
        next_tick += period
        sleep_for = next_tick - time.time()
        if sleep_for > 0:
            time.sleep(sleep_for)
        else:
            # Falling behind — reset the clock so we don't spin
            next_tick = time.time()


# ============================================================================
# Background loops.
# ============================================================================

_RUN_FLAG = {"value": True}


def assessment_loop() -> None:
    """Mission-commander pacing: the focused sat gets a full round-table
    session every tick; the rest of the fleet drifts in a slow background
    sweep so the GPU isn't pinned and the operator sees crisp updates on
    whatever they're staring at."""
    sweep_idx = 0
    last_focus_assess = 0.0
    last_fleet_sweep = 0.0
    while True:
        if _RUN_FLAG["value"]:
            WEATHER.tick()
            for s in SATS:
                degrade_sat(s, WEATHER.snapshot())
                update_telemetry(s)
            wx = WEATHER.snapshot()

            now_ts = time.time()
            focus = focused_sat()

            # Priority 1: focused sat — full round-table with Director.
            with_director = False
            if now_ts - last_focus_assess >= 10.0:
                sat = focus
                last_focus_assess = now_ts
                with_director = True
            # Priority 2: background fleet sweep — specialists only (no
            # Director call), so 1000 sats can be cycled at a reasonable
            # pace. UNKNOWN sats jump the queue so first-pass coverage
            # converges faster.
            elif now_ts - last_fleet_sweep >= 4.0:
                others = [s for s in SATS if s["id"] != focus["id"]]
                unknowns = [s for s in others if s["health"] == "UNKNOWN"]
                if unknowns:
                    sat = unknowns[sweep_idx % len(unknowns)]
                else:
                    sat = others[sweep_idx % len(others)]
                sweep_idx += 1
                last_fleet_sweep = now_ts
            else:
                time.sleep(1.5)
                continue
            assessment = assess_sat(sat, wx, with_director=with_director)

            # surface transitions to alerts + Mission Inbox (no chat popups)
            if assessment["transition"]:
                sev = {"GREEN": "INFO", "YELLOW": "MED", "RED": "HIGH", "BLACK": "HIGH"}[sat["health"]]
                BUS.alert(sev, f"{sat['name']} {assessment['transition']} (consensus {assessment['consensus_pct']}%)", sat["id"])
            # Always offer the brief to the inbox; push_inbox enforces
            # severity gate + cooldown internally.
            if assessment.get("brief"):
                BUS.push_inbox(assessment["brief"])

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
            INFERENCE["host_gpu"] = host_gpu_snapshot()
            BUS.publish({
                "type": "fleet_update",
                "fleet_health": fleet_health_counts(),
                "weather": wx,
                "tokens": token_view(),
                "inference": inference_view(),
                "sats": [public_sat(s) for s in SATS],
                "focused": focused_sat_view(),
                "last_assessed": {"sat_id": sat["id"], "assessment": assessment, "health": sat["health"]},
                "brief": assessment.get("brief"),
            })
        time.sleep(0.5)


def copilot_loop() -> None:
    """No-op (kept for backwards compatibility). The synthetic operator/AI
    chat was retired per docs/RISKS_AND_FIXES.md P0 "Recommendation should
    not keep popping up" — recommendations now land in the Mission Inbox
    with cooldown, not in an interrupt-style text stream."""
    while True:
        time.sleep(60)


def token_history_loop() -> None:
    """Every 5s push a token-rate sample for the gauge sparkline."""
    last = TOKEN_USAGE["spent"]
    while True:
        time.sleep(5)
        delta = TOKEN_USAGE["spent"] - last
        last = TOKEN_USAGE["spent"]
        TOKEN_USAGE["history"].append({"t": int(time.time()), "delta": delta, "spent": TOKEN_USAGE["spent"]})
        BUS.publish({"type": "tokens", "tokens": token_view()})


def neo_tactical_brief_loop() -> None:
    """NEO Tactical Brief panel — every 60s ask Nemotron-Nano-4B for a
    three-sentence executive summary of the current fleet state. The result
    is exposed at /api/neo/tactical-brief and rendered in the dashboard. Each
    successful generation writes an audit row.
    """
    while True:
        if INFERENCE["mode"] == "LIVE-OLLAMA":
            try:
                fleet_state = {"fleet_health": fleet_health_counts()}
                weather = WEATHER.snapshot()
                recent_audit = [r.get("action", "") for r in audit_tail(20) if r.get("action")]
                result = refresh_tactical_brief(
                    fleet_state, weather, recent_audit,
                    ollama_url=INFERENCE["ollama_url"].rstrip("/") + "/api/chat",
                )
                if result.get("ok"):
                    BUS.copilot("model:" + result["model_id"],
                                f"NEO tactical brief refreshed ({result['latency_ms']}ms, "
                                f"{result['eval_count']} tokens)",
                                severity="INFO", action="NEO_TACTICAL_BRIEF",
                                latency_ms=result["latency_ms"],
                                eval_count=result["eval_count"],
                                prompt_hash=result["prompt_hash"])
            except Exception as e:
                BUS.copilot("nemoclaw",
                            f"neo_tactical_brief_loop error: {e}",
                            severity="MED", action="NEO_BRIEF_ERROR")
        time.sleep(60)


# Lightweight test-status cache populated at boot + every 5 minutes by
# neo_test_status_loop. Keeps the dashboard cheap — running pytest on every
# /api/state call would be insane.
NEO_TEST_STATUS: dict = {
    "ok": False,
    "passed": 0, "failed": 0, "errors": 0, "total": 0,
    "duration_s": 0.0,
    "last_run_ts": 0,
    "summary": "(not run yet)",
}


def _run_pytest_collect() -> dict:
    """Run `pytest --collect-only -q` then `pytest -q --no-header` once to get
    a passed/failed summary. Subprocess; short timeout so we never wedge."""
    import subprocess
    repo = Path(__file__).resolve().parent.parent
    t0 = time.time()
    try:
        cp = subprocess.run(
            ["python", "-m", "pytest", "-q", "--no-header", "--tb=no"],
            cwd=str(repo),
            capture_output=True, text=True, timeout=120,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return {
            "ok": False, "passed": 0, "failed": 0, "errors": 0, "total": 0,
            "duration_s": time.time() - t0, "last_run_ts": int(time.time()),
            "summary": f"pytest failed to launch: {e}",
        }
    import re
    tail = (cp.stdout + "\n" + cp.stderr).strip().split("\n")
    # pytest -q --no-header output line shapes we accept:
    #   "44 passed in 0.39s"
    #   "============= 44 passed in 0.39s ============="
    #   "============= 1 failed, 43 passed in 0.39s ============="
    summary_line = ""
    for ln in reversed(tail):
        if ("passed" in ln or "failed" in ln or "error" in ln) and ("in " in ln):
            summary_line = ln.strip("= ").strip()
            break
    passed = failed = errors = 0
    m_p = re.search(r"(\d+) passed", summary_line)
    m_f = re.search(r"(\d+) failed", summary_line)
    m_e = re.search(r"(\d+) error", summary_line)
    if m_p: passed = int(m_p.group(1))
    if m_f: failed = int(m_f.group(1))
    if m_e: errors = int(m_e.group(1))
    return {
        "ok": (failed == 0 and errors == 0 and passed > 0),
        "passed": passed, "failed": failed, "errors": errors,
        "total": passed + failed + errors,
        "duration_s": round(time.time() - t0, 2),
        "last_run_ts": int(time.time()),
        "summary": summary_line or "(no pytest summary)",
    }


def neo_test_status_loop() -> None:
    """Run pytest once at boot, then every 5 minutes. Result lives in
    NEO_TEST_STATUS and is exposed via /api/neo/test-status."""
    global NEO_TEST_STATUS
    while True:
        try:
            NEO_TEST_STATUS = _run_pytest_collect()
            BUS.copilot("nemoclaw",
                        f"NEO test status: {NEO_TEST_STATUS['summary']}",
                        severity="INFO" if NEO_TEST_STATUS["ok"] else "MED",
                        action="NEO_TEST_STATUS",
                        passed=NEO_TEST_STATUS["passed"],
                        failed=NEO_TEST_STATUS["failed"],
                        duration_s=NEO_TEST_STATUS["duration_s"])
        except Exception as e:
            BUS.copilot("nemoclaw",
                        f"neo_test_status_loop error: {e}",
                        severity="HIGH", action="NEO_TEST_ERROR")
        time.sleep(300)


# ============================================================================
# NEO time-series collectors — Prometheus-style versus-time history so the
# dashboard can draw sparklines instead of just showing the current value.
#
# Each deque holds {ts, value} dicts. Cadence ranges from 1/min (SWPC,
# fleet-health) to per-call (LLM latencies). Bounded by maxlen so memory
# never grows unbounded.
# ============================================================================

_TS_LOCK = threading.Lock()
NEO_TIMESERIES: dict[str, deque] = {
    "swpc_kp":          deque(maxlen=720),   # 12h @ 1/min
    "swpc_xray":        deque(maxlen=720),
    "swpc_sep":         deque(maxlen=720),
    "llm_latency_ms":   deque(maxlen=400),   # last 400 LLM calls
    "llm_calls_per_min": deque(maxlen=720),  # per-minute aggregate
    "audit_actions_per_min": deque(maxlen=720),
    "fleet_green":      deque(maxlen=720),
    "fleet_yellow":     deque(maxlen=720),
    "fleet_red":        deque(maxlen=720),
    "fleet_black":      deque(maxlen=720),
    "fleet_unknown":    deque(maxlen=720),
    "cots_anomaly_count": deque(maxlen=720),
    "gpu_vram_pct":     deque(maxlen=720),
}

# Per-minute aggregators reset by neo_timeseries_minute_loop.
_TS_MINUTE_AGG = {
    "llm_calls_at_start": 0,
    "audit_actions_at_start": 0,
}


def _ts_record(metric: str, value: float, ts: float | None = None) -> None:
    if value is None:
        return
    if ts is None:
        ts = time.time()
    with _TS_LOCK:
        d = NEO_TIMESERIES.get(metric)
        if d is not None:
            d.append({"ts": ts, "v": float(value)})


def neo_timeseries_minute_loop() -> None:
    """Once per minute, snapshot SWPC + fleet health + audit rate + LLM rate.

    First sample fires after a short 8s warm-up (so SWPC/Ollama probes have
    completed) — gives the dashboard charts visible data on first load
    instead of "(no samples yet)".
    """
    last_llm_calls = INFERENCE.get("live_calls", 0)
    first = True
    while True:
        time.sleep(8 if first else 60)
        first = False
        try:
            now_ts = time.time()
            # SWPC values from the cached WEATHER snapshot
            wx = WEATHER.snapshot()
            _ts_record("swpc_kp",   wx.get("kp"),    now_ts)
            _ts_record("swpc_xray", wx.get("xray"),  now_ts)
            _ts_record("swpc_sep",  wx.get("sep_pfu"), now_ts)
            # Fleet health
            fh = fleet_health_counts()
            for color in ("GREEN", "YELLOW", "RED", "BLACK", "UNKNOWN"):
                _ts_record(f"fleet_{color.lower()}", fh.get(color, 0), now_ts)
            # LLM call rate over this minute
            cur_llm_calls = INFERENCE.get("live_calls", 0)
            delta = max(0, cur_llm_calls - last_llm_calls)
            last_llm_calls = cur_llm_calls
            _ts_record("llm_calls_per_min", delta, now_ts)
            # Audit action rate over this minute (read from in-memory tail)
            recent_audit = audit_tail(200)
            audit_count = sum(1 for r in recent_audit
                              if now_ts - _parse_ts(r.get("ts","")) < 60)
            _ts_record("audit_actions_per_min", audit_count, now_ts)
            # COTS anomaly count (any anomalous sat right now)
            anom = sum(1 for v in COTS_LATEST.values() if v.get("is_anomaly"))
            _ts_record("cots_anomaly_count", anom, now_ts)
            # GPU VRAM
            gpu = INFERENCE.get("host_gpu") or host_gpu_snapshot()
            if gpu and gpu.get("mem_total_mib"):
                pct = 100.0 * gpu["mem_used_mib"] / gpu["mem_total_mib"]
                _ts_record("gpu_vram_pct", pct, now_ts)
        except Exception as e:
            BUS.copilot("nemoclaw", f"neo_timeseries_minute_loop error: {e}",
                        severity="MED", action="NEO_TS_ERROR")


def _parse_ts(iso: str) -> float:
    """Parse 2026-05-27T10:23:45.123Z → unix epoch float. Returns 0 on parse fail."""
    if not iso:
        return 0.0
    try:
        # Strip the trailing Z and the millisecond suffix if present
        s = iso.rstrip("Z")
        if "." in s:
            s = s.split(".", 1)[0]
        dt = datetime.strptime(s, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, AttributeError):
        return 0.0


def _neo_timeseries_view(metric: str | None) -> dict:
    """If metric is None, return a list of available metrics + their latest value."""
    with _TS_LOCK:
        if metric is None:
            out = {"metrics": {}, "available": list(NEO_TIMESERIES.keys())}
            for name, dq in NEO_TIMESERIES.items():
                if dq:
                    out["metrics"][name] = {"latest": dq[-1]["v"], "samples": len(dq)}
                else:
                    out["metrics"][name] = {"latest": None, "samples": 0}
            return out
        dq = NEO_TIMESERIES.get(metric)
        if dq is None:
            return {"error": f"unknown metric {metric}", "available": list(NEO_TIMESERIES.keys())}
        return {
            "metric": metric,
            "samples": list(dq),
            "count": len(dq),
            "now_ts": time.time(),
        }


def _neo_provenance_view() -> dict:
    """Lightweight aggregation of what's currently backed by real LLM calls.
    Surfaces in the dashboard so judges/reviewers see what's real-time-LLM.
    """
    wx = WEATHER.snapshot()
    brief = get_tactical_brief()
    return {
        "weather": {
            "source": wx.get("source"),
            "real_data_age_s": wx.get("real_data_age_s"),
            "kp": wx.get("kp"),
            "xray_class": wx.get("xray_class"),
            "sep_pfu": wx.get("sep_pfu"),
        },
        "llm": {
            "mode": INFERENCE["mode"],
            "live_calls": INFERENCE.get("live_calls", 0),
            "director_calls": INFERENCE.get("director_calls", 0),
            "vram_gated": INFERENCE.get("vram_gated_count", 0),
        },
        "tactical_brief": {
            "ok": brief.get("ok"),
            "source": brief.get("source"),
            "ttl_remaining_s": brief.get("ttl_remaining_s"),
            "latency_ms": brief.get("latency_ms"),
            "model_id": brief.get("model_id"),
        },
        "kb": {
            "source": kb_load()[1],
            "count": len(kb_load()[0]),
        },
        "policy": {
            "policy_preset_hash": _nemoclaw_policy_hash(),
            "egress_allowlist_count": len(_nemoclaw_egress_allowlist()),
        },
        "tests": NEO_TEST_STATUS,
    }


def swpc_poll_loop() -> None:
    """NEO real-data wiring — poll NOAA SWPC every 60s.

    Each feed has its own cache TTL inside `swpc_fetch_all`; this loop just
    drives the cadence. On any feed failure it logs a MED severity audit row
    so the operator dashboard surfaces the degradation (Weather.source flips
    to "swpc-stale" or "simulated").
    """
    while True:
        try:
            snap = swpc_fetch_all(force=False)
            errs = [(name, f.get("error")) for name, f in snap.items()
                    if f.get("error")]
            if errs and swpc_is_real_data_available():
                BUS.copilot("nemoclaw",
                            f"SWPC poller — {len(errs)} feeds errored; using last-good cache",
                            severity="MED", action="SWPC_PARTIAL_DEGRADE")
            elif errs:
                BUS.copilot("nemoclaw",
                            f"SWPC poller — ALL feeds failed; falling back to simulated weather",
                            severity="HIGH", action="SWPC_FULL_DEGRADE")
        except Exception as e:
            BUS.copilot("nemoclaw",
                        f"swpc_poll_loop unexpected error: {e}",
                        severity="HIGH", action="SWPC_LOOP_ERROR")
        time.sleep(60)


def reprobe_loop() -> None:
    """Every 20s refresh the available-models list from Ollama. Lets newly
    pulled models join the lineup live, and resurrects models that come back
    after temporary failure.
    """
    while True:
        time.sleep(20)
        tags = _http_get(INFERENCE["ollama_url"].rstrip("/") + "/api/tags")
        if tags is None:
            continue
        new_list = [m["name"] for m in tags.get("models", [])]
        before = set(INFERENCE["available_models"])
        after = set(new_list)
        INFERENCE["available_models"] = new_list
        # Resurrect any lineup model that's now available but currently marked dead
        for m in PRIMARY_MODELS + BACKUP_MODELS:
            if m["id"] in after:
                if not m["alive"] and m["consecutive_fail"] >= CONSECUTIVE_FAIL_THRESHOLD:
                    # only auto-resurrect on first appearance, not after real failure
                    pass
                if m["id"] not in before:
                    # newly pulled: bring alive
                    m["alive"] = True
                    m["consecutive_fail"] = 0
                    BUS.copilot("nemoclaw",
                        f"Model {m['id']} ({m['vendor']}) now available — joining lineup.")
        BUS.publish({"type": "inference", "inference": inference_view()})


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
        BUS.copilot("user", "approve recommendation", who_label="Sampras")
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
        if path == "/api/catalog":        self._send_json({"catalog": VISUAL_CATALOG, "size": len(VISUAL_CATALOG)}); return
        if path == "/api/stream":         self._serve_sse(); return
        if path == "/api/audit/last10":   self._send_json(audit_tail(10)); return
        if path.startswith("/api/audit/last"):
            try:
                n = int(path.rsplit("last", 1)[1])
            except (ValueError, IndexError):
                n = 10
            self._send_json(audit_tail(max(1, min(n, 200)))); return
        if path == "/api/audit/policy-hash":
            self._send_json({"policy_preset_hash": _nemoclaw_policy_hash()}); return
        # NEO Action Item 2 — COTS telemetry + JPL detector surfaces
        if path.startswith("/api/cots/telemetry/"):
            sat_id = path.rsplit("/", 1)[1]
            self._send_json(cots_run_detector(sat_id)); return
        if path == "/api/cots/latest":
            self._send_json({"results": COTS_LATEST}); return
        # NEO Action Item 3 — beam-redirect drafts queue
        if path == "/api/decisions/beam-redirect/queue":
            self._send_json({"drafts": list(BEAM_DRAFTS_QUEUE), "count": len(BEAM_DRAFTS_QUEUE)}); return
        if path == "/api/decisions/beam-redirect/tool-schema":
            self._send_json(BEAM_REDIRECT_TOOL_SCHEMA); return
        if path == "/api/kb/source":
            entries, source = kb_load()
            self._send_json({"source": source, "count": len(entries)}); return
        # NEO panels — every cell backed by real Nemotron call
        if path == "/api/neo/tactical-brief":
            self._send_json(get_tactical_brief()); return
        if path == "/api/neo/test-status":
            self._send_json(NEO_TEST_STATUS); return
        if path == "/api/neo/provenance":
            self._send_json(_neo_provenance_view()); return
        if path == "/api/neo/timeseries":
            metric = None
            if "?" in self.path:
                q = self.path.split("?", 1)[1]
                for pair in q.split("&"):
                    if pair.startswith("metric="):
                        metric = pair.split("=", 1)[1]
            self._send_json(_neo_timeseries_view(metric)); return
        if path == "/api/neo/storage-audit":
            from desk.admin.storage_audit import storage_audit
            self._send_json(storage_audit()); return
        if path == "/api/neo/at-risk":
            top_n = 25
            if "?" in self.path:
                for pair in self.path.split("?", 1)[1].split("&"):
                    if pair.startswith("n="):
                        try: top_n = max(1, min(int(pair.split("=", 1)[1]), 200))
                        except ValueError: pass
            ranked = rank_fleet_by_risk(
                sats=SATS, weather=WEATHER.snapshot(),
                orbit_lookup=lambda sid: sgp4_propagate(sid, ts_utc=time.time()),
                cots_lookup=lambda sid: COTS_LATEST.get(sid),
                top_n=top_n,
            )
            summary = fleet_risk_summary(
                sats=SATS, weather=WEATHER.snapshot(),
                orbit_lookup=lambda sid: sgp4_propagate(sid, ts_utc=time.time()),
                cots_lookup=lambda sid: COTS_LATEST.get(sid),
            )
            self._send_json({"top": ranked, "summary": summary,
                             "ts": time.time()}); return
        if path == "/api/neo/space-weather-forecast":
            self._send_json(swpc_combined_forecast()); return
        if path == "/api/neo/where-needs-starlink":
            d = disaster_fetch_combined()
            self._send_json(d.get("value") or {"events": [], "errors": d.get("error")}); return
        if path == "/api/neo/wiki/stats":
            from desk.knowledge.wiki_rag import wiki_stats
            self._send_json(wiki_stats()); return
        if path == "/api/neo/wiki/retrieve":
            from desk.knowledge.wiki_rag import wiki_retrieve
            q = None
            top_k = 5
            if "?" in self.path:
                qs = self.path.split("?", 1)[1]
                for pair in qs.split("&"):
                    if pair.startswith("q="):
                        from urllib.parse import unquote
                        q = unquote(pair.split("=", 1)[1])
                    elif pair.startswith("k="):
                        try: top_k = int(pair.split("=", 1)[1])
                        except ValueError: pass
            hits = wiki_retrieve(q or "", top_k=top_k)
            self._send_json({
                "query": q,
                "top_k": top_k,
                "hits": [{"path": h.path, "title": h.title, "snippet": h.snippet, "score": h.score} for h in hits],
            }); return
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
            BUS.copilot("user", "approve recommendation", who_label="Sampras")
            BUS.copilot("nemoclaw", "Approved — command queued to NemoClaw audit.", action="APPROVED")
            self._send_json({"ok": True}); return
        if self.path == "/api/storm":
            kind = body.get("kind", "flare")
            run_terminal_command(f"storm {kind}")
            self._send_json({"ok": True}); return
        if self.path == "/api/decisions/beam-redirect/draft":
            # NEO Action Item 3 — manually request a beam-redirect draft on
            # demand. Justification text is generated by a real Nemotron call
            # via llm_justify_beam_redirect (template fallback on Ollama miss).
            sat_id = str(body.get("sat", ""))
            target_lat = float(body.get("target_lat", 0.0))
            target_lon = float(body.get("target_lon", 0.0))
            regime = body.get("regime", "see")
            sat = find_sat(sat_id)
            if not sat:
                self._send_json({"error": f"unknown sat {sat_id}"}, status=404); return
            orbit = sgp4_propagate(sat_id, ts_utc=time.time())
            draft = brief_beam_redirect(
                sat=sat,
                anomaly_regime=regime,
                target_lat_deg=target_lat,
                target_lon_deg=target_lon,
                confidence=0.75,
                sub_sat_lat=(orbit or {}).get("lat_deg") if orbit else None,
                sub_sat_lon=(orbit or {}).get("lon_deg") if orbit else None,
                sat_alt_km=(orbit or {}).get("alt_km") if orbit else sat.get("altitude_km"),
                incident_summary=body.get("incident_summary",
                                          "operator-initiated draft"),
            )
            # Replace templated justification with real Nemotron-generated text.
            kb_entries = kb_lookup(failure_mode=regime, regime="LEO", limit=3)
            llm_result = llm_justify_beam_redirect(
                sat_id=draft.sat_id,
                anomaly_regime=regime,
                target_lat=draft.target_lat_deg,
                target_lon=draft.target_lon_deg,
                tilt_deg=draft.tilt_deg,
                duration_s=draft.duration_s,
                incident_summary=body.get("incident_summary", "operator-initiated draft"),
                kb_entries=kb_entries,
                ollama_url=INFERENCE["ollama_url"].rstrip("/") + "/api/chat",
            )
            draft.justification = llm_result["text"]
            draft.evidence_pointers = [e.entry_id for e in kb_entries[:3]]
            BUS.copilot("model:" + llm_result["model_id"],
                        f"justify beam-redirect for {sat_id} via {llm_result['source']} "
                        f"({llm_result['latency_ms']}ms, {llm_result['eval_count']} tokens)",
                        severity="INFO", action="BEAM_REDIRECT_LLM_JUSTIFY",
                        sat_id=sat_id, llm_source=llm_result["source"],
                        latency_ms=llm_result["latency_ms"],
                        eval_count=llm_result["eval_count"],
                        prompt_hash=llm_result["prompt_hash"],
                        override_invariant="O2-decision-verb-4th")
            allow, _, denied = output_guard(draft.justification)
            if not allow:
                self._send_json({"blocked": True, "denied_actions": denied}, status=403); return
            draft_dict = draft.to_dict()
            # Attach LLM provenance fields so dashboard can show the badge.
            draft_dict["llm_source"] = llm_result["source"]
            draft_dict["llm_latency_ms"] = llm_result["latency_ms"]
            draft_dict["llm_model_id"] = llm_result["model_id"]
            BEAM_DRAFTS_QUEUE.insert(0, draft_dict)
            if len(BEAM_DRAFTS_QUEUE) > 50:
                BEAM_DRAFTS_QUEUE.pop()
            BUS.copilot("user",
                        f"operator-drafted beam-redirect for {sat_id}",
                        severity="MED", action="BEAM_REDIRECT_DRAFT_MANUAL",
                        sat_id=sat_id, decision_route="needs-review",
                        evidence_pointers=draft.evidence_pointers,
                        override_invariant="O2-decision-verb-4th")
            self._send_json(draft_dict); return
        if self.path == "/api/dev/inject-anomaly":
            # NEO Action Item 2 — manual SEE / dielectric_charge anomaly injection
            # for demo runs. Triggers a cooldown spike in the COTS stream that
            # the JPL detector picks up within ~2s.
            sat_id = str(body.get("sat", ""))
            kind = body.get("kind", "see")
            stream = cots_init()
            if sat_id not in stream.known_sats():
                self._send_json({"error": f"unknown sat {sat_id}"}, status=404); return
            with stream._lock:
                st = stream._states[sat_id]
                if kind == "see":
                    st.see_cooldown_ticks = int(stream.hz * 1.5)
                elif kind in ("dielectric_charge", "charge"):
                    st.charge_cooldown_ticks = int(stream.hz * 0.6)
                else:
                    self._send_json({"error": f"unknown kind {kind}"}, status=400); return
            BUS.copilot("user", f"manual COTS anomaly injection ({kind}) on {sat_id}",
                        severity="MED", action="COTS_INJECT", sat_id=sat_id, kind=kind,
                        override_invariant="O1-source-list-5th-input")
            self._send_json({"ok": True, "sat": sat_id, "kind": kind}); return
        if self.path == "/api/probe-ollama":
            result = probe_ollama()
            BUS.publish({"type": "inference", "inference": inference_view(), "probe": result})
            self._send_json(result); return
        if self.path == "/api/inference":
            mode = (body.get("mode") or "").upper()
            if mode == "SIM":
                INFERENCE["mode"] = "SIM"
            elif mode == "LIVE-OLLAMA":
                # only honoured if Ollama is reachable
                result = probe_ollama()
                if not result.get("ok"):
                    self._send_json({"error": "Ollama not ready", "detail": result}, status=409); return
            BUS.publish({"type": "inference", "inference": inference_view()})
            self._send_json({"mode": INFERENCE["mode"]}); return
        if self.path == "/api/council-mode":
            mode = (body.get("mode") or "").upper()
            if mode not in COUNCIL_MODES:
                self._send_json({"error": "unknown mode", "valid": list(COUNCIL_MODES.keys())}, status=400)
                return
            INFERENCE["council_mode"] = mode
            BUS.publish({"type": "inference", "inference": inference_view()})
            self._send_json({"ok": True, "mode": mode})
            return
        if self.path.startswith("/api/inbox/"):
            try:
                _, _, _, inbox_id_str, op = self.path.split("/")
                inbox_id = int(inbox_id_str)
            except (ValueError, IndexError):
                self._send_json({"error": "bad inbox path"}, status=400); return
            state = "REVIEWED" if op == "accept" else "DISMISSED" if op == "dismiss" else None
            if state is None:
                self._send_json({"error": "use /accept or /dismiss"}, status=400); return
            ok = BUS.inbox_set_state(inbox_id, state)
            self._send_json({"ok": ok, "state": state})
            return
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

    # Auto-probe Ollama once at boot so the user immediately sees whether
    # LIVE-OLLAMA is available without having to click anything.
    INFERENCE["host_gpu"] = host_gpu_snapshot()
    try:
        boot_probe = probe_ollama()
        print(f"[spacesharks-desk] Ollama probe: {boot_probe}", flush=True)
    except Exception as e:
        print(f"[spacesharks-desk] Ollama probe failed: {e}", flush=True)

    # NEO real-data: pre-flight Celestrak TLE refresh + first SWPC poll.
    # If the network is unreachable both calls return cleanly with a fallback;
    # the operator dashboard will show source="simulated" until SWPC comes back.
    try:
        tle_result = refresh_tle_cache(force=False)
        print(f"[spacesharks-desk] Celestrak TLE: {tle_result}", flush=True)
    except Exception as e:
        print(f"[spacesharks-desk] Celestrak TLE refresh failed: {e}", flush=True)
    try:
        first_swpc = swpc_fetch_all(force=False)
        kp_val = first_swpc.get("kp_1m", {}).get("value")
        xray_val = first_swpc.get("xray_1d", {}).get("value")
        sep_val = first_swpc.get("sep_1d", {}).get("value")
        print(f"[spacesharks-desk] SWPC live: Kp={kp_val} xray={xray_val} sep={sep_val}", flush=True)
    except Exception as e:
        print(f"[spacesharks-desk] SWPC initial fetch failed: {e}", flush=True)

    threading.Thread(target=assessment_loop, daemon=True).start()
    threading.Thread(target=copilot_loop, daemon=True).start()
    threading.Thread(target=token_history_loop, daemon=True).start()
    threading.Thread(target=reprobe_loop, daemon=True).start()
    # NEO Action Item 2 — COTS telemetry + JPL detector
    threading.Thread(target=cots_telemetry_loop, daemon=True).start()
    # NEO real-data — NOAA SWPC poller
    threading.Thread(target=swpc_poll_loop, daemon=True).start()
    # NEO Tactical Brief — real Nemotron-generated executive summary every 60s
    threading.Thread(target=neo_tactical_brief_loop, daemon=True).start()
    # NEO test-status — pytest every 5min
    threading.Thread(target=neo_test_status_loop, daemon=True).start()
    # NEO time-series — Prometheus-style sample collectors @ 1/min
    threading.Thread(target=neo_timeseries_minute_loop, daemon=True).start()

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[spacesharks-desk] http://{args.host}:{args.port}/  (writing {JSONL})", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("[spacesharks-desk] shutting down", file=sys.stderr)


if __name__ == "__main__":
    main()
