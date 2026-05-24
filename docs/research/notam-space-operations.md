---
title: NOTAM — Space Operations subcategories
type: research
category: operational
status: ingested
ingested: 2026-05-24
sources:
  - https://notams.aim.faa.gov/notamSearch/   # FAA NOTAM Search public UI
  - https://www.faa.gov/air_traffic/publications/atpubs/notam_html/  # NOTAM PHAM
  - https://www.ecfr.gov/current/title-14/chapter-III/subchapter-C/part-450  # 14 CFR Part 450 § 450.133
  - https://www.ecfr.gov/current/title-14/chapter-I/subchapter-F/part-91/section-91.143  # 14 CFR § 91.143
  - https://www.faa.gov/space/space_data_integrator  # SDI
  - https://github.com/faa-swim/fns-client            # SWIM/FNS reference client
---

# NOTAM — Space Operations Subcategories

> Status: operational reference. **Out of MVP scope** — listed in
> [INDEX.md](INDEX.md) under "Deferred." Companion to
> [launch-hazard-area.md](launch-hazard-area.md), which covers the AHA
> polygon geometry; this note covers the NOTAM **container** that carries
> the polygon and the related subcategories the post-MVP Phase 1 and
> Phase 5 loops need to ingest.

This page covers the **space-operations-specific NOTAM subcategories** that
are distinct from general aviation NOTAMs. For the base NOTAM structure
(format, retrieval, ICAO field semantics), defer to FAA PHAM Chapter 31
directly — there is no value in re-encoding it here.

The four subcategories below map onto the Mission Desk's post-MVP Phase 1
(pre-launch) and Phase 5 (re-entry / EOL) ingest paths.

## 1. Launch NOTAM (Aircraft Hazard Area)

The most common space-operations NOTAM type. Issued by the **ARTCC** (Air
Route Traffic Control Center) responsible for the airspace surrounding the
launch site. Activates an **Aircraft Hazard Area (AHA)** defining the
debris-risk envelope.

**Regulatory basis:** 14 CFR Part 450 § 450.133 (flight hazard area
analysis); 14 CFR § 91.143 (flight limitation in the proximity of space
flight operations).

**Safety criterion:** AHA sized so the expected number of casualties
among the aircraft population in the hazard area does not exceed
**1 × 10⁻⁶ per launch attempt**. Trajectory-derivation details in
[launch-hazard-area.md](launch-hazard-area.md).

**Required NOTAM content (per FAA PHAM Chapter 31):**

- Keywords "airspace" + "space launch" or "space reentry" in the `E)` field
- Launch site description and geographic reference
- Effective times (`B)` field) and expiry (`C)` field) in UTC
- Backup launch date/time windows embedded in `E)`
- AHA polygon vertices in lat/lon (DDM format: `2400N07952W`)
- Altitude extent — defaults to **surface to unlimited** unless otherwise
  specified
- Availability of in-flight status info for non-participating pilots
  (ATC frequency or phone number)
- Brief launch scenario narrative (vehicle name, flight designation,
  operator)

**Timing.** Must be effective **no less than 30 minutes prior to flight**
and must remain active until at least 30 minutes after the airspace can no
longer be affected by the vehicle or its debris. In practice operators file
**48–72 hours in advance** to allow flight planning.

**ARTCC codes for major US launch sites:**

| Launch site | Primary ARTCC | FIR identifier |
|---|---|---|
| Cape Canaveral / KSC | Jacksonville ARTCC | KZJX |
| Vandenberg SFB (Western Range) | Los Angeles ARTCC | KZLA |
| Starbase, Boca Chica TX | Houston ARTCC + Mexico City FIR | KZHU / MUFH |
| Mid-Atlantic Regional Spaceport (MARS) | Washington ARTCC | KZDC |

**Key distinction — AHA vs TFR.** AHAs are trajectory-derived,
surface-to-unlimited, and may span hundreds of NM of ocean. A simple TFR
(e.g. the standing Starbase TFR 5/3678 at 0–2,000 ft) is a
facility-security measure, **not** a launch-hazard area. The agent should
treat any NOTAM with the phrase "due to space launch" in the `E)` field
and a `QRDCA` or `QRDXX` Q-code as an AHA, regardless of whether the word
"TFR" appears.

**Three NOTAM types per launch event:**

