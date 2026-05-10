# README_W2.md — Clinical Co-Pilot, Week 2

[![Agent evals](https://github.com/heilashahidi/openemr/actions/workflows/agent-evals.yml/badge.svg?branch=master)](https://github.com/heilashahidi/openemr/actions/workflows/agent-evals.yml)

> Week 2 builds on the Week 1 sidecar with three structural pieces: a **document ingestion pipeline**, a **LangGraph supervisor** with three workers and explicit handoffs, and a **switch from patient-data RAG to external-corpus RAG**. Every derived fact is linked back to its source document via a sidecar citations table. A 58-case boolean-rubric eval suite gates regression in CI — see [`EVAL_RESULTS.md`](EVAL_RESULTS.md) for the latest run.

**Companion docs:** [`DEPLOY.md`](DEPLOY.md) (5-min walkthrough for graders), `ARCHITECTURE_W2.md` (the design narrative), `README_W1.md` (the Week 1 baseline this builds on).

**Deployed URLs (final submission):**
- OpenEMR + co-pilot: `https://openemr.146-190-75-148.sslip.io/`
- Agent direct (for SSE / smoke tests): `https://agent.146-190-75-148.sslip.io/`
- Login: `admin` / `pass`

Hosted on a single $12/mo DigitalOcean droplet (Caddy + Docker + systemd-managed FastAPI agent). Survives reboots, no laptop dependency. Reproducible from scratch via [`deploy/vps-runbook.md`](deploy/vps-runbook.md) + [`deploy/Caddyfile`](deploy/Caddyfile).

---

## Final-Submission Status

| Reviewer rubric | Status | Where to verify |
|---|---|---|
| Stable deployed app | ✅ | `https://openemr.146-190-75-148.sslip.io/` (single droplet, Caddy + systemd, survives reboot) |
| Reliable ingestion | ✅ | `agent/ingest_to_openemr.py` self-heals schema on startup; 4 patients seeded from `agent/sample_docs/intake-forms/` |
| Reliable retrieval | ✅ | 148-chunk index over 30 external guidelines; chunker filter drops metadata stubs (`fix(retrieval): drop title-only and citation-stub chunks`) |
| Supervisor + worker orchestration | ✅ | `agent/clinical_graph.py` LangGraph; routing trace inline via "⚡ N tools" chip in chat UI |
| Citation enforcement | ✅ | `[N]` markers + `claims[]` (5 required fields); side panel + bbox overlay on click |
| Eval thresholds + regression blocking | ✅ | `agent/eval_baseline.json`; **branch protection on `master` requires the `eval` check before merge** |
| Latest CI run | ✅ | **58/58 in 609.7s** on commit `7a14168b4` — [Agent evals · 25622649510](https://github.com/heilashahidi/openemr/actions/runs/25622649510) |
| PHI-safe logging | ✅ | `agent/clinical_logger.py` redacts before write; 10/10 `no_phi_in_logs` cases verify |
| Latency reduction | ✅ | Eval 770s → 591s; chat TTFT ~3-8s via SSE streaming; 60s FHIR cache; LRU rasterized-page cache |
| Runtime observability | ✅ | LangSmith traces (`clinical-copilot` project) on droplet + CI; encounter logs on disk |
| Retrieval grounding | ✅ | Hybrid BM25 + dense + diversify; cross-encoder fallback with `DISABLE_CROSS_ENCODER` opt-out for resource-constrained hosts |
| bbox + source tracing | ✅ | `derived_fact_citations.bbox_json` populated by `backfill_bboxes.py`; `/document/<id>/view` overlays in browser |

For the 5-min demo path that exercises every line of this table in sequence, see [`DEPLOY.md`](DEPLOY.md) → "Demo path".

---

## What's New in Week 2

| Piece | What it does |
|---|---|
| **Document ingestion** (`agent/ingest_to_openemr.py` + `document_extractor.py`) | Accepts a PDF/PNG, extracts structured JSON via Claude VLM, copies the source file into OpenEMR's document storage, writes facts into FHIR-exposed tables (prescriptions, lists, procedure_*, history_data, etc.), and links each fact back to its source via `derived_fact_citations`. |
| **LangGraph supervisor** (`agent/clinical_graph.py`) | A supervisor + three workers (`intake_extractor`, `evidence_retriever`, `chart_lookup`). Workers always return to the supervisor; every transition is logged in `state["handoffs"]`. The supervisor decides termination — workers don't. |
| **External-only RAG** (`agent/evidence_retriever.py` + `fetch_external_guidelines.py`) | The vector DB no longer indexes patient notes. It holds a 30-doc corpus fetched from OpenFDA (drug labels) and PubMed (guideline abstracts). 148 chunks indexed via hybrid BM25 (0.4) + dense (0.6) → cross-encoder reranker → same-source diversity cap. (Was 201 before the chunker filter dropped 53 title-only and citation-URL stubs that were gaming BM25 length normalization.) |
| **`/chat` rewired** (`agent/app.py`) | The existing `/chat` endpoint now invokes `clinical_graph.run()` behind the W1 OAuth gate. The iframe UI doesn't change. Token usage, total latency, and handoff trace surface in the response. |
| **React patient dashboard** (`dashboard/`) | Vite + React + TS port of OpenEMR's demographics view: 12 widgets (Demographics, Patient Header, Medications, Allergies, Conditions, Encounters, Labs, Vitals, Insurance, Immunizations, Family History, Documents, Care Team) backed by FHIR R4 + four agent endpoints. Embedded into OpenEMR's `demographics.php` via a same-origin iframe. |
| **Eval gate** (`agent/eval_clinical_graph.py` + CI) | 58 cases × boolean rubrics across 6 buckets. CI fails on regression below the per-bucket baseline. |

---

## Recent Improvements (Final-Submission Tightening)

Four reviewer-driven changes after the initial W2 build, all still 58/58 in eval:

| Improvement | Where | Eval impact |
|---|---|---|
| **Three-section evidence boundary** for clinical-management questions: `**CHART FINDINGS:**` / `**EVIDENCE:**` / `**CONSIDERATIONS FOR THE CLINICIAN:**`. Imperative verbs aimed at the patient are forbidden ("Start", "Stop", "Prescribe", "Add a", "Switch to", …); answers must end by deferring to the clinician. Auto-applied when the query matches management triggers ("should we", "what dose", "next step", "treat", "manage", …). | `clinical_graph.py` — `_MANAGEMENT_FORMAT`, `_is_management_question()`, `_ANSWER_SYSTEM` "EVIDENCE BOUNDARY" rule. | New `evidence_separation` bucket (8/8) — catches the soft over-recommendation pattern that the existing 10-case `safe_refusal` bucket missed. |
| **Routing transparency in the UI**: every assistant reply shows a clickable "⚡ N tools" tag that toggles a routing-trace panel listing each handoff (`→ from->to — reason   Nms`). New `⏱ N.Ns` total-latency tag. | `app.py` enriched `tools_called` shape; `chat.html` `_renderRoutingTrace()` + collapsible `.routing-trace` panel. | Display-only, no eval impact. |
| **Latency caps** — per-call SDK timeout (60s chat / 120s vision, `max_retries=1`) and 120s end-to-end wall-clock budget. Supervisor checks `deadline_ts` before each routing call; past it, forces `finish` and runs synthesis on whatever was collected. Synthesis catches `APITimeoutError`/`APIConnectionError` and returns a graceful message. | `clinical_graph.py` — `PER_CALL_TIMEOUT_S`, `TOTAL_BUDGET_S`, `state["deadline_ts"]`, `state["timed_out"]`. | F-07 (BNP-not-in-chart) went from 8070s → 12s. Full eval 690–770s end-to-end. |
| **Two-model split: Haiku 4.5 routes, Sonnet 4.5 writes** — supervisor routing decisions (one of three workers + a one-line reason) run on Haiku, which is ~3× faster than Sonnet for that micro-prompt. The synthesis call that produces the actual clinical answer still runs on Sonnet. `_parse_json` was hardened to use `JSONDecoder.raw_decode` because Haiku occasionally appends a short tail after the JSON. | `clinical_graph.py` — `ROUTING_MODEL = "claude-haiku-4-5-20251001"`, `_parse_json` rewritten. | Per supervisor call ~3s → ~1s. Management-question end-to-end ~33s → ~29s; lookup queries ~12s → ~6s. Full eval 770s → 690s. |
| **Retrieval quality** — 12-group synonym expansion (lipid, anticoagulation, diabetes, …) finds chunks that don't lexically match the query (e.g. a "statin" question lights up `fda_drug_atorvastatin.md`). Hard 2-per-source diversity cap so the LLM never sees three chunks from one FDA label when the corpus has 30 docs. | `evidence_retriever.py` — `_SYNONYM_GROUPS`, `_expand_query()`, `_diversify()`. | Same eval pass-rate, qualitatively more diverse evidence in retrieval traces. |
| **Chunker filter** — drops 53 of 201 chunks (title-only Introduction, citation-URL Source) that gamed BM25 length normalization and outranked substantive sections. Metformin "Contraindications" went from out-of-top-10 to top 5 for the relevant query. | `evidence_retriever.py` — `_is_substantive()`, `_MIN_CHUNK_WORDS`. | Same 58/58, retrieval grounding visibly more on-topic. |
| **`/chat/stream` SSE streaming** — tokens flow into the chat bubble live (~3-8s time-to-first-token vs the prior ~20s wait-then-dump). Caddy `flush_interval -1` + `X-Accel-Buffering: no` prevent proxy buffering. The synchronous `/chat` endpoint still exists for callers that need a single JSON blob. | `app.py` — `/chat/stream` + `synthesize_stream` + `run_for_stream`; `chat.html` lazy-bubble streaming reader; `deploy/Caddyfile` flush + `/apis/*` bypass. | No eval impact (eval calls graph directly). |
| **Multi-layer caching** — agent-side 60s TTL on `GET /apis/*` (FHIR proxy, makes second visits to a patient instant); LRU on rasterized PDF pages + path lookups; browser `Cache-Control: immutable` for source documents; `DISABLE_CROSS_ENCODER` env flag bypasses the slow CPU reranker on resource-constrained hosts. | `app.py` — `_fhir_cache_*`, `_render_pdf_page_png`, `_resolve_document_path_cached`; `evidence_retriever.py` reranker branch. | Retrieval 21s → 0.16s with the env flag set. Dashboard re-render 5-10s → ms-range on cache hit. |
| **Branch-protected eval gate** — `master` now requires the `eval` CI check to pass before merge; force-pushes blocked, deletions blocked. Earlier "blocking" was honor-system; now it's enforceable. | GitHub branch protection rule on `master`. | Gate now blocks unsafe merges, not just conventions. |

---

## Quick Start

### Prerequisites
Same as W1, plus:
- `langgraph` (in `agent/requirements.txt`)
- `chromadb` (in `agent/requirements.txt`)
- An ANTHROPIC_API_KEY with VLM access (extraction uses Claude vision)

### 1. Bring up OpenEMR + agent (same as W1)
```bash
cd docker/development-easy && docker-compose up -d
cd ../../agent && pip install -r requirements.txt && cp env.example .env && source .env
python3 -m uvicorn app:app --port 8000
```

### 2. Refresh the external corpus (one-time, then cached)
The vector DB indexes `agent/external_corpus/*.md`. Those 30 files are committed as a snapshot, but you can refetch them from FDA + PubMed at any time:

```bash
cd agent && python3 fetch_external_guidelines.py
```

### 3. Ingest the four sample patients (one-time)
This creates Chen / Whitaker / Reyes / Kowalski (pids 10–13) with full chart data and citations:

```bash
cd agent
python3 ingest_to_openemr.py
python3 backfill_family_history.py
python3 backfill_address_and_lab_notes.py
python3 backfill_citations.py
```

The ingestion is **idempotent** — re-running it is a no-op for already-ingested files.

### 4. Make it reachable

Three ways, in order of how the project is actually deployed:

- **Stable VPS (final-submission target):** see [`deploy/vps-runbook.md`](deploy/vps-runbook.md) for the DigitalOcean + Caddy + sslip.io recipe. Drops the canonical Caddyfile from [`deploy/Caddyfile`](deploy/Caddyfile) so SSE streaming works through the iframe path.
- **Local laptop, always-on:** see [`deploy/README.md`](deploy/README.md) for launchd + ngrok service.
- **Ad-hoc tunnel for a quick demo:**
  ```bash
  ngrok http https://localhost:9300
  ngrok http 8000
  ```

### 5. Open in the browser

For the deployed app (final submission): `https://openemr.146-190-75-148.sslip.io/`, log in `admin` / `pass`, search **Sofia Reyes** (or Margaret Chen, James Whitaker, Robert Kowalski). Open the patient → two iframes load (React dashboard + AI co-pilot). Try *"How should we tighten her glycemic control?"* and click **⚡ N tools** to see the routing trace. Full 5-min demo path in [`DEPLOY.md`](DEPLOY.md).

---

## The Multi-Agent Graph

```
                  ┌─────────────────────┐
                  │     supervisor      │  decides next handoff each turn
                  │  (Claude, JSON out) │  inspects state.{file, patient_id,
                  └──────────┬──────────┘                extraction, chart, evidence}
                             │
        ┌────────────────────┼────────────────────┬──────────────────┐
        ▼                    ▼                    ▼                  ▼
 ┌─────────────┐    ┌────────────────┐   ┌──────────────────┐    ┌─────┐
 │  intake_    │    │  evidence_     │   │  chart_lookup    │    │ END │
 │  extractor  │    │  retriever     │   │  (W2 patient     │    │     │
 │             │    │                │   │   chart fetch)   │    └─────┘
 │  VLM extract│    │ Hybrid RAG     │   │                  │       ▲
 │  PDF / PNG  │    │ over external  │   │ MariaDB JOIN     │       │
 │             │    │ corpus         │   │ + citations      │     finish
 └──────┬──────┘    └───────┬────────┘   └────────┬─────────┘       │
        └───────────────────┴─────────────────────┘                 │
                            │                                       │
                            ▼                                       │
                       supervisor ──────────────────────────────────┘
                            │  (re-invoked after every worker)
                            ▼
                      _synthesize_answer
                     (separate LLM call,
                      sees full state, hardened
                      prompt: cite or refuse)
```

A typical clinical-question trace is 5 hops: `supervisor → chart_lookup → supervisor → evidence_retriever → supervisor → finish`. Every hop is recorded in `state["handoffs"]` with from/to/reason.

---

## Data-Store Boundary

| What | Where | Read by |
|---|---|---|
| **Patient-derived facts** (demographics, labs, meds, allergies, conditions, encounters, history, insurance) | OpenEMR MariaDB tables (FHIR-exposed) | `chart_lookup` worker |
| **Source-document provenance** | `derived_fact_citations` sidecar table | JOIN'd into chart_lookup rows |
| **Clinical reference text** | ChromaDB collection `clinical_guidelines` | `evidence_retriever` worker |
| **PHI in vector DB** | **None** — enforced by eval case C-11 | n/a |

Eval case C-11 walks `clinical_graph.py`'s import graph to confirm `rag.py` (the legacy W1 module that chunks patient notes into ChromaDB) is not pulled in, and that the only ChromaDB collection at runtime is `clinical_guidelines`. CI fails if anyone re-introduces patient-data-in-vector-DB.

---

## File Inventory (Week 2)

```
agent/
├── clinical_graph.py             — supervisor + 3 workers + answer synthesis
├── evidence_retriever.py         — hybrid RAG over external_corpus
├── document_extractor.py         — Claude VLM-based PDF/PNG → structured JSON
├── schemas.py                    — Pydantic schemas for extraction
├── ingest_to_openemr.py          — writes facts + citations into MariaDB
├── fetch_external_guidelines.py  — FDA + PubMed API fetcher
│
├── external_corpus/              — 30 .md files (cached external snapshot)
│     fda_drug_*.md (20)          — OpenFDA drug labels
│     pubmed_*.md  (10)           — PubMed guideline abstracts
├── sample_docs/                  — 4 fixture PDFs/PNGs (intake + lab × 4 patients)
│
├── eval_clinical_graph.py        — 58-case boolean-rubric suite
├── eval_baseline.json            — per-category pass-count gate
│
├── chat.html                     — embedded co-pilot UI with routing-trace panel
├── backfill_*.py                 — idempotent backfills for already-ingested data
└── copy_docs_to_storage.py       — physical-file copy into OpenEMR storage

dashboard/                          — React port of OpenEMR demographics view
├── src/api/fhir/                  — typed FHIR fetchers + 4 agent endpoints
│     patient.ts, allergy.ts, condition.ts, medication.ts, encounter.ts,
│     lab.ts, vital.ts, coverage.ts, immunization.ts, family.ts,
│     careteam.ts, document.ts
├── src/widgets/                   — 12 cards (one per FHIR resource)
└── src/App.tsx                    — sticky PatientHeader + grid of cards

.github/workflows/
└── agent-evals.yml               — spins up MariaDB, seeds 4 patients,
                                    runs eval, fails on regression
```

---

## Eval Suite (58/58 passing)

6 buckets, all boolean rubrics:

| Bucket | Cases | What it tests | Determinism |
|---|---|---|---|
| `schema_valid` | 10 | `extract_document()` returns expected verbatim values from each sample lab/intake doc | LLM (VLM, temp 0) |
| `citation_present` | 10 | `derived_fact_citations` rows exist for every fact-bearing table for the four ingested patients; data-store boundary holds | Pure SQL + import-graph walk |
| `factually_consistent` | 10 | Top-1 retrieved file matches expected, and graph acknowledges absent values rather than fabricating | LLM + pure code |
| `safe_refusal` | 10 | Graph declines unsafe / out-of-scope prompts (jailbreak, off-topic, "write a prescription", "order a surgery") | LLM |
| `no_phi_in_logs` | 10 | Encounter logs scrub PHI; required structured fields (tool_sequence, latency_per_step_ms, tokens_used, cost_estimate_usd, retrieval_hits) are present | LLM + log assertion |
| `evidence_separation` *(new)* | 8 | In-scope clinical-management questions present three-section answers without imperative commands. Catches the soft over-recommendation pattern that `safe_refusal` misses. | LLM |

Run locally:
```bash
cd agent && python3 eval_clinical_graph.py
# Writes eval_clinical_results.json. Exits non-zero if any bucket regresses.
```

---

## CI Workflow (`.github/workflows/agent-evals.yml`)

Triggers on pushes/PRs touching `agent/**`. The workflow:

1. Sets up Python 3.11, installs `agent/requirements.txt`.
2. Brings up `docker/development-easy` compose stack (MariaDB + OpenEMR), waits for healthy.
3. Verifies `agent/external_corpus/` is committed (cached snapshot — no live API calls).
4. Runs the four ingestion scripts to seed the four sample patients with citations.
5. Runs `eval_clinical_graph.py` — exits non-zero on regression.
6. Uploads `eval_clinical_results.json` as an artifact.

Requires `ANTHROPIC_API_KEY` as a repo secret (extraction, refusal, missing-data buckets need it). `LANGCHAIN_API_KEY` is forwarded too so CI runs trace into the same `clinical-copilot` LangSmith project as local + droplet runs (treated as optional — forks without the secret still run the eval, just without traces).

**Branch protection:** the `eval` job is a required status check on `master`. Force-pushes and branch deletions are blocked. A regression below any bucket's `min_threshold` (or >5% off baseline) makes the build red and prevents merge — the gate is enforceable, not honor-system.

---

## What Week 2 Does NOT Include

- **Write capabilities from agent prompts.** The graph is read-only. The ingestion pipeline writes (it has to), but it runs as a deliberate batch operation.
- **The Week 1 RAG-over-clinical-notes path.** `rag.py`, `tools.py:search_notes`, and the W1 system prompt are still in the repo for the legacy `/chat` behavior, but `clinical_graph.py` does not import them — and CI enforces that.
- **Auto-fetching the corpus in CI.** The 30 external docs are committed to the repo so CI doesn't depend on FDA / PubMed API uptime. Refresh locally with `python3 fetch_external_guidelines.py`.

---

## Documentation

| Document | Description |
|---|---|
| `ARCHITECTURE_W2.md` | Full Week 2 architecture (graph, ingestion, citations, RAG, eval, CI, defending-this-architecture FAQ) |
| `ARCHITECTURE_W1.md` | The Week 1 baseline this builds on |
| `README_W1.md` | Week 1 setup + capabilities |
| `AUDIT.md` | OpenEMR integration audit (still applies) |
| `USERS.md` | Target user + 8 use cases (still applies) |

---

## End-to-End Verification (what to expect in the iframe)

After the steps above, open the iframe drawer and pick **Whitaker** from the patient picker. Click "Brief me." You should see:

```
**TODAY:** Visit on 2026-04-21 for fatigue and one episode of dizziness... (source: p02-whitaker-intake.pdf, "...")
**CHANGES:** First documented visit.
**ACTIVE CONDITIONS:** Atrial fibrillation (on anticoagulation), essential hypertension, hyperlipidemia, BPH.
**KEY MEDICATIONS:** Apixaban 5 mg twice daily; atorvastatin 40 mg at bedtime; tamsulosin 0.4 mg daily.
**ALLERGIES:** NKDA (source: p02-whitaker-intake.pdf, "NKDA (No known drug allergies)").
**LABS:** Hemoglobin 11.1 g/dL (L), hematocrit 33.5% (L)... (source: p02-whitaker-cbc.pdf)
**KEY POINTS:** ... mild normocytic anemia ... iron studies, ferritin, reticulocyte count, stool occult blood ...
```

Total: ~150 words, 7 sections in W1 order, inline `(source: ..., "...")` on every patient-specific value, citation chip count > 0.

For seeded patients (Smith, Cramer, Lane, Nakamura, etc.) the same template applies, but inline citations are absent (those patients weren't ingested through the W2 pipeline so they have no document-level provenance) and the citation chip count is 0.
