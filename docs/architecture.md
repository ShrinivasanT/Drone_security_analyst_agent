# Architecture

This document describes the system design of the Drone Security Analyst Agent: the data
plane, the LangGraph reasoning agent, the database schema, the alert-rule engine, and the
operator-facing API/UI. For build ordering see [../Implementation.md](../Implementation.md);
for the original full design see
[../02_architecture_and_implementation_plan.md](../02_architecture_and_implementation_plan.md).

---

## 1. System overview

The agent simulates a drone surveillance feed by sampling frames from pre-recorded CCTV
clips, pairing each with synthetic telemetry, then running a per-frame reasoning cycle that
understands the scene, compares it against recent and historical context, decides whether
to log/alert, and persists everything for an operator dashboard.

```
 source .mp4 clips
        │  data/video_loader.py   (OpenCV: sample 1 frame / N seconds of video)
        │                         (+ synthetic telemetry: time, waypoint, GPS, altitude)
        ▼
 (frame_bytes, telemetry)
        │  data/ingest_runner.py  (orchestration)
        ▼
 data/blob_store.py ──PUT──► MinIO (drone-frames)  → blob_url
        │
        ▼  POST /ingest { blob_url, telemetry }
 FastAPI backend → LangGraph agent → PostgreSQL + pgvector
        │
        ▼
 React dashboard  (polls REST endpoints, renders frames from blob_url)
```

**Source-agnostic boundary:** `video_loader` yields the exact `(frame_bytes, telemetry)`
shape the rest of the pipeline expects. Nothing downstream of blob storage knows or cares
that frames came from video vs. a live feed vs. uploads.

---

## 2. Components

| Layer        | Component                       | Responsibility                                              |
| ------------ | ------------------------------- | ----------------------------------------------------------- |
| Data plane   | `data/video_loader.py`          | Sample frames from clips; fabricate per-frame telemetry      |
|              | `data/blob_store.py`            | MinIO upload/fetch; returns browser-reachable `blob_url`     |
|              | `data/ingest_runner.py`         | Orchestrate video → blob → `POST /ingest`                    |
| Agent        | `agent/graph.py`                | LangGraph wiring with conditional edges                      |
|              | `agent/state.py`                | `AgentState` + cross-frame `SessionStore`                    |
|              | `agent/nodes/*`                 | The seven pipeline nodes                                     |
|              | `agent/rules.py`                | Deterministic alert-rule engine                              |
|              | `agent/llm.py`                  | Provider abstraction (Groq / OpenAI), JSON + tool calling    |
|              | `agent/embedder.py`             | Embeddings (OpenAI `text-embedding-3-small` / local fallback)|
|              | `agent/db.py`                   | Async SQLAlchemy helpers                                     |
| Backend      | `backend/main.py`               | FastAPI app, CORS, lifespan                                  |
|              | `backend/routes/*`              | ingest, events, alerts, frames, summary, chat               |
| Frontend     | `frontend/src/components/*`     | Dashboard panels                                            |
| Storage      | PostgreSQL + pgvector / MinIO   | Structured records + frame images                           |

---

## 3. The LangGraph agent

One `POST /ingest` call runs one full cycle. Defined in
[../agent/graph.py](../agent/graph.py).

```
ingest_frame → analyze_frame → query_history → reason_decide
    ├─ route "alert"  → log_event → trigger_alert → update_state → END
    ├─ route "log"    → log_event ───────────────→ update_state → END
    └─ route "normal" ───────────────────────────→ update_state → END
```

### Nodes

