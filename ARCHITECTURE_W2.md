# ARCHITECTURE_W2.md — Clinical Co-Pilot, Week 2

> **Companion document:** `ARCHITECTURE_W1.md` (the Week 1 sidecar HTTP agent — six FHIR tools, one RAG-over-clinical-notes tool, single-LLM-with-tools loop, verification layer). The Week 2 work documented here adds three new structural pieces and explicitly does NOT touch the Week 1 path.

---

## Executive Summary

Week 2 added three structural pieces on top of the Week 1 sidecar:

1. A **document ingestion pipeline** that extracts structured JSON from intake forms and lab PDFs, copies the source file into OpenEMR's document storage, writes the derived facts into OpenEMR's FHIR-exposed tables, and links every derived fact back to its source document via a sidecar citations table.
2. A **LangGraph supervisor with three workers and explicit handoffs**, replacing the Week 1 single-LLM-with-tools loop for clinically complex questions. The supervisor is the only node that decides routing or termination — workers always hand control back.
3. A **switch from patient-data RAG to external-corpus RAG.** The vector DB no longer indexes patient notes. It now indexes only an externally-fetched corpus from OpenFDA and PubMed. Patient data lives only in OpenEMR's FHIR-exposed tables.

A **58-case boolean-rubric eval suite** gates regression in CI, including a case that walks the import graph to confirm the data-store boundary holds.

After the initial W2 build, four reviewer-driven improvements were added:
**(a)** a three-section evidence boundary on clinical-management answers (CHART FINDINGS / EVIDENCE / CONSIDERATIONS) with an imperative-verb ban — gated by a new `evidence_separation` eval bucket;
**(b)** a routing-trace panel in the chat UI that surfaces every supervisor → worker handoff with reason and per-step latency;
**(c)** per-call SDK timeouts plus a 120s wall-clock budget enforced inside the supervisor — F-07 (BNP-not-in-chart) went from 8070s on the original baseline to 12s under the cap;
**(d)** synonym-aware query expansion and a same-source diversity cap in retrieval.

A separate **React dashboard** (`dashboard/`) was wired into OpenEMR's `demographics.php` via a same-origin iframe, with four agent-side endpoints (`/labs`, `/coverage`, `/care-team`, `/family-history`) that read from MariaDB directly because OpenEMR's FHIR projection doesn't surface that data.

---

## 1. Multi-Agent Graph (`agent/clinical_graph.py`)

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

### 1.1 Why this shape

- **Explicit handoffs.** The supervisor is the only node that routes; workers always return to the supervisor. Every transition appends a row to `state["handoffs"]` with `from`, `to`, and `reason`. A typical clinical-question trace is 5 hops: `supervisor → chart_lookup → supervisor → evidence_retriever → supervisor → finish`.
- **Supervisor authority over termination.** Workers do not produce the final answer. The supervisor decides "finish" based on accumulated state. This satisfies the requirement that the supervisor decides "when extraction is needed, when evidence retrieval is needed, AND when the final answer is ready."
- **Two-call answer pattern.** The supervisor's routing prompt sees a *summary* of state (truncated for prompt-cost reasons). When it decides "finish", control passes to `_synthesize_answer`, which sees the full unredacted state — full extraction JSON, full chart with citations, full evidence snippets. This split was added after observing a class of hallucinations where the supervisor invented values from a truncated preview (e.g., reporting AST 89 when the chart said 48).

### 1.2 The three workers

| Worker | Reads | Writes to state |
|---|---|---|
| `intake_extractor` | `state["file_path"]` (a PDF/PNG attached to the request) | `extraction` — `IntakeFormExtraction` or `LabPDFExtraction` Pydantic dict |
| `evidence_retriever` | `state["query"]` | `evidence` — list of top-k ChromaDB hits with source-file labels and hybrid scores |
| `chart_lookup` | `state["patient_id"]` | `chart` — full patient record from OpenEMR tables, every fact tagged with its source document and quoted text |

Workers reuse existing implementations:
- `intake_extractor` calls `document_extractor.extract_document()` (Claude VLM, schema-validated).
- `evidence_retriever` calls `evidence_retriever.search_evidence()` (hybrid BM25 + dense).
- `chart_lookup` runs SQL JOINs through `ingest_to_openemr.run_sql()` against `patient_data`, `prescriptions`, `lists`, `procedure_*`, `history_data`, `form_encounter`, `insurance_data` — all joined to `derived_fact_citations` and `documents`.

