"""desk.decisions.at_risk_ranking — multi-sat composite risk scoring.

Answers user question "哪些衛星有危險?" by computing a single risk score
per satellite from real / projected signals, ranking the fleet DESC, and
returning the top-N with each risk driver enumerated.

This replaces the single-satellite focused-panel pattern with a multi-sat
queue. Score is bounded [0, 100]; each driver contributes 0-30 points and
the function explains which drivers fired.

Inputs (all from server.py state):
  sat              — fleet row with age, TID/budget, SEEs 30d, regime
  weather          — current Kp/Xray/SEP from real SWPC
  orbit            — SGP4 sub-satellite point (lat/lon, eclipse hint)
  cots_anomaly     — JPL detector latest result for this sat (or None)
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass


@dataclass
class RiskDriver:
    name: str           # short code, e.g. "TID_ACCUMULATION"
    label: str          # human-readable e.g. "TID 18/20 krad — 90% of budget"
    score: float        # contribution to total risk (0-30)
    severity: str       # "low" | "medium" | "high"


@dataclass
class SatRisk:
    sat_id: str
    sat_name: str
    regime: str
    total_score: float        # 0-100
    band: str                 # GREEN | YELLOW | RED | BLACK
    drivers: list[RiskDriver]
    health_label: str         # latest LLM-labelled health from assess_sat
    summary: str              # one-line rationale

    def to_dict(self) -> dict:
        return {
            "sat_id": self.sat_id,
            "sat_name": self.sat_name,
            "regime": self.regime,
            "total_score": round(self.total_score, 2),
            "band": self.band,
            "drivers": [
                {"name": d.name, "label": d.label,
                 "score": round(d.score, 2), "severity": d.severity}
                for d in self.drivers
            ],
            "health_label": self.health_label,
            "summary": self.summary,
        }


def _band_for_score(score: float) -> str:
    if score >= 75: return "BLACK"
    if score >= 55: return "RED"
    if score >= 30: return "YELLOW"
    return "GREEN"


def _saa_proximity(lat: float | None, lon: float | None) -> float:
    """South Atlantic Anomaly weight 0..1 based on lat/lon distance from
    SAA centre (~-30°, -30°)."""
    if lat is None or lon is None:
        return 0.0
    saa_lat, saa_lon = -25.0, -45.0
    d = math.sqrt((lat - saa_lat) ** 2 + (lon - saa_lon) ** 2)
    if d > 60:
        return 0.0
    return max(0.0, 1.0 - d / 60.0)


def compute_sat_risk(
    *,
    sat: dict,
    weather: dict,
    orbit: dict | None = None,
    cots_anomaly: dict | None = None,
) -> SatRisk:
    """Computes the composite risk score + driver breakdown for one sat."""
    drivers: list[RiskDriver] = []

    # --- 1. TID accumulation (0-30) -----------------------------------------
    tid_acc = float(sat.get("tid_accumulated_krad", 0))
    tid_budget = float(sat.get("tid_budget_krad", 1) or 1)
    tid_ratio = min(1.0, tid_acc / max(tid_budget, 0.001))
    tid_score = 30.0 * tid_ratio
    if tid_ratio >= 0.5:
        drivers.append(RiskDriver(
            name="TID_ACCUMULATION",
            label=f"TID {tid_acc:.1f}/{tid_budget:.0f} krad — {tid_ratio*100:.0f}% of budget",
            score=tid_score,
            severity="high" if tid_ratio >= 0.8 else "medium",
        ))

    # --- 2. Age vs design life (0-20) ---------------------------------------
    age_years = 0.0
    launched = sat.get("launched")
    if launched:
        try:
            from datetime import datetime
            ld = datetime.strptime(launched, "%Y-%m-%d")
            age_years = (datetime.utcnow() - ld).days / 365.25
        except (TypeError, ValueError):
            pass
    design_life = float(sat.get("design_life_years", 5) or 5)
    age_ratio = min(1.0, age_years / max(design_life, 0.001))
    age_score = 20.0 * age_ratio
    if age_ratio >= 0.7:
        drivers.append(RiskDriver(
            name="AGE_EOL",
            label=f"Age {age_years:.1f}y / {design_life:.0f}y design life ({age_ratio*100:.0f}%)",
            score=age_score,
            severity="high" if age_ratio >= 1.0 else "medium",
        ))

    # --- 3. Recent SEE events (0-15) ----------------------------------------
    sees_30d = int(sat.get("see_events_30d", 0))
    see_score = min(15.0, sees_30d * 3.0)
    if sees_30d >= 2:
        drivers.append(RiskDriver(
            name="SEE_EVENTS",
            label=f"{sees_30d} SEE events in last 30 days",
            score=see_score,
            severity="high" if sees_30d >= 5 else "medium",
        ))

    # --- 4. Space weather exposure (0-20) -----------------------------------
    kp = float(weather.get("kp") or 0)
    xray = float(weather.get("xray") or 0)
    sep = float(weather.get("sep_pfu") or 0)
    wx_score = 0.0
    wx_drivers = []
    if kp >= 5:
        wx_score += min(8, (kp - 5) * 4)
        wx_drivers.append(f"Kp={kp:.1f}")
    # X-class flare = xray >= 1e-4
    if xray >= 1e-5:
        wx_score += min(8, math.log10(xray / 1e-7) * 2)
        flare_class = "X" if xray >= 1e-4 else "M" if xray >= 1e-5 else "C"
        wx_drivers.append(f"X-ray={flare_class}-class")
    # SEP > 10 pfu = solar radiation storm
    if sep >= 10:
        wx_score += min(8, math.log10(sep) * 4)
        wx_drivers.append(f"SEP={sep:.1f} pfu")
    if wx_drivers:
        drivers.append(RiskDriver(
            name="SPACE_WEATHER",
            label="Active space weather: " + ", ".join(wx_drivers),
            score=wx_score,
            severity="high" if wx_score >= 12 else "medium",
        ))

    # --- 5. SAA pass (0-10) ------------------------------------------------
    if orbit and orbit.get("ok"):
        saa_weight = _saa_proximity(orbit.get("lat_deg"), orbit.get("lon_deg"))
        if saa_weight > 0.3:
            saa_score = 10.0 * saa_weight
            drivers.append(RiskDriver(
                name="SAA_PASS",
                label=f"In/near South Atlantic Anomaly (proximity {saa_weight:.2f})",
                score=saa_score,
                severity="medium",
            ))
        if orbit.get("in_eclipse"):
            drivers.append(RiskDriver(
                name="ECLIPSE",
                label="In Earth shadow (charge accumulation window)",
                score=4.0,
                severity="low",
            ))

    # --- 6. COTS anomaly active (0-25) -------------------------------------
    if cots_anomaly and cots_anomaly.get("is_anomaly"):
        regime = cots_anomaly.get("regime", "anomaly")
        magnitude = float(cots_anomaly.get("magnitude", 0))
        anom_score = min(25.0, 8.0 + magnitude * 2.0)
        drivers.append(RiskDriver(
            name="COTS_ANOMALY",
            label=f"JPL detector tripped — regime={regime}, magnitude={magnitude:.2f}σ",
            score=anom_score,
            severity="high",
        ))

    # --- Sum + clamp + band -----------------------------------------------
    total = sum(d.score for d in drivers)
    # Add a small contribution from non-fired moderate drivers so band-changes
    # are smoother (e.g. TID at 30% still counts a little).
    total += tid_score * 0.3 if tid_ratio < 0.5 else 0
    total += age_score * 0.3 if age_ratio < 0.7 else 0
    total = min(100.0, total)
    band = _band_for_score(total)
    if not drivers:
        drivers.append(RiskDriver(
            name="NOMINAL",
            label="No active drivers — nominal envelope",
            score=0.0,
            severity="low",
        ))

    # Summary line
    if drivers and drivers[0].name != "NOMINAL":
        top = drivers[0]
        summary = f"{band}: {top.label}"
        if len(drivers) > 1:
            summary += f" (+{len(drivers)-1} more)"
    else:
        summary = f"{band}: nominal envelope, no drivers"

    return SatRisk(
        sat_id=str(sat.get("id")),
        sat_name=str(sat.get("name", sat.get("id"))),
        regime=str(sat.get("regime", "?")),
        total_score=total,
        band=band,
        drivers=drivers,
        health_label=str(sat.get("health", "UNKNOWN")),
        summary=summary,
    )


def rank_fleet_by_risk(
    *,
    sats: list[dict],
    weather: dict,
    orbit_lookup=None,
    cots_lookup=None,
    top_n: int = 25,
) -> list[dict]:
    """Returns top-N satellites sorted by total risk score, each as a dict.

    `orbit_lookup(sat_id) -> orbit dict | None`
    `cots_lookup(sat_id)  -> JPL detector latest dict | None`
    """
    ranked: list[SatRisk] = []
    for sat in sats:
        sid = str(sat.get("id"))
        orbit = orbit_lookup(sid) if orbit_lookup else None
        cots = cots_lookup(sid) if cots_lookup else None
        ranked.append(compute_sat_risk(sat=sat, weather=weather, orbit=orbit, cots_anomaly=cots))
    ranked.sort(key=lambda r: r.total_score, reverse=True)
    return [r.to_dict() for r in ranked[:max(1, top_n)]]


def fleet_risk_summary(*, sats: list[dict], weather: dict,
                      orbit_lookup=None, cots_lookup=None) -> dict:
    """Counts of sats per band — for the dashboard summary tile."""
    ranked: list[SatRisk] = []
    for sat in sats:
        sid = str(sat.get("id"))
        orbit = orbit_lookup(sid) if orbit_lookup else None
        cots = cots_lookup(sid) if cots_lookup else None
        ranked.append(compute_sat_risk(sat=sat, weather=weather, orbit=orbit, cots_anomaly=cots))
    bands = {"GREEN": 0, "YELLOW": 0, "RED": 0, "BLACK": 0}
    for r in ranked:
        bands[r.band] = bands.get(r.band, 0) + 1
    return {
        "bands": bands,
        "total": len(ranked),
        "ts": time.time(),
    }
