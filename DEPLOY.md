# DEPLOY.md — full step-by-step deployment guide

This walks through deploying the OpenEMR clinical co-pilot from a fresh
laptop to a publicly-reachable URL. Tested on macOS 14+ (Apple Silicon &
Intel). Linux works with minor swaps (`launchd` → `systemd`).

There are four moving pieces and they all need to come up:

```
  ┌──────────────┐    ┌─────────────────┐    ┌──────────────┐
  │  OpenEMR     │    │  FastAPI agent  │    │  React       │
  │  (PHP+MySQL) │    │  (LangGraph,    │    │  dashboard   │
  │  in docker   │◀──▶│   /chat, /apis) │───▶│  (built into │
  │  port 9300   │    │  port 8000      │    │  agent/dist) │
  └──────────────┘    └─────────────────┘    └──────────────┘
         ▲                     ▲
         │ ngrok               │ ngrok
         ▼                     ▼
  backlog-troubling-       agent-copilot.
  unfold.ngrok-free.dev    ngrok-free.dev
```

---

## 1. Prerequisites

| Tool | Version | Why |
|---|---|---|
| **Docker Desktop** | 4.x+ | Runs OpenEMR + MariaDB |
| **Python** | 3.9+ | The agent (FastAPI + LangGraph) |
| **Node.js** | 18+ | Building the React dashboard |
| **ngrok** | 3.x | Exposing both services publicly |
| **git** | any | Cloning the repo |

Accounts needed:
- **Anthropic API key** — https://console.anthropic.com/ (the agent uses Claude Sonnet 4.5 + Haiku 4.5)
- **ngrok account** — https://dashboard.ngrok.com/ (Hobby plan or higher; the reserved domains in `deploy/ngrok.yml` were registered on the project's account)

Optional: **Cohere API key** for the higher-quality reranker
(falls back to a local `sentence-transformers/cross-encoder/ms-marco-MiniLM-L-6-v2`
model when `COHERE_API_KEY` is unset, so this is not required to run the system).

---

## 2. Clone the repo

```sh
git clone https://github.com/heilashahidi/openemr.git
cd openemr
```

---

## 3. Bring up OpenEMR (Docker)

OpenEMR runs in a docker compose stack that ships with the repo. From the
repo root:

```sh
cd docker/development-easy
docker compose up --detach --wait
```

This pulls the OpenEMR + MariaDB images on first run (~5 min) and then
starts them. When it finishes, OpenEMR is reachable at:

- `http://localhost:8300/` (HTTP) — for the web UI
- `https://localhost:9300/` (HTTPS) — for FHIR & REST API access

Default login: `admin` / `pass`.

Verify:
```sh
curl -sI http://localhost:8300/ | head -1
# HTTP/1.1 200 OK
```

If MariaDB takes a while to initialize, the first request may time out;
wait 30 seconds and retry. The `--wait` flag waits for healthchecks but
the OpenEMR PHP app does additional setup work after the container is
"healthy."

---

## 4. Set up the FastAPI agent

```sh
cd ../../agent
python3 -m venv .venv          # optional but recommended
source .venv/bin/activate
pip install -r requirements.txt
```

Create `agent/.env` with your secrets:

```sh
cat > .env <<EOF
ANTHROPIC_API_KEY=sk-ant-...
OPENEMR_BASE=https://localhost:9300
OPENEMR_CLIENT_ID=...
OPENEMR_CLIENT_SECRET=...
# Optional: COHERE_API_KEY=...
EOF
```

The OpenEMR OAuth client ID & secret come from registering the agent as
an OAuth2 client inside OpenEMR. Quick path:

1. Log into OpenEMR (`http://localhost:8300/`, admin/pass).
2. Admin → System → API Clients → Register New App.
3. Set redirect URI to `http://localhost:8000/oauth-callback` (any URL works
   since we use the password grant, not the auth-code flow).
