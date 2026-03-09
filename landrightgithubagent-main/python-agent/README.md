# Python GitHub Agent

Run with the project venv so install and reloader use the venv (avoids Homebrew "externally-managed-environment" and missing modules).

**One-time setup (from this directory):**

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

**Run the server:**

```bash
.venv/bin/python -m uvicorn main:app --reload --host 0.0.0.0 --port 4000
```

If port 4000 is in use: `for p in $(lsof -ti :4000); do kill -9 $p; done` (or use another port, e.g. `--port 4001`).

**GitHub (so the repo actually updates):** The agent only writes to `adjustment_log` when it has successfully pushed at least one file. For pushes to succeed you need write access to the repo: set `GITHUB_TOKEN` with `repo` scope (full control of private repos), or configure a GitHub App (`GITHUB_APP_ID` + `GITHUB_APP_PRIVATE_KEY`) and install it on the repo owner’s account. Without that, the judge may say RUN_ADJUST but the repo will not be updated and you’ll see a warning in the logs.

**Experience library:** After each cron run, the agent evaluates recent adjustment_log rows (once they are at least ADJUSTMENT_EVALUATION_MIN_AGE_SEC old, default 1 hour) and appends lessons to the CTA or data-analyst experience library. So the library is updated automatically; allow time after a push for data to accumulate before evaluation.
