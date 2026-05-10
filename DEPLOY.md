# DEPLOY.md

Three ways to evaluate the project. Pick one.

---

## A. Use the deployed URL (no install)

Open `https://openemr.146-190-75-148.sslip.io/`, log in `admin` / `pass`, search
for any of these patients:

- Margaret Chen
- James Whitaker
- Sofia Reyes
- Robert Kowalski

Open a patient → scroll past OpenEMR's PHP cards. You'll see two iframes:

- **React patient dashboard** — 12 widgets (Patient Header, Demographics,
  Medications, Allergies, Conditions, Encounters, Labs, Vitals, Insurance,
  Immunizations, Family History, Documents, Care Team)
- **AI co-pilot** — clinical chat with three-section evidence-separation,
  routing trace, and citation chips

Try a clinical question on Sofia Reyes: *"How should we tighten her glycemic
control?"* Then click **⚡ N tools** on the reply to see the supervisor →
worker handoff trace.

The deployment is a single $6/mo DigitalOcean droplet (Caddy + Docker
+ FastAPI agent) — survives reboots and crashes; no laptop dependency.

### Demo path (5-min walkthrough)

A single Sofia Reyes session that exercises every reviewer-graded
behavior in sequence. Each step calls out what to look at:

1. **Open the deployed app** → search **Sofia Reyes** → open her chart.
   Two iframes load: the React dashboard (left) and the AI co-pilot
   (right).
2. **Ingestion + EMR grounding.** The dashboard's 12 widgets are populated
   by [`ingest_to_openemr.py`](agent/ingest_to_openemr.py) running once at
   deploy time over the four PDFs in `agent/sample_docs/intake-forms/`.
   Click **Documents** widget → "View" any file → confirm bounding boxes
   render over the source PDF (proves bbox + source tracing land in
   `derived_fact_citations`).
3. **Retrieval + evidence separation.** In the chat, ask: *"How should we
   tighten her glycemic control?"* The answer renders in three sections
   (CHART FINDINGS / EVIDENCE / CONSIDERATIONS) with `[N]` citation chips
   throughout — proves the synthesis prompt enforces citation discipline
   and the management format keeps the answer as decision support, not
   an order.
4. **Citation source viewer.** Click any `[N]` chip → side panel slides
   open with the source PDF page and a colored bbox over the cited
   value. Re-click is instant (browser cache + agent-side LRU).
5. **Orchestration trace.** Click the **⚡ N tools** tag below the answer.
   Inline routing trace expands: `supervisor → chart_lookup (1.2s) → 
   supervisor → evidence_retriever (1.4s) → supervisor → finish (synth
   3.1s)`. Each handoff shows the supervisor's reasoning + per-step
   latency. **No LangSmith login required to see this.**
6. **Streaming.** Send a follow-up — *"What management changes would
   you recommend?"* — and watch the answer fill in token-by-token,
   not in one dump. Time-to-first-token ~3-8s.
7. **Eval gate** — open [`EVAL_RESULTS.md`](EVAL_RESULTS.md) for the
   per-bucket breakdown (58/58, six categories) and click the CI badge
   in [`README_W2.md`](README_W2.md) to confirm it's green on the
   latest commit. Branch protection on `master` makes the `eval` check
   required to merge — a regression in any bucket blocks the build.
8. **PHI-safe logs (if you want to verify directly).** SSH the droplet
   and `tail -1 /opt/openemr/agent/logs/encounters-$(date +%Y-%m-%d).jsonl`.
   You'll see `tool_sequence`, `latency_per_step_ms`, `tokens_used`,
   `cost_estimate_usd`, `retrieval_hits`, `extraction_confidence`,
   `eval_outcome` — and `[NAME]`, `[DATE]`, `[PHONE]` placeholders
   anywhere PHI would otherwise appear.

### Verifying (artifact links)

- **Eval gate** — 58/58 boolean rubrics, blocking in CI. See the badge at the top of [`README_W2.md`](README_W2.md), per-bucket detail in [`EVAL_RESULTS.md`](EVAL_RESULTS.md), per-case JSON in [`agent/eval_clinical_results.json`](agent/eval_clinical_results.json). Branch protection on `master` requires the `eval` check before merge.
- **LangSmith traces** — every chat call streams a supervisor→worker trace tree to https://smith.langchain.com/ (project `clinical-copilot`) when `LANGCHAIN_API_KEY` is set in the agent's `.env`. The same trace is visible inline via the chat UI's clickable **⚡ N tools** tag — no LangSmith login required.
- **PHI-safe encounter logs** — `agent/clinical_logger.py` writes a redacted JSONL record per turn (`tool_sequence`, `latency_per_step_ms`, `tokens_used`, `cost_estimate_usd`, `retrieval_hits`, `extraction_confidence`, `eval_outcome`). Verified by 10 `no_phi_in_logs` eval cases.

---

## B. Run it locally (~10 min)

Need: **Docker Desktop**, **Python 3.9+**, **Node 18+**, an **Anthropic API
key**.

```sh
git clone https://github.com/heilashahidi/openemr.git
cd openemr
cd docker/development-easy && docker compose up --detach --wait && cd ../..

cd agent
pip install -r requirements.txt
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
echo "OPENEMR_BASE=https://localhost:9300" >> .env
echo "OPENEMR_CLIENT_ID=..." >> .env       # registered via Admin → API Clients
echo "OPENEMR_CLIENT_SECRET=..." >> .env

cd ../dashboard && npm install && npm run build && cd ../agent

python3 ingest_to_openemr.py
python3 backfill_family_history.py
python3 backfill_address_and_lab_notes.py
python3 backfill_citations.py

python3 -m uvicorn app:app --port 8000
```

Open in browser:
- `http://localhost:8300/` — OpenEMR (admin/pass), then any of the 4 patients
- `http://localhost:8000/dashboard/?patient=<fhir-uuid>` — React dashboard
- `http://localhost:8000/ui` — AI co-pilot

Run the eval suite (58 cases, ~12 min):
```sh
python3 eval_clinical_graph.py
```

---

## C. Redeploy to your own VPS (cloud, always-on)

The deployed URL above is hosted on a single DigitalOcean droplet. The setup
is reproducible — recipe lives in `deploy/vps-runbook.md` and covers:

1. Spin up a droplet, point sslip.io subdomains at the IP (no DNS purchase
   needed)
2. Install Docker + Caddy + Node + Python venv
3. Clone the repo, bring up OpenEMR, build the dashboard, install the agent
4. Wipe DigitalOcean's broken default DNS, add 2 GB swap (TypeScript +
   Docker need it on a 1 GB droplet), enable `documents.id` AUTO_INCREMENT
   (OpenEMR omits it in this image)
5. Register an OpenEMR OAuth client via SQL (the UI requires a JWKS, which
   we don't need for password grant)
6. systemd service for the agent + Caddy reverse proxy with auto Let's
   Encrypt certs

End state: two stable URLs (`openemr.<IP>.sslip.io`, `agent.<IP>.sslip.io`)
that survive reboots, all from a single `~$6/mo` machine.

Stable laptop deployment instructions (launchd + ngrok service) live in
`deploy/README.md` for anyone who'd rather host on their own laptop.
