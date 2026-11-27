"""Vultr Serverless Inference client. The only LLM endpoint SafePilot QA may call.

TODO(step 3): add the Section 4.3 retry wrapper (429/502/503/504, backoff with jitter).
"""

from __future__ import annotations

from openai import OpenAI

from app.config import Settings

VULTR_INFERENCE_HOST = "api.vultrinference.com"


def make_client(settings: Settings) -> OpenAI:
    if not settings.inference_api_key:
        raise RuntimeError("VULTR_INFERENCE_API_KEY is not set on the control plane")
    if VULTR_INFERENCE_HOST not in settings.inference_base_url:
        raise RuntimeError(f"inference base URL must point at {VULTR_INFERENCE_HOST}")
    return OpenAI(
        api_key=settings.inference_api_key,
        base_url=settings.inference_base_url,
        timeout=settings.inference_timeout_seconds,
        max_retries=0,
    )


def check_inference(settings: Settings) -> tuple[str, str | None]:
    """Cheap authenticated call (model list). Returns ("ok", None) or ("error", reason)."""
    try:
        models = {m.id for m in make_client(settings).models.list()}
    except Exception as exc:  # never include the key in the message
        return "error", f"{type(exc).__name__}: {str(exc)[:200]}"
    if settings.inference_model not in models:
        return "error", f"model {settings.inference_model} not offered by the endpoint"
    return "ok", None
