---
title: Calibrated confidence — measurement, abstention, escalation
type: research
category: pattern
status: ingested
ingested: 2026-05-24
sources:
  - arXiv:1706.04599  # Guo et al. — On Calibration of Modern Neural Networks (ICML 2017)
  - arXiv:2305.14975  # Tian et al. — Just Ask for Calibration (2023)
  - arXiv:2207.05221  # Kadavath et al. — Language Models (Mostly) Know What They Know (Anthropic 2022)
  - arXiv:2306.10193  # Quach et al. — Conformal Language Modeling (ICLR 2024)
  - arXiv:2305.18404  # Kumar et al. — Conformal Prediction with LLMs for Multi-Choice QA (2023)
  - arXiv:1705.08500  # Geifman & El-Yaniv — Selective Prediction (NeurIPS 2017)
  - arXiv:2209.15558  # Ren et al. — OOD Detection and Selective Generation (ICLR 2023)
  - arXiv:1901.09192  # Geifman & El-Yaniv — SelectiveNet (2019)
  - arXiv:2208.12084  # Fisch et al. — Calibrated Selective Classification (2022)
---

# Calibrated confidence — measurement, abstention, escalation

> Status: pattern research note for the Spacesharks Mission Desk. This is the
> *confidence-honesty layer* that gates the
> [Small-Model Ensemble Arbiter](small-model-ensemble-arbiter.md) and feeds
> the [Tiered Inference](tiered-inference.md) dispatcher's "threshold
> proximity" trigger. The trust pitch lives in [TRUST.md](../TRUST.md).

## 1. Why raw model confidence is not enough

A model is **calibrated** when its stated confidence matches empirical
accuracy over many predictions: a 70%-confidence output is correct ~70% of
the time on a reference distribution.

Raw LLM confidence is not calibrated by default:

- **Softmax-max probabilities over the vocabulary** measure generation
  fluency, not factual correctness. They correlate weakly with whether the
  answer is actually right.
- **Self-reported confidence in natural language** ("I'm fairly sure...")
  inherits the same sycophancy and length biases as any other CoT output.
  It can be elicited and calibrated separately, but it is not free.
- **Modern deep nets are systematically over-confident.** Guo et al.
  (arXiv:1706.04599) showed that post-2015 architectures have higher raw
  confidence on wrong answers than older nets — accuracy went up,
  calibration went down.

For an ops copilot that must choose between **publishing, monitoring, or
escalating**, miscalibrated confidence causes two symmetric harms:

1. Overconfident wrong answers are acted on (or escalate too late).
2. Underconfident right answers are suppressed or escalate unnecessarily.

The fix is not "use the bigger model." The fix is to calibrate whatever
confidence channel the orchestrator uses, and to make `abstain` a
first-class output that the system can take.

## 2. Calibration techniques

Five techniques worth knowing, ordered from cheapest at inference time to
most expensive:

| Technique | Inference cost | Needs labelled data | Output shape | Reference |
|---|---|---|---|---|
| Temperature scaling | one division | yes (held-out) | scalar (rescaled) | Guo 2017 (arXiv:1706.04599) |
| Platt scaling / isotonic | negligible | yes (small) | scalar (rescaled) | classical SVM literature |
| Verbalised + calibrated | one extra generation pass | yes (calibration set for the verbal channel) | scalar from text | Tian 2023 (arXiv:2305.14975) |
| P(IK) — Probability of Knowing | one forward pass for the head, or one extra generation | yes (fine-tune) | scalar pre-answer | Kadavath 2022 (arXiv:2207.05221) |
| Conformal prediction | one extra forward pass | yes (calibration set, exchangeability) | **set-valued** with coverage guarantee | Quach 2024 (arXiv:2306.10193); Kumar 2023 (arXiv:2305.18404) |

Selection rules for the Mission Desk:

- **Temperature scaling first.** Cheap, reversible, fits in one cron job.
  Use it on the arbiter's aggregate confidence channel before anything
  else.
- **P(IK) for high-tier escalation.** When T3 is invoked, ask the model
  ahead of generation whether it expects to answer correctly; if its
  pre-generation P(IK) is below threshold, escalate to `needs-human-review`
  instead of generating.
