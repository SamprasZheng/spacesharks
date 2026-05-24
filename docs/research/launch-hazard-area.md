---
title: Launch Hazard Area (LHA) / Aircraft Hazard Area (AHA)
type: research
category: operational
status: ingested
ingested: 2026-05-24
sources:
  - https://www.ecfr.gov/current/title-14/chapter-III/subchapter-C/part-450  # 14 CFR Part 450
  - https://www.ecfr.gov/current/title-14/chapter-III/subchapter-C/part-417  # 14 CFR Part 417 (legacy)
  - https://www.faa.gov/space/streamlined_licensing_process
  - https://www.faa.gov/air_traffic/publications/atpubs/notam_html/  # NOTAM PHAM
---

# Launch Hazard Area (LHA) / Aircraft Hazard Area (AHA)

> Status: operational reference. **Out of MVP scope** — listed in
> [INDEX.md](INDEX.md) under "Deferred." This note exists so that whoever
> wires the FAA NOTAM ingestor post-MVP does not have to reverse-engineer
> the geometry from the polygons. The companion is
> [notam-space-operations.md](notam-space-operations.md), which covers the
> NOTAM container that carries the polygon.

A **Launch Hazard Area (LHA)** — formally called an **Aircraft Hazard Area
(AHA)** in current FAA Part 450 terminology — is the airspace volume
closed to non-participating aircraft and maritime vessels around a rocket
launch or re-entry event. The AHA is the geometric product of a **flight
hazard analysis** and is the single most operationally consequential output
of that analysis, because it directly determines which flights are rerouted
and by how much.

For the Mission Desk's post-MVP Phase 1 (pre-launch survivability) and
Phase 5 (re-entry / EOL) loops, the LHA polygon embedded in a launch NOTAM
is the primary signal: **an unusually large LHA relative to prior launches
of the same vehicle is an early indicator of a trajectory change,
reliability concern, or expanded mission scope.**

## 1. Terminology: LHA vs AHA vs TFR

- **LHA** (Launch Hazard Area) — older FAA term, 14 CFR Part 417, which
  governed expendable launch vehicle safety before Part 450 replaced it in
  March 2021.
- **AHA** (Aircraft Hazard Area) — current Part 450 term, extended to cover
  both launch and re-entry.
- **TFR** (Temporary Flight Restriction) — one of the airspace tools used
  to implement an AHA, but not the AHA itself. A single AHA may be
  implemented as a combination of TFRs, Warning Areas, ATCAAs (Air Traffic
  Control Assigned Airspace), and ALTRVs (Stationary Altitude
  Reservations).

Regulatory home: **14 CFR Part 450 § 450.133** (Aircraft Hazard Areas) and
Appendix B to former Part 417 (Flight Hazard Area Analysis for Aircraft
and Ship Protection).

## 2. Geometric derivation — how the AHA footprint is computed

The AHA is **not a fixed circle** around the launch pad. It is constructed
from a **trajectory dispersion analysis**.

### 2.1 Launch-site AHA (near-field)

1. **Nominal trajectory simulation.** Compute the vehicle's planned
   trajectory from T-0 to stage separation or orbital insertion.
2. **Dispersed trajectory envelope.** Propagate Monte Carlo dispersions
   (wind, thrust variation, guidance error, structural failure modes) to
   find the farthest left/right crossrange, downrange, and uprange
   footprint positions.
3. **Bounding box.** Draw a polygon enclosing the four extreme dispersed
   positions (uprange, downrange, max crossrange left, max crossrange
   right).
4. **Near-launch radial expansion.** For the area immediately surrounding
   the launch site, add **5 NM in every radial direction** as a buffer
   for short-range debris trajectories not captured by the trajectory
   dispersions.
5. **Altitude extent.** Surface to **100,000 ft MSL** for the launch-site
   AHA in most analyses; this is effectively "surface to unlimited" for
   commercial aviation (all commercial routes operate below 45,000 ft).

### 2.2 Stage-impact AHA (downrange)

