"""ingest_frame node — validate inputs and seed AgentState from the session store."""

from __future__ import annotations

from agent.state import AgentState, get_session


async def node(state: AgentState) -> dict:
    current = state.get("current_frame") or {}
    blob_url = current.get("blob_url")
    if not blob_url:
        raise ValueError("ingest_frame: current_frame.blob_url is required")

    telemetry = state.get("telemetry") or current.get("telemetry") or {}
    session = get_session()

    return {
        "current_frame": {"blob_url": blob_url, "telemetry": telemetry},
        "telemetry": telemetry,
        # Snapshot session memory (pre-current) for reasoning this cycle.
        "rolling_window": list(session.rolling_window),
        "events_today": list(session.events_today),
        "active_alerts": list(session.active_alerts),
        "history": [],
    }
