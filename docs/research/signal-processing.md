---
title: Telemetry classifiers & MethodCard layer
type: research
category: roadmap-phase-3
status: ingested
ingested: 2026-05-24
sources:
  - file://D:/career/ee/ADSP/                                  # NTU adaptive signal-processing course
  - file://D:/career/ee/DCC資訊與數位通訊_李琳山/             # NTU digital comms (Prof. Lee Lin-shan)
  - file://D:/Beamformer_RF/f5288-20250227T011804Z-001/f5288/Measurement/    # in-house pattern dataset
  - https://en.wikipedia.org/wiki/Least_mean_squares_filter
  - https://en.wikipedia.org/wiki/Recursive_least_squares_filter
  - https://en.wikipedia.org/wiki/Constant_false_alarm_rate
  - arXiv:1706.04599                                            # Guo et al., calibration / temp scaling
  - arXiv:1705.08500                                            # Geifman & El-Yaniv, selective classification
  - Widrow, B. & Hoff, M. E. (1960) — Adaptive switching circuits — public domain
  - Rohling, H. (1983) — Radar CFAR thresholding in clutter — IEEE
private_material:
  - NTU course slides — private reference; cite by file path only.
  - F5288/F6212 measurement archive contains in-house captures; do not export without clearance.
---

# Telemetry classifiers & MethodCard layer — Phase 3 reference

> Post-MVP roadmap reference. The Phase 0 architecture has "small model A / B / C" boxes for classify / score / draft. Phase 3 replaces those LLM-only placeholders with classifiers whose detection rule, calibration date, and FAR/PD point are *all* documented — i.e. each classifier carries a **MethodCard**. Local expertise: Sampras's ADSP and Prof. Lee's DCC coursework at NTU, plus the F5288/F6212 measurement archive as an in-house labeled-ish dataset.

---

## 1. Why MethodCards exist

The Phase 0 small-model ensemble is honest about *its* own uncertainty (`docs/research/small-model-ensemble-arbiter.md` §4) but currently dishonest about the *substance* of each role: today A/B/C are LLMs prompted to "classify" / "score" / "draft", which is fine for a hackathon and bad for a 24/7 ops copilot. A real classifier needs:

1. A documented detection rule (formula, not prompt).
2. A documented training/calibration set (which files, which captures, which day).
3. A documented FAR/PD operating point.
4. A unit test that re-runs (3) on demand.

Phase 3 introduces a `MethodCard` schema that pins all four. Every classifier in `spacesharks/core/classifiers/` carries one. The Arbiter refuses to ship a recommendation if any consulted card is `> 30 days stale`.

---

## 2. MethodCard schema

```yaml
# spacesharks/core/classifiers/cards/<name>.yaml
name: tle_delta_classifier
version: 0.1.0
maps_to_role: A           # A=classify | B=score | C=draft | D=link | E=thermal
event_classes: [SPACE_WEATHER, CONJUNCTION, UNKNOWN]
detection_rule: |
  Propagate last known state with SGP4 to the time of the fresh TLE.
  Compute residual r = state_fresh - state_propagated in the RIC frame.
  Decision: |r_RIC| > threshold_RIC (3 floats, km).
inputs:
  - kind: tle_record
    schema: spacesharks.events.tle
training_set:
  ref: file://D:/Beamformer_RF/...   # placeholder — Phase 3 must define real set
  size: 0
  labeled: false
calibration:
  date: null
  far_target: 1.0e-2
  far_observed: null
  pd_observed: null
confidence_method: temperature_scaling   # see §5
last_evaluated_at: null
owner: sampras
```

The card is the operator's contract with the system: every claim the classifier makes is reducible to one of those fields.

---

## 3. The three flagship classifiers

### 3.1 TLE-delta classifier (role A, event = orbit change)

**Detection rule.** Propagate the previous TLE with SGP4 to the epoch of the incoming TLE. Compute the residual vector in the radial-along-cross (RIC) frame. Flag when any component exceeds a calibrated threshold:

```
r_RIC = R_eci_to_ric(state_prop) @ (state_fresh - state_prop)

decide:
  if |r_R| > τ_R or |r_I| > τ_I or |r_C| > τ_C  →  SPACE_WEATHER or CONJUNCTION
  else                                          →  UNKNOWN
```

Default thresholds (LEO, h ≈ 500–800 km), to be re-tuned per-mission:

| Component | Quiet 95% | Threshold τ |
|---|---|---|
| `r_R` (radial) | ~50 m | 200 m |
| `r_I` (along-track) | ~1.5 km | 5 km |
| `r_C` (cross-track) | ~80 m | 300 m |

