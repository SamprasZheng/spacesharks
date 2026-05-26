# Spacesharks Mission Desk

> A low-cost Starlink fleet triage agent that turns public space signals into traceable satellite operations recommendations.

Spacesharks monitors a representative Starlink fleet, lets lightweight models flag the satellites that deserve attention, and escalates uncertain cases to `Nemotron` instead of paying large-model costs for every object.

## Why this matters

Starlink is the clearest public reference point for modern LEO operations: large fleet size, frequent public orbital updates, broad public interest, and real operational relevance. The hackathon version focuses on 50 Starlink satellites first, with a path to 100.

Satellite operations span many fragile signals: space weather, orbit changes, decay behavior, conjunction context, and fleet-level outliers. Those signals are rarely organized into a decision loop that is:

- continuous
- source-linked
- cost-aware
- safe to run for long periods

## Core stack

- `NemoClaw`: sandbox and policy boundary
- `OpenClaw`: 24/7 realtime / long-run execution layer
- `Nemotron`: escalation and referee model for higher-trust decisions
- Small-model ensemble: classification, scoring, and triage support
- `OpenRouter`: optional cost fallback when a lighter route is enough

## What the system does

1. Selects a Starlink sample fleet of 50 satellites
2. Adds small MEO/GEO reference sets only for comparison
3. Ingests public orbit, space-environment, and local knowledge signals at a practical cadence
4. Runs a five-model lightweight ensemble to classify, score, and draft triage notes
5. Escalates red or disputed cases to `Nemotron`
6. Produces today, 7-day, and 30-day fleet briefs with evidence links

## What this repository should prove

- The runtime can stay up for 24 hours without manual babysitting
- The system can identify the highest-risk Starlink objects at low cost
- Every recommendation can be traced back to evidence
- Lightweight models plus arbitration can be more practical than a single large model

## Docs

- [Scope and non-goals](docs/SCOPE.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Fleet strategy](docs/FLEET.md)
- [Product pages](docs/PRODUCT_PAGES.md)
- [Local knowledge](docs/LOCAL_KNOWLEDGE.md)
- [Model ensemble](docs/MODEL_ENSEMBLE.md)
- [Ideas to evaluate](docs/IDEAS_TO_EVALUATE.md)
- [Trust model](docs/TRUST.md)
- [Hackathon plan](docs/PLAN.md)
- [Event schema](docs/EVENT_SCHEMA.md)

## Status

Scaffold stage. The current goal is to ship one credible Starlink-first fleet triage loop before expanding to broader satellite lifecycle work.
