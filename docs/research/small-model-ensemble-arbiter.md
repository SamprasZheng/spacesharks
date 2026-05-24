---
title: Small-Model Ensemble Arbiter pattern
type: research
category: pattern
status: ingested
ingested: 2026-05-24
sources:
  - arXiv:2207.05221  # Kadavath et al., Language Models (Mostly) Know What They Know
  - arXiv:1706.04599  # Guo et al., On Calibration of Modern Neural Networks
  - arXiv:1705.08500  # Geifman & El-Yaniv, Selective Classification for Deep Neural Networks
  - arXiv:1901.09192  # Geifman & El-Yaniv, SelectiveNet
  - arXiv:2203.11171  # Wang et al., Self-Consistency Improves Chain of Thought Reasoning
  - arXiv:1701.06538  # Shazeer et al., Sparsely-Gated Mixture-of-Experts
  - arXiv:2208.12084  # Fisch et al., Calibrated Selective Classification
  - https://openrouter.ai/meta-llama/llama-3.1-8b-instruct
  - https://openrouter.ai/mistralai/mistral-7b-instruct-v0.2
  - https://openrouter.ai/nvidia/llama-3.3-nemotron-super-49b-v1
  - https://openrouter.ai/microsoft/phi-3-mini-128k-instruct
---

# Small-Model Ensemble Arbiter pattern

> Status: pattern research note for the Spacesharks Mission Desk. This is the
> *technical* description of the inference pattern. The trust pitch lives in
> [TRUST.md](../TRUST.md); the runtime flow lives in [ARCHITECTURE.md](../ARCHITECTURE.md).

## 1. Pattern definition

The **Small-Model Ensemble Arbiter** pattern routes a single event through
**three small models running in parallel, each owning a *different* sub-task**
(classify, score, draft), and then synthesizes their outputs with a
**deterministic, code-only Arbiter** — no second LLM call. On strong agreement
above a risk threshold, the Arbiter escalates a fully-formed proposal to a
larger reasoning model (Nemotron) inside a sandbox; on disagreement, it
abstains to *monitor-only*.

It is not the same as the three closest neighbours:

- **Majority-vote / bagging ensembles** in classical ML run *the same task* on
  many learners and aggregate. The Arbiter pattern runs *different tasks* on
  different learners — the outputs are not interchangeable, so voting is
  inapplicable.
- **Self-consistency** (Wang et al. 2022, arXiv:2203.11171) samples many
  reasoning paths from the *same* LLM and picks the most consistent final
  answer. Same model, same task, marginalised over sampling noise. The
  Arbiter pattern uses *different models* for *non-overlapping* tasks.
- **Mixture-of-Experts** (Shazeer et al. 2017, arXiv:1701.06538) shares a
  learned routing layer that picks which expert(s) handle each token. The
  router is itself a model and is trained jointly with the experts.
  The Arbiter pattern has *no learned router*: the Arbiter is a small,
  reviewable rule block that consumes structured outputs.

The closest published analogue is **divide-and-arbitrate** /
*case-adaptive multi-agent deliberation* (e.g. the CAMP framework in
arXiv:2510.* clinical-prediction work, 2025) where specialists each
contribute one diagnostic axis and a hybrid router decides between
consensus, abstention, and evidence-based arbitration.

## 2. Role decomposition

| Role | Owns | Input | Output | Suggested model class |
|------|------|-------|--------|-----------------------|
| **A — Classifier** | Event category | normalized event record | one of `{SPACE_WEATHER, CONJUNCTION, LAUNCH_SLIP, DEBRIS, NOTAM, UNKNOWN}` + softmax confidence | Llama-3.1-8B-Instruct, Phi-3-mini-128k, Gemma-2-9B, or a fine-tuned `distilbert` head |
| **B — Risk Scorer** | Severity score `[0, 10]` | normalized event record + category from A (optional) | scalar risk score + scalar confidence | Mistral-7B-Instruct with a template-constrained prompt, or a small regression-tuned model |
| **C — Action Drafter** | One-sentence recommendation | normalized event record + category from A | natural-language sentence (≤ 280 chars) chosen from an allow-listed verb set | General 7–9B chat model with a strict system prompt |

