"""POST /ingest — runs the full LangGraph agent (Stage 5).

Validates ``{ blob_url, telemetry }``, then runs one complete agent cycle:
analyze_frame → query_history → reason_decide → (log_event / trigger_alert) →
update_state. Returns the agent's decision plus the IDs of what was persisted.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from agent.graph import run_frame

router = APIRouter()


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
