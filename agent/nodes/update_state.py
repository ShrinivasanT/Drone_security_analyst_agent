"""update_state node — persist the analyzed frame and build the API result.

Terminal node of the per-frame pipeline. Alerting now happens at the video level
(agent/video_pipeline.py), so this node is analysis-only: it writes the frame row
(metadata + blob_url + embedding), advances the session rolling window, and returns the
payload ``POST /ingest`` responds with. It no longer logs events or triggers alerts.
"""

from __future__ import annotations

import uuid

from agent import db
from agent.state import AgentState, frame_timestamp, get_session


async def node(state: AgentState) -> dict:
    current = state["current_frame"]
    vlm = current.get("vlm_json", {})
    telemetry = state.get("telemetry", {})
    blob_url = current["blob_url"]
    embedding = current.get("embedding")

    frame_id = f"frame_{uuid.uuid4().hex}"
    # Location stored on the frame is the telemetry waypoint (falls back to VLM scene).
    location = telemetry.get("location") or vlm.get("location")

    frame_row = await db.insert_frame(
        frame_id=frame_id,
        timestamp=frame_timestamp(telemetry),
        blob_url=blob_url,
        raw_description=vlm.get("description", ""),
        location=location,
        object_type=vlm.get("object_type"),
        action=vlm.get("action"),
        clothing=vlm.get("clothing"),
        color=vlm.get("color"),
        embedding=embedding,
        telemetry=telemetry,
    )

    # Advance durable session memory (rolling window of recent frame summaries).
    session = get_session()
    session.push_frame({
        "frame_id": frame_id,
        "blob_url": blob_url,
        "object_type": vlm.get("object_type", "none"),
        "location": location or "unknown",
        "action": vlm.get("action", ""),
        "color": vlm.get("color", ""),
        "time": telemetry.get("time"),
    })

    result = {
        "status": "ok",
        "stub": False,
        "frame_id": frame_id,
        "db_id": frame_row["id"],
        "blob_url": blob_url,
        "vlm": vlm,
    }
    return {"result": result}
