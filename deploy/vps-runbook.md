# deploy/vps-runbook.md — single-VPS deployment

End state: two stable HTTPS URLs (`openemr.<IP>.sslip.io`,
`agent.<IP>.sslip.io`), one $6/mo droplet, survives reboots and crashes.
This is the recipe used to deploy the live demo URL referenced in
`DEPLOY.md`.

The runbook is opinionated on a few quirks because each one bit during the
real deployment — read the **gotchas** sections rather than assuming
`docker compose up` Just Works.

---

## 1. Provision the VPS

| Provider | Tier | Note |
|---|---|---|
| DigitalOcean | $6/mo Regular Droplet | What the live demo runs on. 1 GB RAM is tight; add 2 GB swap (step 4). |
| Hetzner | CX22 (€3.79/mo, 4 GB RAM) | Cheaper, more headroom — recommended if you're paying. |
| Oracle Cloud | Always-Free VM.Standard.A1.Flex | Free tier; ARM though, so Docker images need `--platform linux/arm64` support. |

Pick **Ubuntu 24.04 LTS**. Add your SSH key during creation. SSH in:

```sh
ssh root@<your-ip>
```

The rest of this runbook assumes you're root on the droplet.

---

## 2. Base packages

```sh
apt update && apt upgrade -y
apt install -y ca-certificates curl gnupg git python3-venv python3-pip \
                python3.12-venv \
                debian-keyring debian-archive-keyring apt-transport-https
```

### Docker (use the convenience installer — the apt manual route was flaky)

```sh
curl -fsSL https://get.docker.com | sh
docker --version    # → Docker version 27.x.x
```

### Node 20 (NodeSource — Ubuntu's default `nodejs` ships an older `nodejs`
binary with no `node` symlink)

```sh
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs
node --version    # → v20.x.x
```

### Caddy (reverse proxy + auto Let's Encrypt)

```sh
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | tee /etc/apt/sources.list.d/caddy-stable.list
apt update && apt install -y caddy
```

### Firewall — only HTTP/HTTPS + SSH from the public side

```sh
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw --force enable
```

---

## 3. Fix the droplet's DNS (DigitalOcean-specific gotcha)

Fresh DO droplets sometimes ship with a broken `systemd-resolved` setup:
DNS works for ICMP / cached lookups but `nslookup` and `docker pull` time
out against `127.0.0.53`. Replace with static Cloudflare DNS:

```sh
chattr -i /etc/resolv.conf 2>/dev/null
rm -f /etc/resolv.conf
printf 'nameserver 1.1.1.1\nnameserver 8.8.8.8\n' > /etc/resolv.conf
chattr +i /etc/resolv.conf
```

Tell Docker daemon to use the same (Docker has its own resolver):

```sh
mkdir -p /etc/docker
printf '{"dns":["1.1.1.1","8.8.8.8"]}\n' > /etc/docker/daemon.json
systemctl restart docker
```

Verify:

```sh
nslookup registry-1.docker.io
docker pull hello-world
```

---

## 4. Add 2 GB swap (1 GB droplet runs out of RAM during `npm run build`)

```sh
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
free -h    # → Swap: 2.0Gi
```

Leave swap in place — it also helps the agent's first start (corpus
indexing peaks above the 1 GB ceiling).

---

## 5. Clone + bring up OpenEMR

```sh
cd /opt
git clone https://github.com/heilashahidi/openemr.git
cd openemr/docker/development-easy
docker compose up --detach --wait    # ~5–10 min on first run
docker compose ps                     # all containers should report "healthy"
```

OpenEMR is now reachable inside the droplet at `https://localhost:9300/`
(self-signed cert; that's expected — Caddy will terminate TLS publicly in
step 9).

### Build OpenEMR's CSS (gulp output, not committed in the repo)

The repo's `public/themes/` directory contains only SCSS sources; the
compiled CSS is generated at runtime. Run gulp inside the OpenEMR
container:

```sh
docker exec -it development-easy-openemr-1 sh -c \
  "cd /var/www/localhost/htdocs/openemr && npm install && npm run build"
```

This takes ~4 minutes; afterwards `https://localhost:9300/public/themes/style_light.css`
returns 200.

### Add `AUTO_INCREMENT` to `documents.id` (OpenEMR image bug)

This image ships with `documents.id` as `int(11) NOT NULL DEFAULT 0`,
**without** auto-increment. The first document insert lands at id=0 and
all subsequent inserts collide silently on the duplicate primary key —
which is why the ingest only creates one document on a fresh install
without this fix.

```sh
docker exec -i development-easy-mysql-1 mariadb -uroot -proot openemr \
  -e "ALTER TABLE documents MODIFY id INT(11) NOT NULL AUTO_INCREMENT"
```