4. Set scopes to: `openid api:fhir user/Patient.read user/Condition.read user/MedicationRequest.read user/AllergyIntolerance.read user/Encounter.read user/Observation.read user/Coverage.read user/Immunization.read user/DocumentReference.read user/Binary.read user/CareTeam.read`
5. Copy the client ID and client secret into `agent/.env`.

Approve the client by running the SQL update OpenEMR's admin docs describe,
or via the Admin → System → API Clients UI (toggle "Enabled" on the new
client).

---

## 5. Build the React dashboard

```sh
cd ../dashboard
npm install
npm run build
```

This produces `dashboard/dist/` which the agent serves at `/dashboard/`.
Verify the build succeeded:

```sh
ls dist/
# index.html  assets/
```

The agent serves these files via `StaticFiles` at runtime — no separate
web server is needed.

---

## 6. Seed the four sample patients

The repo includes 8 fixture documents (4 patients × intake form + lab
result) in `agent/sample_docs/`. Ingest them into OpenEMR:

```sh
cd ../agent
python3 ingest_to_openemr.py
python3 backfill_family_history.py
python3 backfill_address_and_lab_notes.py
python3 backfill_citations.py
```

The ingest is idempotent — re-running it skips already-loaded documents
(keyed on `documents.name`).

Verify in MariaDB:

```sh
docker compose -f ../docker/development-easy/docker-compose.yml exec -T mysql \
  mariadb -uroot -proot openemr \
  -e "SELECT pid, fname, lname, pubpid FROM patient_data WHERE pid IN (10,11,12,13);"
```

You should see Chen / Whitaker / Reyes / Kowalski with MRNs populated.

---

## 7. First-run smoke test (local, no tunnels)

Start the agent:

```sh
python3 -m uvicorn app:app --port 8000
```

In another terminal, hit each surface:

```sh
# Health
curl -s http://localhost:8000/health

# Dashboard SPA
curl -sI http://localhost:8000/dashboard/ | head -1

# /chat with a real patient (Whitaker pid=11)
curl -s -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"patient_id":"d4067fd9-4791-11f1-a9e7-1a2e75d5087f",
       "message":"List this patient'\''s allergies.",
       "conversation_history":[]}' | head -c 400
```

If `/chat` returns a JSON body with `response`, `tools_called`, and
`claims`, the system is working end-to-end locally.

---

## 8. Run the eval suite (optional, ~12 min)

Confirms the 58 boolean-rubric checks pass on your install:

```sh
python3 eval_clinical_graph.py
# Expect: 58/58 passed (100.0%) in ~700-800s
```

CI runs the same suite on every push to `agent/**`.

---

## 9. Expose to the internet (ngrok)

The repo's `deploy/ngrok.yml` defines both tunnels in one file with
**reserved domains** so the URLs don't change between restarts.

```sh
mkdir -p ~/.config/ngrok
cp deploy/ngrok.yml ~/.config/ngrok/ngrok.yml
# Edit ~/.config/ngrok/ngrok.yml — replace REPLACE_ME with your ngrok
# auth token (https://dashboard.ngrok.com/get-started/your-authtoken).
# If you want different domains, change them here AND reserve them in the
# ngrok dashboard first.

ngrok start --all
```

You should see two tunnels come online:

```
backlog-troubling-unfold.ngrok-free.dev → https://localhost:9300  (OpenEMR)
agent-copilot.ngrok-free.dev            → http://localhost:8000   (Agent)
```

The dashboard is reachable at:

```
https://agent-copilot.ngrok-free.dev/dashboard/?patient=<fhir-uuid>
```

The chat UI is at:

```
https://agent-copilot.ngrok-free.dev/ui
```

OpenEMR is at:

```
https://backlog-troubling-unfold.ngrok-free.dev/
```

---

## 10. Make it survive reboots

`ngrok start --all` runs in the foreground — closing the terminal kills
the tunnel. To make both layers auto-start on login and auto-restart on
crash, see **`deploy/README.md`** for the full launchd setup. Quick
version:

