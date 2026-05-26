"""desk.decisions.tactical_brief — every 60s ask Nemotron for a fleet
executive summary, cache the result, surface via /api/neo/tactical-brief.

This panel is what makes the dashboard's text content come from a real LLM
rather than from a string-formatted aggregate. The brief is bounded (3
short sentences) so the LLM call is cheap (~1-3s on RTX 5070) and the cache
TTL (60s) keeps the volume sustainable even with multiple dashboard tabs.

Every successful generation writes an audit row with
`who="model:nemotron-3-nano:4b"`, `action="NEO_TACTICAL_BRIEF"`, plus the
prompt_hash + eval_count + latency_ms so reviewers can verify the LLM
call actually fired.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import urllib.request


_OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
_DEFAULT_MODEL = "nemotron-3-nano:4b"
_TIMEOUT_S = 40.0
_NUM_PREDICT = 512
_TTL_S = 60.0

_CACHE_LOCK = threading.Lock()
_CACHE: dict = {
    "ok": False,
    "text": "(no brief generated yet — first call in flight)",
    "source": "boot",
    "generated_at": 0.0,
    "ttl_remaining_s": 0,
    "model_id": _DEFAULT_MODEL,
    "prompt_hash": None,
    "latency_ms": 0,
    "eval_count": 0,
    "error": None,
}


def _prompt(fleet_state: dict, weather: dict, recent_audit_actions: list[str],
            wiki_hits: list | None = None) -> str:
    fh = fleet_state.get("fleet_health", {})
    recent = ", ".join(recent_audit_actions[:8]) or "(no recent actions)"
    wiki_block = ""
    if wiki_hits:
        wiki_block = "\nRelevant wiki context (cite by [path] if used):\n"
        for h in wiki_hits[:3]:
            wiki_block += f"  - [{h.path}] {h.title}: {h.snippet[:200]}\n"
    return (
        "You are the NEO ORBITAL DATA CENTER OS tactical arbiter, backed by "
        "Nemotron-Nano-4B running locally on RTX 5070. Write a THREE-SENTENCE "
        "executive brief for the operator looking at the dashboard right now. "
        "Be concrete; cite numbers; mention any RED satellites by name if "
        "present. Do not invent satellites that are not in the snapshot.\n\n"
        f"Fleet health counts: {fh}\n"
        f"Live space weather (from NOAA SWPC): Kp={weather.get('kp')} "
        f"X-ray={weather.get('xray_class')} SEP={weather.get('sep_pfu')} pfu, "
        f"source={weather.get('source')}\n"
        f"Recent NemoClaw audit actions: {recent}"
        f"{wiki_block}\n"
        "Respond with only the three-sentence brief — no preamble, no "
        "bullet points, no markdown. Plain text only."
    )


def _model_call(prompt: str, model_id: str = _DEFAULT_MODEL,
                ollama_url: str = _OLLAMA_URL) -> dict:
    body = json.dumps({
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": _NUM_PREDICT},
    }).encode("utf-8")
    t0 = time.monotonic()
    try:
        req = urllib.request.Request(
            ollama_url, data=body,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "text": "",
            "latency_ms": int((time.monotonic() - t0) * 1000),
            "eval_count": 0,
            "error": f"{type(e).__name__}: {e}",
        }

    msg = payload.get("message") or {}
    content = (msg.get("content") or "").strip()
    thinking = (msg.get("thinking") or "").strip()
    text = content or _last_paragraph(thinking)
    return {
        "ok": bool(text),
        "text": text or "(model returned empty text)",
        "latency_ms": int(payload.get("total_duration", 0) // 1_000_000),
        "eval_count": int(payload.get("eval_count", 0)),
        "error": None if text else "empty content",
    }


def _last_paragraph(s: str) -> str:
    if not s:
        return ""
    parts = [p.strip() for p in s.split("\n\n") if p.strip()]
    return parts[-1] if parts else s[:500]


def get_tactical_brief() -> dict:
    """Read-only — returns the current cached brief dict. Does NOT trigger
    a fetch; call `refresh_tactical_brief()` in a background thread for that."""
    with _CACHE_LOCK:
        ttl_remaining = max(0, int(_TTL_S - (time.time() - _CACHE.get("generated_at", 0))))
        out = dict(_CACHE)
        out["ttl_remaining_s"] = ttl_remaining
        return out


def refresh_tactical_brief(
    fleet_state: dict,
    weather: dict,
    recent_audit_actions: list[str],
    *,
    force: bool = False,
    model_id: str = _DEFAULT_MODEL,
    ollama_url: str = _OLLAMA_URL,
) -> dict:
    """Generate a new brief if the cache is older than _TTL_S (or `force=True`).
    Returns the resulting cache entry. Safe to call from any thread.
    """
    with _CACHE_LOCK:
        age = time.time() - _CACHE.get("generated_at", 0)
        if not force and age < _TTL_S and _CACHE.get("ok"):
            ttl_remaining = max(0, int(_TTL_S - age))
            out = dict(_CACHE)
            out["ttl_remaining_s"] = ttl_remaining
            return out

    # Inject wiki RAG context — pull 3 most relevant wiki pages based on the
    # current weather + audit actions. Local-only, no API cost.
    wiki_hits = []
    try:
        from desk.knowledge.wiki_rag import wiki_retrieve
        ra_actions_q = " ".join(recent_audit_actions[:10])
        wx_q = f"Kp {weather.get('kp')} X-ray {weather.get('xray_class')} SEP {weather.get('sep_pfu')}"
        query = f"satellite fleet operations {wx_q} {ra_actions_q} space weather NemoClaw"
        wiki_hits = wiki_retrieve(query, top_k=3)
    except Exception:
        wiki_hits = []

    prompt = _prompt(fleet_state, weather, recent_audit_actions, wiki_hits=wiki_hits)
    prompt_hash = "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    result = _model_call(prompt, model_id=model_id, ollama_url=ollama_url)

    entry = {
        "ok": result["ok"],
        "text": result["text"],
        "source": "llm" if result["ok"] else "llm-failed",
        "generated_at": time.time(),
        "ttl_remaining_s": int(_TTL_S),
        "model_id": model_id,
        "prompt_hash": prompt_hash,
        "latency_ms": result["latency_ms"],
        "eval_count": result["eval_count"],
        "error": result["error"],
        "wiki_hits": [{"path": h.path, "title": h.title, "score": h.score} for h in wiki_hits],
    }
    # Carry forward the previous text on failure so the dashboard never goes blank.
    if not result["ok"]:
        with _CACHE_LOCK:
            prev = _CACHE.get("text")
        if prev and prev != "(no brief generated yet — first call in flight)":
            entry["text"] = prev + " [stale — refresh in-flight]"
    with _CACHE_LOCK:
        _CACHE.update(entry)
        return dict(_CACHE)
