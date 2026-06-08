"""GET /frames/search — semantic frame search (pgvector); returns blob_url per match."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query

from agent import db
from agent.embedder import embed_text

router = APIRouter()


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
