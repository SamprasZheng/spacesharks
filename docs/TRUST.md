# Trust Model

The system should be trusted because it is observable, calibrated, and willing to abstain.

Each layer below has a corresponding **operational research note** in `docs/research/` with field tables, runnable Python, and references. This page is the *pitch*; the notes are the *contracts*.

## Trust layers

### 1. Source trust → [agentic-provenance.md](research/agentic-provenance.md) §2 Layer 1

- Every event stores its source URL
- Every event stores its timestamp
- Every parser version is recorded
- Every derived field keeps an evidence trail (SHA-256 content-addressed blob)

### 2. Model trust → [small-model-ensemble-arbiter.md](research/small-model-ensemble-arbiter.md) + [tiered-inference.md](research/tiered-inference.md)

- Use multiple small models for different sub-tasks (three-specialist arbiter)
- Require confidence scores from each model
- Treat disagreement as a signal, not noise (first-class abstention trigger)
- Escalate to `Nemotron` when the case is uncertain or high risk (T1 → T2 → T3 cascade with four explicit triggers)

### 3. Decision trust → [calibrated-confidence.md](research/calibrated-confidence.md)

- Never output a recommendation without evidence (`evidence_pointers` field required)
- Include confidence and disagreement level with the answer
- Prefer abstention over a forced guess (three-class `answer / abstain / escalate` output schema)
- Degrade to "monitor only" when the ensemble is not aligned
- Coverage–risk operating point set **per decision class**, not globally

### 4. System trust → [agentic-provenance.md](research/agentic-provenance.md) §2 Layer 4

- Keep all actions inside `NemoClaw` (out-of-process audit log; agent cannot suppress its own trail)
- Keep the runtime alive in `OpenClaw`
- Log all outputs, failures, and escalations (`audit_completeness` scoreboard metric)
- Make the full event chain replayable (5-tuple reproducibility invariant)

## Ensemble policy

A simple version:

| Condition | Action |
|---|---|
| High agreement and moderate risk | Recommend |
| Low agreement | Abstain |
| High risk and low confidence | Escalate to Nemotron |
| No clear evidence | Monitor only |

### Specialist-family rule

The three specialists inside Layer 2 (classifier / scorer / recommender) must be drawn from **different base-model families** (e.g., Nemotron + Qwen-3 + Mistral-derivative). Correlated error from a single family silently collapses the ensemble back to one model — the arbiter cannot detect this because it sees outputs, not weights.

If only one family is available at integration time, mark the ensemble `degraded: same-family` in the audit log and downgrade every output by one confidence tier.

### Tiered inference

| Tier | Model class | Target share | Escalation trigger |
|---|---|---|---|
| T1 | Nemotron Nano 2 9B / Hermes-4 14B | ~80% | inter-model agreement low OR confidence below threshold |
| T2 | Nemotron Super 49B / Hermes-4 70B | ~15% | red Pc event OR high-impact asset OR T2 returns medium confidence |
| T3 | Nemotron Ultra 253B / Hermes-4 405B | ~5% | manual review only |

If T1 share drops below 70% in any 6h window, review Layer 3 calibration thresholds before assuming workload changed.

## Fail-closed invariants

Three rules govern how the four layers interact. A missing field at any layer downgrades the output, never upgrades it.

1. **No output without provenance.** Incomplete Layer 1 fields → Layer 2 refuses to score.
2. **No publish without confidence + agreement.** Low Layer 3 confidence OR high ensemble disagreement → route is `monitor-only` or `needs-review`, never `publish`.
3. **No action without audit.** If Layer 4 cannot write to the audit log, the action aborts.

See [`INVARIANTS.md`](INVARIANTS.md) for the full operational rule set.

## What to show reviewers

- The system can explain itself
- The system can reject uncertain cases
- The system can run cheaply enough to be practical
- The system improves trust through evidence, not through hype

## Suggested metrics

- source coverage
- latency
- abstention rate
- escalation rate
- recommendation acceptance rate
- replay completeness
