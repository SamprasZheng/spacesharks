---
title: Spacesharks Trust Stack — four-layer reliability synthesis
type: research
category: synthesis
status: ingested
ingested: 2026-05-24
sources:
  - ../TRUST.md
  - ../ARCHITECTURE.md
  - ../SCOPE.md
  - small-model-ensemble-arbiter.md
  - calibrated-confidence.md
  - tiered-inference.md
  - agentic-provenance.md
---

# Trust Stack — Reliability by Design, Not by Model Size

> Cross-doc synthesis. The pitch lives in [TRUST.md](../TRUST.md); the runtime
> lives in [ARCHITECTURE.md](../ARCHITECTURE.md); each of the four layers
> below has a dedicated research note in this directory.

## 1. Thesis

Spacesharks does not win the trust argument by renting a larger model. It wins
by demonstrating that a **disciplined, instrumented, multi-model system**
produces more trustworthy operator decisions than any single oversized model —
at lower cost, with auditable provenance, and with calibrated honesty about
what it does not know.

"Largest-model" is commoditised. Trust architecture is not: it requires
schema design, evaluation discipline, and the kind of provenance plumbing
that only pays off after weeks of accumulated logs. The whole MVP is sized
around proving that loop in one window — see [SCOPE.md](../SCOPE.md).

## 2. The four layers

Each layer has a concrete artifact in the repo and a metric on the scoreboard.

| Layer | Guarantees | Research note | Suggested metric |
|---|---|---|---|
| 1. Data | every input is sourced, timestamped, parser-versioned, evidence-anchored | [agentic-provenance.md §Layer 1](agentic-provenance.md) + [noaa-swpc-api.md](noaa-swpc-api.md) / [space-track-cdm-api.md](space-track-cdm-api.md) | `source_coverage`, `freshness_p50`/`p95`, `audit_completeness` |
| 2. Model | multiple specialised small models cross-check; cost-aware escalation when they disagree | [small-model-ensemble-arbiter.md](small-model-ensemble-arbiter.md) + [tiered-inference.md](tiered-inference.md) | `calibration_per_tier`, `brier_score`, `escalation_rate_per_tier` |
| 3. Decision | every output is `(recommendation, confidence, evidence, disagreement, route)`; abstain is first-class | [calibrated-confidence.md](calibrated-confidence.md) | `recommendation_acceptance_rate`, `abstention_rate_by_class` |
| 4. System | sandbox audit log is the single source of truth; out-of-process enforcement; tamper-evident policy hash | [agentic-provenance.md §Layer 4](agentic-provenance.md) | `audit_completeness`, `denied_action_count` |

The metric column intentionally maps onto the existing `TRUST.md` "Suggested
metrics" list. The stack is real only if it shows up on the scoreboard.

## 3. How the layers interlock

Each layer's output feeds the next layer's input. The chain is what makes the
system defensible; any single layer in isolation is unconvincing.

```
Layer 1 (Data)            Layer 2 (Model)              Layer 3 (Decision)      Layer 4 (System)
─────────────────         ────────────────────         ─────────────────       ──────────────────
source_url                model_A.classify()           recommendation          audit_log_id
source_timestamp    ───▶  model_B.score()        ───▶  confidence       ───▶   policy_preset_hash
parser_version            model_C.recommend()          evidence_pointers       denied_actions[]
evidence_hash             arbiter.integrate()          disagreement_level
                          ensemble_disagreement        decision_route
                          tier_used
```

Invariants:

- **No output without provenance.** If any Layer 1 field is incomplete, Layer
  2 refuses to score. Enforced at the event-schema boundary.
- **No publish without confidence + agreement.** If Layer 3 confidence is
  below threshold or ensemble disagreement is above the per-decision-class
  ceiling, the decision route is `monitor-only` or `needs-review`, never
  `publish`. See [calibrated-confidence.md §Abstention as a first-class
  output](calibrated-confidence.md).
- **No action without audit.** If Layer 4 cannot write to the audit log, the
  agent aborts the action. Out-of-process enforcement guarantees the agent
  cannot suppress its own audit trail.

The chain is **fail-closed**: a missing field in any layer downgrades the
output, never upgrades it. This is the operational difference between a
copilot judges can trust and a demo that looks impressive but cannot be
re-derived.

## 4. The three-specialist arbiter (Layer 2 interior)

Inside Layer 2, the [small-model-ensemble-arbiter](small-model-ensemble-arbiter.md)
pattern is the engineered substrate:

- **Model A — classifier** (cheap, e.g., 9B-class): event type + confidence
- **Model B — risk scorer** (cheap-medium, e.g., 7–14B class): severity score + confidence
- **Model C — action drafter** (cheap-medium): one-sentence recommendation + confidence
- **Arbiter** (deterministic rule + thresholds): integrates A+B+C into
  `decision_route ∈ {publish / monitor-only / needs-review / escalate}` plus
  a `disagreement_score`

