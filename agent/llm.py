"""LLM provider abstraction for chat + vision, with cross-provider fallback.

Both OpenAI and Groq expose an OpenAI-compatible chat-completions API, so a single
``openai.OpenAI`` client works for either — only the ``base_url``, key, and model names
differ. This module picks a provider order from the available API keys and tries each in
turn, so the system keeps working if the primary provider is down or unconfigured.

POLICY: vision (analyze_frame) and reasoning (reason_decide) run on **Groq**. OpenAI is
reserved for *embeddings only* (agent/embedder.py) and is excluded from the chat/vision
provider chain unless ``LLM_ALLOW_OPENAI_CHAT=true`` is explicitly set. So even when an
OpenAI key is present (for embeddings), it is never used for vision/reasoning by default.

Provider selection (``LLM_PROVIDER`` env): ``auto`` (default) prefers Groq when
``GROQ_API_KEY`` is set, else OpenAI. Force with ``groq`` or ``openai``.

NOTE: embeddings are handled separately in agent/embedder.py — Groq has no embeddings
endpoint.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

GROQ_BASE_URL = os.environ.get("GROQ_BASE_URL") or "https://api.groq.com/openai/v1"

# Per-provider model defaults. Resolved lazily so empty env values (e.g. compose's
# ${VAR:-}) fall through to these rather than overriding them with "".
_DEFAULT_MODELS = {
    ("groq", "vision"): "meta-llama/llama-4-scout-17b-16e-instruct",
    ("groq", "text"): "llama-3.3-70b-versatile",
    ("openai", "vision"): "gpt-4o",
    ("openai", "text"): "gpt-4o-mini",
}
_MODEL_ENV = {
    ("groq", "vision"): "GROQ_VLM_MODEL",
    ("groq", "text"): "GROQ_TEXT_MODEL",
    ("openai", "vision"): "OPENAI_VLM_MODEL",
    ("openai", "text"): "OPENAI_TEXT_MODEL",
}


def _env(name: str) -> str | None:
    """Return the env value, treating empty/whitespace as absent (None)."""
    val = os.environ.get(name)
    return val if (val and val.strip()) else None


def _have(provider: str) -> bool:
    return bool(_env("GROQ_API_KEY" if provider == "groq" else "OPENAI_API_KEY"))


def _bool_env(name: str, default: bool = False) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def provider_order() -> list[str]:
    """Return chat/vision providers to try, in priority order, filtered to available keys.

    OpenAI is dropped from the chat/vision chain unless ``LLM_ALLOW_OPENAI_CHAT=true`` —
    it is reserved for embeddings. So with the default config and a Groq key set, this
    returns ``["groq"]`` and OpenAI is never used for vision/reasoning.
    """
    pref = os.environ.get("LLM_PROVIDER", "auto").lower()
    if pref == "groq":
        order = ["groq", "openai"]
    elif pref == "openai":
        order = ["openai", "groq"]
    else:  # auto
        order = ["groq", "openai"] if _have("groq") else ["openai", "groq"]

    allow_openai_chat = _bool_env("LLM_ALLOW_OPENAI_CHAT", False)
    chain: list[str] = []
    for p in order:
        if p == "openai" and not allow_openai_chat:
            continue  # OpenAI reserved for embeddings, not chat/vision
        if _have(p):
            chain.append(p)
    return chain


@lru_cache(maxsize=2)
def _client(provider: str) -> OpenAI:
    if provider == "groq":
        return OpenAI(api_key=os.environ["GROQ_API_KEY"], base_url=GROQ_BASE_URL)
    return OpenAI()  # OpenAI SDK reads OPENAI_API_KEY


def _model(provider: str, kind: str) -> str:
    # A generic override (VLM_MODEL / REASONING_MODEL) wins for the active provider,
    # then a provider-specific override, then the built-in default.
    forced = _env("VLM_MODEL" if kind == "vision" else "REASONING_MODEL")
    if forced:
        return forced
    return _env(_MODEL_ENV[(provider, kind)]) or _DEFAULT_MODELS[(provider, kind)]


def _parse_json(content: str) -> dict:
    """Robustly parse a JSON object from a model response (handles code fences/prose)."""
    s = (content or "").strip()
    if s.startswith("```"):
        s = s.strip("`")
        # drop an optional leading "json" language tag
        if s[:4].lower() == "json":
            s = s[4:]
        s = s.strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        i, j = s.find("{"), s.rfind("}")
        if i != -1 and j != -1 and j > i:
            return json.loads(s[i : j + 1])
        raise


def complete_json(
    *,
    system: str,
    text: str,
    image_data_uri: str | None = None,
    image_data_uris: list[str] | None = None,
    temperature: float = 0,
) -> dict:
    """Call the first working provider and return a parsed JSON object.

    Pass ``image_data_uri`` (single) or ``image_data_uris`` (several, e.g. representative
    frames of a clip) to make it a vision request; with neither it's a text request (with
    JSON-mode response_format requested). The two image args are merged, single first.
    """
    images = [image_data_uri] if image_data_uri else []
    images += image_data_uris or []

    order = provider_order()
    if not order:
        raise RuntimeError(
            "no chat/vision provider available: set GROQ_API_KEY "
            "(OpenAI is reserved for embeddings; enable it for chat with "
            "LLM_ALLOW_OPENAI_CHAT=true)"
        )

    kind = "vision" if images else "text"
    last_err: Exception | None = None

    for provider in order:
        client = _client(provider)
        model = _model(provider, kind)
        try:
            if images:
                # Fold the system instruction into the user turn — most compatible with
                # vision models across providers (some reject a system role + image).
                content = [{"type": "text", "text": f"{system}\n\n{text}"}]
                content += [
                    {"type": "image_url", "image_url": {"url": uri}} for uri in images
                ]
                messages = [{"role": "user", "content": content}]
                kwargs: dict = {}
            else:
                messages = [
                    {"role": "system", "content": system},
                    {"role": "user", "content": text},
                ]
                kwargs = {"response_format": {"type": "json_object"}}

            resp = client.chat.completions.create(
                model=model, temperature=temperature, messages=messages, **kwargs
            )
            return _parse_json(resp.choices[0].message.content or "{}")
        except Exception as exc:  # noqa: BLE001 — try the next provider
            last_err = exc
            continue

    raise RuntimeError(f"all LLM providers failed ({order}): {last_err}")


def active_provider() -> str | None:
    order = provider_order()
    return order[0] if order else None
