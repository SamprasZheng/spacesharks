---
title: Agentic provenance — evidence trails for AI agent outputs
type: research
category: pattern
status: ingested
ingested: 2026-05-24
sources:
  - https://www.w3.org/TR/prov-dm/        # W3C PROV-DM Recommendation, 2013
  - https://www.w3.org/TR/prov-o/         # W3C PROV-O Recommendation, 2013
  - https://c2pa.org/                     # Coalition for Content Provenance and Authenticity
  - https://spec.c2pa.org/specifications/specifications/2.4/explainer/Explainer.html
  - https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf   # NIST AI 600-1, July 2024
  - https://cyclonedx.org/capabilities/mlbom/                # CycloneDX ML-BOM v1.7
  - https://artificialintelligenceact.eu/article/50/         # EU AI Act Article 50
---

# Agentic provenance — evidence trails for AI agent outputs

> Status: pattern research note for the Spacesharks Mission Desk. This is the
> *evidence chain* that makes every recommendation reproducible. It sits
> beneath the [Small-Model Ensemble Arbiter](small-model-ensemble-arbiter.md),
> [Tiered Inference](tiered-inference.md), and
> [Calibrated Confidence](calibrated-confidence.md) layers — without it,
> those layers are unverifiable. The trust pitch lives in
> [TRUST.md](../TRUST.md); the runtime flow lives in
> [ARCHITECTURE.md](../ARCHITECTURE.md).

## 1. Definition

**Agentic provenance** is the capacity to answer "where did this
recommendation come from?" at every layer of the agent's reasoning chain:
which input source, which parser version, which model and tier, which
arbiter rule, and which sandbox action.

Provenance is **distinct from logging**. A log records *that something
happened*. Provenance records *why the output is trustworthy* — by chaining
evidence back through every transformation from raw byte to published
recommendation. Without provenance, a labelled dataset is just a file.
With it, the dataset becomes a moat.

## 2. The four trust layers

The Mission Desk implements the four trust layers from [TRUST.md](../TRUST.md)
as a strict, fail-closed schema. Every event row must populate every field
in every layer; a missing field downgrades the row, never upgrades it.

### Layer 1 — Data trust

```yaml
# Layer 1 fields, required on every event row
source_url: "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json"
source_timestamp: "2026-05-24T18:00:00Z"   # when the event occurred
ingest_timestamp: "2026-05-24T18:01:23Z"   # when the agent read+parsed it
parser_version: "swpc-kp@1.2.0"            # semver or git SHA
evidence_hash: "sha256:b3f9..."            # SHA-256 of the raw fetched payload
```

The **evidence hash** is the ground anchor. The raw fetched payload is
written to `data/evidence-blobs/<hash[:2]>/<hash>.raw` as a write-once
blob; the schema row carries the hash only. If a source mutates post-ingest
(the nightly re-hash job detects this), the hash fails to match and the
row is flagged `needs-human-review` — **no silent mutations**.

### Layer 2 — Model trust

```yaml
# Layer 2 fields, required on every inference output
model_id: "nvidia/llama-nemotron-super-49b-v1-5-reasoning"
tier: "T2"                                 # T1 | T2 | T3, see tiered-inference.md
prompt_hash: "sha256:7c1e..."              # SHA-256 of the rendered prompt
model_confidence: 0.72                     # calibrated, see calibrated-confidence.md
ensemble_disagreement: 0.18                # KL divergence or vote gap, see small-model-ensemble-arbiter.md
```

The **prompt hash** is the determinism hook. Given the same model version
and the same prompt hash, the inference is reproducible. Combined with
`parser_version` and `evidence_hash`, the row can be re-derived from first
principles.

### Layer 3 — Decision trust

```yaml
# Layer 3 fields, required on every recommendation
recommendation: "Trigger safe-mode for SAT-42 within 18 min"
confidence: 0.72                            # calibrated, post-arbiter
evidence_pointers:                          # explicit refs to Layer 1 evidence
  - "sha256:b3f9..."                        # SWPC Kp blob
  - "sha256:11ab..."                        # GOES X-ray blob
disagreement_level: 0.18
decision_route: "publish"                  # publish | monitor_only | needs_review | abstain | escalate
```

