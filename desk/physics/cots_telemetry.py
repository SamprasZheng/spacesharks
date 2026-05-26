"""desk.physics.cots_telemetry — 50 Hz simulated COTS chip telemetry stream.

NEO Action Item 2 — under override O1 (source-list-lock 5th input). The stream
is deterministic per (sat_id, regime) seed plus environmental modulation from
space-weather (Kp / X-ray / SEP) and orbit position (eclipse, SAA proximity).
No real hardware; no real spacecraft actuation; no external egress.

Three primary metrics:
  current_mA          — chip supply current; rises with TID damage + flares
  voltage_V           — supply-rail voltage; drops during SEL latch-up events
  seu_bit_error_rate  — bit-error-rate observed over the last second

Plus a coarser regime label (`tid` / `see` / `dielectric_charge` / `nominal`)
emitted by `TelemetryStream.tick()` so the JPL detector and the arbiter both
see a structured anomaly hint.
"""

from __future__ import annotations

import math
import random
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Iterable


# Sliding window length for the JPL detector — 1024 samples @ 50 Hz = ~20 s.
WINDOW_SAMPLES = 1024


@dataclass
class TelemetrySample:
    ts_utc: float
    sat_id: str
    current_mA: float
    voltage_V: float
    seu_bit_error_rate: float
    regime_hint: str  # nominal | tid | see | dielectric_charge


@dataclass
class _SatState:
    """Per-sat random state so streams are independent + deterministic."""
    sat_id: str
    base_current_mA: float
    base_voltage_V: float
    rng: random.Random
    tid_damage: float = 0.0          # cumulative; rises in space-weather events
    see_cooldown_ticks: int = 0      # nonzero = mid-event; voltage drop
    charge_cooldown_ticks: int = 0   # dielectric discharge
    buffer: "deque[TelemetrySample]" = field(default_factory=lambda: deque(maxlen=WINDOW_SAMPLES))


