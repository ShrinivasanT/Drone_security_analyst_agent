"""reason_decide node — LLM narrative + deterministic rule engine → routing decision.

The rule engine (agent/rules.py) decides *whether* an alert fires (reproducible for QA).
The LLM produces the human-readable situational narrative and judges whether an
otherwise-unremarkable frame is still worth logging. If the LLM call fails, we fall back
to a deterministic summary so the pipeline never breaks.

Routes:
  "normal" → just persist the frame
  "log"    → log an event, then persist
  "alert"  → log an event AND trigger alert(s), then persist
"""

from __future__ import annotations

import asyncio
import json

from agent import rules
from agent.llm import complete_json
from agent.state import AgentState


_SYSTEM = (
    "You are the reasoning core of an autonomous drone security analyst. You receive a "
    "structured description of the current frame, recent context, and any security rules "
    "that have already fired. Produce a concise, factual situational assessment for a "
    "human operator. Respond with JSON only."
)


def _build_user_prompt(vlm, telemetry, rolling_window, history, fired) -> str:
    recent = [
        f"- {e.get('time','?')} {e.get('object_type','?')} ({e.get('color','')}) "
        f"{e.get('action','')} @ {e.get('location','?')}"
        for e in rolling_window[-5:]
    ]
    fired_desc = [f"- {f['rule']} [{f['severity']}]: {f['message']}" for f in fired]
    return (
        f"CURRENT FRAME:\n{json.dumps(vlm, indent=2)}\n\n"
        f"TELEMETRY: time={telemetry.get('time')} location={telemetry.get('location')}\n\n"
        f"RECENT FRAMES (most recent last):\n" + ("\n".join(recent) or "  (none)") + "\n\n"
        f"DB HISTORY MATCHES: {len(history)} prior frame(s) retrieved\n\n"
        f"RULES ALREADY FIRED:\n" + ("\n".join(fired_desc) or "  (none)") + "\n\n"
        "Return JSON with keys:\n"
        '  "summary": one or two sentences describing what is happening and why it '
        "matters (or that it is routine).\n"
        '  "noteworthy": boolean — true if this frame is worth logging as an event even '
        "if no rule fired (e.g. a person or vehicle is present).\n"
    )


async def _llm_assessment(vlm, telemetry, rolling_window, history, fired) -> dict:
    prompt = _build_user_prompt(vlm, telemetry, rolling_window, history, fired)
    try:
        return await asyncio.to_thread(
            complete_json, system=_SYSTEM, text=prompt, temperature=0
        )
    except Exception:  # noqa: BLE001 — best-effort; deterministic fallback below
        return {}


async def node(state: AgentState) -> dict:
    vlm = state["current_frame"].get("vlm_json", {})
    telemetry = state.get("telemetry", {})
    rolling_window = state.get("rolling_window", [])
    history = state.get("history", [])

    fired = rules.evaluate(vlm, telemetry, rolling_window, state.get("events_today", []))

    assessment = await _llm_assessment(vlm, telemetry, rolling_window, history, fired)
    object_type = vlm.get("object_type", "none")
    has_subject = object_type not in ("none", "n/a", "")

    summary = assessment.get("summary") or (
        fired[0]["message"] if fired else vlm.get("description", "Routine frame.")
    )
    noteworthy = bool(assessment.get("noteworthy", has_subject))

    if fired:
        route = "alert"
        event_type = fired[0]["event_type"]
        severity = rules.top_severity(fired)
    elif noteworthy:
        route = "log"
        event_type = "person_detected" if rules.is_person(object_type) else (
            "vehicle_detected" if rules.is_vehicle(object_type) else "detection"
        )
        severity = "info"
    else:
        route = "normal"
        event_type = "none"
        severity = "info"

    return {
        "decision": {
            "route": route,
            "summary": summary,
            "event_type": event_type,
            "severity": severity,
            "fired_rules": fired,
        }
    }
