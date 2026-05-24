# Thesis

> Why this project exists in this shape, and why the obvious "use the largest model" framing was rejected.

## The pivot

Spacesharks Mission Desk went through three thesis refinements before settling on the current one.

1. **First version.** Port existing Jamia / Spacesharks GPT personas onto the NVIDIA Nemotron stack as the hackathon entry. **Rejected** — porting an existing product is migration work, not agent work, and the NVIDIA Agent Challenge 2026 judges long-running agents that run, persist, and perform, not product completion.
2. **Second version.** Build a satellite-lifecycle decision copilot, with the dataset as the long-term commercial moat. Approved as the medium-term direction, but flagged as too broad for a four-day build.
3. **Third version (current).** A low-cost, multi-model satellite ops copilot that uses ensemble reasoning, provenance, and safe execution to produce trustworthy recommendations.

The third version is the thesis this document defends.

## Why not "use the largest Nemotron"

The largest-model framing is the default for hackathons. Every entry can rent a 405B endpoint. "We used the biggest model" is therefore not a differentiation argument — it is the baseline.

What is **not** commoditised in a four-day window:

- **Schema design** — every event has a defined row contract before any ingestor is written.
- **Evaluation discipline** — hit rate, calibration per tier, Brier score, freshness p50/p95, and audit completeness are tracked together. Hit rate alone is gameable.
- **Provenance plumbing** — every recommendation can be re-derived from the raw evidence blob. This pays off after weeks of accumulated logs, not minutes.
- **Ensemble disagreement as input** — when small models disagree, the disagreement is a first-class signal, not noise to be averaged away.

These four are the trust stack. Implementing them is the actual hackathon work. See [`TRUST.md`](TRUST.md) for the four-layer architecture and [`INVARIANTS.md`](INVARIANTS.md) for the operational rules they imply.

## Why the dataset is the moat, not the agent

The agent is the visible surface. The dataset and the operating loop are what compound.

Source-of-truth signals for satellite operations live across NOAA SWPC, Celestrak, Space-Track, FAA NOTAM, FCC IBFS, ITU, arXiv, vendor datasheets, and operator press releases. **No public product knits them together per-satellite, per-phase.** The first agent that does will accumulate a moat measured in months of ingest, not days of code.

This is why the schema is locked before any decision logic is written, and why every event in the log carries its source URL, timestamp, parser version, and evidence hash. The agent is replaceable. The dataset is not.

## Honest prior-art landscape

Three areas where this project explicitly does not claim invention:

### MCP in aerospace

Academia has just started advocating MCP for aerospace. Four public repositories exist as of the build window:

| Repo | Stack | Note |
|---|---|---|
| `IO-Aerospace-software-engineering/mcp-server` | .NET, SPICE-based | Production instance at `mcp.io-aerospace.org` (Oct 2025) |
| `alti3/stk-mcp` | Python, Ansys STK wrapper | MIT, ~32 stars (Oct 2025) |
| `cheesejaguar/aerospace-mcp` | Python / FastAPI | 44+ tools, v0.0.2 (Jan 2026) |
| `ProgramComputer/NASA-MCP-server` | Node | 20+ NASA APIs including DONKI (space weather) and TLE |

None of these are peer-reviewed. None ship with sandboxing or policy enforcement. No enterprise satellite operator has publicly named an MCP production deployment.

**Spacesharks's differentiation is therefore not "we use MCP."** It is "we wrap the MCP tool layer inside a NemoClaw sandbox with a Hermes-backed wiki KB for retrieval." That is an architecture claim, not a research breakthrough.

### LLM-based satellite NetOps

Sun et al., *SCNOC-Agentic: A Network Operation and Control Agentic for Satellite Communication Systems* (Electronics 14(16) 3320, 2025) already covers multi-agent + Graph-RAG for satellite NetOps. Benchmark: qwen2.5-70B network-task-planning accuracy improved from 15.6% to 32.2% with the framework. This is the closest prior work to Spacesharks's reasoning surface, though scoped to telco NetOps, not ops desk decisions.

### JEPA + multi-agent RL for SDA

MSBAI's OrbitGuard ($1.2M DoD SBIR Direct-to-Phase II, Sept 2025; AMOS 2025 poster) deploys JEPA + multi-agent RL across ~15,000 on-orbit objects with self-reported 94–98% accuracy. Lockheed Martin's iSpace (C2 + sensor fusion, German Space Agency customer) does not disclose its ML methods publicly.

Spacesharks does not compete with these on SDA precision. The Mission Desk's surface is operator-facing decisions (safe-mode triggers, conjunction triage drafts, decay ETAs), not on-orbit anomaly detection at scale.

## What this project is uniquely positioned to ship

1. **A schema-first event log** with provenance plumbing already designed for long retention.
2. **A multi-model ensemble** with three specialists drawn from different base-model families, plus a deterministic arbiter — not a majority vote.
3. **A sandbox boundary that is auditable** rather than permissive — denied actions are observable, policy hash is recorded.
4. **A publish verb with a cancel window** — not always-on, not silent, not unbounded.
5. **A roadmap that already names where local RF / thermal / signal-processing expertise plugs in** — see [`ROADMAP.md`](ROADMAP.md).

That is the entry. It is intentionally narrower than "a satellite copilot," and intentionally broader than "another LLM wrapper."

## How to read this document

Use `THESIS.md` to answer "why this scope, and why now." Use `TRUST.md` for the layered design. Use `INVARIANTS.md` for the rules an implementer cannot break. Use `PLAN.md` for the day-by-day build. Use `ROADMAP.md` for what to pick up after the hackathon.

If any of the other documents contradicts this thesis, **fix the other document, not this one** — unless the contradiction is itself a deliberate refinement, in which case update this file first.
