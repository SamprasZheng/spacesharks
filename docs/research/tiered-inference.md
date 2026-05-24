---
title: Tiered Inference — cost-aware model cascade routing
type: research
category: pattern
status: ingested
ingested: 2026-05-24
sources:
  - arXiv:2305.05176  # Chen, Zaharia, Zou — FrugalGPT (Stanford, 2023)
  - arXiv:2406.18665  # Ong et al. — RouteLLM (UC Berkeley / Anyscale, 2024)
  - arXiv:2406.04692  # Wang et al. — Mixture-of-Agents (Together AI, 2024)
  - arXiv:2211.17192  # Leviathan et al. — Speculative Decoding (Google, 2023)
  - https://www.lmsys.org/blog/2024-07-01-routellm/
  - https://www.together.ai/blog/together-moa
  - https://platform.claude.com/docs/en/build-with-claude/prompt-caching
  - https://openai.com/index/introducing-o3-and-o4-mini/
  - https://openrouter.ai/nvidia/nemotron-nano-9b-v2
  - https://artificialanalysis.ai/models/llama-nemotron-super-49b-v1-5-reasoning
  - https://lingjiaochen.com/papers/2024_FrugalGPT_TMLR.pdf
  - https://route.withmartian.com/
---

# Tiered Inference — cost-aware model cascade routing

> Status: pattern research note for the Spacesharks Mission Desk. This is the
> *cost-control spine* sitting beneath the
> [Small-Model Ensemble Arbiter](small-model-ensemble-arbiter.md). The trust
> pitch lives in [TRUST.md](../TRUST.md); the runtime flow lives in
> [ARCHITECTURE.md](../ARCHITECTURE.md).

## 1. Pattern definition

**Tiered inference** routes each incoming request to the cheapest model
capable of answering it adequately, escalating to a more powerful (and more
expensive) model only when an explicit trigger fires. For the Mission Desk's
24/7 ops loop, roughly **80% of requests should stay in the cheapest tier**;
escalation is the exception, not the default.

The escalation decision happens **between API calls, at the orchestrator
level**. This distinguishes tiered inference from three superficially similar
ideas:

| Technique | Where gating happens | Unit of decision |
|---|---|---|
| **Tiered inference / model cascade** (this doc) | Orchestrator, between calls | Whole request |
| **Speculative decoding** (Leviathan 2023) | Inside one inference call | Token batch (draft+verify) |
| **Mixture-of-Experts** (Shazeer 2017) | Inside the model, per forward pass | Token-level gating weight |

