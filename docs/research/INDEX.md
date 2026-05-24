# Spacesharks research index

Operational research notes used by the Mission Desk ingestors and arbiter.
Each note is self-contained and copy-paste-into-code ready.

## Tier 1 — real-time (≤ 5 min freshness)

- [NOAA SWPC API](noaa-swpc-api.md) — Kp / GOES X-ray / SEP flux / solar wind endpoints, JSON schemas, polling cadence, G/R/S alert taxonomy, Python ingest skeleton (ingested 2026-05-24)

## Tier 2 — hourly (≤ 1 h freshness)

- [Space-Track CDM API](space-track-cdm-api.md) — cdm_public vs cdm classes, auth + cookies, rate limits (30/min, 300/hr), python-spacetrack snippet, NASA CARA Pc thresholds, TraCSS migration seam (ingested 2026-05-24)

## Tier 3 — daily / per-event / quarterly (reference for post-MVP Phase 1)

- [FAA NOTAM API](faa-notam-api.md) — NOTAM Search + DINS + SWIM FNS access tiers, Q-line/E-line parsing, Starship IFT-9 (A1559/25) worked example, slip-state decision lookup (NOTAMC→scrub / NOTAMR→slip), TraCSS LCOLA seam, runnable DINS regex ingestor (ingested 2026-05-24)
- [FCC IBFS API](fcc-ibfs-api.md) — licensing.fcc.gov/myibfs/ + opendata.fcc.gov + ITU SNL surfaces, Schedule S → Schedule O/F transition (FCC 24-97 NPRM), EPFD decision lookup, recent rulings (Kuiper / Starlink Gen2 / Starlink V-E / AST SCS), BeautifulSoup + Socrata ingest variants (ingested 2026-05-24)

## Patterns

- [Small-Model Ensemble Arbiter](small-model-ensemble-arbiter.md) — three-role decomposition (classifier / risk scorer / action drafter), deterministic arbiter logic, confidence calibration (Brier, temperature scaling), abstain-on-disagreement, OpenRouter cost model, 40-line Python skeleton (ingested 2026-05-24)
- [Tiered Inference](tiered-inference.md) — cost-aware T1/T2/T3 model cascade with four explicit escalation triggers (low agreement / high-risk event / high-impact asset / threshold proximity); FrugalGPT / RouteLLM / Together MoA evidence; Nemotron Nano/Super/Ultra pricing table (May 2026); runnable Python `dispatch()` with `TIER_REGISTRY` config (ingested 2026-05-24)
- [Calibrated Confidence](calibrated-confidence.md) — three-class `answer / abstain / escalate` output schema; five calibration techniques (temperature scaling, Platt, verbalised, P(IK), conformal prediction); coverage–risk operating point per decision class; runnable Brier + reliability diagram + temperature-scaling Python; Day-1 bootstrap from NASA CARA + SWPC ground truth (ingested 2026-05-24)
- [Agentic Provenance](agentic-provenance.md) — four-layer trust schema (data / model / decision / system) with required field tables; W3C PROV-DM / C2PA v2.1 / NIST AI 600-1 / EU AI Act Article 50 / CycloneDX ML-BOM analogues; trace ↔ span ↔ event mapping to commercial observability; runnable `EvidenceStore` + `EventLog` + nightly re-hash verifier; 5-tuple reproducibility invariant (ingested 2026-05-24)

## Deferred (schema-conformant stubs only — see SCOPE.md non-goals)

- Celestrak orbital catalog ingest
- ITU spectrum coordination (BR IFIC API, paid SNS subscription) — partial coverage in [FCC IBFS API](fcc-ibfs-api.md) §11

---

# Local research source catalog (post-MVP roadmap)

