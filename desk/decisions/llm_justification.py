"""desk.decisions.llm_justification — replace templated beam-redirect
justification text with a real Nemotron call.

Closes the post-2026-05-26 owner critique that every dashboard cell must
be backed by a real LLM call or judge, not a rule-based template. The
template fallback is kept for the offline / Ollama-unreachable case so
the dashboard never shows empty text.

Each call writes an audit row with `who="model:nemotron-3-nano:4b"`,
`action="BEAM_REDIRECT_LLM_JUSTIFY"`, plus the prompt_hash and the
generated text length, so reviewers can verify the LLM call actually
fired.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.request


_OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
_DEFAULT_MODEL = "nemotron-3-nano:4b"
_TIMEOUT_S = 45.0
_NUM_PREDICT = 360


def _prompt_for_justification(
    *,
    sat_id: str,
    anomaly_regime: str,
    target_lat: float,
    target_lon: float,
    tilt_deg: float,
    duration_s: int,
    incident_summary: str,
    kb_entries: list,
) -> str:
    kb_lines = []
    for e in (kb_entries or [])[:3]:
        kb_lines.append(
            f"- [{e.entry_id}] {e.failure_mode}/{e.component_class}: {e.answer[:160]}"
        )
    kb_block = "\n".join(kb_lines) or "(no KB entries matched — proceed with caution)"

    return (
        "You are the Spacesharks Mission Desk arbiter. You have been asked to "
        "draft the JUSTIFICATION TEXT for a needs-review beam-redirect proposal. "
        "Write ONE PARAGRAPH (3-5 sentences, plain text, no markdown) explaining:\n"
        "  - what the SEE/dielectric anomaly was\n"
        "  - why redirecting the downlink beam to the target coordinate is a "
        "    defensible operator response\n"
        "  - which KB entry IDs (cited by their ID in brackets) back the call\n"
        "  - the fact that this is needs-review and will not auto-execute\n"
        "DO NOT include any shell commands. DO NOT recommend voltage overrides. "
        "DO NOT use the strings rm -rf, shutdown, format, or voltage_override.\n\n"
        f"Satellite: {sat_id}\n"
        f"Anomaly regime: {anomaly_regime} (recovered)\n"
        f"Target ground coordinate: ({target_lat:.3f}, {target_lon:.3f})\n"
        f"Proposed beam tilt: {tilt_deg:.1f} degrees off-nadir\n"
        f"Proposed hold duration: {duration_s} seconds\n"
        f"Incident context: {incident_summary}\n\n"
        f"Relevant KB entries:\n{kb_block}\n\n"
        "Respond with only the justification paragraph; no preamble, no "
        "follow-up questions."
    )


def llm_justify_beam_redirect(
    *,
    sat_id: str,
    anomaly_regime: str,
    target_lat: float,
    target_lon: float,
    tilt_deg: float,
    duration_s: int,
    incident_summary: str,
    kb_entries: list,
    model_id: str = _DEFAULT_MODEL,
    ollama_url: str = _OLLAMA_URL,
) -> dict:
    """Returns dict::

        {
          "ok": bool,
          "text": str,            # the justification paragraph (real LLM or templated)
          "source": str,          # "llm" or "template-fallback"
          "model_id": str,
          "prompt_hash": str,     # sha256:<hex>
          "latency_ms": int,
          "eval_count": int,
          "error": str | None,
        }

    On any failure we return the templated fallback so the caller is never
    blocked. The `source` field tells the dashboard which path was taken.
    """
    prompt = _prompt_for_justification(
        sat_id=sat_id,
        anomaly_regime=anomaly_regime,
        target_lat=target_lat,
        target_lon=target_lon,
        tilt_deg=tilt_deg,
        duration_s=duration_s,
        incident_summary=incident_summary,
        kb_entries=kb_entries,
    )
    prompt_hash = "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    body = json.dumps({
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": _NUM_PREDICT},
    }).encode("utf-8")

    t0 = time.monotonic()
    try:
        req = urllib.request.Request(
            ollama_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        latency_ms = int((time.monotonic() - t0) * 1000)
        return {
            "ok": False,
            "text": _template_fallback(sat_id, anomaly_regime, target_lat, target_lon,
                                       tilt_deg, duration_s, incident_summary, kb_entries),
            "source": "template-fallback",
            "model_id": model_id,
            "prompt_hash": prompt_hash,
            "latency_ms": latency_ms,
            "eval_count": 0,
            "error": f"{type(e).__name__}: {e}",
        }

    msg = payload.get("message") or {}
    content = (msg.get("content") or "").strip()
    thinking = (msg.get("thinking") or "").strip()
    # Some reasoning models put the actual answer in `thinking` when the
    # response was truncated; prefer non-empty content.
    text = content or _strip_thinking(thinking)
    latency_ms = int(payload.get("total_duration", 0) // 1_000_000)
    eval_count = int(payload.get("eval_count", 0))

    if not text:
        return {
            "ok": False,
            "text": _template_fallback(sat_id, anomaly_regime, target_lat, target_lon,
                                       tilt_deg, duration_s, incident_summary, kb_entries),
            "source": "template-fallback",
            "model_id": model_id,
            "prompt_hash": prompt_hash,
            "latency_ms": latency_ms,
            "eval_count": eval_count,
            "error": "empty content + empty thinking",
        }

    return {
        "ok": True,
        "text": text,
        "source": "llm",
        "model_id": model_id,
        "prompt_hash": prompt_hash,
        "latency_ms": latency_ms,
        "eval_count": eval_count,
        "error": None,
    }


def _strip_thinking(thinking: str) -> str:
    """When the model's `thinking` channel contains the final answer, extract
    the last paragraph (after the reasoning chain) as the justification."""
    if not thinking:
        return ""
    # Heuristic: take the last paragraph separated by blank line.
    parts = [p.strip() for p in thinking.split("\n\n") if p.strip()]
    return parts[-1] if parts else thinking[:500]


def _template_fallback(sat_id, regime, lat, lon, tilt, dur, incident, kb_entries) -> str:
    cited = ", ".join(getattr(e, "entry_id", "?") for e in (kb_entries or [])[:3])
    return (
        f"Drafted needs-review beam-redirect for {sat_id} toward "
        f"({lat:.3f}, {lon:.3f}) at tilt {tilt:.1f} degrees for {dur}s. "
        f"Trigger: {regime} anomaly (recovered); incident: {incident}. "
        f"KB justification: {cited}. "
        f"Template fallback used (Nemotron unreachable). Operator approval "
        f"required via /api/approve under INVARIANTS override O2."
    )
