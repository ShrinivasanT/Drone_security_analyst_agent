# Source video clips

The Drone Security Analyst Agent does not ingest a real drone feed — it samples frames
from pre-recorded surveillance footage to simulate one, paired with synthetic telemetry
generated per sampled frame in [data/video_loader.py](../data/video_loader.py).

## Source dataset

**UCF-Crime — "Normal Videos for Event Recognition"** (49 clips, ~1.1 GB total)

- Why: well-known publicly available CCTV/surveillance benchmark; the "normal" subset
  gives stable, untreated scenes (no staged incidents) so the agent's alert pipeline is
  exercised by genuine ambient activity rather than by the dataset's own labels.
- Source: <https://www.crcv.ucf.edu/projects/real-world/> (UCF-Crime project page,
  University of Central Florida).
- Local copy:
  `videos/Normal_Videos_for_Event_Recognition/Normal_Videos_for_Event_Recognition/*.mp4`
  (gitignored — too large to commit; re-download from the project page to reproduce).

## Re-downloading

The dataset is distributed by the UCF-CRCV team. From the project page above, follow
the link to UCF-Crime and grab the "Normal Videos for Event Recognition" archive.
Extract it under `videos/` so the path matches `VIDEO_SOURCE_DIR` in your `.env`.
(Top-level `videos/` rather than `data/videos/` because the lowercase `data/`
directory holds the Python package, and on case-insensitive filesystems a
`Data/`-with-capital-D dataset directory would collide with it.)

## Configuration (`.env`)

- `VIDEO_SOURCE_DIR` — directory containing the `.mp4` clips.
- `VIDEO_SAMPLE_INTERVAL_SECONDS` — seconds of video-time between sampled frames
  (default `2.0`).

## Sampling rationale

- **One snapshot every 2 s of video time** (default). A real patrol drone transmits
  periodic snapshots, not full-FPS video — 2 s gives ~30 sampled frames per minute of
  source, which is enough variety to exercise the alert pipeline without burning VLM
  budget on near-duplicate consecutive frames.
- Override with `--interval` on `data/video_loader.py` or via env in later stages.

## Synthetic telemetry

Because the dataset has no GPS, time, or platform metadata, telemetry is fabricated.
Per sampled frame:

- **`time`** — linearly spread across a 24-hour patrol cycle: frame `i` of `N` lands at
  `i * (24*60) / N` minutes past midnight. This guarantees that even a short clip
  produces both daytime and after-hours frames, which is needed to demonstrate the
  "person after hours" and loitering alerts (QA-03).
- **`location`** — cycles through six fixed waypoints (`main_gate`, `parking_lot`,
  `warehouse_a`, `perimeter_north`, `perimeter_east`, `loading_dock`).
- **`lat`/`lng`** — anchored per waypoint; ±0.0002° random jitter so consecutive frames
  at the same waypoint look distinct without leaving the site footprint.
- **`altitude`** — uniformly random between 10–30 m.

The RNG is seeded (default `42`) so a given clip + interval + seed produces identical
telemetry every run — important for reproducible QA scenarios.

## Standalone verification

```
python -m data.video_loader \
    --video "videos/Normal_Videos_for_Event_Recognition/Normal_Videos_for_Event_Recognition/Normal_Videos_015_x264.mp4" \
    --interval 2 \
    --n 5 \
    --out tmp_frames
```

Expected: 5 lines like `frame=00 bytes=XXXXX jpeg=True telemetry={...}`, plus 5 JPEGs
written to `tmp_frames/`.