1. **`ingest_frame`** — validates `current_frame.blob_url`; seeds `AgentState` from the
   `SessionStore` (rolling window of recent frames, today's events, active alerts).
2. **`analyze_frame`** — fetches image bytes from MinIO, base64-encodes, calls the **VLM**
   (Groq Llama-4 Scout) with a structured-extraction prompt → validated JSON
   (`object_type`, `location`, `action`, `clothing`, `color`, `confidence`, `description`).
3. **`query_history`** — embeds the description, then runs two retrievals in parallel:
   pgvector cosine similarity (semantically similar past frames) and a SQL location/time
   filter (recent frames at the same waypoint, for loitering/repeat detection). The
   embedding is stashed on state for reuse.
4. **`reason_decide`** — two-stage:
   - **Rule engine** ([../agent/rules.py](../agent/rules.py)) decides *whether* an alert
     fires — deterministic and unit-testable.
   - **LLM** (Groq Llama-3.3-70B) writes the situational narrative and judges whether an
     otherwise-unremarkable frame is worth logging (`noteworthy`). On failure it falls back
     to a deterministic summary so the pipeline never breaks.
   - Emits a routing `decision`: `normal` | `log` | `alert`.
5. **`log_event`** — writes an `events` row (runs for `log` and `alert`).
6. **`trigger_alert`** — writes one `alerts` row per fired rule (runs for `alert`).
7. **`update_state`** — persists the `frames` row (metadata + embedding), advances the
   `SessionStore`, and builds the API result payload.

### State & memory

LangGraph state is per-invocation, but the agent needs memory spanning frames. Two tiers:

- **`SessionStore`** (process singleton, [../agent/state.py](../agent/state.py)) — the
  rolling window of recent frame summaries plus this session's events/alerts. Seeded into
  state in `ingest_frame`, written back in `update_state`. Drives cross-frame rules
  (loitering, repeat vehicle) within a run.
- **PostgreSQL + pgvector** — durable history, read back by `query_history`.

---

## 4. Database schema

[../db/init.sql](../db/init.sql). Three tables:

- **`frames`** — every ingested frame: `frame_id`, `timestamp`, `blob_url`, `location`,
  `object_type`, `action`, `clothing`, `color`, `raw_description`, `embedding VECTOR(1536)`,
  `telemetry JSONB`.
- **`events`** — human-readable log: `event_type`, `description`, `severity`, `frame_id`,
  `blob_url`, `created_at`. Written only for `log`/`alert` routes.
- **`alerts`** — fired rules: `rule`, `message`, `severity`, `blob_url`, `metadata JSONB`,
  `triggered_at`, `resolved_at`.

`blob_url` is denormalised onto events/alerts so the frontend can render the triggering
frame without a join. `pgvector` powers semantic frame search and history retrieval.

---

## 5. Alert-rule engine

Kept separate from the LLM so firing is reproducible run-to-run
([../agent/rules.py](../agent/rules.py)). Business hours default to 08:00–18:00.

| Rule                 | Severity | Condition                                                       |
| -------------------- | -------- | --------------------------------------------------------------- |
| `after_hours_person` | critical | person detected outside business hours                          |
| `after_hours_vehicle`| high     | vehicle detected outside business hours                         |
| `loitering`          | high     | same object + location across ≥5 consecutive frames             |
| `repeat_vehicle`     | warning  | same vehicle descriptor (type+colour) seen ≥3× this session     |
| `restricted_zone`    | critical | any subject in a configured restricted location                 |

The LLM produces narrative only — it **cannot suppress** a rule-fired alert.

---

## 6. LLM provider split

Configurable via `.env`; defaults pin vision/reasoning to Groq and the Q&A chatbot's
reasoning to OpenAI `gpt-4o-mini`.

| Task                           | Provider | Default model                              |
| ------------------------------ | -------- | ------------------------------------------ |
| Frame vision (`analyze_frame`) | Groq     | `meta-llama/llama-4-scout-17b-16e-instruct`|
| Reasoning (`reason_decide`)    | Groq     | `llama-3.3-70b-versatile`                  |
| Q&A reasoning loop             | OpenAI   | `gpt-4o-mini`                              |
| Q&A on-demand vision tool      | Groq     | `meta-llama/llama-4-scout-17b-16e-instruct`|
| Embeddings                     | OpenAI   | `text-embedding-3-small` (local fallback)  |

Both Groq and OpenAI expose an OpenAI-compatible chat API, so a single client abstraction
([../agent/llm.py](../agent/llm.py)) handles both — only `base_url`, key, and model names
differ. The chat route passes explicit `provider=` arguments, so the split holds regardless
of the `LLM_PROVIDER` / `LLM_ALLOW_OPENAI_CHAT` toggles.

---

## 7. Q&A chatbot reasoning loop

`POST /chat` ([../backend/routes/chat.py](../backend/routes/chat.py)) is a ReAct-style loop
(up to 3 tool rounds), not a single-shot RAG call:

```
embed(question) → pgvector top-k retrieval
   → gpt-4o-mini reasons over the JSON metadata
       ├─ metadata sufficient → final {answer, frame_ids}
       └─ needs visual detail → calls analyze_frame_visual(blob_url)
              → Groq VLM inspects the frame for the question
              → result fed back → reason again
```

Prior conversation turns are threaded in, so follow-ups keep context.

---

## 8. Frontend

React + Tailwind ([../frontend/](../frontend/)), polling REST endpoints.

| Panel               | Source            | Update      |
| ------------------- | ----------------- | ----------- |
| Live Telemetry Feed | `GET /frames`     | poll 2 s    |
| Event Log           | `GET /events`     | poll 5 s    |
| Alert Banner        | `GET /alerts`     | poll 2 s    |
| Frame Search        | `GET /frames/search` | on submit|
| Q&A Chatbox         | `POST /chat`      | on submit   |
| Session Summary     | `GET /summary`    | on button   |

All image rendering uses the `blob_url` stored on each record, fetched directly from MinIO
by the browser.
