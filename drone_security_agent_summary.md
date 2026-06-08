# Drone Security Analyst Agent — Discussion Summary

## 1. Problem Statement Summary

Build a prototype AI agent for a **docked drone** that continuously monitors a fixed property. The system processes simulated telemetry data and video frames, detects security events, logs them with context, and raises real-time alerts.

### Core Requirements
| # | Requirement |
|---|---|
| 1 | Process simulated drone telemetry (position, altitude, time) and video frames |
| 2 | Analyze frames to identify objects/activities (vehicles, people) and log them |
| 3 | Generate real-time alerts based on predefined rules |
| 4 | Index frames in a queryable database (by timestamp or object type) |

### Expected Outputs
- **Log**: `"Blue Ford F150 spotted at garage, 12:00"`
- **Alert**: `"Person loitering at main gate, 00:01"`
- **Query**: `"Show all truck events"` → returns matching indexed frames

### Key Deliverables
- Python prototype (VLM + LangGraph agent + telemetry pipeline)
- React dashboard (frontend for demo)
- PDF report + demo video with voiceover
- Private GitHub repo
- Docker Compose setup for full local deployment

### Bonus Features
- Video summarization (1-sentence summary of the full session)
- Chatbot Q&A on top of indexed frames (e.g., *"What objects appeared today?"*)

---

## 2. Issues Identified & Solutions Discussed

---

### Issue 1 — Do we need a frontend?

**Question:** Is a frontend required, and what stack?

**Answer:** Not explicitly required, but strongly implied by:
- The demo video requirement (needs something visual)
- The queryable frame index (needs a search UI)
- Alert display

**Solution:**
- **Stack:** Simple React + Tailwind single-page dashboard
- **Panels:** Live telemetry feed, event log, alert banner, frame search box
- Keep it lightweight — this is a prototype, not a production app

---

### Issue 2 — Where does the agentic framework fit?

**Question:** Where does LangGraph come in? Is a chatbot needed?

**Answer:** The **LangGraph agent** is the core reasoning brain of the system. LangGraph is preferred over plain LangChain because the frame-by-frame processing is inherently **stateful and cyclical** — each frame updates shared state and the agent loops back for the next frame. LangGraph models this natively as a graph with nodes and edges.

**Solution — LangGraph Node Structure:**
```
                  ┌─────────────────┐
                  │   ingest_frame  │  ← receives frame + telemetry
                  └────────┬────────┘
                           ↓
                  ┌─────────────────┐
                  │  analyze_frame  │  ← VLM extracts structured JSON
                  └────────┬────────┘
                           ↓
                  ┌─────────────────┐
                  │  query_history  │  ← pgvector similarity + SQL query
                  └────────┬────────┘
                           ↓
                  ┌─────────────────┐
                  │  reason_decide  │  ← LLM reasons: anomaly? pattern?
                  └────────┬────────┘
                      ↙         ↘
             log_event        trigger_alert
                      ↘         ↙
                  ┌─────────────────┐
                  │  update_state   │  ← persist to PostgreSQL, update rolling window
                  └────────┬────────┘
                           ↓
                     next frame loop
```