`evidence_pointers` are **machine-readable citations** — not free-text
justification — linking to Layer 1 `evidence_hash` values. The governance
layer reads `decision_route` to determine the published surface.

### Layer 4 — System trust

```yaml
# Layer 4 fields, required on every sandbox action
audit_log_id: "nemoclaw-2026-05-24T18-01-25Z-7c1e"
policy_preset_hash: "sha256:2a44..."        # SHA-256 of active openclaw-sandbox.yaml
denied_actions: []                          # tool calls blocked by policy this session
```

NemoClaw enforces Layer 4 **out-of-process** at the OpenShell runtime
layer. The agent cannot suppress its own audit trail via prompt injection;
the audit log row is written before the action returns to the agent.

## 3. Industry analogues

| Standard | Year | What it brings | Where it fits |
|---|---|---|---|
| **W3C PROV-DM / PROV-O** | 2013 | Canonical vocabulary: entities, activities, agents; `wasGeneratedBy`, `used`, `wasAttributedTo`, `wasDerivedFrom` | The four-layer model above is a domain-specific instantiation: a `recommendation` entity `wasGeneratedBy` an inference activity that `used` a dataset entity `wasAttributedTo` a model agent |
| **C2PA / Content Credentials** | v1 2022, v2.1 2024 | Manifest-based, cryptographically signed provenance attached to content; v2.0+ added AI training data disclosure | `evidence_hash` ≅ C2PA content hash; `policy_preset_hash` ≅ C2PA tool assertion |
| **NIST AI 600-1 (Generative AI Profile)** | July 2024 | Provenance is one of four primary considerations; referenced 151× | Mission Desk satisfies "identify which AI system authored the output" via `model_id` + `tier` |
| **CycloneDX ML-BOM (v1.7)** | Oct 2025 | Machine Learning Bill of Materials — model name, training data sources, evaluation metrics, license | `model_id` is the runtime pointer into the ML-BOM record |
| **EU AI Act Article 50** | In force, implementation finalising Aug 2026 | Machine-readable AI-generated-content marking that is effective, interoperable, robust, removal-resistant | `recommended_by` + `evidence_hash` satisfy the marking and preservation-of-provenance obligations |

The Mission Desk does not implement these standards verbatim — it implements
their **operational invariants**. The C2PA manifest is replaced by a JSONL
event log; the W3C PROV graph is replaced by the four-layer schema. The
key claims (content hash, agent attribution, policy assertion) are
preserved.

## 4. Trace ↔ span ↔ event mapping

Commercial agent observability platforms (Helicone, LangSmith, Langfuse,
AgentOps) standardise on the **trace → span → event** model. The Mission
Desk's audit trail maps directly onto it:

| Industry term | Mission Desk equivalent | Fields |
|---|---|---|
| Trace | One lifecycle event row (query → final recommendation) | All fields, Layer 1 + 2 + 3 + 4 |
| Span | One unit of work within the trace (tool call, LLM inference, memory lookup) | `model_id`, `prompt_hash`, `latency_ms` |
| Event | Timestamped annotation within a span (policy denial, confidence below threshold) | `audit_log_id`, `denied_actions`, `decision_route` |

The `audit_completeness` scoreboard metric is what commercial platforms
call **trace coverage**: `audit_completeness = rows_with_audit_log_id /
total_rows`. A row without an `audit_log_id` is unverifiable.

## 5. Reference event-row schema

A complete event row, JSONL-encoded. This is the **contract** every
ingestor and every decision agent must conform to.

