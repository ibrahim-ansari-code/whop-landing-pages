# Landright generator backend

Run with venv: `./run.sh` or `.venv/bin/python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000`.

## Deploy backend only (for time/CTA beacons from deployed export sites)

You have two options: **ngrok** (quick, local) or **deploy to a host** (always on).

### Option A: ngrok (quick, no deploy)

1. **Install ngrok**: https://ngrok.com/download (or `brew install ngrok`).
2. **Start the backend locally** (in `landright-app/backend`):
   ```bash
   .venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000
   ```
   (Drop `--reload` for a stable tunnel URL if you prefer.)
3. **In another terminal**, expose port 8000 and update `.env`:
   ```bash
   ./ngrok.sh
   ```
   This starts ngrok and writes `BEACON_BASE_URL` / `BACKEND_PUBLIC_URL` to `.env`. Or run `ngrok http 8000` and copy the HTTPS URL into `.env` yourself.
4. **Restart the backend** so it reads the new env, then **re-export / re-push the bundle** for the repo (Sync bundle to GitHub from the Landright app) so the bundle bakes in this URL.
5. Keep your machine running and the backend + ngrok processes up. On the **free** ngrok plan the URL changes each time you restart ngrok; with a reserved domain it stays the same.

### Option B: Deploy to Railway (or Render / Fly.io)

Deploy only the `landright-app/backend` folder so it has a permanent public URL.

**Railway (example)**

1. Sign up at https://railway.app and install the CLI or use the dashboard.
2. Create a new project → “Deploy from GitHub repo”. Choose your repo and set the **root directory** to `landright-app/backend` (or the path to the backend folder in your repo).
3. Set **start command** to: `uvicorn main:app --host 0.0.0.0 --port $PORT` (Railway sets `PORT`).
4. In the project **Variables**, add the same env vars as in `.env` (e.g. `ANTHROPIC_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, etc.). Set:
   - `BEACON_BASE_URL=https://your-app-name.up.railway.app`
   - `BACKEND_PUBLIC_URL=https://your-app-name.up.railway.app`
   (Use the actual URL Railway gives you.)
5. Deploy. After deploy, **re-export / re-push the bundle** for any repo that should send beacons to this backend.

**Render**

- New → Web Service → connect repo, set **Root Directory** to `landright-app/backend`.
- Build: `pip install -r requirements.txt`
- Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Add env vars in the dashboard, including `BEACON_BASE_URL` and `BACKEND_PUBLIC_URL` to the service URL.

---

## Deployed repos and time/CTA events

Exported bundles (e.g. repo **ibrahim-ansari-code/y** on Vercel) send analytics to the URL baked in at **build** time. That URL comes from `BEACON_BASE_URL` (or `BACKEND_PUBLIC_URL`) in this directory’s `.env`.

- If that is `http://localhost:8000`, the deployed site will send beacons to **each visitor’s** localhost, so your backend never receives them and **time_events / cta_events stay empty** for that repo.
- To fix: use **ngrok** or **deploy this backend** to a public URL (above), set `BEACON_BASE_URL` and `BACKEND_PUBLIC_URL` to that URL, then **re-build and re-push** the bundle for the repo (e.g. Sync bundle to GitHub again from the Landright app) so the new bundle uses the public URL. After that, visits to the deployed site will update Supabase.
