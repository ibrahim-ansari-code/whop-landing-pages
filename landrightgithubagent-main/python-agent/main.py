"""
Landright GitHub agent: FastAPI service with POST /sync, GET /health, and a background job
that polls Supabase cta_by_variant every 10 seconds and runs an adjust-variants pipeline (then commits)
when best - second_best CTA clicks >= threshold. Design guidance from frontend-design-skill.md.
"""
import logging
import re
import time
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    CTA_THRESHOLD,
    CRON_INTERVAL_SECONDS,
    MAX_ADJUST_COMMITS_PER_WINDOW,
    ADJUST_COMMIT_WINDOW_SECONDS,
    DESIGN_SKILL_PATH_RESOLVED,
    EXPERIENCE_LIBRARY_CTA_PATH_RESOLVED,
    EXPERIENCE_LIBRARY_DATA_ANALYST_PATH_RESOLVED,
    GITHUB_REPO_FULL_NAME,
    GITHUB_TOKEN,
    REPO_ALLOW_LIST,
    SUPABASE_SERVICE_ROLE_KEY,
    SUPABASE_URL,
    SYNC_AGENT_API_KEY,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = FastAPI(title="Landright GitHub Agent")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _load_skill_content() -> str:
    path = DESIGN_SKILL_PATH_RESOLVED
    if not path or not path.exists():
        return ""
    raw = path.read_text(encoding="utf-8").strip()
    if raw.startswith("vi---"):
        raw = "---" + raw[5:]
    return raw


def _load_cta_experience_library() -> list[str]:
    """Load CTA alignment experience library (built by scripts/build_cta_experience_library.py)."""
    import json
    path = EXPERIENCE_LIBRARY_CTA_PATH_RESOLVED
    if not path or not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [str(x).strip() for x in data if x and str(x).strip()]
        if isinstance(data, dict) and "experienceLibrary" in data:
            raw = data["experienceLibrary"]
            if isinstance(raw, list):
                return [str(x).strip() for x in raw if x and str(x).strip()]
    except (json.JSONDecodeError, TypeError, OSError):
        pass
    return []


def _load_data_analyst_experience_library() -> list[str]:
    """Load data analyst experience library (built by scripts/build_data_analyst_experience_library.py)."""
    import json
    path = EXPERIENCE_LIBRARY_DATA_ANALYST_PATH_RESOLVED
    if not path or not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [str(x).strip() for x in data if x and str(x).strip()]
        if isinstance(data, dict) and "experienceLibrary" in data:
            raw = data["experienceLibrary"]
            if isinstance(raw, list):
                return [str(x).strip() for x in raw if x and str(x).strip()]
    except (json.JSONDecodeError, TypeError, OSError):
        pass
    return []


FRONTEND_DESIGN_SKILL = _load_skill_content()
CTA_EXPERIENCE_LIBRARY = _load_cta_experience_library()
DATA_ANALYST_EXPERIENCE_LIBRARY = _load_data_analyst_experience_library()
_ADJUST_RUNTIME_STATE: dict[tuple[str, str], dict] = {}


class SyncBody(BaseModel):
    filePath: str = "app/page.tsx"
    data: str
    commitMessage: str = "Update from Landright"
    repo_full_name: str | None = None


class DeployBody(BaseModel):
    tsx: str
    reasoning: str = ""
    conversionDrivers: list[str] = []
    companyName: str = ""
    variantIndex: int = 0


class AdjustVariantsBody(BaseModel):
    repo_full_name: str
    layer: str


def _get_github_repo(repo_full_name: str):
    from github import Github
    try:
        from github_app import get_github_for_repo
        repo = get_github_for_repo(repo_full_name)
        if repo is not None:
            return repo
    except Exception:
        pass
    if not GITHUB_TOKEN:
        raise RuntimeError(
            "No GitHub access: set GITHUB_TOKEN (PAT) or configure GitHub App "
            "(GITHUB_APP_ID + GITHUB_APP_PRIVATE_KEY) and install the app on the repo owner's account."
        )
    g = Github(GITHUB_TOKEN)
    return g.get_repo(repo_full_name)


def _normalize_variant_tsx_for_vercel(data: str) -> str:
    """Adjust variant TSX so it can run on Vercel: strip BOM, fix font names, ensure \"use client\"."""
    raw = (data or "").replace("\ufeff", "")
    s = raw.strip()
    if not s:
        return data or ""
    s = re.sub(r"\bSource_Sans_Pro\b", "Source_Sans_3", s)
    s = re.sub(r"\bNunito_Sans\b", "Nunito", s)
    lower = s.lstrip().lower()
    if lower.startswith('"use client"') or lower.startswith("'use client'"):
        first = s.find("\n")
        rest = s[first + 1 :].lstrip() if first >= 0 else ""
        return '"use client";\n\n' + (rest + "\n" if rest else "")
    return '"use client";\n\n' + s


