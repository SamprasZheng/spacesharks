# Signal processing & small-model layer (Phase 3)

> Post-MVP design note. Local expertise: Sampras's ADSP (adaptive signal processing) coursework and Prof. Lee's digital communications course at NTU, plus the F5288/F6212 measurement archive as a real-world dataset.

## Why this module belongs in Spacesharks

The MVP architecture has "small model A / B / C" boxes that classify, score, and draft. In Phase 0 they can be LLM-driven for speed. That is fine for a hackathon and bad for trust. A real operator copilot has to ground each classifier in a documented detection rule with a confidence calibration plot — otherwise the "ensemble" is just three LLMs voting noisily.

Phase 3 replaces the placeholders with small models whose behavior is **derivable from signal-processing first principles**, with calibration measured on a held-out replay set.

## What we already have locally

- **`D:\career\ee\ADSP\ADSP1.pdf` – `ADSP4.pdf`** — full adaptive signal processing course. Covers LMS/RLS adaptive filters, detection theory (Neyman-Pearson, CFAR), estimation (MMSE, MAP). These are exactly the tools a residual-based anomaly classifier needs.
- **`D:\career\ee\ADSP\ADSP_Write1.pdf`** — worked examples; useful for porting formulas without re-deriving.
- **`D:\career\ee\DCC資訊與數位通訊_李琳山\`** — digital communications. BER vs. Eb/N0 curves, coding gain, fading channels. Directly supports the link-budget side of Phase 1 and gives a principled noise model for telemetry features.
- **F5288/F6212 measurement archive** (`D:\Beamformer_RF\f5288-...\f5288\Measurement\` and `f6212\...\Measurement\`) — real captured RF data. The closest thing to a labeled in-house dataset that exists today.
- **`D:\career\ee\ML\`** — ML coursework. Used as background only; the small-model layer is *not* a place to introduce a heavyweight ML stack.

Full catalog: [`INDEX.md`](INDEX.md).

## Feature set this can produce

| Classifier | Detection rule (anchor) | Calibration |
|---|---|---|
| TLE-delta classifier | Compare propagated state vs. fresh TLE; threshold on radial / along-track / cross-track residual (km, σ-normalised). | Histogram of residuals over a 30-day replay; set thresholds at FAR = 1e-2. |
| RF interference flag | CFAR detector on baseline noise floor from the measurement archive. ADSP3 covers the CFAR rule. | ROC on captured "clean vs. injected" pairs. |
| Telemetry residual flag | Adaptive (LMS/RLS) one-step predictor; flag when residual exceeds k·σ. ADSP1/2 covers the filter, ADSP3 covers the test. | Per-channel σ estimated on a quiet window; recompute weekly. |
| Modulation/coding health | BER trend vs. expected BER at measured Eb/N0 (DCC course gives the curve). | Confidence = distance between observed and theoretical curve. |

Every classifier exposes a calibrated probability, not a yes/no. That is the precondition for the arbitration policy in `TRUST.md` to work honestly.

## Where this plugs into the architecture

No new ensemble slots — Phase 3 hardens the slots Phase 0 already defined. The change is internal: each small model carries a "method card" describing detection rule, training set (if any), calibration date, and last evaluated ROC point.

```
small model A (classify)  →  method card: "TLE delta, FAR=1e-2 at residual > 4.7 km, evaluated 2026-MM-DD"
small model B (score risk) →  method card: "CDM Pc + arbitration on disagreement with Phase 1 link margin"
small model C (draft)      →  remains LLM-backed; gated by A/B confidence
small model D (link)       →  Phase 1; method card from beamformer calibration
small model E (thermal)    →  Phase 2; method card from thermal model
```

## What to actually build (Phase 3 checklist)

- [ ] Define a `MethodCard` schema (YAML or pydantic): name, detection rule, inputs, outputs, FAR/PD point, calibration date, source citation.
- [ ] Implement TLE-delta classifier as a pure-Python function over an SGP4 propagator; wrap with a method card.
- [ ] Implement CFAR detector against a captured noise-floor sample from the measurement archive; wrap with a method card.
- [ ] Implement LMS/RLS telemetry residual flag against a synthetic + replayed telemetry feed (Phase 0 already produces JSONL).
- [ ] Add a weekly "calibration health" cron in OpenClaw that re-runs each classifier on its replay set and refuses to ship a recommendation if any card is > 30 days stale.
- [ ] Replace the Phase 0 "small model A/B/C" prompts with thin wrappers around these classifiers + a single LLM call for draft text only.
- [ ] Demonstrate one replay where the upgraded small models *abstain* on a case the Phase 0 LLM-only ensemble would have answered confidently — and Nemotron correctly escalates instead.

## Out of scope for Phase 3

- Deep learning. If a problem genuinely needs it, escalate the decision; do not slip it into the Phase 3 PR.
- Replacing Nemotron. Nemotron remains the referee.
- Quantum signal processing (`D:\career\ee\Quantum Computing\`) — interesting, parked.

## Related notes

- Phase 1 link-margin model is built the same way and shares the calibration discipline: [`rf-ground-segment.md`](rf-ground-segment.md).
- Phase 4 lessons-learned corpus depends on these classifiers actually firing for the right reasons: [`case-studies-rosetta.md`](case-studies-rosetta.md).
- Roadmap context: [`../ROADMAP.md`](../ROADMAP.md).
