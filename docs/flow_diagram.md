# Drone Security Analyst Agent — Flow Diagram

End-to-end data flow, from source clip through the LangGraph agent to the operator
dashboard. Conditional routing inside the agent (`normal` / `log` / `alert`) mirrors
`agent/graph.py`.

## End-to-end pipeline

```mermaid
flowchart TD
    subgraph INGEST["🎞️ Ingestion (host)"]
        V[".mp4 CCTV clips"] -->|"video_loader.py<br/>OpenCV sampling"| F["(frame_bytes,<br/>synthetic telemetry)"]
        F -->|"ingest_runner.py"| BS["blob_store.py"]
        BS -->|PUT| MINIO[("MinIO<br/>drone-frames bucket")]
        MINIO -->|returns blob_url| POST["POST /ingest<br/>{ blob_url, telemetry }"]
    end

    POST --> API

    subgraph API["⚙️ FastAPI backend — LangGraph agent (agent/graph.py)"]
        direction TB
        N1["ingest_frame"] --> N2["analyze_frame<br/>(VLM · Groq Llama-4 Scout)"]
        N2 --> N3["query_history<br/>(pgvector semantic recall)"]
        N3 --> N4["reason_decide<br/>(rule engine + LLM narrative)"]

        N4 -->|route: normal| N7
        N4 -->|route: log| N5
        N4 -->|route: alert| N5

        N5["log_event"] -->|route: log / normal| N7
        N5 -->|route: alert| N6["trigger_alert"]
        N6 --> N7["update_state<br/>(persist frame + embedding)"]
        N7 --> ENDN(["END"])
    end

    N7 --> PG[("PostgreSQL + pgvector<br/>frames / events / alerts")]
    PG --> DASH

    subgraph DASH["🖥️ React dashboard (frontend/)"]
        direction LR
        D1["Telemetry feed"]
        D2["Event log"]
        D3["Alert banner"]
        D4["Frame search"]
        D5["Session summary"]
        D6["RAG Q&A chatbot"]
    end

    DASH -.->|"polls /frames /events /alerts<br/>/summary /chat"| API
```

## Agent routing detail (`reason_decide` → END)

```mermaid
flowchart LR
    RD["reason_decide"] -->|normal| US["update_state → END"]
    RD -->|log| LE["log_event"]
    RD -->|alert| LE
    LE -->|log / normal| US
    LE -->|alert| TA["trigger_alert"]
    TA --> US
```

- **normal** — no event/alert; frame is persisted only.
- **log** — `log_event` records the event, then persist.
- **alert** — `log_event` **and** `trigger_alert` fire (rules: after-hours person/vehicle,
  loitering, repeat vehicle, restricted zone), then persist.
