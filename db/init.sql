-- Stage 1: storage schema for the Drone Security Analyst Agent.
-- Auto-run by the postgres container on first startup via
-- /docker-entrypoint-initdb.d/init.sql (mounted in docker-compose.yml).

-- pgvector for embedding similarity search.
CREATE EXTENSION IF NOT EXISTS vector;

-- Indexed frame store: metadata + blob reference + vector embedding.
CREATE TABLE IF NOT EXISTS frames (
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
    telemetry       JSONB,                  -- full telemetry snapshot
    clip_id         TEXT                    -- groups frames sampled from one uploaded video
);

-- Human-readable event log.
CREATE TABLE IF NOT EXISTS events (
    id          SERIAL PRIMARY KEY,
    event_type  TEXT NOT NULL,              -- 'vehicle_entry', 'loitering', etc.
    description TEXT NOT NULL,
    severity    TEXT DEFAULT 'info',        -- 'info', 'warning', 'critical'
    frame_id    TEXT REFERENCES frames(frame_id),
    blob_url    TEXT,                       -- denormalised for fast alert display
    clip_id     TEXT,                       -- clip this event was raised for (video-level flow)
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Active alert registry.
CREATE TABLE IF NOT EXISTS alerts (
    id           SERIAL PRIMARY KEY,
    rule         TEXT NOT NULL,             -- which alert rule fired
    message      TEXT NOT NULL,
    severity     TEXT NOT NULL,
    blob_url     TEXT,                      -- frame that triggered the alert
    clip_id      TEXT,                      -- clip this alert was raised for (video-level flow)
    triggered_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at  TIMESTAMPTZ,
    metadata     JSONB
);

-- Per-video verdict: one row per ingested clip, holding the clip-level action judgment.
CREATE TABLE IF NOT EXISTS clips (
    clip_id                 TEXT PRIMARY KEY,
    filename                TEXT,
    frame_count             INTEGER,
    action_summary          TEXT,
    verdict                 TEXT,           -- 'alert' or 'normal'
    severity                TEXT,
    narrative               TEXT,
    representative_blob_url  TEXT,           -- a frame the operator should look at first
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

-- Fast vector similarity index.
-- HNSW (not ivfflat): ivfflat must be built AFTER data exists to train its centroids,
-- so an ivfflat index created here on the empty table returns no/incomplete results.
-- HNSW needs no training and stays correct as rows are inserted incrementally.
CREATE INDEX IF NOT EXISTS frames_embedding_hnsw
    ON frames USING hnsw (embedding vector_cosine_ops);

-- Fast SQL filters.
CREATE INDEX IF NOT EXISTS frames_location_timestamp_idx
    ON frames (location, timestamp);
CREATE INDEX IF NOT EXISTS frames_object_type_idx
    ON frames (object_type);
CREATE INDEX IF NOT EXISTS frames_clip_id_idx
    ON frames (clip_id);
