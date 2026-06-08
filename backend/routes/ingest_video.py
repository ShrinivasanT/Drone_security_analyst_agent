"""POST /ingest_video — upload a clip, run the video-level agent; GET /clips — list verdicts.

Accepts a multipart video upload plus synthetic-telemetry form fields, streams it to a temp
file, and runs the clip flow (agent/video_pipeline.process_video): every frame is analyzed
with Groq vision and persisted, then the action across the whole clip is judged once to
produce a single verdict (and an alert iff warranted).

Each frame is a separate vision call, so this is synchronous and can take a while —
``max_frames`` defaults low to keep the request responsive.
"""

from __future__ import annotations

import os
import tempfile

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from agent import db
from agent.video_pipeline import process_video

router = APIRouter()

_CHUNK = 1024 * 1024  # 1 MiB streaming chunks


@router.post("/ingest_video")
async def ingest_video(
    file: UploadFile = File(...),
    interval: float = Form(2.0),
    max_frames: int = Form(12),
    start_time: str | None = Form(None),
    location: str | None = Form(None),
    seed: int = Form(42),
) -> dict:
    suffix = os.path.splitext(file.filename or "")[1] or ".mp4"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        while chunk := await file.read(_CHUNK):
            tmp.write(chunk)
        tmp.close()
        return await process_video(
            video_path=tmp.name,
            filename=file.filename,
            interval=interval,
            max_frames=max_frames,
            start_time=(start_time or None),
            location=(location or None),
            seed=seed,
        )
    except Exception as exc:  # noqa: BLE001 — surface pipeline failures as 500s
        raise HTTPException(status_code=500, detail=f"video ingest failed: {exc}") from exc
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


@router.get("/clips")
async def list_clips(limit: int = Query(20, ge=1, le=100)) -> dict:
    clips = await db.fetch_clips(limit=limit)
    return {"count": len(clips), "clips": clips}
