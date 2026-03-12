# AGENTS.md

## Cursor Cloud specific instructions

### Repository structure

Two independent projects in a flat repo (not a typical monorepo):

| Service | Path | Type | Port | Required |
|---|---|---|---|---|
| Next.js Frontend | `landright-app/` | Next.js 16 + React 19 | 3000 | Yes |
| Python Generate API | `landright-app/backend/` | FastAPI (Python 3.12) | 8000 | Yes |
| Node.js Sync Agent | `landrightgithubagent-main/` | Express + TypeScript | 4000 | Optional |
| Python GitHub Agent | `landrightgithubagent-main/python-agent/` | FastAPI | 4000 | Optional |

### Running services

- **Frontend**: `npm run dev` in `landright-app/` (port 3000). Set `NEXT_PUBLIC_GENERATE_API_URL` to the backend origin (localhost port 8000) so the frontend can reach the backend.
- **Backend**: In `landright-app/backend/` run with the venv Python so the reloader subprocess sees venv dependencies (e.g. `bs4`): `.venv/bin/python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000`. (Using `source .venv/bin/activate` then `python -m uvicorn` can still spawn a reloader that uses system Python and fail with `ModuleNotFoundError: No module named 'bs4'`.) Works without `ANTHROPIC_API_KEY` (returns template variants). With a key set, it calls Claude for AI-generated variants.
- The backend's `/health` endpoint confirms readiness.

### Lint / Test / Build

- **Lint**: `npm run lint` in `landright-app/` (ESLint 9 flat config). Warnings about unused vars are pre-existing and not errors.
- **Tests**: `npm test` in `landright-app/` (Vitest). The `test-full-claude-pipeline` test requires a running backend with `ANTHROPIC_API_KEY`; it is expected to fail without one.
- **TypeScript check** (github agent): `npx tsc --noEmit` in `landrightgithubagent-main/`.

### Gotchas

- The `package.json` in `landright-app/` had git merge conflicts between Next.js 14 and Next.js 16 branches. These were resolved in favor of Next.js 16 / React 19 / ESLint 9 to match the ESLint flat config (`eslint.config.mjs`). Test scripts from the HEAD branch were preserved.
- pip installs to `~/.local/bin`; ensure `PATH` includes it (`export PATH="$HOME/.local/bin:$PATH"`).
- External services (Anthropic API, Supabase, GitHub App) are needed for full functionality but not for basic dev/test. The app gracefully falls back to template variants without API keys.
- **Production export (Export bundle / GitHub)**: The bundle bakes in `BEACON_URL` from the backend env (`BEACON_BASE_URL` or `BACKEND_PUBLIC_URL`). For **deployed sites** (e.g. Vercel) to send CTA and time analytics to your backend, set `BEACON_BASE_URL` to your **public** backend URL (e.g. `https://your-backend.example.com`) before generating the export. If you leave it as `http://localhost:8000`, the deployed site will try to send beacons to visitors' localhost, so Supabase will only get events when you test from the same machine as the backend.

- **New repo (e.g. ibrahim-ansari-code/y) not updating time_events or cta_events**: The deployed Vercel app sends beacons to the URL that was in the backend when the bundle was built. If that was `http://localhost:8000`, every visitor’s browser posts to its own localhost — your backend never receives the request, so Supabase gets no rows. **Fix**: (1) Deploy the backend to a public URL (e.g. Railway, Render, Fly.io, or ngrok for testing). (2) In `landright-app/backend/.env` set `BEACON_BASE_URL=https://your-public-backend-url` (and `BACKEND_PUBLIC_URL` if used). (3) Re-build and re-push the bundle for that repo (e.g. Sync bundle to GitHub again from the Landright app, or re-export so the new bundle contains the public beacon URL). (4) Restart the backend so it reads the new env. After that, visits to the deployed site will hit your public backend and time_events/cta_events will update.
- **Experience library (generation) not updating**: The SimGym pipeline appends to both the configured path (default: `landright-app/backend/experience_library_default.json`) and to `landrightgithubagent-main/python-agent/experience_library_generation.json`. If the backend file never gains new entries, check pipeline logs for "Generation paths" to see where writes go. To use pipeline-learned entries in the backend, set `EXPERIENCE_LIBRARY_PATH` in `landright-app/backend/.env` to the absolute path of `experience_library_generation.json`.
- **Only the Landright backend needs to be deployed** for time/CTA events from deployed export sites. The frontend can stay local; the GitHub agent is optional.
- **GitHub agent: repo has App access but no commits**: The cron runs one adjust job at a time. If it's stuck in a long Claude call, you see "maximum number of running instances reached" and no "Pushed" logs. Set `CLAUDE_CTA_ALIGN_TIMEOUT_SECONDS=300` in the python-agent `.env` so each variant request times out after 5 min. Check logs for "Calling Claude to align …", "Pushing …", "Pushed …" or "Failed to update …".: The cron runs one adjust job at a time. If it’s stuck in a long Claude call, you see "maximum number of running instances reached" and no "Pushed" logs. Set `CLAUDE_CTA_ALIGN_TIMEOUT_SECONDS=300` in the python-agent `.env` so each variant request times out after 5 min. Check logs for "Calling Claude to align …", "Pushing …", "Pushed …" or "Failed to update …".
