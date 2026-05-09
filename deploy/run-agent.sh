#!/bin/sh
###############################################################################
# Wrapper script launchd uses to start the FastAPI agent. Lives outside the
# launchd plist so editing env / paths doesn't require reloading the plist.
#
# What it does:
#   1. cd into the agent/ directory (uvicorn imports are relative).
#   2. Source agent/.env so ANTHROPIC_API_KEY (and any other secrets) are
#      visible to the python process.
#   3. Exec uvicorn — `exec` matters so launchd tracks the python PID
#      directly (otherwise it tracks /bin/sh and can't restart the agent
#      when uvicorn crashes).
###############################################################################

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT/agent"

if [ -f ./.env ]; then
  set -a
  . ./.env
  set +a
fi

# Use whatever python3 is first on PATH — pyenv / brew / system, in that order.
exec python3 -m uvicorn app:app --host 127.0.0.1 --port 8000
