"""log_event node — write a human-readable event row (runs for 'log' and 'alert' routes)."""

from __future__ import annotations

from agent import db
from agent.state import AgentState


async def node(state: AgentState) -> dict:
    decision = state.get("decision", {})
    current = state["current_frame"]
    blob_url = current["blob_url"]
    vlm = current.get("vlm_json", {})

    row = await db.insert_event(
        event_type=decision.get("event_type", "detection"),
        description=decision.get("summary", vlm.get("description", "")),
        severity=decision.get("severity", "info"),
        frame_id=None,  # frame row is written later in update_state; keep event independent
        blob_url=blob_url,
    )

    event_record = {
        "id": row["id"],
        "event_type": decision.get("event_type", "detection"),
        "description": decision.get("summary", ""),
        "severity": decision.get("severity", "info"),
        "blob_url": blob_url,
        "time": state.get("telemetry", {}).get("time"),
    }
    events = list(state.get("events_today", []))
    events.append(event_record)
    return {"events_today": events}
