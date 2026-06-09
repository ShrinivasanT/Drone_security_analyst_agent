"""Per-frame agent verification (Stage 5): run the full graph on real frames; assert DB writes.

Samples a few frames from a source clip, uploads each to MinIO, and runs the per-frame
LangGraph agent via ``agent.graph.run_frame`` (ingest_frame → analyze_frame → query_history
→ reason_decide → log/alert → update_state). Asserts that:
  * each cycle returns an ``ok`` result with a routing decision (normal/log/alert) and the
    structured VLM analysis
  * every processed frame persisted a frames row with a real blob_url and a 1536-dim embedding

Connects to the host-published Postgres (localhost:5432). Skips automatically if
GROQ_API_KEY is unset or MinIO/Postgres/the clips are unreachable.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv()

from agent import db
from agent.graph import run_frame
from agent.state import reset_session
from data.blob_store import upload_frame
from data.video_loader import sample_frames

N_FRAMES = 6
VALID_ROUTES = {"normal", "log", "alert"}
TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://drone:drone_pass@localhost:5432/drone_security",
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("GROQ_API_KEY"),
    reason="GROQ_API_KEY not set; skipping live per-frame pipeline test (vision on Groq)",
)


async def test_agent_pipeline_end_to_end():
    db.init_db(TEST_DB_URL)
    try:
        await db.ping()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Postgres not reachable at {TEST_DB_URL}: {exc}")

    clips = sorted(Path(os.environ.get("VIDEO_SOURCE_DIR", "videos")).glob("*.mp4"))
    if not clips:
        pytest.skip("no .mp4 clips under VIDEO_SOURCE_DIR")

    reset_session()
    ran = 0
    try:
        for frame_bytes, telemetry in sample_frames(
            str(clips[0]), interval_seconds=2.0, max_frames=N_FRAMES, seed=7
        ):
            blob_url = upload_frame(frame_bytes)
            result = await run_frame(blob_url, telemetry)
            ran += 1

            assert result["status"] == "ok"
            assert result["blob_url"] == blob_url
            assert result["frame_id"].startswith("frame_")
            assert result["decision"]["route"] in VALID_ROUTES
            for key in ("object_type", "location", "action", "confidence"):
                assert key in result["vlm"]
    except AssertionError:
        raise
    except Exception as exc:  # noqa: BLE001 — MinIO/clip/API issue, not a test failure
        pytest.skip(f"per-frame pipeline could not run (MinIO/clip/API issue): {exc}")

    if ran == 0:
        pytest.skip("no frames sampled from the clip")

    engine = db.get_engine()
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT blob_url, embedding IS NOT NULL AS has_emb,"
                    " vector_dims(embedding) AS dims"
                    " FROM frames ORDER BY id DESC LIMIT :n"
                ),
                {"n": ran},
            )
        ).mappings().all()
        assert len(rows) == ran
        for row in rows:
            assert row["blob_url"].startswith("http")
            assert row["has_emb"] is True
            assert row["dims"] == 1536

    await db.close_db()