Each model returns a small JSON blob:

```json
{ "value": <category | float | text>,
  "confidence": 0.0..1.0,
  "latency_ms": int,
  "model_id": "openrouter/meta-llama/llama-3.1-8b-instruct" }
```

Importantly, **A, B, and C are independent calls**. They can run in parallel
(`asyncio.gather`) — the per-event wall clock is `max(latency_A, latency_B,
latency_C)`, not the sum.

## 3. Arbiter logic (deterministic synthesis)

The Arbiter is **code, not a model**. That is the whole point — every
decision boundary is reviewable and unit-testable.

```python
# Initial defaults; tune from the Day 4 calibration set.
TAU_CLS  = 0.70    # classifier confidence floor
R_HIGH   = 7.0     # escalate-to-Nemotron threshold
R_MID    = 4.0     # recommend threshold
DELTA    = 0.30    # disagreement budget
HIGH_RISK_CLASSES = {"SPACE_WEATHER", "CONJUNCTION"}

def arbitrate(a, b, c) -> ArbiterOutput:
    # 1. Liveness
    if not (a.responded and b.responded and c.responded):
        return ABSTAIN("model_timeout")

    # 2. Sanity — classifier must be confident enough to anchor everything else
    if a.value == "UNKNOWN" or a.confidence < TAU_CLS:
        return ABSTAIN("low_classifier_confidence")

    # 3. Cross-model coherence
    if disagreement(a, b, c) > DELTA:
        return ABSTAIN("ensemble_disagreement")

    # 4. Action gating
    if b.value >= R_HIGH and a.value in HIGH_RISK_CLASSES:
        return ESCALATE(payload=build_nemotron_prompt(a, b, c))
    if b.value >= R_MID:
        return RECOMMEND(action=c.value, risk=b.value, klass=a.value)
    return MONITOR
```

**Rationale for the default thresholds**

- `TAU_CLS = 0.70` — softmax probabilities above ~0.7 on a calibrated
  small classifier correspond empirically to >85% top-1 accuracy
  (cf. Guo et al. 2017, Fig. 1–2: post temperature-scaling reliability
  diagrams cross the diagonal in roughly this band).
- `R_HIGH = 7.0`, `R_MID = 4.0` — chosen so a 0–10 scale maps to
  three operational bands (≥7 escalate, 4–7 recommend, <4 monitor). These
  must be re-tuned against the Day 4 ground-truth set; see §11.
- `DELTA = 0.30` — initial guess; the disagreement function is the
  weighted sum of structural mismatches (next section).

## 4. Confidence calibration

Raw softmax probabilities from a modern neural network are **systematically
miscalibrated** — typically over-confident on hard examples and
under-confident on near-deterministic ones (Guo et al. 2017,
arXiv:1706.04599). For LLMs specifically, Kadavath et al. (2022,
arXiv:2207.05221) show that large models are *reasonably* calibrated on
multi-choice formats but that calibration degrades on free-form generation
and is sensitive to prompt format.

For the Mission Desk we need calibrated probabilities for the
classifier (used in the `TAU_CLS` gate) and ideally for the risk score.

**Techniques in increasing complexity:**

1. **Temperature scaling** (Guo et al. 2017): fit a single scalar `T` on a
   held-out validation set to minimise NLL; replace `softmax(logits)` with
   `softmax(logits / T)`. Cheap, monotonic, almost always helps. This is
   the right starting point for the classifier.
2. **Isotonic regression** / Platt scaling: non-parametric mapping from
   raw confidence to empirical frequency. More flexible than temperature
   scaling, can overfit on small validation sets.
3. **Verbalised confidence** (Kadavath et al. 2022, "P(True)"): ask the
   model itself to predict whether its answer is correct. Useful as a
   second signal but should not replace post-hoc calibration.
