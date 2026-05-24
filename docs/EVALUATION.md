# Evaluation

This is how Spacesharks scores its own predictions, recommendations, and overall operational quality. It is the missing layer between predict / recommend / score and any honest answer to "did the desk get it right?"

The rubric is **honest by construction**: every metric here is computable from rows in the event schema. No manual curation. No cherry-picked windows. If a metric can't be derived from schema rows, it doesn't go on the scoreboard.

> Canonical version: `yxz/wiki/concepts/spacesharks-mission-desk-evaluation-rubric.md`. This file is the build-side reference.

## Two scoring tracks

Keep them separate. Conflating them is the fastest path to a misleading scoreboard.

- **Prediction track** — falsifiable forecasts committed before the predicted window opens. Slip probability, decay ETA, conjunction Pc, safe-mode timing. Scored after the window closes.
- **Recommendation track** — operator-facing action proposals. Scored two ways simultaneously: was it accepted? did the accepted action improve on the no-action baseline?

## Prediction hit rate

**Denominator.** Every prediction row where `verifiable_by_t` is set and has now passed. Predictions still inside their window are excluded. Predictions written without `verifiable_by_t` are permanently ineligible — no backfilling after outcomes are known.

**Numerator.**

- Probabilistic predictions hit when the observed value falls inside the stated confidence interval.
- Classification predictions hit when the categorical output matches the observed category.

**Calibration check.** Bucket by stated `confidence` tier and compare per-bucket hit rate to the expected range:

| Tier | Expected | Failure threshold |
|---|---|---|
| `high` | ≥ 80% | < 65% |
| `medium` | 50–79% | < 40% |
| `low` | 30–49% | < 20% |

A `high` bucket scoring 60% is a calibration failure even when the raw count looks good. Calibration failures appear on the scoreboard alongside the headline hit rate, not buried.

**Brier score.** For every probabilistic prediction, also compute mean squared error against the binary outcome. Baseline floor for random binary guessing is 0.25. A score at or above 0.25 means no better than chance on that prediction class.

## Recommendation scoring

**Acceptance rate.**

```
acceptance_rate = accepted / (accepted + dismissed)
```

Source: the `review_status` field. During the hackathon window the operator (Sampras) plays the simulated reviewer. The desk commits its draft before the operator marks accept/dismiss, so there's no feedback leak.

Dismissed recommendations are never deleted. They stay in the denominator permanently.

**Outcome delta.**

```
outcome_delta = baseline_loss - actual_loss
```

Loss is task-specific:

| Decision | Loss |
|---|---|
| Safe-mode trigger | Unsaved telemetry seconds vs. avoided radiation seconds |
| Momentum dump | Wheel saturation minutes vs. fuel spent on the dump |
| Conjunction triage | Probability-weighted collision consequence vs. manoeuvre delta-v |
| Launch slip pre-alert | Cascade schedule delay vs. operator planning cost |

`outcome_delta > 0` means the accepted action improved on baseline. Aggregate per phase, then normalise by the number of accepted recommendations in that phase.

## False positive / false negative

Cost is asymmetric. Set thresholds accordingly. Report precision and recall separately for recall-favoured decisions; F1 alone hides which direction the model is failing.

| Decision | FP cost | FN cost | Bias |
|---|---|---|---|
| Safe-mode trigger | Low (lost ops minutes) | High (radiation damage, often irreversible) | Recall-favoured |
| Momentum dump | Medium (fuel) | Medium (wheel saturation, recoverable) | Balanced |
| Conjunction triage | Medium (manoeuvre delta-v) | Catastrophic (collision) | Recall-favoured |
| Launch slip pre-alert | Low (operator time) | Medium (cascade delay) | Precision-favoured |

## The public scoreboard

Hit rate alone is gameable by cherry-picking a small number of obvious events. The judge-visible scoreboard shows all ten metrics side by side.

| Metric | Definition |
|---|---|
| `prediction_hit_rate` | Numerator / denominator from above |
| `calibration_per_tier` | Hit rate within each confidence bucket |
| `brier_score` | Mean (predicted_prob − outcome_binary)² |
| `recommendation_acceptance_rate` | Accepted / (accepted + dismissed) |
| `outcome_delta_aggregate` | Sum of `outcome_delta` per phase, normalised |
| `source_coverage` | Distinct `source_type` values in last 24h ÷ enum cardinality |
| `freshness_p50` / `freshness_p95` | Time from `event_time` to first ingest, median + tail |
| `audit_completeness` | Rows with resolvable `evidence_hash` ÷ total rows |
| `denied_action_count` | Sandbox-denied tool calls in the `NemoClaw` audit log |
| `agent_authored_skill_count` | Files in `~/.hermes/skills/` created after build start |

All ten are computed nightly from the live event schema. No metric requires manual operator input.

> 100% hit rate on 3 cherry-picked events is worse than 70% on 100 diverse events. Show the columns to the right of `prediction_hit_rate` and the headline number becomes interpretable.

## Honest-scoring guardrails

These self-imposed constraints exist so the scoreboard can't be gamed after the fact.

- `confidence` on a prediction row is immutable after write
- Dismissed recommendations are never deleted; they remain in every denominator
- `verifiable_by_t` must be set before the predicted event window opens; missing this field permanently disqualifies the row
- A nightly job re-hashes every stored evidence blob; mismatches flip `review_status` to `needs-human-review`
- Hackathon-window misses stay on the board

## What this rubric is not

- Not a market or investment scoring framework. Investment predictions are deliberately deferred per SCOPE.md.
- Not retroactive labelling. A schema row with no matching prediction row written before `verifiable_by_t` cannot be claimed retrospectively as a hit.
- Not phase-agnostic. On-orbit ops predictions dominate by volume; they test different capabilities than pre-launch slip prediction. Disaggregate by phase before averaging.
