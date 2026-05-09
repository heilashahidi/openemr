# DEPLOY.md

Two ways to evaluate the project. Pick one.

---

## A. Use the deployed URL (no install)

Open `https://backlog-troubling-unfold.ngrok-free.dev/`, log in with
`admin` / `pass`, search for any of these four patients:

- Margaret Chen
- James Whitaker
- Sofia Reyes
- Robert Kowalski

Open the patient — scroll down past OpenEMR's cards. You'll see two
iframes: the **React patient dashboard** (12 widgets) and the **AI
co-pilot** (clinical chat with routing trace).

That's the full demo. Try a clinical question in the co-pilot, e.g.
*"How should we tighten her glycemic control?"* on Sofia Reyes, then
click **⚡ N tools** on the reply to see the supervisor → worker trace.

---

## B. Run it locally (~10 min)

You need: **Docker Desktop**, **Python 3.9+**, **Node 18+**, an
**Anthropic API key**.

```sh
# 1. Clone
git clone https://github.com/heilashahidi/openemr.git
cd openemr

# 2. Bring up OpenEMR (PHP + MariaDB)
cd docker/development-easy
docker compose up --detach --wait
cd ../..

# 3. Set up the agent
cd agent
pip install -r requirements.txt
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
echo "OPENEMR_BASE=https://localhost:9300" >> .env
echo "OPENEMR_CLIENT_ID=..." >> .env       # Admin → System → API Clients
echo "OPENEMR_CLIENT_SECRET=..." >> .env

# 4. Build the React dashboard (the agent serves it)
cd ../dashboard && npm install && npm run build && cd ../agent

# 5. Seed the four sample patients
python3 ingest_to_openemr.py
python3 backfill_family_history.py
python3 backfill_address_and_lab_notes.py
python3 backfill_citations.py

# 6. Start the agent
python3 -m uvicorn app:app --port 8000
```

Open in browser:
- `http://localhost:8300/` — OpenEMR (admin/pass), then any of the 4 patients
- `http://localhost:8000/dashboard/?patient=<fhir-uuid>` — React dashboard alone
- `http://localhost:8000/ui` — AI co-pilot alone

Run the eval suite to verify (58 cases, ~12 min):
```sh
python3 eval_clinical_graph.py
```

---

## Stable public deployment

The deployed URL above is hosted on the project laptop via ngrok. To
make both tunnels and the agent auto-restart on crash and survive
laptop reboots, see **`deploy/README.md`** for the launchd + ngrok
service config — relevant if you're redeploying on your own machine
or want to harden this one.
