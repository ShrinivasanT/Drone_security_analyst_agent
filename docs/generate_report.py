"""Generate the Drone Security Analyst Agent project report (PDF).

Builds a multi-section report with architecture/flow diagrams drawn natively in
ReportLab, populated with real project data and QA results.

    python docs/generate_report.py
    -> docs/Drone_Security_Analyst_Report.pdf
"""

from __future__ import annotations

import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Polygon
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
    KeepTogether, ListFlowable, ListItem,
)

OUT = os.path.join(os.path.dirname(__file__), "Drone_Security_Analyst_Report.pdf")

# ---------------------------------------------------------------------------- #
# Palette
# ---------------------------------------------------------------------------- #
NAVY = colors.HexColor("#1f2a44")
SLATE = colors.HexColor("#334155")
ACCENT = colors.HexColor("#0e7490")
LIGHT = colors.HexColor("#e2e8f0")
BOXBG = colors.HexColor("#f1f5f9")
ALERTBG = colors.HexColor("#fee2e2")
ALERTLINE = colors.HexColor("#b91c1c")
OKBG = colors.HexColor("#dcfce7")
GREY = colors.HexColor("#64748b")

# ---------------------------------------------------------------------------- #
# Styles
# ---------------------------------------------------------------------------- #
styles = getSampleStyleSheet()


def _style(name, **kw):
    if name in styles:
        s = styles[name]
        for k, v in kw.items():
            setattr(s, k, v)
        return s
    return ParagraphStyle(name, **kw)


body = _style("BodyText", fontName="Helvetica", fontSize=10, leading=15,
              alignment=TA_JUSTIFY, textColor=SLATE, spaceAfter=6)
h1 = ParagraphStyle("H1", fontName="Helvetica-Bold", fontSize=16, leading=20,
                    textColor=NAVY, spaceBefore=14, spaceAfter=8)
h2 = ParagraphStyle("H2", fontName="Helvetica-Bold", fontSize=12.5, leading=16,
                    textColor=ACCENT, spaceBefore=10, spaceAfter=5)
small = ParagraphStyle("Small", fontName="Helvetica", fontSize=8.5, leading=12,
                       textColor=GREY)
caption = ParagraphStyle("Cap", fontName="Helvetica-Oblique", fontSize=8.5,
                         leading=11, textColor=GREY, alignment=TA_CENTER, spaceAfter=8)
code = ParagraphStyle("Code", fontName="Courier", fontSize=8.5, leading=12,
                      textColor=colors.HexColor("#0f172a"),
                      backColor=colors.HexColor("#f8fafc"), borderPadding=5,
                      spaceBefore=4, spaceAfter=8)
bullet = ParagraphStyle("Bullet", parent=body, spaceAfter=3)


def P(t, s=body):
    return Paragraph(t, s)


def bullets(items, s=bullet):
    return ListFlowable(
        [ListItem(Paragraph(i, s), leftIndent=6, value="•") for i in items],
        bulletType="bullet", bulletColor=ACCENT, leftIndent=12, bulletFontSize=8,
    )


# ---------------------------------------------------------------------------- #
# Diagram helpers
# ---------------------------------------------------------------------------- #
def _box(d, x, y, w, h, text, fill=BOXBG, line=SLATE, tcol=NAVY, fs=8.5, bold=False):
    d.add(Rect(x, y, w, h, fillColor=fill, strokeColor=line, strokeWidth=0.8, rx=4, ry=4))
    font = "Helvetica-Bold" if bold else "Helvetica"
    lines = text.split("\n")
    total = len(lines) * (fs + 2)
    cy = y + h / 2 + total / 2 - fs
    for ln in lines:
        d.add(String(x + w / 2, cy, ln, fontName=font, fontSize=fs,
                     fillColor=tcol, textAnchor="middle"))
        cy -= fs + 2


def _arrow(d, x1, y1, x2, y2, col=ACCENT, label=None):
    d.add(Line(x1, y1, x2, y2, strokeColor=col, strokeWidth=1.1))
    import math
    ang = math.atan2(y2 - y1, x2 - x1)
    ah = 5
    d.add(Polygon([
        x2, y2,
        x2 - ah * math.cos(ang - 0.4), y2 - ah * math.sin(ang - 0.4),
        x2 - ah * math.cos(ang + 0.4), y2 - ah * math.sin(ang + 0.4),
    ], fillColor=col, strokeColor=col))
    if label:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        d.add(String(mx + 4, my + 2, label, fontName="Helvetica", fontSize=7,
                     fillColor=GREY, textAnchor="start"))