### Create the `derived_fact_citations` sidecar table

The repo writes citations to this table during ingest, but the table
itself isn't in the OpenEMR base schema:

```sh
docker exec -i development-easy-mysql-1 mariadb -uroot -proot openemr -e "
CREATE TABLE IF NOT EXISTS derived_fact_citations (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  target_table VARCHAR(64) NOT NULL,
  target_id BIGINT NOT NULL,
  document_id BIGINT NOT NULL,
  page_or_section VARCHAR(255),
  field_or_chunk_id VARCHAR(255),
  quote_or_value TEXT,
  bbox_json TEXT,
  KEY idx_target (target_table, target_id),
  KEY idx_document (document_id)
);"
```

---

## 6. Build the dashboard + set up the agent

```sh
cd /opt/openemr/dashboard
npm install
npm run build    # produces dashboard/dist/

cd /opt/openemr/agent
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Create `agent/.env` (paste your secrets — `read -s` keeps the API key
hidden in scrollback):

```sh
read -s -p "Anthropic key: " KEY; echo
printf 'ANTHROPIC_API_KEY=%s\nOPENEMR_BASE=https://localhost:9300\nOPENEMR_CLIENT_ID=\nOPENEMR_CLIENT_SECRET=\n' "$KEY" > /opt/openemr/agent/.env
chmod 600 /opt/openemr/agent/.env
unset KEY
```

Leave `OPENEMR_CLIENT_ID` / `OPENEMR_CLIENT_SECRET` empty for now — step 8
fills them in.

---

## 7. Seed the four sample patients

```sh
cd /opt/openemr/agent
. .venv/bin/activate
set -a; . .env; set +a    # surface the env vars to the python process
python3 ingest_to_openemr.py
python3 backfill_family_history.py
python3 backfill_address_and_lab_notes.py
python3 backfill_citations.py
```

Verify:

```sh
docker exec -i development-easy-mysql-1 mariadb -uroot -proot openemr \
  -e "SELECT pid, fname, lname, pubpid FROM patient_data WHERE pid IN (10,11,12,13)"
```

You should see all four patients with MRN values.

---

## 8. Register an OpenEMR OAuth client (via SQL — the UI requires JWKS)

OpenEMR's API Client UI is geared toward SMART-on-FHIR's asymmetric auth
(JWKS URI required). For password grant, we don't need that — but the UI
still blocks you. Insert directly:

```sh
SECRET="clinicalcopilot$(openssl rand -hex 8)"
HASH=$(docker exec development-easy-openemr-1 php -r \
  "echo password_hash('$SECRET', PASSWORD_BCRYPT);")
CLIENT_ID="clinical-copilot-$(openssl rand -hex 4)"
SCOPES='openid api:fhir user/Patient.read user/Condition.read user/MedicationRequest.read user/AllergyIntolerance.read user/Encounter.read user/Observation.read user/Coverage.read user/Immunization.read user/DocumentReference.read user/Binary.read user/CareTeam.read'

docker exec -i development-easy-mysql-1 mariadb -uroot -proot openemr -e "
INSERT INTO oauth_clients (client_id, client_role, client_name, client_secret,
  redirect_uri, grant_types, scope, site_id, is_confidential, is_enabled)
VALUES ('$CLIENT_ID', 'users', 'Clinical Co-Pilot', '$HASH',
  'https://agent.<your-ip-with-dashes>.sslip.io/oauth-callback',
  'password refresh_token client_credentials',
  '$SCOPES', 'default', 1, 1);"

echo "OPENEMR_CLIENT_ID=$CLIENT_ID"
echo "OPENEMR_CLIENT_SECRET=$SECRET"
```

Copy the two values into `/opt/openemr/agent/.env`. Test the token endpoint
end-to-end before continuing — if it returns an `access_token`, you're
good:

```sh
curl -sk -X POST 'https://localhost:9300/oauth2/default/token' \
  -d "grant_type=password&username=admin&password=pass&user_role=users&scope=openid&client_id=$CLIENT_ID&client_secret=$SECRET"
