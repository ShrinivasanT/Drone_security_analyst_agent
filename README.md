# 🛰️ Drone Security Analyst Agent

An autonomous security-analyst agent that ingests a simulated drone surveillance feed,
understands each frame with a vision-language model, reasons over rolling context with a
deterministic rule engine + LLM, raises alerts, and exposes everything through a live
operator dashboard.

The system does not consume a real drone feed — it **samples frames from pre-recorded
CCTV footage** and pairs each with **synthetic telemetry** (time-of-day, patrol waypoint,
GPS, altitude) to simulate one. Everything downstream is source-agnostic.

---

## What it does

- **Per-frame understanding** — fetches each frame from blob storage and runs a VLM
  (Groq Llama-4 Scout) to extract a structured description: object type, action, clothing,
  colour, scene context, confidence.
- **Contextual reasoning** — a LangGraph agent combines the current frame with a rolling
  window of recent frames, semantic history (pgvector), and a deterministic alert-rule
  engine, then an LLM (Groq Llama-3.3-70B) writes the situational narrative.
- **Alerting** — reproducible rules fire on after-hours person/vehicle, loitering, repeat
  vehicle, and restricted-zone scenarios. Alerts and events carry the triggering frame's
  `blob_url`.
- **Operator surface** — REST API + React dashboard: live telemetry feed, event log,
  alert banner, semantic frame search, session summary, and a **RAG Q&A chatbot** with a
  reasoning loop that can call the VLM on demand (OpenAI `gpt-4o-mini` reasoning, Groq
  vision).

---

## Architecture at a glance

```
 source .mp4 clips
        │  data/video_loader.py  (OpenCV sampling + synthetic telemetry)
        ▼
 (frame_bytes, telemetry)
        │  data/ingest_runner.py
        ▼
 data/blob_store.py ──PUT──► MinIO (drone-frames bucket)  ──returns blob_url
        │
        ▼  POST /ingest { blob_url, telemetry }
 ┌─────────────────────────────────────────────────────────────────┐
 │ FastAPI backend  (backend/main.py)                                │
 │   LangGraph agent (agent/graph.py):                               │
 │     ingest_frame → analyze_frame(VLM) → query_history(pgvector)   │
 │       → reason_decide(rules + LLM)                                │
 │         → log_event → trigger_alert   (route "alert")             │
 │         → log_event                   (route "log")               │
 │         → —                           (route "normal")            │
 │       → update_state (persist frame + embedding)                  │
 └─────────────────────────────────────────────────────────────────┘
        │                         │
        ▼                         ▼
 PostgreSQL + pgvector      React dashboard (frontend/)
 (frames / events / alerts)  polls /events /alerts /frames, /summary, /chat
```

See [docs/architecture.md](docs/architecture.md) for the full node-by-node design.

---

## Prerequisites

- **Docker + Docker Compose** (runs the whole stack)
- A **Groq API key** (vision + reasoning). Get one at <https://console.groq.com>.
- *(Optional)* an **OpenAI API key** — used for embeddings (`text-embedding-3-small`) and
  for the Q&A chatbot's `gpt-4o-mini` reasoning loop. Without it, embeddings fall back to a
  local hashing embedder and the chatbot falls back to Groq.
