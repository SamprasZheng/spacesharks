"""desk.knowledge — offline COTS defect knowledge fusion for NEO Action Item 1.

Produces `data/cots_defect_knowledge.json` — the AEO-shaped Q&A corpus that
AI#3's `kb_retrieval.py` consumes. Two build modes:

  --seed-only       — deterministic expansion of the 10-entry bundled seed via
                      cross-component-class variations. No LLM. Runs in ~1s.
                      Target: >=50 entries.
  --with-llm        — calls Nemotron-Super-49B via NVIDIA NIM to refine the
                      seed and add up to 200 entries with structured citations.
                      Requires NVIDIA_API_KEY in env. Stretch goal.

Both modes are logged as `offline_batch=True` audit rows so they don't pollute
the live audit_completeness scoreboard metric.
"""

from desk.knowledge.schema import KBEntrySchema, validate_kb_payload
from desk.knowledge.build_cots_kb import build_kb, EXPANSION_MATRIX
from desk.knowledge.wiki_rag import (
    wiki_retrieve, wiki_rebuild, wiki_stats, WikiHit,
)

__all__ = [
    "KBEntrySchema", "validate_kb_payload", "build_kb", "EXPANSION_MATRIX",
    "wiki_retrieve", "wiki_rebuild", "wiki_stats", "WikiHit",
]
