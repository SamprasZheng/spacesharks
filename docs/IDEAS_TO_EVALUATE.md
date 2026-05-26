# Ideas To Evaluate

These are promising ideas, not committed hackathon scope.

## Fleet scope

| Idea | Current stance | Risk |
|---|---|---|
| Expand from 50 to 100 Starlink objects | Good stretch goal | More objects can slow the demo if each object triggers model calls |
| Add MEO/GEO popular reference objects | Useful as comparison only | Equal treatment would dilute the Starlink-first story |
| Add all Starlink satellites | Defer | Too much data for the hackathon narrative |

## Model strategy

| Idea | Current stance | Risk |
|---|---|---|
| Five small models vote | In scope | Must keep output schema compact and sequential to fit 12GB VRAM |
| Backup models | In scope as configuration | Do not download everything unless disk and network budget are confirmed |
| Use the largest model for every item | Out of scope | Expensive and weakens the low-cost thesis |
| Use `Nemotron` only as escalation | In scope | Need at least one visible escalated case in the demo |

## Data and knowledge

| Idea | Current stance | Risk |
|---|---|---|
| Local knowledge pack | In scope | Must cite snippets used by each model |
| Web-crawled source notes | Evaluate | Risk of stale or low-quality data if not curated |
| Private telemetry-style health | Out of scope | Misleading unless real telemetry exists |

## Product pages

| Idea | Current stance | Risk |
|---|---|---|
| Fleet page | In scope | Must stay dense and operational |
| Red queue | In scope | This is the main agent value |
| Brief page | In scope | Report must be output, not the product itself |
| Full 3D orbital visualization | Defer | Looks good but can consume too much build time |

## Refresh cadence

Lower refresh frequency is acceptable. The value is not sub-second tracking; it is reliable triage and report generation.

Suggested cadence:

- orbit data: every 1 to 6 hours
- space-weather context: every 15 to 60 minutes
- today brief: on demand plus scheduled daily
- 7-day / 30-day brief: on demand
