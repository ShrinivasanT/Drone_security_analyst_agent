# Datasets & synthetic telemetry

The agent does not consume a live drone feed. It **samples frames from pre-recorded
surveillance footage** to simulate one, and **fabricates telemetry** per sampled frame.
This document explains the dataset choice, sampling cadence, and how telemetry is derived.

> A focused, operations-oriented companion to this file —
> [video_sources.md](video_sources.md) — covers the exact local paths and re-download
> steps. This document is the *rationale*.

---

## Source dataset

**UCF-Crime — "Normal Videos for Event Recognition"** (~1.1 GB, 49+ clips)

- **Source:** <https://www.crcv.ucf.edu/projects/real-world/> (UCF Center for Research in
  Computer Vision).
- **Why this dataset:**
  - Well-known, publicly available CCTV/surveillance benchmark — appropriate domain for a
    security analyst (fixed/overhead cameras, parking lots, streets, building entrances).
  - The **"normal" subset** contains untreated ambient scenes with **no staged incidents**,
    so the alert pipeline is exercised by genuine activity (people walking, vehicles
    parking) rather than by the dataset's own crime labels. This is a more honest test of
    the agent's reasoning than feeding it pre-labelled anomalies.
  - Enough clips (49+) and variety to produce a diverse frame set across many runs.
- **Not committed to git:** the clips are large binaries and are `.gitignore`d. Re-download
  from the project page and place under
  `videos/Normal_Videos_for_Event_Recognition/...` so the path matches `VIDEO_SOURCE_DIR`.

> The top-level `videos/` directory (not `data/videos/`) avoids a case-insensitive
> filesystem collision with the lowercase `data/` Python package.

---

## Sampling

Implemented in [../data/video_loader.py](../data/video_loader.py) via OpenCV
(`cv2.VideoCapture`).

- **One frame every 2 s of video-time** (default, `VIDEO_SAMPLE_INTERVAL_SECONDS`).
  - A real patrol drone transmits periodic snapshots, not full-FPS video.
  - 2 s ≈ 30 sampled frames per minute of source — enough variety to exercise the alert
    pipeline without burning VLM budget on near-duplicate consecutive frames.
- Each sampled frame is JPEG-encoded to bytes — the same shape blob storage and the agent
  expect.
- `ingest_runner` gathers frames across as many clips as needed (sorted) until the
  requested frame count is reached.

---

## Synthetic telemetry

The dataset has no GPS, time, or platform metadata, so telemetry is fabricated per sampled
frame. Generation is **seeded** (default `42`) so a given clip + interval + seed yields
identical telemetry every run — essential for reproducible QA.

| Field      | Derivation                                                                         |
| ---------- | ---------------------------------------------------------------------------------- |
| `time`     | Linearly spread across a 24 h patrol cycle: frame `i` of `N` → `i·(24·60)/N` min past midnight. Guarantees every run produces both daytime and after-hours frames. |
| `location` | Cycles six fixed waypoints: `main_gate`, `parking_lot`, `warehouse_a`, `perimeter_north`, `perimeter_east`, `loading_dock`. |
| `lat`/`lng`| Anchored per waypoint, with ±0.0002° jitter so consecutive same-waypoint frames look distinct without leaving the site footprint. |
| `altitude` | Uniform random 10–30 m.                                                            |

### Why time is spread across 24 h

Mapping frame position → time-of-day is what makes the after-hours rules demonstrable from
ambient "normal" footage. A short clip sampled into N frames will reliably include frames
mapped past 18:00 / before 08:00, triggering `after_hours_person` / `after_hours_vehicle`
when the VLM detects a subject there — even though the source footage carries no real
timestamps.

---

## Reproducing a QA dataset

```bash
# 25 frames across all clips, deterministic telemetry (seed 42)
python -m data.ingest_runner --frames 25 --interval 2.0

# a single clip
python -m data.ingest_runner --clips Normal_Videos_015_x264.mp4 -n 20
```

Standalone frame-sampling check (no backend needed):

```bash
python -m data.video_loader \
  --video "videos/Normal_Videos_for_Event_Recognition/Normal_Videos_for_Event_Recognition/Normal_Videos_015_x264.mp4" \
  --interval 2 --n 5 --out tmp_frames
```

---

## Secondary image set

A small set of still images also exists under `videos/images/` for quick single-frame
upload testing through the dashboard's **Ingest Frame** panel. These are convenience
samples and not part of the primary video-sourced pipeline.