4. **Calibrated selective classification** (Fisch et al. 2022,
   arXiv:2208.12084): joint calibration + coverage optimisation;
   relevant for §5 below.

**Metric: Brier score**

For a categorical classifier with predicted probability vector
`p` and one-hot ground truth `y`, the Brier score is

```
BS = (1/N) * sum_i ||p_i - y_i||_2^2
```

Lower is better; an uninformative uniform predictor on `K` classes
gives `BS = 1 - 1/K`. We track Brier score on the classifier *post*
temperature scaling, in §11.

## 5. Abstain-on-disagreement

Foundational reference: Geifman & El-Yaniv,
*Selective Classification for Deep Neural Networks* (arXiv:1705.08500, 2017)
and *SelectiveNet* (arXiv:1901.09192, 2019). The high-level principle
is **trade coverage for accuracy** — let the model decline to answer when
it is uncertain, and report both selective risk and coverage as
joint metrics.

In the Arbiter, "uncertainty" is structural rather than purely
probabilistic. We define:

```python
def disagreement(a, b, c) -> float:
    """Returns a scalar in [0, 1]. Higher = more incoherent."""
    score = 0.0

    # (i) Classifier label vs risk bucket coherence
    expected_band = expected_risk_band(a.value)   # e.g. SPACE_WEATHER -> {mid, high}
    if bucket_of(b.value) not in expected_band:
        score += 0.4

    # (ii) Action drafter contradicts classifier
    if not action_consistent_with_class(c.value, a.value):
        score += 0.4

    # (iii) Confidence dispersion — one model wildly less confident than the others
    cs = [a.confidence, b.confidence, c.confidence]
    if max(cs) - min(cs) > 0.5:
        score += 0.2

    return min(score, 1.0)
```

If `disagreement(a, b, c) > DELTA`, the Arbiter returns
`ABSTAIN("ensemble_disagreement")` and the event is logged with full evidence
but no recommendation. Selective-classification theory (Geifman & El-Yaniv)
guarantees that, *given a good confidence function*, dropping the bottom
`1 - c` fraction of examples by confidence strictly improves selective
accuracy. The Arbiter is the engineering instantiation of that result
across three heterogeneous estimators.

## 6. OpenRouter cost model

Prices below were fetched from openrouter.ai on **2026-05-24**. They are
passthrough rates (OpenRouter does not mark up the upstream provider).

| Model | Input $/Mtok | Output $/Mtok | Context |
|-------|-------------:|--------------:|--------:|
| `meta-llama/llama-3.1-8b-instruct` | 0.02 | 0.05 | 131K |
| `mistralai/mistral-7b-instruct-v0.2` | 0.20 | 0.20 | 33K |
| `mistralai/mistral-7b-instruct-v0.1` | 0.11 | 0.19 | 33K |
| `microsoft/phi-3-mini-128k-instruct` | ~0.10* | ~0.10* | 128K |
| `nvidia/llama-3.3-nemotron-super-49b-v1` (v1.5) | 0.10 | 0.40 | 131K |

\* Phi-3-mini list price is not consistently surfaced via the public
OpenRouter model card; the ~$0.10 figure is the Microsoft-direct list
rate quoted by `pricepertoken.com`. Treat as upper bound until verified
in code via the OpenRouter `/api/v1/models` endpoint.

**Per-event ensemble cost** at our default budget
(500 input tok + 50 output tok per role):

```
cost(role) = 500e-6 * P_in + 50e-6 * P_out

Classifier (Llama-3.1-8B):  500e-6*0.02 + 50e-6*0.05 = $0.0000125
Risk      (Mistral-7B v0.2): 500e-6*0.20 + 50e-6*0.20 = $0.00011
Drafter   (Llama-3.1-8B):    500e-6*0.02 + 50e-6*0.05 = $0.0000125

Ensemble subtotal (cheap config, all-Llama-8B):
  3 * $0.0000125                                  = $0.0000375 / event
Ensemble subtotal (mixed, A=Llama-8B, B=Mistral-7B v0.2, C=Llama-8B):
  $0.0000125 + $0.00011 + $0.0000125              = $0.000135  / event
```

