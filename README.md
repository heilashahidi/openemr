# Clinical Co-Pilot — OpenEMR AI Agent

> An AI-powered clinical co-pilot embedded in OpenEMR that gives primary care physicians pre-room briefings, answers follow-up questions, and searches clinical notes — every claim cited to a FHIR record.

**Deployed URLs:**
- OpenEMR: `https://backlog-troubling-unfold.ngrok-free.dev`
- Agent: `https://agent-copilot.ngrok-free.dev`
- Login: `admin` / `pass`

---

## Quick Start

### Prerequisites
- Docker + Docker Compose
- Python 3.9+
- ngrok (hobby plan for two tunnels)
- Anthropic API key
- LangSmith API key

### 1. Start OpenEMR
```bash
cd docker/development-easy
docker-compose up -d
# Wait 60 seconds for initialization
curl -ks https://localhost:9300/interface/login/login.php | head -3
```

### 2. Start the Agent
```bash
cd agent
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
source .env && export OPENEMR_BASE OPENEMR_CLIENT_ID OPENEMR_CLIENT_SECRET ANTHROPIC_API_KEY
export LANGCHAIN_TRACING_V2=true
export LANGCHAIN_API_KEY=your-langsmith-key
export LANGCHAIN_PROJECT=clinical-copilot
python3 -m uvicorn app:app --port 8000
```

### 3. Expose via ngrok
```bash
# Terminal 2
ngrok http https://localhost:9300 --url backlog-troubling-unfold.ngrok-free.dev

# Terminal 3
ngrok http 8000 --url agent-copilot.ngrok-free.dev
```

### 4. Open in browser
- Go to `https://backlog-troubling-unfold.ngrok-free.dev`
- Log in → open any patient → click the red ⚕️ button

---

## Week 1 — Baseline Agent

The Week 1 agent provides a conversational AI co-pilot for PCPs with structured FHIR tools and RAG.

### Capabilities
- **Pre-room briefing** — auto-generated when a patient is selected (UC1)
- **Factual lookup** — "What medications is this patient on?" (UC2)
- **Mid-visit pivot** — "Has she ever mentioned chest pain?" (UC3)
- **Post-visit recap** — "Summarize the last three visits" (UC4)
- **Clinical history search** — RAG semantic search via ChromaDB (UC5)
- **Cross-domain reasoning** — "What in their history might explain leg swelling?" (UC6)
- **New patient handling** — honest silence on empty charts (UC7)
- **Safety guardrails** — declines to prescribe or diagnose (UC8)

### Architecture
Sidecar pattern: Python FastAPI agent alongside OpenEMR, connected via FHIR R4 API + OAuth2.

### 7 Tools
| Tool | Type | What it does |
|---|---|---|
| `get_patient_summary` | FHIR | Demographics |
| `get_active_conditions` | FHIR | Problem list |
| `get_active_medications` | FHIR | Current meds |
| `get_allergies` | FHIR | Allergy list |
| `get_recent_encounters` | FHIR | Visit history |
| `get_recent_labs` | FHIR | Lab results |
| `search_notes` | RAG | Semantic note search (ChromaDB) |

### Eval Results (Week 1)
- Core suite: 29/30 (96.7%) — tool selection, citation, content, negative validation
- RAG suite: 18/18 (100%) — RAG-only, hybrid, silence handling
- **Combined: 47/48 (97.9%)**

### Key Files
| File | Purpose |
|---|---|
| `agent/app.py` | FastAPI service, /chat endpoint |
| `agent/tools.py` | 7 FHIR + RAG tools |
| `agent/rag.py` | ChromaDB RAG module |
| `agent/verification.py` | Citation + hallucination checks |
| `agent/chat.html` | Chat UI with auto-briefing |
| `agent/eval_suite.py` | 30-test core eval suite |
| `agent/test_rag.py` | 18-test RAG eval suite |
| `AUDIT.md` | OpenEMR integration audit |
| `ARCHITECTURE.md` | System architecture |
| `USERS.md` | Target user + 8 use cases |
| `EVAL_RESULTS.md` | Formatted eval results + cost analysis |

---

## Week 2 — Multimodal Evidence Agent

Week 2 extends the agent with document ingestion, multi-agent routing, and eval-driven CI.

### New Capabilities
- **Document ingestion** — upload lab PDFs and intake forms, extract structured data with VLM
- **Multi-agent graph** — supervisor routes to intake-extractor and evidence-retriever workers
- **Hybrid RAG + rerank** — clinical guideline corpus with keyword + dense retrieval
- **Eval-driven CI gate** — 50-case golden set with boolean rubrics, blocks regressions

### Running Week 2 Flow

```bash
# Same setup as above, plus:
pip install langgraph reportlab

# Generate sample documents
python3 agent/create_sample_docs.py

# Run the Week 2 agent (same command — Week 2 tools are added to the existing agent)
cd agent
python3 -m uvicorn app:app --port 8000

# Test document extraction
curl -s -X POST http://localhost:8000/extract \
  -F "file=@sample_docs/sample_lab_report.pdf" \
  -F "patient_id=fbaa4958-437f-11f1-9821-62123fdb3c0f" \
  -F "doc_type=lab_pdf" | python3 -m json.tool

# Run Week 2 evals
python3 eval_w2.py
```

### Week 2 Environment Variables
Same as Week 1. No additional environment variables required.

### Week 2 Key Files
| File | Purpose |
|---|---|
| `agent/document_extractor.py` | VLM-based PDF/image extraction |
| `agent/schemas.py` | Pydantic schemas for lab_pdf + intake_form |
| `agent/supervisor.py` | Multi-agent supervisor + worker graph |
| `agent/evidence_retriever.py` | Guideline RAG with reranking |
| `agent/create_sample_docs.py` | Sample document generator |
| `agent/eval_w2.py` | 50-case Week 2 eval suite |
| `W2_ARCHITECTURE.md` | Week 2 architecture document |
| `sample_docs/` | Sample lab PDFs and intake forms |

### Week 2 Schemas
**Lab PDF** (`LabPDFExtraction`): test_name, value, unit, reference_range, collection_date, abnormal_flag, source_citation

**Intake Form** (`IntakeFormExtraction`): demographics, chief_concern, current_medications, allergies, family_history, social_history, review_of_systems, source_citation

---

## Documentation

| Document | Description |
|---|---|
| [AUDIT.md](AUDIT.md) | OpenEMR security, performance, architecture, data quality, compliance audit |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Week 1 system architecture with RAG, verification, observability |
| [W2_ARCHITECTURE.md](W2_ARCHITECTURE.md) | Week 2 multimodal architecture — ingestion, workers, eval gate |
| [USERS.md](USERS.md) | Target user (PCP), 8 use cases, traceability table |
| [EVAL_RESULTS.md](EVAL_RESULTS.md) | Eval results with cost projections |

---

## Deployment

### Demo (Current)
- OpenEMR: Docker Compose (`docker/development-easy/`) → ngrok tunnel
- Agent: Python/uvicorn → ngrok tunnel
- 4 terminals required: Docker, agent, ngrok×2

### Production Path
See [ARCHITECTURE.md §12](ARCHITECTURE.md) for full production deployment plan including containerization, pgvector, self-hosted Langfuse, and scaling to 300 concurrent clinicians.

---

## Cost

| Scale | Queries/day | Daily cost |
|---|---|---|
| 1 PCP | 60 | $0.84 |
| 10 PCPs | 600 | $8.40 |
| 100 PCPs | 6,000 | $84.00 |
| Hospital (300 PCPs) | 18,000 | $252.00 |
