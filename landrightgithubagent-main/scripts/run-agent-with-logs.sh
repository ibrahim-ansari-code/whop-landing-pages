#!/usr/bin/env bash
# Run the Landright sync agent with cron every 5s and visible logs.
# From landrightgithubagent-main: ./scripts/run-agent-with-logs.sh
# Or: cd python-agent && CRON_INTERVAL_SECONDS=5 python3 -m uvicorn main:app --reload --host 0.0.0.0 --port 4000

set -e
cd "$(dirname "$0")/../python-agent"
export CRON_INTERVAL_SECONDS=5
exec python3 -m uvicorn main:app --reload --host 0.0.0.0 --port 4000
