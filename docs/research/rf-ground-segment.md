# RF & ground-segment advisory (Phase 1)

> Post-MVP design note. Owner of the local expertise: Sampras (MSc thesis on X-band phased-array beamforming, hands-on F5288/F6212 + CORA-Z7 + Yaskawa scan rig).

## Why this module belongs in Spacesharks

The MVP recommends actions (slew, defer, hand off) based on space-weather and conjunction signals. It implicitly assumes the next pass will actually carry the resulting command and telemetry traffic. In practice the link is the bottleneck more often than the spacecraft is: rain fade, scintillation during a geomagnetic storm, antenna calibration drift, element failure in a phased array — any of these can quietly reduce link margin below what a recommended op requires.

A small "pass-quality advisor" closes that loop: before any recommendation ships, ask "what is the honest `link_margin_dB ± σ` for the next N passes?" and let the ensemble factor it in.

## What we already have locally

Sampras's beamformer work covers the full ground-segment RF chain end to end:

- **TX side (F5288)** — 4×4 H/V dual-pol X-band beamformer IC. Driver in `D:\Beamformer_RF\Driver\TXBFIC_source.py` shows the real control surface: 5.6°/step phase shifters, ~30 dB gain range (`gain_code = limit_range(int((gain / 30.47 + 1) * 255), 255, 0)`), per-channel CTRL/SET registers.
- **RX side (F6212)** — mirror IC; driver in `D:\Beamformer_RF\Driver\RXBFIC.py`.
- **Host platform** — CORA-Z7 (Zynq-7) at `D:\Beamformer_RF\f5288-...\f5288\CORA-Z7\`. Bitstreams + Tcl scripts for `vivado_server_*`; this is the reference "hardware-in-the-loop host" pattern.
- **Calibration rig** — Yaskawa robotic arm (`D:\Beamformer_RF\Driver\Yaskawa.py` + `roboticarm.py`) plus a network-analyzer driver (`NA.py`). The calibration notebook (`f5288/Code/calibration.ipynb`) is the canonical per-element phase/gain extraction.
- **Measurement archive** — `f5288/Measurement/0601…0613` and `f6212/Measurement/` contain real captured patterns. This is a usable dataset, not a hypothetical one.
- **Thesis + paper** — `Thesis_0850193.pdf` and `Hybrid X-band Phased Array Transmitter.pdf` for the system-level write-up.

Full catalog: [`INDEX.md`](INDEX.md).

## Feature set this can produce

| Feature | How the local material supports it |
|---|---|
| `link_margin_dB` per pass | Calibrated antenna pattern + ground geometry + path loss + space-weather attenuation/scintillation. The calibration notebooks already define the pattern; thesis defines the link budget. |
| `calibration_drift_score` | Re-run the calibration notebook periodically; track per-element phase/gain delta vs. baseline. Element-level outliers are the leading indicator of a failing PA / LNA. |
| `element_failure_flag` | Array-factor analysis (`f6212/Analysis/array_factor.ipynb`) maps element loss → pattern degradation. A small classifier on measured pattern cuts produces a binary "ok / degraded" with confidence. |
| `interference_flag` | NA / spectrum captures already in the measurement archive give a baseline noise floor. Anomalous floor on a test capture → flag. |
| `pass_recommendation` | Combine the four above into "use", "use with reduced rate", "defer", "hand off" with the same evidence-trail discipline as the rest of the system. |

## Where this plugs into the architecture

Reuses the Phase 0 contract from `ARCHITECTURE.md`. New small model slots into the same ensemble:

```
OpenClaw → small model A (classify space-weather event)
        → small model B (score conjunction risk)
        → small model C (draft op recommendation)
        → small model D (Phase 1: estimate link margin for next N passes)   ← new
        → Nemotron (escalate if D disagrees materially with C)
```

Model D's input contract: TLE (Phase 0 already pulls Celestrak), ground-station geometry (config), recent calibration delta (operator upload — start with a static stub), space-weather attenuation forecast (Phase 0 already pulls NOAA SWPC).

Model D's output contract: `{margin_dB: float, sigma_dB: float, dominant_term: str, evidence: [url|file-ref, ...]}`. Same JSONL log shape as Phase 0.

## What to actually build (Phase 1 checklist)

- [ ] Decide a single ground-station baseline (lat/lon/altitude/antenna gain). Hard-code, don't generalise yet.
- [ ] Port `f5288/Code/calibration.ipynb` core logic into a `link_budget.py` helper. Trim to: per-element phase, per-element gain, beam-pointing-vs-target, fade margin.
- [ ] Write a stub `calibration_drift.json` and a loader. Drift score = max element deviation vs. baseline.
- [ ] Add SWPC scintillation index (`S4` proxy) into the loader Phase 0 already has for SWPC. Re-use, do not duplicate.
- [ ] Implement model D as a deterministic function first (no LLM). It only becomes a "model" once it has confidence calibration.
- [ ] Add one demo replay where the conjunction recommendation flips from "execute" to "defer" because model D says link margin is < 3 dB during a peak S4 window.
- [ ] Write a one-page evidence card per recommendation that cites the calibration baseline file + SWPC reading.

## Out of scope for Phase 1

- Doppler/Polarization fine-tuning beyond what the link budget already captures.
- Actual control of any real ground station. Recommendation only, never actuation.
- Multi-station scheduling — defer to Phase 5 (fleet view).
- Re-deriving the BFIC register maps. Treat datasheet + driver as authoritative.

## Related notes

- Thermal/mechanical posture feeding into pass timing (e.g., post-eclipse warm-up): [`thermal-and-mechanical.md`](thermal-and-mechanical.md).
- Anomaly classifiers consuming RF telemetry: [`signal-processing.md`](signal-processing.md).
- Roadmap context: [`../ROADMAP.md`](../ROADMAP.md).
