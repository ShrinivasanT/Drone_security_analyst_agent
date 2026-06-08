# Drone Security Analyst Agent — Revised Implementation Plan (Ordered Build Sequence)

This reorders [02_architecture_and_implementation_plan.md](02_architecture_and_implementation_plan.md) into a single
linear build sequence for an **empty repo**. The architecture, schema, and node design are unchanged — only the
*order* and *grouping* of work is revised, to fix two dependency problems in the original phase plan and to make
every stage independently runnable/verifiable before moving on.

## What changed vs. the original phase plan, and why

1. **FastAPI skeleton + DB helpers moved from Phase 4 → right after the data layer (new Stage 3).**
   The original Phase 1 deliverable `data/ingest_runner.py` calls `POST /ingest` — but that endpoint isn't built
   until Phase 4, three phases later. As written, `ingest_runner.py` would be unrunnable dead code for most of the
   build. Standing up `backend/main.py` + `agent/db.py` early (with a *stub* `/ingest` that just inserts a row) gives
   every later stage a real, live API to plug into and test against incrementally.

2. **`data/ingest_runner.py` moved from Phase 1 → after the agent loop exists (new Stage 6).**
   It's the orchestration script that drives the *whole* pipeline end-to-end — it can't be meaningfully tested until
   `/ingest` does real work (VLM analysis → reasoning → DB writes). Writing it last (rather than first) means it's
   verified once, against a complete system, instead of being written early and re-validated three times as the
   stub it calls gets replaced.

3. **Added an explicit Stage 0 (scaffolding, env config, git/GitHub).**
   The original plan has no task for repo init, `requirements.txt`/`.env.example`, or creating the private GitHub
   repo + adding `assignments@flytbase.com` as a collaborator — all hard prerequisites, and the last one is an easy
   thing to forget under deadline pressure at the end.

4. **`/ingest` is split into "stub" (Stage 3) and "real" (Stage 5)** rather than appearing once in Phase 4. This is
   what makes incremental verification possible — each stage builds on a running system rather than isolated files
   that only connect at the very end.

Everything else (schema, node responsibilities, alert rules, frontend panels, QA scenarios, docs) is preserved as-is
from the original plan — see it for full task detail. This document is the *order*, not a replacement of the *what*.

---

## Stage 0 — Project scaffolding

**Goal:** An empty-but-runnable repo skeleton with environment and source control in place.

- `git init`, create the private GitHub repo, add `assignments@flytbase.com` as a collaborator (do this early — it's
  a submission requirement and trivial to forget later)
- `requirements.txt` (or `pyproject.toml`), `.env.example`, `.gitignore`
- `docker-compose.yml` skeleton — `postgres`, `minio`, `minio_init` services only (backend/frontend services are
  added once their Dockerfiles exist, in Stages 3 and 8)

**Verify:** `git remote -v` shows the GitHub repo; `docker compose config` parses without error.

---

## Stage 1 — Data plane: PostgreSQL + MinIO

**Goal:** Storage layer running and reachable.

- `db/init.sql` — `frames`, `events`, `alerts` tables, pgvector extension, indexes (per [02_architecture_and_implementation_plan.md:189-236](02_architecture_and_implementation_plan.md))

**Verify:** `docker compose up postgres minio minio_init` → connect with `psql`, confirm the three tables and the
`vector` extension exist → open the MinIO console at `localhost:9001`, confirm the `drone-frames` bucket was created
and is set to public-download.

---

## Stage 2 — Blob client + dataset loader

**Goal:** Can pull a real dataset image and push it to MinIO, getting back a working URL.

- `data/blob_store.py` — `upload_frame(image_bytes, filename) → blob_url`, `get_frame_bytes(blob_url) → bytes`
- `data/dataset_loader.py` — HuggingFace `datasets` (and/or Kaggle CLI) iterator yielding
  `(image_bytes, synthetic_telemetry)` tuples

**Verify:** Upload one test image via `blob_store.upload_frame`, open the returned `blob_url` directly in a browser
and confirm the image renders; iterate `dataset_loader` for ~5 frames and print the synthetic telemetry for each.

---

## Stage 3 — Backend skeleton + DB helpers *(moved up from original Phase 4)*

**Goal:** A running FastAPI service with a real database connection and a *stub* `/ingest` — the seam every later
stage plugs into.

- `agent/db.py` — async SQLAlchemy helpers: `insert_frame()`, `insert_event()`, `insert_alert()`, `query_similar_frames()`
- `backend/main.py` — FastAPI app, CORS, lifespan (DB pool + MinIO client init)
- `POST /ingest` **stub**: validates `{ blob_url, telemetry }`, writes a placeholder row straight to `frames`
  (no VLM, no agent yet — just proves the wire is connected)
- Add `backend` service to `docker-compose.yml`

**Verify:** `docker compose up` the full stack so far; `curl -X POST localhost:8000/ingest` with a fake
`blob_url`/`telemetry` payload; confirm a row lands in `frames`.

*Why here:* this is the dependency the original Phase 1's `ingest_runner.py` silently assumed existed. Building it
now — even as a stub — means every subsequent stage has a live endpoint to integrate against and test incrementally,
instead of everything only coming together at the very end.