1. **Stage-2 / upper-stage impact ellipse.** Compute the **3σ dispersion
   ellipse** for the planned impact location (Gaussian spread of potential
   impact points at the 3-sigma confidence level).
2. **10 NM buffer.** Extend both axes of the ellipse by 10 NM.
3. **Infinite vertical extent.** The stage-impact AHA extends from surface
   to unlimited upward.

### 2.3 Blast overpressure radius (catastrophic pad failure)

```
R_op = 45 * (NEW)^(1/3)
```

where `NEW` = Net Explosive Weight (kg of propellant TNT equivalent). The
formula yields meters; convert to NM for the NOTAM polygon.

### 2.4 Safety threshold

The AHA must be sized so that for every aircraft that might be in the
hazard area, the **individual expected casualty (Ec) probability does
not exceed 1 × 10⁻⁶ per launch attempt**. This is the FAA/Part 450
standard. The maritime ship threshold is **1 × 10⁻⁵**.

## 3. What the LHA covers operationally

A single orbital launch from Kennedy Space Center can generate **four
separate AHAs** filed as separate NOTAMs:

1. **Launch-site AHA** — surface to unlimited, covers the immediate pad
   area and low-altitude flight path (radius ~30 NM from KSC for Falcon 9).
2. **Ascent corridor AHA** — extends over the Atlantic trajectory (for
   KSC eastward launches), reaching hundreds of NM over ocean.
3. **Stage-1 (booster) landing zone AHA** — covers the drone-ship or
   RTLS landing zone; activated and deactivated in real time as the
   booster descends.
4. **Stage-2 re-entry/impact AHA** — covers the planned upper-stage
   disposal point; often extends into international airspace requiring
   foreign FIR coordination.

For Starship Super Heavy IFT-9 (May 2025 license modification), the
expanded AHA covered the Bahamas and Turks & Caicos Islands — affecting
more than 175 airline flights with an average 40-minute delay per flight.

## 4. AHA size as an operational intelligence signal

An agent that tracks AHA polygon area over successive launches of the
same vehicle can detect operationally meaningful changes:

