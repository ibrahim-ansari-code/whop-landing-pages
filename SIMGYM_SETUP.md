# SimGym Setup

Use this when opening the repo in a fresh Cursor window and you need to get SimGym-style traffic working against Landright.

## What SimGym means here

- SimGym traffic is stored through the normal analytics endpoints.
- Use `event_source="simulated"` or `event_source="simgym"` on analytics writes.
- The backend already accepts these sources for both:
  - `POST /beacon`
  - `POST /beacon-time`

Relevant code:
- `landright-app/backend/main.py`
- `landright-app/supabase/schema.sql`

## Services to run

Start these from the repo:

1. Backend

```bash
cd landright-app/backend
.venv/bin/python -m uvicorn main:app --reload --host 0.0.0.0 --port 8003
```

2. Frontend

```bash
cd landright-app
npm run dev
```

3. GitHub agent

```bash
cd landrightgithubagent-main/python-agent
.venv/bin/python -m uvicorn main:app --reload --host 0.0.0.0 --port 4000
```

4. ngrok for public backend access

```bash
ngrok http 8003
```

## Current local ports

- Frontend: `3000`
- Backend: `8003`
- GitHub agent: `4000`

## Env that matters

### Frontend

File: `landright-app/.env.local`

```env
NEXT_PUBLIC_GENERATE_API_URL=http://localhost:8003
```

### Backend

File: `landright-app/backend/.env`

Set the public backend URL before exporting/pushing bundles:

```env
BEACON_BASE_URL=https://your-public-backend-url
BACKEND_PUBLIC_URL=https://your-public-backend-url
```

Important:
- If this points to `localhost`, deployed repos will send analytics to the visitor's localhost instead of your backend.
- Any time `BEACON_BASE_URL` changes, you must re-export / re-push the bundle so the generated `ClientPage.tsx` gets the new beacon URL.

## Supabase setup

Run these in order:

1. `landright-app/supabase/schema.sql`
2. `landright-app/supabase/demo_data.sql`

Notes:
- `adjustment_log` now includes `times_before`.
- `cta_events` and `time_events` allow `event_source in ('real', 'simulated', 'simgym')`.

## Analytics endpoints for SimGym

### CTA clicks

`POST /beacon`

Example payload:

```json
{
  "event": "button_click",
  "repo_full_name": "owner/repo",
  "layer": "1",
  "variant_id": "variant-1",
  "cta_label": "Get started",
  "cta_id": "hero-primary",
  "event_source": "simulated"
}
```

### Time on page

`POST /beacon-time`

Example payload:

```json
{
  "repo_full_name": "owner/repo",
  "layer": "1",
  "variant_id": "variant-1",
  "duration_seconds": 12.34,
  "section_id": "hero",
  "event_source": "simulated"
}
```

## Important fixes already in place

- Exported bundles now send time beacons in a no-preflight-friendly way.
- Backend `/beacon-time` accepts plain-text JSON bodies as well as normal JSON.
- GitHub agent now skips pushes for unrunnable generated TSX.
- `/sync` also refuses to commit unrunnable `.tsx` files.
- Adjust pipeline commit messages include both CTA clicks and time-on-page.
- Adjust pipeline runs CTA alignment sequentially (`max_workers=1`) to reduce retries/timeouts.

## Known gotchas

### 1. Deployed repo has no time data

Usually means the exported bundle was built with the wrong beacon URL.

Fix:
- update `BEACON_BASE_URL` in `landright-app/backend/.env`
- restart backend
- rebuild / re-export
- re-push repo

### 2. You see lots of `OPTIONS /beacon-time` but no real inserts

That was previously caused by preflight on unload/pagehide requests. The codebase now has a fix for this, but old exported repos will still have the broken behavior until re-exported.

### 3. Adjust pipeline says `RUN_ADJUST` but nothing gets pushed

Check GitHub agent logs for:
- TSX validation skip
- Claude timeout
- auth / repo access errors
- sync rejection with `422`

### 4. Repo gets broken TSX

This should now be blocked in both:
- adjust pipeline
- `/sync`

If it happens again, inspect `landrightgithubagent-main/python-agent/main.py` first.

## Good health checks

Backend:

```bash
curl http://127.0.0.1:8003/health
```

Frontend:

```bash
curl -I http://127.0.0.1:3000
```

Agent:

```bash
curl -I http://127.0.0.1:4000/docs
```

ngrok:

```bash
curl http://127.0.0.1:4040/api/tunnels
```

## Recommended first checks in a new window

1. Open `SIMGYM_SETUP.md`
2. Confirm `landright-app/.env.local`
3. Confirm `landright-app/backend/.env`
4. Start backend, frontend, agent, ngrok
5. Run schema + demo data in Supabase if needed
6. Verify `/health` and ngrok tunnel
7. Only then test export / deploy / SimGym traffic