**Single Nemotron-Super-49B call** at 2000 input + 400 output tok
(a fully-formed reasoning prompt with context):

```
2000e-6 * 0.10 + 400e-6 * 0.40 = $0.00020 + $0.00016 = $0.00036 / event
```

So the all-Llama-8B ensemble is **~10× cheaper** than a Nemotron call,
and the mixed ensemble is **~2.7× cheaper**. The escalation-gated design
means Nemotron only runs on the subset of events where the ensemble both
*agrees* and *flags high risk* — typically a single-digit percentage of
the daily feed. At 1000 events/day, the upper-bound monthly bill is on
the order of:

```
1000 events/day * 30 days * ($0.000135 ensemble + 0.05 * $0.00036 nemotron)
  = $4.05 + $0.54 = ~$4.59 / month
```

This is the cost story that justifies the architecture: a calibrated,
abstaining, observable ensemble for ≤ $5/month, with the strong model
held in reserve.

## 7. Escalation gate

Nemotron is **never the default path**. Two and only two triggers
fire `ESCALATE`:

1. **Agreement-and-risk**: `disagreement(a,b,c) ≤ DELTA` *and*
   `b.value ≥ R_HIGH` *and* `a.value ∈ HIGH_RISK_CLASSES`. This is
   the canonical case — the ensemble is coherent and points at something
   genuinely serious, so we spend the larger model's tokens to produce
   the human-readable rationale.
2. **High-stakes class with disagreement**: `a.value ∈ HIGH_RISK_CLASSES`
   *and* `disagreement(a,b,c) > DELTA`. Here the ensemble is *not*
   coherent, but the classifier (with `confidence ≥ TAU_CLS`) believes
   the event is in a high-stakes category. Rather than abstain silently
   we escalate to Nemotron with the full conflicting evidence and let
   the larger model adjudicate. This branch is logged with a
   `gate_reason: "high_stakes_disagreement"` tag for replay review.

Escalation is gated because:

- **Cost**: ~10× per call vs the cheap ensemble (see §6).
- **Latency**: a 49B model under typical OpenRouter load is 2–5×
  slower than an 8B model.
- **Reviewability**: every Nemotron call writes its full prompt and
  response to the event log. We want that log to be small enough to
  audit by hand on Day 4.

## 8. Prior art and references

Verified arXiv references used in this note:

- **Geifman, Y. & El-Yaniv, R.** *Selective Classification for Deep Neural
  Networks.* NeurIPS 2017. arXiv:1705.08500. — foundational
  trade-coverage-for-accuracy framework.
- **Geifman, Y. & El-Yaniv, R.** *SelectiveNet: A Deep Neural Network
  with an Integrated Reject Option.* ICML 2019. arXiv:1901.09192. —
  end-to-end training of the rejection head.
- **Guo, C., Pleiss, G., Sun, Y. & Weinberger, K. Q.** *On Calibration
  of Modern Neural Networks.* ICML 2017. arXiv:1706.04599. — temperature
  scaling, ECE, reliability diagrams.
- **Kadavath, S. et al.** *Language Models (Mostly) Know What They Know.*
  2022. arXiv:2207.05221. — P(True), self-evaluation, calibration of LLMs.
- **Wang, X., Wei, J., Schuurmans, D., et al.** *Self-Consistency
  Improves Chain of Thought Reasoning in Language Models.* ICLR 2023.
  arXiv:2203.11171. — same-model sampling ensemble; explicitly *not*
  what this pattern does.
- **Shazeer, N. et al.** *Outrageously Large Neural Networks: The
  Sparsely-Gated Mixture-of-Experts Layer.* ICLR 2017. arXiv:1701.06538. —
  learned routing across experts; contrast with our hand-written Arbiter.
