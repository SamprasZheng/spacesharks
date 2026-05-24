# Roadmap (post-MVP)

> **Read this only after the MVP in `PLAN.md` is shipped.** Nothing in this file belongs in the hackathon scope. Everything here is a *future* extension anchored on Sampras's existing local expertise (RF beamforming, satellite thermal/mechanical, signal processing) and meant to be picked up phase by phase once the core loop is trustworthy.

## Why this roadmap exists

The MVP proves one narrow thing: a low-cost, multi-model loop can turn public space-weather/conjunction signals into traceable recommendations. That is intentionally a *thin slice* of what an operator actually cares about. A real Spacesharks needs to reason across at least four more axes:

1. **Ground segment health** — can we actually downlink this pass?
2. **Spacecraft thermal & mechanical state** — what is the bus doing physically?
3. **Telemetry & anomaly signals** — what does the engineering data itself say?
4. **Lessons-learned corpus** — what has gone wrong before in similar conditions?

Each axis maps to material Sampras already owns locally. The roadmap below turns that material into a phased plan instead of dumping it into the MVP.

## Phases

### Phase 0 — MVP (current)

Already covered in `PLAN.md`, `SCOPE.md`, `ARCHITECTURE.md`, `TRUST.md`. One scenario, one decision loop, one 24h run. **Do not extend Phase 0 with anything below.**

### Phase 1 — Ground segment & link-quality awareness

Goal: before recommending an action, factor in whether the next pass can actually carry the command/telemetry traffic implied by that action.

Inputs drawn from local expertise:

- X-band phased-array beamformer work (F5288 TX / F6212 RX, CORA-Z7 + Yaskawa scan rig)
- Calibration methodology (per-element phase/gain LUTs, antenna pattern measurement)
- Master's thesis at `D:\Beamformer_RF\Thesis_0850193.pdf` and `Hybrid X-band Phased Array Transmitter.pdf`

Spacesharks deliverable: a "pass-quality advisory" model that takes TLE + ground-station geometry + recent calibration drift + space-weather scintillation forecast and outputs an honest `link_margin_dB ± σ` with an evidence trail.

See [`research/rf-ground-segment.md`](research/rf-ground-segment.md).

### Phase 2 — Thermal & mechanical advisory

Goal: when sun-angle, eclipse entry/exit, or attitude maneuvers change, give operators an early read on thermal-stress risk and what the bus is likely doing.

Inputs drawn from local expertise:

- `D:\career\ee\衛星機械系統\熱控設計.pdf`
- `D:\career\ee\衛星機械系統\06_衛星熱環境介紹 _Homework.pdf`
- `D:\career\ee\衛星機械系統\Rosetta羅賽塔\` (Rosetta lander, including the Philae anomaly references)

Spacesharks deliverable: a "thermal/mechanical posture" model that runs alongside the conjunction/space-weather loop and flags when a recommended action would push a subsystem near a thermal or mechanical limit. Always cites a lessons-learned page.

See [`research/thermal-and-mechanical.md`](research/thermal-and-mechanical.md).

### Phase 3 — Telemetry & anomaly small-model layer

Goal: replace placeholder small-model classifiers in the MVP ensemble with ones grounded in real signal-processing methods, not generic LLM heuristics.

Inputs drawn from local expertise:

- ADSP material (`D:\career\ee\ADSP\`) — adaptive filtering, detection theory
- DCC (李琳山) digital communications — coding, demodulation, link analysis
- Quantum signal processing notes (`D:\career\ee\Quantum Computing\`) — as long-horizon reference, not Phase 3 scope

Spacesharks deliverable: a small-model bench where each classifier (TLE delta, RF interference flag, telemetry residual) has a documented detection rule, a confidence calibration plot, and a replay test set. This is how Phase 0's "small model A/B/C" boxes stop being TODOs.

See [`research/signal-processing.md`](research/signal-processing.md).

### Phase 4 — Lessons-learned corpus

Goal: every escalation by Nemotron should be able to cite at least one real prior incident. The corpus has to start narrow and verifiable, not encyclopedic.

First seed: Rosetta / Philae landing anomalies. Source PDFs already in `D:\career\ee\衛星機械系統\Rosetta羅賽塔\reference\`. The relevant lessons (cold-gas thruster failure, harpoon misfire, thermal load on Philae after bouncing into shadow) map directly onto Phase 1–3 advisory paths.

See [`research/case-studies-rosetta.md`](research/case-studies-rosetta.md).

### Phase 5 — Constellation / fleet view

Goal: extend the single-spacecraft MVP into a small fleet (≤5 spacecraft), with cross-asset arbitration (e.g., reassign a pass from a busy ground station to a healthier one).

This phase has *no* dedicated local-expertise input yet. Listed for completeness; pick it up only after Phase 1–4 have at least one passing replay.

## How to read the `research/` folder

`docs/research/INDEX.md` is the source-of-truth catalog: every relevant file on `D:\`, its absolute path, and the Phase it feeds. The other `research/*.md` files are per-axis design notes — each one ends with a "What to actually build" checklist so a future implementer (Claude, Codex, or human) can pick up a single phase without re-reading everything.

## Non-goals for the roadmap

- This roadmap is **not** a commitment to ship every phase. It is a deliberate, phased way to reuse existing material.
- Nothing here justifies expanding the MVP. If a Phase 1+ idea looks tempting during the hackathon, log it here and move on.
- This roadmap is **not** a portfolio piece. Do not surface it publicly until at least Phase 1 has a working replay.