def architecture_diagram():
    """End to end data plane and backend flow, top to bottom."""
    W, H = 460, 360
    d = Drawing(W, H)
    cx = W / 2
    bw, bh = 230, 30
    x = cx - bw / 2
    rows = [
        ("Source CCTV clips (.mp4)", BOXBG),
        ("video_loader.py: OpenCV sampling + synthetic telemetry", BOXBG),
        ("blob_store.py -> MinIO (drone-frames), returns blob_url", BOXBG),
        ("POST /ingest  { blob_url, telemetry }", LIGHT),
        ("FastAPI + LangGraph agent (7 nodes)", colors.HexColor("#cffafe")),
        ("PostgreSQL + pgvector   |   MinIO blobs", BOXBG),
        ("React + Tailwind operator dashboard", BOXBG),
    ]
    gap = (H - bh) / (len(rows) - 1)
    ys = [H - bh - i * gap for i in range(len(rows))]
    for (txt, fill), y in zip(rows, ys):
        bold = "LangGraph" in txt or "POST /ingest" in txt
        _box(d, x, y, bw, bh, txt, fill=fill, bold=bold, fs=8)
    for i in range(len(rows) - 1):
        _arrow(d, cx, ys[i], cx, ys[i + 1] + bh)
    return d


def agent_flow_diagram():
    """LangGraph node flow with conditional routing."""
    W, H = 470, 430
    d = Drawing(W, H)
    cx = W / 2
    bw, bh = 250, 26
    x = cx - bw / 2
    nodes = [
        "ingest_frame  (validate + seed memory)",
        "analyze_frame  (VLM -> structured JSON)",
        "query_history  (pgvector + SQL recency)",
        "reason_decide  (rules + LLM narrative)",
    ]
    top = H - bh
    ys = [top - i * 46 for i in range(len(nodes))]
    for txt, y in zip(nodes, ys):
        _box(d, x, y, bw, bh, txt, fs=8, bold="reason_decide" in txt,
             fill=colors.HexColor("#cffafe") if "reason_decide" in txt else BOXBG)
    for i in range(len(nodes) - 1):
        _arrow(d, cx, ys[i], cx, ys[i + 1] + bh)

    # Branch row: log_event (left) and trigger_alert (centre-right)
    by = ys[-1] - 74
    sw = 140
    log_x = cx - sw - 18
    alert_x = cx + 18
    _box(d, log_x, by, sw, bh, "log_event (events row)", fill=BOXBG, fs=8)
    _box(d, alert_x, by, sw, bh, "trigger_alert (alerts row)", fill=ALERTBG,
         line=ALERTLINE, tcol=ALERTLINE, fs=8)
    # reason_decide -> log_event (log or alert)
    _arrow(d, cx - 40, ys[-1], log_x + sw / 2, by + bh, label="log / alert")
    # log_event -> trigger_alert (alert only)
    _arrow(d, log_x + sw, by + bh / 2, alert_x, by + bh / 2, col=ALERTLINE, label="alert")

    persist_y = by - 62
    _box(d, x, persist_y, bw, bh, "update_state  (persist frame + embedding)",
         fill=LIGHT, fs=8, bold=True)
    # log_event -> update_state ; trigger_alert -> update_state
    _arrow(d, log_x + sw / 2, by, cx - 25, persist_y + bh)
    _arrow(d, alert_x + sw / 2, by, cx + 25, persist_y + bh, col=ALERTLINE)

    # normal route: elbow down the right-hand lane, clear of the alert box
    rx = W - 26
    ry0 = ys[-1] + bh / 2          # mid-height of reason_decide
    ru = persist_y + bh / 2         # mid-height of update_state
    d.add(Line(x + bw, ry0, rx, ry0, strokeColor=ACCENT, strokeWidth=1.1))
    d.add(Line(rx, ry0, rx, ru, strokeColor=ACCENT, strokeWidth=1.1))
    _arrow(d, rx, ru, x + bw, ru)
    d.add(String(rx - 4, (ry0 + ru) / 2, "normal", fontName="Helvetica", fontSize=7,
                 fillColor=GREY, textAnchor="end"))

    _box(d, cx - 30, persist_y - 46, 60, bh, "END", fill=OKBG, fs=8, bold=True)
    _arrow(d, cx, persist_y, cx, persist_y - 46 + bh)
    return d


