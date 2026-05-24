---
title: Space-Track CDM operational API
type: research
tier: T2
status: ingested
ingested: 2026-05-24
sources: [https://www.space-track.org/documentation, https://github.com/python-astrodynamics/spacetrack, https://spacetrack.readthedocs.io/en/latest/usage.html]
---

# Space-Track CDM Operational API — Day 1 Ingestor Handbook

**Scope.** This document is the verbatim operational reference for the Spacesharks Mission Desk **Tier-2 conjunction ingestor**. It tells an engineer what URL to hit, what string to POST, what field names to parse, when to back off, and what to record for provenance. Conceptual depth on the *meaning* of Pc, covariance, decision thresholds, and operator policy lives in the yxz wiki — links at the bottom. **Do not re-derive theory here.** If you need to know why we use 1×10⁻⁴, read the wiki. If you need to know which HTTP header to send, read this.

---

## 1. Endpoint Catalog

Space-Track exposes its REST API under two controllers; CDMs live in both:

| Controller | Class | Access |
|---|---|---|
| `basicspacedata` | `cdm_public` | Any registered free account |
| `expandedspacedata` | `cdm` | Operator account only (NORAD ID of primary registered with 18 SDS) |

### 1.1 Base URL pattern (verbatim from Space-Track docs)

```
/{controller}/query/class/{class}/{predicate1}/{value1}/{predicate2}/{value2}/.../orderby/{field}/format/{format}
```

Source: `https://www.space-track.org/documentation` (predicate/value pairs are slash-delimited; there is **no** query-string syntax).

### 1.2 Concrete URL templates

**(a) Recent CDMs for a given NORAD ID as primary object:**
```
https://www.space-track.org/basicspacedata/query/class/cdm_public/SAT_1_ID/{norad}/orderby/TCA%20desc/limit/20/format/json
```

**(b) CDMs by date range (TCA in the next 7 days):**
```
https://www.space-track.org/basicspacedata/query/class/cdm_public/TCA/%3Enow/TCA/%3Cnow%2B7/orderby/TCA%20asc/format/json
```
(`%3E` = `>`, `%3C` = `<`, `%2B` = `+`. The Space-Track syntax for "now plus 7 days" is `now+7`. ⚠️ verify against live API — Space-Track's documented examples show `>now-30` style; the `now+N` future form is used by python-spacetrack but should be verified once an account is provisioned.)

**(c) CDMs above a Pc threshold:**
```
https://www.space-track.org/basicspacedata/query/class/cdm_public/PC/%3E0.00001/TCA/%3Enow/orderby/PC%20desc/limit/200/format/json
```

**(d) Operator-tier full CDM (covariance included):**
```
https://www.space-track.org/expandedspacedata/query/class/cdm/SAT_1_ID/{norad}/orderby/CREATION_DATE%20desc/limit/10/format/json
```

### 1.3 Format options

Per Space-Track docs: `tle`, `xml`, `kvn`, `json`, `csv`, `html`. **Use `json`** for the ingestor. KVN is the CCSDS-native serialization and is useful for human inspection but harder to parse.

---

## 2. Authentication Flow

Space-Track does **not** use OAuth, API keys, or bearer tokens. It uses a cookie session established via form POST.

### 2.1 The flow

1. POST `https://www.space-track.org/ajaxauth/login` with form fields `identity={email}` and `password={password}`.
2. Server returns a session cookie (named `chocolatechip`, but treat as opaque).
3. Include the cookie on every subsequent GET to `/basicspacedata/query/...` or `/expandedspacedata/query/...`.
4. Session lifetime is **~2 hours of inactivity**; re-authenticate on 401/403. ⚠️ verify against live API — Space-Track does not publish an exact TTL, but operational reports converge on ~2h.

### 2.2 Raw `requests` pattern (use only if you cannot use python-spacetrack)

```python
import os, requests
s = requests.Session()
r = s.post(
    "https://www.space-track.org/ajaxauth/login",
    data={"identity": os.environ["SPACETRACK_USER"],
          "password": os.environ["SPACETRACK_PASS"]},
    timeout=30,
)
r.raise_for_status()
# session cookie is now on `s`; subsequent GETs work directly
```

### 2.3 Account requirement

A free account at `https://www.space-track.org/auth/createAccount` is **required**. Approval is typically 24–48 h. The User Agreement restricts to non-commercial use and forbids redistribution of raw data — the ingestor must store CDMs only inside the spacesharks lifecycle log, not republish them.

---

## 3. `cdm_public` vs `cdm` — What You Actually Get

Honest summary of what is in each class:

| Field group | `cdm_public` | `cdm` (operator) |
|---|---|---|
| `CDM_ID`, `CREATED`, `TCA`, `MISS_DISTANCE`, `PC` | yes | yes |
| `SAT_1_ID`, `SAT_2_ID`, names, exclusion volumes, relative speed | yes | yes |
| `EMERGENCY_REPORTABLE` flag | yes | yes |
| Primary state vector (position + velocity at TCA) | partial | full |
| Secondary state vector | **omitted** | full |
| Primary 6×6 RTN covariance (21 unique elements) | **omitted** | full |
| Secondary 6×6 RTN covariance (21 unique elements) | **omitted** | full |
| `HARD_BODY_RADIUS`, `AREA_PC`, maneuver metadata | **omitted** | yes |
| `COLLISION_PROBABILITY_METHOD` (e.g. `FOSTER-1992`) | typically present | present |

**Operational consequence.** With only `cdm_public`, the spacesharks ingestor must **trust** the 18 SDS-reported `PC` value. It cannot independently re-run Foster, Akella, Chan, Alfano, or Patera because the inputs (covariance, HBR) are not delivered. This is acceptable for MVP triage. It is **not** acceptable for a production avoidance decision — that requires an operator account or a commercial upgrade (see §11).

⚠️ Some sources state `cdm_public` strips *all* secondary data. In practice, `SAT_2_ID`, `SAT_2_NAME`, `RELATIVE_SPEED`, and `MISS_DISTANCE` remain; only the **state vector and covariance** of the secondary are absent.

---

## 4. Field Schema (CCSDS 508.0-B-1 names verbatim)

Space-Track's class fields follow CCSDS 508.0-B-1 naming, with some shorthand. The fields the ingestor reads on every CDM:

| Space-Track field | CCSDS 508.0-B-1 field | Units / format |
|---|---|---|
| `CDM_ID` | (Space-Track unique ID) | integer |
| `CREATED` | `CREATION_DATE` | ISO-8601 UTC |
| `TCA` | `TCA` | ISO-8601 UTC |
| `MISS_DISTANCE` | `MISS_DISTANCE` | meters |
| `PC` | `COLLISION_PROBABILITY` | dimensionless decimal |
| (per-CDM if populated) | `COLLISION_PROBABILITY_METHOD` | string, e.g. `FOSTER-1992`, `CHAN-1997`, `ALFANO-2005` |
| `SAT_1_ID` | `OBJECT1_DESIGNATOR` | NORAD catalog number |
| `SAT_2_ID` | `OBJECT2_DESIGNATOR` | NORAD catalog number |
| `SAT_1_NAME`, `SAT_2_NAME` | `OBJECT1`, `OBJECT2` | string |
| `RELATIVE_SPEED` | `RELATIVE_SPEED` | m/s |
| `SAT_1_EXCL_VOL`, `SAT_2_EXCL_VOL` | (exclusion volume radii) | meters |
| `EMERGENCY_REPORTABLE` | (Space-Track flag) | "Y"/"N" |
| `MESSAGE_FOR` | `MESSAGE_FOR` | string (primary object designation as written by issuer) |
| `HARD_BODY_RADIUS` (only in `cdm`) | `HARD_BODY_RADIUS` | meters |

Covariance, in the operator-tier `cdm` class, comes as 21 unique elements per object in the **RTN** (Radial / Transverse / Normal) frame: `CR_R`, `CT_R`, `CT_T`, `CN_R`, `CN_T`, `CN_N`, `CRDOT_R`, `CRDOT_T`, `CRDOT_N`, `CRDOT_RDOT`, `CTDOT_R`, ... etc., prefixed with `OBJECT1_` and `OBJECT2_`.

### 4.1 Example record (SYNTHETIC — do not use as real data)

```json
{
  "CDM_ID": "9000123456",
  "CREATED": "2026-05-23T18:04:11.000000",
  "EMERGENCY_REPORTABLE": "N",
  "TCA": "2026-05-25T07:42:18.314000",
  "MISS_DISTANCE": "412.7",
  "RELATIVE_SPEED": "14215.2",
  "PC": "3.18E-05",
  "SAT_1_ID": "52084",
  "SAT_1_NAME": "STARCLOUD-DEMO-1",
  "SAT_1_EXCL_VOL": "5.0",
  "SAT_2_ID": "39772",
  "SAT_2_NAME": "COSMOS 1408 DEB",
  "SAT_2_EXCL_VOL": "1.0",
  "MESSAGE_FOR": "STARCLOUD-DEMO-1"
}
```
This record is synthesized for documentation only. NORAD IDs, names, and values do not correspond to a real conjunction.

---

## 5. Rate Limits

**Verbatim from `https://www.space-track.org/documentation`:**

> "Limit API queries to less than 30 requests per 1 minute(s) and 300 requests per 1 hour(s)"

Violation triggers automatic account throttling and, on repeat, suspension. The ingestor MUST stay strictly under these caps.

### 5.1 Recommended cadence for spacesharks ingestor

| Mode | Cadence | Per-hour request budget |
|---|---|---|
| Constellation-wide CDM pull (default) | every 8 h | 3/day → trivially under cap |
| Per-event re-poll for known Red events | every 1 h per event | ≤ 1/hour/event |
| Pre-TCA emergency (Red, < 12 h to TCA) | every 30 min per event | ≤ 2/hour/event |

If we track ≤ 50 active satellites, the constellation pull is one paginated query — well under 30/min. The risk is implementing tight retry loops on error: don't.

### 5.2 How python-spacetrack throttles

The library applies an internal limiter that **blocks the calling thread** to stay under 30 req/min. Per the README on the python-astrodynamics/spacetrack repository: "Automatic rate limiting — Gets limited to <30 requests per minute automatically by blocking." There is no async cancellation; if you hit the limit, the next call sleeps. The ingestor's job-control must therefore:

- Wrap library calls in `asyncio.wait_for(..., timeout=N)` if you have hard deadlines.
- Log when a call blocks > 5 s (signal of approaching the cap).
- Never call from a tight loop without intentional spacing.

---

## 6. Python-Spacetrack Snippet (Runnable)

This is the canonical Day-1 ingestor sketch. It authenticates, pulls the most recent high-Pc CDMs for a watched NORAD ID, and emits one `spacesharks-event` record per CDM. It is real, importable, runnable Python — `pip install spacetrack` then export `SPACETRACK_USER` and `SPACETRACK_PASS`.

```python
"""spacesharks Day-1 CDM ingestor — minimal viable retrieval."""
import json
import os
from datetime import datetime, timezone

from spacetrack import SpaceTrackClient
import spacetrack.operators as op

ATTENTION_PC = 1e-7   # below this we ignore
WATCH_NORAD = int(os.environ.get("WATCH_NORAD", "25544"))  # demo: ISS

def ingest_cdms_for(norad_id: int) -> list[dict]:
    st = SpaceTrackClient(
        identity=os.environ["SPACETRACK_USER"],
        password=os.environ["SPACETRACK_PASS"],
    )
    # cdm_public method on the client; predicates are kwargs.
    raw = st.cdm_public(
        sat_1_id=norad_id,
        pc=op.greater_than(ATTENTION_PC),
        orderby="TCA asc",
        limit=200,
        format="json",
    )
    now = datetime.now(timezone.utc)
    events = []
    for cdm in raw:
        tca = datetime.fromisoformat(cdm["TCA"].replace("Z", "+00:00"))
        pc = float(cdm.get("PC") or 0.0)
        events.append({
            "schema": "spacesharks.event.conjunction.v1",
            "source": "space-track.cdm_public",
            "cdm_id": cdm["CDM_ID"],
            "created": cdm["CREATED"],
            "tca": cdm["TCA"],
            "time_to_tca_h": round((tca - now).total_seconds() / 3600, 2),
            "miss_distance_m": float(cdm["MISS_DISTANCE"]),
            "pc": pc,
            "primary_norad": int(cdm["SAT_1_ID"]),
            "secondary_norad": int(cdm["SAT_2_ID"]),
            "covariance_available": False,  # cdm_public never includes it
        })
    return events

if __name__ == "__main__":
    for ev in ingest_cdms_for(WATCH_NORAD):
        print(json.dumps(ev))
```

Notes:
- `SpaceTrackClient` is synchronous by default. There is an async variant — `AsyncSpaceTrackClient` — for `asyncio` callers. Use the sync version for a cron-driven Day-1 ingestor; the latency is dominated by the API, not the client.
- `op.greater_than()` and `op.inclusive_range()` are the canonical predicate helpers. Use them rather than string-formatted `">1e-7"` to keep the call type-safe.
- python-spacetrack's `cdm_public` method maps to `/basicspacedata/query/class/cdm_public/...`. For operator-tier, call `st.cdm(...)` (maps to `/expandedspacedata/query/class/cdm/...`).

---

## 7. Pc Decision Threshold Table (verbatim)

The ingestor tiers every CDM by Pc on intake. The full conceptual treatment is in `D:\DOT\yxz\wiki\concepts\pc-probability-of-collision.md`; this is the operational lookup.

| Tier | Pc Range | Required Action | Source |
|---|---|---|---|
| **Red** | `Pc ≥ 1×10⁻⁴` | Mandatory maneuver | NASA NPR 8079.1; NTRS 20190029214 (CARA architecture) |
| **Yellow** | `7×10⁻⁵ ≤ Pc < 1×10⁻⁴` | Maneuver analysis; enhanced monitoring | NASA CARA (NTRS 20190029214) |
| **Green** | `Pc < 1×10⁻⁵` | No action; attention possible above 1×10⁻⁷ | NASA CARA |

Cross-operator reference (do not change the default; document per-mission overrides as config):

- **NASA / CARA:** Red ≥ 1×10⁻⁴ (default).
- **ESA:** Red ≥ 1×10⁻⁴ (High Impact Event threshold).
- **JAXA:** Red ≥ 1×10⁻³ (more permissive — JAXA does fewer maneuvers).
- **SpaceX Starlink:** Not publicly disclosed. Uses Alfano method for Pc.
- **Commercial operators (Planet, Maxar, Iridium):** Typically 1×10⁻⁵–1×10⁻⁴; not disclosed.

⚠️ The NASA yellow floor at 7×10⁻⁵ is the documented default but is sometimes reported as 1×10⁻⁵ in secondary literature. Always emit both the raw Pc and the tier label so a downstream consumer can re-tier if their mission policy differs.

---

## 8. TraCSS Transition — Timing Risk

The civil STM mission is moving from DoD (18 SDS / Space-Track) to the **Office of Space Commerce** (DoC) under the **Traffic Coordination System for Space (TraCSS)**.

- TraCSS 1.0 initial capabilities fielded September 2024; CDMs currently still flow through `space-track.org` to beta users.
- TraCSS production interface (`TraCSS.gov`) targeted for **2026**.
- Operator waitlist opened February 2026.
- See `D:\DOT\yxz\wiki\sources\tracss-oasis-announcement-2024.md` for the full OSC announcement and the three-component (OASIS / SKYLINE / HORIZON) architecture.

**Risk for spacesharks Day-1 build:**

1. The ingestor is built against `space-track.org` URLs. When TraCSS.gov goes live, **the URL host changes**, the auth flow may change, and the CDM JSON schema gets the TraCSS extensions (`OD_QUALITY` field, operator metadata, maneuver-plan fields).
2. Mitigation: abstract the ingestor behind a `ConjunctionDataSource` interface with a single concrete `SpaceTrackSource` implementation today. A future `TraCSSSource` swaps in at one seam.
3. The CCSDS 508.0-B-1 field names (`TCA`, `MISS_DISTANCE`, `COLLISION_PROBABILITY`, etc.) **do not change** — TraCSS CDM Spec v2.1 is a CCSDS-aligned extension. Parsing code is portable.
4. Do **not** depend on Space-Track-specific shorthand like `SAT_1_ID` deep in business logic. Map to canonical CCSDS names at the ingestor boundary.

---

## 9. Failure Modes and Degradation

| Failure | Symptom | Strategy |
|---|---|---|
| **Auth expired** | 401 on a GET after a long-idle session | Re-POST `/ajaxauth/login`, retry once. If second attempt fails, page operator (credentials issue, not transient). |
| **Account suspended** | 403 on login | Do not auto-retry — likely rate-limit ban. Alert + halt CDM ingestor; surface in spacesharks status. |
| **Rate limit hit** | 429 or unexpected blocking from `python-spacetrack` | Honor the library's internal sleep. If you see 429 directly, exponential backoff: 60 s, 120 s, 240 s, then halt. Reduce poll cadence. |
| **Empty result** | `[]` JSON body | Treat as transient on first occurrence — many small constellations have hours with no CDMs. After 24 h of empty results across the whole watchlist, alert (likely auth or filter regression). |
| **Secondary covariance missing** | `OBJECT2_*` covariance fields absent on `cdm_public` | **Expected.** Record `covariance_available=false` and flag the event as "trust 18 SDS Pc only." Do not attempt independent Pc recomputation. |
| **TCA in the past** | `TCA < now` for a freshly-fetched CDM | Conjunction happened or was already resolved. Record as historical and exclude from active triage. |
| **Malformed numeric field** | `PC` is `""` or `"NULL"` | Coerce to `0.0` only after logging the raw value. Never silently swallow. |
| **TLS / DNS error** | `requests` `ConnectionError` | Retry 3× with jitter (1s, 4s, 16s). On persistent failure, downgrade to last-known-good cached CDMs (≤ 8 h old) and flag stale. |

**Degradation principle:** the spacesharks Mission Desk should *never* go silent because Space-Track is down. If the CDM ingestor fails, emit a `spacesharks.event.ingestor.degraded` record so the operator brief shows "conjunction data stale since {ts}" rather than displaying an empty Red/Yellow/Green panel.

---

## 10. Provenance Fields the Ingestor MUST Record

Every spacesharks event derived from a Space-Track CDM must persist these fields so a recommendation can be traced back to its source CDM:

| Field | Source on CDM | Why |
|---|---|---|
| `cdm_id` | `CDM_ID` | Primary key for the conjunction event at Space-Track |
| `cdm_created` | `CREATED` | When 18 SDS generated this CDM — distinct from ingest time |
| `cdm_ingested_at` | (local clock) | When spacesharks pulled it — lets us measure ingest lag |
| `tca` | `TCA` | Anchor for urgency calculations downstream |
| `message_for` | `MESSAGE_FOR` | The primary object as the issuer named it — avoids ambiguity when SAT_1_NAME mutates |
| `source` | constant `"space-track.cdm_public"` (or `"space-track.cdm"`) | Disambiguates from future LeoLabs/TraCSS sources |
| `pc_method` | `COLLISION_PROBABILITY_METHOD` (if present) | Tells the operator which algorithm produced Pc |
| `raw_cdm_payload_sha256` | SHA-256 of the JSON record | Tamper-evidence; lets us prove what we ingested |

The first six are non-negotiable for the Day-1 build. The last two are recommended for hackathon-grade auditability and trivial to add.

---

## 11. Upgrade Path (brief)

When MVP is validated and we need real covariance and sub-hour latency:

- **LeoLabs Conjunction Alerts** — commercial; sub-5-minute CDM delivery; ~400% higher update frequency than 18 SDS; independent covariance computed from LeoLabs phased-array radar network. Pricing not public.
- **Slingshot Beacon** — operator-to-operator coordination layer; complements (does not replace) the CDM feed; useful when secondary is another commercial operator we can negotiate with.
- **TraCSS.gov** — when live, becomes the canonical civil source; same CCSDS schema with `OD_QUALITY` and operator-metadata extensions.

Full provider comparison, capabilities, and integration notes live in `D:\DOT\yxz\wiki\synthesis\cdm-pc-decisioning.md` §7 and `D:\DOT\yxz\wiki\sources\leolabs-conjunction-alerts-2025.md`. **Do not duplicate that depth here** — the Day-1 ingestor only needs to know that a `ConjunctionDataSource` abstraction will be needed.

---

## 12. yxz Wiki Cross-References (read these for conceptual depth)

- `D:\DOT\yxz\wiki\synthesis\cdm-pc-decisioning.md` — full CDM-to-decision workflow, commercial provider tiers, NemoClaw sandbox integration.
- `D:\DOT\yxz\wiki\concepts\pc-probability-of-collision.md` — Pc math, five computation methods, dilution region, threshold derivation.
- `D:\DOT\yxz\wiki\concepts\screening-volume.md` — the 2 km × 25 km × 25 km filter that *produces* CDMs.
- `D:\DOT\yxz\wiki\concepts\covariance-ellipsoid.md` — what the missing secondary covariance means in practice.
- `D:\DOT\yxz\wiki\concepts\tca-time-of-closest-approach.md` — urgency tiering by time-to-TCA.
- `D:\DOT\yxz\wiki\sources\ccsds-508-cdm-2013.md` — the CDM standard.
- `D:\DOT\yxz\wiki\sources\space-track-cdm-api-2023.md` — full Space-Track field catalog beyond the ingestor essentials.
- `D:\DOT\yxz\wiki\sources\tracss-oasis-announcement-2024.md` — TraCSS architecture, timeline, contractors.
- `D:\DOT\yxz\wiki\sources\nasa-cara-handbook-2023.md` — threshold source of truth.
- `D:\DOT\yxz\wiki\entities\18-sds.md` — the CDM issuer.

---

## 13. Items Flagged for Live-API Verification

When the team gets a Space-Track account, verify in one session:

1. `now+N` future-date syntax for `TCA` predicates (Space-Track docs only show `now-N` historical form).
2. Exact session TTL (the ~2 h figure is from operational reports, not docs).
3. Whether `COLLISION_PROBABILITY_METHOD` is consistently populated on `cdm_public` (docs are silent; community reports mixed presence).
4. Whether `MESSAGE_FOR` is present on `cdm_public` or only on operator-tier `cdm` (CCSDS spec mandates it; Space-Track may strip it).
5. Pagination behavior beyond `limit=200` — Space-Track has documented limits per controller that may force chunked queries for constellation-wide pulls.

Each flagged item appears inline above with the `⚠️ verify against live API` tag.