- **Fisch, A., Jaakkola, T. & Barzilay, R.** *Calibrated Selective
  Classification.* TMLR 2022. arXiv:2208.12084. — joint calibration +
  selective prediction objective.

Recent (2024–2025) related work that informed the design but is *not*
load-bearing for any specific claim:

- *LENS: Learning Ensemble Confidence from Neural States for
  Multi-LLM Answer Integration* (arXiv:2507.23167) — confidence
  aggregation across heterogeneous LLMs.
- *Beyond Majority Voting: LLM Aggregation by Leveraging Higher-Order
  Information* (arXiv:2510.01499) — explicitly argues majority vote
  is suboptimal when models are correlated; supports our decision to
  use *different sub-tasks* rather than vote.
- *Debate or Vote: Which Yields Better Decisions in Multi-Agent
  Systems* (arXiv:2508.17536) — empirical comparison of multi-agent
  debate vs aggregation.

We did not find a production deployment of this exact pattern in
the public literature, which is part of why the Mission Desk
should publish its evaluation data.

## 9. Reference Python skeleton

A typed, importable skeleton for `spacesharks/core/arbiter.py`. This
improves on the project lead's initial sketch by:

- typing inputs via `typing.Protocol` so the Arbiter is decoupled from
  any specific LLM client,
- returning a `dataclass` instead of a `dict` for static type safety,
- making thresholds constructor parameters rather than module
  globals, and
- separating the disagreement function as a strategy so it can be
  unit-tested in isolation.

```python
# spacesharks/core/arbiter.py
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, Sequence


class Decision(str, Enum):
    MONITOR = "MONITOR"
    RECOMMEND = "RECOMMEND"
    ESCALATE = "ESCALATE"
    ABSTAIN = "ABSTAIN"


class ModelOutput(Protocol):
    """Minimal shape every small-model response must satisfy."""
    responded: bool
    confidence: float            # 0.0..1.0, calibrated if possible
    latency_ms: int
    model_id: str
    # Each role narrows `value` further; see ClassifierOutput etc.


@dataclass(frozen=True)
class ArbiterOutput:
    decision: Decision
    reason: str
    klass: str | None = None
    risk: float | None = None
    action: str | None = None
    escalation_payload: dict | None = None
    evidence: dict = field(default_factory=dict)


HIGH_RISK_CLASSES: frozenset[str] = frozenset({"SPACE_WEATHER", "CONJUNCTION"})


@dataclass(frozen=True)
class Arbiter:
    tau_cls: float = 0.70
    r_high: float = 7.0
    r_mid: float = 4.0
    disagreement_threshold: float = 0.30
    high_risk_classes: frozenset[str] = HIGH_RISK_CLASSES

    def decide(
        self,
        classifier: "ClassifierOutput",
        risk: "RiskOutput",
        drafter: "DrafterOutput",
        disagreement_fn,
    ) -> ArbiterOutput:
        if not all(m.responded for m in (classifier, risk, drafter)):
            return ArbiterOutput(Decision.ABSTAIN, "model_timeout")

        if classifier.value == "UNKNOWN" or classifier.confidence < self.tau_cls:
            return ArbiterOutput(Decision.ABSTAIN, "low_classifier_confidence")

        d = disagreement_fn(classifier, risk, drafter)
        if d > self.disagreement_threshold:
            if classifier.value in self.high_risk_classes:
                return ArbiterOutput(
                    Decision.ESCALATE,
                    "high_stakes_disagreement",
                    klass=classifier.value,
                    escalation_payload={"a": classifier, "b": risk, "c": drafter},
                )
            return ArbiterOutput(Decision.ABSTAIN, "ensemble_disagreement")

        if risk.value >= self.r_high and classifier.value in self.high_risk_classes:
            return ArbiterOutput(
                Decision.ESCALATE,
                "agreement_high_risk",
                klass=classifier.value,
                risk=risk.value,
                escalation_payload={"a": classifier, "b": risk, "c": drafter},
            )

        if risk.value >= self.r_mid:
            return ArbiterOutput(
                Decision.RECOMMEND,
                "agreement_mid_risk",
                klass=classifier.value,
                risk=risk.value,
                action=drafter.value,
            )

        return ArbiterOutput(Decision.MONITOR, "agreement_low_risk",
                             klass=classifier.value, risk=risk.value)
```

