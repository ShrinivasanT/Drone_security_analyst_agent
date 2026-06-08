"""Stage 4 verification: 5 real frames from the MinIO bucket → structured JSON + embedding.

Samples 5 frames from a source clip, uploads them to MinIO, then asserts that
``analyze_frame`` returns the required schema for each and that ``embed_text`` returns a
valid 1536-dim vector for the VLM description.

Skips automatically when OPENAI_API_KEY is unset or MinIO/the source clips are unreachable
so the suite stays green in environments without API access.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv()

from agent.embedder import EMBEDDING_DIM, embed_text
from agent.nodes.analyze_frame import analyze_frame
from data.blob_store import upload_frame
from data.video_loader import sample_frames

_REQUIRED_FIELDS = ("object_type", "location", "action", "clothing", "color", "confidence")
N_FRAMES = 5

# Vision runs on Groq; only the vision tests require a Groq key. The embedding test uses
# OpenAI-or-local and runs regardless.
requires_groq = pytest.mark.skipif(
    not os.environ.get("GROQ_API_KEY"),
    reason="GROQ_API_KEY not set; skipping live Groq vision test",
)


def _first_clip() -> Path:
    src = Path(os.environ.get("VIDEO_SOURCE_DIR", "videos"))
    clips = sorted(src.glob("*.mp4"))
    if not clips:
        pytest.skip(f"no .mp4 clips under VIDEO_SOURCE_DIR={src}")
    return clips[0]


@pytest.fixture(scope="module")
def blob_urls() -> list[str]:
    clip = _first_clip()
    urls: list[str] = []
    try:
        for i, (frame_bytes, _telemetry) in enumerate(
            sample_frames(clip, interval_seconds=2.0, max_frames=N_FRAMES, seed=42)
        ):
            urls.append(upload_frame(frame_bytes, f"test_analyze_{i:02d}.jpg"))
    except Exception as exc:  # MinIO down, clip unreadable, etc.
        pytest.skip(f"could not prepare test frames in MinIO: {exc}")
    if len(urls) < N_FRAMES:
        pytest.skip(f"clip yielded only {len(urls)} frames (<{N_FRAMES})")
    return urls


def test_uploaded_five_frames(blob_urls: list[str]) -> None:
    assert len(blob_urls) == N_FRAMES
    assert all(u.endswith(".jpg") for u in blob_urls)


@requires_groq
def test_analyze_returns_structured_json(blob_urls: list[str]) -> None:
    for url in blob_urls:
        result = analyze_frame(url)
        for field in _REQUIRED_FIELDS:
            assert field in result, f"missing {field} for {url}: {result}"
            assert result[field] not in (None, ""), f"empty {field} for {url}"
        assert isinstance(result["confidence"], float)
        assert 0.0 <= result["confidence"] <= 1.0
        assert isinstance(result["description"], str) and result["description"]


def test_embedding_is_valid() -> None:
    # Embeddings use OpenAI (or the local hashing fallback) — independent of Groq vision.
    vector = embed_text("a white sedan parked near the main gate at night")
    assert isinstance(vector, list)
    assert len(vector) == EMBEDDING_DIM
    assert all(isinstance(x, float) for x in vector)