- **Conformal prediction for set-valued outputs only.** Use it when the
  output space is discrete and finite (e.g. event-type classification with
  the fixed 6-category schema in
  [Small-Model Ensemble Arbiter §2](small-model-ensemble-arbiter.md#2-role-decomposition));
  the coverage guarantee is worth more than a scalar in that setting.
- **Verbalised confidence as a sanity check.** Useful on Day 1 when no
  calibration set exists; replace with temperature scaling once labelled
  outcomes accumulate.

## 3. Three-class output schema

Raw binary `answer / no-answer` is insufficient. The orchestrator emits one
of three classes per decision:

| Output | Condition | Operator effect |
|---|---|---|
| `answer` | Calibrated confidence ≥ class-specific threshold AND ensemble disagreement < class-specific ceiling | Recommendation published (subject to governance policy) |
| `abstain` | Confidence below threshold OR disagreement above ceiling | Logged with `trigger_reason`; no operator-facing surface; **not silent — this is an auditable row** |
| `escalate` | High-stakes event (Red Pc, X-flare, crewed proximity) OR confidence too low AND significance above threshold | Escalated to next inference tier ([tiered-inference](tiered-inference.md)) OR flagged `needs-human-review` |

Abstention is **a durable, logged event**, not a null. Every abstain row
carries:

```json
{
  "decision_route": "abstain",
  "trigger_reason": "low_confidence" | "high_disagreement" | "contradictory_evidence",
  "confidence": 0.0..1.0,
  "evidence_hash": "<sha256 of inputs that caused the abstain>",
  "ensemble_disagreement": 0.0..1.0,
  "logged_at": "<ISO8601>"
}
```

The `audit_completeness` scoreboard metric penalises silently-dropped
queries — an abstain with a logged reason is good; a query with no row at
all is a bug.

## 4. Coverage–risk operating point per decision class

Geifman & El-Yaniv 2017 (arXiv:1705.08500) formalised the **coverage–risk
curve**: as the abstention threshold tightens, risk (error rate on
*answered* predictions) falls but coverage (fraction of queries answered)
also falls. The operating point on this curve is a **policy choice, not a
model property**.

Mission Desk policy by decision class:

| Decision class | Bias | Why |
|---|---|---|
| Safe-mode trigger | recall-favoured (wide coverage, more FPs OK) | Missing a real safe-mode event is worse than a false alarm to the operator |
| Manoeuvre recommendation (CDM) | recall-favoured | Same — manoeuvre over-suggestions are reviewable; missed Red Pc is not |
| Launch slip pre-alert | precision-favoured (higher abstention OK) | FP cost is low (an operator ignores it); FN cost is also low (slip becomes obvious) |
| Interference attribution | precision-favoured | A wrong attribution is reputationally expensive; an abstain is cheap |
| Decay ETA / EOL | balanced | No urgent operator action; precision and recall are both readable |

Thresholds are **per-class, not global**. The arbiter's logic table reads
the threshold from a YAML config keyed by `decision_class`.

## 5. Validation harness — Brier + reliability diagram

Without measurement, the calibration claim is theatre. The Mission Desk
validates calibration nightly on the live event log.

### Brier score

The Brier score is the mean squared error between predicted probability and
binary outcome:

```
Brier = (1/N) * Σ (p_i - y_i)^2
```

Where `p_i` is the model's stated probability for the correct class and
`y_i ∈ {0, 1}` is the actual outcome. Naive binary-guess baseline: 0.25.
Lower is better. A confident wrong answer is penalised proportionally to
the *square* of the deviation from truth, so overconfident errors cost
more than underconfident ones — the right incentive.

### Reliability diagram

Bin predictions by stated confidence (e.g. 10 bins of width 0.1); for each
bin, plot the observed accuracy. A perfectly calibrated model lies on the
diagonal.

```python
# calibration_eval.py
from __future__ import annotations

import numpy as np
from dataclasses import dataclass

@dataclass
class CalibrationReport:
    brier_score: float
    ece: float                     # expected calibration error
    bin_centres: np.ndarray
    bin_accuracy: np.ndarray
    bin_confidence: np.ndarray
    bin_count: np.ndarray

def reliability_diagram(
    confidences: np.ndarray,       # shape (N,), values in [0, 1]
    outcomes: np.ndarray,          # shape (N,), values in {0, 1}
    n_bins: int = 10,
) -> CalibrationReport:
    if confidences.shape != outcomes.shape:
        raise ValueError("shape mismatch")
    if not ((0.0 <= confidences) & (confidences <= 1.0)).all():
        raise ValueError("confidences must be in [0, 1]")

    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    bin_idx = np.clip(np.searchsorted(bin_edges, confidences, side="right") - 1, 0, n_bins - 1)

    bin_accuracy = np.zeros(n_bins)
    bin_confidence = np.zeros(n_bins)
    bin_count = np.zeros(n_bins, dtype=int)

    for b in range(n_bins):
        mask = bin_idx == b
        n = int(mask.sum())
        bin_count[b] = n
        if n == 0:
            continue
        bin_accuracy[b] = float(outcomes[mask].mean())
        bin_confidence[b] = float(confidences[mask].mean())

    total = bin_count.sum()
    if total == 0:
        ece = float("nan")
    else:
        weights = bin_count / total
        ece = float((weights * np.abs(bin_accuracy - bin_confidence)).sum())

    brier = float(((confidences - outcomes) ** 2).mean())

    return CalibrationReport(
        brier_score=brier,
        ece=ece,
        bin_centres=(bin_edges[:-1] + bin_edges[1:]) / 2,
        bin_accuracy=bin_accuracy,
        bin_confidence=bin_confidence,
        bin_count=bin_count,
    )
```

### Temperature scaling fit

```python
# temperature_scaling.py
import numpy as np
from scipy.optimize import minimize_scalar

def fit_temperature(
    logits: np.ndarray,            # shape (N, K) — pre-softmax logits
    labels: np.ndarray,            # shape (N,)   — class indices
) -> float:
    """Fit a single scalar T minimising NLL on a held-out set.

    Returns T in (0, +inf). T > 1 softens; T < 1 sharpens.
    """
    def nll(T_log: float) -> float:
        T = float(np.exp(T_log))
        z = logits / T
        z -= z.max(axis=1, keepdims=True)        # numeric stability
        log_softmax = z - np.log(np.exp(z).sum(axis=1, keepdims=True))
        return -log_softmax[np.arange(len(labels)), labels].mean()

    res = minimize_scalar(nll, bounds=(-3.0, 3.0), method="bounded")
    return float(np.exp(res.x))
```

Both are drop-in modules. Wire them to run on the previous 24 hours of
events at 02:00 UTC daily; export `brier_score`, `ece`, and the per-bin
table to the scoreboard.

## 6. Bootstrap on Day 1

The Mission Desk has no labelled validation set on Day 1. Bootstrap from:

- **NASA CARA Red / Yellow / Green Pc bands** (Pc ≥ 1×10⁻⁴ Red,
  ≥ 7×10⁻⁵ Yellow per NPR 8079.1; see
  [space-track-cdm-api.md](space-track-cdm-api.md)). These are operational
  ground truth with no human labelling cost.
- **NOAA SWPC G/R/S scale alerts**. The alert *exists* at a known threshold;
  the agent's classification is correct iff it matches the SWPC product
  for the same window (see [noaa-swpc-api.md](noaa-swpc-api.md)).
- **Outcome delta in the audit log**. When a recommendation is followed by
  an operator (logged as `operator_action_taken`), the *outcome* (anomaly
  / no anomaly within window) is the binary outcome for that row. This
  generates labels at zero marginal cost as the desk runs.

The long-term calibration set is the labelled-lifecycle dataset that
accumulates as the desk operates. By Phase 1 there should be enough rows to
fit per-decision-class temperatures.

## 7. Where it fails

- **Calibration drifts.** A temperature fit at week 1 may be wrong at week
  8 because the input distribution changed (e.g. solar cycle phase shift,
  new constellation in the catalog). Refit nightly; alarm on ECE > 0.05.
- **Class imbalance kills the ECE estimate.** If 99% of CDMs are
  `monitor_only` and 1% are `manoeuvre`, naive bins underweight the
  important minority. Use class-stratified bins for the metric to be
  meaningful.
- **Verbalised confidence is brittle out of distribution.** Tian et al.
  found verbalised confidence is better than softmax on factual QA but
  degrades on OOD prompts. The Mission Desk's domain is OOD for every
  general-purpose LLM — verbalised confidence is a Day 1 placeholder, not
  a long-term answer.
- **P(IK) is model-size dependent.** Kadavath et al. found P(IK) accuracy
  is roughly log-linear in model size — small models are bad at predicting
  their own correctness. P(IK) is a T2/T3 technique, not a T1 one.

## 8. What to actually build

- [ ] `calibration_eval.py` module with `reliability_diagram()` and
      `fit_temperature()` per §5.
- [ ] Nightly cron at 02:00 UTC running the validator on the previous 24h
      of event rows; writes `metrics/calibration-<date>.json` and updates
      the scoreboard.
- [ ] Per-decision-class threshold YAML config; loaded by the arbiter at
      startup; hot-reloaded on SIGHUP.
- [ ] `decision_route` field added to every event row (see
      [agentic-provenance](agentic-provenance.md)).
- [ ] `abstain_rate_by_class` and `ece_by_class` metrics on the
      scoreboard.
- [ ] One demo case showing a `monitor_only` Pc event being abstained on
      because of low ensemble agreement, with the trigger reason visible
      in the audit log.

## 9. References

- Guo et al. *On Calibration of Modern Neural Networks.* arXiv:1706.04599
  (ICML 2017).
- Tian et al. *Just Ask for Calibration.* arXiv:2305.14975 (2023).
- Kadavath et al. *Language Models (Mostly) Know What They Know.*
  arXiv:2207.05221 (Anthropic, 2022).
- Quach et al. *Conformal Language Modeling.* arXiv:2306.10193 (ICLR 2024).
- Kumar et al. *Conformal Prediction with LLMs for Multi-Choice QA.*
  arXiv:2305.18404 (2023).
- Geifman & El-Yaniv. *Selective Prediction in Deep Neural Networks.*
  arXiv:1705.08500 (NeurIPS 2017).
- Ren et al. *Out-of-Distribution Detection and Selective Generation for
  Generative Language Models.* arXiv:2209.15558 (ICLR 2023).
- Geifman & El-Yaniv. *SelectiveNet.* arXiv:1901.09192 (2019).
- Fisch et al. *Calibrated Selective Classification.* arXiv:2208.12084
  (2022).