@app.post("/deploy")
def deploy(body: DeployBody):
    """Accept a selected variant + reasoning from the generate backend. Returns ok so backend forward succeeds."""
    log.info("deploy: company=%r variant=%d", body.companyName, body.variantIndex)
    return {"ok": True, "companyName": body.companyName, "variantIndex": body.variantIndex}


@app.post("/sync")
def sync(
    body: SyncBody,
    x_api_key: str | None = Header(None),
    authorization: str | None = Header(None),
):
    if SYNC_AGENT_API_KEY:
        token = (x_api_key or (authorization or "").replace("Bearer ", "").strip())
        if token != SYNC_AGENT_API_KEY:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")
    repo_name = (body.repo_full_name or GITHUB_REPO_FULL_NAME or "").strip()
    if not repo_name:
        raise HTTPException(status_code=400, detail="repo_full_name required in body or GITHUB_REPO_FULL_NAME in env")
    if not body.data:
        raise HTTPException(status_code=400, detail="data is required")
    data = body.data
    path = (body.filePath or "app/page.tsx").strip().lstrip("/")
    # When committing a variant file, adjust code so it can run on Vercel
    if path and path.startswith("app/variants/") and path.endswith(".tsx"):
        data = _normalize_variant_tsx_for_vercel(data)
    try:
        repo = _get_github_repo(repo_name)
        try:
            existing = repo.get_contents(path)
            repo.update_file(
                path,
                body.commitMessage or "Update from Landright",
                data,
                existing.sha,
            )
        except Exception as e:
            if "404" in str(e) or "Not Found" in str(e):
                repo.create_file(path, body.commitMessage or "Update from Landright", data)
            else:
                raise
        return {"ok": True, "repo": repo_name, "path": path}
    except Exception as e:
        log.exception("Sync failed")
        raise HTTPException(status_code=502, detail=str(e)) from e


@app.get("/health")
def health():
    return {
        "status": "ok",
        "skill_loaded": bool(FRONTEND_DESIGN_SKILL),
        "cta_experience_count": len(CTA_EXPERIENCE_LIBRARY),
        "data_analyst_experience_count": len(DATA_ANALYST_EXPERIENCE_LIBRARY),
    }


def _describe_cta_structure(tsx: str) -> str:
    lines = tsx.split("\n")
    total = len(lines)
    cta_positions: list[str] = []
    for i, line in enumerate(lines):
        if re.search(r"<button|className=.*[bB]tn|onClick.*cta|data-cta|Call to action|Get started|Sign up|Contact", line, re.I):
            if total:
                pct = (i + 1) / total
                if pct <= 0.35:
                    cta_positions.append("hero/top")
                elif pct >= 0.65:
                    cta_positions.append("footer/bottom")
                else:
                    cta_positions.append("mid")
            else:
                cta_positions.append("unknown")
    if not cta_positions:
        return "CTA structure: no obvious CTAs detected (describe placement from layout)."
    return "CTA structure: " + ", ".join(cta_positions) + f" (total ~{len(cta_positions)} primary CTAs)."


def _fetch_variant_files(repo_full_name: str) -> dict[str, str]:
    repo = _get_github_repo(repo_full_name)
    out: dict[str, str] = {}
    for i in range(1, 5):
        path = f"app/variants/variant-{i}.tsx"
        try:
            content = repo.get_contents(path)
            raw = content.decoded_content.decode("utf-8")
            out[f"variant-{i}"] = raw
        except Exception as e:
            log.warning("Could not fetch %s: %s", path, e)
    return out


def _call_claude_align_cta(
    design_skill: str,
    best_cta_description: str,
    underperforming_tsx: str,
    best_variant_id: str,
    experience_library: list[str] | None = None,
    temperature: float = 0.0,
) -> str:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    import anthropic
    client = anthropic.Anthropic()
    experiences_block = ""
    if experience_library:
        bullets = "\n".join(f"• {e}" for e in experience_library[:30])
        experiences_block = (
            "\n\nWhen aligning CTAs, consider this experiential knowledge (from past alignments):\n" + bullets
        )
    system = (
        design_skill
        + "\n\n---\n\n"
        + "You are aligning an underperforming landing variant to the CTA structure of the best-performing variant. "
        + "Keep the variant's existing design and copy style; only adjust CTA placement, count, and prominence to match the best variant's structure. "
        + "Do not copy the best variant verbatim; introduce intentional variance (e.g. different button text, order) while matching structure."
        + experiences_block
    )
    user = (
        f"The best-performing variant ({best_variant_id}) has this CTA structure:\n{best_cta_description}\n\n"
        + "Rewrite the following variant TSX to align its CTA structure to the best variant. Output only valid TSX, no markdown fences or explanation.\n\n"
        + underperforming_tsx
    )
    msg = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=16000,
        system=system,
        messages=[{"role": "user", "content": user}],
        temperature=temperature,
    )
    text = ""
    for b in msg.content:
        if hasattr(b, "text"):
            text += b.text
    return text.strip()


