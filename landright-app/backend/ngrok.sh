#!/usr/bin/env bash
# Start ngrok for port 8000, then update .env with the public URL.
# Prereqs: backend running on 8000, ngrok installed (brew install ngrok).
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Starting ngrok (ensure backend is running: .venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000)..."
ngrok http 8000 --log=stdout > /tmp/ngrok.log 2>&1 &
NGROK_PID=$!
sleep 3
if ! kill -0 $NGROK_PID 2>/dev/null; then
  echo "ngrok failed to start. Check /tmp/ngrok.log"
  exit 1
fi

URL=""
for i in 1 2 3 4 5; do
  URL=$(curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    for t in d.get('tunnels', []):
        if t.get('proto') == 'https':
            print(t.get('public_url', ''))
            break
except Exception:
    pass
" 2>/dev/null)
  [ -n "$URL" ] && break
  sleep 1
done

if [ -z "$URL" ]; then
  echo "Could not get ngrok URL. Is ngrok running? Try: curl http://127.0.0.1:4040/api/tunnels"
  kill $NGROK_PID 2>/dev/null || true
  exit 1
fi

echo "ngrok URL: $URL"
if [ -f .env ]; then
  if grep -q '^BEACON_BASE_URL=' .env; then
    sed -i.bak "s|^BEACON_BASE_URL=.*|BEACON_BASE_URL=$URL|" .env
  else
    echo "BEACON_BASE_URL=$URL" >> .env
  fi
  if grep -q '^BACKEND_PUBLIC_URL=' .env; then
    sed -i.bak "s|^BACKEND_PUBLIC_URL=.*|BACKEND_PUBLIC_URL=$URL|" .env
  else
    echo "BACKEND_PUBLIC_URL=$URL" >> .env
  fi
  rm -f .env.bak
  echo "Updated .env with BEACON_BASE_URL and BACKEND_PUBLIC_URL=$URL"
else
  echo "No .env found; create one and set BEACON_BASE_URL=$URL and BACKEND_PUBLIC_URL=$URL"
fi
echo "Leave ngrok running (PID $NGROK_PID). Restart the backend so it picks up the new URL, then re-export/re-push the bundle."
