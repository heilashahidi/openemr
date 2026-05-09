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