class TelemetryStream:
    """50 Hz simulated telemetry stream across a fleet.

    Usage::

        stream = TelemetryStream([sat["id"] for sat in SATS])
        stream.tick(get_weather, get_orbit)   # call at 50 Hz from a worker
        win = stream.window("44737")          # numpy-compatible list[float]
    """

    def __init__(self, sat_ids: Iterable[str], hz: float = 50.0) -> None:
        self.hz = hz
        self._states: dict[str, _SatState] = {}
        self._lock = threading.Lock()
        for sid in sat_ids:
            self._register(sid)

    def _register(self, sat_id: str) -> _SatState:
        rng = random.Random(int(hash("cots-" + sat_id)) & 0xFFFFFFFF)
        st = _SatState(
            sat_id=sat_id,
            base_current_mA=rng.uniform(400.0, 900.0),
            base_voltage_V=rng.uniform(3.25, 3.35),
            rng=rng,
        )
        self._states[sat_id] = st
        return st

    def known_sats(self) -> list[str]:
        with self._lock:
            return list(self._states.keys())

    def window(self, sat_id: str) -> list[TelemetrySample]:
        with self._lock:
            st = self._states.get(sat_id)
            if not st:
                return []
            return list(st.buffer)

    def tick(
        self,
        *,
        ts_utc: float | None = None,
        weather: dict | None = None,
        orbit_lookup=None,  # callable: sat_id -> dict | None
    ) -> dict[str, TelemetrySample]:
        """Generate one sample per sat at this tick.

        `weather` is the `WEATHER.snapshot()` dict from server.py (kp / xray /
        sep_pfu / storm_regime). `orbit_lookup` returns the SGP4 propagate()
        dict for a sat, used for eclipse + SAA proximity hints.
        """
        if ts_utc is None:
            ts_utc = time.time()
        weather = weather or {}
        kp = float(weather.get("kp", 2.0))
        xray = float(weather.get("xray", 1e-7))
        sep = float(weather.get("sep_pfu", 0.5))
        # X-class flare ⇒ ≥ 1e-4 W/m²; SEP storm ≥ 10 pfu
        flare_score = max(0.0, math.log10(max(xray, 1e-9)) + 7.0) / 3.0   # 0..2 typical
        sep_score = max(0.0, math.log10(max(sep, 0.1) + 1) - 1.0)         # 0..2 typical
        storm_score = max(0.0, (kp - 4.0) / 4.0)                          # 0..1.25 typical

        out: dict[str, TelemetrySample] = {}
        with self._lock:
            for sid, st in self._states.items():
                orbit = orbit_lookup(sid) if orbit_lookup else None
                in_eclipse = bool(orbit and orbit.get("in_eclipse"))
                # SAA proxy: lat in [-50..-20] AND lon in [-90..0]
                saa = False
                if orbit and orbit.get("ok"):
                    lat = orbit["lat_deg"]
                    lon = orbit["lon_deg"]
                    saa = -50.0 <= lat <= -20.0 and -90.0 <= lon <= 0.0

                # Cumulative TID damage rises slowly with flare exposure.
                # Real spacecraft accumulate krad/yr; we accelerate so the
                # demo can show drift inside a few minutes.
                st.tid_damage += flare_score * 0.0005 + storm_score * 0.0002

                # Probabilistic SEE event — single-event latch-up. Probability
                # rises sharply during SEP events and SAA passes.
                if st.see_cooldown_ticks == 0:
                    p_see = 1e-4 + 5e-4 * sep_score + 4e-4 * (1.0 if saa else 0.0)
                    if st.rng.random() < p_see:
                        st.see_cooldown_ticks = int(self.hz * st.rng.uniform(0.4, 1.5))
                else:
                    st.see_cooldown_ticks -= 1

                # Dielectric charging discharge — favoured by high-Kp storms
                # AND eclipse exit (charge buildup during eclipse).
                if st.charge_cooldown_ticks == 0:
                    p_chg = 2e-5 + 8e-4 * storm_score * (1.0 if in_eclipse else 0.0)
                    if st.rng.random() < p_chg:
                        st.charge_cooldown_ticks = int(self.hz * st.rng.uniform(0.2, 0.6))
                else:
                    st.charge_cooldown_ticks -= 1

                # Sample current_mA — base + TID drift + flare noise + SEE spike.
                noise = st.rng.gauss(0.0, 2.0)
                current = st.base_current_mA \
                    * (1.0 + 0.10 * st.tid_damage) \
                    + 8.0 * flare_score \
                    + noise
                if st.see_cooldown_ticks > 0:
                    current += 250.0 + st.rng.uniform(0, 80.0)  # latch-up current spike

                # voltage_V — base minus rail droop during SEE/charge events.
                voltage = st.base_voltage_V - 0.01 * st.tid_damage \
                    - st.rng.gauss(0.0, 0.003)
                if st.see_cooldown_ticks > 0:
                    voltage -= st.rng.uniform(0.10, 0.25)
                if st.charge_cooldown_ticks > 0:
                    voltage -= st.rng.uniform(0.05, 0.15)

                # SEU BER rises with SEP score AND SAA.
                ber = 1e-9 + 5e-8 * sep_score \
                    + (1e-7 if saa else 0.0) \
                    + (5e-7 if st.see_cooldown_ticks > 0 else 0.0)

                # Regime hint — purely heuristic; the JPL detector is the
                # ground truth for the arbiter, but this is a useful field to
                # surface in the dashboard.
                if st.see_cooldown_ticks > 0:
                    regime = "see"
                elif st.charge_cooldown_ticks > 0:
                    regime = "dielectric_charge"
                elif st.tid_damage > 0.8:
                    regime = "tid"
                else:
                    regime = "nominal"

                samp = TelemetrySample(
                    ts_utc=ts_utc,
                    sat_id=sid,
                    current_mA=round(current, 3),
                    voltage_V=round(voltage, 4),
                    seu_bit_error_rate=ber,
                    regime_hint=regime,
                )
                st.buffer.append(samp)
                out[sid] = samp

        return out


# Module-level helper for tests + dashboard panels.
def telemetry_buffer_for(stream: TelemetryStream, sat_id: str, metric: str) -> list[float]:
    """Extract one metric as a flat list[float] for the JPL detector."""
    win = stream.window(sat_id)
    if metric == "current_mA":
        return [s.current_mA for s in win]
    if metric == "voltage_V":
        return [s.voltage_V for s in win]
    if metric == "seu_bit_error_rate":
        return [s.seu_bit_error_rate for s in win]
    raise ValueError(f"unknown metric: {metric}")
