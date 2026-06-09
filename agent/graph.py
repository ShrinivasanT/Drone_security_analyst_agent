"""LangGraph wiring for the per-frame analysis + alerting pipeline (Stage 5).

The full reasoning cycle for one frame:

    ingest_frame → analyze_frame → query_history → reason_decide
        → (log_event → trigger_alert)   [route "alert"]
        → (log_event)                   [route "log"]
        → (—)                           [route "normal"]
        → update_state → END

``reason_decide`` produces a routing ``decision`` (normal / log / alert) from the
deterministic rule engine (agent/rules.py) plus an LLM narrative; conditional edges then
fan out to log an event and/or trigger alert(s) before the terminal ``update_state`` node
persists the frame and builds the API result.
"""

from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, StateGraph

from agent.nodes import (
    analyze_frame,
    ingest_frame,
    log_event,
    query_history,
    reason_decide,
    trigger_alert,
    update_state,
)
from agent.state import AgentState


def _route(state: AgentState) -> str:
    """Routing key from reason_decide's decision: 'normal' | 'log' | 'alert'."""
    return state.get("decision", {}).get("route", "normal")


def build_graph():
    g = StateGraph(AgentState)

    g.add_node("ingest_frame", ingest_frame.node)
    g.add_node("analyze_frame", analyze_frame.node)
    g.add_node("query_history", query_history.node)
    g.add_node("reason_decide", reason_decide.node)
    g.add_node("log_event", log_event.node)
    g.add_node("trigger_alert", trigger_alert.node)
    g.add_node("update_state", update_state.node)

    g.set_entry_point("ingest_frame")
    g.add_edge("ingest_frame", "analyze_frame")
    g.add_edge("analyze_frame", "query_history")
    g.add_edge("query_history", "reason_decide")

    # normal → straight to persist; log/alert → log the event first.
    g.add_conditional_edges(
        "reason_decide",
        _route,
        {"normal": "update_state", "log": "log_event", "alert": "log_event"},
    )
    # after logging: alert → also trigger alert(s); otherwise persist.
    g.add_conditional_edges(
        "log_event",
        _route,
        {"alert": "trigger_alert", "log": "update_state", "normal": "update_state"},
    )
    g.add_edge("trigger_alert", "update_state")
    g.add_edge("update_state", END)

    return g.compile()


@lru_cache(maxsize=1)
def get_graph():
    """Compiled graph singleton (compilation is cheap but done once)."""
    return build_graph()


async def run_frame(blob_url: str, telemetry: dict) -> dict:
    """Run one full agent cycle for a frame; returns the API result payload."""
    graph = get_graph()
    initial: AgentState = {
        "current_frame": {"blob_url": blob_url, "telemetry": telemetry},
        "telemetry": telemetry,
    }
    final = await graph.ainvoke(initial)
    return final["result"]
