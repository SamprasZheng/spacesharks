# Governance

This is the rulebook for what Spacesharks may publish autonomously, what it must hold for human review, and how the debate and denied-action behaviours surface without becoming noise.

The posture is **suggested-by-default, autonomous-by-exception**. Noisy automation is the failure mode for always-on agents. A high-signal scoreboard is more compelling than a wall of auto-posts.

> Canonical version: `yxz/wiki/concepts/spacesharks-mission-desk-governance.md`. This file is the build-side reference.

## Tiered publish policy

The governance layer sets `review_status` at ingest based on `confidence` (from the schema) and an event significance score (unusual magnitude, novel sat/phase combination, or decision confidence ≥ 0.85).

| Confidence | Significance | Destination | Human gate |
|---|---|---|---|
| `high` | above-threshold | `blog/` draft → auto-published after a 30-min cancel window | Soft (publish if no cancel) |
| `high` | below-threshold | `blog/` draft, held indefinitely | Hard (operator approval) |
| `medium` | any | `blog/` draft only, never auto-published | Hard |
| `low` | any | `data/lifecycle-events/*.jsonl` only — never propagates | None (never leaves the desk) |

### Why the 30-min cancel window

It's the only path to true autonomous publishing during long-running demos without making the governance layer theatre. A disagreeing operator has thirty minutes to press cancel; absent that, the scheduler publishes and logs the non-action as implicit approval. Cancel is the tripwire — small enough to respect operator time, large enough to catch real errors before they go public.

### Why medium never auto-publishes

Calibration is fragile at distribution boundaries. Medium-tier hit rates degrade fastest under distribution shift. The reputational cost of a false claim under the desk's own byline outweighs the throughput cost of holding for review.

### Calibration auto-downgrade gate

If `calibration_per_tier` for the `high` bucket drops below 70% over a rolling 7-day window, **all** `high` rows downgrade to `medium` policy until calibration recovers. The nightly evaluation job enforces this; the agent at ingest time cannot override the demotion. The operator restores the `high` tier explicitly after reviewing the failure cases.

## `review_status` lifecycle

The enum is `auto-published | draft | internal-log-only | needs-human-review | dismissed`. Who can make each transition matters as much as the transition itself.

- **Initial state** — set by the governance layer at ingest. The agent does not write `review_status` directly.
- **`draft` → `auto-published`** — scheduler only, after the 30-min cancel window expires and the tier hasn't been auto-downgraded.
- **Any → `needs-human-review`** — nightly evidence re-hash job (on hash mismatch) or contradiction-detector (against prior wiki/doc claim). The agent must not self-flag — that's a trivially gameable self-exemption loop.
- **Any → `dismissed`** — explicit human action only. Dismissed rows stay in the JSONL and SQLite mirror with a `dismissed_at` timestamp.
- **`auto-published` is terminal for publishing** but mutable for evaluation: `operator_action_taken`, `outcome`, and `outcome_delta` get backfilled retrospectively.

## Denied-action audit

`NemoClaw` is the lower governance layer. It enforces what the agent is physically allowed to do regardless of what its own policy says. Treat the sandbox as a first-class governance surface, not a backstop.

- Every denied tool call increments `denied_action_count` on the scoreboard. A desk that never triggers a denial has a permissive policy file, not a secure one.
- The agent **must** deliberately stage at least one denied action during the hackathon window — typically a `curl` to a non-allowlisted domain. The audit row is captured and committed as evidence the policy is restrictive, not just present.
- Repeated denial of the same domain (5+ within 1h) auto-creates a `needs-human-review` row with `source_type: derived`. Semantic: the desk is asking the operator "policy gap, or am I doing something I shouldn't?"

## Debate format

The two-agent (Jamia × Spacesharks) debate is good demo material because it surfaces genuine disagreement between a commercial/policy lens and an operator/engineering lens. Free-form transcripts are not demo material — they're theatre. These constraints turn debate into a reviewable artefact.

Every debate must resolve into this YAML before it's considered complete:

```yaml
debate_id: <ulid>
event_id: <links to a lifecycle event row>
participants: [jamia, spacesharks]
positions:
  jamia:
    stance: ...
    key_claims: [...]
    cited_wiki_pages: [...]
  spacesharks:
    stance: ...
    key_claims: [...]
    cited_wiki_pages: [...]
resolution: agreement | disagreement | escalated-to-human
```

Rules:

- Debates without a backing `event_id` are not shipped. Pure speculation doesn't get a stage.
- `cited_wiki_pages` on each position must contain at least one entry. Empty = opinion, not a reasoned stance. Reject.
- Disagreement and escalation are surfaced on the scoreboard with their own counter. A desk where the two voices always agree has a single point of view wearing two hats.
- Maximum one published debate transcript per 24h window. Additional debates stay `internal-log-only`.

## Contradiction handling

The desk follows the contradiction rule from the yxz wiki schema without exception.

- The older claim's page is flagged with the standard marker: `> **Contradicted** by [lifecycle-events/<event_id>]: <one-line note>`
- The new event row's `review_status` is forced to `needs-human-review` even if `confidence: high`. Contradictions always escalate.
- The desk never silently overwrites. The moat is provenance; silent overwrites destroy provenance. Every rewrite must leave a visible scar.

## Hackathon-window posture

More restrictive than long-run production: thin calibration history, judges watching for restraint.

**During the build:**

- Operator reviews every `draft` row at least once daily
- Auto-publish throttled to ≤ 3 rows per day
- Dismissed rows preserved with reason

**During the demo:**

- Scoreboard shows live counts for every `review_status` value
- Judges can click any `auto-published` row and trace it via `evidence_hash` to the raw payload
- The `NemoClaw` audit log excerpt showing at least one denied action is linked from the submission README

**Post-hackathon:**

- The cancel window may extend or contract based on calibration history
- Multi-operator review is a planned future feature; not in scope for the hackathon
- The nightly calibration gate stays active indefinitely
