# Scope

## Goal

Prove that a safe, low-cost, multi-model system can triage a representative Starlink fleet and turn public space signals into trustworthy operator recommendations.

## In scope for the hackathon

- One core scenario: Starlink on-orbit fleet triage
- One public sample fleet: 50 Starlink satellites, expandable to 100
- Small reference sets for popular MEO/GEO objects, only for comparison
- One small set of signal sources: public orbit data plus space-environment context
- One local knowledge pack for model grounding
- One decision loop: ingest -> reason -> recommend -> log
- One audit trail for every recommendation
- One report loop: today, 7-day, and 30-day fleet brief

## What is deferred

- Full lifecycle automation
- Pre-launch, commissioning, and end-of-life depth
- Full MEO/GEO coverage or equal treatment with Starlink
- Claiming to know private Starlink telemetry
- Real spacecraft actuation
- Trading or investment positioning
- Broad source coverage
- Auto-publishing as the primary product

## Recommended first demo case

Use a Starlink fleet health flow:

- monitor 50 public Starlink objects
- compare against a small MEO/GEO reference set when useful
- rank satellites by risk
- highlight the red cases
- produce a today / 7-day / 30-day brief
- escalate disputed red cases to `Nemotron`

Why this case:

- Starlink is the most visible LEO constellation
- the risk is easy to justify
- the red/yellow/green output is easy to scan
- the trust path is easy to audit

## Success criteria

- The system can run continuously
- The system can show its evidence
- The system can abstain when confidence is low
- The system can explain why it escalated
- The system can do all of the above at a lower cost than always using the largest model