`ClassifierOutput`, `RiskOutput`, and `DrafterOutput` are role-specific
`@dataclass` subclasses that fix the type of `value` (`str`, `float`,
`str` respectively). `disagreement_fn` is injected so the same Arbiter
can be tested against multiple coherence policies.

## 10. Failure modes and defaults

| Failure mode | Detection | Default behaviour |
|---|---|---|
| Model A/B/C never responds before timeout | `m.responded == False` | `ABSTAIN("model_timeout")` |
| Classifier returns class outside the enum | post-validation against `Set[str]` | treat as `UNKNOWN` → `ABSTAIN("low_classifier_confidence")` |
| Classifier confidence is `NaN` or out of `[0,1]` | numeric check | treat as 0 → abstain |
| Risk scorer returns `NaN` / non-finite | `math.isfinite(b.value)` | abstain |
| Risk scorer returns value outside `[0, 10]` | range clamp + log | clamp to `[0, 10]`, log warning |
| Drafter returns an action verb outside the allowlist | regex/set check | replace with `"hold"` and log; treat as drafter contradiction in §5 |
| Drafter returns >280 chars | length check | truncate at 280, log warning |
| Two of three responded but one timed out | `responded` flags | `ABSTAIN("model_timeout")` — never proceed on 2-of-3 |
| All three respond but the classifier confidence is 1.0 (suspicious) | confidence bucket = `>0.99` | proceed but log `suspicious_perfect_confidence` for offline review |

The bias is uniform: **prefer to abstain**. The cost of an abstention
during a hackathon demo is a "monitor-only" row in the timeline; the
cost of a false recommendation is the entire trust pitch.

## 11. Calibration evaluation plan (Day 4)

The Day 4 scoreboard must answer: *is the ensemble honest?*

**Required metrics**

- **Classifier Brier score** on the held-out ground truth, pre- and
  post-temperature-scaling. Target: post < pre, ideally < 0.15 on a
  6-class problem (uninformative baseline ≈ 0.83).
- **Classifier reliability diagram** (Guo et al. 2017): 10 confidence
  bins on the x-axis, empirical accuracy on the y-axis. The diagonal
  is perfect calibration; we plot pre- and post-temperature-scaling.
- **Risk-score MAE** vs labelled risk (where ground truth is available)
  and **risk-score rank correlation** (Spearman ρ) where it is not.
- **Abstention rate**, broken down by reason
  (`model_timeout`, `low_classifier_confidence`, `ensemble_disagreement`).
  A healthy demo run is roughly 5–25% abstain — much lower implies the
  thresholds are too loose, much higher implies the small models are
  underpowered for the feed.
- **Escalation rate** to Nemotron. Target: well under 10% of events,
  so the cost story in §6 holds.
- **Selective accuracy** (Geifman & El-Yaniv): accuracy on the
  *non-abstained* subset. Should monotonically improve as we tighten
  `TAU_CLS` and `DELTA`.
- **Replay completeness**: every output row in the log can be
  reconstructed from the input event + Arbiter config snapshot. This is
  a binary pass/fail.

**Outputs to ship with the demo**

- `scoreboard.json` — one row per metric above, with timestamps.
- `reliability_pre.png`, `reliability_post.png` — the two reliability
  diagrams.
- `abstention_breakdown.png` — stacked bar of abstention reasons over
  the demo window.
- A short note in `docs/research/scoreboard-notes.md` explaining what
  was tuned, what was held out, and which decisions were judgement
  calls rather than data-driven.

The pattern is only worth its complexity if the scoreboard says so.
That is the whole bet of this design.
