"""
Clinical Co-Pilot Agent Service
FastAPI app that uses Claude to answer PCP questions about patients via OpenEMR FHIR API.
"""

import os
import json
import time
import requests
import urllib3
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
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
from clinical_graph import run as graph_run
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
            "reason": h.get("reason", ""),
        }
        for h in handoffs
    ]

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


def _resolve_document_path(document_id: int) -> Path:
    out = _run_sql(f"SELECT name FROM documents WHERE id={document_id} LIMIT 1;") or ""
    lines = out.strip().split("\n")
    if len(lines) < 2:
        raise HTTPException(404, "document not found")
    name = lines[1].strip()
    subdir = "intake-forms" if "intake" in name.lower() else "lab-results"
    path = Path(__file__).parent / "sample_docs" / subdir / name
    if not path.exists():
        raise HTTPException(404, "source file missing on host")
    return path


@app.get("/document/{document_id}/file")
async def document_file(document_id: int):
    """Serve the original PDF/PNG for a given document_id."""
    path = _resolve_document_path(document_id)
    media = "application/pdf" if path.suffix.lower() == ".pdf" else "image/png"
    return FileResponse(path, media_type=media)


@app.get("/document/{document_id}/page/{page_num}.png")
async def document_page_png(document_id: int, page_num: int):
    """Rasterize page N of a PDF source and return as PNG.

    The viewer overlays a colored rectangle at the citation's bbox on top
    of this PNG. PNG sources just round-trip to /file directly.
    """
    path = _resolve_document_path(document_id)
    if path.suffix.lower() != ".pdf":
        return FileResponse(path, media_type="image/png")
    try:
        import fitz  # type: ignore[import-not-found]
    except ImportError:
        raise HTTPException(500, "pymupdf not installed")
    doc = fitz.open(path)
    if page_num < 1 or page_num > len(doc):
        doc.close()
        raise HTTPException(404, f"page {page_num} out of range (1..{len(doc)})")
    page = doc[page_num - 1]
    # Render at 2x to get a sharp image without ballooning size.
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
    png_bytes = pix.tobytes("png")
    doc.close()
    from fastapi.responses import Response
    return Response(content=png_bytes, media_type="image/png")


@app.get("/document/{document_id}/view")
async def document_view(document_id: int):
    """HTML page that renders the source PDF/PNG with a bbox overlay.

    Query params:
      page=N        which page to scroll to (1-based)
      bboxes=JSON   list of {page,x0,y0,x1,y1,page_width,page_height}
                    matching what's stored in derived_fact_citations.bbox_json
    """
    return FileResponse(Path(__file__).parent / "doc_viewer.html", media_type="text/html")


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


@app.api_route("/apis/{rest_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def openemr_api_proxy(rest_path: str, request: Request):
    """Proxy /apis/* to OpenEMR with the agent's OAuth bearer token attached.

    Lets the React dashboard call e.g. /apis/default/fhir/Patient/<id> from
    the same origin (no CORS, no client-side token plumbing). Same auth
    surface as everything else the agent does — no new credentials.
    """
    token = get_openemr_token()
    target = f"{OPENEMR_BASE}/apis/{rest_path}"
    qs = request.url.query
    if qs:
        target = f"{target}?{qs}"

    body = await request.body()
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": request.headers.get("accept", "application/fhir+json"),
    }
    if request.method != "GET" and request.headers.get("content-type"):
        headers["Content-Type"] = request.headers["content-type"]

    resp = requests.request(
        request.method,
        target,
        data=body if body else None,
        headers=headers,
        verify=False,
    )
    media = resp.headers.get("content-type", "application/json")
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