> Catalog of `D:\` material that feeds the Spacesharks **post-MVP roadmap**. Each row lists the absolute path, what the asset actually is, and which `ROADMAP.md` phase it should feed. Nothing in this catalog is part of the MVP.

## How to use this section

1. Find the phase you are about to start in `../ROADMAP.md`.
2. Pull the rows tagged with that phase from the tables below.
3. Open the per-axis design note (`rf-ground-segment.md`, `thermal-and-mechanical.md`, etc.) for the actual integration plan.
4. If you add new local material, append a row here in the same format. Keep the path absolute — these are sources of truth, not copies.

---

## RF / beamforming / ground segment → Phase 1

| Path | What it is | Why it matters |
|---|---|---|
| `D:\Beamformer_RF\Thesis_0850193.pdf` | Sampras's MSc thesis | Primary write-up of the beamformer work; cite once for system-level claims. |
| `D:\Beamformer_RF\Hybrid X-band Phased Array Transmitter.pdf` | Conference/journal style paper | X-band TX architecture, gain/phase budget, calibration approach. |
| `D:\Beamformer_RF\Driver\TXBFIC_source.py` | F5288 TX BFIC driver | Real SPI register map, 5.6°/step phase shifter, ~30 dB gain range, 4×4 H/V dual-pol channels. |
| `D:\Beamformer_RF\Driver\RXBFIC.py` | F6212 RX BFIC driver | Mirror of TX side for receive chains. |
| `D:\Beamformer_RF\Driver\Yaskawa.py` | Robotic arm scan rig | Antenna pattern measurement automation — template for any in-lab calibration loop. |
| `D:\Beamformer_RF\Driver\roboticarm.py` | Robotic arm wrapper | Higher-level scan motion. |
| `D:\Beamformer_RF\Driver\NA.py` | Network analyzer driver | S-parameter capture path. |
| `D:\Beamformer_RF\Driver\regmap.txt` | F5288 register map dump | Authoritative reference for any reimplementation. |
| `D:\Beamformer_RF\f5288-20250227T011804Z-001\f5288\Document\F5288-Datasheet-v300 rev0.14.pdf` | F5288 datasheet | Electrical specs, link budget inputs. |
| `D:\Beamformer_RF\f5288-20250227T011804Z-001\f5288\Document\REN_F5268-F5288_MAH_20211123.pdf` | Vendor MAH | Module assembly notes; useful when modeling antenna-element variance. |
| `D:\Beamformer_RF\f5288-20250227T011804Z-001\f5288\Document\f5288_2x2_BVH.pdf` | 2×2 BVH layout | Element-spacing / mutual coupling reference. |
| `D:\Beamformer_RF\f5288-20250227T011804Z-001\f5288\Code\calibration.ipynb` | Calibration notebook | The actual calibration method — basis for "calibration drift" feature in Phase 1. |
| `D:\Beamformer_RF\f5288-20250227T011804Z-001\f5288\Code\antenna_plotter.ipynb` | Pattern visualisation | Useful as a reference output shape (azimuth/elevation cuts). |
| `D:\Beamformer_RF\f5288-20250227T011804Z-001\f5288\Measurement\` | Raw measurements (0601–0613) | Ground-truth dataset for any pass-quality model. |
| `D:\Beamformer_RF\f5288-20250227T011804Z-001\f5288\CORA-Z7\` | Zynq FPGA host | Hardware-in-the-loop host for the BFIC; bitstreams + Tcl. |
| `D:\Beamformer_RF\f6212-20250227T011807Z-001\f6212\Document\F6212_Datasheet.pdf` | F6212 RX datasheet | RX-chain budget inputs. |
| `D:\Beamformer_RF\f6212-20250227T011807Z-001\f6212\Analysis\array_factor.ipynb` | Array-factor analysis | Mathematical basis for beam shape vs. element failure. |
| `D:\Beamformer_RF\f6212-20250227T011807Z-001\f6212\Analysis\RX_plotter.ipynb` | RX pattern plotting | Inverse of the TX plotter. |

Design note: [`rf-ground-segment.md`](rf-ground-segment.md).

---

## Thermal / mechanical / spacecraft bus → Phase 2

| Path | What it is | Why it matters |
|---|---|---|
| `D:\career\ee\衛星機械系統\熱控設計.pdf` | Thermal control design notes | Primary reference for the thermal advisory model. |
| `D:\career\ee\衛星機械系統\06_衛星熱環境介紹 _Homework.pdf` | Spacecraft thermal-environment homework | Equations / boundary conditions to seed the model. |
| `D:\career\ee\衛星機械系統\Rosetta羅賽塔\20200319_羅賽塔.docx` | Sampras's Rosetta write-up | Internal teaching-grade summary; useful for tone. |
| `D:\career\ee\衛星機械系統\Rosetta羅賽塔\Rosetta.stl` | Rosetta CAD mesh | Visual aid for case-study page. |
| `D:\career\ee\衛星機械系統\Rosetta羅賽塔\reference\Glassmeieretal-2007.pdf` | RPC instrument overview | Citable source for instrument-level thermal/EM context. |
| `D:\career\ee\衛星機械系統\Rosetta羅賽塔\reference\Rosetta_Lander_Philae_Investigations.pdf` | Philae lander investigation | Primary source for the Phase 4 case study. |
| `D:\career\ee\衛星機械系統\satellite general survey\各國衛星整理\` | Multi-country satellite survey | Currently empty / placeholder — refill when expanding the lessons-learned corpus. |

Design note: [`thermal-and-mechanical.md`](thermal-and-mechanical.md).

---

## Signal processing / digital comms → Phase 3

| Path | What it is | Why it matters |
|---|---|---|
| `D:\career\ee\ADSP\ADSP1.pdf` – `ADSP4.pdf` | Adaptive signal processing course | Detection, estimation, adaptive filtering — basis for telemetry residual classifiers. |
| `D:\career\ee\ADSP\ADSP_Write1.pdf` | Course writeup | Worked examples to lift formulas from. |
| `D:\career\ee\ADSP\QuantumSignalProcessing.pdf` | QSP reference | Out of Phase 3 scope; tag for "long-horizon ideas". |
| `D:\career\ee\DCC資訊與數位通訊_李琳山\` | Digital comms course (Prof. Lee) | Coding/modulation theory; supports link-budget claims and demod features. |
| `D:\career\ee\ML\` | ML coursework | Reference only — not a substitute for the small models defined in `ARCHITECTURE.md`. |

Design note: [`signal-processing.md`](signal-processing.md).

---

## Lessons-learned seed → Phase 4

| Path | What it is | Why it matters |
|---|---|---|
| `D:\career\ee\衛星機械系統\Rosetta羅賽塔\reference\Rosetta_Lander_Philae_Investigations.pdf` | Philae anomaly investigations | Real, well-documented multi-cause failure — ideal first case. |
| `D:\career\ee\衛星機械系統\Rosetta羅賽塔\reference\Glassmeieretal-2007.pdf` | RPC instrument overview | Provides the instrument context behind the anomaly. |
| `D:\career\ee\衛星機械系統\Rosetta羅賽塔\reference\reference website.txt` | Curated web references | Use as link-rot-safe pointers; re-archive into Spacesharks's own log when ingested. |

Design note: [`case-studies-rosetta.md`](case-studies-rosetta.md).

---

## Material explicitly **out of scope**

These exist on `D:\` and were considered, but do not earn a roadmap slot today. Listed so future me does not re-evaluate them every quarter.

- `D:\career\ee\NTU-Courses\`, `D:\career\ee\NTUT_Course\`, `D:\career\ee\NTU_CompSci\` — general coursework; no satellite-specific yield.
- `D:\career\ee\Quantum Computing\` — interesting but not a near-term Spacesharks input.
- `D:\career\ee\ntu-thesis\` — undergrad ROI-detection thesis; unrelated domain.
- `D:\career\ee\LA\` — linear algebra notes; assumed prerequisite, not a source.

Move them up into a table above only when there is a concrete model or feature that would consume them.