- The **source video clips** (see [Sourcing the video clips](#sourcing-the-video-clips)).

---

## Quick start

```bash
# 1. Configure environment
cp .env.example .env
#    then edit .env and set:  GROQ_API_KEY=...   (and optionally OPENAI_API_KEY=...)

# 2. Bring up the full stack (postgres, minio, backend, frontend)
docker compose up -d --build

# 3. Open the dashboard
#    Dashboard:      http://localhost:3000
#    Backend API:    http://localhost:8000
#    MinIO console:  http://localhost:9101   (minioadmin / minioadmin)
```

The database schema ([db/init.sql](db/init.sql)) and the `drone-frames` MinIO bucket are
created automatically on first boot.

### Feeding the agent

The dashboard starts empty. Populate it either way:

```bash
# A) Drive frames from source video clips through the live agent (recommended)
python -m data.ingest_runner --frames 25 --interval 2.0

#    target a specific clip:
python -m data.ingest_runner --clips Normal_Videos_015_x264.mp4 -n 20
```

…or **B)** upload a single image through the dashboard's **Ingest Frame** panel.

> `ingest_runner` runs on the **host** and talks to the published ports
> (`localhost:8000`, `localhost:9100`). Install the host deps first:
> `pip install -r requirements.txt`.

---

## Sourcing the video clips

The clips are **not** committed to git (large binaries, gitignored). The agent samples
them to simulate a drone feed.

- **Dataset:** UCF-Crime — *Normal Videos for Event Recognition* (~1.1 GB, 49+ clips)
- **Download:** <https://www.crcv.ucf.edu/projects/real-world/>
- **Place under:** `videos/Normal_Videos_for_Event_Recognition/...` so the path matches
  `VIDEO_SOURCE_DIR` in `.env`.

Full rationale (why this dataset, sampling cadence, how synthetic telemetry is derived)
is in [docs/datasets.md](docs/datasets.md) and [docs/video_sources.md](docs/video_sources.md).

---

## REST API

| Method | Endpoint           | Purpose                                                        |
| ------ | ------------------ | ------------------------------------------------------------- |
| POST   | `/ingest`          | Run the full agent on `{ blob_url, telemetry }`               |
| POST   | `/ingest_image`    | Multipart image upload → MinIO → agent (dashboard upload)     |
| GET    | `/frames`          | Recent ingested frames (drives the Live Telemetry Feed)       |
| GET    | `/frames/search?q=`| Semantic (pgvector) frame search; `blob_url` per match        |
| GET    | `/events`          | Event log (logged/alerted frames)                             |
| GET    | `/alerts`          | Alerts; `active_only` filters unresolved                      |
| GET    | `/summary`         | LLM session summary + aggregate stats                         |
| POST   | `/chat`            | RAG Q&A with a reasoning loop + on-demand VLM tool            |
| GET    | `/health`          | Liveness                                                      |

---

## Provider split (LLMs)

| Task                          | Provider | Default model                              |
| ----------------------------- | -------- | ------------------------------------------ |
| Frame vision (`analyze_frame`)| Groq     | `meta-llama/llama-4-scout-17b-16e-instruct`|
| Reasoning (`reason_decide`)   | Groq     | `llama-3.3-70b-versatile`                  |
| Q&A chatbot reasoning         | OpenAI   | `gpt-4o-mini`                              |
| Q&A chatbot vision tool       | Groq     | `meta-llama/llama-4-scout-17b-16e-instruct`|
| Embeddings                    | OpenAI   | `text-embedding-3-small` (local fallback)  |

All configurable via `.env` (see [.env.example](.env.example)).

---

## Testing

```bash
# Unit + agent tests
pytest tests/test_analyze_frame.py tests/test_agent_pipeline.py

# API tests (requires the stack running)
pytest tests/test_api.py
```

QA scenarios (QA-01 … QA-09) with expected-vs-actual results are in
[docs/test_cases.md](docs/test_cases.md).

---

## Project structure

```
├── docker-compose.yml          # postgres, minio, minio_init, backend, frontend
├── db/init.sql                 # frames / events / alerts schema + pgvector
├── data/
│   ├── video_loader.py         # OpenCV frame sampling + synthetic telemetry
│   ├── blob_store.py           # MinIO upload/fetch
│   └── ingest_runner.py        # video → blob → POST /ingest orchestration
├── agent/
│   ├── graph.py                # LangGraph wiring
│   ├── state.py                # AgentState + cross-frame SessionStore
│   ├── llm.py                  # provider abstraction (Groq / OpenAI)
│   ├── embedder.py             # embeddings (OpenAI / local fallback)
│   ├── rules.py                # deterministic alert-rule engine
│   ├── db.py                   # async SQLAlchemy helpers
│   └── nodes/                  # ingest, analyze, query_history, reason, log, alert, update
├── backend/
│   ├── main.py                 # FastAPI app + lifespan
│   └── routes/                 # ingest, events, alerts, frames, summary, chat
├── frontend/                   # React + Tailwind dashboard
└── docs/                       # architecture, datasets, video_sources, test_cases
```

---

## Documentation

- [docs/architecture.md](docs/architecture.md) — system design, agent graph, schema, rules
- [docs/datasets.md](docs/datasets.md) — dataset choice, sampling, synthetic telemetry
- [docs/video_sources.md](docs/video_sources.md) — source clips + re-download steps
- [docs/test_cases.md](docs/test_cases.md) — QA scenarios, expected vs actual
