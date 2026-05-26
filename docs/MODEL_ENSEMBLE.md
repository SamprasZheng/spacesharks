# Model Ensemble

The model strategy is five small models voting first, with `Nemotron` escalation when the vote is risky or unstable.

Local hardware target checked on 2026-05-24:

```text
GPU: NVIDIA GeForce RTX 5070
VRAM: 12227 MiB
```

`ollama` was not available in PATH during this check, so the list below is a target stack, not a confirmed local install.

## Primary five

| Slot | Model | Provider family | Proposed role | Why it belongs |
|---|---|---|---|---|
| 1 | `nemotron-3-nano:4b` | NVIDIA | Fast triage classifier | Keeps the demo close to the NVIDIA stack and should be light enough for RTX 5070 |
| 2 | `mistral-nemo:12b` | Mistral + NVIDIA | Long-context brief drafter | Strong long-context model; also gives NVIDIA a second presence without using a huge model |
| 3 | `qwen3:8b` or `qwen3.5:9b` | Alibaba Qwen | Reasoning and structured extraction | Popular local model family with strong tool/reasoning behavior |
| 4 | `gemma3:4b` | Google | Conservative cross-checker | Small, popular, and useful as a different model family |
| 5 | `phi4-mini` | Microsoft | Function-call and rule-following checker | Lightweight reasoning model with good constrained-output behavior |

## Backup pool

| Backup | Use when | Notes |
|---|---|---|
| `deepseek-r1:7b` or `deepseek-r1:8b` | Need another reasoning vote | Good backup, but do not let chain-of-thought style output leak into the UI |
| `llama3.1:8b` | Need a stable generalist fallback | Mature and widely supported |
| `qwen3:4b` | Need a lighter Qwen path | Useful if 8B/9B is too slow or memory pressure is high |

## 5070 operating rule

The RTX 5070 has about 12GB VRAM. Run one local model at a time unless testing proves concurrent models fit. The ensemble can still work by querying models sequentially and caching votes.

Suggested default:

```text
run classifier -> run scorer -> run checker -> run brief drafter -> run arbiter
```

## Voting contract

Each model must return the same compact schema:

```json
{
  "risk_label": "green | yellow | red | abstain",
  "risk_score": 0.0,
  "confidence": "high | medium | low",
  "reason_codes": [],
  "evidence_used": [],
  "recommendation": null
}
```

## Escalation rules

Escalate to `Nemotron` when:

- at least two models vote `red`
- any model votes `red` and confidence is low
- model disagreement is high
- the result would appear in the user-facing brief
- local evidence is missing or contradictory

## Failure handling

If a model is offline:

- mark `model_status = offline`
- continue with the remaining models
- require higher agreement from the remaining votes
- escalate to `Nemotron` if fewer than three primary models respond

If `Nemotron` is unavailable:

- do not upgrade yellow to red
- route disputed cases to `needs-review`
- still generate the brief with the missing escalation noted

## Do not overclaim

The ensemble improves robustness only if the models make different mistakes. If all five models are variants of the same base family, the system should mark the run as `degraded: correlated-model-risk`.
