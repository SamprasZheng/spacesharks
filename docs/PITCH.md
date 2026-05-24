---
status: locked
locked_on: 2026-05-24
type: pitch
audience: hackathon-judges, day-1-builders
---

# Pitch — Spacesharks Mission Desk

> Canonical submission narrative for the NVIDIA Agent Challenge 2026 entry.
> Single source of truth for the "What is Spacesharks?" question.
>
> If [SCOPE.md](SCOPE.md), [ARCHITECTURE.md](ARCHITECTURE.md), [TRUST.md](TRUST.md),
> or [PLAN.md](PLAN.md) contradict this page, the companion docs are the contracts —
> reconcile **here** first, then propagate.

## 5-Word Scope

The five terms the four-day build will not drift from:

| Term | Role |
|---|---|
| `NemoClaw` | Safe boundary (sandboxed network + policy + audit) |
| `OpenClaw` | 24/7 execution layer (the long-running runtime) |
| `Small-Model Ensemble` | "Three cobblers" decomposition (classify · score · draft) |
| `Provenance` | Source-traceable decision audit trail |
| `24/7 Ops Loop` | Closed loop: ingest → reason → recommend → log |

## Submission Pitch

### Project Hook & Summary

**Spacesharks Mission Desk** — a low-cost, multi-model satellite ops copilot that uses ensemble reasoning, provenance, and safe execution to produce trustworthy recommendations.

### The Problem

Traditional space operations rely either on rigid, hard-coded thresholds or generic, expensive LLMs that suffer from hallucinations, high latency, and astronomical token costs — making 24/7 continuous deployment commercially unviable and dangerous for mission-critical SatOps.

### Our Solution — The Architecture of Trust

Instead of relying on a single, expensive reasoning model, Spacesharks implements a **Tiered Inference Framework** powered by a specialized small-model ensemble inside a strictly controlled environment:

- **24/7 Ops Loop (`OpenClaw`)** — Continually ingests multi-source environmental signals (NOAA SWPC space weather, Space-Track CDMs) in real time. See [research/noaa-swpc-api.md](research/noaa-swpc-api.md) and [research/space-track-cdm-api.md](research/space-track-cdm-api.md).
- **Small-Model Ensemble** — Three specialized, low-cost small models (routed efficiently via OpenRouter) work in parallel: Model A classifies events, Model B calculates risk scores, Model C drafts mitigation steps. See [research/small-model-ensemble-arbiter.md](research/small-model-ensemble-arbiter.md).
- **Arbiter & Provenance** — A deterministic arbiter synthesizes the ensemble's outputs, calibrates confidence, and enforces provenance — tracing every recommendation back to its exact data source and timestamp. On high disagreement or low confidence, the system gracefully abstains to **Monitor Only**.
- **Safe Boundary (`NemoClaw`)** — The autonomous system operates only inside a sandboxed network + policy file. Every decision is auditable.

## System Architecture (Data + Decision Flow)

```
                           [ Real-Time Data Ingest (OpenClaw) ]
                                    │ (NOAA SWPC / CDM)
                                    ▼
                        [ Tiered Inference Router ]
                                    │
            ┌───────────────────────┼───────────────────────┐
            ▼                       ▼                       ▼
   [ Small Model A ]       [ Small Model B ]       [ Small Model C ]
   (Event Classifier)      (Risk Scoring Engine)  (Mitigation Drafter)
            │                       │                       │
            └───────────────────────┬───────────────────────┘
                                    ▼
                         [ Ensemble Arbiter ]
                                    │
                    ┌───────────────┴───────────────┐
                    │ Calibrate Confidence & Vote   │
                    └───────────────┬───────────────┘
                                    ▼
                      Disagreement High / Low Confidence?
                                    ├──► [ YES ] ──► [ Abstain & Monitor Only ]
                                    └──► [ NO  ] ──► [ Escalate / Execute ]
                                                            │
                                                            ▼
                                                [ NemoClaw Safe Sandbox ]
                                                            │
                                                            ▼
                                                  [ Auto-Publish ]
                                          (With Strict Source Provenance)
```

The Mermaid runtime variant lives in [ARCHITECTURE.md](ARCHITECTURE.md); both diagrams describe the same loop.

