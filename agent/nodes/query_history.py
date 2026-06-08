"""query_history node — embed the current description, retrieve prior context.

Combines two signals:
  * pgvector cosine search   — semantically similar past frames (any location).
  * SQL location/time filter — recent frames at the same waypoint (loitering/repeat).
The current frame's embedding is computed here once and stashed on the state so
update_state can reuse it without a second API call.
"""

from __future__ import annotations

import asyncio

from agent import db
from agent.embedder import embed_text
from agent.state import AgentState


def _merge_unique(*rowsets: list[dict]) -> list[dict]:
    seen: set[str] = set()
    merged: list[dict] = []
    for rows in rowsets:
        for r in rows:
            fid = r.get("frame_id")
            if fid in seen:
                continue
            seen.add(fid)
            merged.append(r)
    return merged


async def node(state: AgentState) -> dict:
    current = state["current_frame"]
    vlm = current.get("vlm_json", {})
    telemetry = state.get("telemetry", {})

    description = vlm.get("description") or vlm.get("raw_description") or ""
    embedding = await asyncio.to_thread(embed_text, description)

    location = telemetry.get("location") or vlm.get("location") or ""
    similar, recent = await asyncio.gather(
        db.query_similar_frames(embedding, limit=10),
        db.query_recent_by_location(location, within_minutes=60, limit=10),
    )

    history = _merge_unique(recent, similar)
    return {
        "current_frame": {**current, "embedding": embedding},
        "history": history,
    }
