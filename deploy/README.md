# Stable deployment on macOS (ngrok + launchd)

The reviewer feedback flagged that the deployed URL was offline when graders
checked. This directory contains a one-time setup that makes both ngrok
tunnels and the FastAPI agent **survive laptop reboots, terminal closes,
and process crashes** — so the public URLs stay reachable as long as the
laptop is on and connected.

## What's here

| File | Purpose |
|---|---|
| `ngrok.yml` | Single config defining both tunnels (OpenEMR + agent). Reserved domains so URLs don't change. |
| `run-agent.sh` | Wrapper script that sources `agent/.env`, then `exec`s uvicorn so launchd can track the PID. |
| `launchd/com.openemr.agent.plist` | launchd agent definition. Starts the FastAPI process at login, restarts it on crash. |

## One-time setup

Replace `REPO_ROOT` below with the absolute path to this checkout (e.g.
`/Users/heilashahidi/Gauntlet/openemr`).

### 1. ngrok config + service

```sh
mkdir -p ~/.config/ngrok
cp REPO_ROOT/deploy/ngrok.yml ~/.config/ngrok/ngrok.yml
# Edit the copy: replace `REPLACE_ME` with your auth token from
# https://dashboard.ngrok.com/get-started/your-authtoken
# (Optional) uncomment the basic_auth block on the agent tunnel.

ngrok service install --config ~/.config/ngrok/ngrok.yml
sudo ngrok service start
```

Verify both tunnels are up:

```sh
curl -sI https://backlog-troubling-unfold.ngrok-free.dev/ | head -1
curl -sI -H "ngrok-skip-browser-warning: 1" https://agent-copilot.ngrok-free.dev/health | head -1
```

### 2. FastAPI agent as a launchd service

```sh
# Copy the plist template
cp REPO_ROOT/deploy/launchd/com.openemr.agent.plist ~/Library/LaunchAgents/

# Replace the placeholder with your absolute repo path. Two occurrences.
sed -i '' "s|REPO_ROOT_HERE|REPO_ROOT|g" ~/Library/LaunchAgents/com.openemr.agent.plist

# Bootstrap into the user's launchd session
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.openemr.agent.plist
launchctl enable gui/$UID/com.openemr.agent

# Verify
curl -s http://localhost:8000/health    # should print {"status":"ok"}
tail -20 /tmp/openemr-agent.out.log
```

To restart after editing code:

```sh
launchctl kickstart -k gui/$UID/com.openemr.agent
```

To stop / uninstall:

```sh
launchctl bootout gui/$UID/com.openemr.agent
rm ~/Library/LaunchAgents/com.openemr.agent.plist
```

### 3. Docker auto-start

OpenEMR runs on the docker compose stack at `docker/development-easy/`. Two
changes to keep it up:

1. **Docker Desktop → start at login**: macOS System Settings → General →
   Login Items & Extensions → "Open at Login" → add Docker.
2. **Container restart policy**: edit `docker/development-easy/docker-compose.yml`
   and add `restart: unless-stopped` to the OpenEMR + MariaDB services
   (already set on most recent OpenEMR templates).

### 4. Prevent macOS sleep when plugged in

```sh
sudo pmset -c sleep 0 disablesleep 1
```

Only applies on AC power. Battery sleep is unaffected — close the lid only
when you don't need the public URL to be reachable.

## What this fixes

| Failure mode | Before (manual `ngrok http ...`) | After |
|---|---|---|
| Tunnel dies when terminal closes | ❌ tunnel offline until restarted manually | ✅ launchd respawns |
| Agent crashes mid-query | ❌ 502 through tunnel | ✅ `KeepAlive` restarts agent |
| Laptop reboots | ❌ everything down | ✅ all services come back at login |
| macOS sleeps on AC | ❌ tunnel drops, slow reconnect | ✅ sleep disabled on AC |
| Bots probe the URL | ❌ shared bandwidth | ✅ optional Basic Auth in `ngrok.yml` |

## What this does NOT fix

- **Laptop powered off, lid closed on battery, off-network**: nothing on
  this machine can serve traffic. If the demo URL needs to work while the
  laptop is in a backpack, only a real cloud deployment (Fly.io / Render /
  a VPS) solves that — see the main `README_W2.md` for migration notes.
- **ngrok edge incidents**: rare but real. ngrok's status page is at
  https://status.ngrok.com — out of our control.
