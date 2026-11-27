"""Vultr Serverless Inference wrapper (BUILD_SPEC Section 4).

OpenAI-compatible client pointed at https://api.vultrinference.com/v1.
The API key lives only here, on the control plane.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import time
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI

from ..config import settings

log = logging.getLogger("safepilot.inference")

RETRY_STATUS = {429, 502, 503, 504}
REASONING = os.environ.get("VULTR_INFERENCE_REASONING", "off").lower() in ("1", "on", "true")


class InferenceError(RuntimeError):
    pass


class InferenceDisabled(InferenceError):
    pass


_client: AsyncOpenAI | None = None
_active_model = settings.inference_model
_health: dict[str, Any] = {"checked_at": 0.0, "status": "unchecked", "error": None}


def active_model() -> str:
    return _active_model


def _get_client() -> AsyncOpenAI:
    global _client
    if not settings.inference_enabled:
        raise InferenceDisabled("VULTR_INFERENCE_API_KEY is not set on the control plane")
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.inference_api_key,
            base_url=settings.inference_base_url,
            timeout=float(settings.inference_timeout),
            max_retries=0,
        )
    return _client


def _strip_fence(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"^<think>.*?</think>", "", text, flags=re.S).strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1).strip()
    if not text.startswith("{"):
        i, j = text.find("{"), text.rfind("}")
        if i != -1 and j > i:
            text = text[i : j + 1]
    return text


ALLOWED_MODELS = (settings.inference_model, settings.inference_fallback_model)


async def _chat(messages: list[dict[str, Any]], max_tokens: int, model: str | None = None) -> str:
    """model: per-run choice from the run settings. None uses the process-wide active model."""
    global _active_model
    client = _get_client()
    pinned = model if model in ALLOWED_MODELS else None
    use = pinned or _active_model
    delay = 0.5
    last_exc: Exception | None = None
    for attempt in range(settings.inference_max_retries):
        try:
            resp = await client.chat.completions.create(
                model=use,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.2,
                # qwen3.8-flash-next reasons by default and can burn the whole token budget
                # on hidden thinking. Structured JSON tasks are faster and reliable without it.
                extra_body={"reasoning": {"enabled": REASONING}},
            )
            return resp.choices[0].message.content or ""
        except APIStatusError as exc:
            last_exc = exc
            body = str(exc.message).lower()
            if exc.status_code in (400, 404) and "model" in body and use != settings.inference_fallback_model:
                log.warning("model %s unavailable, falling back to %s", use, settings.inference_fallback_model)
                if pinned is None:
                    _active_model = settings.inference_fallback_model
                use = settings.inference_fallback_model
                continue
            if exc.status_code not in RETRY_STATUS:
                raise InferenceError(f"HTTP {exc.status_code}: {exc.message[:200]}") from exc
        except (APIConnectionError, APITimeoutError) as exc:
            last_exc = exc
        await asyncio.sleep(delay + random.uniform(0, delay / 2))
        delay *= 2
    raise InferenceError(f"inference failed after retries: {last_exc}")


async def chat_json(system: str, user_text: str, image_b64: str | None = None,
                    image_type: str = "image/jpeg", max_tokens: int = 700, model: str | None = None) -> dict[str, Any]:
    """Call the model and strictly parse one JSON object, with one repair retry."""
    content: Any = user_text
    if image_b64:
        content = [
            {"type": "text", "text": user_text},
            {"type": "image_url", "image_url": {"url": f"data:{image_type};base64,{image_b64}"}},
        ]
    messages = [{"role": "system", "content": system}, {"role": "user", "content": content}]
    raw = await _chat(messages, max_tokens, model)
    try:
        return json.loads(_strip_fence(raw))
    except json.JSONDecodeError:
        repair = messages + [
            {"role": "assistant", "content": raw[:2000]},
            {"role": "user", "content": "That was not valid JSON. Return ONLY the JSON object, no prose, no markdown."},
        ]
        raw2 = await _chat(repair, max_tokens, model)
        try:
            return json.loads(_strip_fence(raw2))
        except json.JSONDecodeError as exc:
            raise InferenceError(f"model returned non-JSON: {raw2[:160]!r}") from exc


async def health() -> tuple[str, str | None]:
    """Cheap authenticated check, cached for 60s. Never logs the key."""
    if not settings.inference_enabled:
        return "missing_key", "VULTR_INFERENCE_API_KEY not set (planner runs in heuristic stub mode)"
    if time.time() - _health["checked_at"] < 60:
        return _health["status"], _health["error"]
    try:
        await _chat([{"role": "user", "content": "Reply with the word ok."}], max_tokens=5)
        _health.update(status="ok", error=None)
    except Exception as exc:  # noqa: BLE001
        _health.update(status="error", error=str(exc)[:200])
    _health["checked_at"] = time.time()
    return _health["status"], _health["error"]