1. **Airspace NOTAM** — activates the AHA (described above)
2. **Flow NOTAM** — route-guidance advisory for affected flights (issued
   by ARTCC traffic management unit)
3. **Security NOTAM** — coordinates UAS restrictions and perimeter-security
   measures (optional; more common for high-profile / crewed launches)

## 2. Re-entry and stage-separation NOTAMs

Re-entry vehicles (spent upper stages, reusable first stages, returning
crew capsules) generate NOTAMs for:

- **Stage impact zones.** Expendable first/second stages have planned
  ocean impact zones. Each zone is an AHA, sized by the debris dispersion
  ellipse + 10 NM buffer (see
  [launch-hazard-area.md §2.2](launch-hazard-area.md)). A single Falcon 9
  launch can generate **two** separate NOTAMs — one for the ascent
  corridor and one for the stage-2 re-entry / splashdown zone.
- **RTLS (Return to Launch Site) re-entry corridor.** When a reusable
  booster returns to the launch site (e.g. Falcon 9 booster at Cape
  Canaveral or Falcon Heavy side cores), a separate AHA NOTAM covers the
  re-entry trajectory and landing zone.
- **Starship orbital re-entry.** Generates a third AHA covering the
  re-entry corridor (currently over the Indian Ocean or Pacific for IFT
  missions; over the Bahamas / Turks & Caicos for Starship-at-KSC
  trajectories per the May 2025 license modification covering IFT-9).

**Verified example.** Starship IFT-5 (October 2024) generated NOTAM
`F3682/24` specifically for the Ship (Stage 2) atmospheric re-entry and
splashdown zone, in addition to the main AHA NOTAM for the ascent phase.

**EOL / deorbit NOTAMs.** Controlled satellite re-entry generates NOTAMs
for the predicted impact footprint, issued by the range authority
responsible for the disposal trajectory. For uncontrolled re-entries, the
FAA issues a NOTAM when the impact window narrows to **less than 12
hours** and the footprint is defined with sufficient confidence. For
Phase 5 (EOL / deorbit) an agent should poll NOTAM Search for the
satellite's catalog number or operator name during the predicted decay
window.

## 3. Debris Response Area (DRA) NOTAM

A **DRA** is a reactive NOTAM activated **only after** an anomaly occurs
during flight — it is NOT issued pre-launch.

**Activation sequence:**

1. Vehicle telemetry shows anomaly (explosion, breakup, loss of control)
2. FAA range safety officer / SDI system detects debris event
3. FAA issues emergency DRA NOTAM — aircraft in the area receive
   immediate ATC alerts and rerouting instructions
4. DRA remains active until all debris has reached the surface
5. FAA issues DRA closeout NOTAM / alert

**SDI role.** The **Space Data Integrator** feeds real-time vehicle state
vectors (position, altitude, velocity, deviation from planned trajectory)
into the FAA's Traffic Flow Management System (TFMS). SDI is now
operational and used for every major US commercial launch. SpaceX is the
primary operator currently sharing telemetry. SDI enables the FAA to
detect a vehicle breakup within seconds of telemetry loss and trigger the
DRA NOTAM faster than the traditional range-safety phone-call chain.

**Agent implication.** A DRA NOTAM appearing in the feed for a vehicle
the agent is tracking is a **high-confidence signal of a launch failure**.
Cross-check against the NOTAM `E)` field for the vehicle name, then
immediately:

- Update the launch phase status to `ANOMALY`
- Trigger a `score_launch_failure_probability` arbiter run (T2 escalation)
- Check FAA AST statements for mishap investigation opening

## 4. Spectrum / RF NOTAMs

These NOTAMs cover temporary frequency use, transmitter activation, or
radio silence requirements associated with space operations. Less commonly
searched by satellite operators but relevant for:

- **Telemetry and tracking activation windows.** Some range safety NOTAMs
  specify the transmitter frequency bands used for range tracking during
  a launch. Operationally relevant for ground stations that share
  frequency allocations with range tracking radars.
- **Radar / uplink interference zones.** High-power radar transmitters
  used for space surveillance (e.g. Space Fence) can generate RF NOTAMs
  when their scan patterns intersect with instrument approach corridors.
