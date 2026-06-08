"""GET /alerts — alert registry (each includes the triggering frame's blob_url)."""

from __future__ import annotations

from fastapi import APIRouter, Query

from agent import db

router = APIRouter()


@router.get("/alerts")
async def list_alerts(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    active_only: bool = Query(False, description="only unresolved alerts (resolved_at IS NULL)"),
) -> dict:
    alerts = await db.fetch_alerts(limit=limit, offset=offset, active_only=active_only)
    return {"count": len(alerts), "alerts": alerts}