def _push_variant_file(repo_full_name: str, variant_id: str, content: str, commit_message: str) -> None:
    path = f"app/variants/{variant_id}.tsx"
    repo = _get_github_repo(repo_full_name)
    existing = repo.get_contents(path)
    repo.update_file(path, commit_message, content, existing.sha)


def _normalize_variant_clicks(variant_clicks: dict[str, int]) -> dict[str, int]:
    """Normalize IDs and ensure all 4 variants exist (missing => 0 clicks)."""
    def to_file_key(vid: str) -> str:
        vid = (vid or "").strip()
        if vid.startswith("variant-"):
            return vid
        return f"variant-{vid}" if vid.isdigit() else vid

    normalized: dict[str, int] = {}
    for k, v in (variant_clicks or {}).items():
        nk = to_file_key(k)
        try:
            normalized[nk] = int(v or 0)
        except Exception:
            normalized[nk] = 0
    for i in range(1, 5):
        normalized.setdefault(f"variant-{i}", 0)
    return normalized


def _clicks_signature(variant_clicks: dict[str, int]) -> str:
    items = sorted((k, int(v or 0)) for k, v in variant_clicks.items())
    return "|".join(f"{k}:{v}" for k, v in items)


def _should_run_adjust_llm_judge(
    repo_full_name: str,
    variant_clicks: dict[str, int],
    experience_library: list[str],
) -> bool:
    """LLM judge: given variant click data and CTA context, decide whether to run the adjust pipeline. Uses data analyst experience library. Returns True for RUN_ADJUST."""
    normalized = _normalize_variant_clicks(variant_clicks)
    sorted_variants = sorted(normalized.items(), key=lambda x: -x[1])
    if len(sorted_variants) < 2:
        return False
    best_id, best_clicks = sorted_variants[0]
    second_id, second_clicks = sorted_variants[1]
    best_cta_desc = ""
    second_cta_desc = ""
    try:
        files = _fetch_variant_files(repo_full_name)
        if best_id in files:
            best_cta_desc = _describe_cta_structure(files[best_id])
        if second_id in files:
            second_cta_desc = _describe_cta_structure(files[second_id])
    except Exception as e:
        log.warning("Judge: could not fetch variant files: %s", e)
    variant_clicks_str = "\n".join(f"  {k}: {v} clicks" for k, v in sorted(variant_clicks.items()))
    experiences_block = ""
    if experience_library:
        bullets = "\n".join(f"• {e}" for e in experience_library[:20])
        experiences_block = "\n\nConsider this experiential knowledge:\n" + bullets
    system = (
        "You are a data analyst for a landing page A/B test. Given variant CTA click counts and CTA structure summaries, "
        "decide whether to run the CTA alignment pipeline (align underperforming variants to the best variant's CTA structure). "
        "If you recommend running it, also state what should change in the underperforming pages based on the data (CTA placement/count/prominence). "
        "Output format:\n"
        "Decision: RUN_ADJUST or SKIP\n"
        "Update: comma-separated variant ids to update (or NONE)\n"
        "Plan: 2-4 short bullets describing what CTA changes to make.\n"
        + experiences_block
    )
    user = (
        f"Variant click counts:\n{variant_clicks_str}\n\n"
        f"Best variant: {best_id} ({best_clicks} CTA clicks). CTA structure: {best_cta_desc or 'unknown'}\n\n"
        f"Second variant: {second_id} ({second_clicks} CTA clicks). CTA structure: {second_cta_desc or 'unknown'}\n\n"
        "Should we run the CTA alignment pipeline? Follow the required output format."
    )
    if not ANTHROPIC_API_KEY:
        return best_clicks - second_clicks >= CTA_THRESHOLD
    try:
        import anthropic
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=512,
            system=system,
            messages=[{"role": "user", "content": user}],
            temperature=0.0,
        )
        text = ""
        for b in msg.content:
            if hasattr(b, "text"):
                text += b.text
        raw = text.strip().upper()
        if "RUN_ADJUST" in raw:
            return True
        if "SKIP" in raw:
            return False
        return best_clicks - second_clicks >= CTA_THRESHOLD
    except Exception as e:
        log.warning("Judge failed, using threshold fallback: %s", e)
        return best_clicks - second_clicks >= CTA_THRESHOLD