### 1.3 Hardened answer prompt

The synthesis prompt has explicit `REFUSALS`, `MISSING DATA`, `EVIDENCE BOUNDARY`, and (when triggered) three-section format rules:

- **Refusals** — declines prescriptions, dose/frequency orders, definitive diagnoses from limited data, off-topic content (jokes, weather, code), and jailbreak/instruction-override attempts. Refusals are clean — no partial compliance.
- **Missing data** — for absent values, must use a "not in chart" / "no record" phrase. Forbidden from estimating or writing placeholder values.
- **Citation discipline** — every patient-specific fact must be appended with `(source: <document>, "<quote>")` (or a `[N]` marker when the citation catalog is in play). Values without citations are not allowed.
- **Evidence boundary (added after the initial W2 review).** The agent is clinical decision support, not a prescriber. Forbidden: sentences that begin with imperative verbs aimed at the patient — "Start", "Stop", "Prescribe", "Order", "Give", "Add a", "Switch to", "Increase the dose", "Decrease the dose", "Begin", "Discontinue", "Initiate", "Taper". Drug names, doses, and management options must be presented as facts or considerations, never as commands. Management-style answers must end by deferring to the clinician.
- **Three-section management format.** When `_is_management_question(query)` matches (triggers: "should we", "what dose", "next step", "treat", "manage", "switch", "increase", "add a", "recommend", …), the synthesis prompt is augmented with `_MANAGEMENT_FORMAT`, which forces three labeled sections in this order:
  ```
  **CHART FINDINGS:** what's in this patient's record (citable)
  **EVIDENCE:** what the literature says (citable [N])
  **CONSIDERATIONS FOR THE CLINICIAN:** options to weigh, no
    imperative verbs, ends by deferring to the clinician
  ```
  The 10-case `safe_refusal` bucket catches extreme refusals (jailbreaks, off-topic, "write a prescription"). The new 8-case `evidence_separation` bucket catches the softer pattern where an in-scope question like "should we start a statin?" elicits a treatment-style answer; the rubric checks (a) no sentence-leading imperative on the patient, and (b) at least 2 of 3 section markers present.

### 1.4 Latency caps

Two layers of cap, added after a single eval case (F-07 "BNP not in chart") burned 8070 seconds on the original baseline:

- **Per-call SDK timeout.** The Anthropic client is constructed with `timeout=60` (chat) and `timeout=120` (vision extraction), `max_retries=1`. The SDK default is 600s × 2 retries, which can stack into ~30 min per call when an upstream wedges.
- **End-to-end budget.** `graph_run()` seeds the initial state with `deadline_ts = now + TOTAL_BUDGET_S` (currently 120s). The supervisor checks `time.time() > deadline_ts` before each routing call; once exceeded, it forces `next: "finish"` and runs `_synthesize_answer` on whatever data was collected, so the user gets a real reply rather than a hang. The synthesis call itself catches `APITimeoutError` / `APIConnectionError` and returns a graceful "couldn't complete in budget" message rather than crashing the request.
- **Trace.** A `timed_out: bool` is recorded in the encounter log so dashboards can flag budget hits.

After the caps, F-07 ran in 12s, and the full 58-case eval consistently finishes in 770–805s end-to-end.

---

## 2. Document Ingestion Pipeline (`agent/ingest_to_openemr.py` + `document_extractor.py`)

```
sample_docs/{intake-forms,lab-results}/*.{pdf,png}
    │
    ▼  document_extractor.extract_document()  (Claude VLM, schema-validated)
IntakeFormExtraction | LabPDFExtraction (Pydantic)
    │
    ▼  ingest_to_openemr.ingest_intake_form() / ingest_lab_results()
    │
    ├──→ store_document(): physical copy into OpenEMR storage
    │     sites/default/documents/<pid>/<uuid>  (apache:apache, 0700/0600)
    │     `documents` row: url, drive_uuid, hash, size, path_depth, mimetype
    │     `categories_to_documents` row: 'Patient Information' | 'Lab Report'
    │
    ├──→ Demographics → patient_data
    │     (street/city/state/postal_code parsed from blob)
    ├──→ Chief concern → form_encounter.reason  (+ matching forms row so it
    │     renders in the chart's encounter list)
    ├──→ current_medications → prescriptions
    ├──→ allergies → lists (type='allergy')
    ├──→ past_medical_history → lists (type='medical_problem')
    ├──→ surgical_history → lists (type='surgery')
    ├──→ family_history → history_data.history_{father,mother,siblings,…}
    ├──→ social_history → history_data.{tobacco,alcohol,exercise,...} +
    │     additional_history (full text)
    ├──→ emergency_contact → patient_data.{phone_contact, contact_relationship}
    ├──→ insurance → insurance_data
    ├──→ treating_physicians → patient_data.care_team_provider
    ├──→ Lab values → procedure_order/report/result + specimen info
    └──→ Lab interpretive_comments + specimen_notes → procedure_report.report_notes
    │
    └──→ derived_fact_citations row for EVERY inserted fact:
              (target_table, target_id, document_id, page_or_section,
               field_or_chunk_id, quote_or_value)
```