---

## Stage 4 — VLM integration

**Goal:** Real image in MinIO → structured JSON description → embedding vector.

- `agent/embedder.py` — wraps `text-embedding-3-small`, returns a 1536-dim vector
- `agent/nodes/analyze_frame.py` — fetches image bytes via `blob_store.get_frame_bytes()`, base64-encodes, calls the
  VLM (GPT-4o / Claude vision) with a structured-extraction prompt, parses/validates the JSON response
- `tests/test_analyze_frame.py`

**Verify:** Run against 5 real images pulled straight from the MinIO bucket; assert each returns valid structured
JSON (`object_type`, `location`, `action`, `clothing`, `color`, `confidence`) and a valid embedding vector.

---

## Stage 5 — LangGraph agent core loop (wires into the real `/ingest`)

**Goal:** The full reasoning cycle runs end-to-end on one real frame, replacing the Stage 3 stub.

- `agent/state.py` — `AgentState` TypedDict
- Remaining nodes: `ingest_frame`, `query_history`, `reason_decide`, `log_event`, `trigger_alert`, `update_state`
- `agent/graph.py` — wire the graph with conditional edges (log vs. alert vs. both)
- Replace the Stage 3 stub: `POST /ingest` now runs the full LangGraph agent and returns its result
- `tests/test_agent_pipeline.py`

**Verify:** `POST /ingest` with a real `blob_url` + telemetry → full cycle runs (analyze → query history → reason →
log/alert → persist) → `frames`/`events`/`alerts` rows appear with valid `blob_url` and `embedding`. Run the graph
directly on 10 real dataset images and assert correct DB writes.

---

## Stage 6 — Ingest runner *(moved down from original Phase 1)*

**Goal:** End-to-end automation — dataset → MinIO → live agent — driven by one script.

- `data/ingest_runner.py` — loader → `blob_store.upload_frame` → `POST /ingest`, configurable frame count/interval/dataset

**Verify:** Run it for 20+ frames against the now-live backend; confirm events accumulate, and that at least one
after-hours or loitering alert fires from the synthetic telemetry timestamps (this is the first point at which this
script *can* be meaningfully tested, since it depends on the full agent loop existing).

---

## Stage 7 — Remaining REST endpoints

**Goal:** Full operator-facing API surface.

- Routes: `GET /events`, `GET /alerts`, `GET /frames/search`, `GET /summary`, `POST /chat`
  (`/ingest` already shipped in Stage 5)
- `tests/test_api.py` — assert `blob_url` present in search results

**Verify:** `curl` each endpoint against data produced by the Stage 6 run; confirm `blob_url` fields are present and
resolve to real images.

---

## Stage 8 — React dashboard

**Goal:** Visual operator UI rendering live data and real frame thumbnails.

- Scaffold React + Tailwind, add `frontend` service to `docker-compose.yml`
- `TelemetryFeed.jsx`, `EventLog.jsx`, `AlertBanner.jsx`, `FrameSearch.jsx`, `ChatBox.jsx`, `SessionSummary.jsx`
  (panel-to-endpoint mapping per [02_architecture_and_implementation_plan.md:505-512](02_architecture_and_implementation_plan.md))

**Verify:** `docker compose up` the entire stack; manually exercise each panel in the browser — search renders
thumbnails from `blob_url`, alert banner shows the triggering frame, etc.

---

## Stage 9 — QA, documentation, demo, submission

**Goal:** Everything the assignment requires for grading is produced and the repo is submission-ready.

- Run QA-01 through QA-09 (scenario table per [02_architecture_and_implementation_plan.md:539-549](02_architecture_and_implementation_plan.md)), record actual vs. expected
- `README.md`, `docs/architecture.md`, `docs/datasets.md`, `docs/test_cases.md`
- Record the demo video(s) with voiceover (per-goal, as required by the assignment brief)
- Write the PDF report (assumptions, tool justifications, results, "what I'd improve with more time")
- Final push to GitHub; confirm `assignments@flytbase.com` still has collaborator access (set up in Stage 0)

---

## Stage Summary

| Stage | Focus | Depends on | Key verification |
|---|---|---|---|
| 0 | Scaffolding, git/GitHub, env | — | repo + compose config valid |
| 1 | Postgres + MinIO running | 0 | tables exist, bucket created |
| 2 | Blob client + dataset loader | 1 | uploaded test image renders via URL |
| 3 | Backend skeleton + stub `/ingest` | 1, 2 | curl POST → row in `frames` |
| 4 | VLM integration | 2, 3 | 5 real images → valid structured JSON + embeddings |
| 5 | LangGraph agent (real `/ingest`) | 3, 4 | full cycle on real frame writes events/alerts |
| 6 | Ingest runner | 5 | 20+ frame run produces events + at least one alert |
| 7 | Remaining REST endpoints | 5, 6 | each endpoint returns data incl. `blob_url` |
| 8 | React dashboard | 7 | full stack runs, panels render real thumbnails |
| 9 | QA, docs, demo, submission | 8 | QA table filled, docs/video/report done, repo shared |