- **GPS jamming notices.** FAA issues GPS interference NOTAMs (typically
  under the `QNMAS` Q-code) for range safety testing and some launch
  activities that generate GPS signal degradation in surrounding
  airspace. These affect instrument approaches and en-route navigation,
  and are therefore listed in the NOTAM feed under affected ARTCCs.

**For interference attribution (post-MVP):** when investigating downlink
degradation, cross-check the GPS NOTAM feed for the time window. A GPS
jamming NOTAM overlapping the satellite's downlink window is a possible
environmental interference source. Query NOTAM Search with keyword "GPS"
or "GNSS" filtered to the relevant ARTCC.

**Q-codes relevant to spectrum/RF NOTAMs:**

| Q-code | Meaning |
|---|---|
| `QNMAS` | GPS/GNSS navigation aid — signal unreliable or unavailable |
| `QNMAU` | GPS/GNSS navigation aid — unserviceable |
| `QNTAU` | TACAN — unserviceable (less relevant but shares spectrum) |

## 5. NMS modernization and ICAO format transition (2026–2028)

**NMS deployment (April 18, 2026).** The FAA replaced its 1980s-era U.S.
NOTAM System (USNS) with the cloud-based **NOTAM Management Service
(NMS)**, deployed April 18, 2026 between midnight–04:00 Eastern. The
system processes 4+ million NOTAMs per year. This was a **back-end
replacement**; NOTAM content, format, and the public search interface at
`notams.aim.faa.gov/notamSearch/` are unchanged.

**ICAO format transition (planned late 2027 – early 2028).** The FAA
missed its December 2024 target for full ICAO format adoption. As of
April 2026, NOTAMs remain available in domestic, ICAO, or plain-language
formats simultaneously. Full retirement of the domestic format is planned
for late 2027 or early 2028.

**What changes for space ops.** The ICAO format separates altitude limits
into explicit `F)` (lower) and `G)` (upper) fields, making the "surface
to unlimited" specification **machine-parseable** without text extraction
from the `E)` field. Agent code written today against the `E)` field
regex will continue to work through at least 2027; add `F)` and `G)`
field parsing as a non-breaking upgrade when the ICAO transition
completes.

