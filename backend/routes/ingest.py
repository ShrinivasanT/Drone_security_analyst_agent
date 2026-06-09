"""POST /ingest — runs the full LangGraph agent (Stage 5).

Validates ``{ blob_url, telemetry }``, then runs one complete agent cycle:
analyze_frame → query_history → reason_decide → (log_event / trigger_alert) →
update_state. Returns the agent's decision plus the IDs of what was persisted.

``POST /ingest_image`` is the browser-facing variant: it accepts a multipart image
upload plus telemetry form fields, pushes the bytes to MinIO to obtain a ``blob_url``,
then runs the same per-frame agent. Only images are ingested — a video upload is
rejected (the UI blocks it client-side; this guard is defence in depth).
"""

from __future__ import annotations

import asyncio
import os
import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from agent.graph import run_frame
from data.blob_store import upload_frame

router = APIRouter()

# Extensions we accept when the browser doesn't send a precise image/* content type.
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


class Telemetry(BaseModel):
    # Synthetic drone telemetry from data/video_loader.py. Extra keys allowed.
    model_config = ConfigDict(extra="allow")

    time: str | None = Field(default=None, description='"HH:MM" of the simulated patrol day')
    location: str | None = None
    lat: float | None = None
    lng: float | None = None
    altitude: float | None = None


class IngestRequest(BaseModel):
    blob_url: str = Field(..., min_length=1)
    telemetry: Telemetry = Field(default_factory=Telemetry)


@router.post("/ingest")
async def ingest(req: IngestRequest) -> dict:
    telemetry = req.telemetry.model_dump()
    try:
        return await run_frame(req.blob_url, telemetry)
    except Exception as exc:  # noqa: BLE001 — surface agent failures as 500s
        raise HTTPException(status_code=500, detail=f"agent run failed: {exc}") from exc


@router.post("/ingest_image")
async def ingest_image(
    file: UploadFile = File(...),
    time: str | None = Form(None),
    location: str | None = Form(None),
    lat: float | None = Form(None),
    lng: float | None = Form(None),
    altitude: float | None = Form(None),
) -> dict:
    """Upload an image + dropdown telemetry, store it in MinIO, run the per-frame agent."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    content_type = file.content_type or ""
    if not content_type.startswith("image/") and ext not in _IMAGE_EXTS:
        raise HTTPException(
            status_code=415,
            detail="only images are ingested; video ingestion is not supported",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty upload")

    try:
        blob_url = await asyncio.to_thread(
            upload_frame, data, f"upload_{uuid.uuid4().hex}{ext or '.jpg'}"
        )
    except Exception as exc:  # noqa: BLE001 — surface storage failures as 502s
        raise HTTPException(status_code=502, detail=f"blob upload failed: {exc}") from exc

    # Drop unset fields so the agent sees only the telemetry the operator actually chose.
    telemetry = {
        k: v
        for k, v in {
            "time": time,
            "location": location,
            "lat": lat,
            "lng": lng,
            "altitude": altitude,
        }.items()
        if v not in (None, "")
    }

    try:
        return await run_frame(blob_url, telemetry)
    except Exception as exc:  # noqa: BLE001 — surface agent failures as 500s
        raise HTTPException(status_code=500, detail=f"agent run failed: {exc}") from exc
