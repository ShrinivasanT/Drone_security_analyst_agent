"""Generate the Drone Security Analyst Agent code documentation (PDF).

A code-level companion to the project report: framework, tech stack, module reference,
key implementation details, and how the system's functionality was validated, including
test cases and the dynamic-input and emergency-response scenarios.

    python docs/generate_code_docs.py
    -> docs/Drone_Security_Analyst_Code_Documentation.pdf
"""

from __future__ import annotations

import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
    ListFlowable, ListItem, Preformatted, KeepTogether,
)

OUT = os.path.join(os.path.dirname(__file__),
                   "Drone_Security_Analyst_Code_Documentation.pdf")

# Palette (matches the project report)
NAVY = colors.HexColor("#1f2a44")
SLATE = colors.HexColor("#334155")
ACCENT = colors.HexColor("#0e7490")
LIGHT = colors.HexColor("#e2e8f0")
BOXBG = colors.HexColor("#f1f5f9")
GREY = colors.HexColor("#64748b")
CODEBG = colors.HexColor("#f8fafc")

styles = getSampleStyleSheet()
body = styles["BodyText"]
body.fontName = "Helvetica"; body.fontSize = 10; body.leading = 15
body.alignment = TA_JUSTIFY; body.textColor = SLATE; body.spaceAfter = 6

h1 = ParagraphStyle("H1", fontName="Helvetica-Bold", fontSize=16, leading=20,
                    textColor=NAVY, spaceBefore=14, spaceAfter=8)
h2 = ParagraphStyle("H2", fontName="Helvetica-Bold", fontSize=12.5, leading=16,
                    textColor=ACCENT, spaceBefore=10, spaceAfter=5)
h3 = ParagraphStyle("H3", fontName="Helvetica-Bold", fontSize=10.5, leading=14,
                    textColor=NAVY, spaceBefore=7, spaceAfter=3)
small = ParagraphStyle("Small", fontName="Helvetica", fontSize=8.5, leading=12,
                       textColor=GREY)
bullet = ParagraphStyle("Bullet", parent=body, spaceAfter=3)
mono = ParagraphStyle("Mono", fontName="Courier", fontSize=8, leading=11,
                      textColor=colors.HexColor("#0f172a"), backColor=CODEBG,
                      borderColor=LIGHT, borderWidth=0.5, borderPadding=6,
                      spaceBefore=4, spaceAfter=8)


def P(t, s=body):
    return Paragraph(t, s)


def bullets(items, s=bullet):
    return ListFlowable(
        [ListItem(Paragraph(i, s), leftIndent=6, value="•") for i in items],
        bulletType="bullet", bulletColor=ACCENT, leftIndent=12, bulletFontSize=8,
    )


def codeblock(txt):
    return Preformatted(txt, mono)


