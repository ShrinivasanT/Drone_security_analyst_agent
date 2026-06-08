"""FastAPI application entrypoint.

Stage 3 scope: CORS, a lifespan that stands up the async DB engine and a MinIO
(boto3) client, a health check, and the stub ``POST /ingest`` route. Later stages
add the remaining routes (events, alerts, frames/search, summary, chat) and swap the
ingest stub for the real LangGraph agent.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

import boto3
from botocore.config import Config
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent import db
from backend.routes import alerts, chat, events, frames, ingest, ingest_video, summary

load_dotenv()


def _make_minio_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("MINIO_ENDPOINT", "http://minio:9000"),
        aws_access_key_id=os.environ.get("MINIO_ACCESS_KEY", "minioadmin"),
        aws_secret_access_key=os.environ.get("MINIO_SECRET_KEY", "minioadmin"),
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: DB engine + connectivity check, idempotent migration, MinIO client.
    db.init_db()
    await db.ping()
    await db.migrate()
    app.state.minio = _make_minio_client()
    app.state.minio_bucket = os.environ.get("MINIO_BUCKET", "drone-frames")
    try:
        yield
    finally:
        await db.close_db()


app = FastAPI(title="Drone Security Analyst Agent", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest.router)
app.include_router(ingest_video.router)
app.include_router(events.router)
app.include_router(alerts.router)
app.include_router(frames.router)
app.include_router(summary.router)
app.include_router(chat.router)


@app.get("/health")
async def health() -> dict[str, bool]:
    return {"ok": await db.ping()}
