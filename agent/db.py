"""Async PostgreSQL helpers (SQLAlchemy + asyncpg).

Raw parameterised ``text()`` SQL is used throughout rather than the ORM so that the
pgvector columns can be handled with explicit ``::vector`` casts — this sidesteps the
need to register an asyncpg vector codec on every connection, and keeps the embedding
wire-format (the pgvector literal string ``[1,2,3]``) under our direct control.

Public surface (per Implementation.md Stage 3):
  * init_db() / close_db()      — lifespan hooks
  * insert_frame(...)           — INSERT INTO frames (metadata + blob_url + embedding)
  * insert_event(...)           — INSERT INTO events
  * insert_alert(...)           — INSERT INTO alerts
  * query_similar_frames(...)   — pgvector cosine similarity search
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Sequence

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

load_dotenv()

_engine: AsyncEngine | None = None


def _vector_literal(embedding: Sequence[float] | None) -> str | None:
    """Convert a float sequence to the pgvector text literal ``[1,2,3]``."""
    if embedding is None:
        return None
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"


def init_db(database_url: str | None = None) -> AsyncEngine:
    """Create (once) and return the shared async engine. Call from app lifespan."""
    global _engine
    if _engine is None:
        url = database_url or os.environ["DATABASE_URL"]
        _engine = create_async_engine(url, pool_pre_ping=True, future=True)
    return _engine


def get_engine() -> AsyncEngine:
    if _engine is None:
        return init_db()
    return _engine


async def close_db() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


async def ping() -> bool:
    """Lightweight connectivity check used by the lifespan startup."""
    engine = get_engine()
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return True


# --------------------------------------------------------------------------- #
# Writes
# --------------------------------------------------------------------------- #

_INSERT_FRAME = text(
    """
    INSERT INTO frames (
        frame_id, timestamp, blob_url, location, object_type, action,
        clothing, color, raw_description, embedding, telemetry
    ) VALUES (
        :frame_id, :timestamp, :blob_url, :location, :object_type, :action,
        :clothing, :color, :raw_description, CAST(:embedding AS vector),
        CAST(:telemetry AS jsonb)
    )
    RETURNING id, frame_id
    """
)


async def insert_frame(
    *,
    frame_id: str,
    timestamp: datetime | None = None,
    blob_url: str,
    raw_description: str,
    location: str | None = None,
    object_type: str | None = None,
    action: str | None = None,
    clothing: str | None = None,
    color: str | None = None,
    embedding: Sequence[float] | None = None,
    telemetry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist a frame row; returns ``{id, frame_id}``."""
    engine = get_engine()
    params = {
        "frame_id": frame_id,
        "timestamp": timestamp or datetime.now(timezone.utc),
        "blob_url": blob_url,
        "location": location,
        "object_type": object_type,
        "action": action,
        "clothing": clothing,
        "color": color,
        "raw_description": raw_description,
        "embedding": _vector_literal(embedding),
        "telemetry": json.dumps(telemetry) if telemetry is not None else None,
    }
    async with engine.begin() as conn:
        row = (await conn.execute(_INSERT_FRAME, params)).mappings().one()
    return dict(row)


_INSERT_EVENT = text(
    """
    INSERT INTO events (event_type, description, severity, frame_id, blob_url)
    VALUES (:event_type, :description, :severity, :frame_id, :blob_url)
    RETURNING id
    """
)


async def insert_event(
    *,
    event_type: str,
    description: str,
    severity: str = "info",
    frame_id: str | None = None,
    blob_url: str | None = None,
) -> dict[str, Any]:
    engine = get_engine()
    params = {
        "event_type": event_type,
        "description": description,
        "severity": severity,
        "frame_id": frame_id,
        "blob_url": blob_url,
    }
    async with engine.begin() as conn:
        row = (await conn.execute(_INSERT_EVENT, params)).mappings().one()
    return dict(row)


_INSERT_ALERT = text(
    """
    INSERT INTO alerts (rule, message, severity, blob_url, metadata)
    VALUES (:rule, :message, :severity, :blob_url, CAST(:metadata AS jsonb))
    RETURNING id
    """
)