```json
{
  "event_id": "sw-2026-05-24T18-00-00Z-kp7",
  "phase": "on_orbit",
  "event_type": "x_flare",

  "source_url": "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json",
  "source_timestamp": "2026-05-24T18:00:00Z",
  "ingest_timestamp": "2026-05-24T18:01:23Z",
  "parser_version": "swpc-kp@1.2.0",
  "evidence_hash": "sha256:b3f9...",

  "model_id": "nvidia/llama-nemotron-super-49b-v1-5-reasoning",
  "tier": "T2",
  "prompt_hash": "sha256:7c1e...",
  "model_confidence": 0.72,
  "ensemble_disagreement": 0.18,

  "recommendation": "Trigger safe-mode for SAT-42 within 18 min",
  "confidence": 0.72,
  "evidence_pointers": ["sha256:b3f9...", "sha256:11ab..."],
  "disagreement_level": 0.18,
  "decision_route": "publish",

  "audit_log_id": "nemoclaw-2026-05-24T18-01-25Z-7c1e",
  "policy_preset_hash": "sha256:2a44...",
  "denied_actions": [],

  "review_status": "auto_publish_pending",
  "recommended_by": "spacesharks-mission-desk@0.1.0"
}
```

Storage layout:

```
data/
  events/                # JSONL append-only, rotated daily
    2026-05-24.jsonl
    2026-05-25.jsonl
  evidence-blobs/        # write-once raw payloads, content-addressed
    b3/b3f9...raw
    11/11ab...raw
    7c/7c1e...prompt.txt
  audit/                 # NemoClaw out-of-process audit log
    2026-05-24.jsonl
```

## 6. Reproducibility invariant

**Every event row is reproducible from a 5-tuple**:

```
(source_url, parser_version, model_id, tier, policy_preset_hash, timestamp)
```

Given those five values, any reviewer can re-derive the row by re-running
the same parser version against the same content-addressed payload through
the same model at the same tier under the same sandbox policy. **This is
what makes the labelled-lifecycle dataset a commercially defensible asset,
not merely a historical record.**

## 7. Implementation — Python event-row writer

```python
# provenance.py
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal


def sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


@dataclass
class Layer1:
    source_url: str
    source_timestamp: str
    ingest_timestamp: str
    parser_version: str
    evidence_hash: str

@dataclass
class Layer2:
    model_id: str
    tier: Literal["T1", "T2", "T3"]
    prompt_hash: str
    model_confidence: float
    ensemble_disagreement: float

@dataclass
class Layer3:
    recommendation: str
    confidence: float
    evidence_pointers: list[str]
    disagreement_level: float
    decision_route: Literal["publish", "monitor_only", "needs_review", "abstain", "escalate"]

@dataclass
class Layer4:
    audit_log_id: str
    policy_preset_hash: str
    denied_actions: list[str] = field(default_factory=list)


@dataclass
class EventRow:
    event_id: str
    phase: str
    event_type: str
    l1: Layer1
    l2: Layer2
    l3: Layer3
    l4: Layer4
    review_status: str
    recommended_by: str


class EvidenceStore:
    """Content-addressed write-once blob store."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def write(self, payload: bytes) -> str:
        h = sha256_bytes(payload)
        digest = h.removeprefix("sha256:")
        path = self.root / digest[:2] / f"{digest}.raw"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            existing = path.read_bytes()
            if existing != payload:
                # SHA-256 collision is astronomically unlikely — if this
                # ever fires, log loudly. Do NOT overwrite.
                raise RuntimeError(f"sha256 collision at {h}")
            return h
        # write-once: write to a tmp file then atomic rename
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(payload)
        tmp.rename(path)
        return h


class EventLog:
    """JSONL append-only event log with daily rotation."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def append(self, row: EventRow) -> None:
        date = row.l1.ingest_timestamp[:10]      # YYYY-MM-DD
        path = self.root / f"{date}.jsonl"
        line = json.dumps(self._to_flat(row), separators=(",", ":"))
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    @staticmethod
    def _to_flat(row: EventRow) -> dict:
        out: dict = {
            "event_id": row.event_id,
            "phase": row.phase,
            "event_type": row.event_type,
        }
        out.update(asdict(row.l1))
        out.update(asdict(row.l2))
        out.update(asdict(row.l3))
        out.update(asdict(row.l4))
        out["review_status"] = row.review_status
        out["recommended_by"] = row.recommended_by
        return out


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
```