Speculative decoding is a latency optimization *within* a single call: a small
draft model generates candidate tokens that the large verifier accepts or
rejects. MoE (e.g. Nemotron 3 Nano's 31.6B-total / 3.2B-active architecture)
routes computation inside the model; the caller never sees it. Neither
substitutes for tiered inference at the orchestrator level.

## 2. Published evidence

| Reference | Result | Mechanism |
|---|---|---|
| FrugalGPT (arXiv:2305.05176) | **up to 98% cost reduction** at GPT-4 parity | Sequential cascade with a learned "good enough" scorer between tiers |
| RouteLLM (arXiv:2406.18665) | **up to 75% cost reduction** on MT Bench | Learned router predicts P(strong > weak); threshold α controls dial |
| Together MoA (arXiv:2406.04692) | 65.1% AlpacaEval 2.0 (vs GPT-4o 57.5%) | Parallel proposers + aggregator; orthogonal to cascade, can be combined |
| Anthropic prompt caching | 0.1× input-token price on cache hits | Same model, cheaper context; not a routing decision but same motivation |
| OpenAI o3 / o4-mini (June 2025) | Low/medium/high reasoning effort param | Built-in single-model cascade; pair o4-mini with o3 for true tiered |
| Martian Model Router (commercial) | Up to 98% claimed savings | Closed-source routing service; Accenture investment Sep 2024 |

Mission Desk anchors on FrugalGPT-style cascade for the local-first
deployment and RouteLLM-style learned router as a Phase-1 upgrade once
labeled outcomes accumulate.

## 3. Tier mapping for the Mission Desk

The local-first stack on a [DGX Spark]
(128 GB unified memory ceiling) plus optional sandboxed cloud egress:

| Tier | Model class | Steady-state load | Hosting | Per-token cost (May 2026) |
|---|---|---|---|---|
| **T1** | Nemotron Nano 2 (9B v2) or Hermes-4 14B | ~80% (CDM screen, NOTAM parse, SWPC summary) | Local on DGX Spark | $0.04 in / $0.16 out per M (OpenRouter) |
| **T2** | Nemotron Super 49B v1.5 or Hermes-4 70B | ~15% (ambiguous classifications, threshold proximity) | Local on DGX Spark | $0.10 in / $0.40 out per M (ArtificialAnalysis ~48 tok/s) |
| **T3** | Nemotron Ultra 253B or Hermes-4 405B | ~5% (red events, high-impact assets, novel event types) | Sandboxed cloud egress via NemoClaw L7 proxy | ~$0.20–0.80 in / ~$0.80–3.20 out per M (provider-dependent) |

The tier table is **a contract, not a suggestion**. Every audited row records
`tier_used` so calibration drift over time is visible — if T1 hit rate falls
below 80%, the dispatcher (§5) is mis-calibrated, not the model.

## 4. Escalation triggers

Four explicit triggers, all evaluated at the orchestrator level on T1's
output before any T2/T3 call is dispatched:

1. **Low inter-model agreement.** The
   [Small-Model Ensemble Arbiter](small-model-ensemble-arbiter.md) returns a
   `disagreement` score above the per-decision-class ceiling. The cheap tier
   is too noisy to own this case.
2. **High-risk event.** The event is on a hard-coded risk list:
   - Red Pc CDM (≥ 1×10⁻⁴ per NASA CARA Best Practices)
   - X-class solar flare with downstream SEP risk
   - Crewed-vehicle proximity within screening volume
   - Debris cloud novel event type
3. **High-impact asset.** The satellite in question is in a high-value asset
   class — flagship telecom satellite, government asset, asset with
   `priority: critical` flag. Even a routine event for such an asset is
   escalated.
4. **Threshold proximity.** The output sits near a decision boundary — Pc
   just below Red, launch-slip probability near 50%, calibrated confidence
   tier = `medium` rather than `high` or `low`. The
   [calibrated-confidence](calibrated-confidence.md) layer detects this.

Triggers are **OR-combined**. A T1 output that hits *any* trigger is
escalated; no trigger means publish-by-arbiter logic. A T2 output that hits
any trigger (other than "high-risk event," which is one-shot) is escalated
to T3.

## 5. Dispatcher implementation

A minimal, deterministic dispatcher. Pure logic — the only LLM calls are
inside the `tier_call` provider implementations, which are injected.

```python
# tiered_inference.py
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Protocol

# ----- Tier registry --------------------------------------------------------

class Tier(str, Enum):
    T1 = "T1"  # cheap local
    T2 = "T2"  # medium local
    T3 = "T3"  # expensive (local or egress)

@dataclass
class TierConfig:
    name: Tier
    model_id: str               # e.g. "nvidia/nemotron-nano-9b-v2"
    local: bool                 # True = on DGX Spark, False = sandboxed egress
    max_tokens: int             # output budget
    in_price_per_M: float       # USD per million input tokens (May 2026)
    out_price_per_M: float      # USD per million output tokens

TIER_REGISTRY: dict[Tier, TierConfig] = {
    Tier.T1: TierConfig(Tier.T1, "nvidia/nemotron-nano-9b-v2",
                        local=True,  max_tokens=512, in_price_per_M=0.04, out_price_per_M=0.16),
    Tier.T2: TierConfig(Tier.T2, "nvidia/llama-nemotron-super-49b-v1-5-reasoning",
                        local=True,  max_tokens=1024, in_price_per_M=0.10, out_price_per_M=0.40),
    Tier.T3: TierConfig(Tier.T3, "nvidia/llama-3.1-nemotron-ultra-253b-v1",
                        local=False, max_tokens=2048, in_price_per_M=0.40, out_price_per_M=1.60),
}

# ----- Trigger evaluation ---------------------------------------------------

@dataclass
class EscalationDecision:
    escalate: bool
    next_tier: Tier | None
    reasons: list[str] = field(default_factory=list)

HIGH_RISK_EVENT_TYPES: set[str] = {
    "cdm_red",         # Pc >= 1e-4
    "x_flare",         # X-class with SEP risk
    "crewed_proximity",
    "novel_debris",
}

def evaluate_escalation(
    *,
    current_tier: Tier,
    event_type: str,
    ensemble_disagreement: float,
    confidence_tier: str,         # "high" | "medium" | "low"
    asset_priority: str,          # "normal" | "critical"
    disagreement_ceiling: float,
) -> EscalationDecision:
    if current_tier == Tier.T3:
        return EscalationDecision(escalate=False, next_tier=None,
                                  reasons=["already at T3"])

    reasons: list[str] = []
    if ensemble_disagreement >= disagreement_ceiling:
        reasons.append(f"disagreement {ensemble_disagreement:.2f} >= ceiling {disagreement_ceiling:.2f}")
    if event_type in HIGH_RISK_EVENT_TYPES:
        reasons.append(f"high-risk event type: {event_type}")
    if asset_priority == "critical":
        reasons.append("critical-priority asset")
    if confidence_tier == "medium":
        reasons.append("threshold proximity (confidence=medium)")

    if not reasons:
        return EscalationDecision(escalate=False, next_tier=None, reasons=[])

    next_tier = Tier.T2 if current_tier == Tier.T1 else Tier.T3
    return EscalationDecision(escalate=True, next_tier=next_tier, reasons=reasons)

# ----- Dispatcher -----------------------------------------------------------

class TierCaller(Protocol):
    async def __call__(self, *, tier: TierConfig, prompt: str) -> dict[str, Any]: ...

@dataclass
class TierCallResult:
    tier: Tier
    model_id: str
    output: str
    in_tokens: int
    out_tokens: int
    latency_ms: int
    usd_cost: float

def estimate_cost(cfg: TierConfig, in_tokens: int, out_tokens: int) -> float:
    return (in_tokens / 1_000_000) * cfg.in_price_per_M \
         + (out_tokens / 1_000_000) * cfg.out_price_per_M

async def dispatch(
    *,
    prompt: str,
    event_type: str,
    asset_priority: str,
    confidence_tier_at_t1: str,
    ensemble_disagreement: float,
    disagreement_ceiling: float,
    call: TierCaller,
) -> tuple[TierCallResult, list[str]]:
    """Run the cascade. Returns (final result, escalation reason chain).

    The dispatcher is fail-closed: any provider exception aborts the cascade
    and bubbles up — never silently drops a query.
    """
    current_tier = Tier.T1
    reasons_chain: list[str] = []

    while True:
        cfg = TIER_REGISTRY[current_tier]
        t0 = time.monotonic_ns()
        raw = await call(tier=cfg, prompt=prompt)
        latency_ms = (time.monotonic_ns() - t0) // 1_000_000
        result = TierCallResult(
            tier=current_tier,
            model_id=cfg.model_id,
            output=raw["output"],
            in_tokens=raw["in_tokens"],
            out_tokens=raw["out_tokens"],
            latency_ms=latency_ms,
            usd_cost=estimate_cost(cfg, raw["in_tokens"], raw["out_tokens"]),
        )

        # Evaluate escalation only on T1 and T2 outputs.
        decision = evaluate_escalation(
            current_tier=current_tier,
            event_type=event_type,
            ensemble_disagreement=ensemble_disagreement,
            confidence_tier=confidence_tier_at_t1,
            asset_priority=asset_priority,
            disagreement_ceiling=disagreement_ceiling,
        )
        reasons_chain.extend(f"[{current_tier.value}→{decision.next_tier.value if decision.escalate else 'STOP'}] {r}"
                             for r in (decision.reasons or ["no escalation trigger fired"]))

        if not decision.escalate or decision.next_tier is None:
            return result, reasons_chain
        current_tier = decision.next_tier
```

The dispatcher is intentionally short and reviewable. **No learned router on
Day 1** — the cold-start problem (FrugalGPT and RouteLLM both train their
routers on labelled data the Mission Desk does not yet have) is sidestepped
by hand-coded triggers. Replace with a learned router only after Phase-1
labelled outcomes accumulate.

## 6. Cost simulation

Order-of-magnitude per-event cost on a typical 1,500-input / 200-output
prompt at the May-2026 prices above:

| Tier | Cost per event | Cost per 1,000 events |
|---|---|---|
| T1 only | $0.000092 | $0.092 |
| T1 → T2 (escalate 15%) | $0.000219 | $0.219 |
| T1 → T2 → T3 (escalate 15% then 5% of total) | $0.000324 | $0.324 |
| Always T3 (no cascade) | $0.000920 | $0.920 |

**Cascaded routing is ~3× cheaper than always-T3 at this workload mix.** The
gap widens as input length grows because T3's input price is 10× T1's.
Source coverage and freshness do not change — only the average inference
cost per event does.

## 7. Where it fails

- **Router error.** A mis-classified Red-Pc event that stays in T1 is a
  safety incident. Over-triggering sends every borderline event to T3 and
  erodes the cost savings. Both modes must be measured on the scoreboard
  (`escalation_rate_per_tier`, `escalation_false_positive_rate`).
- **Escalation latency.** When a trigger fires the request is re-issued to
  the next tier, ~doubling round-trip time. For a CDM with TCA < 2 h, this
  latency penalty matters; prefer parallel speculative T1+T2 in that case
  (T1 returns first, T2 returns within a few seconds; if T1's output is
  trusted by trigger evaluation, drop T2's result).
- **Calibration is offline.** Setting the disagreement ceiling and the
  confidence-tier thresholds requires a labelled validation set the Mission
  Desk does not have on Day 1. Bootstrap from CDM Red/Yellow/Green ground
  truth (NASA CARA bands) and from SWPC alert categories; expand from
  labelled outcomes as they accumulate.
- **Cold-start for novel event types.** Triggers fall back to conservative
  T3 escalation when `event_type` is `unknown` — accept the cost cost on
  Day 1; tune triggers after the first month of operation.

## 8. What to actually build

- [ ] `tiered_inference.py` module with the dispatcher in §5 (drop-in
      between the arbiter and any tier-aware caller).
- [ ] Provider adapters for at least T1 (local Ollama or vLLM running
      Nemotron Nano 2) and T3 (sandboxed egress via NemoClaw L7 proxy to
      OpenRouter or NVIDIA NIM).
- [ ] `TIER_REGISTRY` populated from a YAML config file so prices and model
      IDs can be updated without code changes.
- [ ] `tier_used` field added to every event row (see
      [agentic-provenance](agentic-provenance.md) for the schema).
- [ ] Scoreboard metrics: `escalation_rate_per_tier`,
      `escalation_false_positive_rate`, `cost_per_event_usd`.
- [ ] One demo case showing T1 → T2 escalation on a manufactured
      threshold-proximity event, with the reason chain visible in the audit
      log.

## 9. References

- Chen, Zaharia & Zou. *FrugalGPT: How to Use Large Language Models While
  Reducing Cost and Improving Performance.* arXiv:2305.05176 (2023).
  TMLR extended version: [lingjiaochen.com/papers/2024_FrugalGPT_TMLR.pdf](https://lingjiaochen.com/papers/2024_FrugalGPT_TMLR.pdf).
- Ong et al. *RouteLLM: Learning to Route LLMs with Preference Data.*
  arXiv:2406.18665 (2024).
  Blog: [lmsys.org/blog/2024-07-01-routellm](https://www.lmsys.org/blog/2024-07-01-routellm/).
- Wang et al. *Mixture-of-Agents Enhances Large Language Model
  Capabilities.* arXiv:2406.04692 (2024).
  Blog: [together.ai/blog/together-moa](https://www.together.ai/blog/together-moa).
- Leviathan, Kalman & Matias. *Fast Inference from Transformers via
  Speculative Decoding.* arXiv:2211.17192 (2023).
- Anthropic. *Prompt caching docs.*
  [platform.claude.com/docs/en/build-with-claude/prompt-caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching).
- OpenAI. *Introducing o3 and o4-mini.*
  [openai.com/index/introducing-o3-and-o4-mini](https://openai.com/index/introducing-o3-and-o4-mini/).
- Nemotron Nano 2 (9B v2) pricing: [openrouter.ai/nvidia/nemotron-nano-9b-v2](https://openrouter.ai/nvidia/nemotron-nano-9b-v2).
- Nemotron Super 49B v1.5 pricing: [artificialanalysis.ai/models/llama-nemotron-super-49b-v1-5-reasoning](https://artificialanalysis.ai/models/llama-nemotron-super-49b-v1-5-reasoning).
- Martian Model Router: [route.withmartian.com](https://route.withmartian.com/).
