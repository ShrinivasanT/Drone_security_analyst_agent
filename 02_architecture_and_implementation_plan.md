# Drone Security Analyst Agent — Architecture & Implementation Plan

## 1. System Architecture

### High-Level Overview

The system is composed of five primary layers. Data flows in one direction — from dataset images through blob storage and the agent pipeline to stored intelligence — while the agent's decision loop runs continuously on top of the stored state.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        DATASET INGESTION LAYER                         │
│   HuggingFace datasets / Kaggle CLI  →  data/ingest_runner.py         │
│   Real images + synthetic telemetry paired per frame                   │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │ PUT image bytes
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│                          MINIO (Blob Storage)                           │
│   S3-compatible object store  ·  Bucket: drone-frames                  │
│   Returns blob_url per uploaded frame                                   │
│   Serves images directly to browser via HTTP                            │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │ blob_url + telemetry → POST /ingest
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│                         BACKEND (FastAPI)                               │
│                                                                         │
│   /ingest         →   LangGraph Agent Pipeline                         │
│   /events         →   Query PostgreSQL events table                    │
│   /alerts         →   Query PostgreSQL alerts table                    │
│   /frames/search  →   pgvector similarity + SQL → returns blob_urls    │
│   /summary        →   LLM session summary generation                   │
│   /chat           →   Natural-language Q&A over frame index            │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │ SQLAlchemy / asyncpg
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│                      POSTGRESQL + pgvector                              │
│                                                                         │
│   frames   │ events   │ alerts   │ telemetry                          │
│   (metadata + blob_url + embeddings stored together)                   │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │ REST API (polling)
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│                       FRONTEND (React + Tailwind)                       │
│   Live Telemetry · Event Log · Alert Banner                            │
│   Frame Search (renders <img src={blob_url}/> from MinIO)              │
│   Q&A Chatbox · Session Summary                                        │
└────────────────────────────────────────────────────────────────────────┘
```

---

### Blob Storage — Write and Read Paths

#### Write Path (Ingest)

```
data/ingest_runner.py  iterates dataset images
        │
        ├──► open image file as bytes
        │
        ├──► PUT bytes → MinIO  bucket=drone-frames  key=frame_{uuid}.jpg
        │    ← returns: http://minio:9000/drone-frames/frame_{uuid}.jpg
        │
        └──► POST /ingest
             body: { blob_url, telemetry: { time, location, lat, lng, altitude } }
                        │
                        ▼
               LangGraph Agent
                        │
               fetch image bytes from blob_url (HTTP GET → MinIO)
                        │
               send bytes to VLM API → structured JSON
                        │
               embed description → INSERT INTO frames (..., blob_url, embedding)
```

#### Read Path (Search Result Rendering)

```
Operator: "show all truck events"
        │
        ▼
GET /frames/search?q=truck
        │
        ▼
pgvector cosine search
→ SELECT frame_id, timestamp, location, object_type, blob_url, similarity FROM frames
  ORDER BY embedding <-> $query_embedding LIMIT 10
        │
        ▼
API response: [ { frame_id, timestamp, blob_url, object_type, ... }, ... ]
        │
        ▼
React frontend:
  {results.map(r => <img src={r.blob_url} alt={r.object_type} />)}
