---
title: FCC IBFS operational API
type: research
tier: T3
status: ingested
ingested: 2026-05-24
sources: [https://licensing.fcc.gov/myibfs/, https://www.fcc.gov/space-bureau, https://www.fcc.gov/space, https://opendata.fcc.gov/, https://www.itu.int/en/ITU-R/space/snl/]
---

# FCC IBFS Operational API — Day 1 Ingestor Handbook

**Scope.** This document is the verbatim operational reference for the Spacesharks Mission Desk **Tier-3 spectrum-filing ingestor**. It tells an engineer what URL to GET, what filing type code to filter by, which Schedule S field to extract, when to back off, and what to record for provenance. Conceptual depth on *why* EPFD limits exist, how processing rounds work, what an API-CR-Notification pipeline means, and which call signs anchor which constellation lives in the yxz wiki — links at the bottom. **Do not re-derive theory here.** If you need to know why aggregate NGSO EPFD has a Resolution 76 overlay, read the wiki. If you need to know which URL to GET, read this.

**Tier-3 justification.** Spectrum filings publish on a **quarter-to-quarter** cadence, not real-time poll. A Part 25 license modification takes 6–24 months from filing to grant; an ITU API publication appears in the bi-weekly BR IFIC; the FCC Daily Digest is once-per-business-day. There is no operational reason to poll faster than every 24 h. This handbook is therefore graded **T3** — the ingestor runs on a slow cron, not a tight loop. Spacesharks' MVP (per `D:\DOT\spacesharks\docs\SCOPE.md`) defers spectrum entirely; this handbook is the reference for **post-MVP Phase 1** ground-segment + interference-attribution work.

**Decision verbs this serves.** Spacesharks uses IBFS data for two distinct Phase-4 decision verbs:
1. **Interference attribution** — match observed downlink degradation at a watched LEO receiver to a recently granted NGSO modification in the same band.
2. **Post-MVP spectrum monitoring** — for any orbital data center (ODC) mission with a ground-segment terminal, generate compliance-check briefs against the EPFD environment defined by neighbouring filings.

This handbook **pairs with** `D:\DOT\spacesharks\docs\research\faa-notam-api.md` (being written in parallel by a sibling subagent) for the joint interference-attribution + launch-context decision flow: a launch NOTAM + a fresh SAT-MOD on the same call sign is the canonical "neighbour just changed something" trigger.

---

## 1. Endpoint Catalog

Unlike Space-Track or NOAA SWPC, the FCC's satellite-filing surface is **not a single REST API**. It is a federation of public portals, bulk-data dumps, third-party mirrors, and upstream ITU services. The ingestor must speak multiple shapes.

| Surface | URL | Access tier | Freshness | Format | MVP/upgrade |
|---|---|---|---|---|---|
| **IBFS public portal** | `https://licensing.fcc.gov/myibfs/` | Free, no auth | Same business day | HTML / form-driven; PDF exhibits | MVP (primary) |
| **IBFS legacy redirect** | `https://apps.fcc.gov/ibfsweb/` | Free, no auth | Redirects to `licensing.fcc.gov/myibfs/` | HTML | Deprecated; preserve redirect-following |
| **FCC Open Data IBFS dataset** | `https://opendata.fcc.gov/International/International-Bureau-Filing-System-IBFS-/78n9-wprc` | Free, optional Socrata API token | Daily | CSV / JSON via Socrata | MVP (metadata) ⚠️ verify Space Bureau namespace post-2023 |
| **fcc.report mirror** | `https://fcc.report/IBFS/` | Free, no auth | ~24 h behind IBFS | HTML + per-filing-type RSS | MVP (event triggers) — **not canonical** |
| **FCC Daily Digest** | `https://www.fcc.gov/daily-releases` | Free, no auth | Daily M–F | HTML / text | MVP (release watcher) |
| **Federal Register** | `https://www.federalregister.gov/agencies/federal-communications-commission` | Free; documented REST API | Daily | JSON | MVP (NPRM / final rule watcher) |
| **ITU Space Network List** | `https://www.itu.int/en/ITU-R/space/snl/` | Free public lookup | Bi-weekly | HTML / PDF | MVP (non-US operator filings) |
| **ITU BR IFIC** | `https://www.itu.int/en/ITU-R/space/asreceived/Publication/AsReceived` | Free | Bi-weekly | PDF only | MVP (API / CR notices) ⚠️ PDF-only |
| **ITU SpaceExplorer / SNS** | `https://www.itu.int/pub/R-SOFT-SNS` | **Paid subscription** | Bi-weekly machine-readable | Database export | Upgrade tier |
| **ITU EPFD validation software** | `https://www.itu.int/epfdsupport/` | Free download | Static; revs at WRC cycles | Windows binary | MVP (compliance check) |
| **Legacy IBFS direct query** | `https://licensing.fcc.gov/cgi-bin/ws.exe/prod/ib/forms/reports/swr08b.hts` | Free, no auth | Same business day | HTML | Brittle; do not rely on past Day-1 |

**Operational consequence.** With *only* the free surfaces, Spacesharks can:
- Search filings by operator, call sign, file number, or filing type (IBFS portal + Open Data dataset)
- Pull Schedule S PDF exhibits (IBFS individual filing pages)
- Monitor new-filing RSS streams (fcc.report)
- Track Space Bureau orders + NPRMs (Federal Register + Daily Digest)
- Look up non-US operator filings (ITU SNL)
- Run a quantitative EPFD geometry check (ITU EPFD software, locally)

What requires the **paid** ITU SpaceExplorer / SNS subscription:
- Full machine-readable API/CR/Notification history across all administrations
- Complete coordination status for non-US operators with no FCC filing record
- Geo-specific upstream coordination data for cross-administration disputes

See §11 for full upgrade-path pricing posture (mostly opaque — flagged for live verification).

---

## 2. Authentication Flow

There is no auth flow for **read** operations. Public IBFS search, document download, fcc.report mirror access, Federal Register API, and ITU SNL all serve content over plain HTTP(S) GET with no credentials, no API key, no bearer token, no session cookie.

Two narrow exceptions:

1. **Socrata API token (optional, recommended).** The FCC Open Data portal serves the IBFS dataset (`78n9-wprc`) via Socrata. Anonymous access is rate-limited; a free Socrata account yields an API token that lifts the limit. Pass it as `X-App-Token: <token>` on every GET to `opendata.fcc.gov/resource/78n9-wprc.json`. Account creation: `https://opendata.fcc.gov/signup`.

2. **Filer access (out of scope for ingestor).** Submitting a new filing requires an FCC Registration Number (FRN) issued by the Commission Registration System (CORES) at `https://apps.fcc.gov/cores/`. **Spacesharks does not file** — it reads — so this flow is documented only for disambiguation.

⚠️ verify against live API — confirm that `opendata.fcc.gov/International/...` is still the active path under the Space Bureau's post-2023 reorganization, and that the `78n9-wprc` dataset is still the canonical IBFS resource (the FCC has reorganized dataset namespaces in past portal migrations).

---

## 3. Filing Types & Forms

Every satellite filing in IBFS carries a **file type prefix** (e.g. `SAT-LOA-`, `SES-LIC-`) and is built on **FCC Form 312** (Main Form) plus a technical schedule. The ingestor must recognize the prefix to route the filing to the correct decoder.

| Prefix | Name | Rule part | License term | Processing time | Notes |
|---|---|---|---|---|---|
| **SAT-LOA** | Launch and Operate Application (new) | Part 25 | 15 yr standard / 6 yr small sat | 6–9 mo uncontested GSO; 12–24+ mo NGSO processing round | Form 312 + Schedule S |
| **SAT-MOD** | Modification of space station authorization | Part 25 | Inherits parent | 6–18 mo | **Top interference-attribution signal** — neighbour just changed something |
| **SAT-AMD** | Amended application (within processing round) | Part 25 | n/a (pre-grant) | Bound to round | May alter EPFD commitment |
| **SAT-STA** | Special Temporary Authority | Part 25 | ≤ 180 d | Days–weeks | Test / demo phase |
| **SAT-PPL** | Pioneer Preference Petition | Part 25 | n/a | Variable | Rare; tracks novel-tech petitions |
| **SAT-T/C** | Transfer of Control | Part 25 | Inherits parent | Months | Ownership change; useful for entity tracking |
| **SES-LIC** | Earth Station License (new) | Part 25 | 15 yr | 3–6 mo | Ground terminal authorization |
| **SES-MOD** | Earth Station Modification | Part 25 | Inherits parent | Months | Gateway / VSAT changes |
| **SES-REG** | Earth Station Registration | Part 25 | Blanket | Days | Consumer terminals under blanket license |
| **ELS / 1903-EX** | Experimental STA | Part 5 | 2–5 yr | 3–6 mo (file ≥ 3 mo before launch) | No commercial service permitted |

Part 97 amateur space station licenses are handled in the FCC's Universal Licensing System (ULS), **not** IBFS. They are out of Spacesharks scope and documented here only for disambiguation — an operator search that returns a Part 97 record should be filtered out by the ingestor.

**Field-name caveat.** The FCC's *Space Modernization for the 21st Century* NPRM (FCC 24-97, Dec 2024) proposes replacing **Schedule S** with **Schedule O** (orbital) + **Schedule F** (frequency) and expediting initial processing to under 6 months for uncontested GSO. Final rules were not adopted as of the ingest date. The ingestor MUST abstract Schedule-S parsing behind a `SpectrumFilingSource` interface so the schema mutation is a one-seam swap when the new rule lands. See §4 for the schema-abstraction posture.

For full Part 25 license-type semantics, term lengths, and rule-section anchors, read `D:\DOT\yxz\wiki\sources\fcc-part-25-2024.md` rather than duplicating it here.

---

## 4. Schedule S Data Shape

**[[concepts/schedule-s]]** (`D:\DOT\yxz\wiki\concepts\schedule-s.md`) is the technical annex to Form 312. It is **the** structured source for constellation geometry and link-budget envelope. The Schedule S exhibit is filed as a **PDF attachment** to each individual IBFS record — there is no native JSON / XML export from the public portal. Tabular structured data (orbital parameters, frequency table, EIRP density) lives inside the PDF tables and must be parsed.

**⚠️ Verification gap.** The yxz research team noted that the canonical Schedule S instruction PDF at `enterpriseefiling.fcc.gov` returned **HTTP 403** when attempted from a public IP during ingest. The ingestor MUST tolerate this and fall back to fetching individual exhibit PDFs from `fcc.report` mirrors when the canonical FCC mirror is blocked. Do not silently retry the same URL.

A real-world reference Schedule S example — Flock 1 (Planet Labs) — is browsable at `fcc.report` per the yxz research; do not republish the PDF contents here.

### 4.1 Schedule S fields the ingestor must extract

| Schedule S section | Field | Use |
|---|---|---|
| 1 Orbit type | GSO / NGSO | Routes to EPFD analysis if NGSO |
| 2 Network name | string (e.g. `STARLINK-GEN2`) | Joins to ITU SNS record |
| 3 Orbital parameters | altitude, inclination, RAAN, eccentricity, mean anomaly, n_planes, sats_per_plane | Constellation geometry |
| 4 Spacecraft | mass BOL, fuel mass, deployed area | Debris-casualty input |
| 5 Frequency bands | uplink/downlink MHz ranges, channel BW | Co-band search key |
| 5 EIRP density | dBW/4 kHz (< 15 GHz) or dBW/MHz (≥ 15 GHz) | EPFD lookup driver |
| 5 Total EIRP per beam | dBW | Link-budget envelope |
| 6 Antenna pattern | gain envelope, off-axis gain, PFD at surface | Off-axis interference geometry |
| 7 EPFD commitment | declaration + sim output ref | Compliance status |
| 8 Call sign | string (assigned at grant) | Cross-ref to ITU SNS Notification |

### 4.2 Synthesized normalized JSON shape (Spacesharks event schema)

The ingestor emits one canonical record per filing, conforming to the Spacesharks event schema. **This shape is synthetic for documentation; do not assume any specific filing exposes every field.**

```json
{
  "schema": "spacesharks.event.spectrum_filing.v1",
  "source": "fcc.ibfs",
  "file_number": "SAT-MOD-20221206-00193",
  "call_sign": "S3128",
  "operator": "Space Exploration Holdings, LLC",
  "filing_type": "SAT-MOD",
  "rule_part": "Part 25",
  "schedule_version": "S",
  "network_name": "STARLINK-GEN2",
  "orbit_type": "NGSO",
  "orbits": [
    {"altitude_km": 525, "inclination_deg": 53.0, "n_planes": 28, "sats_per_plane": 60, "raan_deg": null}
  ],
  "bands": [
    {"band": "Ku", "uplink_mhz": [14000, 14500], "downlink_mhz": [10700, 12700]},
    {"band": "Ka", "uplink_mhz": [27500, 30000], "downlink_mhz": [17700, 19700]}
  ],
  "eirp_density_dbw_per_mhz": -38.0,
  "max_eirp_per_beam_dbw": 4.0,
  "antenna_patterns": ["Exhibit A — antenna gain envelope"],
  "epfd_compliant": true,
  "epfd_compliance_doc": "Exhibit B — EPFD sim output",
  "status": "filed",
  "filed_date": "2022-12-06",
  "decision_date": null,
  "decision_doc": null,
  "raw_pdf_url": "https://fcc.report/IBFS/SAT-MOD-20221206-00193/...",
  "ingested_at": "2026-05-24T10:15:00Z"
}
```

The `status` enum is: `filed | accepted | granted | partial | modified | dismissed | withdrawn`. The `schedule_version` enum is: `S | O+F` (to absorb the FCC 24-97 NPRM transition).

⚠️ **Synthetic data warning.** The example above mixes Starlink Gen2 orbital parameters (verifiable in `D:\DOT\yxz\wiki\sources\fcc-starlink-gen2-kuiper-rulings-2022-2024.md`) with placeholder EIRP / EPFD values. The Spacesharks ingestor must clearly label any record where Schedule S extraction failed or returned partial data — never silently default missing fields to plausible-looking numbers.

### 4.3 The Schedule O / Schedule F transition

When FCC 24-97 final rules adopt:
- `schedule_version` flips from `"S"` to `"O+F"`
- Orbital fields move to a separate Schedule O exhibit; frequency fields to Schedule F
- Earth-station applicants can cross-reference Schedule O without re-declaring orbital data
- The ingestor's `SpectrumFilingSource` interface is unchanged; the **concrete parser** swaps at the boundary

Do not bake Schedule-S-specific field names into business logic. Map to the canonical event schema at the ingestor boundary so a future `ScheduleOFSource` swaps in at one seam.

---

## 5. EPFD Constraints — Decision Lookup

The ingestor does not *compute* EPFD — that requires the ITU validation software in §1 and a time-domain simulation over ≥ 10 days. What the ingestor *does* is provide the lookup table that lets the arbiter decide whether a new filing is in an interference-relevant band for a watched receiver.

Full conceptual treatment lives at `D:\DOT\yxz\wiki\concepts\epfd-equivalent-power-flux-density.md` and `D:\DOT\yxz\wiki\sources\itu-radio-regulations-article-22-2023.md`. This is the operational lookup only.

### 5.1 EPFD limit table (illustrative — verify against current RR text)

| ITU RR table | Direction | Band | Limit |
|---|---|---|---|
| 22-1A | Downlink (EPFD↓) | 10.7–12.75 GHz Ku FSS/BSS | −160 to −175 dBW/m²/40 kHz (elevation-dependent) |
| 22-1E | Downlink (EPFD↓) | 17.7–19.7 GHz Ka FSS | −164 to −175 dBW/m²/MHz |
| 22-2 | Uplink (EPFD↑) | 27.5–30 GHz Ka uplink | −170 to −175 dBW/m²/MHz |
| Res. 76 Tbl 1A–1D | Aggregate (multi-NGSO) | Ku / Ka shared | Per WRC-23 update |

⚠️ The exact dBW values above are flagged as **illustrative** in the yxz research (`D:\DOT\yxz\wiki\sources\itu-radio-regulations-article-22-2023.md` §"Article 22 EPFD Limit Tables"). Real Article 22 limits are elevation-angle and sub-band dependent and must be verified against the current ITU Radio Regulations text. The ingestor MUST NOT make hard pass/fail decisions on these placeholder values — use them only to seed a "this band is EPFD-regulated; flag for compliance check" Boolean.

### 5.2 How the arbiter uses this lookup

When the ingestor emits a new SAT-MOD event with a `bands[].downlink_mhz` that overlaps a watched operator's downlink, the arbiter:

1. Checks whether the modifier's band is on the EPFD limit table (Ku / Ka / V).
2. If yes, scores **interference probability** as a function of EPFD-margin headroom (computed externally by the ITU validation software, cached as a per-(band, altitude, inclination) lookup).
3. If the modifier's filing carries a `epfd_compliant: true` and a recent `epfd_compliance_doc`, attribute lower interference probability.
4. Generates a compliance-check brief for any ODC mission planning new ground-segment deployments in the affected band.

The full attribution flow is documented in `D:\DOT\yxz\wiki\synthesis\fcc-ibfs-filings-coordination.md` §4 ("What the Agent Can Do with Public Data Only").

---

## 6. Refresh Cadence

Spectrum filings are a **slow-moving signal**. The ingestor's cron schedule budget should never exceed ~500 GETs per month total across all surfaces.

| Mode | Surface | Cadence | Per-month budget |
|---|---|---|---|
| **Daily** | FCC Daily Digest (`fcc.gov/daily-releases`) | Once per business day | ~22 GETs |
| **Daily** | fcc.report SAT / SES RSS feed | Once per business day | ~22 GETs |
| **Per-launch** | IBFS filing record for launching operator | On FAA NOTAM trigger (see `D:\DOT\spacesharks\docs\research\faa-notam-api.md`) | Variable — typically 10–30/month |
| **Weekly** | Federal Register FCC index (Part 25 / Space Bureau NPRM / final rule) | Weekly | ~4 GETs |
| **Bi-weekly** | ITU BR IFIC index page | Bi-weekly (matches IFIC publication) | 2 GETs |
| **Quarterly** | ITU SNL Special Section snapshot | Quarterly | 4 GETs |
| **Monthly** | FCC Open Data IBFS dataset full refresh | Monthly | 1 GET (paginated; ~50 pages) |

**Total Day-1 budget: ~100 GETs / month** plus per-launch bursts. Well under any conceivable rate cap.

### 6.1 Rate limit posture

The FCC does not publish a documented rate limit for `licensing.fcc.gov/myibfs/` or `opendata.fcc.gov`. Operational courtesy:
- Send a descriptive `User-Agent`: `Spacesharks-MissionDesk/1.0 (+contact-email)`.
- Honour `Cache-Control` and `Last-Modified`.
- Don't poll faster than the underlying update cadence (IBFS posts new releases once per business day; polling more than every 4 h adds no signal).
- Back off exponentially on `5xx` and `429`.

⚠️ verify against live API — the actual rate-cap behaviour of `licensing.fcc.gov` is unconfirmed. The yxz research noted that deep filing-pages occasionally **time out** under load; treat this as transient and retry with jitter rather than escalating.

---

## 7. Python Ingest Snippets

Two variants. **Variant A** is the Day-1 MVP — `requests`-based HTML scrape of the IBFS public search page for a known call sign. It is brittle by design; the FCC has revised the IBFS HTML template multiple times. **Variant B** is the upgrade path — the FCC Open Data Socrata API, which is structurally stable but covers metadata only (not Schedule S contents).

### 7.1 Variant A — MVP HTML scrape (≤ 50 lines)

```python
"""Spacesharks Day-1 IBFS ingestor — MVP HTML scrape.

Fetches the IBFS search-results page for a known operator/call-sign,
extracts the filing list, and emits Spacesharks events. Brittle to
HTML template drift — wrap calls in template-version assertions.
"""
import os
import re
from datetime import datetime, timezone
from typing import Iterable

import httpx
from bs4 import BeautifulSoup  # pip install beautifulsoup4

USER_AGENT = "Spacesharks-MissionDesk/1.0 (+ops@spacesharks.example)"
IBFS_SEARCH = "https://licensing.fcc.gov/myibfs/forwardtopublictabaction.do"

def fetch_filings_for_call_sign(call_sign: str) -> Iterable[dict]:
    """Yield Spacesharks spectrum_filing events for one call sign."""
    params = {"call_sign": call_sign, "tab": "satellite"}
    r = httpx.get(IBFS_SEARCH, params=params,
                  headers={"User-Agent": USER_AGENT}, timeout=30,
                  follow_redirects=True)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    # ⚠️ FCC has migrated this template at least twice (2019, 2023).
    # Pin the parse to a wrapper that asserts the table-id we expect.
    table = soup.find("table", id="filing_list_table")
    if table is None:
        raise RuntimeError("IBFS template drift — filing_list_table not found")
    rows = table.find_all("tr")[1:]  # skip header
    ingest_ts = datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
    for row in rows:
        cells = [c.get_text(strip=True) for c in row.find_all("td")]
        if len(cells) < 5:
            continue
        file_no, filing_type, applicant, filed_date, status = cells[:5]
        yield {
            "schema": "spacesharks.event.spectrum_filing.v1",
            "source": "fcc.ibfs",
            "file_number": file_no,
            "call_sign": call_sign,
            "operator": applicant,
            "filing_type": filing_type,
            "status": status.lower(),
            "filed_date": filed_date,
            "raw_pdf_url": None,  # follow-up fetch on individual filing page
            "ingested_at": ingest_ts,
            "raw_payload_sha256": None,  # compute on the row HTML
        }

if __name__ == "__main__":
    # Starlink Gen2 modification — yxz cites SAT-MOD-20221206-00193 etc.
    for ev in fetch_filings_for_call_sign(os.environ.get("CALL_SIGN", "S3128")):
        print(ev)
```

**Honest caveats for Variant A:**
- The form parameters (`call_sign`, `tab`) and table id (`filing_list_table`) are **guessed** from the public IBFS search UI behaviour and ⚠️ MUST be verified against the live form via a single browser inspection session before relying on them.
- The IBFS HTML template has drifted on past major releases (2019, 2023). Pin the parser to a single template version and assert; quarantine to `unparseable/` on drift.
- This variant covers metadata only. To pull Schedule S contents, follow `raw_pdf_url` and run a PDF parser — out of scope for Day-1.
- For a constellation-wide watchlist, run this once per business day on a fixed list of call signs (S3128, S3155, S2984, S3036, etc.).

### 7.2 Variant B — Upgrade: FCC Open Data Socrata API

```python
"""Spacesharks Day-2 IBFS ingestor — Socrata Open Data.

Uses the FCC Open Data IBFS dataset (78n9-wprc) via the Socrata API.
Structurally stable; covers metadata only (no Schedule S contents).
"""
import os
from typing import Iterable

import httpx

DATASET = "78n9-wprc"
BASE = f"https://opendata.fcc.gov/resource/{DATASET}.json"
APP_TOKEN = os.environ.get("FCC_SOCRATA_TOKEN")  # optional but recommended

def fetch_recent_sat_filings(days_back: int = 30, limit: int = 1000) -> Iterable[dict]:
    """Yield IBFS records filed in the last N days."""
    # ⚠️ verify column names against live dataset — Socrata field names
    # for the IBFS dataset have not been confirmed in the yxz research.
    # Expected columns (label clearly as 'verify'):
    #   file_number, call_sign, applicant_name, filing_type,
    #   status, date_filed, date_granted
    params = {
        "$where": f"date_filed > '{_iso_n_days_ago(days_back)}'",
        "$limit": limit,
        "$order": "date_filed DESC",
    }
    headers = {"User-Agent": "Spacesharks-MissionDesk/1.0"}
    if APP_TOKEN:
        headers["X-App-Token"] = APP_TOKEN
    r = httpx.get(BASE, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    for row in r.json():
        yield {
            "schema": "spacesharks.event.spectrum_filing.v1",
            "source": "fcc.opendata.ibfs",
            "file_number": row.get("file_number"),       # ⚠️ verify
            "call_sign": row.get("call_sign"),           # ⚠️ verify
            "operator": row.get("applicant_name"),       # ⚠️ verify
            "filing_type": row.get("filing_type"),       # ⚠️ verify
            "status": (row.get("status") or "").lower(), # ⚠️ verify
            "filed_date": row.get("date_filed"),         # ⚠️ verify
            "decision_date": row.get("date_granted"),    # ⚠️ verify
        }

def _iso_n_days_ago(n: int) -> str:
    from datetime import datetime, timedelta, timezone
    return (datetime.now(tz=timezone.utc) - timedelta(days=n)).strftime("%Y-%m-%dT%H:%M:%S")
```

**Variant B is more robust** than Variant A for **metadata** (Socrata is a stable contract). It is still **insufficient** for Schedule S contents — those remain PDF-only on individual IBFS records. The full pipeline is: Variant B for metadata + filing-list discovery, Variant A or a PDF parser for Schedule S exhibit details.

---

## 8. Recent Rulings to Watch

The ingestor should pre-load a watchlist of call signs anchored to the rulings below. These constellations dominate the Ku / Ka / V interference environment over the US and are the first lookup targets when a downlink anomaly is observed at a watched LEO receiver. Full background in `D:\DOT\yxz\wiki\sources\fcc-starlink-gen2-kuiper-rulings-2022-2024.md`.

| Operator | File / Doc | Decision date | Authorized | Spacesharks relevance |
|---|---|---|---|---|
| **Amazon Kuiper** | SAT-LOA-20190704-00057 / FCC 20-102 | 2020-07-30 | 3,236 sats Ka-band (later 3,232 after SAT-MOD) | Baseline Ka-band NGSO interference source |
| **SpaceX Starlink Gen2** | FCC 22-91 | 2022-12-01 | 7,500 sats Ku/Ka (partial grant; ~30k requested) | Dominant Ku/Ka co-frequency source |
| **OneWeb** | DA-23-362 (expedited partial) | 2022-09 | ~648 + Gen2 pending | Ku-band incumbent at ~1,200 km |
| **SpaceX Starlink Gen2 V/E-band** | DA-24-1193 | 2024-11-26 | V (37.5–42 / 47.2–51.4 GHz) and E-band at 340–360 km | New V/E-band interference class |
| **AST SpaceMobile SCS** | DA-24-756 | 2024 | 248 sats, 700 MHz / 850 MHz cellular | Novel cellular-band LEO interference class |
| **Kuiper modification** | DA-24-224 | 2024-03-08 | Revised orbital shells | Schedule-S delta — geometry change |

**For interference attribution**: when a watched LEO downlink degrades, the ingestor's first action is to pull the most recent SAT-MOD or SAT-AMD filings by Starlink, Kuiper, OneWeb, and AST SpaceMobile in the affected band. The decision-doc number (`FCC 22-91`, `DA-24-1193`, etc.) anchors the rule lineage.

---

## 9. Failure Modes and Degradation

| Failure | Symptom | Strategy |
|---|---|---|
| **IBFS HTML template drift** | Variant A scraper raises `RuntimeError("template drift")` | Quarantine row to `unparseable/`; alert ops; fall back to Variant B (Socrata) for metadata while ops fixes the parser. |
| **FCC Daily Digest gap on US federal holidays** | No new release for ≥ 48 h | Expected; not a failure. Resume on next business day. |
| **Schedule S PDF returns HTTP 403** | Canonical FCC mirror blocks the IP (yxz research observed this on `enterpriseefiling.fcc.gov`) | Retry via `fcc.report` mirror; if both fail, mark filing as `epfd_compliance_doc: "fetch_blocked"` and emit a degraded event. Do **not** retry the same canonical URL in a tight loop. |
| **Call-sign reuse on modified LOA** | Two filings carry the same call sign with different `file_number` | Expected — modifications preserve call sign. Use `file_number` as primary key; treat call sign as group-by attribute. |
| **ITU SNL JSON not available** | ITU returns PDF Special Sections only | Expected — there is no documented machine-readable SNL public API. Capture PDF; emit metadata-only event; flag `pdf_only: true`. |
| **fcc.report mirror staleness** | Mirror lags IBFS by > 48 h | Confirm against canonical IBFS portal; if both stale, the FCC is degraded — emit `source_degraded` event and pause discovery cron. |
| **Federal Register API rate** | 429 on rapid pagination | Documented limit; back off 60 s, 120 s, 240 s. Federal Register API is stable. |
| **Socrata dataset namespace migration** | `78n9-wprc` returns 404 | The FCC has migrated dataset paths in past portal revisions. Maintain a `DATASET_CANDIDATES` list; alert if the primary 404s. |
| **PDF parse failure on Schedule S** | Table extraction returns empty `orbits[]` | Emit a metadata-only event with `orbits: null` and `parse_status: "schedule_s_unparsed"`; do **not** fabricate orbital params. |
| **NPRM-driven schema migration mid-flight** | FCC 24-97 final rule adopts; new filings carry Schedule O+F | The `SpectrumFilingSource` interface is unchanged; swap concrete parser. Old filings remain Schedule S. Tag `schedule_version` per filing. |

**Degradation principle.** The spacesharks Mission Desk should *never* go silent because the FCC portal is misbehaving. If the IBFS ingestor fails, emit a `spacesharks.event.ingestor.degraded` record so the operator brief shows "spectrum-filing data stale since {ts}" rather than displaying an empty interference panel. This mirrors the CDM ingestor's degradation contract (see `D:\DOT\spacesharks\docs\research\space-track-cdm-api.md` §9).

---

## 10. Provenance Fields the Ingestor MUST Record

Every Spacesharks event derived from an FCC IBFS or ITU SNL filing must persist these fields so a recommendation can be traced back to its source filing.

| Field | Source | Why |
|---|---|---|
| `file_number` | IBFS file number (e.g. `SAT-MOD-20221206-00193`) | Primary key for the filing at IBFS |
| `call_sign` | Schedule S §8 (assigned post-grant) | Group-by attribute for an operator's holdings |
| `operator` | Form 312 Main Form applicant name | Disambiguates filings under entity name changes |
| `filed_date` | IBFS filing timestamp | When the operator submitted |
| `decision_date` | Grant order release date (or `null` if pending) | When the FCC ruled |
| `decision_doc` | FCC / DA document number (`FCC 22-91`, `DA-24-1193`, ...) | Anchors the rule lineage |
| `schedule_s_url` | Direct URL to the Schedule S PDF exhibit on the IBFS record | Reproducibility — operator can click through |
| `schedule_version` | `"S"` or `"O+F"` | Absorbs the FCC 24-97 NPRM transition |
| `ingest_at` | Local clock when Spacesharks pulled it | Freshness budget calculation |
| `source` | constant: `"fcc.ibfs"` / `"fcc.opendata.ibfs"` / `"fcc.report"` / `"itu.snl"` / `"fcc.daily_digest"` | Disambiguates surface — Variant A vs B vs mirror |
| `raw_payload_sha256` | SHA-256 of the row HTML / JSON / PDF bytes | Tamper-evidence; lets us prove what we ingested |
| `parser_version` | constant per release of the ingestor | Replayability |
| `parse_status` | `"complete" \| "metadata_only" \| "schedule_s_unparsed" \| "fetch_blocked"` | Surface upstream caveats to operator |

The first eight are non-negotiable for the Day-1 build. The last four are recommended for hackathon-grade auditability.

Downstream arbiter recommendations MUST cite at least one `file_number` + `schedule_s_url` (or equivalent fallback URL) from the underlying ingest record. This is the audit chain that ties every interference-attribution claim back to an FCC artefact a human can independently fetch.

---

## 11. Upgrade Path (brief)

When the MVP is validated and we need machine-readable cross-administration coordination data, the paid surfaces are:

- **ITU SpaceExplorer / SNS subscription** (`https://www.itu.int/pub/R-SOFT-SNS`) — full machine-readable Space Network System database; required for complete API/CR/Notification history across all administrations, not just the US. Subscription-based; **pricing not public**. ⚠️ verify pricing — the yxz research hit the same wall and could not confirm tiered pricing without an ITU account.
- **FCC Daily Digest commercial aggregators** — third-party services (TR Daily, Communications Daily) reformat the Daily Digest with structured tagging and email alerts. Useful for monitored-keyword alerting; not a substitute for the canonical FCC source. Pricing not public.
- **Commercial spectrum-coordination advisories** — NSR (Northern Sky Research), SpaceTec Partners, and Quilty Analytics publish market intelligence on satellite-spectrum filings, processing-round outcomes, and ITU coordination disputes. The yxz synthesis (`D:\DOT\yxz\wiki\synthesis\fcc-ibfs-filings-coordination.md` §4.2) cites NSR and SpaceTec by name as the standard commercial layer. **Pricing not public; geo-specific.**
- **Geo-specific national filings** — for non-US LEO operators (e.g. Chinese GW / Guowang, EU IRIS², Indian Bharti / OneWeb-India), each administration runs its own spectrum-coordination filing portal. None has a documented machine-readable public API; access typically requires local counsel + paid intermediaries.

Full provider comparison and the rationale for *not* paying for ITU SNS in the hackathon scope lives in `D:\DOT\yxz\wiki\synthesis\fcc-ibfs-filings-coordination.md` §4.2. **Do not duplicate that depth here** — the Day-1 ingestor only needs to know that a `SpectrumFilingSource` abstraction will be needed when the upgrade hits.

---

## 12. yxz Wiki Cross-References

Absolute paths. Read these for conceptual depth — do not re-derive any of this content in Spacesharks code.

- `D:\DOT\yxz\wiki\synthesis\fcc-ibfs-filings-coordination.md` — **read this when** you need the full IBFS → ITU pipeline narrative, the MVP recipe, and the integration map to NemoClaw / Hermes / Firefly.
- `D:\DOT\yxz\wiki\sources\fcc-ibfs-portal-2023.md` — **read this when** you need the IBFS portal mechanics, file-type code list, and the official-vs-mirror surface map.
- `D:\DOT\yxz\wiki\sources\fcc-space-bureau-2023.md` — **read this when** you need to understand why the 2023 reorganization split Space Bureau from Office of International Affairs and what each handles.
- `D:\DOT\yxz\wiki\sources\fcc-part-25-2024.md` — **read this when** you need full Part 25 license-type semantics, term lengths, processing timelines, and Part 25 vs Part 5 decision rules.
- `D:\DOT\yxz\wiki\sources\itu-radio-regulations-article-22-2023.md` — **read this when** you need the Article 22 EPFD tables, Resolution 76 aggregate limits, and the ITU coordination pipeline anchored in WRC-23.
- `D:\DOT\yxz\wiki\sources\fcc-starlink-gen2-kuiper-rulings-2022-2024.md` — **read this when** you need the operator-specific call signs, altitudes, and grant orders that anchor the interference-attribution watchlist.
- `D:\DOT\yxz\wiki\concepts\schedule-s.md` — **read this when** you need to know which Schedule S section to extract for which downstream task (geometry, frequency, EIRP, antenna pattern).
- `D:\DOT\yxz\wiki\concepts\epfd-equivalent-power-flux-density.md` — **read this when** you need the EPFD mathematical definition, time-domain simulation context, and FCC § 25.146 codification.
- `D:\DOT\yxz\wiki\concepts\processing-round.md` — **read this when** you need to understand why a SAT-MOD might be stalled in a 2020 processing round and which operators are co-batched.
- `D:\DOT\yxz\wiki\concepts\ngso-gso-coordination.md` — **read this when** you need to distinguish FCC grant date from ITU Notification date and understand who has priority in a coordination dispute.

---

## 13. Items Flagged for Live-API Verification

When the team gets time on a live FCC / ITU surface, verify in one session:

1. Whether `licensing.fcc.gov/myibfs/` exposes a documented machine-readable export (CSV / JSON / XML) for satellite filings beyond the Open Data Socrata dataset. The yxz research saw FCC.gov deep filing pages time out and could not confirm a machine-readable export path direct from the portal.
2. Exact ITU Space Network List (SNL) public API surface. The current `itu.int/en/ITU-R/space/snl/` surface returns HTML lookup + PDF Special Sections; whether a JSON or CSV download exists for non-subscribers is unconfirmed.
3. Schedule S instruction PDF content from `enterpriseefiling.fcc.gov`. The yxz research hit **HTTP 403** on the canonical instruction PDF. Confirm whether this is geo-blocked, IP-blocked, or universally inaccessible; identify the canonical alternative URL.
4. Real-time vs day-stale FCC Daily Digest publishing window. The Daily Digest is documented as M–F daily but the exact UTC publish time is not verified — confirm whether 1×/day polling at 02:00 UTC catches that day's release.
5. Whether `opendata.fcc.gov` has a Space Bureau-specific dataset namespace post-2023 reorganization. The dataset id `78n9-wprc` is documented in the yxz `fcc-ibfs-portal-2023` source but its persistence under the new bureau structure is unverified.
6. Whether EPFD compliance simulation reports submitted via `itu.int/epfdsupport/` are downloadable for third parties under Article 22 transparency. The yxz research notes the ITU EPFD validation software is freely downloadable for *running* simulations; whether *other operators' submitted compliance evidence* is publicly retrievable is unconfirmed.
7. Whether `fcc.report` RSS feeds at `fcc.report/IBFS/Filing-List/SAT` and `/SES` carry stable XML and survive HTML template revisions on the upstream IBFS portal. The mirror has been described as ~24 h lag; confirm whether it can be relied on as a primary discovery surface during a Spacesharks 24 h demo window.
8. Whether SAT-AMD and SAT-MOD filings carry a distinguishable "what changed" delta in the public record, or whether the only way to compute the delta is by diffing the new Schedule S PDF against the prior-grant Schedule S PDF.
9. Whether the FCC's `licensing.fcc.gov/cgi-bin/ws.exe/prod/ib/forms/reports/swr08b.hts` legacy direct-query endpoint is still functional and whether it survives the post-2023 reorganization. Documented but flagged as brittle by the yxz research.

Each flagged item appears inline above with the `⚠️ verify against live API` or equivalent tag.

---

## Cross-handbook reference

This handbook pairs with:
- `D:\DOT\spacesharks\docs\research\faa-notam-api.md` — launch-context decision flow; a launch NOTAM plus a fresh SAT-MOD on the same operator's call sign is the canonical "neighbour just changed something" interference-attribution trigger.
- `D:\DOT\spacesharks\docs\research\space-track-cdm-api.md` — conjunction data substrate; same provenance / abstraction posture (`ConjunctionDataSource` ↔ `SpectrumFilingSource`).
- `D:\DOT\spacesharks\docs\research\noaa-swpc-api.md` — Tier-1 real-time signal contrast; IBFS is Tier-3 quarterly, NOAA is Tier-1 ≤5 min.
