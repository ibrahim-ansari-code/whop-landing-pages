"""
Config for Landright GitHub agent. All from env; load .env from this directory.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

AGENT_DIR = Path(__file__).resolve().parent
load_dotenv(AGENT_DIR / ".env", override=True)

# Supabase (cta_by_variant)
SUPABASE_URL = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()

# Optional: GitHub App (for multi-user repo access). If set, agent uses App to get installation token per repo.
GITHUB_APP_ID = (os.environ.get("GITHUB_APP_ID") or "").strip()
GITHUB_APP_PRIVATE_KEY = (os.environ.get("GITHUB_APP_PRIVATE_KEY") or "").strip()
GITHUB_APP_PRIVATE_KEY_PATH = (os.environ.get("GITHUB_APP_PRIVATE_KEY_PATH") or "").strip()

# GitHub: PAT or fallback when GitHub App is not configured (single-owner or dev)
GITHUB_TOKEN = (os.environ.get("GITHUB_TOKEN") or "").strip()
GITHUB_REPO_FULL_NAME = (os.environ.get("GITHUB_REPO_FULL_NAME") or "").strip()

# Anthropic (Claude for adjust pipeline)
ANTHROPIC_API_KEY = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
ANTHROPIC_MODEL = (os.environ.get("ANTHROPIC_MODEL") or "claude-sonnet-4-20250514").strip()

# Design skill: same file as landright-app backend; first system block in LLM calls
DESIGN_SKILL_PATH = (os.environ.get("DESIGN_SKILL_PATH") or str(AGENT_DIR / "frontend-design-skill.md")).strip()
DESIGN_SKILL_PATH_RESOLVED = Path(DESIGN_SKILL_PATH).expanduser().resolve() if DESIGN_SKILL_PATH else None

# Cron: threshold for triggering adjust (best_cta_clicks - second_best >= CTA_THRESHOLD)
CTA_THRESHOLD = max(0, int(os.environ.get("CTA_THRESHOLD", "50")))
# Poll Supabase every N seconds, then run adjust pipeline and commit when threshold met
CRON_INTERVAL_SECONDS = max(1, int(os.environ.get("CRON_INTERVAL_SECONDS", "30")))
# Safety guard: max commit cycles per repo/layer in a rolling window
MAX_ADJUST_COMMITS_PER_WINDOW = max(1, int(os.environ.get("MAX_ADJUST_COMMITS_PER_WINDOW", "3")))
ADJUST_COMMIT_WINDOW_SECONDS = max(60, int(os.environ.get("ADJUST_COMMIT_WINDOW_SECONDS", "3600")))

# Optional: allow list of repo_full_name (comma-separated). Empty = process all from cta_by_variant.
REPO_ALLOW_LIST = [
    s.strip() for s in (os.environ.get("REPO_ALLOW_LIST") or "").split(",") if s.strip()
]
# Optional: repos in this list are never adjusted (judge bypassed, always skip). Use to show "no edits" demo.
REPO_SKIP_ADJUST_LIST = [
    s.strip() for s in (os.environ.get("REPO_SKIP_ADJUST_LIST") or "").split(",") if s.strip()
]

# Sync API: optional API key (Landright app sends x-api-key / Bearer)
SYNC_AGENT_API_KEY = (os.environ.get("SYNC_AGENT_API_KEY") or "").strip()

# CTA alignment: experience library (built by scripts/build_cta_experience_library.py)
EXPERIENCE_LIBRARY_CTA_PATH = (
    os.environ.get("EXPERIENCE_LIBRARY_CTA_PATH") or str(AGENT_DIR / "experience_library_cta.json")
).strip()
EXPERIENCE_LIBRARY_CTA_PATH_RESOLVED = (
    Path(EXPERIENCE_LIBRARY_CTA_PATH).expanduser().resolve() if EXPERIENCE_LIBRARY_CTA_PATH else None
)

# Claude CTA-align: request timeout (seconds). Keep prompts small so this is rarely hit.
CLAUDE_CTA_ALIGN_TIMEOUT_SECONDS = max(120, int(os.environ.get("CLAUDE_CTA_ALIGN_TIMEOUT_SECONDS", "300")))

# Max variant TSX chars sent to Claude. Keep this relatively small because CTA-align now returns
# a compact operation plan instead of a full-file rewrite.
MAX_VARIANT_CHARS_FOR_CTA_ALIGN = max(12_000, min(200_000, int(os.environ.get("MAX_VARIANT_CHARS_FOR_CTA_ALIGN", "18000"))))

# Data analyst: experience library for LLM judge (when to run adjust pipeline); built by scripts/build_data_analyst_experience_library.py
EXPERIENCE_LIBRARY_DATA_ANALYST_PATH = (
    os.environ.get("EXPERIENCE_LIBRARY_DATA_ANALYST_PATH") or str(AGENT_DIR / "experience_library_data_analyst.json")
).strip()
EXPERIENCE_LIBRARY_DATA_ANALYST_PATH_RESOLVED = (
    Path(EXPERIENCE_LIBRARY_DATA_ANALYST_PATH).expanduser().resolve() if EXPERIENCE_LIBRARY_DATA_ANALYST_PATH else None
)

# Generation: append durable lessons into the backend's default library so future frontend/backend
# generations can benefit from what the agent learns from winning variants.
EXPERIENCE_LIBRARY_GENERATION_PATH = (
    os.environ.get("EXPERIENCE_LIBRARY_GENERATION_PATH")
    or str(AGENT_DIR.parent.parent / "landright-app" / "backend" / "experience_library_default.json")
).strip()
EXPERIENCE_LIBRARY_GENERATION_PATH_RESOLVED = (
    Path(EXPERIENCE_LIBRARY_GENERATION_PATH).expanduser().resolve() if EXPERIENCE_LIBRARY_GENERATION_PATH else None
)

# SimGym: browser-based simulation pipeline
# Structure: N generations, each with M rounds. Each round = run bots_per_round → adjust → learn → delay. Total bots = generations × rounds_per_generation × bots_per_round.
SIMGYM_N_GENERATIONS = max(1, int(os.environ.get("SIMGYM_N_GENERATIONS", "5")))
SIMGYM_N_ROUNDS_PER_GENERATION = max(1, int(os.environ.get("SIMGYM_N_ROUNDS_PER_GENERATION", "4")))
SIMGYM_N_BOTS_PER_ROUND = max(1, int(os.environ.get("SIMGYM_N_BOTS_PER_ROUND", os.environ.get("SIMGYM_N_BOTS", "100"))))
# Backward compat: SIMGYM_N_BOTS and SIMGYM_N_ROUNDS (used if not using generations)
SIMGYM_N_BOTS = max(1, int(os.environ.get("SIMGYM_N_BOTS", "100")))
SIMGYM_N_ROUNDS = max(1, int(os.environ.get("SIMGYM_N_ROUNDS", "5")))
SIMGYM_USE_VISION = os.environ.get("SIMGYM_USE_VISION", "1").strip().lower() in ("1", "true", "yes")
SIMGYM_BASE_URL = (os.environ.get("SIMGYM_BASE_URL") or "http://localhost:3000").strip().rstrip("/")
SIMGYM_PERSONAS_PATH = (
    os.environ.get("SIMGYM_PERSONAS_PATH") or str(AGENT_DIR / "simgym_personas.json")
).strip()
SIMGYM_PERSONAS_PATH_RESOLVED = (
    Path(SIMGYM_PERSONAS_PATH).expanduser().resolve() if SIMGYM_PERSONAS_PATH else None
)
SIMGYM_HEADLESS = os.environ.get("SIMGYM_HEADLESS", "true").strip().lower() in ("1", "true", "yes")
SIMGYM_MAX_WORKERS = max(1, int(os.environ.get("SIMGYM_MAX_WORKERS", "4")))
SIMGYM_USE_BROWSERBASE = os.environ.get("SIMGYM_USE_BROWSERBASE", "").strip().lower() in ("1", "true", "yes")
# Backend URL for POST /beacon and /beacon-time (SimGym bots send event_source=simgym)
SIMGYM_BEACON_URL = (os.environ.get("SIMGYM_BEACON_URL") or "http://localhost:8000").strip().rstrip("/")
# Landright backend URL for /generate and /build-export-bundle (bootstrap). Defaults to same as beacon.
LANDRIGHT_BACKEND_URL = (os.environ.get("LANDRIGHT_BACKEND_URL") or os.environ.get("SIMGYM_BEACON_URL") or "http://localhost:8000").strip().rstrip("/")
# Local directory where export bundle is written (bootstrap) and variants are read/written (adjust). Full Next.js app.
SIMGYM_EXPORT_DIR = (os.environ.get("SIMGYM_EXPORT_DIR") or str(AGENT_DIR.parent.parent / "simgym-export")).strip()
SIMGYM_EXPORT_DIR_RESOLVED = Path(SIMGYM_EXPORT_DIR).expanduser().resolve() if SIMGYM_EXPORT_DIR else None
# Variant source: "local" = read/write SIMGYM_EXPORT_DIR/app/variants/; "github" = fetch/push via GitHub.
SIMGYM_VARIANT_SOURCE = (os.environ.get("SIMGYM_VARIANT_SOURCE") or ("local" if SIMGYM_EXPORT_DIR else "github")).strip().lower()
# Default repo/layer for Supabase and bundle (bootstrap and run). No hardcoded repo/layer in pipeline.
SIMGYM_DEFAULT_REPO = (os.environ.get("SIMGYM_DEFAULT_REPO") or "simgym/local").strip()
SIMGYM_DEFAULT_LAYER = (os.environ.get("SIMGYM_DEFAULT_LAYER") or "1").strip()
# Path to spec JSON for bootstrap /generate (must contain spec + promptId).
SIMGYM_SPEC_PATH = (os.environ.get("SIMGYM_SPEC_PATH") or str(AGENT_DIR / "simgym_spec.json")).strip()
SIMGYM_SPEC_PATH_RESOLVED = Path(SIMGYM_SPEC_PATH).expanduser().resolve() if SIMGYM_SPEC_PATH else None
# Delay (seconds) between each bot so Supabase/backend can persist events
SIMGYM_BOT_DELAY_SECONDS = max(0.0, float(os.environ.get("SIMGYM_BOT_DELAY_SECONDS", "2.0")))
# After each round: 0 = start next round as soon as adjust + learning finish (no fixed delay).
SIMGYM_POST_ROUND_DELAY_SECONDS = max(0, int(os.environ.get("SIMGYM_POST_ROUND_DELAY_SECONDS", "0")))
# When using local export: wait this many seconds after writing variant files before starting next bot round, so the dev server can reload and bots never see mid-edit state.
SIMGYM_POST_EDIT_DELAY_SECONDS = max(0, float(os.environ.get("SIMGYM_POST_EDIT_DELAY_SECONDS", "2.0")))
# Groq for vision (Llama 4 Scout); optional for text-only fallback (Llama 3.1 8B)
GROQ_API_KEY = (os.environ.get("GROQ_API_KEY") or "").strip()

# Experience libraries: max entries per file to avoid unbounded growth; oldest entries are dropped when over cap
EXPERIENCE_LIBRARY_MAX_ENTRIES = max(10, int(os.environ.get("EXPERIENCE_LIBRARY_MAX_ENTRIES", "200")))
# Similarity threshold (0.0-1.0): if new entry overlaps this much with an existing one, skip add (avoid near-duplicates/contradictions)
EXPERIENCE_LIBRARY_SIMILARITY_SKIP_THRESHOLD = max(0.0, min(1.0, float(os.environ.get("EXPERIENCE_LIBRARY_SIMILARITY_SKIP_THRESHOLD", "0.75"))))
