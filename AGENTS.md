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
- **Backend**: `python3 -m uvicorn main:app --reload --host 0.0.0.0 --port 8000` in `landright-app/backend/`. Works without `ANTHROPIC_API_KEY` (returns template variants). With a key set, it calls Claude for AI-generated variants.
- The backend's `/health` endpoint confirms readiness.

### Lint / Test / Build

- **Lint**: `npm run lint` in `landright-app/` (ESLint 9 flat config). Warnings about unused vars are pre-existing and not errors.
- **Tests**: `npm test` in `landright-app/` (Vitest). The `test-full-claude-pipeline` test requires a running backend with `ANTHROPIC_API_KEY`; it is expected to fail without one.
- **TypeScript check** (github agent): `npx tsc --noEmit` in `landrightgithubagent-main/`.

### Gotchas

- The `package.json` in `landright-app/` had git merge conflicts between Next.js 14 and Next.js 16 branches. These were resolved in favor of Next.js 16 / React 19 / ESLint 9 to match the ESLint flat config (`eslint.config.mjs`). Test scripts from the HEAD branch were preserved.
- pip installs to `~/.local/bin`; ensure `PATH` includes it (`export PATH="$HOME/.local/bin:$PATH"`).
- External services (Anthropic API, Supabase, GitHub App) are needed for full functionality but not for basic dev/test. The app gracefully falls back to template variants without API keys.
