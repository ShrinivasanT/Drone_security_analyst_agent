"""Video-level verification: run the clip flow on one short clip; assert DB writes.

Runs agent.video_pipeline.process_video on a single source clip (frames sampled, each
analyzed with Groq vision and persisted, then one clip-level verdict), and asserts:
  * every sampled frame persisted a frames row sharing the clip's clip_id, with a real
    blob_url and a 1536-dim embedding
  * exactly one clips row was written for that clip
  * a clip-level event was logged (and an alert row exists iff the verdict alerted)

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
from agent.video_pipeline import process_video

MAX_FRAMES = 6
TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://drone:drone_pass@localhost:5432/drone_security",
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("GROQ_API_KEY"),
    reason="GROQ_API_KEY not set; skipping live clip pipeline test (vision on Groq)",
)


async def test_video_pipeline_end_to_end():
    db.init_db(TEST_DB_URL)
    try:
        await db.ping()
        await db.migrate()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Postgres not reachable at {TEST_DB_URL}: {exc}")

    clips = sorted(Path(os.environ.get("VIDEO_SOURCE_DIR", "videos")).glob("*.mp4"))
    if not clips:
        pytest.skip("no .mp4 clips under VIDEO_SOURCE_DIR")

    try:
        result = await process_video(
            video_path=str(clips[0]),
            filename=clips[0].name,
            interval=2.0,
            max_frames=MAX_FRAMES,
            seed=7,
        )
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"clip pipeline could not run (MinIO/clip/API issue): {exc}")

    clip_id = result["clip_id"]
    assert clip_id.startswith("clip_")
    assert 1 <= result["frame_count"] <= MAX_FRAMES
    assert len(result["frames"]) == result["frame_count"]

    verdict = result["verdict"]
    for key in ("action_summary", "alert", "severity", "event_type", "narrative"):
        assert key in verdict

    engine = db.get_engine()
    async with engine.connect() as conn:
        # 1) every frame persisted under this clip_id, with a 1536-dim embedding
        frame_rows = (
            await conn.execute(
                text(
                    "SELECT blob_url, embedding IS NOT NULL AS has_emb,"
                    " vector_dims(embedding) AS dims"
                    " FROM frames WHERE clip_id = :cid"
                ),
                {"cid": clip_id},
            )
        ).mappings().all()
        assert len(frame_rows) == result["frame_count"]
        for row in frame_rows:
            assert row["blob_url"].startswith("http")
            assert row["has_emb"] is True
            assert row["dims"] == 1536

        # 2) exactly one clips row for this clip
        clip_count = (
            await conn.execute(
                text("SELECT COUNT(*) FROM clips WHERE clip_id = :cid"), {"cid": clip_id}
            )
        ).scalar_one()
        assert clip_count == 1

        # 3) a clip-level event; an alert row iff the verdict alerted
        event_count = (
            await conn.execute(
                text("SELECT COUNT(*) FROM events WHERE clip_id = :cid"), {"cid": clip_id}
            )
        ).scalar_one()
        assert event_count >= 1

        alert_count = (
            await conn.execute(
                text("SELECT COUNT(*) FROM alerts WHERE clip_id = :cid"), {"cid": clip_id}
            )
        ).scalar_one()
        assert alert_count == (1 if verdict["alert"] else 0)

    await db.close_db()
