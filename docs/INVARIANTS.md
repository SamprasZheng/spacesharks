# Invariants

> Operational rules an implementer must not break inside the hackathon window. Each rule has a one-line justification — if a rule appears arbitrary, re-read the justification before bending it.
>
> This file is the **quick-reference**. The full specifications live in:
> - [`EVENT_SCHEMA.md`](EVENT_SCHEMA.md) — row contract for Layer 1 provenance
> - [`EVALUATION.md`](EVALUATION.md) — the ten-metric scoreboard and honest-scoring guardrails
> - [`GOVERNANCE.md`](GOVERNANCE.md) — publish gate, debate format, denied-action policy
>
> If this file and a spec file disagree, the spec file wins. Update the spec first, then re-derive the invariant.

## Fail-closed invariants

These three rules govern how the four trust layers (see [`TRUST.md`](TRUST.md)) interact. A missing field at any layer downgrades the output, never upgrades it.

1. **No output without provenance.** If Layer 1 fields (`source_url`, `source_timestamp`, `parser_version`, `evidence_hash`) are incomplete, Layer 2 refuses to score. The event is queued, not silently dropped.
2. **No publish without confidence + agreement.** If Layer 3 confidence is below threshold *or* ensemble disagreement is above ceiling, the decision route is `monitor-only` or `needs-review`, never `publish`.
3. **No action without audit.** If Layer 4 cannot write to the audit log, the agent must abort the action. Out-of-process enforcement guarantees the agent cannot suppress its own audit trail.

The chain is fail-closed because every observable Spacesharks ships — scoreboard, dataset preview, denied-action log, agent-authored skills — depends on these three holding.

## Source-list lock (first version)

The first version of the desk ingests from exactly four hosts:

1. `celestrak.org` — orbit / TLE / event signals
2. `swpc.noaa.gov` — space weather (Kp, X-ray, SEP, ENLIL)
3. `tfr.faa.gov` — NOTAM (launch, regulatory, dynamic restrictions)
4. One case-study satellite set — telemetry, press release, vendor datasheet for the demo bird

**Other domains stay in the policy file as commented stubs.** Adding a fifth ingestor inside the hackathon window requires explicit owner approval, not a feeling that it would be nice to have.

Justification: 8+ ingestors burn the entire build budget on plumbing.

## Ingestor build rule: 2 complete + 3 stub

On Day 1, build **two complete ingestors** (Celestrak + NOAA SWPC) and **three schema-conformant stubs** (CDM, NOTAM, launch manifest) that parse only the first field.

Why this exact split:

- The data contract is exercised end-to-end on Day 1.
- The demo on Day 2 has at least two real data feeds backing the headline decision.
- The remaining three are pre-wired for Day 3–4 enrichment without re-architecting the loop.

Five half-baked ingestors looks broad but never demos cleanly. This pattern looks narrower but holds up under live review.

## Decision-loop discipline

Phase-4 (on-orbit ops) has four candidate decision verbs:

1. **Safe-mode trigger recommendation** — primary MVP, owns the demo video.
2. **Conjunction triage** — secondary, demo-ready because input → output → action is the cleanest causal chain.
3. **Decay ETA** — supplementary, built but not given screen time; sits in the dataset preview as proof of breadth.
4. **Momentum dump / interference attribution** — documented in `ROADMAP.md`, *not* shipped this window.

Only the first three exist as code paths in the MVP. The fourth is intentionally a roadmap row.

## Publish-gate rules

Auto-publish exists, but it is gated. No exceptions.

| Confidence × Significance | Route |
|---|---|
| `high` + above-threshold | Enter 30-minute human-cancel window → auto-publish if uncanceled |
| `high` + below-threshold | Stay `draft` until a human promotes |
| `medium` | Stay `draft` until a human promotes |
| `low` | `internal-log-only`; never enters the publish queue |

