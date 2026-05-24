---
title: FAA NOTAM operational API
type: research
tier: T3
status: ingested
ingested: 2026-05-24
sources: [https://notams.aim.faa.gov/, https://www.faa.gov/space, https://www.federalregister.gov/, github.com/faa-swim/fns-client]
---

# FAA NOTAM Operational API — Day 1 Ingestor Handbook

**Scope.** This document is the verbatim operational reference for the Spacesharks Mission Desk **Tier-3 launch-window ingestor**. It tells an engineer what URL to hit, what NOTAM ID format to expect, which fields to parse out of the Q-line and E-line, when to re-poll, and what to record for provenance. Conceptual depth on the *meaning* of a NOTAM, the AHA-vs-TFR distinction, slip mechanics, the Part 450 regulatory chain, and the slip-probability scoring math lives in the yxz wiki — links at the bottom. **Do not re-derive theory here.** If you need to know why a NOTAMC means "scrub" and a NOTAMR means "slip", read the wiki. If you need to know which URL to GET, read this.

**Pre-MVP positioning.** Per `D:\DOT\spacesharks\docs\SCOPE.md`, pre-launch is **deferred** for the hackathon MVP. This handbook is the Phase-1 (post-hackathon) reference. **Tier-3 classification rationale:** NOTAMs are launch-event-driven, not real-time-poll. Daily cadence outside the launch-imminent window, escalating to hourly inside T-72 h, is sufficient. Re-tier upward only when SWIM FNS credentialed access is in place (§3 Tier B).

---

## 1. Endpoint Catalog

The FAA does not expose a single free machine-readable NOTAM API. The catalog below is heterogeneous: public web pages, credentialed firehoses, quarterly PDFs, and parallel maritime feeds.

| Source | URL | Tier | Access | Format | Freshness | MVP vs Upgrade |
|---|---|---|---|---|---|---|
| FAA NOTAM Search | `notams.aim.faa.gov/notamSearch/` | A | None | HTML / iframe | Live | **Primary MVP** — scrape-only; brittle |
| FAA DINS legacy | `notams.faa.gov/dinsQueryWeb/` | A | None | Plain text | Live | MVP fallback — regex-friendly |
| FAA SWIM FNS via SCDS | `scds.faa.gov` | B | SCDS account + AIM FNS sub | JMS/AMQP + SFTP FIL | Sub-minute push | **Upgrade target** — credentialed firehose |
| FNS reference client | `github.com/faa-swim/fns-client` | B | Same as SCDS | Java + REST wrapper | — | Implementation pattern |
| FAA API Gateway | `api.faa.gov/s/` | B | Prototype | REST/JSON | Evolving | Not production-stable as of 2025 |
| FAA TFR graphic | `tfr.faa.gov/tfr3/` | A | None | XML (`detail_<N>.xml`) | Live | Supplementary — graphic TFR detail only |
| AST stakeholder pages | `faa.gov/space/stakeholder_engagement/{operator}` | A | None | HTML + PDFs | Per event | License modifications, EA/EIS, mishap status |
| Commercial Space Data | `faa.gov/data_research/commercial_space_data/licenses/` | A | None | HTML; quarterly | Quarterly | License roster — no JSON API ⚠️ |
| Federal Register | `federalregister.gov` | A | None | HTML + JSON API | Per rule | Slow signal — Part 450 ARC outputs |
| USCG NAVCEN BNM | `navcen.uscg.gov/broadcast-notice-to-mariners-message` | A | None | HTML | ~24 h | Maritime parallel for ocean-trajectory launches |
| Commercial aggregators (RocketReach, ForeFlight, AVDP) | varies | C | Paid | Vendor-specific | Vendor-specific | Pricing not public ⚠️ |

**Operational consequence.** No "just hit this REST URL" path exists for the MVP. Abstract a `LaunchWindowDataSource` interface so a `NotamSearchScrapeSource` (today) can be swapped for an `FnsJmsSource` (post-credential) without touching downstream slip-probability code. Same pattern as the `ConjunctionDataSource` seam in `D:\DOT\spacesharks\docs\research\space-track-cdm-api.md` §8.

---

## 2. Authentication & Access — Three Tiers

The MVP lives entirely in Tier A.

### 2.1 Tier A — Public scrape (MVP path)

`notams.aim.faa.gov/notamSearch/` has **no documented machine-readable API** — it is an iframe-rendered web form. The scraper must POST/GET search parameters (keyword like `"space launch"`, `"SpaceX"`, `"Starship"`; ICAO `KZJX`/`KZMA`/`MUFH`/`KZHU`/`KZLA`; date range), receive an HTML page, and regex-parse the embedded NOTAM body for Q/A/B/C/D/E lines.

⚠️ **Verify against live API.** The yxz wiki ingest reports direct `requests` GETs against `faa.gov`-family hosts returned **HTTP 403** — likely server-side bot-rule block, not an absent endpoint. Mitigation: set a realistic User-Agent header. **Honest fallback:** `notams.faa.gov/dinsQueryWeb/queryRetrievalMapAction.do?method=displayByICAOs&reportType=RAW&formatType=DOMESTIC&retrieveLocId=KZMA+KZJX+KZHU+MUFH` — DINS returns raw NOTAM text (regex-friendly) and historically tolerates programmatic clients better than the AIM iframe.

No rate limit is documented for either NOTAM Search or DINS. Treat as "informal" — keep below ~50 GET/launch-event/day (§4).

### 2.2 Tier B — FAA SWIM FNS (credentialed firehose)

Access path:

1. Apply for an SCDS account at `scds.faa.gov`. SLA not publicly documented ⚠️.
2. Request subscription to the **AIM FNS** service (SCDS hosts many SWIM products; AIM FNS is the NOTAM one).
3. Receive credentials for the SFTP FIL (Federal NOTAM System Initial Load — full snapshot of active NOTAMs) and the JMS/AMQP endpoint for push updates.
4. Run the FAA's Apache-licensed Java reference client at `https://github.com/faa-swim/fns-client`. The `FnsRestApi` sub-module wraps the JMS stream as a local REST API.
5. Persist pushed NOTAMs locally; expose by ICAO / keyword / NOTAM ID to `launch_planner.py`.

Latency: sub-minute from issuance. The only path that gives "NOTAM filed *N* seconds ago" semantics.

### 2.3 Tier C — Third-party commercial

The yxz wiki names commercial NOTAM distributors (RocketReach-style aggregators, ForeFlight, AVDP) but pricing is **not public** ⚠️. Defer until Tier B is exhausted.

---

## 3. Data Shape — Canonical NOTAM Q-Line / E-Line Structure

A US domestic NOTAM ID is `<series-letter><4-digit-sequence>/<2-digit-year>`. Verified examples from yxz wiki:

| NOTAM ID | Subject |
|---|---|
| `A1559/25` | Starship IFT-9 launch hazard area, May 2025, MUFH |
| `B0824/24` | Starship IFT-5 launch, October 2024 |
| `F3682/24` | Starship IFT-5 Stage 2 re-entry / splashdown area |
| `B0423/26` | Rocket Lab Electron, NZ temporary danger area, 2026 |

### 3.1 ICAO field structure (verbatim, ICAO Annex 15)

```
<number> NOTAM<N|R|C>
Q) <FIR>/<Q-code>/<traffic>/<purpose>/<scope>/<lower-FL>/<upper-FL>/<coordinates><radius>
A) <location ICAO>
B) <effective time YYMMDDHHmm>
C) <expiry time YYMMDDHHmm> [PERM | EST]
D) <schedule — blank or day/time schedule for multi-day windows>
E) <plain-language description>
```

Q-codes for launch: `QRDCA` (Danger Area active — primary), `QRDXX` (Danger Area plain-language — no standard code fits), `QRTCA` (Temporary Reserved/Restricted Area), `QWULW` (Unmanned aircraft activity — some suborbital tests).

NOTAM type codes:

| Code | Meaning | Slip signal |
|---|---|---|
| `NOTAMN` | New — first publication for a window | Standard pre-launch |
| `NOTAMR NNNN/YY` | Replaces NOTAM NNNN/YY; same subject, new times | **Slip** — pre-count rescheduling |
| `NOTAMC NNNN/YY` | Cancels NOTAM NNNN/YY | **Scrub** or cancellation |

### 3.2 Verified example — `A1559/25` (Starship IFT-9, May 2025)

Reproduced verbatim from yxz wiki source `D:\DOT\yxz\wiki\sources\notam-starship-ift8-2025.md` §4:

```
A1559/25 NOTAMN
Q) MUFH/QRDXX/IV/BO/W/000/999/2400N07952W...
A) MUFH
B) 2505132330  (2025 May 13 23:30 UTC)
C) 2505140135  (2025 May 14 01:35 UTC)
D) [backup windows May 14-17 at same hours]
E) DANGER ZONE - DUE TO SPACE LAUNCH FROM BOCA CHICA, TX.
   HAZARD AREA: 2400N07952W, 2318N07658W, 2211N07525W,
   2320N07951W, 2340N08121W, 2346N08205W, 2400N08302W.
   BACKUP LAUNCH DATES: 2505142330-2505150135,
   2505152330-2505160135, 2505162330-2505170135.
```

Polygon vertex regex: `\d{4}[NS]\d{5}[EW]`. Format is `DDMMNS DDDMMEW` (degrees + minutes + hemisphere), not decimal degrees — convert before geometry operations.

### 3.3 Spacesharks normalized event schema (SYNTHETIC example)

The ingestor MUST normalize every parsed NOTAM into this canonical shape before handing to downstream slip-probability logic. Field names are stable across Tier A scrape and Tier B FNS push; only the `source` field changes.

```json
{
  "schema": "spacesharks.event.launch_window.v1",
  "source": "faa.notam-search",
  "notam_id": "A1559/25",
  "notam_type": "N",
  "fir": "MUFH",
  "q_code": "QRDXX",
  "issued": "2025-05-13T18:04:00Z",
  "effective_from": "2025-05-13T23:30:00Z",
  "effective_to": "2025-05-14T01:35:00Z",
  "backup_windows": [
    {"start": "2025-05-14T23:30:00Z", "end": "2025-05-15T01:35:00Z"},
    {"start": "2025-05-15T23:30:00Z", "end": "2025-05-16T01:35:00Z"},
    {"start": "2025-05-16T23:30:00Z", "end": "2025-05-17T01:35:00Z"}
  ],
  "hazard_polygon": [
    {"lat": 24.000, "lon": -79.867}, {"lat": 23.300, "lon": -76.967},
    {"lat": 22.183, "lon": -75.417}, {"lat": 23.333, "lon": -79.850},
    {"lat": 23.667, "lon": -81.350}, {"lat": 23.767, "lon": -82.083},
    {"lat": 24.000, "lon": -83.033}
  ],
  "altitude_lower_ft": 0,
  "vertical_limit_unlimited": true,
  "launch_vehicle_hint": "STARSHIP",
  "flight_designation_hint": "IFT-9",
  "launch_site_hint": "BOCA CHICA TX",
  "status": "active",
  "replaces_notam_id": null,
  "cancelled_by_notam_id": null
}
```

FSM label semantics for `status`: `active` (effective window not yet replaced/cancelled), `cancelled` (NOTAMC issued), `replaced` (NOTAMR issued, `cancelled_by_notam_id` populated), `extended` (same-day backup activated; tagged separately for dataset rows), `consumed` (T-0 observed in window; close lifecycle, attach `actual_t`).

All `_hint` fields are best-effort E-line extraction — not part of the ICAO schema, never used as authoritative join keys.

**Synthetic record.** The JSON above mixes verbatim NOTAM A1559/25 content (effective times, coordinate strings, polygon) with synthetic decimal-degree conversions and a synthesized `issued` timestamp. Documentation example only — do not consume as live data.

---

## 4. Refresh Cadence

NOTAMs are filed 48–72 h before launch and replaced/cancelled on slip — not a real-time stream like Kp or X-ray flux.

| Mode | Cadence | Per-launch request budget |
|---|---|---|
| AST Launch Manifest crawl (quarterly PDF) | Once per quarter | 1 GET |
| Operator stakeholder page crawl (license / mishap status) | Daily | ≤ 10 GET/day across the watchlist |
| NOTAM Search baseline (no launch in next 14 d) | Daily | 1 GET per watched ICAO |
| T-14 d to T-72 h (NOTAM expected soon) | Every 12 h | 2 GET/day per mission |
| Launch-imminent (T-72 h to T-0) | Every 1 h | 24 GET/day per mission |
| USCG NAVCEN cross-check | Daily (≤ T-72 h baseline) → every 6 h (T-72 h to T-0) | ≤ 5 GET/day per mission |
| **Per-mission total budget** | — | **≤ 50 GET/day during launch-imminent** |

Rationale: a 1-hour cadence inside T-72 h captures every NOTAMR/NOTAMC well within the operator decision loop. Polling faster wastes scrape budget and risks tripping informal bot rules. If sub-hour latency is ever needed, that is the trigger to flip to Tier B — not to crank up the scrape rate.

---

## 5. Python Ingest Snippet (Runnable-ish)

**Variant A** is the MVP path — runnable against DINS today, zero credentials. **Variant B** is pseudo-code for the SWIM FNS upgrade (requires SCDS credentials).

### 5.1 Variant A — MVP, free public path

```python
"""spacesharks Day-1 NOTAM ingestor — minimal viable retrieval (Tier A)."""
import json, re
from datetime import datetime, timezone
import requests

# DINS multi-ICAO query is more programmer-friendly than the AIM iframe —
# it returns plain-text NOTAMs that regex cleanly. See yxz wiki
# D:\DOT\yxz\wiki\sources\faa-notam-search-2024.md §1 for the ICAO table.
DINS_URL = ("https://notams.faa.gov/dinsQueryWeb/queryRetrievalMapAction.do"
            "?method=displayByICAOs&reportType=RAW&formatType=DOMESTIC"
            "&retrieveLocId={locs}")
LAUNCH_ICAOS = "KZJX+KZMA+KZHU+MUFH+KZLA"

LAUNCH_KW = re.compile(
    r"\b(SPACE LAUNCH|ROCKET|STARSHIP|FALCON|ELECTRON|VULCAN|NEW GLENN|"
    r"BOCA CHICA|VANDENBERG|CAPE CANAVERAL|KSC)\b", re.I)
HDR = re.compile(r"(?P<id>[A-Z]\d{4}/\d{2})\s+NOTAM(?P<type>[NRC])"
                 r"(?:\s+(?P<replaces>[A-Z]\d{4}/\d{2}))?")
Q = re.compile(r"Q\)\s*(?P<fir>\w+)/(?P<qcode>Q\w+)/")
B = re.compile(r"\bB\)\s*(\d{10})")
C = re.compile(r"\bC\)\s*(\d{10})")
COORD = re.compile(r"\d{4}[NS]\d{5}[EW]")
BACKUP = re.compile(r"(\d{10})-(\d{10})")
VEH = re.compile(r"\b(STARSHIP|FALCON\s*9|FALCON\s*HEAVY|ELECTRON|VULCAN|NEW GLENN)\b", re.I)


def _ts(s: str) -> str:
    """YYMMDDHHmm -> ISO-8601 UTC (2-digit year assumed 2000+)."""
    return datetime(2000 + int(s[0:2]), int(s[2:4]), int(s[4:6]),
                    int(s[6:8]), int(s[8:10]), tzinfo=timezone.utc).isoformat()


def parse_notam(block: str) -> dict | None:
    h, b, c = HDR.search(block), B.search(block), C.search(block)
    if not (h and b and c):
        return None
    q, v = Q.search(block), VEH.search(block)
    backups = [{"start": _ts(a), "end": _ts(z)}
               for a, z in BACKUP.findall(block) if (a, z) != (b.group(1), c.group(1))]
    return {
        "schema": "spacesharks.event.launch_window.v1",
        "source": "faa.dins",
        "notam_id": h.group("id"),
        "notam_type": h.group("type"),
        "replaces_notam_id": h.group("replaces"),
        "fir": q.group("fir") if q else None,
        "q_code": q.group("qcode") if q else None,
        "effective_from": _ts(b.group(1)),
        "effective_to": _ts(c.group(1)),
        "backup_windows": backups,
        "hazard_polygon_raw": COORD.findall(block),
        "launch_vehicle_hint": v.group(1).upper() if v else None,
        "status": {"N": "active", "R": "active", "C": "cancelled"}[h.group("type")],
    }


def fetch_and_filter(icaos: str = LAUNCH_ICAOS) -> list[dict]:
    # ⚠️ faa.gov-family hosts have returned HTTP 403 to bare requests in
    # the yxz wiki ingest. Set a realistic UA and use a session in prod.
    headers = {"User-Agent": "spacesharks/0.1 (research)"}
    r = requests.get(DINS_URL.format(locs=icaos), headers=headers, timeout=30)
    r.raise_for_status()
    blocks = re.split(r"\n\s*\n", r.text)
    return [ev for block in blocks if LAUNCH_KW.search(block)
            and (ev := parse_notam(block)) is not None]


if __name__ == "__main__":
    for ev in fetch_and_filter():
        print(json.dumps(ev, default=str))
```

Caveats: DINS occasionally returns HTML wrappers under load — the regex chain degrades to "no parse → skipped". Emit `spacesharks.event.ingestor.degraded` when zero results persist 24 h across the full watchlist (mirror the CDM handbook §9 degradation principle). The polygon is left as raw `DDMMNS DDDMMEW` strings — decimal-degree conversion is downstream geometry. Production should add `requests.Session` + `urllib3.util.Retry` and respect the 50 GET/day per-mission budget (§4).

### 5.2 Variant B — Upgrade, FNS firehose (pseudo-code)

```python
"""SWIM FNS firehose (Tier B). Requires SCDS account + AIM FNS subscription.
Reference: github.com/faa-swim/fns-client (Java; FnsRestApi wraps JMS as REST)."""

# from proton.handlers import MessagingHandler
# from proton.reactor import Container
#
# class FnsConsumer(MessagingHandler):
#     def __init__(self, url, topic, creds):  # url: amqps://scds.faa.gov:5671
#         super().__init__()                   # topic: FAA-assigned AIM FNS topic
#         self.url, self.topic, self.creds = url, topic, creds
#     def on_start(self, event):
#         conn = event.container.connect(self.url, ...self.creds...)
#         event.container.create_receiver(conn, self.topic)
#     def on_message(self, event):
#         # FAA FNS messages are XML-encoded per AIXM/FNS schema.
#         emit_to_spacesharks_bus(normalize_fns_notam(event.message.body))
#
# Container(FnsConsumer(URL, TOPIC, CREDS)).run()
```

Tier-B output must use the same `spacesharks.event.launch_window.v1` schema as Tier-A — only the `source` field changes (set to `"faa.swim-fns"`).

---

## 6. Slip Mechanics — Decision Lookup

Each parsed NOTAM reduces to one operational signal consumed by the slip-probability score. Full theory in `D:\DOT\yxz\wiki\concepts\launch-window-slip.md`.

| NOTAM state | Filed when | Operational signal | Decision verb |
|---|---|---|---|
| **Filed 48–72 h pre-launch** | First NOTAMN | Standard pre-launch | Normal monitoring; emit baseline `slip_probability_score` |
| **Extended (same/next-day NOTAMR)** | NOTAMR, `B)` shifted < 48 h | Slip ≤ 24 h | Update slip-prob; do NOT trigger CDM rescreen |
| **Replaced (multi-day NOTAMR)** | NOTAMR, `B)` shifted ≥ 48 h | Slip ≥ 48 h | **Recompute conjunction screening** — new T-0 invalidates LCOLA |
| **Cancelled (NOTAMC, no replacement)** | NOTAMC; no NOTAMR within 6 h | Scrub | **Halt T-0-anchored work**; flag indefinite delay; re-poll for new NOTAMN |
| **Cancelled + replaced (NOTAMC + NOTAMN ≤ 6 h)** | NOTAMC then fresh NOTAMN | Same-day scrub with new window | Routine — IFT-style scrub |
| **Consumed** | `C)` passes with telemetry-confirmed T-0 | Success | Record `actual_t`; close lifecycle |
| **No replacement after expiry** | `C)` passes silently, no NOTAMR/NOTAMN | Stealth scrub | Treat as cancelled after 6 h grace; warn |
| **Filed pre-regulatory clearance** | NOTAM exists but mishap/license-mod pending | "Filed ≠ imminent" | Apply `P(launch_in_window) ≈ 0.05` (IFT-9 rule); see §9 |

The ingestor only produces inputs; the slip-probability score itself is a Mission Desk arbiter responsibility.

---

## 7. TraCSS / LCOLA Interaction

A filed launch NOTAM is the upstream trigger for **LCOLA** (Launch Collision Avoidance) screening on the Space-Track / TraCSS side. SpaceX joined TraCSS as its **10th beta user** under a CRADA signed with NOAA in **January 2024**, specifically for ascent-trajectory LCOLA. As of February 2026, 17 organizations are TraCSS pilot users.

Chain: NOTAM filed → LCOLA screens planned ascent against catalogued population → LCOLA failure forces slip (regulatory-force driver; identical to other slips from the ingestor's view) → post-launch the newly inserted object enters the catalogue and the Spacesharks CDM ingestor (`space-track-cdm-api.md`) picks it up.

Spacesharks does **not** ingest the LCOLA result directly today. Phase-1 design: `launch_planner.py` emits `conjunction_rescreen_required` on NOTAM state change (replaced / cancelled) so previously-cached T-0-anchored screenings are invalidated. Cross-link: `D:\DOT\spacesharks\docs\research\space-track-cdm-api.md` §8 (TraCSS transition timing risk).

---

## 8. Failure Modes and Degradation

| Failure | Symptom | Strategy |
|---|---|---|
| **403 from `faa.gov`-family GET** | HTTP 403 on direct `requests.get` | Realistic User-Agent; session + cookie jar; fall back to DINS (`notams.faa.gov/dinsQueryWeb/`) ⚠️ |
| **Stale NOTAM Search HTML** | CDN-cached HTML showing yesterday's NOTAMs as active | Compare parsed `B)`/`C)` against wall-clock; treat `C)` > 24 h in the past as expired regardless of upstream markup |
| **Parser drift on FAA template change** | Regex fails on `B)`/`C)` after site update | Emit `ingestor.degraded` with `reason=parser_drift`; halt scrape. Do NOT silently fall back to "no NOTAMs" |
| **Missing IFT-N NOTAM ID** | Operator filed under unexpected FIR (e.g., `KFDC` for a re-entry corridor) | Rotate watchlist ICAOs; weekly fall back to keyword-only query without ICAO filter |
| **NOTAM filed pre-regulatory clearance** | NOTAM active but mishap investigation open or license mod pending (IFT-9: A1559/25 filed ~May 13, actual launch May 27) | Cross-check operator stakeholder page; apply `P(launch_in_window) ≈ 0.05` (yxz wiki `notam-starship-ift8-2025.md` §5); flag `regulatory_hold_active=true` |
| **USCG-only ocean hazard NOTMAR** | NOTMAR exists with no parallel NOTAM (rare) | Cross-check `navcen.uscg.gov`; emit `notmar_present` independently |
| **ARTCC-issued NOTAM by proxy** | NOTAM filed under ARTCC location (e.g., `KZMA`) not launch-site FIR | Covered by multi-ICAO scrape; series-letter encodes ARTCC of origin (yxz wiki `concepts/notam.md` §2) |
| **Empty result 24 h across watchlist** | Zero parsed NOTAMs | Likely auth/parser regression — emit `ingestor.degraded`; do NOT report "no launches" downstream |
| **TFR-only filing (no NOTAM)** | Standing TFR (e.g., Starbase 5/3678) without per-launch NOTAM | Standing TFRs cover facility security only — orbital launches need NOTAMs; flag if observed |
| **Backup-window misparse** | E-line `BACKUP LAUNCH DATES:` parsed with wrong day boundary | Sort by `start`; assert `start < end`; reject windows whose duration differs from primary by > 6 h |

**Degradation principle** (same as CDM handbook §9): the Mission Desk must never go silent on FAA unreliability. Emit `spacesharks.event.ingestor.degraded` so the operator brief shows "launch-window data stale since {ts}" rather than an empty "no launches" panel that could be confused with a quiet manifest.

---

## 9. Provenance Fields the Ingestor MUST Record

Every event derived from a NOTAM must persist these fields. Same shape as `D:\DOT\spacesharks\docs\research\space-track-cdm-api.md` §10.

| Field | Source on NOTAM | Why |
|---|---|---|
| `notam_id` | Header (`A1559/25` etc.) | Primary key for the launch-window event upstream |
| `notam_type` | Header (`NOTAMN`/`NOTAMR`/`NOTAMC`) | Encodes the lifecycle state — non-recoverable from `status` alone |
| `replaces_notam_id` | Header (when `NOTAMR`/`NOTAMC`) | Chain previous NOTAM for slip-history tracing |
| `notam_fetched_at` | Local clock at ingest | Measures FAA-side issue → Spacesharks-side observe lag |
| `notam_effective_from` / `notam_effective_to` | `B)` / `C)` fields | Anchor for slip-probability and downstream T-0 calculations |
| `source` | Constant `"faa.notam-search"`, `"faa.dins"`, `"faa.swim-fns"` | Disambiguates Tier A scrape vs DINS fallback vs Tier B firehose |
| `raw_body_sha256` | SHA-256 of the unparsed NOTAM block | Tamper-evidence; lets us prove what we ingested even after FAA-side re-render |
| `regulatory_hold_active` | Derived from cross-check of operator stakeholder page | Required to apply the IFT-9 "filed ≠ imminent" probability adjustment |

The first six are non-negotiable for Phase 1. The regulatory-hold flag in particular changed the IFT-9 launch-window inference by an order of magnitude (yxz wiki `notam-starship-ift8-2025.md` §5).

---

## 10. Upgrade Path (brief)

- **Part 450 transition — March 10, 2026.** All operators must hold a Part 450 license by this date; legacy Parts 415/417/431/435 are removed (`D:\DOT\yxz\wiki\sources\faa-part-450-2020.md`). Expect a burst of license modifications and EA documents on operator stakeholder pages around this transition.
- **SWIM FNS credentialed access** — apply at `scds.faa.gov`, subscribe to AIM FNS, implement the AMQP consumer per Variant B. Sub-minute push; eliminates the 403-prone scrape. SLA not publicly documented ⚠️.
- **Commercial aggregators** — RocketReach-style services, ForeFlight, AVDP. Pricing not public ⚠️ — defer until SWIM FNS is confirmed insufficient.
- **TraCSS LCOLA integration** — when TraCSS.gov goes live (target 2026), the LCOLA result becomes directly queryable, replacing "infer LCOLA from slip pattern" with direct ingest.

Full upgrade-path table in `D:\DOT\yxz\wiki\synthesis\faa-notam-launch-lifecycle.md` §10.

---

## 11. yxz Wiki Cross-References (read for conceptual depth)

- `D:\DOT\yxz\wiki\synthesis\faa-notam-launch-lifecycle.md` — read for the full L-180 → T+30 timeline, regulatory-chain diagram, and the MVP cookbook this handbook crystallizes.
- `D:\DOT\yxz\wiki\sources\faa-notam-search-2024.md` — read when extending the regex parser; canonical ICAO/FIR table and original parsing pattern Variant A is built from.
- `D:\DOT\yxz\wiki\sources\faa-ast-launch-licensing-2025.md` — read when interpreting an operator stakeholder page; Part 450 license workflow, 180-day statutory clock, AST license-modification chain.
- `D:\DOT\yxz\wiki\sources\faa-part-450-2020.md` — read for the regulatory basis (EC ≤ 10⁻⁴ casualty limit, § 450.161 hazard-area / NOTAM obligation).
- `D:\DOT\yxz\wiki\sources\notam-starship-ift8-2025.md` — read when calibrating the IFT-9 "filed ≠ imminent" probability rule; verified end-to-end lifecycle example (Feb 28 → March 6, six-day slip).
- `D:\DOT\yxz\wiki\concepts\notam.md` — read when parsing an unfamiliar Q-code or FIR; canonical NOTAM ID format and ICAO-format field reference.
- `D:\DOT\yxz\wiki\concepts\launch-window-slip.md` — read when implementing the slip-probability score itself; window taxonomy and weighted signal formula.

---

## 12. Items Flagged for Live-API Verification

When FAA-side access (an SCDS account or confirmed scrape allowlist) is in place, verify in one session:

1. **Whether `notams.aim.faa.gov/notamSearch/` exposes a documented machine-readable export.** The yxz wiki ingest reports `requests.get` calls against `faa.gov`-family hosts returned HTTP 403 (likely server-side bot block, not an absent API). Confirm whether a JSON/XML endpoint exists behind the iframe, or whether the public path is genuinely HTML-only.
2. **Exact SWIM FNS / SCDS account application steps and SLA.** `scds.faa.gov` describes the process but publishes no turn-around-time commitment.
3. **Whether the AST Launch Manifest is published as JSON or only PDF.** `faa.gov/data_research/commercial_space_data/licenses/` is described in the yxz wiki as web/PDF only. If PDF-only, evaluate text-extraction approach.
4. **Exact mapping from a Part 450 launch license to the issued NOTAM ID.** The license is issued by FAA AST; the NOTAM is issued by ARTCC on the operator's behalf. The yxz wiki does NOT document whether license-modification records reference the NOTAM ID. Required for deterministic `license_id → notam_id` joins (vs date/vehicle/site heuristics) in slip-probability dataset rows.
5. **DINS multi-ICAO response format under sustained load.** Variant A §5.1 assumes plain-text blocks. Confirm DINS does not silently switch to HTML under high request volume and document the rate at which output degrades.
6. **Whether `FnsRestApi` (the `github.com/faa-swim/fns-client` REST wrapper) accepts non-Java clients.** The reference implementation is Java; the REST surface *should* be language-agnostic but is not confirmed.
7. **Whether `tfr.faa.gov/save_pages/detail_<number>.xml` still serves valid XML for active TFRs.** The yxz wiki documents this pattern but predates the 2026 FAA site refresh.

Each flagged item appears inline above with the `⚠️ verify against live FAA access` tag.