## Day 1 Implementation Shape

Reference skeleton for `spacesharks/core/arbiter.py`. The fully-typed version (with `@dataclass` outputs and `typing.Protocol` model interfaces, plus thresholds + injectable disagreement function) lives in [research/small-model-ensemble-arbiter.md](research/small-model-ensemble-arbiter.md). The version below is the readable narrative form for the pitch.

```python
# spacesharks/core/arbiter.py
import datetime
from typing import Dict, Any, Optional


class MissionDeskArbiter:
    def __init__(self, model_a, model_b, model_c):
        self.model_a = model_a  # Classifier
        self.model_b = model_b  # Risk Scorer
        self.model_c = model_c  # Action Drafter

    def process_event(self, raw_signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        # Layer 1 — Source trust: provenance is stamped before any model runs.
        provenance = {
            "source": raw_signal.get("source"),
            "source_timestamp": raw_signal.get("timestamp"),
            "ingest_timestamp": datetime.datetime.utcnow().isoformat(),
            "parser_version": "v1.0.2",
        }

        # Layer 2 — Model trust: three small models, three independent roles.
        event_class = self.model_a.classify(raw_signal)         # e.g. "SPACE_WEATHER"
        risk_score = self.model_b.score_risk(raw_signal)        # e.g. 8.5 / 10
        proposed_action = self.model_c.draft_action(raw_signal) # e.g. "TRIGGER_SAFE_MODE"

        # Layer 3 — Decision trust: thresholds gate execution; otherwise abstain.
        if risk_score > 7.0 and event_class == "SPACE_WEATHER":
            return {
                "decision": "RECOMMEND",
                "action": proposed_action,
                "confidence": 0.88,
                "provenance": provenance,
                "status": "EXECUTED_IN_SANDBOX",  # Layer 4 — System trust (NemoClaw)
            }

        # High disagreement or low risk → never hard-guess.
        return {
            "decision": "ABSTAIN",
            "status": "MONITOR_ONLY",
            "provenance": provenance,
        }
```

## Build Sequence (B → D → A, locked 2026-05-24)

1. **Option B — Lock the thesis.** This file plus [TRUST.md](TRUST.md), [SCOPE.md](SCOPE.md), [ARCHITECTURE.md](ARCHITECTURE.md), [PLAN.md](PLAN.md). Done in commit `fdcd787`.
2. **Option D — Lightweight ingest research.** Day 1 ingest narrowed to NOAA SWPC + Space-Track CDM only. Operational handbooks committed under [research/](research/INDEX.md).
3. **Day 1 Build.** Implement OpenClaw 24/7 listener + `MissionDeskArbiter` from the skeleton above. Wire to the two ingestors; abstain by default until confidence is real.

## Why this scores on "Architecture" + "Commercial Viability"

- Most hackathon entries argue about prompt length or LLM size. This entry argues about **trust, cost, and determinism** — the real production blocker for autonomous SatOps.
- The four trust layers (source · model · decision · system) are concrete, audit-friendly, and each maps to a committed artefact in this repo.
- The ensemble + arbiter pattern is **measurably cheaper** than a single Nemotron call per event (see OpenRouter cost model in [research/small-model-ensemble-arbiter.md](research/small-model-ensemble-arbiter.md)) **without sacrificing safety**, because abstain-on-disagreement is the safe default.
- Every recommendation is replayable from the event log + NemoClaw audit row → judges can re-derive any decision after the demo.

## Related contracts

- [SCOPE.md](SCOPE.md) — what is in-scope vs deferred
- [TRUST.md](TRUST.md) — the four trust layers, ensemble policy table
- [ARCHITECTURE.md](ARCHITECTURE.md) — Mermaid runtime flow + 5-step execution pattern
- [PLAN.md](PLAN.md) — 4-day build sequence
- [research/INDEX.md](research/INDEX.md) — operational research notes
- [research/noaa-swpc-api.md](research/noaa-swpc-api.md) — T1 ingest handbook
- [research/space-track-cdm-api.md](research/space-track-cdm-api.md) — T2 ingest handbook
- [research/small-model-ensemble-arbiter.md](research/small-model-ensemble-arbiter.md) — arbiter pattern + cost model