Hard ceiling: **≤ 3 auto-published items per 24 hours during the hackathon window.** This is a discipline rule, not a technical limit — it forces the demo to feature curated highlights rather than firehose output.

The 30-minute cancel window must be visible in the demo. A judge clicking on a draft should see the timer.

Full spec: [`GOVERNANCE.md`](GOVERNANCE.md).

## Specialist-arbiter rule

Inside Layer 2 of the trust stack, the three specialists (classifier / scorer / recommender) must be drawn from **different base-model families** (e.g., Nemotron + Qwen-3 + Mistral-derivative).

Justification: correlated error from a single base family silently collapses the ensemble back to a single model. The arbiter cannot detect this failure mode because it operates on outputs, not weights.

If only one model family is available at integration time, mark the ensemble as `degraded: same-family` in the audit log and downgrade every output by one confidence tier. This is the fail-closed posture for a Layer-2 degradation.

## Tiered-inference cascade

| Tier | Model class | Target steady-state share | Escalation trigger |
|---|---|---|---|
| T1 | Nemotron Nano 2 9B / Hermes-4 14B | ~80% | inter-model agreement low OR confidence below threshold |
| T2 | Nemotron Super 49B / Hermes-4 70B | ~15% | red Pc event OR high-impact asset OR T2 itself returns medium confidence |
| T3 | Nemotron Ultra 253B / Hermes-4 405B | ~5% | manual review only |

The percentages are targets, not hard quotas. If T1 share drops below 70% in any 6h window, the calibration thresholds in Layer 3 should be reviewed before assuming the workload changed.

## The five things judges actually see

Demo polish must serve these six artefacts and no others:

1. **Live scoreboard** with the full ten-metric set (hit rate, calibration per tier, Brier, recommendation acceptance, source coverage, freshness p50/p95, audit completeness, denied-action count, agent-authored skill count, abstention rate). Hackathon-window misses stay on the board uncurated. Full metric definitions: [`EVALUATION.md`](EVALUATION.md).
2. **Git history with agent-authored commits.** Author `spacesharks-mission-desk-bot`. Every committed dataset row and published blog draft.
3. **NemoClaw audit log excerpt.** At least one denied action visible, proving the policy file is real, not permissive.
4. **`~/.hermes/skills/` folder** with ≥ 2 agent-authored skills dated after the build started.
5. **`lifecycle-events.jsonl` first 100 rows.** Each row carries phase tag + source URL + timestamp.
6. **Suggested-publish queue.** The 30-min cancel-window timer is visible; one `draft → auto-published` transition is staged during the demo.

If a feature does not serve one of these six, it is out of scope for the hackathon window.

## Contradiction-handling rule

When the desk's prediction contradicts a prior wiki claim (per `wiki/AGENTS.md`), the older page is flagged with `> **Contradicted** by …` — never silently edited. This is a wiki-side rule that the desk must respect when emitting blog drafts or wiki updates.

Any contradiction event also flips `review_status` to `needs-human-review`, regardless of confidence. High-confidence contradictions are *more* likely to need review, not less.

## Out-of-scope reminders

For each item below, log to `ROADMAP.md` if a future phase wants it; do not let the hackathon window absorb it.

- Real trades, real broker emails, real ground-station commands.
- Real-time RF hardware integration (the X-band beamformer stays in Phase 1 territory).
- General space-news monitoring beyond the five lifecycle phases.
- Investment / trade recommendations as a demo surface.
- Silently overwritten wiki claims.
- More than four ingestion sources in the first version.
- Autonomous publishing without a 30-min cancel window.
- Free-form debate output without the structured artefact contract.

## How to use this document

When picking up an implementation task, read the matching section here *before* writing code. If a section feels wrong for the situation, the answer is to write a deliberate exception into the audit log (`override_invariant: <id> reason: <text>`) — not to silently break the rule.

Every override is reviewed at the Day 3 governance pass. Overrides without an audit row are themselves an invariant violation.
