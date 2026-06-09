"""POST /chat — ReAct reasoning loop with a VLM tool for visual grounding.

Flow (up to MAX_STEPS iterations):
  1. Embed question → pgvector retrieval of top-k frame records.
  2. LLM (gpt-4o-mini) reasons over the JSON metadata.
     • If the text index has enough detail → returns final JSON answer.
     • If a frame needs visual inspection → calls analyze_frame_visual(blob_url).
  3. Tool result is fed back; LLM continues until it answers or the step limit is hit.
"""

from __future__ import annotations

import asyncio
import base64
import json

from fastapi import APIRouter
from pydantic import BaseModel, Field

from agent import db
from agent.embedder import embed_text
from agent.llm import complete_json, complete_with_tools
from data.blob_store import get_frame_bytes

router = APIRouter()

MAX_STEPS = 3  # max tool-call rounds before forcing a final answer

_SYSTEM = (
    "You are a drone security analyst assistant. Answer the operator's question using "
    "the retrieved frame records provided. Cite frames by their frame_id when relevant. "
    "If the JSON metadata lacks the visual detail you need, call analyze_frame_visual on "
    "the most relevant frame — but only when necessary. "
    "When you are ready to answer, respond with JSON only: "
    '{"answer": "<concise answer>", "frame_ids": ["<id>", ...]}'
)

_TOOL_ANALYZE_FRAME = {
    "type": "function",
    "function": {
        "name": "analyze_frame_visual",
        "description": (
            "Run a vision model over a specific surveillance frame to extract visual "
            "detail not present in the text index (e.g. clothing colour, licence plate, "
            "exact position). Use only when the retrieved JSON metadata is insufficient."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "blob_url": {
                    "type": "string",
                    "description": "blob_url of the frame to inspect visually.",
                },
                "frame_id": {
                    "type": "string",
                    "description": "frame_id for reference (optional).",
                },
            },
            "required": ["blob_url"],
        },
    },
}


class _Turn(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    top_k: int = Field(8, ge=1, le=20)
    history: list[_Turn] = Field(default_factory=list)


def _context_block(frames: list[dict]) -> str:
    lines = []
    for f in frames:
        lines.append(
            f"- frame_id={f['frame_id']} time={(f.get('telemetry') or {}).get('time', '?')} "
            f"location={f.get('location')} object={f.get('object_type')} "
            f"action={f.get('action')} color={f.get('color')} "
            f'desc="{f.get("raw_description", "")}"'
        )
    return "\n".join(lines) or "  (no matching frames)"


async def _vlm_for_question(blob_url: str, question: str) -> dict:
    """Call the vision model on a frame, focusing the prompt on the operator's question."""
    image_bytes = await asyncio.to_thread(get_frame_bytes, blob_url)
    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_uri = f"data:image/jpeg;base64,{b64}"

    system = (
        "You are a drone security camera vision analyst. "
        "Inspect this surveillance frame and answer the question below. "
        "Be factual and precise. Respond with JSON only."
    )
    prompt = (
        f"OPERATOR QUESTION: {question}\n\n"
        "Return JSON with keys:\n"
        '  "visual_findings": what you observe that is directly relevant to the question\n'
        '  "objects": list of notable objects or people visible\n'
        '  "description": one sentence summarising the scene\n'
    )
    # Vision runs on Groq (Llama-4 Scout); the QA reasoning loop runs on OpenAI mini.
    return await asyncio.to_thread(
        complete_json,
        system=system,
        text=prompt,
        image_data_uri=data_uri,
        temperature=0,
        provider="groq",
    )


def _parse_final(content: str) -> tuple[str, list[str]]:
    """Extract answer + frame_ids from the LLM's final JSON response."""
    try:
        s = (content or "").strip()
        if s.startswith("```"):
            s = s.strip("`")
            if s[:4].lower() == "json":
                s = s[4:]
            s = s.strip()
        i, j = s.find("{"), s.rfind("}")
        obj = json.loads(s[i : j + 1]) if i != -1 and j > i else {}
        answer = str(obj.get("answer", "")).strip() or s
        cited = [str(x) for x in obj.get("frame_ids", []) if x]
        return answer, cited
    except Exception:
        return (content or "").strip(), []


@router.post("/chat")
async def chat(req: ChatRequest) -> dict:
    # ── 1. Embed + retrieve ────────────────────────────────────────────────────
    embedding = await asyncio.to_thread(embed_text, req.question)
    frames = await db.query_similar_frames(embedding, limit=req.top_k)
    by_id = {f["frame_id"]: f for f in frames}

    # ── 2. Build initial messages ──────────────────────────────────────────────
    context_prompt = (
        f"QUESTION: {req.question}\n\n"
        f"RETRIEVED FRAMES (JSON index):\n{_context_block(frames)}\n\n"
        "Reason over these records. If the text metadata is sufficient, answer now. "
        "If you need to visually inspect a specific frame, call analyze_frame_visual."
    )
    history = [{"role": t.role, "content": t.content} for t in req.history]
    messages: list[dict] = [*history, {"role": "user", "content": context_prompt}]

    # ── 3. ReAct loop ──────────────────────────────────────────────────────────
    answer = ""
    cited: list[str] = []

    for step in range(MAX_STEPS + 1):
        force_final = step == MAX_STEPS

        if force_final:
            # No more tool calls allowed — ask for a plain answer.
            messages.append({
                "role": "user",
                "content": (
                    "You have reached the tool call limit. "
                    "Summarise what you know and return your final JSON answer now."
                ),
            })

        msg = await asyncio.to_thread(
            complete_with_tools,
            system=_SYSTEM,
            messages=messages,
            tools=[] if force_final else [_TOOL_ANALYZE_FRAME],
            provider="openai",
        )

        if msg.tool_calls and not force_final:
            # Append assistant turn with tool calls.
            messages.append({
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            })

            # Execute each tool call and append results.
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                    blob_url = args.get("blob_url", "")
                    vlm_result = await _vlm_for_question(blob_url, req.question)
                    tool_content = json.dumps(vlm_result)
                except Exception as exc:  # noqa: BLE001
                    tool_content = json.dumps({"error": str(exc)})

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_content,
                })
        else:
            # No tool calls → this is the final answer.
            answer, cited = _parse_final(msg.content or "")
            break

    if not answer:
        answer = "Unable to generate an answer."

    # ── 4. Build reference list ────────────────────────────────────────────────
    chosen = [by_id[fid] for fid in cited if fid in by_id] or frames
    references = [
        {
            "frame_id": f["frame_id"],
            "blob_url": f["blob_url"],
            "timestamp": f["timestamp"],
            "object_type": f["object_type"],
            "location": f["location"],
            "similarity": round(float(f["similarity"]), 4) if f.get("similarity") is not None else None,
        }
        for f in chosen
    ]
    return {"question": req.question, "answer": answer, "references": references}
