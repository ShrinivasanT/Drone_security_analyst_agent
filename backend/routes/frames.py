"""GET /frames — recent-frame feed; GET /frames/search — semantic frame search (pgvector)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query

from agent import db
from agent.embedder import embed_text

router = APIRouter()


@router.get("/frames")
async def list_frames(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    """Every ingested frame, newest first — drives the Live Telemetry Feed.

    Unlike ``/events`` (only logged/alerted frames), this lists *all* frames, so an
    uploaded image with no alert still shows up here.
    """
    frames = await db.fetch_recent_frames(limit=limit, offset=offset)
    return {"count": len(frames), "frames": frames}


@router.get("/frames/search")
async def search_frames(
    q: str = Query(..., min_length=1, description="natural-language query"),
    limit: int = Query(10, ge=1, le=50),
) -> dict:
    # Embed the query, then cosine-rank stored frames by their description embedding.
    embedding = await asyncio.to_thread(embed_text, q)
    matches = await db.query_similar_frames(embedding, limit=limit)

    results = [
        {
            "frame_id": m["frame_id"],
            "timestamp": m["timestamp"],
            "blob_url": m["blob_url"],
            "object_type": m["object_type"],
            "location": m["location"],
            "action": m["action"],
            "color": m["color"],
            "raw_description": m["raw_description"],
            "similarity": round(float(m["similarity"]), 4) if m.get("similarity") is not None else None,
        }
        for m in matches
    ]
    return {"query": q, "count": len(results), "results": results}
