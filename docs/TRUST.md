# Trust Model

The system should be trusted because it is observable, calibrated, and willing to abstain. For the hackathon, trust is measured on a Starlink sample fleet rather than across every satellite in orbit.

## Trust layers

### 1. Source trust

- Every satellite state stores a source URL
- Every state stores an observation timestamp
- Every parser version is recorded
- Every derived risk field points back to public evidence
- No private SpaceX telemetry is implied or claimed

### 2. Model trust

- Use multiple small models for different Starlink triage tasks
- Require confidence scores from each model
- Treat disagreement as a signal, not noise
- Escalate red, disputed, or low-confidence cases to `Nemotron`
- Mark degraded mode when the ensemble is not diverse enough

### 3. Decision trust

- Never mark a satellite red without evidence
- Include confidence and disagreement level with each triage result
- Prefer abstention over a forced guess
- Degrade to "monitor only" when the ensemble is not aligned
- Separate "needs attention" from "operator should act now"

### 4. System trust

- Keep all actions inside `NemoClaw`
- Keep the runtime alive in `OpenClaw`
- Log all outputs, failures, abstentions, and escalations
- Make the full event chain replayable

## Ensemble policy

| Condition | Action |
|---|---|
| High agreement and low risk | Mark green |
| High agreement and moderate risk | Mark yellow and include in brief |
| High agreement and high risk | Mark red and draft recommendation |
| Low agreement | Abstain |
| High risk and low confidence | Escalate to `Nemotron` |
| No clear evidence | Monitor only |

## Health labels

The fleet view uses three labels:

- `green`: no current attention required
- `yellow`: notable change or elevated context, include in report
- `red`: high-priority review item with evidence and recommendation

These labels are triage labels, not claims of actual spacecraft health. The system only sees public evidence.

## What to show reviewers

- The system can highlight a few concerning Starlink objects from a larger fleet
- The system can explain why an object is red, yellow, green, or abstained
- The system can reject uncertain cases
- The system can run cheaply enough to be practical
- The system improves trust through evidence, not through hype

## Suggested metrics

- source coverage
- report freshness
- abstention rate
- escalation rate
- red satellite review precision
- replay completeness
- model cost per report

## Real vs projected — honest data provenance

> **Added 2026-05-26 (NEO post-review).** This section exists because the
> demo would not be defensible if it secretly presented synthetic numbers
> as observed telemetry. The line between *real* and *projected* is
> explicit; the dashboard surfaces it via the `weather.source` field.

### What is real

| Signal | Source | Live verification |
|---|---|---|
| Active satellite catalog | `celestrak.org/NORAD/elements/gp.php?GROUP=active` | 15,441 sats in the cache file (`data/tle/celestrak-active.tle`, 2.6 MB) |
| Sub-satellite point / altitude / eclipse hint | SGP4 propagation on real TLEs via `desk.physics.sgp4_propagator` | `/api/state` returns lat/lon/alt that match Celestrak's web ground-track tool |
| Planetary Kp index | `services.swpc.noaa.gov/json/planetary_k_index_1m.json` | `weather.source == "swpc-live"` in snapshot |
| GOES X-ray flux (0.1–0.8 nm long band) | `services.swpc.noaa.gov/json/goes/primary/xrays-1-day.json` | Returns `xray_class = C1`/`M1`/`X1` derived from the live flux |
| GOES SEP flux (≥10 MeV) | `services.swpc.noaa.gov/json/goes/primary/integral-protons-1-day.json` | Returns real pfu values |
| LLM inference latency / output | Local Ollama daemon on the host (verified at 2026-05-26 with `nemotron-3-nano:4b` returning `"GREEN"` in 628 ms after a real `/api/chat` POST) | `inference.mode == "LIVE-OLLAMA"`; `live_calls` counter rises on each tick |
| NemoClaw policy hash | SHA-256 of `desk/nemoclaw/policy.py` recomputed on file mtime change | `/api/audit/policy-hash` returns the real hash |

### What is projected (not observed)

| Signal | Why it's not observed | How we make it defensible |
|---|---|---|
| Chip-level current_mA / voltage_V / SEU bit-error-rate | No public feed of real LEO chip-level telemetry exists. Operators (SpaceX, ESA, Planet Labs) keep that data proprietary. | The `desk.physics.cots_telemetry.TelemetryStream` is a *physics-based projection* — given the real SGP4 sub-satellite point (eclipse / SAA proximity) and the real SWPC space-weather state, what would a representative COTS chip experience? The simulator is deterministic per `(sat_id, regime)` seed and modulated only by real environmental inputs. It is **not** a synthetic stand-in for a missing real feed; it is an explicit risk-envelope projection. |
| Per-sat TID accumulation | Same reason — proprietary mission-telemetry | Same approach. Slow drift driven by real SWPC flare exposure + orbit position. |
| 4-state health label | Derived from the ensemble, not measured | Honest framing on the dashboard: "triage labels, not claims of actual spacecraft health." See §"Health labels" above. |
| Beam-redirect target coordinates | The hackathon demo uses the sub-satellite point as a stand-in for an emergency disaster target. A production deployment would consume a real disaster-feed input. | The draft is locked to `decision_route="needs-review"` under INVARIANTS override O2 — operator approval required before any downstream system acts. No real RF hardware, no real ground station. |

### How the dashboard surfaces this honestly

- `weather.source` field on every `/api/state` snapshot: one of `swpc-live`, `swpc-stale` (≥15 min old cache), or `simulated` (cold boot or sustained outage).
- `weather.real_data_age_s` shows seconds since last successful SWPC fetch.
- When `weather.source == "swpc-live"`, the random `_spawn_event()` path is **suppressed** — real storms come from the real feed, not from random dice rolls.
- COTS anomaly audit rows are tagged with `override_invariant=O1-source-list-5th-input` so reviewers can see that the COTS telemetry is the authorized 5th input (under explicit override), not a stealth 5th data source.
- The 4-tuple `(source_url, source_timestamp, parser_version, evidence_hash)` from `wiki/concepts/agentic-provenance.md` Layer 1 is present on every event row.

### Limits we will not paper over

- **Per-spacecraft chip data**: until an operator partners with us, projected-only. No "TID curve from on-orbit measurement" claim is made.
- **Beam-redirect actuation**: draft-only. The system never sends RF commands.
- **Hermes-4 14B + Nemotron-Super 49B**: not currently pulled in the local Ollama instance. The lineup falls back to Nemotron-Nano 4B for the Mission Director seat too; the tier-3 cloud path exists in code but is not currently invoked.
- **NemoClaw sandbox binary**: when the WSL gateway is up, the agent runs inside the NemoClaw `my-assistant` sandbox at port 18789. When the gateway is down, the `desk/nemoclaw/` Python module enforces the same policy + audit interface from inside the server process. Both paths write to the same JSONL audit log; the `policy_preset_hash` field tells reviewers which policy file was active.