```

---

## 9. systemd service for the agent

```sh
cat > /etc/systemd/system/openemr-agent.service <<'EOF'
[Unit]
Description=OpenEMR Clinical Co-Pilot agent
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/openemr/agent
EnvironmentFile=/opt/openemr/agent/.env
# Force unbuffered stdout so module-level print() output (LangSmith init
# banner, corpus-index banner) reaches the journal in real time. Without
# this, Python block-buffers stdout for non-TTYs and startup diagnostics
# only flush when the buffer fills or the process exits.
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/openemr/agent/.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now openemr-agent
sleep 15    # corpus indexing takes ~30s on first start
curl -s http://127.0.0.1:8000/health    # → {"status":"ok"}
```

If it errors with `python-multipart`, install it (the repo's
`requirements.txt` doesn't pin it):

```sh
. .venv/bin/activate && pip install python-multipart
systemctl restart openemr-agent
```

---

## 10. Caddy reverse proxy with sslip.io domains

`<IP>.sslip.io` resolves any subdomain to the literal IP encoded in the
hostname — no DNS panel, no domain purchase. Replace dashes for dots:
`146.190.75.148` → `146-190-75-148`.

The Caddyfile has two key requirements beyond the obvious reverse-proxies:

1. **`flush_interval -1`** on the agent block — Caddy 2 buffers responses by
   default, which drops the streaming benefit for `/chat/stream` SSE.
   Setting it to `-1` flushes every chunk immediately.
2. **Path-based routing on the OpenEMR block** — without it, all agent
   requests from the chat iframe (`openemr.<IP>.sslip.io/ui`,
   `/chat/stream`, `/dashboard/*`, etc.) flow through OpenEMR's PHP layer,
   which buffers SSE end-to-end. Pinning agent paths directly to the
   FastAPI service via Caddy bypasses OpenEMR for those requests.

```sh
cat > /etc/caddy/Caddyfile <<'EOF'
openemr.<IP-with-dashes>.sslip.io {
    # Agent paths bypass OpenEMR's PHP proxy so SSE actually streams.
    @agent path /chat /chat/* /ui /ui/* /extract /document/* /dashboard/* \
                /family-history/* /labs/* /coverage/* /care-team/* /health
    handle @agent {
        reverse_proxy 127.0.0.1:8000 {
            flush_interval -1
        }
    }

    # Everything else (FHIR, OAuth, OpenEMR PHP UI) stays on OpenEMR.
    handle {
        reverse_proxy https://127.0.0.1:9300 {
            transport http {
                tls
                tls_insecure_skip_verify
            }
        }
    }
}

agent.<IP-with-dashes>.sslip.io {
    reverse_proxy 127.0.0.1:8000 {
        flush_interval -1
    }
}
EOF
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
journalctl -u caddy -n 30 --no-pager    # watch for "certificate obtained successfully"
```

Verify both URLs and that streaming actually streams (no Caddy buffering):

```sh
curl -sI https://openemr.<IP-with-dashes>.sslip.io/ | head -1   # → 302
curl -s https://agent.<IP-with-dashes>.sslip.io/health          # → {"status":"ok"}

# Should print SSE events one at a time, not in a single dump at the end.
curl -N -s -X POST https://openemr.<IP-with-dashes>.sslip.io/chat/stream \
    -H 'Content-Type: application/json' \
    -d '{"patient_id":"","message":"What does the FDA label say about metformin?","conversation_history":[]}'
```

---

## 11. Wire OpenEMR's iframes to the public agent URL

`interface/patient_file/summary/demographics.php` embeds two iframes (the
React dashboard + the AI co-pilot). The repo's default points at the live
demo's URL. If you're deploying to a different IP, swap it:

```sh
cd /opt/openemr
sed -i "s|agent.146-190-75-148.sslip.io|agent.<your-ip-with-dashes>.sslip.io|g" \
  interface/patient_file/summary/demographics.php
```

The OpenEMR docker container mounts the repo at runtime, so the change
takes effect on the next page load — no container restart needed.

---

## 12. End-to-end verify

In a browser, visit `https://openemr.<IP-with-dashes>.sslip.io/`, log in
`admin` / `pass`, search for any of Chen / Whitaker / Reyes / Kowalski,
open the demographics page. Confirm:

- OpenEMR's PHP cards render with proper styling (CSS loaded)
- The React dashboard iframe shows 12 widgets populated
- The AI co-pilot iframe — pick the same patient from the dropdown and ask
  *"List this patient's allergies"*. Reply should include citation chips.
- Click ⚡ N tools on a reply to see the supervisor → worker handoff trace.

If any of the iframes show an `agent-copilot.ngrok-free.dev` URL, you
missed the `sed` in step 11.

---

## What this runbook does NOT cover

- Production hardening (admin password rotation, fail2ban, Anthropic key
  rotation, audit logging beyond `clinical_logger`).
- HIPAA compliance — the redaction layer is a starting point but a real
  PHI environment needs a BAA, encryption at rest, signed access logs, and
  formal incident response.
- Auto-scaling / HA. Single droplet only. If it dies, the URL goes down
  until you reboot it.

For the laptop-host alternative (ngrok + launchd auto-restart), see
`deploy/README.md`.
