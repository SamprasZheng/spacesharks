# Hackathon Plan

This plan is intentionally narrow. The goal is to prove one trustworthy loop, not to build the full satellite lifecycle platform in four days.

## Outcome to prove

Deliver a working satellite operations copilot that:

- runs safely in `NemoClaw`
- stays alive in `OpenClaw` for 24 hours
- uses a small-model ensemble for low-cost reasoning
- escalates uncertain cases to `Nemotron`
- produces traceable recommendations with event-level provenance

## Build sequence

### Day 1

- Lock the scope to one core ops scenario (safe-mode trigger recommendation)
- Define the event schema and commit it before writing any ingestor
- Stand up the runtime boundary and logging path
- Lock the first-version source list to four hosts: `celestrak.org`, `swpc.noaa.gov`, `tfr.faa.gov`, plus one case-study satellite set
- Build **2 complete ingestors** (Celestrak + NOAA SWPC) and **3 schema-conformant stubs** (CDM, NOTAM, launch manifest) that parse only the first field

### Day 2

- Implement the ensemble loop with three specialists from different base-model families
- Add arbitration, abstain rules, and the T1 / T2 / T3 escalation cascade
- Wire the primary decision (safe-mode trigger) and the secondary (conjunction triage) end to end
- Decay ETA is built but stays in the dataset preview — no demo screen time
- Verify the event log can be replayed
- Start the continuous-runtime test before end of day

### Day 3

- Build the demo narrative; pick 3–5 best moments
- Stage one denied action in NemoClaw (audit row captured)
- Stage one structured debate (`event_id`, `cited_wiki_pages`, structured resolution — no free-form theatre)
- Promote 1–2 `draft` items to `auto-published` through the 30-min cancel window so the gate is visible
- Verify `~/.hermes/skills/` contains ≥ 2 agent-authored skills

### Day 4

- Architecture is frozen — no event log shape edits today
- Record the handdrawn walkthrough video
- Polish the README and diagrams
- Validate the live 24h behaviour
- Bring the ten-metric scoreboard live (hit rate, calibration per tier, Brier, recommendation acceptance, source coverage, freshness p50/p95, audit completeness, denied-action count, agent-authored skill count, abstention rate)
- Package the submission and record the retrospective

## Deliverables

- One clear demo loop
- One architecture diagram
- One trust / confidence explanation
- One replayable event log
- One concise submission narrative

## Publish-gate rules

Auto-publish is gated. Hard ceiling: ≤ 3 auto-published items per 24 hours during the hackathon window.

| Confidence × Significance | Route |
|---|---|
| `high` + above-threshold | 30-minute human-cancel window → auto-publish if uncanceled |
| `high` + below-threshold | `draft` until a human promotes |
| `medium` | `draft` until a human promotes |
| `low` | `internal-log-only` |

The cancel-window timer must be visible during the demo.

## Non-goals

- No full lifecycle coverage
- No automated real-world actuation
- No trading or investment framing
- No large source crawl on day one
- No dependency on the most expensive model for every step
- No fifth ingestion source inside the hackathon window without explicit owner approval
- No autonomous publishing without a 30-min cancel window
- No free-form debate output

See [`INVARIANTS.md`](INVARIANTS.md) for the full operational rule set.