# ---------------------------------------------------------------------------- #
# Page furniture
# ---------------------------------------------------------------------------- #
def _footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(LIGHT)
    canvas.setLineWidth(0.6)
    canvas.line(20 * mm, 14 * mm, A4[0] - 20 * mm, 14 * mm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GREY)
    canvas.drawString(20 * mm, 9 * mm, "Drone Security Analyst Agent")
    canvas.drawRightString(A4[0] - 20 * mm, 9 * mm, f"Page {doc.page}")
    canvas.restoreState()


def kv_table(rows, col_widths):
    t = Table(rows, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("TEXTCOLOR", (0, 1), (-1, -1), SLATE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BOXBG]),
        ("GRID", (0, 0), (-1, -1), 0.4, LIGHT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


# ---------------------------------------------------------------------------- #
# Content
# ---------------------------------------------------------------------------- #
def build():
    doc = SimpleDocTemplate(
        OUT, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=20 * mm,
        title="Drone Security Analyst Agent - Project Report",
        author="Shrinivasan T",
    )
    s = []

    # ---- Title ----
    s.append(Spacer(1, 40))
    s.append(Paragraph("Drone Security Analyst Agent",
                       ParagraphStyle("T", fontName="Helvetica-Bold", fontSize=26,
                                      textColor=NAVY, alignment=TA_CENTER, leading=30)))
    s.append(Spacer(1, 8))
    s.append(Paragraph("Autonomous frame understanding, contextual reasoning, and alerting "
                       "over a simulated drone surveillance feed",
                       ParagraphStyle("ST", fontName="Helvetica", fontSize=12,
                                      textColor=ACCENT, alignment=TA_CENTER, leading=16)))
    s.append(Spacer(1, 30))

    # ---- 1. Overview ----
    s.append(P("1. Overview and Approach", h1))
    s.append(P("The system acts as an autonomous security analyst for an aerial patrol feed. "
               "It does not consume a live drone stream. Instead it samples frames from "
               "pre recorded CCTV footage and pairs each frame with synthetic telemetry "
               "(time of day, patrol waypoint, GPS, altitude) to simulate one. Every layer "
               "below blob storage is source agnostic, so swapping the simulated feed for a "
               "real stream later touches only the ingestion edge."))
    s.append(P("The problem was broken into four concerns, each independently runnable and "
               "verifiable before moving on: a data plane that produces frames and telemetry, "
               "a perception layer that turns an image into structured facts, a reasoning "
               "layer that decides whether a frame is routine or worth an alert, and an "
               "operator surface that makes all of it visible. The build followed an ordered "
               "sequence so that a live API existed early and every later stage integrated "
               "against a running system rather than isolated files."))
    s.append(P("The guiding design decision was to keep alert firing deterministic and the "
               "language model responsible only for description and narrative. A rule engine "
               "decides whether an alert fires, which makes behaviour reproducible and "
               "testable, while the model supplies the human readable situational summary. "
               "The model cannot suppress a rule that has fired."))

    # ---- 2. Framework and tech stack ----
    s.append(P("2. Framework and Technology Stack", h1))
    s.append(P("The stack favours mature, OpenAI compatible, container friendly components so "
               "the whole system runs from a single compose file.", body))
    s.append(kv_table([
        ["Layer", "Technology", "Role"],
        ["Agent framework", "LangGraph 0.2", "Stateful graph of reasoning nodes with conditional routing"],
        ["Backend API", "FastAPI + Uvicorn", "Async REST surface and agent invocation"],
        ["Database", "PostgreSQL 15 + pgvector", "Frames, events, alerts, and 1536 dim vector search"],
        ["Blob storage", "MinIO (S3 API, boto3)", "Frame images, served to the browser by URL"],
        ["Vision model", "Groq Llama 4 Scout 17B", "Frame to structured JSON description"],
        ["Reasoning model", "Groq Llama 3.3 70B", "Situational narrative and noteworthiness"],
        ["Chat reasoning", "OpenAI gpt 4o mini", "Q and A reasoning loop with a vision tool"],
        ["Embeddings", "OpenAI text embedding 3 small", "Semantic search, local hashing fallback"],
        ["Frame sampling", "OpenCV (headless)", "Sample frames from clips at an interval"],
        ["Frontend", "React 18 + Tailwind", "Live operator dashboard"],
        ["ORM / DB access", "SQLAlchemy 2 async + asyncpg", "Non blocking database calls"],
        ["Testing", "pytest + httpx", "Unit, agent, and live API tests"],
    ], [95, 150, 175]))

    s.append(Spacer(1, 6))
    s.append(P("Why these choices", h2))
    s.append(bullets([
        "<b>LangGraph</b> models the per frame cycle as an explicit graph. Conditional edges "
        "express the normal, log, and alert routes cleanly, and the typed state object keeps "
        "each node small and independently testable.",
        "<b>pgvector inside PostgreSQL</b> avoids running a separate vector database. The same "
        "store holds structured rows and embeddings, so history retrieval and semantic search "
        "are one SQL dialect.",
        "<b>MinIO</b> gives an S3 compatible object store locally. Frame URLs are stored on "
        "each record, so the browser renders images directly without proxying through the API.",
        "<b>Groq for vision and reasoning</b> was chosen for low latency on the Llama 4 and "
        "Llama 3.3 models through an OpenAI compatible API, which let a single client "
        "abstraction serve both Groq and OpenAI with only a base URL and model name change.",
        "<b>OpenAI gpt 4o mini for the chatbot</b> keeps the interactive Q and A reasoning "
        "loop cheap while still supporting tool calling, which the loop uses to invoke the "
        "vision model on demand.",
        "<b>Deterministic rule engine</b> is deliberately separate from the model so security "
        "behaviour is reproducible run to run and can be unit tested without an API call.",
    ]))

    s.append(PageBreak())

    # ---- 3. System design ----
    s.append(P("3. System Design and Reasoning Flow", h1))
    s.append(P("A single POST to the ingest endpoint runs one full reasoning cycle. The graph "
               "is wired with conditional edges so that a routine frame is simply persisted, "
               "a noteworthy frame is logged, and a rule violating frame is logged and "
               "alerted before persistence.", body))
    s.append(KeepTogether([agent_flow_diagram(),
                           Paragraph("Figure 1. LangGraph agent. The route from reason_decide "
                                     "is normal, log, or alert.", caption)]))

    s.append(P("Node responsibilities", h2))
    s.append(bullets([
        "<b>ingest_frame</b> validates the frame URL and seeds working state from a process "
        "level session store that holds the rolling window of recent frames and the current "
        "session's events and alerts.",
        "<b>analyze_frame</b> fetches the image bytes from blob storage, base64 encodes them, "
        "and asks the vision model for a fixed schema: object type, location, action, "
        "clothing, colour, confidence, and a one sentence description.",
        "<b>query_history</b> embeds the description and runs two retrievals in parallel, a "
        "vector similarity search for similar past frames and a SQL filter for recent frames "
        "at the same waypoint, which feeds loitering and repeat detection.",
        "<b>reason_decide</b> runs the rule engine for the firing decision and the reasoning "
        "model for the narrative, then emits the route. If the model call fails it falls back "
        "to a deterministic summary so the pipeline never breaks.",
        "<b>log_event</b> and <b>trigger_alert</b> write the events and alerts rows, each "
        "carrying the triggering frame URL for the dashboard.",
        "<b>update_state</b> persists the frame with its embedding and telemetry, advances the "
        "session memory, and returns the API result.",
    ]))

    s.append(P("Memory model", h2))
    s.append(P("Graph state is per invocation, but the agent needs memory across frames. Two "
               "tiers handle this. A process singleton session store carries the rolling "
               "window of recent frame summaries and the current session's events and alerts, "
               "which drives cross frame rules such as loitering and repeat vehicle. "
               "PostgreSQL with pgvector holds durable history that query_history reads back "
               "on every frame."))

    s.append(P("Alert rules", h2))
    s.append(P("Business hours default to 08:00 to 18:00. Severity is attached per rule.", body))
    s.append(kv_table([
        ["Rule", "Severity", "Condition"],
        ["after_hours_person", "critical", "Person detected outside business hours"],
        ["after_hours_vehicle", "high", "Vehicle detected outside business hours"],
        ["loitering", "high", "Same object and location across 5 or more consecutive frames"],
        ["repeat_vehicle", "warning", "Same vehicle descriptor seen 3 or more times this session"],
        ["restricted_zone", "critical", "Any subject inside a configured restricted location"],
    ], [130, 70, 220]))

    s.append(PageBreak())

    # ---- 4. Validation ----
    s.append(P("4. Validation and Functionality Testing", h1))
    s.append(P("Validation runs at three levels: unit and agent tests, a live API test suite, "
               "and a scenario harness that drives real video sourced frames through the "
               "running system and checks operator facing behaviour."))

    s.append(P("Automated test suites", h2))
    s.append(bullets([
        "<b>Vision extraction test</b> asserts the analyze step returns the full schema with "
        "valid types and a usable embedding vector.",
        "<b>Agent pipeline test</b> runs a full cycle end to end and checks that frames, "
        "events, and alerts are written with a valid frame URL and embedding.",
        "<b>API test</b> exercises every REST endpoint against the live backend and asserts "
        "that frame URLs are present in search results and resolve to real images.",
    ]))
    s.append(P("All nine automated tests pass against the running stack.", body))

    s.append(P("Dynamic input and emergency response scenarios", h2))
    s.append(P("Twenty five frames were sampled from the source clips with deterministic "
               "seeded telemetry and driven through the live agent. Because the synthetic "
               "time of day is spread across a full 24 hour cycle, a single run produces both "
               "routine daytime frames and after hours frames, which is what exercises the "
               "emergency response path. The run produced 22 alert routes, 2 normal, and 1 "
               "log, firing after hours vehicle 10 times, after hours person 8 times, and "
               "repeat vehicle 8 times across 30 total frames in the database."))

    s.append(P("The scenario harness then checked nine cases. Result: 7 pass, 2 informational, "
               "0 fail. The two informational cases are documented and expected behaviours of "
               "the dataset rather than defects.", body))
    s.append(kv_table([
        ["Case", "Scenario", "Outcome"],
        ["QA-01", "Vehicle frame persisted with URL", "Pass, 20 vehicle frames, all with URLs"],
        ["QA-02", "Repeat or after hours vehicle alert", "Pass, 18 vehicle alerts"],
        ["QA-03", "After hours pedestrian alert", "Pass, 8 alerts, e.g. person at loading_dock 04:48"],
        ["QA-04", "Loitering across 5 frames", "Info, rule verified directly, see note"],
        ["QA-05", "Frame search returns images", "Pass, query returns rows with URLs"],
        ["QA-06", "Search image is fetchable", "Pass, HTTP 200, image/jpeg from MinIO"],
        ["QA-07", "Chat answer grounded in frames", "Pass, answer cites a specific frame"],
        ["QA-08", "Session summary generated", "Pass, summary over 30 frames and 26 alerts"],
        ["QA-09", "Normal daytime activity", "Info, daytime alerts are repeat_vehicle by design"],
    ], [50, 195, 175]))
    s.append(Spacer(1, 4))
    s.append(P("On QA-04, the loitering rule does not fire from the ingest run because the "
               "synthetic telemetry cycles the patrol waypoint on every frame, so no five "
               "consecutive same location frames occur. The rule itself was verified by direct "
               "evaluation with a constructed five frame window, which produced a loitering "
               "alert as expected. On QA-09, several daytime frames do raise alerts, but those "
               "are repeat_vehicle, which is intentionally not time gated since a vehicle "
               "making repeated passes is notable at any hour.", small))

    s.append(PageBreak())

    # ---- 5. Results and examples ----
    s.append(P("5. Results, with Examples", h1))
    s.append(P("Frame descriptions, structured by the vision model", h2))
    s.append(P("Each frame is reduced to a fixed schema. Representative outputs from the live "
               "run, exactly as stored:", body))
    s.append(kv_table([
        ["Object", "Location, time", "Description"],
        ["person", "main_gate, 00:00", "A woman and child walk through a mall corridor past storefronts and an orange construction barrier."],
        ["person", "parking_lot, 04:00", "A woman in a white shirt and dark pants walks through a shopping mall corridor."],
        ["car", "perimeter_north, 14:24", "A dark coloured car is driving in the center lane of a busy multi lane road."],
        ["car", "perimeter_east, 15:21", "A white car is driving on a busy road with multiple lanes."],
    ], [60, 110, 250]))

    s.append(P("Agent recommendations and narratives", h2))
    s.append(P("The reasoning model produces a situational assessment per logged frame. Real "
               "examples from the run:", body))
    s.append(P("Critical, after_hours_person: \"A person is walking in the corridor of a "
               "shopping mall, which is a routine activity, but the fact that a person was "
               "detected at the loading dock after hours triggers the after hours person "
               "rule.\"", code))
    s.append(P("Info, person_detected: \"A person, wearing a white shirt and dark pants, is "
               "walking near storefronts in a mall corridor, which appears to be a routine "
               "activity given the location and time.\"", code))

    s.append(P("Session summary, generated over the full run", h2))
    s.append(P("Headline: Multiple after hours vehicle sightings and repeat vehicle alerts "
               "indicate potential security concerns at the perimeter and warehouse areas.", code))
    s.append(P("Summary: The session recorded 26 alerts, with 10 after hours vehicle alerts "
               "and 8 repeat vehicle alerts. The most significant alerts were after hours "
               "vehicle sightings at various locations, including warehouse_a, parking_lot, "
               "and perimeter_east. A pattern of repeated after hours presence was observed, "
               "with multiple vehicles detected at different times.", code))

    s.append(P("Grounded question answering", h2))
    s.append(P("The chatbot retrieves relevant frames, reasons over their metadata, and may "
               "call the vision model on a specific frame when the text index is not enough. "
               "Example exchange from the live system:", body))
    s.append(P("Q: Was a vehicle seen after hours?", code))
    s.append(P("A: Yes, a dark coloured car was seen parked at the main gate at 22:30, which "
               "is after hours. (one frame reference returned)", code))

    s.append(P("Demo video", h2))
    s.append(P("The accompanying demo video walks through the running dashboard with these "
               "results live: the telemetry feed populating as frames arrive, the alert "
               "banner showing the triggering frame for an after hours detection, semantic "
               "frame search rendering thumbnails from stored URLs, the session summary, and "
               "the grounded chatbot. The video files are submitted alongside this report. "
               "Refer to them for the dashboard walkthrough and the per goal narration.", body))

    s.append(PageBreak())

    # ---- 6. Challenges ----
    s.append(P("6. Challenges and Solutions", h1))
    s.append(P("Several issues surfaced during integration and QA. Each is recorded here with "
               "the fix, since they shaped the final design.", body))

    challenges = [
        ("Telemetry feed only showed alerted frames",
         "The live telemetry panel polled the events endpoint, but events are written only "
         "for the log and alert routes. A normal frame with no alert produced no event row, "
         "so uploads with no alert never appeared. The fix added a frames listing endpoint "
         "that returns every ingested frame, and the feed now reads that. The event log panel "
         "keeps reading events, so the two panels have distinct, correct roles."),
        ("Single shot question answering missed visual detail",
         "The first chatbot was a single retrieval and one model call over text metadata "
         "only. Questions needing visual detail not in the index could not be answered. The "
         "fix turned it into a short reasoning loop that can call the vision model on a "
         "specific frame when the metadata is insufficient, then fold the visual findings "
         "into the final answer."),
        ("Provider split for cost and latency",
         "Vision and reasoning run on Groq for speed, while the interactive chatbot reasoning "
         "runs on a cheaper OpenAI mini model and embeddings run on OpenAI. The client "
         "abstraction passes an explicit provider per call so the split holds regardless of "
         "global provider toggles, and embeddings fall back to a local hashing embedder when "
         "no key is present."),
        ("Ingest runner crash on alert counting",
         "The end to end runner aggregated fired rules with a counter, but fired rules are "
         "dictionaries, which are not hashable, so the run crashed on the first alerting "
         "frame. The fix counts by rule name. This was found by QA and is exactly why the "
         "runner is validated against a complete system rather than in isolation."),
        ("Dual MinIO endpoints",
         "The backend container reaches MinIO by its service name, but the browser needs a "
         "host reachable URL. Storing a public endpoint URL on each record, separate from the "
         "internal endpoint used for byte access, lets the API and the browser both resolve "
         "frames correctly."),
        ("Loitering not observable from cycling telemetry",
         "Because the synthetic telemetry cycles the waypoint every frame, the five "
         "consecutive same location condition is never met by an ingest run. Rather than "
         "weaken the rule, this was documented and the rule was verified directly, with a "
         "stationary telemetry mode noted as the way to demonstrate it end to end."),
    ]
    for title, txt in challenges:
        s.append(P(f"<b>{title}</b>", ParagraphStyle("ch", parent=body, spaceAfter=2,
                                                     textColor=NAVY)))
        s.append(P(txt, ParagraphStyle("chb", parent=body, spaceAfter=8)))

    s.append(PageBreak())

    # ---- 7. Future work ----
    s.append(P("7. What Could Be Improved With More Time", h1))
    s.append(P("The current system simulates a feed by sampling recorded clips. With more "
               "time the following directions would raise both realism and quality.", body))

    s.append(P("Live streaming and real time ingestion", h2))
    s.append(bullets([
        "Replace the file sampler with a live capture path using OpenCV VideoCapture on an "
        "RTSP or device stream, so frames are pulled from an actual camera or drone link "
        "rather than from stored files.",
        "Add a streaming ingestion mode that pushes frames as they arrive, with backpressure "
        "and a sampling throttle so the vision model is not overwhelmed at full frame rate.",
        "Stream results to the dashboard over websockets for a true live telecast, replacing "
        "the current polling with server pushed updates and a live video tile alongside the "
        "telemetry feed.",
        "Real platform telemetry from the drone autopilot, replacing the synthetic time and "
        "GPS with genuine values, which also makes the after hours and zone rules act on real "
        "conditions.",
    ]))

    s.append(P("Perception quality", h2))
    s.append(bullets([
        "Fine tune or adapt the vision model on aerial and CCTV imagery if a suitably labelled "
        "dataset is available, since the general model can be uncertain on overhead views and "
        "small distant subjects. Even light domain adaptation on drone footage would improve "
        "object typing and action recognition.",
        "Noise removal and pre processing before the model sees a frame: denoising, "
        "deblurring, low light enhancement, and stabilisation, which directly affect "
        "description quality on real outdoor and night footage.",
        "Temporal smoothing and tracking across frames so the same subject is associated over "
        "time, which would make loitering and repeat detection far more robust than the "
        "current per frame descriptor matching.",
        "De duplication of near identical consecutive frames to save model calls and avoid "
        "repeated alerts for one continuous event.",
    ]))

    s.append(P("Reasoning and operations", h2))
    s.append(bullets([
        "A learned anomaly score to complement the deterministic rules, so subtle unusual "
        "patterns that no single rule captures can still be surfaced for review.",
        "Alert lifecycle management with acknowledgement, resolution, and de duplication so an "
        "operator is not flooded by repeated firings of the same situation.",
        "Confidence aware routing that asks for a second look from the vision model when the "
        "first description is low confidence, rather than acting on an uncertain read.",
        "Evaluation harness with labelled ground truth to measure precision and recall of the "
        "alerts, which the current scenario tests approximate but do not quantify.",
    ]))

    s.append(Spacer(1, 10))
    s.append(P("Summary", h2))
    s.append(P("The delivered system meets its core goal: it understands each frame, reasons "
               "over rolling and historical context, raises reproducible alerts with the "
               "triggering image, and presents everything through a live dashboard and a "
               "grounded question answering interface. The architecture keeps the language "
               "model bounded to perception and narrative while a deterministic engine owns "
               "the security decisions, which is what makes the behaviour testable and the "
               "validation results above meaningful.", body))

    doc.build(s, onFirstPage=_footer, onLaterPages=_footer)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    build()