**Persistent state across frames** (LangGraph's key advantage):
```python
class AgentState(TypedDict):
    current_frame: dict
    telemetry: dict
    rolling_window: list      # last N frame descriptions
    events_today: list        # all logged events this session
    active_alerts: list       # currently active alerts
```

The **chatbot** is a secondary bonus feature — a thin Q&A interface on top of the already-built frame index. Not the main agent.

---

### Issue 3 — Why does the agent query history? What's the point?

**Question:** What would the agent actually query history for?

**Answer:** History gives the agent **context over time**, enabling pattern detection that single frames cannot provide.

**Solution — Concrete Examples:**

| Scenario | Without History | With History |
|---|---|---|
| Repeat vehicle | "Blue truck seen" | "Blue F150 entered 3 times today, last at 11pm — unusual" |
| Loitering | "Person at gate" | "Same person, same spot, 8 minutes — ALERT: loitering" |
| After-hours | "Person at gate" | "All prior entries 08:00–18:00, current time 00:01 — ALERT: intrusion" |

> **Key insight:** Without history, the agent just says *"person seen."* With history, it says *"same person, third time tonight, at midnight."*

---

### Issue 4 — VLM has no context across frames (Core architectural challenge)

**Question:** How can you identify the same person or event across frames when a VLM processes each frame in isolation?

**Answer:** This is the central challenge. A VLM sees each frame independently with no cross-frame memory.

**Solution — Three-Layer Approach:**

#### Layer 1 — Structured Metadata Extraction (VLM's job)
Ask the VLM to extract consistent descriptors per frame as structured JSON:
```json
{
  "object_type": "person",
  "clothing": "red shirt, blue jeans",
  "location": "main gate",
  "action": "standing",
  "time": "00:01"
}
```
The VLM **describes**. It does not reason across time.

#### Layer 2 — Rolling Context Window (LangGraph state)
The `rolling_window` field in LangGraph's agent state holds the last N frame descriptions. At the `reason_decide` node, the full window is passed into the LLM prompt:
```
"Here are the last 5 frames:
 Frame 5: person in red shirt at gate
 Frame 6: person in red shirt at gate
 Frame 7: person in red shirt at gate
 Is anything suspicious?"
```
Now the LLM reasons across frames because history is part of the graph's persistent state.

#### Layer 3 — pgvector Semantic Search (Cross-domain indexing)
Frame description embeddings are stored in PostgreSQL via the `pgvector` extension. The `query_history` node runs a combined query:
```sql
SELECT * FROM frames
WHERE location = 'main gate'
  AND timestamp > NOW() - INTERVAL '1 hour'
ORDER BY embedding <-> $1  -- cosine similarity
LIMIT 10;
```
This gives both **structured filtering** (SQL) and **semantic similarity** (vector) in a single query — something ChromaDB cannot do natively.

#### Full Pipeline
```
Video Frame
    ↓
  VLM  →  Structured JSON (object, color, location, action)
    ↓
Store in PostgreSQL (structured row + pgvector embedding)
    ↓
LangGraph Agent state contains:
  - Current frame description
  - Rolling window of last N frames
  - Query results from pgvector
    ↓
Agent reasons: same person? repeat vehicle? anomaly?
    ↓
Log event  /  Trigger alert
```

---

### Issue 5 — Tool & Database Choice Rationale

#### Why PostgreSQL + pgvector over ChromaDB / FAISS / Pinecone?

| DB | Verdict |
|---|---|
| **FAISS** | Library only — no persistence, no metadata filtering, no SQL. Needs storage built on top. |
| **ChromaDB** | Easy setup but no combined SQL + vector query. Metadata filtering is limited. |
| **Pinecone** | Cloud-only, paid, external dependency. Adds friction. |
| **Milvus** | Production-grade but heavy Docker setup, overkill for prototype. |
| **PostgreSQL + pgvector** | Full SQL + vector similarity in one place. Single combined queries. Production-realistic. Runs in Docker. |

#### Why LangGraph over LangChain?

| | LangChain | LangGraph |
|---|---|---|
| **Mental model** | Linear chain / agent loop | Stateful graph with nodes + edges |
| **State management** | Basic, manual | Explicit, persistent across steps |
| **Branching logic** | Hard to express | Native (conditional edges) |
| **Frame-by-frame loops** | Hacked on top | Built-in cyclic graph support |
| **Fits this problem** | Partially | Naturally |

#### Why not a fine-tuned local VLM?

- No labeled security footage dataset available
- GPU inference setup overhead for a prototype
- Fine-tuning without domain data makes outputs *worse*, not better
- **Report note:** Mention that production deployment would benefit from a fine-tuned model on CCTV footage — shows architectural maturity

---

## 3. Final Tech Stack

| Layer | Tool | Reason |
|---|---|---|
| VLM / Frame Analysis | GPT-4o / Claude API | Best out-of-box accuracy, no infra needed |
| Agent Framework | **LangGraph** | Stateful cyclic graph, native state management |
| Database | **PostgreSQL + pgvector** | SQL + vector search in one, production-realistic |
| Backend | Python (FastAPI) | Lightweight, async-friendly |
| Frontend | React + Tailwind | Simple dashboard for demo |
| Infrastructure | **Docker Compose** | One-command local setup |

---

## 4. Docker Compose Service Layout

```yaml
services:
  postgres:           # PostgreSQL with pgvector extension
  backend:            # FastAPI + LangGraph agent (Python)
  frontend:           # React dashboard (Nginx)
```

All services run locally via `docker compose up`. No external dependencies except the VLM API key.

**Why Docker:**
- Reproducible setup — works the same on any machine
- PostgreSQL + pgvector needs a specific extension; Docker image handles this cleanly (`ankane/pgvector`)
- Makes the demo video setup look professional and production-grade
- Reviewer can run the full system with one command

---

## 5. Scope Clarification for Prototype

This is a **prototype**, not a production CCTV system. The assignment tests:
- Whether you can architect the reasoning pipeline
- Whether the agent uses context intelligently over time
- Quality of documentation and design decisions

You do **not** need:
- Real computer vision or re-identification models
- Actual drone video feed
- GPU inference
