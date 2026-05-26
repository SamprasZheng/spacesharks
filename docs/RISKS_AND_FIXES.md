# Risks And Fixes

This document records risks and pending fixes. It is intentionally documentation-only while implementation work is in progress elsewhere.

## Immediate UX fixes

### P0: Earth view should be larger and more visually dominant

Problem:

The current orbital trajectory panel does not make Earth feel like the central object. The demo needs a stronger "global coverage" impression, especially if the pitch is Starlink-first fleet triage.

Risk:

- The interface looks like a dense dashboard instead of a mission desk
- The user does not immediately feel satellite scale or global coverage
- The strongest visual asset is underused

Pending fix:

- Make the Earth panel larger by default
- Allow UI/UX layout adjustment between `analysis-heavy` and `earth-heavy` modes
- Show enough satellites to make the globe feel populated
- Keep health coloring visible on satellites and orbit traces
- Preserve the right-side brief and left-side fleet list, but reduce their dominance when in earth-heavy mode

Acceptance criteria:

- First glance communicates "global satellite fleet"
- Earth is large enough to be the visual anchor
- Red/yellow/green fleet state remains readable
- The UI can switch back to denser analysis mode when reviewing evidence

### P0: Recommendation should not keep popping up

Problem:

The mission UI should not interrupt the user repeatedly with recommendation panels. A constantly appearing `PENDING RECOMMENDATION` block can feel noisy, gamey, and unsafe, especially when the recommendation includes command-like language such as `APPROVE COMMAND`.

Risk:

- User alert fatigue
- Demo looks like a notification spammer instead of an agent workbench
- Reviewers may think the system is trying to push actions before trust is established
- Unsafe perception if recommendations look too close to real spacecraft commands

Pending fix:

- Move recommendations into a persistent `Red Queue` or `Mission Inbox`
- Show only one non-blocking banner for new high-priority items
- Add cooldown rules so the same object cannot trigger repeated popups
- Require user pull-to-review for non-critical recommendations
- Rename `APPROVE COMMAND` to a safer phrase such as `ACCEPT BRIEF ITEM` or `MARK REVIEWED`

Acceptance criteria:

- No repeated modal or popup for the same satellite within a short window
- User can continue using the dashboard while recommendations accumulate
- Every recommendation has a timestamp, evidence link, confidence, and dismiss/review state
- UI language makes clear this is advisory triage, not real spacecraft control

## Product scope risks

### P1: Fleet size should feel global without forcing realtime updates

Problem:

The current visible list is too small to communicate fleet scale. A 50 or 100 object demo can prove the agent loop, but it does not create the visual feeling of a global constellation. The target should feel like thousands of satellites covering Earth, while keeping model triage focused and cheap.

Pending fix:

- Move from a small demo set toward at least 5,000 locally recorded visual/catalog objects
- Keep Starlink as the main focus
- Aim to record at least half of the active public catalog locally as a stretch target
- Update objects sequentially in a queue instead of refreshing all objects at once
- Make "last updated" visible per object or per batch
- Render objects not yet updated as `black` / inactive / unknown instead of green/yellow/red
- Keep the model triage queue limited to a much smaller active subset

Notes:

- The goal is broad local coverage, not realtime precision
- The demo can still focus on top red/yellow Starlink objects
- MEO/GEO can remain reference categories
- The visual layer can show thousands of dots; the reasoning layer should not run five models on thousands of objects every refresh

Acceptance criteria:

- Earth view can show at least 5,000 satellite points or orbit markers
- Unknown or not-yet-refreshed satellites remain black
- Updated satellites can become green/yellow/red only after data is available
- Sequential update progress is visible
- Starlink triage remains the main user-facing queue

### P1: Local database initialization needs a clear lifecycle

Problem:

If the app initializes from cloud sources every time it starts, startup will be slow and fragile. If it never refreshes, reports become stale.

Pending fix:

- Add a first-run initialization pass that scans public catalog data quickly
- Store normalized satellite records locally
- Do not repeat full initialization on every launch
- Add daily refresh jobs for reports
- Keep local data available for fast UI loading and model retrieval

Acceptance criteria:

- First run creates a local satellite cache
- Later launches load from local data first
- Cloud pull runs as background refresh
- A daily report can finish without needing full realtime refresh

### P1: Starlink focus can get diluted

Problem:

Adding LEO, MEO, GEO, and "most popular satellites" can make the product look unfocused.

Pending fix:

- Keep Starlink as the primary fleet
- Limit MEO/GEO to small reference strips
- Label MEO/GEO as comparison objects, not the main queue

### P1: "Satellite health" can overclaim

Problem:

The system only sees public data. It does not know private SpaceX telemetry or true spacecraft subsystem health.

Pending fix:

- Use terms like `public-data triage`, `attention level`, or `review priority`
- Avoid claiming actual spacecraft health
- Add a visible note in the detail view: `Based on public orbit and environment evidence only`

### P1: Reports can become the product

Problem:

Today / 7-day / 30-day reports are useful, but they can make the system feel like a report generator instead of an agent.

Pending fix:

- Treat reports as output of the agent's triage
- Keep the main demo focused on how the agent decides what deserves attention

## Model risks

### P0: RTX 5070 must be a hard performance target

Problem:

The demo must run on an RTX 5070-class consumer GPU. The current machine shows about 12GB dedicated VRAM, and the screenshot shows VRAM pressure can already reach roughly 9.6GB / 12GB. A design that requires multiple large local models loaded at once is not acceptable.

Risk:

