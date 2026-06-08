"""trigger_alert node — write one alert row per fired rule (runs for 'alert' route)."""

from __future__ import annotations

from agent import db
from agent.state import AgentState


async def node(state: AgentState) -> dict:
    decision = state.get("decision", {})
    fired = decision.get("fired_rules", [])
    current = state["current_frame"]
    blob_url = current["blob_url"]
    telemetry = state.get("telemetry", {})

    new_alerts: list[dict] = []
    for rule in fired:
        row = await db.insert_alert(
            rule=rule["rule"],
            message=rule["message"],
            severity=rule["severity"],
            blob_url=blob_url,
            metadata={
                "time": telemetry.get("time"),
                "location": telemetry.get("location"),
                "object_type": current.get("vlm_json", {}).get("object_type"),
            },
        )
        new_alerts.append({
            "id": row["id"],
            "rule": rule["rule"],
            "message": rule["message"],
            "severity": rule["severity"],
            "blob_url": blob_url,
        })

    active = list(state.get("active_alerts", []))
    active.extend(new_alerts)
    return {"active_alerts": active}
