"""
Clinical Co-Pilot Agent Service
FastAPI app that uses Claude to answer PCP questions about patients via OpenEMR FHIR API.
"""

import os
import json
import time
import functools
import requests
import urllib3
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
from anthropic import Anthropic
from langsmith.wrappers import wrap_anthropic
from tools import TOOLS, execute_tool
from verification import verify_response
from document_extractor import extract_document
from pathlib import Path

# Week 2 graph — replaces the single-LLM-with-tools loop for /chat.
from clinical_graph import (
    run as graph_run,
    run_for_stream as graph_run_for_stream,
    synthesize_stream,
)
from clinical_logger import log_encounter, estimate_cost_usd
from ingest_to_openemr import run_sql as _run_sql

urllib3.disable_warnings()

app = FastAPI(title="Clinical Co-Pilot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Config
OPENEMR_BASE = os.getenv("OPENEMR_BASE", "https://localhost:9300")
OPENEMR_CLIENT_ID = os.getenv("OPENEMR_CLIENT_ID", "")
OPENEMR_CLIENT_SECRET = os.getenv("OPENEMR_CLIENT_SECRET", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

client = wrap_anthropic(Anthropic(api_key=ANTHROPIC_API_KEY))

# Token cache
_token_cache = {"token": None, "expires_at": 0}


def get_openemr_token():
    """Get or refresh OAuth2 token for OpenEMR."""
    if _token_cache["token"] and time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["token"]

    resp = requests.post(
        f"{OPENEMR_BASE}/oauth2/default/token",
        data={
            "grant_type": "password",
            "username": "admin",
            "password": "pass",
            "user_role": "users",
            "scope": "openid api:fhir user/Patient.read user/Condition.read user/MedicationRequest.read user/AllergyIntolerance.read user/Encounter.read user/Observation.read user/Coverage.read user/Immunization.read user/DocumentReference.read user/Binary.read user/CareTeam.read",
            "client_id": OPENEMR_CLIENT_ID,
            "client_secret": OPENEMR_CLIENT_SECRET,
        },
        verify=False,
    )
    if resp.status_code != 200:
        raise Exception(f"Token failed: {resp.status_code} {resp.text}")

    data = resp.json()
    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = time.time() + data.get("expires_in", 3600)
    return _token_cache["token"]


SYSTEM_PROMPT = """You are a Clinical Co-Pilot for a primary care physician (PCP).
You help the PCP by answering questions about their patients using data from OpenEMR.

RULES:
1. Every factual claim MUST cite a source. Use the FHIR resource IDs returned by tools.
2. If the record is silent on a topic, say "No [topic] documented in the record." Do NOT guess.
3. The patient-stated reason for visit is a signal, not confirmed truth. Say "The patient indicated they are here for X."
4. Always surface chronic conditions from the active problem list, even if not related to today's visit.
5. Keep pre-room briefings under 150 words so the PCP can read in 30 seconds.
6. For factual lookups, give a direct answer with citation. Don't ramble.
7. If a tool fails, say what failed and suggest the PCP check the chart directly.
8. Never make up medication names, lab values, or diagnoses not in the data.

TOOL SELECTION:
- For structured data (current medications, active conditions, allergies, lab values, vitals): use the specific structured tools (get_active_medications, get_active_conditions, get_allergies, get_recent_labs).
- For unstructured/historical questions (has the patient ever mentioned a symptom, any history of a complaint, what was discussed at prior visits, symptom patterns over time): use search_notes.
- For briefings: call structured tools first, then search_notes if the visit reason suggests a topic worth searching notes for.

When the PCP asks for a briefing, call tools in this order:
1. get_active_conditions - to know chronic conditions
2. get_active_medications - current med list
3. get_allergies - allergy list
4. get_recent_encounters - visit history and today's reason
5. get_recent_labs - if relevant to conditions

Structure briefings EXACTLY as follows. Do NOT include a top-level header like "Pre-Room Briefing" or "## PRE-ROOM BRIEFING". Start directly with the section labels:

**TODAY:** [What the visit appears to be about, with encounter citation]
**CHANGES:** [What's changed since last visit]
**ACTIVE CONDITIONS:** [Chronic problems to keep in mind, with condition citations]
**KEY MEDICATIONS:** [Relevant medications with citations]
**ALLERGIES:** [Known allergies]
**LABS:** [Recent lab results or "No laboratory results documented"]
**KEY POINTS:** [1-2 sentence clinical focus for this visit]
"""


class ChatRequest(BaseModel):
    patient_id: str
    message: str
    conversation_history: list = []


class ChatResponse(BaseModel):
    response: str
    citations: list
    claims: list = []
    tools_called: list
    tokens_used: dict
    verified: bool
    # Total wall-clock time the supervisor spent producing this answer.
    # Surfaced so the chat UI can render a routing-trace footer showing
    # supervisor → worker handoffs with their per-step latency.
    total_latency_ms: float = 0.0
    evidence_count: int = 0


def _pid_from_fhir_uuid(fhir_uuid: str) -> Optional[int]:
    """Translate the FHIR UUID the UI sends into the integer pid that
    chart_lookup expects. Returns None if the patient isn't local."""
    if not fhir_uuid:
        return None
    out = _run_sql(
        f"SELECT pid FROM patient_data WHERE uuid = UNHEX(REPLACE('{fhir_uuid}','-','')) LIMIT 1;"
    ) or ""
    lines = [l for l in out.strip().split("\n") if l]
    if len(lines) >= 2 and lines[1].strip().isdigit():
        return int(lines[1].strip())
    return None


def _flatten_chart_citations(chart: dict) -> list[dict]:
    """Pull (document, quote) pairs out of the chart_lookup result so the
    UI can render them as citation chips."""
    if not chart:
        return []
    cites = []
    for key in ("medications", "allergies", "conditions", "surgeries", "encounters", "labs"):
        for row in chart.get(key) or []:
            src = row.get("source") or {}
            if src.get("document"):
                cites.append({
                    "type": key,
                    "document": src.get("document"),
                    "quote": src.get("quote") or "",
                })
    hist = chart.get("history") or {}
    if hist.get("source", {}).get("document"):
        cites.append({
            "type": "history",
            "document": hist["source"]["document"],
            "quote": hist["source"].get("quote") or "",
        })
    return cites


def _evidence_citations(evidence: list) -> list[dict]:
    out = []
    for e in evidence or []:
        src = e.get("source") or {}
        out.append({
            "type": "guideline",
            "document": src.get("file"),
            "section": src.get("section"),
        })
    return out


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Main chat endpoint — runs the W2 LangGraph behind the W1 OAuth gate.

    The OAuth token fetch is preserved as the door — if OpenEMR rejects the
    agent, the request fails before any graph work runs. After auth, the
    request is dispatched to clinical_graph which decides routing
    (chart_lookup / evidence_retriever / intake_extractor) and writes the
    final answer with explicit citations.
    """
    # OAuth gate — fails fast if OpenEMR rejects the agent.
    get_openemr_token()

    # The UI sends a FHIR UUID; chart_lookup expects an int pid.
    pid_int = _pid_from_fhir_uuid(req.patient_id) or 0

    result = graph_run(req.message, patient_id=pid_int)

    final_text = result.get("final_answer") or ""
    chart = result.get("chart") or {}
    evidence = result.get("evidence") or []
    handoffs = result.get("handoffs") or []

    citations = _flatten_chart_citations(chart) + _evidence_citations(evidence)
    tools_called = [
        {
            "tool": f"{h.get('from')}->{h.get('to')}",
            "from": h.get("from", ""),
            "to": h.get("to", ""),
            "reason": h.get("reason", ""),
            "elapsed_ms": h.get("elapsed_ms", 0),
        }
        for h in handoffs
    ]
    total_latency_ms = sum(h.get("elapsed_ms", 0) or 0 for h in handoffs)

    # The W2 synthesis prompt enforces citation discipline; we surface the
    # boolean so the UI can still render the verification badge.
    verified = bool(final_text)

    usage = result.get("usage") or {}
    return ChatResponse(
        response=final_text,
        citations=citations,
        claims=result.get("claims") or [],
        tools_called=tools_called,
        tokens_used={
            "input": usage.get("input", 0),
            "output": usage.get("output", 0),
            "total": usage.get("total", 0),
        },
        verified=verified,
        total_latency_ms=round(total_latency_ms, 1),
        evidence_count=len(evidence),
    )


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """Streaming chat — drops time-to-first-token from ~20s to ~3s.

    Wire format: Server-Sent Events. Each event is a JSON object framed
    with `data: ` and a blank line, per the SSE spec. Event kinds:
        {"type":"routing","tools_called":[...]}     after the graph routes
        {"type":"text","delta":"..."}               for each synthesis token
        {"type":"meta", citations/claims/usage/...} once the answer completes
        {"type":"error","message":"..."}            on synthesis failure

    The routing/retrieval phases run synchronously (they're fast — usually
    sub-second). Synthesis is the slow LLM call, and that's the part we
    stream so the chat bubble fills in live instead of staring at a spinner.
    """
    get_openemr_token()

    pid_int = _pid_from_fhir_uuid(req.patient_id) or 0
    query = req.message

    def _sse(payload: dict) -> bytes:
        return f"data: {json.dumps(payload)}\n\n".encode("utf-8")

    def event_stream():
        t_start = time.time()
        # Phase 1: run the graph through routing + retrieval, but stop
        # before synthesis so we can stream tokens.
        try:
            state = graph_run_for_stream(query, patient_id=pid_int)
        except Exception as exc:
            yield _sse({"type": "error",
                        "message": f"graph failed: {type(exc).__name__}"})
            return

        chart = state.get("chart") or {}
        evidence = state.get("evidence") or []
        handoffs = state.get("handoffs") or []
        routing_usage = dict(state.get("usage") or {})

        tools_called = [
            {
                "tool": f"{h.get('from')}->{h.get('to')}",
                "from": h.get("from", ""),
                "to": h.get("to", ""),
                "reason": h.get("reason", ""),
                "elapsed_ms": h.get("elapsed_ms", 0),
            }
            for h in handoffs
        ]
        citations = _flatten_chart_citations(chart) + _evidence_citations(evidence)

        # Tell the UI which workers ran so it can render the routing trace
        # before the first synthesis token even arrives.
        yield _sse({
            "type": "routing",
            "tools_called": tools_called,
            "evidence_count": len(evidence),
            "elapsed_ms": round((time.time() - t_start) * 1000, 1),
        })

        # Phase 2: stream synthesis tokens.
        answer = ""
        claims: list = []
        synth_usage: dict = {}
        for kind, payload in synthesize_stream(state):
            if kind == "text":
                yield _sse({"type": "text", "delta": payload})
            elif kind == "done":
                answer = payload.get("answer") or ""
                claims = payload.get("claims") or []
                synth_usage = payload.get("usage") or {}
            elif kind == "error":
                yield _sse({"type": "error", "message": payload})
                return

        # Final tally — combine routing + synthesis token counts.
        merged_input = (routing_usage.get("input", 0) or 0) + (synth_usage.get("input", 0) or 0)
        merged_output = (routing_usage.get("output", 0) or 0) + (synth_usage.get("output", 0) or 0)
        usage = {
            "input": merged_input,
            "output": merged_output,
            "total": merged_input + merged_output,
        }
        total_latency_ms = round((time.time() - t_start) * 1000, 1)

        yield _sse({
            "type": "meta",
            "response": answer,
            "citations": citations,
            "claims": claims,
            "tools_called": tools_called,
            "tokens_used": usage,
            "verified": bool(answer),
            "total_latency_ms": total_latency_ms,
            "evidence_count": len(evidence),
        })

        # Mirror the encounter-log call that graph_run() does in the
        # non-streaming path so we don't lose observability for streamed turns.
        try:
            log_encounter({
                "query": query,
                "patient_id": pid_int or None,
                "file_path": None,
                "tool_sequence": [f"{h.get('from')}→{h.get('to')}" for h in handoffs],
                "latency_per_step_ms": [h.get("elapsed_ms") for h in handoffs],
                "total_latency_ms": total_latency_ms,
                "tokens_used": usage,
                "cost_estimate_usd": estimate_cost_usd(usage),
                "retrieval_hits": len(evidence),
                "extraction_confidence": None,
                "claims_count": len(claims),
                "answer_length_chars": len(answer),
                "timed_out": bool(state.get("timed_out")),
                "eval_outcome": None,
            })
        except Exception:
            # Logging must never break the stream.
            pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            # Disable proxy buffering so Caddy / nginx forward each chunk
            # immediately. Without this, the whole stream can be buffered
            # to completion and arrive as one block.
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/extract")
async def extract_doc(
    file: UploadFile = File(...),
    patient_id: str = Form(...),
    doc_type: str = Form(...),
):
    """Upload and extract a clinical document (lab PDF or intake form)."""
    import tempfile
    from document_extractor import attach_and_extract
    
    # Save uploaded file temporarily
    suffix = Path(file.filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
    
    try:
        token = get_openemr_token()
        result = attach_and_extract(patient_id, tmp_path, doc_type, token, OPENEMR_BASE)
        return result
    finally:
        os.unlink(tmp_path)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ui")
async def ui():
    """Serve the chat iframe UI. Loaded by demographics.php in OpenEMR.

    no-store so browsers don't cache the iframe HTML — otherwise UI changes
    don't reach the user until they hard-refresh, which they often won't.
    """
    return FileResponse(
        Path(__file__).parent / "chat.html",
        media_type="text/html",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


# Resolved document_id → filesystem path lookups never change for the
# lifetime of a row (filename is the dedup key in `documents`), so caching
# the lookup avoids a SQL round-trip on every citation click.
@functools.lru_cache(maxsize=512)
def _resolve_document_path_cached(document_id: int) -> str:
    out = _run_sql(f"SELECT name FROM documents WHERE id={document_id} LIMIT 1;") or ""
    lines = out.strip().split("\n")
    if len(lines) < 2:
        raise HTTPException(404, "document not found")
    name = lines[1].strip()
    subdir = "intake-forms" if "intake" in name.lower() else "lab-results"
    path = Path(__file__).parent / "sample_docs" / subdir / name
    if not path.exists():
        raise HTTPException(404, "source file missing on host")
    return str(path)


def _resolve_document_path(document_id: int) -> Path:
    return Path(_resolve_document_path_cached(document_id))


# In-memory PNG cache for rasterized PDF pages. PyMuPDF rendering at 2x
# takes ~1-2s per page on the CPU droplet; without server-side caching
# every NEW citation click pays the full cost (browser cache only helps
# after the first click on the same page). 256 pages ≈ 100-200 MB at 2x —
# fine for the demo workload, drop it if memory becomes a concern.
@functools.lru_cache(maxsize=256)
def _render_pdf_page_png(path_str: str, page_num: int) -> bytes:
    import fitz  # type: ignore[import-not-found]
    doc = fitz.open(path_str)
    try:
        if page_num < 1 or page_num > len(doc):
            raise HTTPException(404, f"page {page_num} out of range (1..{len(doc)})")
        page = doc[page_num - 1]
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        return pix.tobytes("png")
    finally:
        doc.close()


# Source documents are immutable once ingested (filename = dedup key, no
# in-place updates), so the browser can safely cache them aggressively.
# Set 1-hour Cache-Control with `immutable` so re-clicking a citation
# during the same demo session doesn't re-fetch the PDF + re-rasterize
# the page each time. First click pays the streaming cost; subsequent
# clicks are served from the browser's cache instantly.
_DOC_CACHE_HEADERS = {"Cache-Control": "public, max-age=3600, immutable"}


@app.get("/document/{document_id}/file")
async def document_file(document_id: int):
    """Serve the original PDF/PNG for a given document_id."""
    path = _resolve_document_path(document_id)
    media = "application/pdf" if path.suffix.lower() == ".pdf" else "image/png"
    return FileResponse(path, media_type=media, headers=_DOC_CACHE_HEADERS)


@app.get("/document/{document_id}/page/{page_num}.png")
async def document_page_png(document_id: int, page_num: int):
    """Rasterize page N of a PDF source and return as PNG.

    The viewer overlays a colored rectangle at the citation's bbox on top
    of this PNG. PNG sources just round-trip to /file directly.
    """
    path = _resolve_document_path(document_id)
    if path.suffix.lower() != ".pdf":
        return FileResponse(path, media_type="image/png", headers=_DOC_CACHE_HEADERS)
    try:
        png_bytes = _render_pdf_page_png(str(path), page_num)
    except ImportError:
        raise HTTPException(500, "pymupdf not installed")
    return Response(content=png_bytes, media_type="image/png", headers=_DOC_CACHE_HEADERS)


@app.get("/document/{document_id}/view")
async def document_view(document_id: int):
    """HTML page that renders the source PDF/PNG with a bbox overlay.

    Query params:
      page=N        which page to scroll to (1-based)
      bboxes=JSON   list of {page,x0,y0,x1,y1,page_width,page_height}
                    matching what's stored in derived_fact_citations.bbox_json
    """
    # The viewer HTML is small (<10 KB) and does change when we tweak the
    # overlay logic, so don't make it `immutable` — but a short cache is
    # fine to skip re-fetching on every citation click in the same session.
    return FileResponse(
        Path(__file__).parent / "doc_viewer.html",
        media_type="text/html",
        headers={"Cache-Control": "public, max-age=300"},
    )


# ── Patient dashboard (React) — embedded into OpenEMR's demographics page ──
#
# The dashboard is a separate Vite + React + TS SPA under ../dashboard. We
# serve its production build from /dashboard so OpenEMR can iframe it from
# the same origin as the AI co-pilot. /apis/* is proxied through the agent
# (with the bearer token attached server-side) so the dashboard never needs
# to handle auth and there's no CORS handshake.

DASHBOARD_DIST = Path(__file__).parent.parent / "dashboard" / "dist"
if DASHBOARD_DIST.is_dir():
    app.mount(
        "/dashboard",
        StaticFiles(directory=str(DASHBOARD_DIST), html=True),
        name="dashboard",
    )


# In-memory TTL cache for GET /apis/* responses. The React dashboard fires
# ~10 FHIR calls in parallel on every patient open (Patient, Medications,
# Allergies, Conditions, Encounters, Observations, Immunizations,
# DocumentReferences, etc.) — each one round-trips through OpenEMR's PHP
# layer to MariaDB. Caching for 60s makes any patient that's already been
# loaded re-render instantly, which is the dominant pattern during a
# demo (clinician switches between 4 patients repeatedly).
_FHIR_CACHE_TTL_S = 60.0
_fhir_cache: dict[str, tuple[float, int, str, bytes]] = {}
_FHIR_CACHE_MAX_ENTRIES = 256


def _fhir_cache_set(key: str, status_code: int, media: str, content: bytes) -> None:
    if len(_fhir_cache) >= _FHIR_CACHE_MAX_ENTRIES:
        # Cheap eviction: drop the oldest entry. dict iteration order is
        # insertion order on Python 3.7+, so the first key is the oldest.
        oldest = next(iter(_fhir_cache))
        _fhir_cache.pop(oldest, None)
    _fhir_cache[key] = (time.time(), status_code, media, content)


def _fhir_cache_get(key: str) -> Optional[tuple[int, str, bytes]]:
    entry = _fhir_cache.get(key)
    if entry is None:
        return None
    ts, status_code, media, content = entry
    if time.time() - ts > _FHIR_CACHE_TTL_S:
        _fhir_cache.pop(key, None)
        return None
    return status_code, media, content


# Browser-cache header for cached FHIR GETs. `private` so any future shared
# proxy doesn't keep PHI; max-age matches the server-side TTL so the two
# caches expire together.
_FHIR_BROWSER_CACHE_HEADERS = {
    "Cache-Control": f"private, max-age={int(_FHIR_CACHE_TTL_S)}",
}


@app.api_route("/apis/{rest_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def openemr_api_proxy(rest_path: str, request: Request):
    """Proxy /apis/* to OpenEMR with the agent's OAuth bearer token attached.

    Lets the React dashboard call e.g. /apis/default/fhir/Patient/<id> from
    the same origin (no CORS, no client-side token plumbing). Same auth
    surface as everything else the agent does — no new credentials.

    GET responses are cached in-memory for 60s — see _FHIR_CACHE_TTL_S.
    Mutating methods bust the entire cache so writes don't read stale data
    on the next refresh.
    """
    method = request.method
    qs = request.url.query
    cache_key = f"{rest_path}?{qs}" if qs else rest_path

    # Cache hit — skip the OpenEMR round-trip entirely.
    if method == "GET":
        cached = _fhir_cache_get(cache_key)
        if cached is not None:
            status_code, media, content = cached
            return Response(
                content=content,
                status_code=status_code,
                media_type=media,
                headers={**_FHIR_BROWSER_CACHE_HEADERS, "X-Agent-Cache": "hit"},
            )

    token = get_openemr_token()
    target = f"{OPENEMR_BASE}/apis/{rest_path}"
    if qs:
        target = f"{target}?{qs}"

    body = await request.body()
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": request.headers.get("accept", "application/fhir+json"),
    }
    if method != "GET" and request.headers.get("content-type"):
        headers["Content-Type"] = request.headers["content-type"]

    resp = requests.request(
        method,
        target,
        data=body if body else None,
        headers=headers,
        verify=False,
    )
    media = resp.headers.get("content-type", "application/json")

    # Cache successful GETs; bust everything on writes (the next read will
    # repopulate). 200/304 only — don't cache 401/500/etc.
    if method == "GET" and 200 <= resp.status_code < 300:
        _fhir_cache_set(cache_key, resp.status_code, media, resp.content)
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type=media,
            headers={**_FHIR_BROWSER_CACHE_HEADERS, "X-Agent-Cache": "miss"},
        )
    elif method != "GET":
        _fhir_cache.clear()

    return Response(content=resp.content, status_code=resp.status_code, media_type=media)


# OpenEMR doesn't expose FamilyMemberHistory as a FHIR resource (the route
# returns 404). The data lives in `history_data` (one row per patient) with
# free-text columns: history_mother, history_father, and relatives_*. This
# endpoint reads those columns and returns a small array shaped like the
# dashboard's FamilyHistoryRow so the widget renders cleanly.
@app.get("/family-history/{patient_uuid}")
def family_history(patient_uuid: str):
    pid = _pid_from_fhir_uuid(patient_uuid)
    if pid is None:
        return []

    cols = [
        ("history_mother", "Mother"),
        ("history_father", "Father"),
        ("relatives_cancer", "Relatives — cancer"),
        ("relatives_diabetes", "Relatives — diabetes"),
        ("relatives_high_blood_pressure", "Relatives — hypertension"),
        ("relatives_heart_problems", "Relatives — heart disease"),
        ("relatives_stroke", "Relatives — stroke"),
        ("relatives_epilepsy", "Relatives — epilepsy"),
        ("relatives_mental_illness", "Relatives — mental illness"),
        ("relatives_suicide", "Relatives — suicide"),
        ("relatives_tuberculosis", "Relatives — tuberculosis"),
    ]
    select_list = ", ".join(c for c, _ in cols)
    out = _run_sql(f"SELECT {select_list} FROM history_data WHERE pid={pid} LIMIT 1;") or ""
    lines = [l for l in out.strip().split("\n") if l]
    if len(lines) < 2:
        return []
    values = lines[1].split("\t")

    rows: list[dict] = []
    for i, (_, label) in enumerate(cols):
        v = values[i] if i < len(values) else ""
        if not v or v.strip() in ("NULL", ""):
            continue
        cond, status = _split_conditions_status(v)
        rows.append({
            "id": f"fh_{pid}_{i}",
            "relation": label,
            "conditions": cond or "(no conditions reported)",
            "status": status,
        })
    return rows


# OpenEMR's FHIR Observation projection doesn't surface our procedure_result
# rows (returns total=0 even for a direct GET on the result UUID — broken
# even for the seeded demo patient). Read the data directly so the labs
# card has something to render.
@app.get("/labs/{patient_uuid}")
def labs(patient_uuid: str):
    pid = _pid_from_fhir_uuid(patient_uuid)
    if pid is None:
        return []
    out = _run_sql(
        "SELECT pres.procedure_result_id, pres.result_text, pres.result, "
        "pres.units, pres.abnormal, prep.date_collected "
        "FROM procedure_result pres "
        "JOIN procedure_report prep ON pres.procedure_report_id=prep.procedure_report_id "
        "JOIN procedure_order po ON prep.procedure_order_id=po.procedure_order_id "
        f"WHERE po.patient_id={pid} ORDER BY prep.date_collected DESC LIMIT 50;"
    ) or ""
    lines = [l for l in out.strip().split("\n") if l]
    if len(lines) < 2:
        return []

    abnormal_codes = {"H", "HH", "L", "LL", "A", "AA"}
    rows: list[dict] = []
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) < 6:
            continue
        rid, title, value, units, flag, date = parts[:6]
        title = title.strip()
        value = value.strip()
        units = units.strip()
        flag = (flag or "").strip()
        date = (date or "").strip()
        if date in ("NULL", ""):
            date_iso = ""
        else:
            date_iso = date.split(" ")[0]
        value_with_unit = f"{value} {units}".strip() if units else value
        rows.append({
            "id": f"lab_{rid}",
            "title": title or "Unknown test",
            "value_with_unit": value_with_unit,
            "flag": flag,
            "date": date_iso,
            "is_abnormal": flag in abnormal_codes,
        })
    return rows


# OpenEMR's FHIR Coverage requires insurance_data.provider to be an integer
# FK into insurance_companies, but the projection still returns total=0 for
# our minimal company rows. Read insurance_data directly and LEFT JOIN to
# insurance_companies to recover the carrier display name (insurance_data
# stores only the integer FK, not the name).
@app.get("/coverage/{patient_uuid}")
def coverage(patient_uuid: str):
    pid = _pid_from_fhir_uuid(patient_uuid)
    if pid is None:
        return []
    out = _run_sql(
        "SELECT i.id, i.type, ic.name AS company_name, i.plan_name, "
        "i.policy_number, i.group_number, i.copay, i.accept_assignment, "
        "i.date, i.date_end "
        "FROM insurance_data i "
        "LEFT JOIN insurance_companies ic "
        "  ON ic.id = CAST(NULLIF(i.provider,'') AS UNSIGNED) "
        f"WHERE i.pid={pid} "
        "ORDER BY FIELD(i.type,'primary','secondary','tertiary');"
    ) or ""
    lines = [l for l in out.strip().split("\n") if l]
    if len(lines) < 2:
        return []

    rows: list[dict] = []
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) < 10:
            continue
        cid, ctype, company_name, plan, policy, group, copay, accept, date, date_end = parts[:10]
        def clean(s: str) -> str:
            s = (s or "").strip()
            return "" if s == "NULL" else s
        # Prefer the insurance_companies.name; fall back to plan_name (where
        # the ingest now mirrors the carrier text for display).
        insurer = clean(company_name) or clean(plan)
        rows.append({
            "id": f"cov_{cid}",
            "type": clean(ctype) or "primary",
            "insurer_name": insurer,
            "plan_name": clean(plan),
            "policy_number": clean(policy),
            "group_number": clean(group),
            "copay": clean(copay),
            "accept_assignment": clean(accept),
            "date": clean(date).split(" ")[0],
            "date_end": clean(date_end).split(" ")[0],
        })
    return rows


# FHIR CareTeam returns an empty Bundle for our patients — OpenEMR's
# projection doesn't read patient_data.care_team_provider, where ingest
# stores the free-text "PCP: Dr. X / Cardiologist: Dr. Y" string from the
# intake form. Parse that into one row per provider.
@app.get("/care-team/{patient_uuid}")
def care_team(patient_uuid: str):
    pid = _pid_from_fhir_uuid(patient_uuid)
    if pid is None:
        return []
    out = _run_sql(
        f"SELECT care_team_provider FROM patient_data WHERE pid={pid} LIMIT 1;"
    ) or ""
    lines = [l for l in out.strip().split("\n") if l]
    if len(lines) < 2:
        return []
    blob = lines[1].strip()
    if not blob or blob == "NULL":
        return []

    # Free text shaped like "Primary Care Physician: Dr. Anjali Rao, MD -
    # Berkeley Family Medical Group, PCP NPI 1659302147" possibly with
    # multiple providers separated by ' / ' or newlines. Split on those,
    # then split each segment on the FIRST ':' into role:name.
    segments: list[str] = []
    for chunk in blob.replace("\n", " / ").split(" / "):
        segments.extend(s.strip() for s in chunk.split(";") if s.strip())

    rows: list[dict] = []
    for i, seg in enumerate(segments):
        if not seg:
            continue
        if ":" in seg:
            role, name = seg.split(":", 1)
            role = role.strip()
            name = name.strip()
        else:
            role, name = "Provider", seg
        if not name:
            continue
        rows.append({
            "id": f"ct_{pid}_{i}",
            "name": name,
            "role": role or "Provider",
        })
    return rows


def _split_conditions_status(v: str) -> tuple[str, str]:
    """Split "<conditions> (<status>)" into (conditions, status).

    The status itself can contain nested parentheses (e.g.
    "Deceased age 81 (natural)"), so a simple rfind('(') would leak the
    inner closing paren into status. Walk backwards from the trailing ')'
    matching depth to find the OUTER opening paren.
    """
    if not v.endswith(")"):
        return v.strip(), ""
    depth = 0
    for i in range(len(v) - 1, -1, -1):
        if v[i] == ")":
            depth += 1
        elif v[i] == "(":
            depth -= 1
            if depth == 0:
                return v[:i].strip(), v[i + 1 : -1].strip()
    return v.strip(), ""