- Demo instability on the target machine
- Out-of-memory failures during model council runs
- Poor fit with the consumer-GPU thesis
- Users with RTX 4070 or older cards cannot use the product

Pending fix:

- Treat RTX 5070 as the upper mainstream target, not as unlimited headroom
- Run local specialist models sequentially by default
- Keep only one local model loaded when memory pressure is high
- Add a visible `performance mode` selector
- Add model-seat reduction so users can lower the council size
- Persist intermediate votes so failed model calls do not restart the whole council

Acceptance criteria:

- Default mode runs reliably on RTX 5070 12GB VRAM
- Reduced mode is available for RTX 4070 / older GPUs
- The app does not require five models to be resident in VRAM at the same time
- The UI warns when GPU memory is too high before launching another local model

### P0: Minimum council size should be three models

Problem:

Five specialist models are the ideal demo, but weaker machines need a smaller configuration. The minimum viable version should still preserve redundancy.

Pending fix:

- Support configurable council size: `3`, `4`, or `5`
- Treat `3` as the minimum valid council
- Frame the 3-model mode as TMR-style redundancy
- Keep `Nemotron` as the fixed mission director when available
- If only two specialist models respond, mark the result `insufficient-council`

Suggested modes:

| Mode | Specialist seats | Use case |
|---|---:|---|
| `Eco` | 3 | RTX 4070 / older GPUs / battery-conscious runs |
| `Balanced` | 4 | Safer default when 12GB VRAM is under pressure |
| `Full Council` | 5 | Best demo mode on RTX 5070 when memory allows |

Minimum TMR seats:

- Orbit Analyst
- Health / Triage Analyst
- Evidence Analyst

Optional seats:

- Radiation / Space Weather Analyst
- Mission Impact Analyst

### P1: Five models can cost more without adding trust

Problem:

If all five models see the same prompt and do the same task, the ensemble becomes expensive majority voting.

Pending fix:

- Replace generic voting with `Specialist Mission Council`
- Assign each model a role: orbit, radiation, mission impact, health triage, evidence retrieval
- Log each specialist's role, output, confidence, and evidence

### P1: Nemotron role must stay central

Problem:

If `Nemotron` is only a backup model, the NVIDIA hackathon fit becomes weaker.

Pending fix:

- Make `Nemotron` the fixed mission director
- Specialist models can be swapped
- `Nemotron` arbitrates conflicts and writes the final recommendation

### P2: RTX 5070 memory pressure

Problem:

The local GPU has about 12GB VRAM. Running multiple models at the same time may fail or become slow.

Pending fix:

- Run specialist models sequentially
- Cache each model's vote
- Show "council is deliberating" in the UI instead of requiring true parallel inference

### P2: Model availability may differ by machine

Problem:

`ollama` was not available in PATH during the last local check. Some target models may not be installed or may not run well locally.

Pending fix:

- Keep model seats role-based, not model-name-based
- Add backup models
- Mark degraded mode when fewer than three specialist models respond

## Data and safety risks

### P1: Uncontrolled fetch behavior

Problem:

Allowing every model to fetch data directly makes provenance, safety, and cost hard to control.

Pending fix:

- Only the retrieval specialist or `Nemotron` can request new data
- All fetches must pass through `NemoClaw` policy
- Log source URL, timestamp, parser version, and evidence hash

### P2: Low refresh frequency can look stale

Problem:

Lower update frequency is acceptable, but the UI must not look stale or broken.

Pending fix:

- Show last refresh time
- Show source freshness
- Use report cadence deliberately: today, 7-day, 30-day

### P2: Large local catalog can hide what matters

Problem:

If thousands of satellites are stored locally, the UI can become noisy and slow unless the agent filters aggressively.

Pending fix:

- Keep the main queue focused on Starlink risk cases
- Add filters for `Starlink`, `LEO`, `MEO`, `GEO`, and `red/yellow only`
- Use pagination or virtualized lists
- Keep report generation focused on top changes and top risks
- Separate `visual catalog` from `active triage set`
- Do not let all 5,000 objects enter model council evaluation by default

### P2: Red labels need calibration

Problem:

Too many red satellites makes the system look alarmist. Too few makes it look useless.

Pending fix:

- Keep red as high-priority review only
- Use yellow for notable changes
- Track red precision during manual review

## Game mode risks

### P1: Game mode can overpower the agent story

Problem:

A game-like UI can be memorable, but it can also make the project look like a visual demo instead of an AI agent.

Pending fix:

- Keep `Fleet`, `Red Queue`, `Satellite Detail`, and `Briefs` as the real workflow
- Use game mode to reveal model deliberation, not to hide weak reasoning

### P2: EXE packaging may consume too much time

Problem:

Packaging as an EXE before the agent loop is stable can derail the hackathon build.

Pending fix:

- Prefer web/PWA game mode first
- Package later only if the core demo is already stable

## Open decisions

- Final 50 Starlink sample selection rule
- Whether the local catalog target is 50, 100, half of public active objects, or another staged number
- Whether the visual catalog target should be fixed at 5,000 objects for the first global-coverage demo
- How many of the 5,000 visual objects enter daily triage
- First-run initialization strategy and where the local database should live
- Daily report cadence and whether reports run automatically or on demand
- Earth-heavy versus analysis-heavy layout switch
- Whether MEO/GEO references appear on the first demo screen or only in a comparison tab
- Exact five specialist model assignments
- Default performance mode for RTX 5070
- Reduced council presets for RTX 4070 and older GPUs
- GPU memory threshold for refusing or delaying another model call
- Backup model list after local install is confirmed
- Recommendation wording for advisory actions
- Cooldown period for repeated recommendations
