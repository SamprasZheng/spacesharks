"""desk.knowledge.wiki_rag — local RAG retrieval over the yxz wiki.

Indexes ~184 wiki pages from `D:/DOT/yxz/wiki/` (concepts/sources/entities/
synthesis) into an in-memory token-overlap retriever. Used to inject relevant
satellite/RF/space-weather context into Nemotron prompts so the local LLM
calls have grounded domain knowledge instead of generating from scratch.

Why this is local-first and free:
  - No embeddings model needed — token-overlap (BM25-ish) is enough for 184
    short pages. Indexing takes <1s at boot.
  - No vector DB, no Pinecone, no Weaviate. One Python dict.
  - No paid API. The wiki is on disk under D:/DOT/yxz/wiki/.

The retriever returns the top-K most relevant wiki pages for a given query.
Each result carries (page_path, title, snippet, score) so the caller can
include the snippet directly in the Nemotron prompt and the page_path for
audit-trail provenance.
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


_WIKI_ROOT = Path("D:/DOT/yxz/wiki").resolve()
_SUBDIRS = ("concepts", "sources", "entities", "synthesis")

# Token regex — split on word boundaries; lowercase; drop short tokens.
_TOKEN_RE = re.compile(r"[a-z][a-z0-9-]{2,}")

# Stopwords that don't help retrieval and waste cycles.
_STOP = frozenset("""
the and for are with that from this have was not but you they will into all any can has had its
which when where there their them then than what who any our use using used uses how very also
some such only when more most less than then has been only does can may not are
""".split())


@dataclass
class WikiHit:
    path: str          # relative path under wiki/, e.g. "concepts/aesa.md"
    title: str         # first heading or filename if no heading
    snippet: str       # first ~280 chars after stripping frontmatter
    score: float       # cosine-ish token-overlap score


@dataclass
class _IndexEntry:
    path: str          # absolute path
    relpath: str
    title: str
    snippet: str
    raw: str           # full page text (for re-ranking)
    tf: dict[str, int] # term frequencies


class _WikiIndex:
    def __init__(self) -> None:
        self.entries: list[_IndexEntry] = []
        self.df: dict[str, int] = {}    # doc frequency per term
        self.n_docs: int = 0
        self.built_at: float = 0.0
        self.build_ms: int = 0

    def build(self) -> dict:
        t0 = time.monotonic()
        self.entries.clear()
        self.df.clear()
        if not _WIKI_ROOT.exists():
            self.built_at = time.time()
            self.build_ms = int((time.monotonic() - t0) * 1000)
            return {"ok": False, "error": f"wiki root not found: {_WIKI_ROOT}", "count": 0}

        for sub in _SUBDIRS:
            d = _WIKI_ROOT / sub
            if not d.exists():
                continue
            for fp in d.rglob("*.md"):
                try:
                    text = fp.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                body = _strip_frontmatter(text)
                title = _extract_title(body, fp)
                snippet = _make_snippet(body)
                tokens = self._tokenize(body)
                if not tokens:
                    continue
                tf: dict[str, int] = {}
                for tok in tokens:
                    tf[tok] = tf.get(tok, 0) + 1
                for tok in tf:
                    self.df[tok] = self.df.get(tok, 0) + 1
                self.entries.append(_IndexEntry(
                    path=str(fp),
                    relpath=str(fp.relative_to(_WIKI_ROOT)).replace("\\", "/"),
                    title=title,
                    snippet=snippet,
                    raw=body,
                    tf=tf,
                ))

        self.n_docs = len(self.entries)
        self.built_at = time.time()
        self.build_ms = int((time.monotonic() - t0) * 1000)
        return {
            "ok": True,
            "count": self.n_docs,
            "build_ms": self.build_ms,
            "wiki_root": str(_WIKI_ROOT),
            "unique_terms": len(self.df),
        }

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOP]

    def retrieve(self, query: str, top_k: int = 3) -> list[WikiHit]:
        if not self.entries:
            return []
        q_tokens = self._tokenize(query)
        if not q_tokens:
            return []
        # Term frequency in query
        q_tf: dict[str, int] = {}
        for t in q_tokens:
            q_tf[t] = q_tf.get(t, 0) + 1

        scored: list[tuple[float, _IndexEntry]] = []
        for entry in self.entries:
            score = self._score(q_tf, entry)
            if score > 0:
                scored.append((score, entry))
        scored.sort(key=lambda x: x[0], reverse=True)

        out: list[WikiHit] = []
        for score, entry in scored[:max(1, top_k)]:
            out.append(WikiHit(
                path=entry.relpath, title=entry.title,
                snippet=entry.snippet, score=round(score, 4),
            ))
        return out

    def _score(self, q_tf: dict[str, int], entry: _IndexEntry) -> float:
        """Token-overlap with IDF weighting. Equivalent to a simple TF-IDF
        cosine without normalisation; good enough for 184 docs."""
        score = 0.0
        for t, q_count in q_tf.items():
            d_count = entry.tf.get(t, 0)
            if d_count == 0:
                continue
            df = self.df.get(t, 1)
            idf = math.log((1 + self.n_docs) / (1 + df)) + 1.0
            score += q_count * d_count * idf
        # Title boost
        title_low = entry.title.lower()
        for t in q_tf:
            if t in title_low:
                score *= 1.4
        return score

    def stats(self) -> dict:
        return {
            "n_docs": self.n_docs,
            "unique_terms": len(self.df),
            "built_at": self.built_at,
            "build_ms": self.build_ms,
            "wiki_root": str(_WIKI_ROOT),
        }


def _strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end >= 0:
            return text[end + 4:].lstrip("\n")
    return text


def _extract_title(body: str, fp: Path) -> str:
    for line in body.splitlines()[:6]:
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return fp.stem


def _make_snippet(body: str, max_chars: int = 280) -> str:
    # Skip the first heading line, take next non-empty paragraph.
    lines = body.splitlines()
    out: list[str] = []
    total = 0
    seen_heading = False
    for ln in lines:
        s = ln.strip()
        if not s:
            if out and total > 80:
                break
            continue
        if s.startswith("#"):
            seen_heading = True
            continue
        if not seen_heading and not out:
            continue
        out.append(s)
        total += len(s) + 1
        if total >= max_chars:
            break
    snippet = " ".join(out)
    if len(snippet) > max_chars:
        snippet = snippet[: max_chars - 1].rstrip() + "…"
    return snippet


# Module-level singleton index.
_INDEX: _WikiIndex | None = None


def get_index() -> _WikiIndex:
    global _INDEX
    if _INDEX is None:
        _INDEX = _WikiIndex()
        _INDEX.build()
    return _INDEX


def wiki_rebuild() -> dict:
    """Force a re-index. Call from /api/neo/wiki/rebuild."""
    global _INDEX
    _INDEX = _WikiIndex()
    return _INDEX.build()


def wiki_retrieve(query: str, top_k: int = 3) -> list[WikiHit]:
    return get_index().retrieve(query, top_k=top_k)


def wiki_stats() -> dict:
    return get_index().stats()
