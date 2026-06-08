"""Video-level ingest orchestrator (the clip flow).

Drives the whole video-level pipeline for one uploaded clip:

    source clip
      → video_loader.sample_frames        (OpenCV sampling + synthetic telemetry)
      → per frame: blob_store.upload_frame (→ MinIO blob_url)
                   analyze_frame           (Groq VISION — describe the single still)
                   embed_text              (1536-dim, for frame search)
                   db.insert_frame(clip_id) (persist; NO per-frame event/alert)
      → reason_video.judge_clip            (Groq VISION — judge the ACTION across the clip)
      → db.insert_clip / insert_event / insert_alert  (one verdict for the whole video)

Unlike the per-frame agent (agent/graph.py), alerting happens once, at the clip level —
the deliberate "alert on the video, not the image" design.
"""

from __future__ import annotations

import asyncio
import base64
import uuid

from agent import db
from agent.embedder import embed_text
from agent.nodes.analyze_frame import analyze_frame
from agent.nodes.reason_video import judge_clip
from agent.state import frame_timestamp
from data.blob_store import upload_frame
from data.video_loader import sample_frames

# How many representative stills to attach to the clip-level judge.
MAX_JUDGE_IMAGES = 4


def _pick_representative_indices(n: int, k: int = MAX_JUDGE_IMAGES) -> list[int]:
    """Up to ``k`` evenly-spaced frame indices over ``[0, n)`` (always includes 0 and n-1)."""
    if n <= 0:
        return []
    if n <= k:
        return list(range(n))
    step = (n - 1) / (k - 1)
    return sorted({round(i * step) for i in range(k)})


async def _ingest_one_frame(frame_bytes: bytes, telemetry: dict, clip_id: str) -> dict:
    """Upload + analyze + embed + persist a single frame; return its compact summary."""
    blob_url = await asyncio.to_thread(upload_frame, frame_bytes)
    vlm = await asyncio.to_thread(analyze_frame, blob_url)
    description = vlm.get("description") or ""
    embedding = await asyncio.to_thread(embed_text, description)

    frame_id = f"frame_{uuid.uuid4().hex}"
    location = telemetry.get("location") or vlm.get("location")
    await db.insert_frame(
        frame_id=frame_id,
        timestamp=frame_timestamp(telemetry),
        blob_url=blob_url,
        raw_description=description,
        location=location,
        object_type=vlm.get("object_type"),
        action=vlm.get("action"),
        clothing=vlm.get("clothing"),
        color=vlm.get("color"),
        embedding=embedding,
        telemetry=telemetry,
        clip_id=clip_id,
    )
    return {
        "frame_id": frame_id,
        "blob_url": blob_url,
        "time": telemetry.get("time"),
        "location": location or "unknown",
        "object_type": vlm.get("object_type", "none"),
        "action": vlm.get("action", ""),
        "color": vlm.get("color", ""),
        "description": description,
    }


async def process_video(
    *,
    video_path: str,
    filename: str | None = None,
    interval: float = 2.0,
    max_frames: int = 12,
    start_time: str | None = None,
    location: str | None = None,
    seed: int = 42,
) -> dict:
    """Ingest one clip end-to-end and return ``{clip_id, frame_count, frames, verdict}``."""
    clip_id = f"clip_{uuid.uuid4().hex}"

    frames: list[dict] = []
    frame_jpegs: list[bytes] = []
    for frame_bytes, telemetry in sample_frames(
        video_path,
        interval_seconds=interval,
        max_frames=max_frames,
        seed=seed,
        start_time=start_time,
        location=location,
    ):
        summary = await _ingest_one_frame(frame_bytes, telemetry, clip_id)
        frames.append(summary)
        frame_jpegs.append(frame_bytes)

    if not frames:
        raise ValueError(f"no frames could be sampled from {filename or video_path}")

    # Representative stills for the multimodal clip judge.
    rep_idx = _pick_representative_indices(len(frames))
    rep_image_uris = [
        "data:image/jpeg;base64," + base64.b64encode(frame_jpegs[i]).decode("ascii")
        for i in rep_idx
    ]

    verdict = await judge_clip(frames, rep_image_uris)

    key_idx = verdict.get("key_frame_index", 0)
    representative_blob_url = frames[key_idx]["blob_url"] if frames else None

    # Persist the clip verdict + one clip-level event, and an alert iff warranted.
    await db.insert_clip(
        clip_id=clip_id,
        filename=filename,
        frame_count=len(frames),
        action_summary=verdict["action_summary"],
        verdict="alert" if verdict["alert"] else "normal",
        severity=verdict["severity"],
        narrative=verdict["narrative"],
        representative_blob_url=representative_blob_url,
    )
    await db.insert_event(
        event_type=verdict["event_type"],
        description=verdict["narrative"],
        severity=verdict["severity"],
        blob_url=representative_blob_url,
        clip_id=clip_id,
    )
    if verdict["alert"]:
        await db.insert_alert(
            rule="video_action",
            message=verdict["action_summary"],
            severity=verdict["severity"],
            blob_url=representative_blob_url,
            clip_id=clip_id,
            metadata={
                "event_type": verdict["event_type"],
                "narrative": verdict["narrative"],
                "frame_count": len(frames),
                "filename": filename,
            },
        )

    return {
        "clip_id": clip_id,
        "filename": filename,
        "frame_count": len(frames),
        "frames": frames,
        "verdict": verdict,
        "representative_blob_url": representative_blob_url,
    }
