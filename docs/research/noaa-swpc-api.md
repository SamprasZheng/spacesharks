---
title: NOAA SWPC operational API
type: research
tier: T1
status: ingested
ingested: 2026-05-24
sources: [https://services.swpc.noaa.gov/, https://www.swpc.noaa.gov/]
---

# NOAA SWPC operational API — Day 1 ingestor handbook

This is the **operational** handbook for building the Spacesharks Tier‑1 NOAA SWPC ingestor on Day 1. Conceptual coverage of Kp / G‑scale / radiation belt physics lives in the yxz wiki (`concepts/solar-cycle-25-leo-radiation`). This page only documents:

- which endpoints to poll,
- their JSON shape (verified live against `services.swpc.noaa.gov` on 2026‑05‑24),
- update cadence and the Spacesharks freshness budget,
- the alert taxonomy thresholds,
- a runnable Python sketch that emits records in the Spacesharks event schema,
- failure modes and provenance.

---

## 1. Product catalog — SWPC products → satellite‑ops decisions

| SWPC product | Decision it drives | Scale | Tier‑1 status |
|---|---|---|---|
| GOES X‑ray flux (long, 0.1–0.8 nm) | Safe‑mode / payload‑off on M/X flare | R1–R5 | **Tier‑1, must‑have** |
| GOES integral proton flux (≥10 MeV) | SEP shielding, single‑event‑upset risk, EVA hold | S1–S5 | **Tier‑1, must‑have** |
| Planetary K‑index (3‑hour) | Drag / attitude / thermospheric heating | G1–G5 | **Tier‑1, must‑have** |
| Boulder / planetary K 1‑minute estimate | Faster geomagnetic ramp detection | (unscaled) | Tier‑1, secondary |
| Solar wind plasma (DSCOVR/ACE, 5‑min) — `speed`, `density`, `temperature` | CME arrival shock detection | — | Tier‑1, secondary |
| Solar wind magnetic field (DSCOVR/ACE, 5‑min) — `bz_gsm`, `bt` | Southward Bz → geo‑effective storm onset | — | Tier‑1, secondary |
| Alerts / Watches / Warnings (`alerts.json`) | Human‑issued forecaster events (ALTEF3, TIIA, WARK04, …) | Mixed | **Tier‑1, must‑have** |
| NOAA scales (`noaa-scales.json`) | Current + 3‑day R/S/G probability | R/S/G | Tier‑1, secondary |
| 3‑day / 27‑day Kp forecast | Pre‑pass planning, manoeuvre windows | G1–G5 | Tier‑2 |
| OVATION aurora grid | Aurora overlay only — not used for sat‑ops in v1 | — | Tier‑3 (display only) |
| Solar regions (`solar_regions.json`) | M/X‑flare probability per active region | — | Tier‑2 |
| F10.7 cm radio flux | Long‑term drag modelling, mission planning | — | Tier‑2 |
| Sunspot number, 10cm‑flux‑30‑day | Long‑term context | — | Tier‑3 |
| Geoelectric field (power‑grid) | **Out of scope** for sat‑ops | — | Not ingested |

Day 1 ingest list (must‑have, locked):

1. GOES X‑ray (`/json/goes/primary/xrays-1-day.json`)
2. GOES proton (`/json/goes/primary/integral-protons-1-day.json`)
3. Planetary Kp (`/products/noaa-planetary-k-index.json`)
4. Alerts (`/products/alerts.json`)
5. Solar wind plasma + mag (`/products/solar-wind/{plasma,mag}-5-minute.json`)
6. NOAA scales (`/products/noaa-scales.json`)

---

## 2. API endpoints — verbatim URLs

Root: `https://services.swpc.noaa.gov/`
No HTTP authentication, no API key, no quota header. Plain GET. CORS allows browser access. All responses are JSON (`Content-Type: application/json`) unless otherwise noted.

### 2.1 Top‑level directory layout (verified 2026‑05‑24)

```
https://services.swpc.noaa.gov/
├── experimental/      # pre‑production feeds, do NOT rely on for Tier‑1
├── images/            # PNG / GIF visualisations
├── json/              # primary JSON feeds (newer products)
│   ├── ace/
│   ├── dscovr/
│   ├── geospace/
│   ├── goes/
│   ├── lists/
│   ├── rtsw/
│   ├── solar-cycle/
│   └── stereo/
├── netcdf/            # NetCDF archives
├── products/          # legacy + curated JSON products
│   ├── animations/
│   ├── ccor1/         # coronograph
│   ├── flares/
│   ├── geospace/
│   ├── glotec/
│   ├── gong/
│   ├── solar-wind/
│   └── summary/
├── static/
└── text/              # human‑readable / forecaster bulletins
```

### 2.2 Tier‑1 endpoints (must‑have)

| Purpose | URL |
|---|---|
| Alerts / watches / warnings | `https://services.swpc.noaa.gov/products/alerts.json` |
| Planetary K‑index, 3‑hour | `https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json` |
| Planetary K‑index, 1‑min estimate | `https://services.swpc.noaa.gov/json/planetary_k_index_1m.json` |
| 3‑day Kp forecast | `https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json` |
| NOAA scales (now + 3‑day prob.) | `https://services.swpc.noaa.gov/products/noaa-scales.json` |
| GOES primary X‑ray, 1‑day | `https://services.swpc.noaa.gov/json/goes/primary/xrays-1-day.json` |
| GOES primary X‑ray, 7‑day | `https://services.swpc.noaa.gov/json/goes/primary/xrays-7-day.json` |
| GOES primary proton integral, 1‑day | `https://services.swpc.noaa.gov/json/goes/primary/integral-protons-1-day.json` |
| GOES primary proton integral, 7‑day | `https://services.swpc.noaa.gov/json/goes/primary/integral-protons-7-day.json` |
| Solar wind plasma 5‑min (DSCOVR/ACE) | `https://services.swpc.noaa.gov/products/solar-wind/plasma-5-minute.json` |
| Solar wind magnetic field 5‑min | `https://services.swpc.noaa.gov/products/solar-wind/mag-5-minute.json` |

### 2.3 Tier‑2 endpoints (nice‑to‑have for Day 2+)

| Purpose | URL |
|---|---|
| F10.7 cm flux (current) | `https://services.swpc.noaa.gov/json/f107_cm_flux.json` |
| Predicted F10.7 cm | `https://services.swpc.noaa.gov/json/predicted_f107cm_flux.json` |
| Solar active regions (daily) | `https://services.swpc.noaa.gov/json/solar_regions.json` |
| Electron fluence forecast | `https://services.swpc.noaa.gov/json/electron_fluence_forecast.json` |
| OVATION aurora forecast grid | `https://services.swpc.noaa.gov/json/ovation_aurora_latest.json` |
| Edited events (forecaster log) | `https://services.swpc.noaa.gov/json/edited_events.json` |
| Solar probabilities | `https://services.swpc.noaa.gov/json/solar_probabilities.json` |
| 45‑day forecast | `https://services.swpc.noaa.gov/json/45-day-forecast.json` |
| ICAO space weather advisories | `https://services.swpc.noaa.gov/json/icao-space-weather-advisories.json` |
| Sunspot report | `https://services.swpc.noaa.gov/json/sunspot_report.json` |
| Kyoto Dst | `https://services.swpc.noaa.gov/products/kyoto-dst.json` |
| 10 cm flux 30‑day | `https://services.swpc.noaa.gov/products/10cm-flux-30-day.json` |

> **GOES secondary** — replace `primary` with `secondary` in the path for the backup spacecraft (e.g. `/json/goes/secondary/xrays-1-day.json`). Day 1 ingestor should fail over to secondary when primary returns stale data (>10 min since `time_tag`).

### 2.4 Endpoints flagged

All 11 Tier‑1 URLs above were fetched live on 2026‑05‑24 and returned valid JSON. No Tier‑1 endpoints are unverified.

---

## 3. JSON schemas — verified live samples

### 3.1 `alerts.json` (object‑per‑record)

```json
[
  {
    "product_id": "EF3A",
    "issue_datetime": "2026-05-24 05:00:10.340",
    "message": "Space Weather Message Code: ALTEF3\r\nSerial Number: 3694\r\nIssue Time: 2026 May 24 0500 UTC\r\n\r\nCONTINUED ALERT: Electron 2MeV Integral Flux exceeded 1000pfu\nContinuation of Serial Number: 3693\nBegin Time: 2026-05-16 17:40\nYesterday Maximum 2MeV Flux: 3762 pfu\n..."
  }
]
```

Fields:
- `product_id` — short alphanumeric code, the alert taxonomy key (see §5.4). `EF3A` = electron flux >1000 pfu at 2 MeV; `TIIA` = Type II radio sweep; `WARK04` = Kp ≥4 watch; etc.
- `issue_datetime` — UTC, format `YYYY-MM-DD HH:MM:SS.fff` (note: space separator, **not** ISO `T`).
- `message` — free text. The first line `Space Weather Message Code: <CODE>` is the canonical machine‑parsable code. `Serial Number` is monotone per code.

> **Parsing note:** the same `product_id` appears for both initial issue and continuations — disambiguate by `Serial Number` extracted from `message`. The text contains both `\r\n` and `\n` — normalise on ingest.

### 3.2 `noaa-planetary-k-index.json` (object‑per‑record, 3‑hour cadence)

```json
[
  {"time_tag": "2026-05-17T00:00:00", "Kp": 2.00, "a_running": 7,  "station_count": 8},
  {"time_tag": "2026-05-17T03:00:00", "Kp": 2.33, "a_running": 9,  "station_count": 8},
  {"time_tag": "2026-05-17T06:00:00", "Kp": 2.00, "a_running": 7,  "station_count": 8}
]
```

- `time_tag` — ISO 8601 UTC, naive (no `Z` suffix).
- `Kp` — float, range 0.00–9.00 in 1/3 steps. G‑scale mapping in §5.1.
- `a_running` — running ap equivalent (linear, geomagnetic).
- `station_count` — number of contributing magnetometer stations (estimated quality flag; <6 means degraded).

> **Latency:** record N for hour H is typically posted within ~30 min after H ends. The 1‑minute estimate (`/json/planetary_k_index_1m.json`) closes the gap.

### 3.3 `goes/primary/xrays-1-day.json` (two records per timestamp — one per energy band)

```json
[
  {
    "time_tag": "2026-05-23T11:21:00Z",
    "satellite": 18,
    "flux": 9.712956661189764e-09,
    "observed_flux": 3.91842576163981e-08,
    "electron_correction": 2.9471301843386755e-08,
    "electron_contaminaton": true,
    "energy": "0.05-0.4nm"
  },
  {
    "time_tag": "2026-05-23T11:21:00Z",
    "satellite": 18,
    "flux": 8.10367168924131e-07,
    "observed_flux": 8.27398707770044e-07,
    "electron_correction": 1.703156371490877e-08,
    "electron_contaminaton": false,
    "energy": "0.1-0.8nm"
  }
]
```

- `time_tag` — ISO 8601 UTC, **with** `Z`.
- `satellite` — int (18 = GOES‑18, 19 = GOES‑19, etc.).
- `flux` — W/m², electron‑contamination‑corrected. **This is the value used for R‑scale flare classification.**
- `observed_flux` — raw flux before electron correction.
- `electron_correction` — subtracted amount.
- `electron_contaminaton` *(SIC — note typo, preserve verbatim in the parser)* — boolean. When `true`, treat `flux` as best‑effort only; the short‑band 0.05–0.4 nm channel is often electron‑contaminated during high‑energy events.
- `energy` — string, exactly `"0.05-0.4nm"` (XRS short) or `"0.1-0.8nm"` (XRS long). The R‑scale uses the **long band** 0.1–0.8 nm.

> **Spacesharks contract:** when classifying flare level, filter records to `energy == "0.1-0.8nm"` first, then apply §5.2.

### 3.4 `goes/primary/integral-protons-1-day.json`

```json
[
  {"time_tag": "2026-05-23T11:25:00Z", "satellite": 19, "flux": 12.572590827941895, "energy": ">=1 MeV"},
  {"time_tag": "2026-05-23T11:25:00Z", "satellite": 19, "flux": 0.20005369186401367, "energy": ">=10 MeV"},
  {"time_tag": "2026-05-23T11:25:00Z", "satellite": 19, "flux": 0.16602618992328644, "energy": ">=100 MeV"}
]
```

- `flux` units: pfu = particles · cm⁻² · s⁻¹ · sr⁻¹.
- `energy` values: `">=1 MeV"`, `">=10 MeV"`, `">=50 MeV"`, `">=100 MeV"`, `">=500 MeV"`. The S‑scale is defined on the `">=10 MeV"` channel (see §5.3).

### 3.5 `noaa-scales.json` (forecast current + 3‑day probabilities)

Top‑level is an object keyed by day offset:
- `"-1"` = yesterday, `"0"` = today / now, `"1"` = today (rest of UTC day), `"2"` = +1 day, `"3"` = +2 day.

```json
{
  "0": {
    "DateStamp": "2026-05-24",
    "TimeStamp": "11:21:00",
    "R": {"Scale": "0", "Text": "none", "MinorProb": null, "MajorProb": null},
    "S": {"Scale": "0", "Text": "none", "Prob": null},
    "G": {"Scale": "0", "Text": "none"}
  },
  "1": {
    "DateStamp": "2026-05-24", "TimeStamp": "11:21:00",
    "R": {"Scale": null, "Text": null, "MinorProb": "35", "MajorProb": "5"},
    "S": {"Scale": null, "Text": null, "Prob": "5"},
    "G": {"Scale": "0", "Text": "none"}
  }
}
```

Records with day offset `"0"` and `"-1"` carry observed `Scale` strings (`"0"`–`"5"`). Forecast days (`"1"`–`"3"`) carry `MinorProb` / `MajorProb` / `Prob` (percentage strings).

### 3.6 `solar-wind/plasma-5-minute.json` (CSV‑style: header row + value rows)

```json
[
  ["time_tag", "density", "speed", "temperature"],
  ["2026-05-24 11:18:00.000", "3.78", "304.6", "15871"],
  ["2026-05-24 11:19:00.000", "3.50", "303.3", "16333"]
]
```

- All values are **strings** — parse to float.
- `density` in cm⁻³, `speed` in km/s, `temperature` in K.
- `time_tag` is space‑separated UTC, milliseconds appended.

### 3.7 `solar-wind/mag-5-minute.json`

```json
[
  ["time_tag", "bx_gsm", "by_gsm", "bz_gsm", "lon_gsm", "lat_gsm", "bt"],
  ["2026-05-24 11:18:00.000", "-1.50", "-4.12", "-0.76", "250.04", "-9.78", "4.45"]
]
```

- Magnetic field in nT, GSM coordinates. **Negative `bz_gsm`** is geo‑effective; sustained `bz_gsm < -5 nT` for >30 min is a classic CME storm onset signature.

### 3.8 `solar_regions.json` (daily, one record per active region)

Key fields: `region` (NOAA AR number), `latitude`, `longitude`, `location` (e.g. `"S15E26"`), `area` (millionths of solar hemisphere), `spot_class` (McIntosh), `mag_class` (Mt Wilson — `Alpha`/`Beta`/`Gamma`/`Delta`), `c_xray_events`, `m_xray_events`, `x_xray_events`, `c_flare_probability`, `m_flare_probability`, `x_flare_probability`, `proton_probability`. All probabilities are integer percentages.

### 3.9 `ovation_aurora_latest.json` (forecast grid)

Top‑level: `{"Observation Time": "...", "Forecast Time": "...", "coordinates": [[lon, lat, aurora], ...]}`. Aurora is 0–100 (probability‑weighted intensity). 1° resolution. ~65 000 points. **Do not poll faster than 5 min** — file is ~1.5 MB.

---

## 4. Polling cadence and the Spacesharks freshness budget

Spacesharks Mission Desk hackathon plan locks the Tier‑1 freshness contract at **≤ 5 min freshness, ≤ 90 s ingest latency** (synthesis: `spacesharks-mission-desk-hackathon-plan.md`). The polling cadences below are tuned to meet that budget without hammering SWPC.

| Endpoint | SWPC update cadence | Recommended poll interval | Why |
|---|---|---|---|
| `goes/primary/xrays-1-day.json` | ~1 min | **60 s** | Flare onset must be caught fast; this is the most time‑critical feed. |
| `goes/primary/integral-protons-1-day.json` | ~5 min | **60 s** | SEP events ramp over minutes; over‑polling is cheap. |
| `products/alerts.json` | event‑driven (forecasters) | **60 s** | New alerts arrive at any moment; small file. |
| `solar-wind/plasma-5-minute.json` | 5 min | **120 s** | Already 5‑min averaged; poll every 2 min. |
| `solar-wind/mag-5-minute.json` | 5 min | **120 s** | Same. |
| `products/noaa-planetary-k-index.json` | every 3 h | **300 s** | Cheap to poll every 5 min for the new 3‑h slot. |
| `json/planetary_k_index_1m.json` | 1 min | **60 s** | Bridge for the 3‑h Kp gap. |
| `products/noaa-scales.json` | hourly | **600 s** | Forecast probabilities change slowly. |
| `json/solar_regions.json` | daily | **3600 s** | Daily synoptic update. |
| `ovation_aurora_latest.json` | 5 min | **300 s** | Big file (~1.5 MB), display‑only. |

### Ingest latency budget breakdown (Spacesharks 90 s target)

```
SWPC publish time    ──┐
                        ├─ Poll interval ≤ 60 s
Our poller fires    ──┘
                       ├─ HTTP round trip + parse: ~1–3 s
Record persisted to       ├─ Schema validation + provenance stamp: <500 ms
event store              ├─ Arbiter notified: <500 ms
                       ───
                       Total: well under 90 s if poll interval ≤ 60 s.
```

**Use `If-Modified-Since` / `ETag` headers** — SWPC serves both, and a 304 response is essentially free. Don't burn quota re‑downloading unchanged files.

---

## 5. Alert taxonomy

### 5.1 G‑scale (geomagnetic storm) — threshold on Kp

| Level | Kp | Label |
|---|---|---|
| G1 | 5 | Minor |
| G2 | 6 | Moderate |
| G3 | 7 | Strong |
| G4 | 8, including 9− | Severe |
| G5 | 9 | Extreme |

### 5.2 R‑scale (radio blackout) — threshold on GOES X‑ray 0.1–0.8 nm flux

| Level | Long‑band flux (W/m²) | GOES flare class | Label |
|---|---|---|---|
| R1 | ≥ 1 × 10⁻⁵ | M1 | Minor |
| R2 | ≥ 5 × 10⁻⁵ | M5 | Moderate |
| R3 | ≥ 1 × 10⁻⁴ | X1 | Strong |
| R4 | ≥ 1 × 10⁻³ | X10 | Severe |
| R5 | ≥ 2 × 10⁻³ | X20 | Extreme |

GOES flare classes follow `A < B < C < M < X`, each a factor of 10, indexed by mantissa (`M2.3` = 2.3 × 10⁻⁵ W/m²). R‑scale starts at M1.

### 5.3 S‑scale (solar radiation storm) — threshold on GOES ≥10 MeV proton flux

| Level | Flux (pfu @ ≥10 MeV) | Label |
|---|---|---|
| S1 | ≥ 10¹ | Minor |
| S2 | ≥ 10² | Moderate |
| S3 | ≥ 10³ | Strong |
| S4 | ≥ 10⁴ | Severe |
| S5 | ≥ 10⁵ | Extreme |

SEP event is declared when integral ≥10 MeV flux crosses 10 pfu and stays above for ≥3 consecutive 5‑min observations.

### 5.4 SWPC alert product codes (`product_id` in `alerts.json`)

Common codes the Day 1 ingestor will see and must classify:

| Code | Meaning | Drives |
|---|---|---|
| `WARK04`, `WARK05`, … | Geomagnetic K‑index watch (≥4, ≥5, …) | G‑scale forecast |
| `WATA50`, `WATA20` | A‑index watch | G‑scale forecast |
| `ALTK04`, `ALTK05`, … | Geomagnetic K‑index reached threshold (alert) | G‑scale observed |
| `SUMK04`, `SUMK05`, … | Geomagnetic K‑index summary | G‑scale post‑event |
| `WARPX1`, `WARPX10` | Proton flux watch (≥10 pfu, ≥10⁴ pfu) | S‑scale forecast |
| `ALTPX1`, `ALTPX10` | Proton flux alert | S‑scale observed |
| `ALTEF3` | Electron 2 MeV flux ≥1000 pfu | Internal‑charging risk |
| `WARSUDR05`, `SUMXM5`, `SUMX01` | X‑ray flare summaries | R‑scale post‑event |
| `RWARN` / `ALTXMF` | X‑ray flare alert (M/X class) | R‑scale observed |
| `WARSEC` | SEC ECA forecaster bulletin | General |
| `TIIA` | Type II radio sweep (CME signature) | Possible CME → G‑scale precursor |
| `TIVA` | Type IV radio sweep (CME signature) | Possible CME → G‑scale precursor |
| `CMEA` | Coronal mass ejection alert | G‑scale precursor |

Full code list lives in SWPC product documentation; the ingestor should pass `product_id` through verbatim into the event payload and let the arbiter classify.

---

## 6. Authentication, rate limits, ToS

- **No authentication.** No API key, no token, no `Authorization` header.
- **No published rate limit.** SWPC does not document a request budget for `services.swpc.noaa.gov`. Confirmed by inspecting `https://www.swpc.noaa.gov/content/data-access` and SWPC FAQs — neither mentions a limit. The service is public, taxpayer‑funded, and front‑ended by a CDN.
- **Operational courtesy:**
  - Send a descriptive `User-Agent`: `Spacesharks-MissionDesk/1.0 (+contact-email)`. NOAA explicitly logs UA strings.
  - Honour `Cache-Control` and `Last-Modified` (the CDN serves them).
  - Don't poll faster than the data update cadence. Polling `xrays-1-day.json` once per 60 s is fine; once per 5 s is abusive.
  - Back off exponentially on `5xx` and `429` (treat 429 defensively even though it's not documented).
- **If a 429 ever fires or the service blocks the IP:** contact `swpc.webmaster@noaa.gov`.

---

## 7. Python ingestion pattern

Day‑1‑copy‑and‑paste sketch. Polls Kp, GOES X‑ray, and alerts; emits records conforming to the sat‑agnostic Spacesharks event schema `{source, source_timestamp, ingest_timestamp, parser_version, payload}`.

```python
"""Spacesharks NOAA SWPC ingestor — Day 1 sketch.

Emits one event per record into `out`. Replace `out.append` with your real
event sink (Kafka, SQLite, parquet, whatever the Mission Desk is using).
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Iterable

import httpx  # pip install httpx

PARSER_VERSION = "swpc-ingestor/0.1.0"
USER_AGENT = "Spacesharks-MissionDesk/1.0 (+ops@spacesharks.example)"

ENDPOINTS = {
    "swpc.kp.3h":      "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json",
    "swpc.goes.xray":  "https://services.swpc.noaa.gov/json/goes/primary/xrays-1-day.json",
    "swpc.goes.proton":"https://services.swpc.noaa.gov/json/goes/primary/integral-protons-1-day.json",
    "swpc.alerts":     "https://services.swpc.noaa.gov/products/alerts.json",
    "swpc.scales":     "https://services.swpc.noaa.gov/products/noaa-scales.json",
}


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds")


def _extract_source_ts(source: str, record: dict | list) -> str | None:
    """Pull the per‑record SWPC timestamp out of the heterogeneous shapes."""
    if isinstance(record, dict):
        return record.get("time_tag") or record.get("issue_datetime") or record.get("DateStamp")
    return None  # list‑of‑lists products (solar wind) handled by the caller


def fetch(source: str, url: str, client: httpx.Client) -> Iterable[dict]:
    """Yield Spacesharks events for one SWPC endpoint."""
    r = client.get(url, headers={"User-Agent": USER_AGENT}, timeout=10.0)
    r.raise_for_status()
    data = r.json()
    ingest_ts = _now_iso()
    # alerts.json, kp, xrays, protons, solar_regions, ... are all list‑of‑dicts
    # noaa-scales.json is a single dict keyed by day offset
    records = data if isinstance(data, list) else [data]
    for rec in records:
        yield {
            "source": source,
            "source_timestamp": _extract_source_ts(source, rec),
            "ingest_timestamp": ingest_ts,
            "parser_version": PARSER_VERSION,
            "payload": rec,
            "provenance": {"url": url, "fetched_at": ingest_ts},
        }


def poll_once(out: list[dict]) -> None:
    with httpx.Client(http2=True) as client:
        for source, url in ENDPOINTS.items():
            try:
                out.extend(fetch(source, url, client))
            except (httpx.HTTPError, ValueError) as e:
                out.append({
                    "source": source, "source_timestamp": None,
                    "ingest_timestamp": _now_iso(),
                    "parser_version": PARSER_VERSION,
                    "payload": None,
                    "provenance": {"url": url, "error": repr(e)},
                })


if __name__ == "__main__":
    events: list[dict] = []
    while True:
        poll_once(events)
        # Drain `events` into the real sink here, then clear.
        print(f"{_now_iso()} ingested {len(events)} records")
        events.clear()
        time.sleep(60)
```

Notes for production hardening (Day 2+):
- Add `If-Modified-Since` from the previous `Last-Modified` per endpoint, treat 304 as no‑op.
- Dedupe by `(source, source_timestamp, payload.satellite, payload.energy)` for GOES; by `(source, issue_datetime, product_id, serial_number)` for alerts.
- Solar‑wind CSV‑style endpoints need a small wrapper that drops the header row and converts string fields to floats before emitting.
- Failover to `/json/goes/secondary/...` if primary `time_tag` is older than 10 min.

---

## 8. Failure modes

| Mode | What happens | Detection | Degradation |
|---|---|---|---|
| **NOAA CDN 5xx** | services.swpc.noaa.gov returns 502/503 (rare, ~minutes) | HTTP code | Exponential backoff 30 s → 5 min, keep last known good cached. Mark recommendations as `stale_upstream=true`. |
| **Stale `time_tag`** | Endpoint still 200‑OKs but data hasn't moved | `(now - time_tag) > 2× cadence` | Mark feed `stale`. For GOES, switch primary→secondary. |
| **Weekend / holiday gap** in solar regions | `solar_regions.json` is daily and can lag on US federal holidays | `observed_date` < today‑1 | Treat as low‑freshness; raise flare‑probability uncertainty in arbiter. |
| **Forecaster bulletin lag** in `alerts.json` | Issue gap of hours during off‑shift coverage | gap > 8 h with no alerts | Not a failure — alerts are event‑driven; document expected silence windows. |
| **GOES primary outage** (eclipse, anomaly) | `xrays-1-day.json` returns empty array or stale | empty list / stale `time_tag` | Auto‑failover to `goes/secondary/` |
| **CME‑driven NOAA‑internal outage** (rare but documented in past Halloween storms) | Both primary and secondary GOES degrade simultaneously; SWPC bulletins lag | Cross‑check ACE/DSCOVR solar wind shock; if NOAA degraded but DSCOVR shock present, set system into "blind" mode | Spacesharks arbiter should refuse to issue confident recommendations; surface "Sensor‑degraded — operator decision required". |
| **Electron contamination** of GOES short‑band X‑ray | `electron_contaminaton: true` | Field flag | Use long‑band 0.1–0.8 nm only for R‑scale; report short band with warning. |
| **HTTP redirect to https** | None observed — services.swpc.noaa.gov is HTTPS‑only | n/a | n/a |
| **JSON schema drift** (SWPC has changed field names in past — e.g. proton energy strings) | Pydantic / dataclass validation error | Schema validator | Quarantine record into `unparseable/` for human review; alert ops. |

Halloween‑storm precedent: during the Oct/Nov 2003 storms, SWPC's primary GOES SXI was saturated; secondary degraded; ACE was partially blinded by particles. **The lesson for Spacesharks: never let a single SWPC product be the only input gating an irreversible decision.** Always require ≥2 of {GOES X‑ray, GOES proton, Kp, solar wind, alerts.json} to agree before issuing a confidence‑weighted recommendation.

---

## 9. Provenance fields — Spacesharks contract

Every record emitted by the SWPC ingestor MUST carry, at minimum:

| Field | Source | Why |
|---|---|---|
| `source` | constant (`"swpc.goes.xray"`, etc. — see §7 `ENDPOINTS` keys) | Routing + arbiter weighting |
| `source_timestamp` | the SWPC record's own `time_tag` / `issue_datetime` / `DateStamp` | Truth time — what NOAA says happened |
| `ingest_timestamp` | wall clock when our poller persisted the row | Freshness budget calc |
| `parser_version` | constant string per release of the ingestor | Replayability |
| `payload` | raw SWPC record, **unmodified** | Re‑derivation, audit |
| `provenance.url` | the exact endpoint URL we hit | Reproducibility — operator can click through |
| `provenance.fetched_at` | HTTP fetch wall clock | Distinguish HTTP latency from queue latency |
| `provenance.http_last_modified` | `Last-Modified` response header (if present) | Cache freshness audit |
| `provenance.http_etag` | `ETag` response header (if present) | Cache freshness audit |
| `provenance.parser_warnings` | list, e.g. `["electron_contaminaton:true"]` | Surface upstream caveats to operator |

Downstream arbiter recommendations MUST cite at least one `source_timestamp` + `provenance.url` from the underlying ingest record. This is the audit chain that ties every Mission Desk recommendation back to a NOAA artefact a human can independently fetch.

---

## 10. References

- SWPC services root (live index): https://services.swpc.noaa.gov/
- SWPC public site: https://www.swpc.noaa.gov/
- NOAA space weather scales (G/R/S): https://www.swpc.noaa.gov/noaa-scales-explanation
- SWPC data access page: https://www.swpc.noaa.gov/content/data-access
- GOES‑R series instrument overview (XRS, SEISS): https://www.goes-r.gov/spacesegment/instruments.html
- GOES‑R XRS data product user guide: https://www.ngdc.noaa.gov/stp/satellite/goes-r.html
- SWPC product list: https://www.swpc.noaa.gov/products
- DSCOVR mission page (solar‑wind upstream): https://www.nesdis.noaa.gov/current-satellite-missions/currently-flying/dscovr-deep-space-climate-observatory
- yxz wiki conceptual coverage: `[[concepts/solar-cycle-25-leo-radiation]]`
- Spacesharks plan: `synthesis/spacesharks-mission-desk-hackathon-plan.md`

---

## Appendix A — Quick‑reference Day 1 implementation checklist

- [ ] Implement HTTP client with `User-Agent: Spacesharks-MissionDesk/1.0`
- [ ] Implement 5 Tier‑1 pollers (Kp, GOES X‑ray, GOES proton, alerts, solar wind plasma+mag) at the cadences in §4
- [ ] Implement the event schema from §9
- [ ] Implement primary→secondary GOES failover
- [ ] Implement `If-Modified-Since` / 304 short‑circuit
- [ ] Implement schema validation with quarantine on drift
- [ ] Implement R/S/G classification using §5.1–5.3 thresholds
- [ ] Wire `provenance.url` + `source_timestamp` into arbiter recommendation citations
- [ ] Add a watchdog that alerts if any Tier‑1 feed exceeds 2× its expected cadence
