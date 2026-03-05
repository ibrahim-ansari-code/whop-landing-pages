#!/usr/bin/env bash
# Trigger a sync: injects a new .md file into the repo on each run.
# Usage: ./scripts/trigger-sync.sh [agent_url]
# Default agent: http://localhost:4000

set -e
AGENT_URL="${1:-http://localhost:4000}"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
# New file every time: sync/trigger-YYYY-MM-DDTHH-MM-SSZ.md
SAFE_TS=$(echo "$TIMESTAMP" | tr ':' '-')
FILE_PATH="sync/trigger-${SAFE_TS}.md"

MD_CONTENT="# Sync trigger

**Time (UTC):** $TIMESTAMP

Injected by agent trigger-sync.
"

echo "Triggering sync -> $AGENT_URL/sync"
echo "New file: $FILE_PATH"
echo ""

# Build JSON (use jq if available for multi-line .md, else one-line content)
if command -v jq >/dev/null 2>&1; then
  JSON_DATA=$(printf '%s' "$MD_CONTENT" | jq -Rs .)
  PAYLOAD=$(jq -n \
    --arg path "$FILE_PATH" \
    --argjson data "$JSON_DATA" \
    --arg msg "chore: inject sync trigger $TIMESTAMP" \
    '{filePath: $path, data: $data, commitMessage: $msg}')
else
  PAYLOAD="{\"filePath\":\"$FILE_PATH\",\"data\":\"# Sync trigger\\n\\nTriggered at $TIMESTAMP\",\"commitMessage\":\"chore: inject sync trigger $TIMESTAMP\"}"
fi

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$AGENT_URL/sync" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD")

HTTP_CODE=$(echo "$RESPONSE" | tail -n 1)
HTTP_BODY=$(echo "$RESPONSE" | sed '$d')

echo "HTTP $HTTP_CODE"
echo "$HTTP_BODY" | jq . 2>/dev/null || echo "$HTTP_BODY"
echo ""

if [ "$HTTP_CODE" = "200" ]; then
  echo "Done. Check the repo for new file: $FILE_PATH"
  exit 0
else
  echo "Sync failed (check agent logs and .env)"
  echo "If you see no 'detail' above, restart the agent: npm run build && npm start"
  exit 1
fi