def table(rows, col_widths, header=True):
    t = Table(rows, colWidths=col_widths)
    style = [
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("TEXTCOLOR", (0, 1), (-1, -1), SLATE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BOXBG]),
        ("GRID", (0, 0), (-1, -1), 0.4, LIGHT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]
    if header:
        style += [
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ]
    t.setStyle(TableStyle(style))
    return t


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(LIGHT)
    canvas.setLineWidth(0.6)
    canvas.line(20 * mm, 14 * mm, A4[0] - 20 * mm, 14 * mm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GREY)
    canvas.drawString(20 * mm, 9 * mm, "Drone Security Analyst Agent  |  Code Documentation")
    canvas.drawRightString(A4[0] - 20 * mm, 9 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build():
    doc = SimpleDocTemplate(
        OUT, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=20 * mm,
        title="Drone Security Analyst Agent - Code Documentation",
        author="Shrinivasan T",
    )
    s = []

    # ---- Title ----
    s.append(Spacer(1, 24))
    s.append(Paragraph("Drone Security Analyst Agent",
                       ParagraphStyle("T", fontName="Helvetica-Bold", fontSize=24,
                                      textColor=NAVY, alignment=TA_CENTER, leading=28)))
    s.append(Spacer(1, 6))
    s.append(Paragraph("Code Documentation",
                       ParagraphStyle("ST", fontName="Helvetica", fontSize=13,
                                      textColor=ACCENT, alignment=TA_CENTER)))
    s.append(Spacer(1, 18))

    # ---- 1. Framework and architecture ----
    s.append(P("1. Framework and Architecture", h1))
    s.append(P("The codebase is organised into four packages, each a clear layer with a "
               "single responsibility, plus a database schema and a container definition. "
               "Every layer below blob storage is source agnostic, so the simulated feed can "
               "be replaced by a real stream without touching the agent, backend, or "
               "frontend."))
    s.append(P("Package layout", h2))
    s.append(codeblock(
        "data/        frame production: video sampling, blob storage, ingest runner\n"
        "agent/       perception + reasoning: graph, nodes, rules, llm, db, embedder\n"
        "  nodes/     the seven LangGraph nodes\n"
        "backend/     FastAPI app + REST routes\n"
        "frontend/    React + Tailwind dashboard\n"
        "db/init.sql  frames / events / alerts schema with pgvector\n"
        "tests/       unit, agent, API, and QA scenario suites"
    ))
    s.append(P("The agent framework is LangGraph. One HTTP call to the ingest endpoint runs a "
               "graph of seven nodes with conditional edges. A typed state object is threaded "
               "through the nodes, and a process level session store provides memory across "
               "frames. The language model is bounded to perception and narrative, while a "
               "deterministic rule engine owns the decision of whether an alert fires."))

    # ---- 2. Technology stack ----
    s.append(P("2. Technology Stack", h1))
    s.append(P("Pinned versions from requirements.txt, with the role each component plays.",
               body))
    s.append(table([
        ["Component", "Version", "Role"],
        ["fastapi / uvicorn", "0.115 / 0.34", "Async REST API and ASGI server"],
        ["langgraph", "0.2.62", "Stateful agent graph with conditional routing"],
        ["langchain-openai", "0.3.0", "OpenAI compatible client wiring"],
        ["openai", "1.59", "Chat, vision, and embeddings client (Groq + OpenAI)"],
        ["sqlalchemy[asyncio]", "2.0.36", "Async ORM core"],
        ["asyncpg", "0.30", "PostgreSQL async driver"],
        ["pgvector", "0.3.6", "Vector column type and similarity search"],
        ["boto3", "1.35", "S3 API client for MinIO"],
        ["opencv-python-headless", "4.10", "Frame sampling from video clips"],
        ["pillow", "11.1", "JPEG encoding of sampled frames"],
        ["pydantic", "2.10", "Request validation and typed models"],
        ["pytest / pytest-asyncio", "8.3 / 0.25", "Test runner, async tests"],
        ["httpx", "0.28", "HTTP client for the live API and QA tests"],
    ], [120, 75, 225]))
    s.append(Spacer(1, 4))
    s.append(P("Models in use", h2))
    s.append(table([
        ["Task", "Provider", "Model"],
        ["Frame vision", "Groq", "meta-llama/llama-4-scout-17b-16e-instruct"],
        ["Reasoning narrative", "Groq", "llama-3.3-70b-versatile"],
        ["Chatbot reasoning loop", "OpenAI", "gpt-4o-mini"],
        ["Embeddings", "OpenAI", "text-embedding-3-small (local hashing fallback)"],
    ], [150, 70, 200]))

    s.append(PageBreak())

    # ---- 3. Module reference ----
    s.append(P("3. Module Reference", h1))

    s.append(P("data/ : frame production", h2))
    s.append(bullets([
        "<b>video_loader.sample_frames(clip, interval_seconds, max_frames, seed)</b> opens a "
        "clip with OpenCV, samples one frame every N seconds of video time, JPEG encodes it, "
        "and yields (frame_bytes, telemetry). Telemetry is seeded so a clip plus interval "
        "plus seed reproduces identical output.",
        "<b>blob_store.upload_frame(image_bytes, filename)</b> puts bytes into MinIO and "
        "returns a browser reachable URL; <b>get_frame_bytes(blob_url)</b> fetches them back. "
        "Two endpoints are used by design: an internal one for byte access and a public one "
        "baked into stored URLs for the browser.",
        "<b>ingest_runner.run(...)</b> drives the whole pipeline: sample frames across clips, "
        "upload each, POST to the ingest endpoint, and print a per frame line plus an "
        "aggregate of routes, events, and alerts.",
    ]))

    s.append(P("agent/ : perception and reasoning", h2))
    s.append(bullets([
        "<b>graph.run_frame(blob_url, telemetry)</b> compiles the graph once (cached) and runs "
        "one full cycle, returning the API result payload.",
        "<b>nodes/analyze_frame.analyze_frame(blob_url)</b> fetches the image, calls the vision "
        "model, and validates the response into a fixed schema.",
        "<b>nodes/query_history.node</b> embeds the description and runs a pgvector similarity "
        "search and a SQL recency filter in parallel.",
        "<b>rules.evaluate(vlm, telemetry, rolling_window, events_today)</b> returns the list "
        "of fired rules; pure and unit testable, no API call.",
        "<b>llm.complete_json(...)</b> returns a parsed JSON object from the first working "
        "provider; <b>complete_with_tools(...)</b> supports the chatbot tool calling loop. "
        "Both accept an explicit provider argument.",
        "<b>embedder.embed_text(text)</b> returns a 1536 dimension vector from OpenAI or a "
        "deterministic local hashing fallback.",
        "<b>db</b> holds async helpers: insert_frame, insert_event, insert_alert, "
        "query_similar_frames, query_recent_by_location, fetch_events, fetch_alerts, "
        "fetch_recent_frames, fetch_summary_stats.",
        "<b>state</b> defines the AgentState type and the SessionStore that carries the "
        "rolling window and this session's events and alerts across frames.",
    ]))

    s.append(KeepTogether([
        P("backend/ : API surface", h2),
        table([
            ["Route", "Method", "Purpose"],
            ["/ingest", "POST", "Run the full agent on a blob_url plus telemetry"],
            ["/ingest_image", "POST", "Multipart image upload, store, then run the agent"],
            ["/frames", "GET", "Recent frames (drives the live telemetry feed)"],
            ["/frames/search", "GET", "pgvector semantic search, returns blob_url per match"],
            ["/events", "GET", "Event log"],
            ["/alerts", "GET", "Alerts, with active_only filter"],
            ["/summary", "GET", "Aggregate stats plus an LLM session summary"],
            ["/chat", "POST", "Grounded Q and A with a reasoning loop and vision tool"],
            ["/health", "GET", "Liveness"],
        ], [105, 55, 235]),
    ]))

    # ---- 4. Key implementation details ----
    s.append(P("4. Key Implementation Details", h1))

    s.append(P("Conditional routing in the graph", h3))
    s.append(P("reason_decide emits a route, and two conditional edge maps fan the flow out. "
               "A normal frame goes straight to persistence; log and alert pass through "
               "log_event first; only alert continues to trigger_alert.", body))
    s.append(codeblock(
        'g.add_conditional_edges("reason_decide", _route,\n'
        '    {"normal": "update_state", "log": "log_event", "alert": "log_event"})\n'
        'g.add_conditional_edges("log_event", _route,\n'
        '    {"alert": "trigger_alert", "log": "update_state", "normal": "update_state"})'
    ))

    s.append(P("Deterministic rules separate from the model", h3))
    s.append(P("Alert firing is decided by a pure function so behaviour is reproducible and "
               "testable. The model supplies narrative only and cannot suppress a fired rule.",
               body))
    s.append(codeblock(
        "fired = rules.evaluate(vlm, telemetry, rolling_window, events_today)\n"
        "if fired:        route = 'alert'\n"
        "elif noteworthy: route = 'log'\n"
        "else:            route = 'normal'"
    ))

    s.append(P("Provider split with a single client abstraction", h3))
    s.append(P("Groq and OpenAI both expose an OpenAI compatible chat API, so one client "
               "serves both. Each call passes an explicit provider, so vision and reasoning "
               "stay on Groq while the chatbot reasoning stays on the OpenAI mini model, "
               "regardless of global toggles.", body))

    s.append(P("Chatbot reasoning loop with an on demand vision tool", h3))
    s.append(P("The chat route is a short tool calling loop rather than a single shot. It "
               "retrieves frames, reasons over their metadata, and may call the vision model "
               "on a specific frame when the text index is insufficient, then folds the visual "
               "findings into the answer.", body))

    # ---- 5. Validation ----
    s.append(P("5. Validation of Functionality", h1))
    s.append(P("Validation runs at three levels: unit and agent tests close to the code, a "
               "live API suite over the running service, and a scenario harness that drives "
               "real video sourced frames through the system and checks operator facing "
               "behaviour. All nine automated tests pass against the running stack."))

    s.append(P("5.1 Unit and agent tests", h2))
    s.append(P("<b>tests/test_analyze_frame.py</b> samples five real frames into MinIO and "
               "asserts the vision step returns the full schema with valid types, plus a "
               "valid embedding. The key assertions:", body))
    s.append(codeblock(
        "for field in (object_type, location, action, clothing, color, confidence):\n"
        "    assert field in result and result[field] not in (None, '')\n"
        "assert 0.0 <= result['confidence'] <= 1.0\n"
        "assert len(embed_text(desc)) == 1536"
    ))
    s.append(P("<b>tests/test_agent_pipeline.py</b> runs the full graph on six real frames via "
               "run_frame and asserts both the returned result and the database writes:", body))
    s.append(codeblock(
        "assert result['status'] == 'ok'\n"
        "assert result['decision']['route'] in {normal, log, alert}\n"
        "# then, reading back the frames table:\n"
        "assert row['blob_url'].startswith('http')\n"
        "assert row['has_emb'] and row['dims'] == 1536"
    ))
    s.append(P("<b>tests/test_api.py</b> exercises every REST endpoint against the live "
               "backend and asserts, as the central requirement, that frame URLs are present "
               "and resolve to real images served by MinIO.", body))

    s.append(PageBreak())

    s.append(P("5.2 Scenario harness for dynamic inputs", h2))
    s.append(P("The dynamic input is a real run of sampled video frames with seeded synthetic "
               "telemetry. Twenty five frames were driven through the live agent. Because the "
               "synthetic time of day is spread across a full 24 hour cycle, one run produces "
               "both routine daytime frames and after hours frames, which exercises the "
               "emergency path without any staged input. The run produced 22 alert routes, "
               "2 normal, and 1 log, with after hours vehicle firing 10 times, after hours "
               "person 8 times, and repeat vehicle 8 times across 30 frames in the database."))
    s.append(P("The harness, tests/qa_scenarios.py, queries the live endpoints and reports "
               "each case. Result: 7 pass, 2 informational, 0 fail.", body))
    s.append(table([
        ["Case", "Scenario", "Outcome"],
        ["QA-01", "Vehicle frame persisted with URL", "Pass, 20 vehicle frames with URLs"],
        ["QA-02", "Repeat or after hours vehicle alert", "Pass, 18 vehicle alerts"],
        ["QA-03", "After hours pedestrian alert", "Pass, 8 alerts"],
        ["QA-04", "Loitering across 5 frames", "Info, rule verified directly"],
        ["QA-05", "Frame search returns images", "Pass, rows carry blob_url"],
        ["QA-06", "Search image is fetchable", "Pass, HTTP 200 image/jpeg"],
        ["QA-07", "Chat answer grounded in frames", "Pass, answer cites a frame"],
        ["QA-08", "Session summary generated", "Pass, over 30 frames and 26 alerts"],
        ["QA-09", "Normal daytime activity", "Info, daytime alerts are repeat_vehicle"],
    ], [48, 200, 174]))

    s.append(P("5.3 Emergency response scenarios", h2))
    s.append(P("The emergency path is the route from a rule violation to a persisted alert "
               "that carries the triggering frame. These were observed live during the run:",
               body))
    s.append(bullets([
        "<b>After hours person (critical).</b> A person detected outside business hours fires "
        "after_hours_person. Example message: person at loading_dock, 04:48, after hours.",
        "<b>After hours vehicle (high).</b> A vehicle outside business hours fires "
        "after_hours_vehicle; ten such alerts were raised in the run.",
        "<b>Repeat vehicle (warning).</b> The same vehicle descriptor seen three or more "
        "times in a session fires repeat_vehicle; eight were raised, and this rule is "
        "intentionally not time gated.",
        "<b>Loitering (high).</b> Five consecutive frames of the same subject at one location "
        "fire loitering. It does not arise from the ingest run because telemetry cycles the "
        "waypoint each frame, so it was verified by direct evaluation, which produced the "
        "alert as expected.",
        "<b>Restricted zone (critical).</b> Any subject in a configured restricted location "
        "fires restricted_zone when that configuration is set.",
    ]))
    s.append(P("In every alerting case the alert row stores the rule, message, severity, and "
               "the triggering frame URL, which is what the dashboard alert banner renders. "
               "If the reasoning model call fails, the node falls back to a deterministic "
               "summary, so an alert is never lost to a model error.", body))

    s.append(P("5.4 Running the tests", h2))
    s.append(codeblock(
        "# unit and agent tests\n"
        "pytest tests/test_analyze_frame.py tests/test_agent_pipeline.py\n\n"
        "# live API tests (stack must be up)\n"
        "pytest tests/test_api.py\n\n"
        "# populate data, then run the scenario harness\n"
        "python -m data.ingest_runner --frames 25 --interval 2.0\n"
        "python tests/qa_scenarios.py"
    ))
    s.append(P("Tests that need a model key or a reachable service skip themselves cleanly "
               "when those are absent, so the suite stays green in restricted environments "
               "rather than reporting false failures.", small))

    doc.build(s, onFirstPage=_footer, onLaterPages=_footer)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    build()
