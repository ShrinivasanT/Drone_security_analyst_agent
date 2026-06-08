"""AgentState schema + cross-frame session store.

LangGraph state is per-invocation. The drone agent, however, needs memory that spans
frames — the rolling window of recent descriptions, the day's events, and unresolved
alerts. ``SessionStore`` is a process-singleton holding that durable state; the graph
seeds AgentState from it in ``ingest_frame`` and writes back in ``update_state``.
Durable history (for loitering/repeat detection) also lives in PostgreSQL and is read
back via ``query_history``.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, TypedDict

ROLLING_WINDOW_SIZE = int(os.environ.get("ROLLING_WINDOW_SIZE", "10"))


class AgentState(TypedDict, total=False):
    # Inputs / carried context
    current_frame: dict          # { blob_url, telemetry, vlm_json, embedding }
    telemetry: dict              # { time, location, lat, lng, altitude }
    rolling_window: list[dict]   # last N frame summaries (pre-current)
    events_today: list[dict]     # events logged this session
    active_alerts: list[dict]    # unresolved alerts this session

    # Working fields produced as the graph runs
    history: list[dict]          # query_history results (DB rows incl. blob_url)
    decision: dict               # reason_decide output (route, summary, fired rules)
    result: dict                 # final payload returned by POST /ingest


class SessionStore:
    """In-process memory shared across ``/ingest`` calls for one running backend."""

    def __init__(self, window_size: int = ROLLING_WINDOW_SIZE) -> None:
        self.window_size = window_size
        self.rolling_window: list[dict] = []
        self.events_today: list[dict] = []
        self.active_alerts: list[dict] = []

    def push_frame(self, summary: dict) -> None:
        self.rolling_window.append(summary)
        if len(self.rolling_window) > self.window_size:
            self.rolling_window = self.rolling_window[-self.window_size :]

    def reset(self) -> None:
        self.rolling_window.clear()
        self.events_today.clear()
        self.active_alerts.clear()


_session = SessionStore()


def get_session() -> SessionStore:
    return _session


def reset_session() -> None:
    _session.reset()


def frame_timestamp(telemetry: dict[str, Any]) -> datetime:
    """Map telemetry ``"HH:MM"`` onto today's UTC date; fall back to now()."""
    now = datetime.now(timezone.utc)
    raw = telemetry.get("time") if telemetry else None
    if raw:
        try:
            hh, mm = (int(p) for p in str(raw).split(":"))
            return now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        except (ValueError, TypeError):
            pass
    return now