**SWIM / FNS programmatic access.** Unchanged by NMS deployment. Continue
to use `scds.faa.gov` account → AIM FNS subscription → FIL SFTP initial
load + JMS real-time updates. Reference implementation:
[`github.com/faa-swim/fns-client`](https://github.com/faa-swim/fns-client).
Payload format remains AIXM 5.1 XML.

## 6. Foreign FIR NOTAM coordination

For launches with trajectory segments over foreign FIRs, the FAA must
coordinate AHA NOTAMs with the relevant Air Navigation Service Providers
(ANSPs). Typical coordination timeline: **7–10 days** for ANSPs familiar
with US space operations. This is a documented bottleneck in the FAA
Space CDM (Collaborative Decision Making) process.

| Trajectory | Foreign FIRs affected |
|---|---|
| Starship Boca Chica eastward | MUFH (Mexico City), MUHA (Havana), MKJK (Kingston), TJZS (San Juan) |
| Falcon 9 from KSC to LEO ISS | KZJX, KZMA, then Caribbean FIRs |
| Vandenberg Polar/SSO | Pacific FIRs (KZOA, then Fukuoka / Auckland depending on trajectory) |

An agent monitoring a launch from a non-US site (e.g. Rocket Lab Electron
from Mahia, NZ) should query the relevant national NOTAM database. Rocket
Lab NZ operations appear under **NZZO** (Oceanic FIR) and nearby ARTCCs.
NOTAM `B0423/26` (Electron launch, 2026) is a documented example.

## 7. Mission Desk integration decision table (post-MVP)

| Phase | NOTAM subcategory | Agent action |
|---|---|---|
| Phase 1 (pre-launch) | Launch AHA NOTAM (NOTAMN) | Extract window B/C, vehicle, backup dates; compute slip probability |
| Phase 1 (pre-launch) | NOTAMR / NOTAMC | Detect slip; recompute conjunction screening epoch; emit CDM re-screen event |
| Phase 2 (launch + ascent) | DRA NOTAM | Flag anomaly; update launch phase to ANOMALY; open mishap investigation watch |
| Phase 4 (on-orbit ops) | GPS / GNSS NOTAM | Check overlap with downlink schedule; attribute interference |
| Phase 5 (EOL / deorbit) | Re-entry impact zone NOTAM | Parse footprint polygon; compute casualty risk overlap; update deorbit tracking |

Every row in this table is a decision verb the [arbiter](small-model-ensemble-arbiter.md)
can be wired to handle once the NOTAM ingestor is built.

## 8. Retrieval recipes

**Public web search.** [notams.aim.faa.gov/notamSearch](https://notams.aim.faa.gov/notamSearch/).
Filterable by ARTCC, keyword, effective date range, Q-code. No
programmatic API.

**SWIM / FNS subscription.** AIXM 5.1 XML payload over JMS for real-time
updates; SFTP for initial bulk load (FIL). Account creation via
`scds.faa.gov`. Reference client:
[github.com/faa-swim/fns-client](https://github.com/faa-swim/fns-client).
This is the right path for the post-MVP NOTAM ingestor; web scraping the
NOTAM Search UI is brittle and rate-limited.

**Foreign NOTAMs.** Each ANSP publishes its own. The European
Aeronautical Information Documents (eAIDs) are accessible via
EUROCONTROL's EAD (European AIS Database) but require an account.
Defer multi-national NOTAM ingest until US-only operation is solid.

## 9. Where it fails

- **Free-text `E)` fields.** Coordinate-list extraction must tolerate
  missing separators, line wraps, and `BY` waypoint names mixed with
  DDMM coordinates. Move to AIXM 5.1 XML via SWIM/FNS when available.
- **NOTAM revisions during the window.** A single launch may go through
  10+ NOTAMRs as the schedule slips. The ingestor must dedupe on
  `notam_number` and treat each NOTAMR as the new authoritative version,
  preserving the prior version in the audit log per the
  [agentic-provenance](agentic-provenance.md) write-once rule.
- **Spurious "space launch" matches.** Q-code `QRDCA` is overloaded.
  Filter on the combination of (Q-code OR keyword "space launch") AND
  ARTCC matching a known launch-site list to avoid false positives from
  non-space airspace closures.
- **NMS deployment day (April 18, 2026).** Confirmed back-end replacement
  only; verify content / format unchanged before relying on parsers
  developed against the old USNS.

## 10. What to actually build (post-MVP)

- [ ] SWIM/FNS subscription onboarding (`scds.faa.gov` account, AIM FNS
      subscription, FIL SFTP initial load + JMS real-time updates).
- [ ] AIXM 5.1 XML parser for the four subcategories in §1–§4.
- [ ] Cross-launch dedupe and revision tracking with the original NOTAMR
      / NOTAMC preserved per [agentic-provenance §6](agentic-provenance.md).
- [ ] Decision-verb wiring per §7 table.
- [ ] One demo case showing IFT-9 NOTAM ingest with the AHA polygon area
      computed via [launch-hazard-area.md §8](launch-hazard-area.md) and
      compared against the IFT-8 baseline.

## 11. References

- 14 CFR Part 450 § 450.133 — Aircraft Hazard Areas.
- 14 CFR § 91.143 — Flight limitation in the proximity of space flight
  operations.
- FAA PHAM (Pilot/Controller Aeronautical Information Services Handbook)
  Chapter 31 — Space Operations NOTAMs.
  [faa.gov/air_traffic/publications/atpubs/notam_html](https://www.faa.gov/air_traffic/publications/atpubs/notam_html/).
- FAA. *Space Data Integrator.*
  [faa.gov/space/space_data_integrator](https://www.faa.gov/space/space_data_integrator).
- FAA. *NOTAM Search.*
  [notams.aim.faa.gov/notamSearch](https://notams.aim.faa.gov/notamSearch/).
- FAA SWIM. *FNS reference client.*
  [github.com/faa-swim/fns-client](https://github.com/faa-swim/fns-client).

## See also

- [launch-hazard-area.md](launch-hazard-area.md) — geometric derivation of the AHA polygon
- [agentic-provenance.md](agentic-provenance.md) — write-once + NOTAM-revision tracking rule
- [small-model-ensemble-arbiter.md](small-model-ensemble-arbiter.md) — arbiter that consumes the parsed NOTAM events
- [INDEX.md](INDEX.md) "Deferred" section — the post-MVP roadmap slot this serves