def run_adjust_pipeline(repo_full_name: str, layer: str, variant_clicks: dict[str, int]) -> None:
    normalized = _normalize_variant_clicks(variant_clicks)
    sorted_variants = sorted(normalized.items(), key=lambda x: -x[1])
    if len(sorted_variants) < 2:
        return
    best_id, best_clicks = sorted_variants[0]
    second_id, second_clicks = sorted_variants[1]
    if not _should_run_adjust_llm_judge(repo_full_name, variant_clicks, DATA_ANALYST_EXPERIENCE_LIBRARY):
        return
    files = _fetch_variant_files(repo_full_name)
    if best_id not in files:
        log.warning("Best variant %s not in fetched files", best_id)
        return
    best_tsx = files[best_id]
    cta_description = _describe_cta_structure(best_tsx)
    underperforming = [vid for vid, _ in sorted_variants[1:] if vid in files]
    commit_msg = f"CTA structure alignment (best: {best_id})"
    for vid in underperforming:
        try:
            new_tsx = _call_claude_align_cta(
                FRONTEND_DESIGN_SKILL, cta_description, files[vid], best_id, experience_library=CTA_EXPERIENCE_LIBRARY
            )
            if new_tsx:
                _push_variant_file(repo_full_name, vid, new_tsx, commit_msg)
                log.info("Pushed updated %s for %s layer %s", vid, repo_full_name, layer)
        except Exception as e:
            log.exception("Failed to update %s: %s", vid, e)


def _get_cta_by_variant() -> list[dict]:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        log.warning("Supabase not configured; cron skip")
        return []
    from supabase import create_client
    client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    r = client.table("cta_by_variant").select("repo_full_name,layer,variant_id,cta_clicks").execute()
    return list(r.data or [])


def _cron_check_and_adjust():
    rows = _get_cta_by_variant()
    if not rows:
        return
    from collections import defaultdict
    by_repo_layer: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        repo = (r.get("repo_full_name") or "").strip()
        layer = (r.get("layer") or "").strip()
        if repo and layer:
            by_repo_layer[(repo, layer)].append(r)
    for (repo, layer), group in by_repo_layer.items():
        if REPO_ALLOW_LIST and repo not in REPO_ALLOW_LIST:
            continue
        raw_clicks = {r["variant_id"]: int(r.get("cta_clicks") or 0) for r in group}
        variant_clicks = _normalize_variant_clicks(raw_clicks)
        state_key = (repo, layer)
        state = _ADJUST_RUNTIME_STATE.setdefault(state_key, {"last_signature": None, "commit_times": []})
        sig = _clicks_signature(variant_clicks)
        if state.get("last_signature") == sig:
            # No new data signal; avoid repeated commits on identical click snapshot.
            continue
        # Rolling rate limit per repo/layer to prevent commit spam.
        now = time.time()
        commit_times = [t for t in state.get("commit_times", []) if now - t <= ADJUST_COMMIT_WINDOW_SECONDS]
        state["commit_times"] = commit_times
        if len(commit_times) >= MAX_ADJUST_COMMITS_PER_WINDOW:
            log.warning(
                "Adjust rate-limited for %s layer %s (%s commits in last %ss). Waiting for new data + judge approval.",
                repo, layer, len(commit_times), ADJUST_COMMIT_WINDOW_SECONDS,
            )
            continue
        try:
            run_adjust_pipeline(repo, layer, variant_clicks)
            # Record this snapshot as processed so cron doesn't keep recommitting unchanged data.
            state["last_signature"] = sig
            state["commit_times"] = [*state.get("commit_times", []), now]
        except Exception as e:
            log.exception("Adjust pipeline failed for %s layer %s: %s", repo, layer, e)


@app.post("/api/adjust-variants")
def api_adjust_variants(body: AdjustVariantsBody):
    rows = _get_cta_by_variant()
    variant_clicks = {
        r["variant_id"]: int(r.get("cta_clicks") or 0)
        for r in rows
        if (r.get("repo_full_name") or "").strip() == body.repo_full_name and (r.get("layer") or "").strip() == body.layer
    }
    variant_clicks = _normalize_variant_clicks(variant_clicks)
    try:
        run_adjust_pipeline(body.repo_full_name, body.layer, variant_clicks)
        return {"ok": True, "repo_full_name": body.repo_full_name, "layer": body.layer}
    except Exception as e:
        log.exception("Adjust failed")
        raise HTTPException(status_code=502, detail=str(e)) from e


_scheduler: BackgroundScheduler | None = None


@app.on_event("startup")
def startup():
    """Start background scheduler only when the API server starts.

    This prevents side effects (cron job + GitHub pushes) when importing this module
    from training scripts.
    """
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(_cron_check_and_adjust, "interval", seconds=CRON_INTERVAL_SECONDS, id="cta_adjust")
    _scheduler.start()


@app.on_event("shutdown")
def shutdown():
    global _scheduler
    if _scheduler is None:
        return
    _scheduler.shutdown(wait=False)
    _scheduler = None


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=4000)
