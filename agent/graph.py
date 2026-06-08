"""LangGraph wiring for the per-frame analysis pipeline.

Linear, analysis-only backbone (alerting now lives at the VIDEO level — see
agent/video_pipeline.py — so this path just describes and persists each frame):
    ingest_frame → analyze_frame → query_history → update_state

The legacy per-frame alerting nodes (reason_decide / log_event / trigger_alert) and the
rule engine (agent/rules.py) are no longer wired here; alert decisions are made once per
clip by agent/nodes/reason_video.py.
"""

from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, StateGraph

from agent.nodes import (
    analyze_frame,
    ingest_frame,
    query_history,
    update_state,
)
from agent.state import AgentState


def build_graph():
    g = StateGraph(AgentState)

    g.add_node("ingest_frame", ingest_frame.node)
    g.add_node("analyze_frame", analyze_frame.node)
    g.add_node("query_history", query_history.node)
    g.add_node("update_state", update_state.node)

    g.set_entry_point("ingest_frame")
    g.add_edge("ingest_frame", "analyze_frame")
    g.add_edge("analyze_frame", "query_history")
    g.add_edge("query_history", "update_state")
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
