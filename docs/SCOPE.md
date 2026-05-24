# Scope

## Goal

Prove that a safe, low-cost, multi-model system can turn public satellite signals into trustworthy operator recommendations.

## In scope for the hackathon

- One core scenario: on-orbit operations
- One small set of signal sources
- One satellite case or a very small fleet
- One decision loop: ingest -> reason -> recommend -> log
- One audit trail for every recommendation
- One 24h runtime demonstration

## What is deferred

- Full lifecycle automation
- Pre-launch, commissioning, and end-of-life depth
- Real spacecraft actuation
- Trading or investment positioning
- Broad source coverage
- Auto-publishing as the primary product

## Recommended first demo case

Use a space-weather or conjunction-driven ops recommendation flow.

Why this case:

- the signal is easy to explain
- the risk is easy to justify
- the recommendation is visible
- the trust path is easy to audit

## Success criteria

- The system can run continuously
- The system can show its evidence
- The system can abstain when confidence is low
- The system can explain why it escalated
- The system can do all of the above at a lower cost than always using the largest model
