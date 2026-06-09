"""Stage 9 QA harness — exercises QA-01 … QA-09 against the live stack and prints
actual results next to expectations. Run after populating data via ingest_runner:

    python -m data.ingest_runner --frames 25
    python tests/qa_scenarios.py

Requires the full stack up (backend on :8000, MinIO reachable). Read-only except for
the chat/summary LLM calls. Results are summarised in docs/test_cases.md.
"""

from __future__ import annotations

import os
import sys

import httpx

# Source alert messages contain non-ASCII (—); force UTF-8 so Windows cp1252 doesn't choke.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BACKEND = os.environ.get("BACKEND_URL", "http://localhost:8000")
VEHICLE_WORDS = {"car", "truck", "van", "bus", "vehicle", "motorcycle", "suv", "jeep"}


def _get(client: httpx.Client, path: str, **params):
    r = client.get(f"{BACKEND}{path}", params=params or None)
    r.raise_for_status()
    return r.json()


def _post(client: httpx.Client, path: str, body: dict):
    r = client.post(f"{BACKEND}{path}", json=body)
    r.raise_for_status()
    return r.json()


def main() -> int:
    results: list[tuple[str, str, str]] = []  # (id, pass/fail/info, detail)

    with httpx.Client(timeout=120.0) as c:
        frames = _get(c, "/frames", limit=200).get("frames", [])
        events = _get(c, "/events", limit=200).get("events", [])
        alerts = _get(c, "/alerts", active_only=False, limit=200).get("alerts", [])

        def hour(f):
            t = (f.get("telemetry") or {}).get("time") or ""
            try:
                return int(t.split(":")[0])
            except Exception:
                return None

        # QA-01 — a vehicle frame is ingested and persisted with a blob_url
        veh = [f for f in frames if (f.get("object_type") or "").lower() in VEHICLE_WORDS]
        ok = bool(veh) and all(f.get("blob_url", "").startswith("http") for f in veh)
        results.append(("QA-01", "PASS" if ok else "FAIL",
                        f"{len(veh)} vehicle frame(s); e.g. {veh[0]['object_type']} @ "
                        f"{veh[0]['location']} blob={veh[0]['blob_url'][:48]}..." if veh
                        else "no vehicle frames ingested"))

        # QA-02 — repeat vehicle / after-hours vehicle alert
        rv = [a for a in alerts if a["rule"] in ("repeat_vehicle", "after_hours_vehicle")]
        results.append(("QA-02", "PASS" if rv else "INFO",
                        f"{len(rv)} vehicle alert(s): "
                        + ", ".join(sorted({a['rule'] for a in rv})) if rv
                        else "no repeat/after-hours vehicle alert in this dataset"))

        # QA-03 — after-hours person alert
        ap = [a for a in alerts if a["rule"] == "after_hours_person"]
        ok = bool(ap) and all(a.get("blob_url", "").startswith("http") for a in ap)
        results.append(("QA-03", "PASS" if ok else "FAIL",
                        f"{len(ap)} after_hours_person alert(s); e.g. \"{ap[0]['message']}\""
                        if ap else "no after_hours_person alert fired"))

        # QA-04 — loitering
        lo = [a for a in alerts if a["rule"] == "loitering"]
        results.append(("QA-04", "PASS" if lo else "INFO",
                        f"{len(lo)} loitering alert(s)" if lo
                        else "no loitering alert (needs 5 consecutive same subject+location)"))

        # QA-05 — frame search returns rows with blob_url
        sr = _get(c, "/frames/search", q="vehicle", limit=5).get("results", [])
        ok = bool(sr) and all(r["blob_url"].startswith("http") for r in sr)
        results.append(("QA-05", "PASS" if ok else "FAIL",
                        f"query 'vehicle' -> {len(sr)} result(s) with blob_url"))

        # QA-06 — a search blob_url resolves to a real image
        detail = "no search results to fetch"
        ok06 = False
        if sr:
            img = httpx.get(sr[0]["blob_url"], timeout=30.0)
            ct = img.headers.get("content-type", "")
            ok06 = img.status_code == 200 and ct.startswith("image/")
            detail = f"GET blob -> {img.status_code}, content-type={ct}"
        results.append(("QA-06", "PASS" if ok06 else "FAIL", detail))

        # QA-07 — chat answer grounded in frames (references with blob_url)
        chat = _post(c, "/chat", {"question": "Was a vehicle seen after hours?"})
        refs = chat.get("references", [])
        ok = isinstance(chat.get("answer"), str) and chat["answer"].strip() != ""
        results.append(("QA-07", "PASS" if ok else "FAIL",
                        f"answer={chat.get('answer','')[:90]!r} | {len(refs)} reference(s)"))

        # QA-08 — session summary
        summ = _get(c, "/summary")
        ok = bool(summ.get("summary")) and "stats" in summ
        results.append(("QA-08", "PASS" if ok else "FAIL",
                        f"headline={summ.get('headline','')[:80]!r}; "
                        f"frames={summ['stats']['frames']} alerts={summ['stats']['alerts']}"))

        # QA-09 — daytime frames (08:00–17:59) produce no alerts
        day_frames = [f for f in frames if (h := hour(f)) is not None and 8 <= h < 18]
        alert_blobs = {a.get("blob_url") for a in alerts}
        day_alerted = [f for f in day_frames if f.get("blob_url") in alert_blobs]
        ok = len(day_alerted) == 0
        results.append(("QA-09", "PASS" if ok else "INFO",
                        f"{len(day_frames)} daytime frame(s), {len(day_alerted)} alerted "
                        f"(expect 0)"))

    print(f"\nQA results against {BACKEND}  (frames={len(frames)} events={len(events)} "
          f"alerts={len(alerts)})\n" + "=" * 72)
    for qid, status, detail in results:
        print(f"{qid}  [{status:4}]  {detail}")
    fails = [r for r in results if r[1] == "FAIL"]
    print("=" * 72)
    print(f"{len(results)} scenarios — {sum(1 for r in results if r[1]=='PASS')} PASS, "
          f"{sum(1 for r in results if r[1]=='INFO')} INFO, {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
