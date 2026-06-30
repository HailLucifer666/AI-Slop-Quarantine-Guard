"""The Crew — AI explainer (Phase 7). ADVISORY ONLY.

Takes one Guard finding and returns a plain-English explanation for a
non-technical founder: what it is, why it matters, how to fix it. Hard rules:
- Never changes a Guard conclusion or severity (it only reads a finding).
- Never claims the code was AI-written.
- Any failure (no key, timeout, bad response) → returns None so the caller
  degrades gracefully ("explanation unavailable") — findings still stand.

Provider is the OpenAI-compatible endpoint in settings (NVIDIA NIM by default);
swapping to Claude Haiku later is just llm_base_url/llm_model/llm_api_key.
"""

import json
import logging

import httpx

from app.config import settings

logger = logging.getLogger("crew")

# minimax-m3 is a reasoning-capable model — 500 tokens can take 30-60s. Give it room.
_TIMEOUT = 90.0
_MAX_TOKENS = 500

_SYSTEM = (
    "You are a senior engineer explaining a code quality or security finding to a "
    "NON-TECHNICAL founder who builds apps with AI but cannot read code. "
    "Be warm, concrete, and plain-spoken. Hard rules: "
    "(1) Never claim the code was written by AI. "
    "(2) Never tell them to ignore a finding marked CERTAIN. "
    "(3) Do not invent facts beyond the finding you are given. "
    "Respond with ONLY a JSON object, no markdown, with exactly these keys: "
    '"explanation" (1-2 sentences, what this is in plain English), '
    '"why_it_matters" (1-2 sentences, the real-world risk), '
    '"how_to_fix" (1-3 short steps the founder or their AI can take).'
)


def _build_prompt(finding: dict) -> str:
    ev = finding.get("evidence") or {}
    lines = [
        f"Check: {finding.get('rule_id')} ({finding.get('category')})",
        f"Confidence: {finding.get('confidence')}",
        f"File: {finding.get('file_path')}:{finding.get('line_start')}",
        f"What the Guard found: {finding.get('message')}",
    ]
    snippet = ev.get("snippet")
    if snippet:
        lines.append(f"Offending line: {snippet.strip()[:300]}")
    if finding.get("fix_suggestion"):
        lines.append(f"Guard's fix hint: {finding['fix_suggestion']}")
    return "\n".join(lines)


def _coerce(value) -> str:
    """Models sometimes return a list of steps — flatten to clean newline text."""
    if isinstance(value, list):
        return "\n".join(f"{i + 1}. {str(v).strip()}" for i, v in enumerate(value) if str(v).strip())
    return str(value or "").strip()


def _parse(content: str) -> dict | None:
    """Pull the JSON object out of the model's reply, defensively."""
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        try:
            obj = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            obj = None
        if isinstance(obj, dict):
            return {
                "explanation": _coerce(obj.get("explanation")),
                "why_it_matters": _coerce(obj.get("why_it_matters")),
                "how_to_fix": _coerce(obj.get("how_to_fix")),
            }
    # Fallback: the model didn't give clean JSON — use the whole reply as the body.
    return {"explanation": text[:800], "why_it_matters": "", "how_to_fix": ""}


async def explain_finding(finding: dict) -> dict | None:
    """Return {explanation, why_it_matters, how_to_fix} or None if unavailable."""
    if not settings.llm_api_key:
        logger.warning("crew: no LLM_API_KEY set — explainer disabled")
        return None

    payload = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _build_prompt(finding)},
        ],
        "temperature": 0.2,
        "max_tokens": _MAX_TOKENS,
    }
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        logger.warning("crew: LLM call failed: %s: %s", type(exc).__name__, exc)
        return None

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        logger.warning("crew: unexpected LLM response shape")
        return None

    usage = data.get("usage") or {}
    logger.info(
        "crew explained %s tokens=%s",
        finding.get("rule_id"),
        usage.get("total_tokens", "?"),
    )
    return _parse(content)