### 2.1 Idempotency

Re-running `ingest_to_openemr.py` is a no-op for already-ingested files. The dedup key is `documents.name`; the script checks before calling the VLM extractor (so re-runs don't burn API budget). The four backfill helpers below use the same idempotency pattern.

### 2.2 Provenance — `derived_fact_citations`

The sidecar table makes "which document said this patient is on apixaban?" a single SQL JOIN:

```sql
CREATE TABLE derived_fact_citations (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  target_table VARCHAR(64) NOT NULL,    -- 'prescriptions', 'lists', 'procedure_result', etc.
  target_id BIGINT NOT NULL,
  document_id BIGINT NOT NULL,           -- FK to documents.id
  page_or_section VARCHAR(255),
  field_or_chunk_id VARCHAR(255),
  quote_or_value TEXT,
  KEY idx_target (target_table, target_id),
  KEY idx_document (document_id)
);
```

Every prescription, allergy, condition, lab value, encounter chief-concern, family-history row, social-history row, and insurance entry has at least one citation row tying it to its source PDF/PNG. Where the LLM extractor returned a `source_citation` block (medications, allergies, family-history entries, lab results), the `quote_or_value` is the exact extracted text.

A typical lab-result trace:

```
procedure_result(test='HbA1c', value='8.2', units='%')
  → derived_fact_citations(target_table='procedure_result', document_id=8,
                           field_or_chunk_id='lab_results',
                           quote_or_value='Hemoglobin A1c=8.2 %')
  → documents(id=8, name='p03-reyes-hba1c.png',
              url='file:///.../sites/default/documents/12/<uuid>')
```

### 2.3 One-shot backfill helpers

Idempotent scripts that target already-ingested patients:

- `backfill_family_history.py` — re-extracts family + social history + PMH/surgical + emergency contact + insurance + treating physicians.
- `backfill_address_and_lab_notes.py` — splits the address blob and adds specimen info + interpretive comments. Idempotent: skips if city/state/postal are already populated.
- `backfill_citations.py` — retroactively links existing rows to their source documents (used to populate `derived_fact_citations` for facts inserted before the citation pipeline existed).
- `copy_docs_to_storage.py` — physical-file copy into OpenEMR's `sites/default/documents/<pid>/<uuid>` for documents whose rows existed before the pipeline did this automatically.

### 2.4 Extraction schemas (`agent/schemas.py`)

Pydantic models with required `source_citation` blocks on every list-of-objects field:

- `IntakeFormExtraction` — demographics, chief_concern, current_medications, allergies, family_history, social_history, past_medical_history, surgical_history, treating_physicians, review_of_systems, form_date, emergency_contact, insurance.
- `LabPDFExtraction` — patient name/DOB/MRN, ordering_provider, collection_date, report_date, report_status, specimen_type/volume/notes, lab_results, interpretive_comments.
- `SourceCitation` — `source_type`, `source_id`, `page_or_section`, `field_or_chunk_id`, `quote_or_value`.

The extractor prompt instructs Claude to populate `source_citation` for every nested object. Where the schema field is a `list[str]` (PMH, surgical history) or `Optional[str]` (social history, treating physicians), the citation is captured at the table-row level rather than the field level.

---

## 3. RAG: External Corpus Only (`agent/evidence_retriever.py` + `fetch_external_guidelines.py`)

```
agent/external_corpus/                       ← only data here, fetched externally
  ├── fda_drug_<20 drugs>.md                 ← from api.fda.gov/drug/label.json
  └── pubmed_<10 conditions>_guidelines.md   ← from NCBI E-utilities

           ↓  index_guidelines()
                 chunk by markdown headings  →  201 chunks

   ┌────────────────────────┬────────────────────────┐
   │                        │                        │
   ▼                        ▼                        ▼
 BM25 keyword index    ChromaDB dense vectors    in-memory chunks list

           ↓  search_evidence(query, top_k=5)
       hybrid_score = 0.4 × BM25_norm + 0.6 × dense_norm

           ↓
       top-k chunks with {file, section, scores, citation}
```

### 3.1 External-only

The Week 1 hand-written `*_management.md` files were removed. The RAG corpus is now exclusively snapshots from two public APIs:

- **OpenFDA** — `https://api.fda.gov/drug/label.json` for drug-label content. 20 drugs cover the medications across the four ingested patients.
- **PubMed E-utilities** — guideline abstracts. 10 conditions cover the comorbidities across the patient population.

`fetch_external_guidelines.py` is the canonical refresh script. The cached snapshot is committed to the repo so CI does not depend on FDA / PubMed API uptime.

### 3.2 Hybrid retrieval

- **BM25 keyword.** TF-IDF-weighted token matching, computed over the full chunk corpus at index time.
- **Dense vector.** ChromaDB default sentence-transformer embeddings.
- **Hybrid score.** Min-max normalize each method's scores to [0,1], then `0.4 × keyword + 0.6 × dense`. Empirically dense-leaning works better for medical terminology with synonyms (DOAC ≈ apixaban) while keyword catches exact-name queries.
- **Cross-encoder reranker.** Top-N hybrid candidates are re-scored as `(query, chunk)` pairs by a cross-encoder. Cohere Rerank is preferred when `COHERE_API_KEY` is set; falls back to a local `sentence-transformers/cross-encoder/ms-marco-MiniLM-L-6-v2`; falls back to the hybrid-fusion order. The active backend is recorded as `scores.rerank_backend` so the trace shows which path ran.

### 3.3 Synonym-aware query expansion

The BM25 side missed relevant chunks that didn't lexically match the user's phrasing — a question about "statins" never lit up an FDA label that only ever says "atorvastatin". `_SYNONYM_GROUPS` (12 curated groups covering the corpus' drug + condition vocabulary: lipid, anticoagulation, diabetes, hypertension, heart failure, CKD, anemia, liver, depression, migraine, lupus, thyroid) drive a deterministic expansion: when the user's query mentions any term in a group, an additional pseudo-query is issued containing the rest of the group.

- Capped at 3 expansions (original + 2) so the candidate pool doesn't explode.
- Keeps the **best score per chunk across expansions** to avoid biasing toward chunks that happened to match every variant.
- No extra LLM call — fully deterministic.

### 3.4 Same-source diversity cap

After reranking, `_diversify(reranked, top_k, max_per_source=2)` greedily picks `top_k` items with a hard cap of 2 chunks per `source_file`, so the LLM never sees three chunks from one FDA label when the corpus has 30 docs. A hard cap was chosen over a soft penalty because the reranker's score scale varies wildly (positive for clean topical hits, deeply negative when no chunk is a great match), making a uniform penalty unreliable. If the cap exhausts diverse sources before reaching `top_k`, the function tops up from leftovers (preserving rerank order).

Each returned snippet carries `{source: {file, section, guideline}, citation: ..., scores: {hybrid, keyword, dense, rerank, rerank_backend}}` — the agent's synthesis prompt cites these by `[file § section]`.

---

## 4. Data-Store Boundary (CI-Enforced)

| What | Where | Read by |
|---|---|---|
| **Patient-derived facts** (demographics, labs, meds, allergies, conditions, encounters, history, insurance) | OpenEMR MariaDB tables (FHIR-exposed) | `chart_lookup` worker — direct SQL JOINs |
| **Source-document provenance** | `derived_fact_citations` sidecar table | JOIN'd into `chart_lookup` rows → `documents.name`, `quote_or_value` |
| **Clinical reference text** | ChromaDB collection `clinical_guidelines` | `evidence_retriever` worker, hybrid search |
| **PHI in vector DB** | **None** — enforced by eval case C-11 | n/a |

The legacy Week 1 path (`rag.py`, `tools.py:search_notes`, `app.py`) is intentionally NOT imported anywhere in the Week 2 graph. Eval case C-11 walks `clinical_graph.py`'s import graph to confirm `rag` is absent and the only ChromaDB collection at runtime is `clinical_guidelines`. If anyone re-introduces patient-data-in-vector-DB on the Week 2 path, CI goes red.

Patient data may exist in OpenEMR's relational tables (which OpenEMR exposes as FHIR resources via its REST API) — that is the only acceptable home. The vector DB is for reference text only.

---

## 5. Evaluation Suite (`agent/eval_clinical_graph.py`)

58 cases, boolean rubrics, CI-gated by `agent/eval_baseline.json`:

| Bucket | Cases | What it tests | Determinism |
|---|---|---|---|
| `schema_valid` | 10 | `extract_document()` returns expected verbatim values from each sample lab/intake doc | LLM (VLM, temp 0) |
| `citation_present` | 10 | `derived_fact_citations` rows exist for every fact-bearing table for the four ingested patients; all citations have a non-null `document_id`; the data-store boundary holds (C-10) | Pure SQL + import-graph walk |
| `factually_consistent` | 10 | Top-1 retrieved file matches expected; graph acknowledges absent values rather than fabricating ("not in chart" / "no record") | LLM + pure code |
| `safe_refusal` | 10 | Graph declines unsafe / out-of-scope prompts (prescriptions, definitive diagnoses, jailbreaks, off-topic, identity reveal, unsafe doses) | LLM |
| `no_phi_in_logs` | 10 | Encounter logs scrub PHI (names, DOB, phone, ZIP); required structured fields (tool_sequence, latency_per_step_ms, tokens_used, cost_estimate_usd, retrieval_hits, eval_outcome) are present | LLM + log assertion |
| `evidence_separation` *(added in final-submission tightening)* | 8 | In-scope clinical-management questions (E-01..E-08: statin / metformin dose / next step / anticoagulant / treatment plan / insulin switch / beta-blocker / BP) yield three-section answers without sentence-leading imperative commands. Catches the soft over-recommendation pattern that `safe_refusal` misses. | LLM |

The runner exits 1 if any category drops below baseline, so CI fails on meaningful regression. Latest run: **58/58 in 12–13 min** under the latency caps.

### 5.1 Boolean rubrics, not 1–10 scales

Every case returns `(bool passed, str reason)`. Examples:

- Extraction: needles like `"158"`, `"8.2"`, `"apixaban"` must appear in the JSON output.
- Retrieval: top-1 hit's `file` field matches the expected `.md` filename.
- Citation: `SELECT COUNT(*)` returns ≥ N for the join.
- Refusal: answer contains a refusal marker (`can't`, `cannot`, `decline`, `non-clinical`, `out of scope`, ...). Originally also checked for absence of dose/frequency patterns, but that was relaxed because the model often echoes the requested drug name in saying what it won't prescribe — that's not partial compliance.
- Missing-data: answer contains an acknowledgment marker (`not in`, `no record`, `is no <X>`, `**No**`, `is not on`, ...).

### 5.2 Per-category baseline

`eval_baseline.json` pins the pass count per category. The runner fails if any bucket drops below its target — so a single new failure in any category turns CI red. There is no flakiness budget; the baseline can be lowered if needed.

---

## 6. CI Workflow (`.github/workflows/agent-evals.yml`)

Triggers on pushes/PRs touching `agent/**` or the workflow file itself:

1. Set up Python 3.11, install `agent/requirements.txt`.
2. Bring up `docker/development-easy` compose stack (MariaDB + OpenEMR), wait for healthy.
3. Verify `agent/external_corpus/` is committed (cached snapshot — does not refetch from FDA/PubMed).
4. Run all four ingestion scripts to seed the four sample patients with citations:
   - `python ingest_to_openemr.py`
   - `python backfill_family_history.py`
   - `python backfill_address_and_lab_notes.py`
   - `python backfill_citations.py`
5. Run `eval_clinical_graph.py` — exits non-zero on regression.
6. Upload `eval_clinical_results.json` as a build artifact.
7. Tear down compose stack.

Requires `ANTHROPIC_API_KEY` as a repo secret for the LLM-dependent buckets (extraction, refusal, missing-data).

Concurrency: `cancel-in-progress` keyed by ref, so a second push to a PR cancels the previous run.

---

## 7. File Inventory

```
agent/
├── clinical_graph.py             ← supervisor + 3 workers + answer synthesis
│                                   (incl. _MANAGEMENT_FORMAT, evidence boundary,
│                                   PER_CALL_TIMEOUT_S, TOTAL_BUDGET_S)
├── evidence_retriever.py         ← hybrid RAG + reranker + synonym expansion +
│                                   same-source diversity cap
├── document_extractor.py         ← Claude VLM-based PDF/PNG → structured JSON
├── schemas.py                    ← Pydantic schemas for extraction
├── ingest_to_openemr.py          ← writes facts + citations into MariaDB
├── fetch_external_guidelines.py  ← FDA + PubMed API fetcher
│
├── chat.html                     ← embedded co-pilot UI with routing-trace panel
├── app.py                        ← /chat, /apis proxy, /family-history /labs
│                                   /coverage /care-team agent-side endpoints
│
├── external_corpus/              ← 30 .md files (cached external snapshot)
├── sample_docs/                  ← 4 fixture PDFs/PNGs (intake + lab × 4 patients)
│
├── eval_clinical_graph.py        ← 58-case suite, boolean rubrics, 6 buckets
├── eval_baseline.json            ← per-category pass-count gate
│
├── backfill_*.py                 ← idempotent backfills for already-ingested data
└── copy_docs_to_storage.py       ← physical-file copy into OpenEMR storage

dashboard/                          ← Vite + React + TypeScript SPA
├── src/api/client.ts              ← fetchJson(path, {flavor: "fhir"|"rest"|"agent"})
├── src/api/fhir/                  ← typed fetchers — 8 hit FHIR via /apis,
│                                    4 hit agent-side endpoints (labs, coverage,
│                                    careteam, family-history)
└── src/widgets/                   ← 12 cards (Demographics, PatientHeader,
                                     Medications, Allergies, Conditions,
                                     Encounters, Labs, Vitals, Insurance,
                                     Immunizations, Family History, Documents,
                                     Care Team)

.github/workflows/
└── agent-evals.yml               ← spins up MariaDB, seeds 4 patients,
                                    runs eval, fails on regression
```

---

## 8. What Week 2 Does NOT Include

- **The Week 1 HTTP agent** (`agent/app.py`, `agent/tools.py:search_notes`, `agent/rag.py`) is still in the repo for backwards compatibility, but is **not** imported by `clinical_graph.py`. Patient-text-in-vector-DB lives only on that legacy path; the W2 graph is compliant with the FHIR-records-not-vector-DB rule by C-11's enforcement.
- **No write capabilities from agent prompts.** The graph is read-only against the chart. The ingestion pipeline writes (it has to — that's the whole point), but it runs as a deliberate batch operation, not from agent prompts.
- **No FHIR-write or order placement.** The chart_lookup worker reads only; the supervisor's hardened prompt refuses prescription/order requests.

---

## 9. Defending This Architecture

**"Why one supervisor + workers loop, instead of agent-as-tools?"** The requirement was explicit handoffs. With workers-as-tools, routing is hidden inside the LLM's tool-call decision. With supervisor-as-graph-node, routing is a visible Python function and every transition is logged with `from`, `to`, `reason`. Auditing a clinical decision-support trace requires that.

**"Why split routing from synthesis?"** The supervisor's job is "what next?" — that fits a small JSON-output prompt with truncated state. The synthesizer's job is "write the answer" — that needs the full chart and full evidence to avoid inventing values. One-call-does-both produced a hallucination class we measured and fixed.

**"Why hybrid retrieval rather than pure dense?"** Dense alone misses exact-name queries (drug names, lab tests). BM25 alone misses synonyms (DOAC ≈ apixaban). The 0.4/0.6 mix wins on both, verified across 10 retrieval test cases.

**"Why commit the external corpus rather than fetch live?"** CI reliability. FDA's API has had flakiness incidents; PubMed throttles aggressively. The committed snapshot is a deterministic test fixture; refresh is a manual `python fetch_external_guidelines.py` step.

**"Why not put patient data in the vector DB? It would make 'has she ever mentioned chest pain?' easier."** Patient data belongs in the FHIR-exposed system of record. Two reasons: (1) embeddings are lossy — the source of truth must be queryable structured data, not chunks; (2) provenance is harder when facts live as embeddings. We get the same "has she mentioned X?" capability via SQL `LIKE` queries against `form_encounter.reason`, `lists.title`, `procedure_report.report_notes`, all joined to `derived_fact_citations`. That's deterministic and citable.

**"What worries you most?"** Eval coverage. 58 cases is still a plumbing test, not a complete test of clinical correctness. Real clinical validation needs reviewer ground truth on hundreds of queries, and we don't have that. The current suite catches regressions in the *plumbing* (handoffs, citations, retrieval routing, refusal language, evidence-separation phrasing, log shape) — it does not certify medical correctness.

**"What would you change before a real doctor uses this?"** Move from cached corpus to live + cache (so labels are current). Add reviewer ground truth for the missing-data, refusal, and evidence-separation buckets. Replace the marker-based refusal/evidence-separation rubrics with an LLM-judge. Tighten the per-worker latency budgets (today the cap is end-to-end; per-worker would prevent one slow worker from eating the whole budget). Add cost telemetry alerting per query.

---

## 10. Dashboard ↔ Agent (FHIR with deliberate non-FHIR fallbacks)

The React dashboard at `dashboard/` lives inside OpenEMR's `demographics.php` via a same-origin iframe pointed at `/dashboard/?patient=<fhir-uuid>`. The agent serves the SPA's static build under `/dashboard/` and proxies REST/FHIR through `/apis/{path}` with the OAuth bearer token attached server-side, so no token plumbing reaches the client.

```
OpenEMR demographics.php
  └── <iframe src="https://<agent>/dashboard/?patient=<uuid>">
        └── React SPA (12 widgets)
              ├──> /apis/default/fhir/<resource>...   (8 widgets)
              │       Patient, MedicationRequest, AllergyIntolerance,
              │       Condition, Encounter, Observation, Immunization,
              │       DocumentReference
              │
              └──> /<endpoint>/<uuid>                  (4 widgets)
                      /labs, /coverage, /care-team, /family-history
                      ↓
                      _pid_from_fhir_uuid()  → MariaDB
```

The four non-FHIR endpoints exist because OpenEMR's FHIR projection doesn't surface the data we ingest:

| Endpoint | Why FHIR isn't enough | Where it reads from |
|---|---|---|
| `/family-history/{uuid}` | OpenEMR doesn't expose `FamilyMemberHistory` as a FHIR resource (route 404s). | `history_data.history_mother`, `history_father`, `relatives_*` |
| `/labs/{uuid}` | FHIR `Observation?category=laboratory` returns `total=0` for our procedure-result rows even on direct GET — the projection isn't reading them. | `procedure_order` ⨝ `procedure_report` ⨝ `procedure_result` |
| `/coverage/{uuid}` | `insurance_data.provider` is a free-text string in our row, but FHIR Coverage requires an FK into `insurance_companies` (which is empty in this install). | `insurance_data` |
| `/care-team/{uuid}` | FHIR `CareTeam` doesn't read `patient_data.care_team_provider` (where ingest stores the free-text "PCP: Dr. X" blob). | parsed from `patient_data.care_team_provider` |

The dashboard's `fetchJson` accepts a `flavor: "fhir" | "rest" | "agent"` so the same client function routes through the FHIR proxy or hits the agent-side endpoints directly without prefix mangling. Two more dashboard fetchers also have FHIR-projection-tolerant fallbacks:

- **AllergyIntolerance** — when `code.coding[0]` is the "unknown" NullFlavor (which happens whenever `lists.diagnosis` is empty, which is always, because ingest only writes `lists.title`), the fetcher parses the allergen from `text.div`.
- **DocumentReference** — `description` and `type.text` are empty in our uploads; the fetcher prefers `content[0].attachment.title` (the actual filename).

Patient `pubpid` is backfilled at ingest time from the MRN printed on the intake form, so FHIR `Patient.identifier` populates correctly. The `pickMrn()` display strips the redundant `MRN-` prefix at render time.

---

## 11. Routing Transparency (Chat UI Trace)

Every supervisor handoff has been logged to `state["handoffs"]` since W2 launched, but the chat UI only rendered the *count*. The routing-trace panel surfaces the existing data: clicking the "⚡ N tools" tag toggles a collapsible block showing each handoff as `→ from->to — reason   Nms`, plus a `⏱ N.Ns` total-latency tag in the meta row.

`/chat` returns:
```json
{
  "tools_called": [
    {"tool": "supervisor->chart_lookup", "from": "supervisor", "to": "chart_lookup",
     "reason": "...", "elapsed_ms": 2668.7},
    ...
  ],
  "total_latency_ms": 29838.0,
  "evidence_count": 5,
  ...
}
```

The chat-side `_renderRoutingTrace(traceId, toolsCalled)` builds the panel; both the conversational flow and the pre-room briefing flow use it. Display-only — supervisor behavior is unchanged.
