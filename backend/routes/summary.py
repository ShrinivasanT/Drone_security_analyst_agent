"""GET /summary — LLM-generated session summary grounded in DB aggregates."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter

from agent import db
from agent.llm import complete_json

router = APIRouter()

_SYSTEM = (
    "You are a drone security analyst writing an end-of-session briefing for a human "
    "operator. Be concise, factual, and operational. Respond with JSON only."
)


def _build_prompt(stats: dict, recent_alerts: list[dict]) -> str:
    alert_lines = [
        f"- [{a['severity']}] {a['rule']}: {a['message']}" for a in recent_alerts[:15]
    ] or ["  (no alerts)"]
    return (
        "SESSION STATISTICS:\n"
        f"{json.dumps(stats, indent=2, default=str)}\n\n"
        "RECENT ALERTS (newest first):\n" + "\n".join(alert_lines) + "\n\n"
        "Return JSON with keys:\n"
        '  "summary": a 3-5 sentence operator briefing covering overall activity, the '
        "most significant alerts, and any patterns (e.g. repeated after-hours presence).\n"
        '  "headline": a single short sentence (the one thing the operator must know).\n'
    )


@router.get("/summary")
async def session_summary() -> dict:
    stats = await db.fetch_summary_stats()
    recent_alerts = await db.fetch_alerts(limit=15)

    narrative: dict = {}
    try:
        narrative = await asyncio.to_thread(
            complete_json, system=_SYSTEM, text=_build_prompt(stats, recent_alerts)
        )
    except Exception as exc:  # noqa: BLE001 — summary still returns stats if LLM fails
        narrative = {
            "summary": (
                f"{stats['frames']} frames analysed, {stats['events']} events logged, "
                f"{stats['alerts']} alerts raised."
            ),
            "headline": "LLM summary unavailable; showing raw statistics.",
            "error": str(exc),
        }

    return {
        "stats": stats,
        "headline": narrative.get("headline", ""),
        "summary": narrative.get("summary", ""),
    }
