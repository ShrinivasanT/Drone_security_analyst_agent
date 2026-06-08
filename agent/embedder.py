"""Text embedding (1536-dim) with provider fallback.

Primary: OpenAI ``text-embedding-3-small``. Groq has NO embeddings endpoint, so when no
OpenAI key is configured we fall back to a dependency-free deterministic hashing
embedder. The fallback is a bag-of-words hashed into the same 1536-dim space and
L2-normalized — lower quality than a learned model, but it keeps pgvector similarity
search functional and leaves the VECTOR(1536) schema/index untouched.

Control with EMBEDDING_PROVIDER: ``auto`` (default — OpenAI if its key is set, else
local), ``openai`` (force, error if unkeyed), or ``local`` (force hashing fallback).
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIM = 1536
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _use_openai() -> bool:
    pref = os.environ.get("EMBEDDING_PROVIDER", "auto").lower()
    if pref == "openai":
        return True
    if pref == "local":
        return False
    return bool(os.environ.get("OPENAI_API_KEY"))  # auto


@lru_cache(maxsize=1)
def _openai_client():
    from openai import OpenAI

    return OpenAI()


def _openai_embed(text: str) -> list[float]:
    resp = _openai_client().embeddings.create(model=EMBEDDING_MODEL, input=text)
    return resp.data[0].embedding


def _hash_embed(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """Deterministic, dependency-free fallback embedding (hashed bag-of-words)."""
    tokens = _TOKEN_RE.findall(text.lower()) or [text.strip() or "empty"]
    vec = [0.0] * dim
    for tok in tokens:
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h >> 7) & 1 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec


def embed_text(text: str) -> list[float]:
    """Return a 1536-dim embedding for ``text`` (OpenAI if available, else local)."""
    payload = text.strip() or " "
    if _use_openai():
        vector = _openai_embed(payload)
        if len(vector) != EMBEDDING_DIM:
            raise ValueError(
                f"expected {EMBEDDING_DIM}-dim embedding, got {len(vector)} "
                f"from model {EMBEDDING_MODEL!r}"
            )
        return vector
    return _hash_embed(payload)


if __name__ == "__main__":
    provider = "openai" if _use_openai() else "local-hash"
    v = embed_text("a white sedan parked near the main gate at night")
    print(f"provider={provider} dim={len(v)} first3={v[:3]}")
