"""update_state node — persist the analyzed frame and build the API result.

Terminal node of the per-frame pipeline. It writes the frame row (metadata + blob_url +
embedding), advances the durable session memory (rolling window of recent frames, plus the
events/alerts accumulated this cycle by log_event/trigger_alert), and returns the payload
``POST /ingest`` responds with — including the routing decision and how many events/alerts
were raised.
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
    decision = state.get("decision", {})
    route = decision.get("route", "normal")
    fired = decision.get("fired_rules", [])

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

    # Advance durable session memory: rolling window + write back this cycle's
    # events/alerts so cross-frame rules (loitering, repeat vehicle) and the operator
    # views see them on subsequent frames.
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
    session.events_today = list(state.get("events_today", []))
    session.active_alerts = list(state.get("active_alerts", []))

    result = {
        "status": "ok",
        "frame_id": frame_id,
        "db_id": frame_row["id"],
        "blob_url": blob_url,
        "vlm": vlm,
        "decision": decision,
        "fired_rules": fired,
        "events_logged": 1 if route in ("log", "alert") else 0,
        "alerts_triggered": len(fired) if route == "alert" else 0,
    }
    return {"result": result}