Class disambiguation (`SPACE_WEATHER` vs `CONJUNCTION`) is by simultaneity with other signals — not by the residual alone. The classifier emits *both* candidate classes when the rule fires; the Arbiter resolves with model B's risk score and any CDM ingest.

### 3.2 CFAR-based RF interference flag (Phase 1 cross-cut, role A')

**Detection rule.** Cell-averaging CFAR (Rohling 1983). For a 1-D power spectrum `P[k]`, the test cell at index `k_t` is compared to the mean of `N` adjacent reference cells excluding guard cells:

```
P̄_noise = (1/N) · Σ_{k ∈ ref(k_t)} P[k]
threshold = α · P̄_noise
α = N · (P_FA^(-1/N) − 1)              # Rohling/Finn-Johnson formula
decide: H1 if P[k_t] > threshold else H0
```

For target `P_FA = 1e-2`, `N = 16`: `α ≈ 16 · (100^(1/16) − 1) ≈ 5.2` (≈ 7.2 dB above noise mean).

Training-set source: the in-house captures under `D:\Beamformer_RF\f5288-...\f5288\Measurement\` provide a baseline noise floor; injected "interferer" cases are generated by additive synthetic tones, not by external data.

### 3.3 Adaptive telemetry residual classifier (role B input, anomaly score)

**Detection rule (LMS).** A one-step predictor learns the per-channel telemetry signal:

```
LMS update (Widrow & Hoff 1960):
  ŷ_n = w_n^T · x_n
  e_n = y_n − ŷ_n
  w_{n+1} = w_n + 2 · μ · e_n · x_n
```

Choose step size `μ` from the Widrow stability bound `0 < μ < 1 / λ_max(R_xx)`. For practical defaults, set `μ = 0.01 / (P_x + ε)` (normalised LMS) with `P_x = ||x_n||²`. Flag when `e_n` exceeds `k · σ̂_e` (`k = 4` for ~`FAR = 6e-5` under Gaussian assumption).

**Detection rule (RLS, optional).** When channel statistics are non-stationary (post-eclipse warm-up, beta-angle drift), switch to RLS with forgetting factor `0.95 ≤ λ ≤ 0.99`:

```
RLS update:
  k_n = P_{n-1} x_n / (λ + x_n^T P_{n-1} x_n)
  e_n = y_n − w_{n-1}^T x_n
  w_n = w_{n-1} + k_n · e_n
  P_n = (1/λ) · (P_{n-1} − k_n · x_n^T · P_{n-1})
```

RLS converges faster but is `O(M²)` per step vs LMS's `O(M)`. Use only on the highest-importance channels (battery V, payload T) where the cost is justified.

### 3.4 BER-trend monitor (link-health, supports Phase 1)

Use the link-budget derived `E_b/N_0` (Section 3.2 of `rf-ground-segment.md`) and a table BER(E_b/N_0) for the configured FEC. Compare observed BER to theoretical:

```
score = log10(BER_obs / BER_theory(E_b/N_0_meas))
confidence = exp(-|score|)
```

A persistent `score > +1.0` (i.e., 10× worse than expected) is itself an anomaly signal even when the link is "up".

---

## 4. Where these plug into the architecture

No new ensemble slots — Phase 3 hardens the slots Phase 0 already defined.

```
Phase 0 slot          →  Phase 3 substance
small model A (class) →  TLE-delta classifier + CFAR interferer flag, ensembled per event type
small model B (risk)  →  LMS/RLS residual + (existing LLM only for natural-language scoring)
small model C (draft) →  remains LLM, but constrained to allow-listed verbs from MethodCard
small model D (link)  →  Phase 1 model, see rf-ground-segment.md
small model E (thermal) → Phase 2 model, see thermal-and-mechanical.md
```

The Arbiter logic itself does **not** change. Phase 3 only replaces what populates A/B with classifiers that are reviewable line-by-line.

---

## 5. Confidence calibration discipline

Same toolbox as the arbiter doc (§4 of `small-model-ensemble-arbiter.md`):

1. **Temperature scaling** (Guo et al. 2017, arXiv:1706.04599). For any classifier that emits logits, fit a single scalar `T` on a held-out set to minimise NLL; replace `softmax(logits)` with `softmax(logits / T)`. For the CFAR and LMS detectors which are non-probabilistic, derive a calibrated probability from the false-alarm-rate target:

   ```
   P_correct(score) = 1 − P_FA(score)        # under H0 (no anomaly)
   P_correct(score) = P_D(score)             # under H1 (anomaly)
   ```

   Use whichever applies based on the rule's output side.

2. **Brier score** as the headline calibration metric. A classifier without a Brier number on its MethodCard is not Phase-3-ready.

3. **Reliability diagrams** (10 confidence bins). Required for the TLE-delta classifier because RIC components have very different statistics.

4. **Selective accuracy** at fixed coverage levels (Geifman & El-Yaniv 2017, arXiv:1705.08500). The MethodCard records `acc@coverage = (0.5, 0.7, 0.9)`.

---

## 6. Calibration health cron

```python
# spacesharks/ops/calibration_cron.py
def is_card_fresh(card_path: Path, max_age_days: int = 30) -> bool:
    card = yaml.safe_load(card_path.read_text())
    last = card["calibration"]["date"]
    if last is None:
        return False
    return (date.today() - date.fromisoformat(last)).days <= max_age_days

