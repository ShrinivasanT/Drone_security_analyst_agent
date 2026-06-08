"""GET /events — paginated event log (each row carries its frame blob_url)."""

from __future__ import annotations

from fastapi import APIRouter, Query

from agent import db

router = APIRouter()


@router.get("/events")
async def list_events(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    events = await db.fetch_events(limit=limit, offset=offset)
    return {"count": len(events), "events": events}
