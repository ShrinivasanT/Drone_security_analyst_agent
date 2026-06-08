"""POST /chat — natural-language Q&A grounded in the frame index (RAG over pgvector)."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter
from pydantic import BaseModel, Field

from agent import db
from agent.embedder import embed_text
from agent.llm import complete_json

router = APIRouter()

_SYSTEM = (
    "You are a drone security analyst assistant. Answer the operator's question using ONLY "
    "the retrieved frame records provided as context. Cite frames by their frame_id when "
    "relevant. If the context does not contain the answer, say so plainly. JSON only."
)


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    top_k: int = Field(8, ge=1, le=20)


def _context_block(frames: list[dict]) -> str:
    lines = []
    for f in frames:
        lines.append(
            f"- frame_id={f['frame_id']} time={(f.get('telemetry') or {}).get('time', '?')} "
            f"location={f.get('location')} object={f.get('object_type')} "
            f"action={f.get('action')} color={f.get('color')} "
            f"desc=\"{f.get('raw_description', '')}\""
        )
    return "\n".join(lines) or "  (no matching frames)"


@router.post("/chat")
async def chat(req: ChatRequest) -> dict:
    embedding = await asyncio.to_thread(embed_text, req.question)
    frames = await db.query_similar_frames(embedding, limit=req.top_k)

    prompt = (
        f"QUESTION: {req.question}\n\n"
        f"RETRIEVED FRAMES:\n{_context_block(frames)}\n\n"
        'Return JSON with keys:\n'
        '  "answer": a concise, grounded answer to the question.\n'
        '  "frame_ids": a list of frame_id strings you actually used (may be empty).\n'
    )

    answer = ""
    cited: list[str] = []
    try:
        result = await asyncio.to_thread(complete_json, system=_SYSTEM, text=prompt)
        answer = str(result.get("answer", "")).strip()
        cited = [str(x) for x in result.get("frame_ids", []) if x]
    except Exception as exc:  # noqa: BLE001
        answer = f"Unable to generate an answer ({exc})."

    # References: prefer LLM-cited frames, else fall back to all retrieved (with blob_urls).
    by_id = {f["frame_id"]: f for f in frames}
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