def daily_health_check(classifiers: list[Classifier]) -> CalibrationHealthReport:
    stale = [c.name for c in classifiers if not is_card_fresh(c.card_path)]
    if stale:
        # Arbiter consults this report; refuses ESCALATE/RECOMMEND if any
        # required role's card is stale. Card-stale events are still logged.
        return CalibrationHealthReport(stale=stale, healthy=False)
    return CalibrationHealthReport(stale=[], healthy=True)
```

Runs once a day in OpenClaw. The Trust Model (`docs/TRUST.md`) commits to *abstain rather than recommend* when the card is stale; this cron enforces that mechanically.

---

## 7. Interface contract

```python
@dataclass(frozen=True)
class ClassifierOutput:
    responded: bool
    confidence: float
    latency_ms: int
    model_id: str
    value: str                    # event class
    raw_score: float              # for downstream calibration
    method_card: str              # path to YAML
    evidence: dict
```

Every classifier carries `method_card` as a path string; arbiter audits the path lazily and refuses to proceed if the card is missing or stale.

---

## 8. What to actually build (Phase 3 checklist)

- [ ] Land the `MethodCard` schema (§2) as a Pydantic / dataclass model with a YAML loader.
- [ ] Implement `tle_delta_classifier` with SGP4 propagation and the RIC-residual rule (§3.1). Card filled with a real `training_set.ref` from a 30-day replay.
- [ ] Implement `cfar_interferer_flag` with the Rohling α formula (§3.2). Training set = noise-floor extract from `D:\Beamformer_RF\...\Measurement\`. Synthetic-injection test harness for ROC.
- [ ] Implement `lms_residual_flag` per §3.3. Default `μ = 0.01 / (P_x + ε)`. RLS variant optional.
- [ ] Implement `ber_trend_monitor` per §3.4.
- [ ] Wire each classifier into the Phase 0 Arbiter slot A/B as a wrapper over `ClassifierOutput`.
- [ ] Add `spacesharks/ops/calibration_cron.py` (§6). Verify it actually blocks a recommendation when a card is stale.
- [ ] Calibrate via temperature scaling on each classifier; record Brier, reliability diagram, selective accuracy on the MethodCard.
- [ ] One replay where Phase 3 classifiers cause an *abstain* on a case the Phase 0 LLM-only ensemble would have answered confidently; Nemotron correctly escalates.
- [ ] One replay where the cron blocks a recommendation because a card is 31 days old.

---

## 9. Non-goals for Phase 3

- No deep learning. If a problem genuinely needs it, escalate the design decision; do not slip it into a Phase 3 PR.
- No replacement of Nemotron. Nemotron remains the referee on escalations.
- No quantum signal processing (`D:\career\ee\Quantum Computing\`) — interesting, parked.
- No on-line auto-retraining from production traffic. Calibration windows are explicit and operator-acknowledged.

---

## 10. Open uncertainties

- The RIC thresholds in §3.1 are placeholders. Real values depend on tracking-station / TLE-source noise statistics and must come from a 30-day replay before the card can ship `calibration.date`.
- LMS step size `μ` for telemetry channels: Widrow's bound is tight only when `R_xx` is known; in practice we estimate it on a quiet window and revisit weekly.
- The CFAR detector assumes Gaussian background — for impulsive interferers (e.g., terrestrial radar), a CA-CFAR is biased. Note the assumption on the card and document the failure mode.

---

## 11. Related notes

- Roadmap context: [`../ROADMAP.md`](../ROADMAP.md).
- Phase 0 arbiter (calibration discipline section): [`small-model-ensemble-arbiter.md`](small-model-ensemble-arbiter.md).
- Phase 1 link-margin advisor (shares the measurement archive): [`rf-ground-segment.md`](rf-ground-segment.md).
- Phase 2 thermal posture (cross-couples via PA / payload thermal): [`thermal-and-mechanical.md`](thermal-and-mechanical.md).
- Phase 4 corpus query when classifier fires: [`case-studies-rosetta.md`](case-studies-rosetta.md).
- Source-of-truth catalog: [`INDEX.md`](INDEX.md).
