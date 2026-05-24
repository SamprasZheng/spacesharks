# Mission Desk — MVP dashboard

The MVP focus is **per-satellite health monitoring** with a four-state traffic
light (`GREEN → YELLOW → RED → BLACK`). Multiple assessor models vote on every
sat every tick; their disagreement is surfaced in the trust-stack panel.
Space-weather inputs (Kp, X-ray, SEP, AE) drive transitions; sat-intrinsic
factors (age vs design life, accumulated TID, recent SEEs) gate how exposed
each sat is. The right pane is an AI Copilot timeline that proposes
SAFE-MODE / RETIRE recommendations the operator can approve.

Phase 0 runs entirely on synthetic data so it boots without any API key. The
seams for real sources (Celestrak, NOAA SWPC, NOTAM, Space-Track CDM) are in
`server.py` — replace `Weather.tick()` and add ingestor calls inside
`assessment_loop()`. Token usage is tracked because the long-term plan is to
migrate from Nimble Cloud to a local GPU and become "token-free".

## Run

```powershell
python desk\server.py --port 8765
# open http://127.0.0.1:8765/
```

Stdlib only. No pip, no node, no build step.

## Panels

| Panel | What it shows | Mapping to docs |
|---|---|---|
| Top bar — Nimble Cloud meter | tokens spent / daily quota + rate/min, by-model breakdown via `tokens` cmd | bridges to the "local GPU = token-free" target |
| Top bar — Fleet Health | live count by state (GREEN/YELLOW/RED/BLACK) | new health-monitor MVP |
| NemoClaw Trust Stack | 5-model branching consensus tree for the focused sat | Layer-2 ensemble in [`ARCHITECTURE.md`](../docs/ARCHITECTURE.md), specialist-arbiter rule in [`INVARIANTS.md`](../docs/INVARIANTS.md) |
| Orbital Trajectory Tracking | Earth with graticule, atmosphere, stars, 4-regime orbit rings, sat dots coloured by health, clickable to focus | the demo case in [`PLAN.md`](../docs/PLAN.md) |
| AI Copilot | user / NEMOCLAW timeline + pending recommendation + Approve / Review buttons | publish-gate cancel-window stand-in from [`GOVERNANCE.md`](../docs/GOVERNANCE.md) |
| Satellite Lifecycle | chevron pipeline for focused sat | per-phase taxonomy in [`EVENT_SCHEMA.md`](../docs/EVENT_SCHEMA.md) |
| Telemetry Metrics | Alt / Vel / Signal sparklines for focused sat | live confidence proxy, signal floor degrades with health |
| Sat Dossier | operator, launch date, age/life %, mission, TID, SEE 30d, factor bars | health factors per [`EVALUATION.md`](../docs/EVALUATION.md) |
| Drawer (collapsed by default) | assessment log, alerts, fleet table, terminal | secondary detail; click bottom-left toggle to open |

## Health model

Each sat has a dossier (design life, TID budget, SEE threshold, mission type,
launch date, regime). Every tick:

1. **Space weather ticks** — Kp/X-ray/SEP random walk + occasional events
   (solar flares, CME impacts, SEP events, geomagnetic storms).
2. **Sats degrade** — TID accumulates faster under high Kp / high SEP; SEEs
   roll probabilistically with SEP flux.
3. **Round-robin assessment** — one sat per tick is scored by the full
   5-model ensemble; each model has a different bias (age / radiation /
   weather / balanced / optimistic). Median vote becomes the new health.
4. **Transitions are surfaced** — any state change generates an alert row
   and (for RED / BLACK) a copilot recommendation.

`BLACK` is irrecoverable in the MVP: a sat that crosses TID budget or sees
a sustained `BLACK` consensus stays there.

## Assessor models

| Model | Family | Bias | Tokens/call |
|---|---|---|---|
| DeepProp-7B    | Nemotron-Nano  | age        | 1,100 |
| OrbitNet-13B   | Hermes-4       | radiation  | 1,450 |
| SatGuard-9B    | Mistral-deriv  | weather    | 1,250 |
| Astro-AI-22B   | Qwen-3         | balanced   | 1,900 |
| Pathfinder-17B | Nemotron-Super | optimistic | 1,700 |

Different base-model families per the specialist-arbiter rule in
[`INVARIANTS.md`](../docs/INVARIANTS.md). Synthetic Nimble Cloud daily quota
is 2,000,000 tokens — the top-bar gauge turns warn-yellow at 50% and bad-red
at 80% so the operator can tell whether the loop will outrun the cap.

## Terminal commands

  - `status` — fleet health + worst sat + current weather
  - `list [color]` — list sats, optionally filter by health
  - `focus <name|id>` — focus a sat (drives the right-side panels)
  - `weather` — dump space-weather inputs
  - `storm [flare|cme|sep|geomag]` — manually trigger a storm (great for demo)
  - `tokens` — Nimble Cloud usage broken down per model
  - `models` — list assessor models and their biases
  - `events [N]` / `alerts [N]` — tail event rows / alerts
  - `approve` — approve the latest copilot recommendation
  - `start` / `stop` — pause / resume the assessor loop

## Schema conformance

Every event written to `desk/data/lifecycle-events.jsonl` carries the v1.0
required fields: `schema_version`, `event_id`, `sat_id`, `phase`,
`event_time`, `source_type`, `source_url`, `confidence`, `evidence_hash`,
`parser_version`, `review_status`, and (when present) `recommendation` +
`recommended_by`. The publish-gate routing in `_route()` matches the table in
`PLAN.md`:

| confidence × significance | route |
|---|---|
| high + above-threshold | `auto-published` |
| high + below-threshold | `draft` |
| medium | `draft` |
| low | `internal-log-only` |

## Roadmap (after MVP)

1. Replace `Weather.tick()` synthetic walk with NOAA SWPC pulls; replace the
   TID model with a regime-aware AE9/AP9 lookup.
2. Replace synthetic assessor votes with real Nimble Cloud calls — same
   prompt fan-out, same arbitration, real model IDs. Token gauge already
   wired.
3. Local-GPU mode: behind a flag, swap Nimble Cloud calls for a local Ollama
   client — `token-free` operation. Surface the toggle in the top bar so the
   operator knows which path is hot.
4. 30-minute cancel-window timer on the Approve button (per
   `GOVERNANCE.md`).
5. Persist health histories so the dashboard can scrub backwards and replay
   a storm window.

## Files

```
desk/
  server.py            # stdlib HTTP + SSE + health engine + assessor ensemble
  web/index.html       # single-page dashboard, layout matches the mockup
  web/styles.css       # Google-Earth-feel dark theme
  web/app.js           # SSE client, Earth animation, trust-stack tree,
                       # copilot stream, lifecycle chevrons, telemetry, dossier
  data/                # lifecycle-events.jsonl appended at runtime
  README.md            # this file
```