The `EvidenceStore` writes are **fail-closed**: a SHA-256 mismatch raises;
there is no "overwrite anyway" path. Combined with the daily JSONL rotation,
this gives the same operational properties as a journaled write-ahead log
without taking a database dependency on Day 1.

## 8. Nightly re-hash verification

A nightly cron at 03:00 UTC verifies every blob in the previous 24 hours
matches its declared hash. The job:

1. Reads each event row from yesterday's JSONL.
2. Reads each `evidence_hash`'s blob from disk.
3. Recomputes SHA-256 and compares.
4. On mismatch, flips the row's `review_status` to `needs_human_review`
   and writes a `mismatch` event into the audit log.
5. Reports `audit_completeness` and `evidence_integrity_rate` to the
   scoreboard.

```python
# verify_evidence.py
def verify_blob(store_root: Path, evidence_hash: str) -> bool:
    digest = evidence_hash.removeprefix("sha256:")
    path = store_root / digest[:2] / f"{digest}.raw"
    if not path.exists():
        return False
    actual = sha256_bytes(path.read_bytes())
    return actual == evidence_hash
```

## 9. Where it fails

- **Lossy logs are catastrophic.** The 24/7 ops loop in
  [OpenClaw](https://www.openclaw.ai) means one dropped log row breaks
  reproducibility for every downstream row that referenced that decision
  in its `evidence_pointers`. This is why NemoClaw's
  *out-of-process* audit enforcement is a hard requirement, not a
  convenience: the agent cannot be the sole log writer.
- **Storage growth.** Write-once evidence blobs accumulate. Budget 100 MB
  per day for SWPC + CDM polling (most is JSON; few KB per fetch); plan
  for ~36 GB/year. Compress with zstd after 30 days; keep originals for at
  least 90 days.
- **Hash chains, not Merkle trees, on Day 1.** A proper Merkle tree over
  the JSONL log would let a reviewer verify a single row without reading
  the whole file. Day 1 implementation skips this; revisit when log size
  exceeds 1 GB.
- **No cryptographic timestamping.** `ingest_timestamp` is a host clock
  reading, not a signed third-party timestamp. For hackathon scope this is
  acceptable; for a regulated product (EU AI Act Article 50 compliance)
  add RFC 3161 timestamping later.

## 10. What to actually build

- [ ] `provenance.py` module with `Layer1`–`Layer4`, `EventRow`,
      `EvidenceStore`, `EventLog`.
- [ ] Wire every ingestor (NOAA SWPC, Space-Track CDM) to write through
      `EvidenceStore.write()` before the parser sees the payload.
- [ ] Wire every model call (per-tier in `tiered-inference.py`) to compute
      and log `prompt_hash`.
- [ ] Wire the NemoClaw audit log to a daily rotation under `data/audit/`
      with `audit_log_id` echoed into the event row.
- [ ] `verify_evidence.py` nightly cron at 03:00 UTC.
- [ ] Scoreboard metrics: `audit_completeness`, `evidence_integrity_rate`,
      `evidence_blob_size_total_mb`.
- [ ] One demo case showing a deliberately-mutated source flagging a row
      as `needs_human_review` via the nightly re-hash.

## 11. References

- W3C. [PROV-DM: The PROV Data Model](https://www.w3.org/TR/prov-dm/)
  (Recommendation, 30 April 2013).
- W3C. [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/)
  (Recommendation, 30 April 2013).
- C2PA. [Coalition for Content Provenance and Authenticity](https://c2pa.org/).
  v2.1 explainer: [spec.c2pa.org](https://spec.c2pa.org/specifications/specifications/2.4/explainer/Explainer.html).
- NIST. [AI 600-1 — Generative AI Profile](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf)
  (July 2024).
- CycloneDX. [ML-BOM / Machine Learning Bill of Materials](https://cyclonedx.org/capabilities/mlbom/)
  (v1.7, October 2025).
- EU. [AI Act Article 50](https://artificialintelligenceact.eu/article/50/)
  — transparency obligations for AI-generated content.
