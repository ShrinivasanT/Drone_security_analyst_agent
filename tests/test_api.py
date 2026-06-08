"""Stage 7 verification: exercise each REST endpoint against the live backend.

Asserts the operator-facing surface works and — the key Stage 7 requirement — that
``blob_url`` is present in frame-search results (and resolves to a real image).

Runs against BACKEND_URL (default http://localhost:8000). Skips automatically if the
backend isn't reachable.
"""

from __future__ import annotations

import os

import httpx
import pytest
from dotenv import load_dotenv

load_dotenv()

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")


@pytest.fixture(scope="module")
def client():
    c = httpx.Client(base_url=BACKEND_URL, timeout=60.0)
    try:
        r = c.get("/health")
        r.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"backend not reachable at {BACKEND_URL}: {exc}")
    yield c
    c.close()


def test_events(client: httpx.Client) -> None:
    r = client.get("/events", params={"limit": 5})
    assert r.status_code == 200
    body = r.json()
    assert "events" in body and isinstance(body["events"], list)
    for ev in body["events"]:
        assert "blob_url" in ev
        assert {"event_type", "severity", "description"} <= ev.keys()


def test_alerts(client: httpx.Client) -> None:
    r = client.get("/alerts", params={"limit": 5})
    assert r.status_code == 200
    body = r.json()
    assert "alerts" in body and isinstance(body["alerts"], list)
    for al in body["alerts"]:
        assert "blob_url" in al
        assert {"rule", "message", "severity"} <= al.keys()


def test_frames_search_has_blob_url(client: httpx.Client) -> None:
    r = client.get("/frames/search", params={"q": "person walking", "limit": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["results"], "expected at least one search result from seeded data"
    for res in body["results"]:
        assert res["blob_url"].startswith("http"), "blob_url must be present in search results"
        assert "similarity" in res

    # blob_url must resolve to a real image
    first = body["results"][0]["blob_url"]
    img = httpx.get(first, timeout=30.0)
    assert img.status_code == 200
    assert img.headers.get("content-type", "").startswith("image/")


def test_summary(client: httpx.Client) -> None:
    r = client.get("/summary")
    assert r.status_code == 200
    body = r.json()
    assert "stats" in body and "summary" in body
    assert body["stats"]["frames"] >= 0


def test_chat_returns_grounded_references(client: httpx.Client) -> None:
    r = client.post("/chat", json={"question": "Were there any people after hours?"})
    assert r.status_code == 200
    body = r.json()
    assert "answer" in body and isinstance(body["answer"], str)
    assert "references" in body and isinstance(body["references"], list)
    for ref in body["references"]:
        assert ref["blob_url"].startswith("http")
