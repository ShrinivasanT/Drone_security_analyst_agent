"""analyze_frame node — real image (MinIO) → structured JSON description.

Fetches the frame bytes for a ``blob_url`` from MinIO, base64-encodes them, and asks a
vision model (Groq Llama-4 / GPT-4o depending on configured provider) to extract a fixed
schema describing the most salient subject in the scene. The parsed/validated dict is
what the rest of the agent reasons over and what feeds the embedder.

Returned keys (always present, never None):
    object_type, location, action, clothing, color, confidence, description
"""

from __future__ import annotations

import base64
import json

from dotenv import load_dotenv

from agent.llm import complete_json
from data.blob_store import get_frame_bytes

load_dotenv()

# Fields the downstream agent and DB schema rely on.
_REQUIRED_FIELDS = ("object_type", "location", "action", "clothing", "color", "confidence")

_SYSTEM_PROMPT = (
    "You are a drone-mounted security camera vision system. You are given a single "
    "still frame from an aerial/CCTV patrol feed. Identify the single most security-"
    "relevant subject in the frame (a person or vehicle if present; otherwise the most "
    "salient object) and describe it concisely and factually. Do not speculate beyond "
    "what is visible. Respond with JSON only."
)

_USER_PROMPT = (
    "Analyze this surveillance frame and return a JSON object with exactly these keys:\n"
    '  "object_type": short noun for the main subject (e.g. "person", "car", "truck", '
    '"bicycle", "none" if the scene is empty of notable subjects)\n'
    '  "location": where in the scene the subject is / scene context '
    '(e.g. "parking lot", "near building entrance", "open road")\n'
    '  "action": what the subject is doing (e.g. "walking", "parked", "loading", '
    '"standing still"; "none" if not applicable)\n'
    '  "clothing": clothing description for a person, else "n/a"\n'
    '  "color": dominant color of the subject (e.g. "white", "dark blue"; "n/a" if unclear)\n'
    '  "confidence": your confidence in this analysis as a number between 0 and 1\n'
    '  "description": one natural-language sentence summarizing the scene\n'
    "Return only the JSON object, no markdown, no commentary."
)


def _coerce(raw: dict) -> dict:
    """Validate required keys exist; coerce types; fill optional description."""
    missing = [k for k in _REQUIRED_FIELDS if k not in raw]
    if missing:
        raise ValueError(f"VLM response missing required keys: {missing}; got {raw}")

    try:
        confidence = float(raw["confidence"])
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    def _s(key: str, default: str = "n/a") -> str:
        val = raw.get(key)
        return str(val).strip() if val not in (None, "") else default

    object_type = _s("object_type", "none")
    out = {
        "object_type": object_type,
        "location": _s("location", "unknown"),
        "action": _s("action", "none"),
        "clothing": _s("clothing"),
        "color": _s("color"),
        "confidence": confidence,
    }
    description = raw.get("description")
    if description in (None, ""):
        description = (
            f"{out['color']} {object_type} {out['action']} at {out['location']}".strip()
        )
    out["description"] = str(description).strip()
    return out


def analyze_frame(blob_url: str) -> dict:
    """Fetch the frame at ``blob_url`` and return its structured VLM analysis."""
    image_bytes = get_frame_bytes(blob_url)
    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_uri = f"data:image/jpeg;base64,{b64}"

    parsed = complete_json(
        system=_SYSTEM_PROMPT,
        text=_USER_PROMPT,
        image_data_uri=data_uri,
        temperature=0,
    )
    return _coerce(parsed)


async def node(state: dict) -> dict:
    """LangGraph node: run VLM analysis on the current frame's blob_url."""
    import asyncio

    current = state["current_frame"]
    vlm = await asyncio.to_thread(analyze_frame, current["blob_url"])
    return {"current_frame": {**current, "vlm_json": vlm}}


if __name__ == "__main__":
    import sys

    url = sys.argv[1] if len(sys.argv) > 1 else None
    if not url:
        print("usage: python -m agent.nodes.analyze_frame <blob_url>")
        raise SystemExit(2)
    print(json.dumps(analyze_frame(url), indent=2))
