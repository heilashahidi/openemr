# README_W1.md — Clinical Co-Pilot, Week 1

> An AI-powered clinical co-pilot embedded in OpenEMR that gives primary care physicians pre-room briefings, answers follow-up questions, and searches clinical notes — every claim cited to a FHIR record.

**Companion docs:** `ARCHITECTURE_W1.md` (system architecture), `README_W2.md` (the Week 2 work that builds on this).

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
- LangSmith API key (optional, for tracing)

### 1. Start OpenEMR
```bash
cd docker/development-easy
docker-compose up -d
# Wait ~60 seconds for initialization
curl -ks https://localhost:9300/interface/login/login.php | head -3
```

### 2. Start the Agent
```bash
cd agent
pip install -r requirements.txt
cp env.example .env
# Edit .env with your API keys
source .env
python3 -m uvicorn app:app --port 8000
```

### 3. Expose via ngrok
```bash
# Terminal 2 — OpenEMR
ngrok http https://localhost:9300 --url backlog-troubling-unfold.ngrok-free.dev

# Terminal 3 — Agent
ngrok http 8000 --url agent-copilot.ngrok-free.dev
```

### 4. Open in browser
- Go to `https://backlog-troubling-unfold.ngrok-free.dev`
- Log in → open any patient → click the floating ⚕️ button

---

## What Week 1 Provides

A conversational AI co-pilot for PCPs with structured FHIR tools and RAG over clinical notes. Every claim cites a FHIR resource UUID; a verification layer flags responses without citations.

### Capabilities (the 8 use cases)
- **UC1 — Pre-room briefing:** auto-generated when a patient is selected
- **UC2 — Factual lookup:** "What medications is this patient on?"
- **UC3 — Mid-visit pivot:** "Has she ever mentioned chest pain?"
- **UC4 — Post-visit recap:** "Summarize the last three visits"
- **UC5 — Clinical history search:** RAG semantic search via ChromaDB
- **UC6 — Cross-domain reasoning:** "What in their history might explain leg swelling?"
- **UC7 — New patient handling:** honest silence on empty charts
- **UC8 — Safety guardrails:** declines to prescribe or diagnose

### Architecture (sidecar)
Python FastAPI agent runs alongside OpenEMR and authenticates via OAuth2. Reads FHIR R4 resources (`Patient`, `Condition`, `MedicationRequest`, `AllergyIntolerance`, `Encounter`, `Observation`). Never writes to the chart. The only OpenEMR-side change is an iframe injection in `interface/patient_file/summary/demographics.php` that loads the chat UI.

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

### Verification layer
Every response is checked before the PCP sees it:
- **Citation completeness** — clinical claims must reference retrieved data
- **Hallucination patterns** — phrases like "I recommend prescribing" are flagged
- **Silence enforcement** — empty records are reported honestly, not filled
- Unverified responses get a warning badge in the UI

### Eval Results (Week 1)
- Core suite: 29/30 (96.7%) — tool selection, citation, content, negative validation
- RAG suite: 18/18 (100%) — RAG-only, hybrid, silence handling
- **Combined: 47/48 (97.9%)**

---

## Week 1 File Inventory

| File | Purpose |
|---|---|
| `agent/app.py` | FastAPI service, `/chat` and `/extract` endpoints |
| `agent/tools.py` | The 7 FHIR + RAG tool definitions and dispatcher |
| `agent/rag.py` | ChromaDB module that indexes patient encounter notes/conditions/meds |
| `agent/verification.py` | Citation + hallucination checks |
| `agent/chat.html` | Chat UI with auto-briefing (loaded into the demographics iframe) |
| `agent/eval_suite.py` | 30-test core eval suite |
| `agent/test_rag.py` | 18-test RAG eval suite |
| `agent/test_agent.py` | Smoke tests |
| `ARCHITECTURE_W1.md` | System architecture |
| `AUDIT.md` | OpenEMR integration audit |
| `USERS.md` | Target user + 8 use cases |
| `EVAL_RESULTS.md` | Formatted eval results + cost analysis |

---

## Documentation

| Document | Description |
|---|---|
| `ARCHITECTURE_W1.md` | Week 1 system architecture (sidecar, FHIR tools, RAG, verification, observability) |
| `AUDIT.md` | OpenEMR security, performance, architecture, data quality, compliance audit |
| `USERS.md` | Target user (PCP), 8 use cases, traceability table |
| `EVAL_RESULTS.md` | Eval results with cost projections |
| `README_W2.md` | The Week 2 follow-up |
| `ARCHITECTURE_W2.md` | Week 2 system architecture |

---

## Cost (Week 1, 7-tool agent + RAG)

| Scale | Queries/day | Daily cost |
|---|---|---|
| 1 PCP | 60 | $0.84 |
| 10 PCPs | 600 | $8.40 |
| 100 PCPs | 6,000 | $84.00 |
| Hospital (300 PCPs) | 18,000 | $252.00 |

---

## Note: Week 1 vs Week 2

The Week 1 path (`app.py` → `tools.py` + `rag.py`) chunks patient encounter notes into ChromaDB for RAG. **Week 2 replaces that with a different design** — patient data stays in OpenEMR's FHIR-exposed tables, and the vector DB holds only an external clinical corpus (FDA + PubMed). See `README_W2.md` for what changed and why.
