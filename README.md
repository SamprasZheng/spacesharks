# Spacesharks Mission Desk

> An autonomous AI desk that doesn't just watch the space industry — it predicts every phase of the satellite lifecycle, recommends operator actions, archives every event into a labeled dataset future operators will pay for, and posts its own track record.

Built for the **NVIDIA Agent Challenge 2026** at GTC Taipei (deadline 2026-05-28). Powered by [NVIDIA Nemotron](https://www.nvidia.com/en-us/ai-data-science/foundation-models/nemotron/) for reasoning, sandboxed by [NVIDIA NemoClaw](https://github.com/NVIDIA/NemoClaw), persistent via [NousResearch Hermes Agent](https://github.com/NousResearch/hermes-agent).

## What it is

A long-running agent (not a dashboard, not a chatbot) that operates as a satellite-lifecycle decision co-pilot. It ingests environmental + telemetry-adjacent signals in real time, reasons about implications per individual satellite, and produces **executable operator decisions** — while quietly accumulating a structured, source-linked satellite-lifecycle event dataset.

## Lifecycle taxonomy

The agent owns five phases of every satellite. Each phase has defined signals, at least one decision action, and a dataset row schema.

| Phase | Decision action(s) | Signal sources |
|---|---|---|
| Pre-launch | Slip probability score, readiness checklist gap flag, survivability brief | FAA NOTAM, weather, FCC/ITU clock |
| Launch & ascent | Telemetry envelope anomaly flag | Vehicle historical data, operator releases |
| Commissioning (D+0 to D+30) | Day-N baseline deviation alert | Anomaly database by sat class |
| **On-orbit operations** | **Safe-mode trigger, momentum dump window, conjunction triage, interference attribution** | NOAA SWPC, GOES, Celestrak, Space-Track CDM, FCC IBFS |
| EOL & deorbit | Decay-window prediction, passivation draft, ITU notice timing | TLE decay, atmospheric density |

## Agent verbs (≠ "monitor")

`Predict` · `Recommend` · `Score` · `Brief` · `Patch-self` (Hermes skill creation) · `Publish-selectively` · `Debate` (Jamia × Spacesharks two-agent dialectic)

## Canonical plan

Full plan, defensibility argument, 2+2 day milestone schedule, demo deliverables, and risk register live in the author's wiki:

→ [`yxz/wiki/synthesis/spacesharks-mission-desk-hackathon-plan.md`](https://github.com/SamprasZheng/yxz/blob/wiki/nemoclaw-hermes-runbook/wiki/synthesis/spacesharks-mission-desk-hackathon-plan.md)

The knowledge base the agent retrieves from (orbit dose budgeting, TID/SEE physics, solar cycle 25, RHA, LEO value chain, etc.) also lives in [`SamprasZheng/yxz`](https://github.com/SamprasZheng/yxz) under `wiki/concepts/`.

## Status

Day 0 — scaffold only. Build begins 2026-05-24.

## License

Apache-2.0. Aligned with the NVIDIA NemoClaw / OpenShell upstream license model.
