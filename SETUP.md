# OpenEMR — Personal Setup & Workflow Notes

Personal scratch notes for the Gauntlet OpenEMR project — start/stop commands,
your seeded test patients, OAuth flow, and the FHIR/DB patterns you've been using.

Repo: `~/Gauntlet/openemr` (OpenEMR 8.1.1-dev, master @ `d752953a6`).

---

## Start / stop

```bash
cd ~/Gauntlet/openemr/docker/development-easy

docker compose up --detach --wait    # first start (or after reboot)
docker compose ps                    # status
docker compose stop                  # stop, keep data
docker compose start                 # bring back up
docker compose down                  # stop + remove containers (data persists)
docker compose down -v               # NUKE everything (loses patients, OAuth clients, seed data)
```

If Docker Desktop isn't running yet: `open -a Docker`, wait for the whale.

---

## App URLs

| Service | URL | Login |
|---|---|---|
| OpenEMR (HTTP) | http://localhost:8300/ | `admin` / `pass` |
| OpenEMR (HTTPS) | https://localhost:9300/ | `admin` / `pass` |
| phpMyAdmin | http://localhost:8310/ | (auto) |
| Mailpit (email capture) | http://localhost:8025/ | — |
| Selenium VNC | http://localhost:7900/ | — |

---

## Your seeded test patients

Persist in the MariaDB volume across `docker compose stop/start`. Lost on `down -v`.

| Name | PID | Patient UUID | Condition | Med | Allergy | Visit reason |
|---|---|---|---|---|---|---|
| Sarah Smith | 1 | `a1a5b7d7-bac2-4eb8-b471-96f0eadb219e` | Hypertension (I10) | Lisinopril 10mg daily | Peanuts | Annual physical |
| Philip Cramer | 2 | `a1a5b82c-a50b-4e0d-b86f-4d7d216f6c27` | T2DM (E11.9) | Metformin 500mg BID | Penicillin | Diabetes follow-up |
| Candy Lane | 3 | `a1a5b8f9-7933-44a5-bad1-b4fdf8381d57` | Asthma (J45.909) | Albuterol HFA PRN | Sulfa drugs | Annual wellness exam |

Each also has a `form_vitals` row, but vitals don't yet surface as FHIR Observations (open audit item).

---

## OAuth2 — getting a token

You registered an OAuth2 client called "Audit E2E Verifier" and enabled it via direct DB update (registration disables clients by default — see AUDIT.md §7). Credentials saved at:

```
/tmp/oauth_client.json   # client_id + client_secret
/tmp/oauth_token.json    # access_token (~1h lifetime)
```

### Re-register a client (if `/tmp` is wiped or containers reset)

```bash
curl -k -X POST https://localhost:9300/oauth2/default/registration \
  -H 'Content-Type: application/json' \
  -d '{
    "application_type":"private",
    "client_name":"Audit E2E Verifier",
    "redirect_uris":["https://localhost:9300/callback"],
    "scope":"openid offline_access api:fhir api:oemr user/Patient.read user/Condition.read user/Observation.read user/Encounter.read user/MedicationRequest.read user/AllergyIntolerance.read user/Appointment.read"
  }' | tee /tmp/oauth_client.json | jq

# Enable it (registration leaves is_enabled=0)
CID=$(jq -r '.client_id' /tmp/oauth_client.json)
cd ~/Gauntlet/openemr/docker/development-easy
docker compose exec -T mysql mariadb -uroot -proot openemr \
  -e "UPDATE oauth_clients SET is_enabled=1 WHERE client_id='$CID';"
```

### Refresh the token (do this every ~hour)

```bash
CID=$(jq -r '.client_id' /tmp/oauth_client.json)
CSEC=$(jq -r '.client_secret' /tmp/oauth_client.json)
curl -ks -X POST https://localhost:9300/oauth2/default/token \
  -d "grant_type=password" -d "client_id=$CID" -d "client_secret=$CSEC" \
  -d "user_role=users" -d "username=admin" -d "password=pass" \
  -d "scope=openid api:fhir user/Patient.read user/Condition.read user/Observation.read user/Encounter.read user/MedicationRequest.read user/AllergyIntolerance.read user/Appointment.read" \
  > /tmp/oauth_token.json
export TOKEN=$(jq -r '.access_token' /tmp/oauth_token.json)
export BASE="https://localhost:9300/apis/default/fhir"
```

---

## FHIR calls — the patterns you've been using

```bash
# Sanity check (no auth)
curl -k $BASE/metadata | jq '.fhirVersion, .software'

# All FHIR data for one patient
PT="a1a5b7d7-bac2-4eb8-b471-96f0eadb219e"   # Sarah

for R in Patient Condition MedicationRequest AllergyIntolerance Encounter Observation; do
  N=$(curl -ks -H "Authorization: Bearer $TOKEN" "$BASE/$R?patient=$PT" | jq -r '.total // 0')
  echo "$R: $N"
done

# meta.profile inspection (the audit pattern)
curl -ks -H "Authorization: Bearer $TOKEN" "$BASE/Patient/$PT" | jq '.meta'
curl -ks -H "Authorization: Bearer $TOKEN" "$BASE/Condition?patient=$PT" | jq '.entry[0].resource.meta'

# Visit reason (UC1)
curl -ks -H "Authorization: Bearer $TOKEN" "$BASE/Encounter?patient=$PT" \
  | jq '.entry[].resource.reasonCode[0].text'
```

---

## Direct DB — common queries

```bash
cd ~/Gauntlet/openemr/docker/development-easy

# Quick query
docker compose exec -T mysql mariadb -uroot -proot openemr -e "SELECT pid, fname, lname FROM patient_data;"

# Interactive shell
docker compose exec mysql mariadb -uroot -proot openemr
```

Useful one-liners:

```sql
SELECT pid, fname, lname FROM patient_data;
SELECT pid, type, COUNT(*) FROM lists GROUP BY pid, type;
SELECT pid, encounter, reason FROM form_encounter ORDER BY pid;
```

---

## When something breaks

**FHIR returns 401:** token expired. Re-run the token block above.

**Token request returns `invalid_client`:** the client you're using no longer exists or `is_enabled=0`. Re-register and re-enable.

**`unsupported_grant_type` for `password`:** Admin → Config → Connectors → "Enable OAuth2 Password Grant" got toggled off.

**Can't reach `/fhir/metadata`:** Admin → Config → Connectors → "Enable OpenEMR FHIR REST API" got toggled off.

**PHP errors:** `docker compose exec openemr tail -n 80 /var/log/apache2/error.log`

**Total reset:** `docker compose down -v && docker compose up --detach --wait`. Loses everything; re-seed from chat history.

---

## Project deliverables (in the repo, root-level)

- `AUDIT.md` — FHIR API audit findings (~500 words + interview prep)
- `USERS.md` — target user + use cases
- `ARCHITECTURE.md` — AI agent integration plan

Architecture is **read via FHIR, write via Standard REST** with a single user-role OAuth2 token (the Standard REST API rejects patient-context tokens by design — see AUDIT.md §6).

---

## Tests (when you eventually need them)

```bash
docker compose exec openemr /root/devtools unit-test
docker compose exec openemr /root/devtools api-test
docker compose exec openemr /root/devtools php-log
```