```sh
# Run ngrok as a service
ngrok service install --config ~/.config/ngrok/ngrok.yml
sudo ngrok service start

# Run the agent as a launchd agent
cp deploy/launchd/com.openemr.agent.plist ~/Library/LaunchAgents/
sed -i '' "s|REPO_ROOT_HERE|$(pwd)|g" \
  ~/Library/LaunchAgents/com.openemr.agent.plist
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.openemr.agent.plist

# Set Docker Desktop to "Open at Login" in System Settings → Login Items
# Set the laptop to never sleep when plugged in:
sudo pmset -c sleep 0 disablesleep 1
```

Verify after a reboot: `curl -s http://localhost:8000/health` returns
`{"status":"ok"}` without you starting anything manually.

---

## 11. End-to-end verify the deployed URL

```sh
HDR="ngrok-skip-browser-warning: 1"
BASE="https://agent-copilot.ngrok-free.dev"

# 1. Tunnel + bundle
curl -sI -H "$HDR" "$BASE/health" | head -1

# 2. SPA HTML
curl -s -H "$HDR" "$BASE/dashboard/?patient=d4067fd9-4791-11f1-a9e7-1a2e75d5087f" \
  | grep -oE '/dashboard/assets/[^"]+\.js'

# 3. FHIR proxy (Whitaker's chart)
curl -sI -H "$HDR" "$BASE/apis/default/fhir/Patient/d4067fd9-4791-11f1-a9e7-1a2e75d5087f" | head -1

# 4. Chat call
curl -s -H "$HDR" -X POST "$BASE/chat" \
  -H 'Content-Type: application/json' \
  -d '{"patient_id":"d4067fd9-4791-11f1-a9e7-1a2e75d5087f",
       "message":"List this patient'\''s allergies.",
       "conversation_history":[]}' | head -c 200
```

All four should succeed with 200/JSON responses.

---

## 12. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `curl http://localhost:8000/health` → connection refused | Agent not running | `python3 -m uvicorn app:app --port 8000` (or `launchctl kickstart -k gui/$UID/com.openemr.agent` if using launchd) |
| `https://agent-copilot.ngrok-free.dev/health` → 404 ERR_NGROK_3200 | ngrok tunnel not registered | `ngrok start --all` (or `sudo ngrok service start` if installed as service) |
| `https://agent-copilot.ngrok-free.dev/health` → TLS handshake error | ngrok edge transient failure | Wait a minute, retry. If persistent, restart the tunnel. |
| `/chat` returns "I cannot reach OpenEMR" | OpenEMR Docker stack down | `cd docker/development-easy && docker compose up --detach --wait` |
| `/chat` returns 401 | OAuth client not enabled, or scopes mismatch | Re-check Admin → System → API Clients in OpenEMR |
| Dashboard widgets show "Nothing Recorded" for everything | Patient hasn't been ingested | `python3 ingest_to_openemr.py` |
| Eval fails on `safe_refusal` cases with "Extra data" parse errors | Old `_parse_json` from before the Haiku migration | Pull the latest commits — the parse helper now uses `JSONDecoder.raw_decode` |
| OpenEMR demographics page returns 500 ("An error has occurred.") | `insurance_data.provider` set to a string instead of FK | Re-run ingest_to_openemr.py — the upsert now resolves provider to an integer FK |

For OpenEMR PHP errors, tail the log:

```sh
docker compose -f docker/development-easy/docker-compose.yml exec openemr /root/devtools php-log
```

For agent errors, tail the log:

```sh
tail -50 /tmp/openemr-agent.err.log    # if using launchd
# or just look at the terminal where uvicorn is running
```

---

## What's NOT in this guide

- **Production hardening** (TLS termination, secrets management, multi-tenant
  separation, audit logging beyond `clinical_logger`). The system is built
  for solo development and demo, not patient-facing production use.
- **Cloud deployment** (Render / Fly.io / a VPS). The system runs on a
  laptop; if you need always-on without the laptop being on, that's a
  separate migration and not yet documented.
- **HIPAA compliance**. The redaction layer in `clinical_logger` is a
  starting point; real PHI handling needs a BAA, encryption at rest,
  access controls, and audit you can prove to a regulator. None of that
  ships in this repo.