→ Browser fetches images directly from MinIO HTTP endpoint
→ Operator sees real dataset frames rendered as thumbnails
```

This design keeps PostgreSQL lean (metadata + vectors only) and offloads binary blob serving entirely to MinIO, which is purpose-built for it.

---

### LangGraph Agent — Node-by-Node Architecture

The agent is the reasoning core. It runs as a stateful cyclic graph — every video frame triggers one full cycle through all nodes, with persistent state carried forward between cycles.

```
                    ┌──────────────────────────┐
                    │       ingest_frame        │
                    │  receives blob_url        │
                    │  + telemetry JSON         │
                    └──────────┬────────────────┘
                               │
                               ▼
                    ┌──────────────────────────┐
                    │      analyze_frame        │
                    │  fetch image from MinIO   │
                    │  send bytes → VLM API     │
                    │  → structured JSON:       │
                    │   object_type, location,  │
                    │   action, clothing, color │
                    └──────────┬────────────────┘
                               │
                               ▼
                    ┌──────────────────────────┐
                    │      query_history        │
                    │  embed current descrip.   │
                    │  pgvector cosine search   │
                    │  + SQL filter on          │
                    │  location / time window   │
                    │  → returns prior frames   │
                    │    including blob_urls    │
                    └──────────┬────────────────┘
                               │
                               ▼
                    ┌──────────────────────────┐
                    │      reason_decide        │
                    │  LLM receives:            │
                    │  - current frame JSON     │
                    │  - rolling window (last N)│
                    │  - history query results  │
                    │  - alert rules            │
                    │  Decides: normal /        │
                    │  log_event / alert        │
                    └─────┬──────────┬──────────┘
                          │          │
               ┌──────────▼──┐  ┌───▼──────────┐
               │  log_event  │  │ trigger_alert │
               │  INSERT INTO│  │ INSERT INTO   │
               │  events     │  │ alerts table  │
               │  with       │  │ with blob_url │
               │  blob_url   │  │ of trigger    │
               └──────────┬──┘  └───┬───────────┘
                          │         │
                          └────┬────┘
                               ▼
                    ┌──────────────────────────┐
                    │      update_state         │
                    │  embed description        │
                    │  INSERT INTO frames       │
                    │  (metadata + blob_url     │
                    │   + embedding vector)     │
                    │  advance rolling_window   │
                    │  append to events_today   │
                    └──────────┬────────────────┘
                               │
                          next frame
```

### AgentState Schema

```python
class AgentState(TypedDict):
    current_frame: dict          # { blob_url, vlm_json, telemetry }
    telemetry: dict              # { time, location, lat, lng, altitude }
    rolling_window: list[dict]   # last N frame VLM descriptions (configurable, default 10)
    events_today: list[dict]     # all logged events this session
    active_alerts: list[dict]    # currently unresolved alerts
```

---

### Database Schema

```sql
-- Indexed frame store: metadata + blob reference + vector embedding
CREATE TABLE frames (
    id              SERIAL PRIMARY KEY,
    frame_id        TEXT NOT NULL UNIQUE,
    timestamp       TIMESTAMPTZ NOT NULL,
    blob_url        TEXT NOT NULL,          -- MinIO URL; frontend renders this as <img>
    location        TEXT,
    object_type     TEXT,
    action          TEXT,
    clothing        TEXT,
    color           TEXT,
    raw_description TEXT NOT NULL,          -- full VLM output text
    embedding       VECTOR(1536),           -- text-embedding-3-small
    telemetry       JSONB                   -- full telemetry snapshot
);