This is **not majority vote** — each model has a different role and a
different output space. The arbiter weights by role-confidence, not by
count. Draw the three specialists from **different base-model families**
(e.g., Llama, Mistral, Phi) so correlated-error modes do not silently
dominate; this is the practical guard against the "ensemble of clones"
failure mode that majority voting on copies of the same model exhibits.

## 5. Tiered inference is the cost-control spine

The arbiter triggers [tiered-inference](tiered-inference.md) escalation;
together they handle the routine load on T1 and reserve expensive inference
for events that warrant it.

| Tier | Model class | Steady-state load | Trigger to escalate |
|---|---|---|---|
| T1 | 8–14B (e.g., Llama-3.1-8B, Phi-3-mini, Hermes-4 14B) | ~80% (CDM screen, NOTAM parse, summary tasks) | Low inter-model agreement OR confidence below threshold |
| T2 | 49–70B (e.g., Nemotron Super 49B, Hermes-4 70B) | ~15% (ambiguous classifications) | Red Pc event OR high-impact asset OR T2 itself returns medium-confidence |
| T3 | 253–405B (e.g., Nemotron Ultra 253B, Hermes-4 405B) | ~5% (red events, crewed proximity, novel event types) | Manual review or arbiter escalation |

Published evidence that the cascade pays off: FrugalGPT reports up to **98%
cost reduction** at accuracy parity vs always-best-model; RouteLLM reports
**>75% cost reduction** on MT Bench; Together MoA reports **65.1% on
AlpacaEval 2.0** with only open-source models, beating closed-model
baselines. See [tiered-inference.md §Published Analogues](tiered-inference.md)
for the verified citations.

## 6. Calibration and abstention are the honesty layer

The trust stack is meaningless if the system claims high confidence on
outputs it cannot defend. [calibrated-confidence.md](calibrated-confidence.md)
specifies the three-class output schema (`answer` / `abstain` / `escalate`)
and the calibration techniques (temperature scaling, P(IK), conformal
prediction, selective prediction) that make stated confidence empirically
meaningful.

The operational test is direct: a 70%-confidence output should be correct
~70% of the time over the live scoreboard window. The `calibration_per_tier`
metric measures this directly; the `brier_score` metric penalises
overconfident wrong answers more than underconfident right answers. Both are
computed nightly from event-schema rows — no manual curation.

The hard rule, lifted from TRUST.md: **when the arbiter's `disagreement_score`
exceeds the per-decision-class ceiling, the output is `abstain` with a
logged trigger reason, never a published recommendation.** Abstention is
auditable evidence that the threshold is real, not decorative.

## 7. Why this beats "I have the biggest model"

The argument structure for any reviewer:

1. **Cost.** Tiered inference + small-model specialists run at a small fraction
   of always-top-tier cost. Energy footprint is materially lower for a 24/7
   ops loop on a single workstation-class box.
2. **Reliability.** Multiple specialised models cross-check each other;
   correlated-failure modes are mitigated by drawing from different base
   families. Disagreement is a first-order operational input, not a
   discarded artefact.
3. **Honesty.** Calibrated confidence and explicit abstention make the
   scoreboard credible — reviewers can see what the desk does NOT know, not
   just what it claims.
4. **Provenance.** Every recommendation is reproducible to a raw byte. The
   labelled lifecycle-event dataset becomes commercially defensible because
   each row is independently verifiable, not because the corpus is large.
5. **Containment.** NemoClaw enforces the safety boundary out-of-process;
   the agent cannot suppress its own audit trail. This is the structural
   property that makes the rest of the stack worth anything —
   instrumentation an attacker can disable is no instrumentation at all.

The pitch is not "we used the most powerful model." The pitch is **"we built
a system that is correct, honest, cheap, and auditable — and the dataset
that falls out of it is the moat."**

## 8. Scope discipline — the five words

From `SCOPE.md` distilled to five operational primitives. If a feature does
not directly serve one of these, it is out of scope for the hackathon
window:

- `NemoClaw` — sandbox + audit (Layer 4)
- `OpenClaw` — always-on runtime + 24/7 ingest (Layer 1 input loop)
- `small-model ensemble` — multi-model arbiter (Layer 2)
- `provenance` — reproducible evidence chain (Layer 1 + cross-layer)
- `24/7 ops loop` — continuous operation; the property that makes lossy
  logs catastrophic per [agentic-provenance.md §3](agentic-provenance.md)

## 9. Relationship to existing spacesharks docs

This synthesis intentionally does NOT redefine:

- **The runtime flow** — lives in [ARCHITECTURE.md](../ARCHITECTURE.md)
- **The trust narrative** — lives in [TRUST.md](../TRUST.md)
- **The build sequence** — lives in [PLAN.md](../PLAN.md)
- **The scope boundary** — lives in [SCOPE.md](../SCOPE.md)
- **The arbiter mechanics** — live in [small-model-ensemble-arbiter.md](small-model-ensemble-arbiter.md)

If anything on this page conflicts with the canonical page above, the
**canonical page wins**. This page exists to make the four-layer story
legible end-to-end without forcing a reader to assemble it themselves.