| LHA area change vs prior flight | Probable cause |
|---|---|
| Larger than previous flight | New trajectory, reliability reduction, expanded mission (RTLS add-on, new stage-2 disposal site) |
| Smaller than previous flight | Improved reliability score, simplified mission profile, SDI real-time shrink |
| Same polygon, different orientation | Trajectory azimuth change (inclination change, launch window timing) |
| New foreign FIR polygon added | Expanded trajectory (e.g., Starship eastward KSC launch adding Bahamas AHA that wasn't in Boca Chica trajectory) |

**Implementation sketch.** Parse the NOTAM `E)` field coordinates list,
compute the polygon area via the shoelace formula, store as
`{flight_id, aha_polygon_area_nm2, aha_vertex_count, aha_firs_affected}`,
and compare against the rolling vehicle-family baseline.

## 5. Dynamic AHA — real-time shrinking during flight

Traditional AHAs are **static** — the full polygon is activated before
launch and released after the flight. The FAA is moving toward **dynamic
AHAs** that shrink in real time as the vehicle clears each hazard zone.
This is enabled by the **Space Data Integrator (SDI)**, which feeds live
vehicle state vectors into TFMS.

**Current state (2024–2026):**

- SDI is operational and used for every major US commercial launch.
- SpaceX shares live telemetry via SDI.
- FAA ATC can reroute aircraft dynamically when actual debris falls
  within a **sub-corridor** of the pre-activated AHA polygon — aircraft
  outside the real-time debris cone but inside the pre-declared AHA
  polygon can be released into their original flight path sooner than the
  NOTAM expiry time.
- A formally designated "dynamic LHA" (dLHA) protocol does **not** yet
  exist as a named regulatory framework (as of mid-2026). The FAA uses
  SDI-enabled real-time monitoring and controller judgment rather than
  automated dLHA activation.
- AHA size can **shrink over successive flights** as the operator
  accumulates reliability data — a vehicle-level learning effect across
  flights, not a within-flight dynamic. Falcon 9's AHA has decreased over
  its ~340-flight history vs its initial LHA sizing. Starship's AHA grew
  between IFT-4 and IFT-9 after the IFT-8 mishap increased conservative
  analysis inputs.

**Trend (2024–2026):** The FAA CSINAS ConOps (Commercial Space
Integration into the National Airspace System) calls for progressive
adoption of **Time-Based Launch Procedures** — shifting from blanket
airspace closures to per-flight dynamic corridors keyed to the actual
vehicle state. This will reduce the average divert burden from 40+
minutes per affected flight toward single-digit minutes for nominal
flights.

## 6. AHA and the NOTAM agent — extraction shape

For each launch NOTAM the agent parses, extract and store:

```json
{
  "notam_number": "A1559/25",
  "vehicle": "STARSHIP",
  "flight": "IFT-9",
  "launch_site": "BOCA CHICA TX",
  "aha_type": "ascent+stage2",
  "effective_utc": "2025-05-13T23:30Z",
  "expiry_utc": "2025-05-14T01:35Z",
  "backup_windows": ["2025-05-14T23:30Z/2025-05-15T01:35Z"],
  "aha_polygon_vertices": [
    "2400N07952W", "2318N07658W", "2211N07525W",
    "2320N07951W", "2340N08121W", "2346N08205W", "2400N08302W"
  ],
  "aha_firs_affected": ["MUFH", "MUHA", "MKJK"],
  "altitude_floor_ft": 0,
  "altitude_ceiling": "UNLIMITED",
  "airlines_affected_estimate": null,
  "aha_polygon_area_nm2": null
}
```

**Decision verbs this enables in the post-MVP Phase 1 loop:**

- **Predict** — slip probability increases if no NOTAM filed within 72h
  of NET date, or if AHA includes a new foreign FIR (regulatory
  coordination delay).
- **Recommend** — defer any downlink scheduling window that overlaps the
  AHA activation time (SDR ground station operators near the launch
  corridor may see RF interference from the vehicle).
- **Brief** — pre-launch survivability brief includes AHA size vs vehicle
  baseline; flag if the current LHA is significantly larger than prior
  flights of the same vehicle.

## 7. AHA for re-entry and EOL operations (Phase 5)

Re-entry AHAs are sized by the same dispersion-ellipse + buffer method,
applied to the predicted impact point of the re-entering body:

- **Controlled re-entry (deorbit burn).** Tight dispersion ellipse + 10
  NM buffer; NOTAM filed 48–72h in advance when the planned impact zone
  is defined.
- **Uncontrolled / decaying re-entry.** AHA is not filed until the impact
  window narrows to a predictable footprint (typically within 12–24
  hours). The NOTAM may cover very large ocean areas early and shrink as
  tracking improves.

For Phase 5 the agent should watch for re-entry NOTAMs filed under the
satellite's operator name or NORAD ID as indicators that the deorbit has
been initiated or that decay is imminent.

## 8. Implementation hook — polygon area in Python

The shoelace formula is the right tool for the AHA-area comparison
metric. Lat/lon must be projected to a local equal-area projection for
the area to be in NM² rather than degree²; on the spatial scale of an
AHA (≤ ~500 NM characteristic length) a simple equirectangular projection
at the polygon centroid is within ~1% of a proper UTM projection.

```python
# aha_area.py
import math

def parse_ddm(s: str) -> tuple[float, float]:
    """Parse 'DDMMNDDDMMW' (e.g., '2400N07952W') into (lat_deg, lon_deg).

    Eastern longitudes return positive values; western negative. Northern
    latitudes positive; southern negative.
    """
    # latitude: DDMM[N|S]
    lat_deg = int(s[0:2]) + int(s[2:4]) / 60.0
    if s[4] == "S":
        lat_deg = -lat_deg
    # longitude: DDDMM[E|W]
    lon_deg = int(s[5:8]) + int(s[8:10]) / 60.0
    if s[10] == "W":
        lon_deg = -lon_deg
    return lat_deg, lon_deg

NM_PER_DEG_LAT = 60.0   # by definition

def aha_polygon_area_nm2(ddm_vertices: list[str]) -> float:
    """Shoelace area of a lat/lon polygon, returned in NM^2.

    Uses an equirectangular projection at the polygon centroid. Accurate
    to ~1% for AHAs up to a few hundred NM across.
    """
    coords = [parse_ddm(v) for v in ddm_vertices]
    lat_c = sum(c[0] for c in coords) / len(coords)
    nm_per_deg_lon = NM_PER_DEG_LAT * math.cos(math.radians(lat_c))

    # Project to local NM frame
    xs = [(lon - coords[0][1]) * nm_per_deg_lon for _, lon in coords]
    ys = [(lat - coords[0][0]) * NM_PER_DEG_LAT  for lat, _ in coords]

    # Shoelace
    n = len(xs)
    area2 = 0.0
    for i in range(n):
        j = (i + 1) % n
        area2 += xs[i] * ys[j] - xs[j] * ys[i]
    return abs(area2) / 2.0
```

This is the only AHA-specific code worth pre-writing; everything else
(NOTAM container parsing, ARTCC ↔ launch-site mapping, FIR coordination
timing) is covered in [notam-space-operations.md](notam-space-operations.md).

## 9. Where it fails

- **Parsing fragility.** The `E)` field is free-text by FAA convention.
  Coordinate-list extraction must tolerate missing separators, line
  wraps, and `BY` waypoint names mixed with DDMM coordinates. Defer to
  AIXM 5.1 XML via SWIM/FNS when available (see notam-space-operations
  §5 on the ICAO format transition).
- **Foreign launch sites.** Rocket Lab Electron from Mahia (NZ),
  Arianespace from Kourou (FG), and CNSA launches from Wenchang (CN) do
  not appear in FAA NOTAM Search. Each has a national NOTAM database
  with different access patterns. Defer multi-national NOTAM ingest
  until US-only operation is solid.
- **Re-license modifications mid-campaign.** Starship IFT-9's AHA was a
  license-mod expansion vs IFT-8. Track FAA AST license filings (not
  just NOTAMs) to anticipate AHA size jumps.

## 10. What to actually build (post-MVP)

- [ ] `aha_area.py` per §8 with the `parse_ddm` and `aha_polygon_area_nm2`
      helpers. Unit-test against known AHAs (IFT-8 vs IFT-9).
- [ ] Vehicle-family rolling baseline storage:
      `data/aha-baselines/<vehicle>.jsonl` with one row per historical
      flight.
- [ ] Phase 1 decision-verb wiring in the arbiter for `predict_slip`,
      `recommend_downlink_defer`, and `brief_pre_launch`.
- [ ] One demo case: IFT-9 vs IFT-8 AHA area delta, with the brief
      output highlighting the Bahamas/Turks-and-Caicos addition.

## 11. References

- 14 CFR Part 450 (Streamlined Launch and Reentry License Requirements,
  effective 15 March 2021), § 450.133 Aircraft Hazard Areas.
- 14 CFR Part 417 Appendix B (Flight Hazard Area Analysis for Aircraft
  and Ship Protection) — legacy but still referenced.
- FAA Pilot/Controller Handbook for Aeronautical Information Services
  (PHAM) Chapter 31 — Space Operations NOTAMs.
- FAA AST. *Streamlined Launch and Reentry Licensing Requirements.*
  [faa.gov/space/streamlined_licensing_process](https://www.faa.gov/space/streamlined_licensing_process).
- FAA. *CSINAS ConOps* — Commercial Space Integration into the National
  Airspace System (concept of operations).

## See also

- [notam-space-operations.md](notam-space-operations.md) — NOTAM container that carries the AHA polygon
- [trust-stack.md](trust-stack.md) — Layer 1 (Data trust) is what makes the AHA-area baseline a defensible signal
- [INDEX.md](INDEX.md) "Deferred" section — the post-MVP roadmap slot this serves