async def insert_alert(
    *,
    rule: str,
    message: str,
    severity: str,
    blob_url: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    engine = get_engine()
    params = {
        "rule": rule,
        "message": message,
        "severity": severity,
        "blob_url": blob_url,
        "metadata": json.dumps(metadata) if metadata is not None else None,
    }
    async with engine.begin() as conn:
        row = (await conn.execute(_INSERT_ALERT, params)).mappings().one()
    return dict(row)


# --------------------------------------------------------------------------- #
# Reads
# --------------------------------------------------------------------------- #

_QUERY_SIMILAR = text(
    """
    SELECT
        frame_id,
        timestamp,
        blob_url,
        location,
        object_type,
        action,
        clothing,
        color,
        raw_description,
        telemetry,
        1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
    FROM frames
    WHERE embedding IS NOT NULL
    ORDER BY embedding <=> CAST(:embedding AS vector)
    LIMIT :limit
    """
)


async def query_similar_frames(
    embedding: Sequence[float], limit: int = 10
) -> list[dict[str, Any]]:
    """Return the ``limit`` frames most similar to ``embedding`` (cosine), with score."""
    engine = get_engine()
    params = {"embedding": _vector_literal(embedding), "limit": limit}
    async with engine.connect() as conn:
        rows = (await conn.execute(_QUERY_SIMILAR, params)).mappings().all()
    return [dict(r) for r in rows]


_QUERY_RECENT_LOCATION = text(
    """
    SELECT frame_id, timestamp, blob_url, location, object_type, action,
           clothing, color, raw_description
    FROM frames
    WHERE location = :location
      AND timestamp >= NOW() - make_interval(mins => :within_minutes)
    ORDER BY timestamp DESC
    LIMIT :limit
    """
)


async def query_recent_by_location(
    location: str, within_minutes: int = 60, limit: int = 10
) -> list[dict[str, Any]]:
    """Recent frames at the same ``location`` within a time window (newest first)."""
    if not location:
        return []
    engine = get_engine()
    params = {"location": location, "within_minutes": within_minutes, "limit": limit}
    async with engine.connect() as conn:
        rows = (await conn.execute(_QUERY_RECENT_LOCATION, params)).mappings().all()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------- #
# Operator-facing reads (Stage 7 REST endpoints)
# --------------------------------------------------------------------------- #

_FETCH_EVENTS = text(
    """
    SELECT id, event_type, description, severity, frame_id, blob_url, created_at
    FROM events
    ORDER BY id DESC
    LIMIT :limit OFFSET :offset
    """
)


async def fetch_events(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    """Most recent events first (each includes its frame ``blob_url``)."""
    engine = get_engine()
    async with engine.connect() as conn:
        rows = (
            await conn.execute(_FETCH_EVENTS, {"limit": limit, "offset": offset})
        ).mappings().all()
    return [dict(r) for r in rows]


_FETCH_FRAMES = text(
    """
    SELECT id, frame_id, timestamp, blob_url, location, object_type,
           action, color, raw_description, telemetry
    FROM frames
    ORDER BY id DESC
    LIMIT :limit OFFSET :offset
    """
)


async def fetch_recent_frames(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    """Most recently ingested frames first — every frame, regardless of event/alert route."""
    engine = get_engine()
    async with engine.connect() as conn:
        rows = (
            await conn.execute(_FETCH_FRAMES, {"limit": limit, "offset": offset})
        ).mappings().all()
    return [dict(r) for r in rows]


_FETCH_ALERTS = text(
    """
    SELECT id, rule, message, severity, blob_url, triggered_at, resolved_at, metadata
    FROM alerts
    WHERE (:active_only = false) OR (resolved_at IS NULL)
    ORDER BY id DESC
    LIMIT :limit OFFSET :offset
    """
)


async def fetch_alerts(
    limit: int = 50, offset: int = 0, active_only: bool = False
) -> list[dict[str, Any]]:
    """Alerts newest first; ``active_only`` restricts to unresolved (``resolved_at IS NULL``)."""
    engine = get_engine()
    params = {"limit": limit, "offset": offset, "active_only": active_only}
    async with engine.connect() as conn:
        rows = (await conn.execute(_FETCH_ALERTS, params)).mappings().all()
    return [dict(r) for r in rows]


async def fetch_summary_stats() -> dict[str, Any]:
    """Aggregate counts + breakdowns for the session summary endpoint."""
    engine = get_engine()
    async with engine.connect() as conn:
        frames = (await conn.execute(text("SELECT COUNT(*) FROM frames"))).scalar_one()
        events = (await conn.execute(text("SELECT COUNT(*) FROM events"))).scalar_one()
        alerts = (await conn.execute(text("SELECT COUNT(*) FROM alerts"))).scalar_one()
        by_rule = (
            await conn.execute(
                text("SELECT rule, COUNT(*) AS n FROM alerts GROUP BY rule ORDER BY n DESC")
            )
        ).mappings().all()
        by_object = (
            await conn.execute(
                text(
                    "SELECT object_type, COUNT(*) AS n FROM frames "
                    "WHERE object_type IS NOT NULL GROUP BY object_type ORDER BY n DESC LIMIT 10"
                )
            )
        ).mappings().all()
        time_span = (
            await conn.execute(
                text("SELECT MIN(timestamp) AS first, MAX(timestamp) AS last FROM frames")
            )
        ).mappings().one()
    return {
        "frames": frames,
        "events": events,
        "alerts": alerts,
        "alerts_by_rule": {r["rule"]: r["n"] for r in by_rule},
        "objects": {r["object_type"]: r["n"] for r in by_object},
        "first_frame": time_span["first"],
        "last_frame": time_span["last"],
    }