-- Human-readable event log
CREATE TABLE events (
    id          SERIAL PRIMARY KEY,
    event_type  TEXT NOT NULL,              -- 'vehicle_entry', 'loitering', etc.
    description TEXT NOT NULL,
    severity    TEXT DEFAULT 'info',        -- 'info', 'warning', 'critical'
    frame_id    TEXT REFERENCES frames(frame_id),
    blob_url    TEXT,                       -- denormalised for fast alert display
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Active alert registry
CREATE TABLE alerts (
    id           SERIAL PRIMARY KEY,
    rule         TEXT NOT NULL,             -- which alert rule fired
    message      TEXT NOT NULL,
    severity     TEXT NOT NULL,
    blob_url     TEXT,                      -- frame that triggered the alert
    triggered_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at  TIMESTAMPTZ,
    metadata     JSONB
);

-- Fast vector similarity index
CREATE INDEX ON frames USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Fast SQL filters
CREATE INDEX ON frames (location, timestamp);
CREATE INDEX ON frames (object_type);
```

---

### Docker Compose Service Layout

```yaml
version: "3.9"

services:

  postgres:
    image: ankane/pgvector             # PostgreSQL 15 + pgvector pre-installed
    environment:
      POSTGRES_DB: drone_security
      POSTGRES_USER: drone
      POSTGRES_PASSWORD: drone_pass
    volumes:
      - pg_data:/var/lib/postgresql/data
      - ./db/init.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "5432:5432"

  minio:
    image: minio/minio                 # S3-compatible object store
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    volumes:
      - minio_data:/data
    ports:
      - "9000:9000"   # S3 API (boto3 endpoint)
      - "9001:9001"   # MinIO web console

  minio_init:
    image: minio/mc                    # one-shot: create bucket on startup
    depends_on:
      - minio
    entrypoint: >
      /bin/sh -c "
        mc alias set local http://minio:9000 minioadmin minioadmin &&
        mc mb --ignore-existing local/drone-frames &&
        mc anonymous set download local/drone-frames
      "

  backend:
    build: ./backend                   # Python 3.11 + FastAPI + LangGraph
    environment:
      DATABASE_URL: postgresql+asyncpg://drone:drone_pass@postgres/drone_security
      MINIO_ENDPOINT: http://minio:9000
      MINIO_ACCESS_KEY: minioadmin
      MINIO_SECRET_KEY: minioadmin
      MINIO_BUCKET: drone-frames
      OPENAI_API_KEY: ${OPENAI_API_KEY}
    depends_on:
      - postgres
      - minio
    ports:
      - "8000:8000"

  frontend:
    build: ./frontend                  # React + Tailwind, served via Nginx
    ports:
      - "3000:80"
    depends_on:
      - backend

volumes:
  pg_data:
  minio_data:
```

---

## 2. Data Flow — Real Image Frame to Alert

```
Dataset image: pedestrian_night_0042.jpg  (from HuggingFace nighttime dataset)
        +
Synthetic telemetry:
{ time: "00:01", location: "main gate", altitude: 12, lat: 18.52, lng: 73.85 }
        │
        ▼  ingest_runner.py
        │
        ├─ Upload image bytes → MinIO
        │  ← blob_url: http://localhost:9000/drone-frames/frame_0042.jpg
        │
        ▼  POST /ingest { blob_url, telemetry }
        │
        ├─ [analyze_frame]
        │   Fetch image bytes from blob_url (HTTP GET → MinIO)
        │   VLM prompt: "Analyse this security camera image. Extract structured JSON."
        │   VLM sees: actual image of a person standing at a gate at night
        │   Output: { object_type: "person", clothing: "dark jacket",
        │             location: "main gate", action: "standing",
        │             estimated_time_of_day: "night", confidence: 0.91 }
        │
        ├─ [query_history]
        │   Embed "person in dark jacket standing at main gate at night"
        │   SQL: WHERE location = 'main gate' AND timestamp > NOW() - INTERVAL '1 hour'
        │   pgvector: ORDER BY embedding <-> $query_embedding LIMIT 10
        │   Result: 4 prior frames showing same description over last 8 minutes
        │
        ├─ [reason_decide]
        │   LLM prompt includes:
        │     - current frame JSON
        │     - rolling window: frames 5–9 all show "person at main gate"
        │     - history: 4 prior matches in last 8 minutes
        │     - alert rule: loitering = same object_type + location across 5+ frames
        │   LLM output: "Person has been at main gate for 8 consecutive frames
        │                at 00:01 — outside permitted hours. ALERT: loitering."
        │
        ├─ [trigger_alert]
        │   INSERT INTO alerts
        │   (rule='loitering_after_hours',
        │    message='Person loitering at main gate, 00:01 — 8 minutes',
        │    severity='critical',
        │    blob_url='http://localhost:9000/drone-frames/frame_0042.jpg')
        │
        └─ [update_state]
            Embed description → INSERT INTO frames (blob_url, embedding, metadata)
            Append to rolling_window
            Append to events_today
```

---

## 3. Alert Rules

| Rule ID | Condition | Severity | Example Message |
|---|---|---|---|
| `after_hours_person` | Person detected outside 08:00–18:00 | Critical | "Person at main gate, 00:01 — after hours" |
| `loitering` | Same object_type + location across 5+ consecutive frames | High | "Person loitering at side entrance, 8 minutes" |
| `repeat_vehicle` | Same vehicle descriptor seen 3+ times in session | Warning | "Blue truck — 3rd entry today, last at 23:50" |
| `restricted_zone` | Any object in a configured restricted location label | Critical | "Person at server room zone, 14:32" |
| `after_hours_vehicle` | Vehicle entry outside 08:00–18:00 | High | "Vehicle at garage gate, 23:50 — after hours" |

---

## 4. Implementation Plan — Phases

---

### Phase 1 — Foundation (Blob Storage + Database + Dataset Loader)

**Goal:** MinIO and PostgreSQL running in Docker, with a working dataset image loader that uploads frames to MinIO and seeds the database.

**Tasks:**
- Write `docker-compose.yml` with `postgres`, `minio`, `minio_init` services
- Write `db/init.sql` — create `frames`, `events`, `alerts` tables, indexes, and pgvector extension
- Write `data/dataset_loader.py`
  - Uses `datasets` library (HuggingFace) to download the nighttime pedestrian dataset and/or cars dataset
  - Alternatively supports Kaggle CLI download for VIRAT / person detection datasets
  - Yields `(image_bytes, synthetic_telemetry)` tuples
- Write `data/blob_store.py`
  - `boto3` S3 client pointed at MinIO
  - `upload_frame(image_bytes, filename) → blob_url`
  - `get_frame_bytes(blob_url) → bytes`
- Write `data/ingest_runner.py`
  - Calls `dataset_loader` → `blob_store.upload_frame` → `POST /ingest`
  - Configurable: how many frames to ingest, which dataset, frame interval
- Verify: `docker compose up postgres minio minio_init` → MinIO console at localhost:9001 → bucket created → upload a test image → URL accessible in browser

**Deliverables:**
- `docker-compose.yml`
- `db/init.sql`
- `data/dataset_loader.py`
- `data/blob_store.py`
- `data/ingest_runner.py`

---

### Phase 2 — VLM Integration (Frame Analysis with Real Images)

**Goal:** A working `analyze_frame` node that fetches a real image from MinIO, sends it to the VLM API, and returns structured JSON.

**Tasks:**
- Write `agent/nodes/analyze_frame.py`
  - Accepts `blob_url` from agent state
  - Fetches image bytes from MinIO via `blob_store.get_frame_bytes()`
  - Encodes bytes as base64
  - Calls GPT-4o vision (or Claude API) with the image and a structured extraction prompt
  - Parses and validates the JSON response
  - Returns `object_type`, `location`, `action`, `clothing`, `color`, `confidence`
- Write `agent/embedder.py`
  - Calls `text-embedding-3-small` on the VLM's text description
  - Returns a 1536-dimensional vector
- Write `agent/db.py`
  - Async SQLAlchemy helpers: `insert_frame()`, `query_similar_frames()`, `insert_event()`, `insert_alert()`
  - `insert_frame()` writes `blob_url` and `embedding` together
- Unit test: feed 5 real dataset images → assert valid structured JSON returned for each

**Deliverables:**
- `agent/nodes/analyze_frame.py`
- `agent/embedder.py`
- `agent/db.py`
- `tests/test_analyze_frame.py`

---

### Phase 3 — LangGraph Agent (Core Loop)

**Goal:** A complete LangGraph graph that processes one real image frame end-to-end and writes results to the database.

**Tasks:**
- Define `AgentState` TypedDict in `agent/state.py`
- Implement remaining nodes:
  - `agent/nodes/ingest_frame.py` — validates blob_url + telemetry, structures initial state
  - `agent/nodes/query_history.py` — runs combined pgvector + SQL query, returns matching rows including blob_urls
  - `agent/nodes/reason_decide.py` — LLM reasoning with rolling window, history context, and alert rules
  - `agent/nodes/log_event.py` — writes to `events` table with blob_url
  - `agent/nodes/trigger_alert.py` — writes to `alerts` table with blob_url of triggering frame
  - `agent/nodes/update_state.py` — persists frame to PostgreSQL (metadata + blob_url + embedding), advances rolling window
- Wire the graph in `agent/graph.py` with conditional edges (log vs alert vs both)
- Integration test: run graph on 10 real dataset images → assert events and alerts written correctly with valid blob_urls

**Deliverables:**
- `agent/state.py`
- `agent/nodes/*.py` (6 node files)
- `agent/graph.py`
- `tests/test_agent_pipeline.py`

---

### Phase 4 — FastAPI Backend (REST Endpoints)

**Goal:** A FastAPI server that exposes the agent, database, and blob-aware search over HTTP.

**Tasks:**
- `backend/main.py` — FastAPI app with CORS, lifespan (DB pool init, MinIO client init)
- Routes:
  - `POST /ingest` — accepts `{ blob_url, telemetry }`, runs LangGraph agent, returns result
  - `GET /events` — paginated list of logged events (includes `blob_url` per event)
  - `GET /alerts` — list of active alerts (includes `blob_url` of triggering frame)
  - `GET /frames/search?q=...` — pgvector similarity search; response includes `blob_url` per match so frontend can render images
  - `GET /summary` — triggers LLM session summary generation
  - `POST /chat` — accepts a natural-language question, returns grounded answer with referenced blob_urls
- Write `tests/test_api.py` — test each endpoint with sample payloads; assert blob_url present in search results

**Search response shape:**
```json
{
  "results": [
    {
      "frame_id": "frame_0042",
      "timestamp": "2024-01-15T00:01:00Z",
      "blob_url": "http://localhost:9000/drone-frames/frame_0042.jpg",
      "object_type": "person",
      "location": "main gate",
      "similarity": 0.94
    }
  ]
}
```

**Deliverables:**
- `backend/main.py`
- `backend/routes/*.py`
- `tests/test_api.py`

---

### Phase 5 — React Dashboard (Frontend with Image Rendering)

**Goal:** A working single-page dashboard that visualises live agent output and renders actual frame images from MinIO.

**Panels:**

| Panel | Data Source | Update | Image Rendering |
|---|---|---|---|
| Live Telemetry Feed | `GET /events` (last 10) | Poll 2 s | Small thumbnail per event via `blob_url` |
| Event Log | `GET /events` | Poll 5 s | Thumbnail on row expand |
| Alert Banner | `GET /alerts` (unresolved) | Poll 2 s | Snapshot of triggering frame |
| Frame Search | `GET /frames/search?q=` | On user input | Grid of `<img src={blob_url}/>` thumbnails |
| Q&A Chatbox | `POST /chat` | On submit | Referenced frames shown inline |
| Session Summary | `GET /summary` | On button click | Text only |

**Tasks:**
- Scaffold React app with Tailwind CSS
- `FrameSearch.jsx` — search box + result grid rendering `<img src={blob_url} />` for each match; clicking a thumbnail shows the full frame in a modal with metadata sidebar
- `AlertBanner.jsx` — red banner with the triggering frame image and alert message
- `EventLog.jsx` — expandable rows, thumbnail shown on expand
- `TelemetryFeed.jsx` — scrolling live feed
- `ChatBox.jsx` — chat UI with inline frame references
- `SessionSummary.jsx` — summary text panel

**Deliverables:**
- `frontend/src/components/TelemetryFeed.jsx`
- `frontend/src/components/EventLog.jsx`
- `frontend/src/components/AlertBanner.jsx`
- `frontend/src/components/FrameSearch.jsx`
- `frontend/src/components/ChatBox.jsx`
- `frontend/src/components/SessionSummary.jsx`

---

### Phase 6 — Integration, QA, and Documentation

**Goal:** Full system running end-to-end with real dataset images, documented test cases, README, and demo-ready setup.

**QA Test Cases:**

| Test ID | Scenario | Input | Expected Result |
|---|---|---|---|
| QA-01 | Vehicle image ingested | Car image from cars196 dataset at 12:00 | Event logged with blob_url; object_type = vehicle |
| QA-02 | Same vehicle descriptor 3rd time at 23:50 | 3 car images, similar VLM outputs | Alert triggered: "Repeat vehicle, after-hours"; blob_url in alert |
| QA-03 | Nighttime pedestrian image at 00:01 | Nighttime pedestrian dataset image | Alert triggered: "Person after hours, 00:01" |
| QA-04 | Loitering — same person/location across 5 frames | 5 consecutive similar nighttime pedestrian images | Alert triggered: "Loitering detected" |
| QA-05 | Frame search returns images | Query "truck" or "vehicle" | API returns rows with blob_url; frontend renders thumbnails |
| QA-06 | Search result image accessible | blob_url from QA-05 | HTTP GET to blob_url returns valid image bytes (200 OK from MinIO) |
| QA-07 | Chat Q grounded in frames | "Was a vehicle seen after midnight?" | Answer references specific frame timestamps and blob_urls |
| QA-08 | Session summary | After 20 real frames processed | One-sentence summary covering detected object types and alerts |
| QA-09 | Normal daytime activity | Daytime vehicle/person images 09:00–17:00 | No alerts; events logged normally with blob_urls |

**Documentation Tasks:**
- `README.md` — setup instructions (docker compose up, dataset download, ingest_runner), architecture overview, AI tools used
- `docs/architecture.md` — this document
- `docs/datasets.md` — dataset sources, download commands, licensing notes
- `docs/test_cases.md` — QA scenarios with expected vs actual outputs
- Record demo video with voiceover showing real frame images in the dashboard

**Deliverables:**
- `README.md`
- `docs/` directory
- Demo video

---

## 5. Repository Structure

```
drone-security-agent/
│
├── docker-compose.yml
├── .env.example
├── README.md
│
├── db/
│   └── init.sql
│
├── data/
│   ├── dataset_loader.py        # HuggingFace / Kaggle dataset download + iteration
│   ├── blob_store.py            # boto3 MinIO client: upload_frame(), get_frame_bytes()
│   └── ingest_runner.py         # orchestrates loader → blob upload → POST /ingest
│
├── agent/
│   ├── state.py
│   ├── graph.py
│   ├── embedder.py
│   ├── db.py
│   └── nodes/
│       ├── ingest_frame.py      # validate blob_url + telemetry
│       ├── analyze_frame.py     # fetch image from MinIO → VLM → structured JSON
│       ├── query_history.py     # pgvector + SQL → returns rows with blob_urls
│       ├── reason_decide.py     # LLM reasoning: normal / log / alert
│       ├── log_event.py         # INSERT INTO events (blob_url, ...)
│       ├── trigger_alert.py     # INSERT INTO alerts (blob_url, ...)
│       └── update_state.py      # INSERT INTO frames (blob_url, embedding, ...)
│
├── backend/
│   ├── main.py
│   └── routes/
│       ├── ingest.py
│       ├── events.py
│       ├── alerts.py
│       ├── frames.py            # /frames/search returns blob_url per result
│       ├── summary.py
│       └── chat.py
│
├── frontend/
│   ├── package.json
│   ├── Dockerfile
│   └── src/
│       ├── App.jsx
│       └── components/
│           ├── TelemetryFeed.jsx
│           ├── EventLog.jsx
│           ├── AlertBanner.jsx  # renders triggering frame image
│           ├── FrameSearch.jsx  # image grid from blob_urls
│           ├── ChatBox.jsx
│           └── SessionSummary.jsx
│
├── tests/
│   ├── test_analyze_frame.py
│   ├── test_agent_pipeline.py
│   └── test_api.py              # asserts blob_url present in search responses
│
└── docs/
    ├── architecture.md
    ├── datasets.md
    └── test_cases.md
```

---

## 6. Phase Summary

| Phase | Focus | Key Output |
|---|---|---|
| 1 | Foundation | Docker + DB schema + MinIO + Dataset loader + Blob uploader |
| 2 | VLM Integration | Real image fetch from MinIO → VLM analysis → embedding + DB helpers |
| 3 | LangGraph Agent | Full reasoning loop — ingest → analyse real image → reason → log/alert with blob_urls |
| 4 | FastAPI Backend | REST API; search endpoint returns blob_urls for image rendering |
| 5 | React Dashboard | Image grid search, alert banner with triggering frame, expandable event log thumbnails |
| 6 | QA + Docs | Test cases (incl. blob_url accessibility), README with dataset download instructions |
