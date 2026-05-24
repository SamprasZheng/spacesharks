# Spacesharks Mission Desk

> A low-cost, traceable satellite operations copilot that turns public space signals into actionable recommendations.

Spacesharks is built around one core idea: do not rely on a single expensive model to guess what is happening in orbit. Instead, use a safe runtime, multiple lightweight models, and provenance-first event logging to produce recommendations that operators can inspect, replay, and trust.

## Why this matters

Satellite operations span many fragile signals: space weather, conjunctions, launch slips, regulatory notices, and orbital decay. Those signals are scattered across many sources and rarely organized into a decision loop that is:

- continuous
- source-linked
- cost-aware
- safe to run for long periods

Spacesharks is the attempt to close that gap.

## Core stack

- `NemoClaw`: sandbox and policy boundary
- `OpenClaw`: 24/7 realtime / long-run execution layer
- `Nemotron`: primary reasoning model for higher-trust decisions
- Small-model ensemble: classification, scoring, and recommendation support
- `OpenRouter`: optional cost fallback when a lighter route is enough

## What the system does

1. Ingests a small set of high-value public signals
2. Normalizes them into timestamped events
3. Runs a lightweight ensemble to classify, score, and draft recommendations
4. Escalates uncertain or high-risk cases to stronger reasoning
5. Stores every event, decision, and disagreement in a replayable log

## What this repository should prove

- The runtime can stay up for 24 hours without manual babysitting
- The system can produce useful recommendations at low cost
- Every recommendation can be traced back to evidence
- Lightweight models plus arbitration can be more practical than a single large model

## Docs

- [**Pitch — Spacesharks Mission Desk**](docs/PITCH.md) — canonical submission narrative (5-word scope, problem, solution, architecture diagram, Day 1 code shape)
- [Scope and non-goals](docs/SCOPE.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Trust model](docs/TRUST.md)
- [Hackathon plan](docs/PLAN.md)
- [Roadmap (post-MVP)](docs/ROADMAP.md) — phased expansion grounded on existing RF, thermal-mechanical, and signal-processing work. Read only after the MVP is shipped; nothing here belongs in the hackathon scope.
- [Local research catalog](docs/research/INDEX.md) — index of local `D:\` material that feeds the roadmap.
- [Research notes](docs/research/index.md)

## Status

Scaffold stage. The current goal is to keep the scope narrow enough to ship, while preserving a larger roadmap for later phases.
