# Architecture

## Overview

The system is designed as a safe, long-running decision loop rather than a chatbot.

```mermaid
flowchart LR
  subgraph Sources["Public signal sources"]
    SWPC["NOAA SWPC"]
    TLE["Celestrak / TLE"]
    CDM["Space-Track / CDM"]
    NOTAM["FAA NOTAM"]
  end

  subgraph Runtime["Controlled runtime"]
    NC["NemoClaw sandbox"]
    OC["OpenClaw 24/7 runner"]
    OR["OpenRouter fallback"]
  end

  subgraph Models["Model tier"]
    A["Small model A: classify"]
    B["Small model B: score risk"]
    C["Small model C: draft recommendation"]
    N["Nemotron: escalate / referee"]
  end

  subgraph Outputs["Outputs"]
    R["Recommendation + confidence + evidence"]
    L["Event log / JSONL"]
    D["Dashboard / timeline / demo"]
  end

  Sources --> NC --> OC
  OC --> A
  OC --> B
  OC --> C
  A --> N
  B --> N
  C --> N
  OR -. optional cost fallback .-> OC
  N --> R --> L --> D
```

## Execution pattern

1. Ingest a small number of high-value events
2. Normalize each event into a structured record
3. Run lightweight models first
4. Escalate only when uncertainty or risk is high
5. Persist the full decision trail

## Design principles

- Safety first: all execution stays inside `NemoClaw`
- Longevity first: `OpenClaw` keeps the loop alive for long runs
- Cost awareness: small models do the default work
- Escalation only when needed: reserve `Nemotron` for harder cases
- Replayability: every result must be reconstructable from the log
