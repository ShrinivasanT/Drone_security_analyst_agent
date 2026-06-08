"""reason_video — clip-level action judge (the video-level analog of reason_decide).

Where ``analyze_frame`` describes a *single* still, this judges the *action/behavior
unfolding across an entire clip*. It receives the time-ordered per-frame analyses plus a
few representative stills and asks a vision model for one verdict for the whole video:
whether the activity warrants a security alert, at what severity, with a human narrative.

If the LLM call fails it degrades to a deterministic, no-alert summary built from the most
common object/action across the clip — mirroring reason_decide's best-effort fallback so
ingestion never breaks.

Returned keys (always present):
    action_summary, alert, severity, event_type, narrative, key_frame_index
"""

from __future__ import annotations

import asyncio
from collections import Counter

from agent.llm import complete_json

_VALID_SEVERITY = ("info", "warning", "high", "critical")

_SYSTEM = (
    "You are the reasoning core of an autonomous drone security analyst. You are given a "
    "time-ordered summary of EVERY frame sampled from a single video clip, plus a few "
    "representative still images from that clip. Judge the action or behavior unfolding "
    "ACROSS the whole clip — a sequence over time, not any single frame. Decide whether "
    "that activity warrants a security alert. Be factual and do not speculate beyond what "
    "the frames support. Respond with JSON only."
)


def build_timeline(frames: list[dict]) -> str:
    """Render the per-frame analyses as a numbered, time-ordered timeline."""
    lines = []
    for i, f in enumerate(frames):
        lines.append(
            f"#{i:02d} t={f.get('time', '?')} loc={f.get('location', '?')} "
            f"obj={f.get('object_type', 'none')} action={f.get('action', 'none')} "
            f"color={f.get('color', 'n/a')} :: {f.get('description', '')}"
        )
    return "\n".join(lines) or "(no frames)"


def _user_prompt(frames: list[dict]) -> str:
    return (
        f"CLIP FRAME TIMELINE ({len(frames)} frames, earliest first):\n"
        f"{build_timeline(frames)}\n\n"
        f"The attached images are representative frames from this clip.\n\n"
        "Return a JSON object with exactly these keys:\n"
        '  "action_summary": one short phrase naming the main action/behavior across the '
        'clip (e.g. "person loitering near the loading dock", "vehicle entering after hours", '
        '"routine empty perimeter").\n'
        '  "alert": boolean — true if this activity warrants a security alert.\n'
        '  "severity": one of "info", "warning", "high", "critical" (use "info" when alert '
        "is false).\n"
        '  "event_type": short snake_case label for the activity '
        '(e.g. "loitering", "after_hours_intrusion", "vehicle_movement", "routine").\n'
        '  "narrative": one to three sentences describing what happens across the clip and '
        "why it does or does not matter to an operator.\n"
        '  "key_frame_index": integer index (from the timeline above) of the single most '
        "relevant frame an operator should look at first.\n"
        "Return only the JSON object, no markdown, no commentary."
    )


def _fallback(frames: list[dict]) -> dict:
    """Deterministic no-alert verdict when the LLM is unavailable."""
    objects = [
        f.get("object_type", "none")
        for f in frames
        if f.get("object_type") not in (None, "", "none", "n/a")
    ]
    actions = [f.get("action") for f in frames if f.get("action") not in (None, "", "none")]
    top_obj = Counter(objects).most_common(1)[0][0] if objects else "no notable subjects"
    top_act = Counter(actions).most_common(1)[0][0] if actions else "no notable activity"
    return {
        "action_summary": f"{top_obj} — {top_act}",
        "alert": False,
        "severity": "info",
        "event_type": "routine",
        "narrative": (
            f"Automated fallback: across {len(frames)} sampled frames the most common "
            f"subject was '{top_obj}' and activity '{top_act}'. No clip-level reasoning "
            "model was available to assess this further."
        ),
        "key_frame_index": 0,
    }


def _coerce(raw: dict, frames: list[dict]) -> dict:
    """Validate/normalize the model's verdict; never raise."""
    if not isinstance(raw, dict) or not raw:
        return _fallback(frames)

    alert = bool(raw.get("alert", False))
    severity = str(raw.get("severity", "info")).strip().lower()
    if severity not in _VALID_SEVERITY:
        severity = "high" if alert else "info"
    if not alert:
        severity = "info"

    try:
        key_idx = int(raw.get("key_frame_index", 0))
    except (TypeError, ValueError):
        key_idx = 0
    key_idx = max(0, min(key_idx, max(0, len(frames) - 1)))

    action_summary = str(raw.get("action_summary") or "").strip() or _fallback(frames)["action_summary"]
    narrative = str(raw.get("narrative") or "").strip() or action_summary
    event_type = str(raw.get("event_type") or ("detection" if alert else "routine")).strip()

    return {
        "action_summary": action_summary,
        "alert": alert,
        "severity": severity,
        "event_type": event_type,
        "narrative": narrative,
        "key_frame_index": key_idx,
    }


async def judge_clip(frames: list[dict], rep_image_uris: list[str]) -> dict:
    """Judge the action across ``frames`` (with representative images); return a verdict dict."""
    if not frames:
        return _fallback(frames)
    try:
        raw = await asyncio.to_thread(
            complete_json,
            system=_SYSTEM,
            text=_user_prompt(frames),
            image_data_uris=rep_image_uris,
            temperature=0,
        )
    except Exception:  # noqa: BLE001 — best-effort; deterministic fallback below
        return _fallback(frames)
    return _coerce(raw, frames)
