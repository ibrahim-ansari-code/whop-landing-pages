"""
Landright GitHub agent: FastAPI service with POST /sync, GET /health, and a background job
that polls Supabase cta_by_variant every 10 seconds and runs an adjust-variants pipeline (then commits)
when best - second_best CTA clicks >= threshold. Design guidance from frontend-design-skill.md.
"""
import difflib
import json
import logging
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    CLAUDE_CTA_ALIGN_TIMEOUT_SECONDS,
    CTA_THRESHOLD,
    CRON_INTERVAL_SECONDS,
    MAX_ADJUST_COMMITS_PER_WINDOW,
    MAX_VARIANT_CHARS_FOR_CTA_ALIGN,
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
_ADJUST_RUNTIME_STATE: dict[tuple[str, str], dict] = {}


def _get_cta_experience_library() -> list[str]:
    """Always re-read from file so newly appended lessons are picked up."""
    return _load_cta_experience_library()


def _get_data_analyst_experience_library() -> list[str]:
    """Always re-read from file so newly appended lessons are picked up."""
    return _load_data_analyst_experience_library()


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
    force: bool = False


class ImplementBody(BaseModel):
    repo_full_name: str
    instruction: str
    scope: str = "all"  # "variant-1" | "variant-2" | "variant-3" | "variant-4" | "all"


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


_FONT_WHITELIST = frozenset({
    "Bebas_Neue", "Playfair_Display", "Oswald", "Anton", "Archivo_Black", "Barlow_Condensed",
    "DM_Serif_Display", "Righteous", "Teko", "Ultra", "Abril_Fatface", "Alfa_Slab_One", "Fredoka_One",
    "Manrope", "Source_Sans_3", "Nunito", "DM_Sans", "Outfit", "Sora", "Plus_Jakarta_Sans",
    "Lexend", "Figtree", "Work_Sans", "Karla", "Lora", "Open_Sans", "Raleway", "Poppins",
})


def _normalize_font_names_for_vercel(text: str) -> str:
    """Replace any next/font/google font not in whitelist with Manrope."""
    s = text
    candidates = set(re.findall(r"\b([A-Z][A-Za-z0-9_]*)\s*\(\s*\{", s))
    imp = re.search(r"import\s+\{([^}]+)\}\s+from\s+['\"]next/font/google['\"]", s)
    if imp:
        for name in re.findall(r"\b([A-Za-z][A-Za-z0-9_]*)", imp.group(1)):
            candidates.add(name)
    for name in candidates:
        if name not in _FONT_WHITELIST:
            s = re.sub(r"\b" + re.escape(name) + r"\b", "Manrope", s)
    imp2 = re.search(r"(import\s+\{)([^}]+)(\}\s+from\s+['\"]next/font/google['\"])", s)
    if imp2:
        names = [x.strip() for x in imp2.group(2).split(",") if x.strip()]
        unique = list(dict.fromkeys(names))
        s = s[: imp2.start()] + imp2.group(1) + ", ".join(unique) + imp2.group(3) + s[imp2.end() :]
    return s


def _normalize_variant_tsx_for_vercel(data: str) -> str:
    """Adjust variant TSX so it can run on Vercel: strip fences, normalize quotes, BOM, font names, ensure \"use client\"."""
    if not (data or "").strip():
        return data or ""
    s = data.strip()
    # Strip markdown code fences so we never push ```tsx ... ``` into the file
    if "```" in s:
        if s.startswith("```"):
            first = s.find("\n")
            s = (s[first + 1 :] if first >= 0 else s).strip()
        if s.endswith("```"):
            s = s[: s.rfind("```")].rstrip()
    # Normalize curly/smart quotes and non-ASCII backticks
    s = s.replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"').replace("\u201b", "'")
    s = s.replace("\u02cb", "`")  # modifier letter grave -> ASCII backtick
    s = s.replace("\ufeff", "")
    for char in ("\u200b", "\u200c", "\u200d"):
        s = s.replace(char, "")
    s = s.strip()
    if not s:
        return data or ""
    s = re.sub(r"\bSource_Sans_Pro\b", "Source_Sans_3", s)
    s = re.sub(r"\bNunito_Sans\b", "Nunito", s)
    s = _normalize_font_names_for_vercel(s)
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
    # Never push unrunnable TSX files through sync (variants or generated app files).
    if path.endswith(".tsx"):
        is_runnable, validation_reason = _validate_variant_tsx_runnable(data)
        if not is_runnable:
            raise HTTPException(
                status_code=422,
                detail=f"Refusing to sync unrunnable TSX for {path}: {validation_reason}",
            )
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


def _call_claude_implement(instruction: str, current_content: str, file_label: str = "variant") -> str:
    """Ask Claude to apply the instruction to the given TSX. Returns modified TSX."""
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    import anthropic
    client = anthropic.Anthropic()
    system = (
        (FRONTEND_DESIGN_SKILL or "")
        + "\n\nYou are applying a user-requested change to a Next.js variant TSX file. "
        "Output only the modified TSX. No markdown fences, no explanation. Preserve \"use client\", imports, and valid React/JSX. "
        "Keep the file runnable (Tailwind, next/font, browser-safe)."
    )
    user = (
        f"Apply this change: {instruction}\n\n"
        f"Current {file_label} TSX:\n\n{current_content[:60000]}\n\n"
        "Output only the complete modified TSX file."
    )
    msg = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=16000,
        system=system,
        messages=[{"role": "user", "content": user}],
        temperature=0.2,
    )
    text = ""
    for b in msg.content:
        if hasattr(b, "text"):
            text += b.text
    return _strip_tsx_fences(text.strip())


@app.post("/implement")
def implement(
    body: ImplementBody,
    x_api_key: str | None = Header(None),
    authorization: str | None = Header(None),
):
    """Fetch file(s) from GitHub, apply instruction via Claude, normalize, and commit."""
    if SYNC_AGENT_API_KEY:
        token = (x_api_key or (authorization or "").replace("Bearer ", "").strip())
        if token != SYNC_AGENT_API_KEY:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")
    repo_name = (body.repo_full_name or "").strip()
    if not repo_name:
        repo_name = (GITHUB_REPO_FULL_NAME or "").strip()
    if not repo_name:
        raise HTTPException(status_code=400, detail="repo_full_name required")
    instruction = (body.instruction or "").strip()
    if not instruction:
        raise HTTPException(status_code=400, detail="instruction required")
    scope = (body.scope or "all").strip().lower()
    if scope == "all":
        variant_ids = ["variant-1", "variant-2", "variant-3", "variant-4"]
    elif scope in ("variant-1", "variant-2", "variant-3", "variant-4"):
        variant_ids = [scope]
    else:
        raise HTTPException(status_code=400, detail="scope must be variant-1, variant-2, variant-3, variant-4, or all")
    try:
        files = _fetch_variant_files(repo_name)
    except Exception as e:
        log.exception("Implement: fetch failed for %s", repo_name)
        raise HTTPException(status_code=502, detail=f"Could not fetch repo files: {e}") from e
    commit_message = f"Implement: {instruction[:72]}"
    pushed: list[str] = []
    for vid in variant_ids:
        if vid not in files:
            log.warning("Implement: skipping %s (not in repo)", vid)
            continue
        try:
            new_tsx = _call_claude_implement(instruction, files[vid], vid)
            if new_tsx:
                _push_variant_file(repo_name, vid, new_tsx, commit_message)
                pushed.append(vid)
        except Exception as e:
            log.exception("Implement: failed for %s", vid)
            raise HTTPException(status_code=502, detail=f"Failed to apply to {vid}: {e}") from e
    return {"ok": True, "repo": repo_name, "pushed": pushed, "message": f"Committed to {', '.join(pushed)}."}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "skill_loaded": bool(FRONTEND_DESIGN_SKILL),
        "cta_experience_count": len(_get_cta_experience_library()),
        "data_analyst_experience_count": len(_get_data_analyst_experience_library()),
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
    branch = getattr(repo, "default_branch", None) or "main"
    for i in range(1, 5):
        path = f"app/variants/variant-{i}.tsx"
        try:
            content = repo.get_contents(path, ref=branch)
            raw = content.decoded_content.decode("utf-8")
            out[f"variant-{i}"] = raw
        except Exception as e:
            log.warning("Could not fetch %s: %s", path, e)
    return out


# Anthropic 200k token input limit. We truncate variant TSX and optionally verify with count_tokens when large.
ANTHROPIC_INPUT_TOKEN_LIMIT = 200_000
# Target under the limit so we never hit 400 Bad Request (prompt is too long).
TARGET_INPUT_TOKENS = 194_000
# Only run count_tokens when variant might be near limit (saves API round-trips when under cap).
CHAR_THRESHOLD_FOR_TOKEN_CHECK = 80_000
TRUNCATION_SUFFIX = "\n\n// ... [truncated for API length limit]"
MAX_CTA_ADJUST_OPS = 5
MAX_CTA_ADJUST_CHANGED_LINES = 120


def _normalize_section_key(section: str | None) -> str:
    raw = re.sub(r"[^a-z0-9]+", "-", (section or "").strip().lower()).strip("-")
    if raw in {"hero-top", "top", "hero"}:
        return "hero"
    if raw in {"footer-bottom", "bottom", "footer"}:
        return "footer"
    return raw


def _strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _normalize_cta_label(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").strip().lower()).strip()


def _count_changed_lines(old: str, new: str) -> int:
    old_lines = (old or "").splitlines()
    new_lines = (new or "").splitlines()
    changed = 0
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace":
            changed += max(i2 - i1, j2 - j1)
        elif tag == "delete":
            changed += i2 - i1
        elif tag == "insert":
            changed += j2 - j1
    return changed


def _extract_json_object(raw: str) -> dict | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def _extract_alignment_tsx(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    plan = _extract_json_object(text)
    if isinstance(plan, dict):
        for key in ("tsx", "code", "content"):
            value = plan.get(key)
            if isinstance(value, str) and value.strip():
                return _strip_tsx_fences(value)
    return _strip_tsx_fences(text)


def _extract_section_ids(tsx: str) -> list[str]:
    return re.findall(r'data-landright-section\s*=\s*["\']([^"\']+)["\']', tsx or "", re.IGNORECASE)


def _validate_alignment_candidate(original_tsx: str, candidate_tsx: str) -> tuple[bool, str]:
    original = (original_tsx or "").strip()
    candidate = (candidate_tsx or "").strip()
    if not candidate:
        return False, "empty output"
    if candidate == original:
        return False, "no change"
    original_lower = original.lower()
    candidate_lower = candidate.lower()
    if '"use client"' in original_lower and '"use client"' not in candidate_lower and "'use client'" not in candidate_lower:
        return False, 'missing "use client"'
    for token in ("calendly", "widget.js", "<script"):
        if token in original_lower and token not in candidate_lower:
            return False, f"missing frozen token {token}"
    original_sections = [_normalize_section_key(section_id) for section_id in _extract_section_ids(original)]
    candidate_sections = [_normalize_section_key(section_id) for section_id in _extract_section_ids(candidate)]
    if original_sections:
        missing_sections = [section_id for section_id in original_sections if section_id not in set(candidate_sections)]
        if missing_sections:
            return False, f"missing tracked sections: {', '.join(missing_sections[:5])}"
    if len(candidate) < max(500, int(len(original) * 0.55)):
        return False, "output shrank too much"
    return True, "ok"


def _call_claude_align_cta_section_rewrite(
    design_skill: str,
    best_cta_description: str,
    underperforming_tsx: str,
    *,
    best_variant_id: str,
    underperforming_variant_id: str | None = None,
    best_clicks: int | None = None,
    best_time_sec: float | None = None,
    underperforming_clicks: int | None = None,
    underperforming_time_sec: float | None = None,
    best_section_times: dict[str, float] | None = None,
    underperforming_section_times: dict[str, float] | None = None,
    experience_library: list[str] | None = None,
    temperature: float = 0.0,
) -> str:
    editable_sections = _select_alignment_sections(underperforming_tsx, underperforming_section_times, limit=3)
    if not editable_sections:
        return ""
    tracked_sections = _extract_section_ids(underperforming_tsx)
    experiences_block = ""
    if experience_library:
        bullets = "\n".join(f"• {e}" for e in experience_library[:20])
        experiences_block = "\n\nUse this CTA learning context when relevant:\n" + bullets
    selected_blocks_text = "\n\n".join(
        f"SECTION {item['section_id']}:\n{item['block']}" for item in editable_sections
    )
    best_metrics = []
    if best_clicks is not None:
        best_metrics.append(f"{best_clicks} CTA clicks")
    if best_time_sec is not None and best_time_sec > 0:
        best_metrics.append(f"{int(round(best_time_sec))}s time on page")
    under_metrics = []
    if underperforming_clicks is not None:
        under_metrics.append(f"{underperforming_clicks} CTA clicks")
    if underperforming_time_sec is not None and underperforming_time_sec > 0:
        under_metrics.append(f"{int(round(underperforming_time_sec))}s time on page")
    system = (
        design_skill
        + "\n\n---\n\n"
        + "You are revising CTA-related tracked sections of an underperforming landing page variant. "
        + "Return only the rewritten tracked sections using this exact wrapper format for each changed section:\n"
        + "<!-- LANDRIGHT-SECTION:hero -->\n<section data-landright-section=\"hero\">...</section>\n<!-- /LANDRIGHT-SECTION -->\n"
        + "Only include tracked sections you are changing. "
        + "Within those sections you have full control over CTA structure, CTA prominence, CTA labels, CTA-local wrappers, and CTA placement. "
        + "Keep the variant's design language and overall identity intact, and make it more similar to the winner's CTA strategy without copying it exactly. "
        + "Do not introduce new React state, helper functions, modal toggles, undefined handlers, or fake embed behavior. "
        + "Preserve any existing embed/widget/script markup if it appears inside a returned section. "
        + "Do not rename or remove data-landright-section values. "
        + "Output only the wrapped section blocks, with no explanation."
        + experiences_block
    )
    user = (
        f"Best-performing variant: {best_variant_id}. CTA structure summary: {best_cta_description}\n"
        + (f"Best metrics: {', '.join(best_metrics)}.\n" if best_metrics else "")
        + (f"Underperforming variant {underperforming_variant_id} metrics: {', '.join(under_metrics)}.\n" if under_metrics else "")
        + f"Tracked sections in the full file that must still exist: {', '.join(tracked_sections) if tracked_sections else 'none'}.\n"
        + f"Highest-engagement sections in the best variant: {_summarize_section_engagement(best_section_times or {})}.\n"
        + f"Highest-engagement sections in the underperforming variant: {_summarize_section_engagement(underperforming_section_times or {})}.\n"
        + "Rewrite only the tracked sections below. Keep each returned section self-contained, valid TSX, and preserve its data-landright-section id.\n\n"
        + selected_blocks_text
    )
    import anthropic
    client = anthropic.Anthropic(
        timeout=float(CLAUDE_CTA_ALIGN_TIMEOUT_SECONDS),
        max_retries=2,
    )
    try:
        msg = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=5000,
            system=system,
            messages=[{"role": "user", "content": user}],
            temperature=temperature,
        )
    except Exception as e:
        log.warning("CTA section-rewrite LLM failed: %s", e)
        return ""
    text = ""
    for b in msg.content:
        if hasattr(b, "text"):
            text += b.text
    preview = (text.strip()[:300] + "…") if len(text.strip()) > 300 else text.strip()
    rewrites = _extract_alignment_section_rewrites(text)
    if not rewrites:
        log.warning("CTA section-rewrite returned invalid section blocks; preview=%r", preview)
        return ""
    candidate = _apply_alignment_section_rewrites(underperforming_tsx, rewrites)
    if not candidate:
        log.warning("CTA section-rewrite could not be applied; preview=%r", preview)
        return ""
    ok, reason = _validate_alignment_candidate(underperforming_tsx, candidate)
    if not ok:
        log.warning("CTA section-rewrite returned invalid TSX (%s); preview=%r", reason, preview)
        return ""
    return candidate


def _contains_frozen_markup(snippet: str) -> bool:
    lower = (snippet or "").lower()
    return any(
        token in lower
        for token in (
            "calendly",
            "widget.js",
            "<script",
            "data-landright-section",
            'import ',
            '"use client"',
            "'use client'",
        )
    )


def _summarize_cta_candidates(candidates: list[dict], limit: int = 8) -> str:
    if not candidates:
        return "none"
    parts = []
    for item in candidates[:limit]:
        section = item.get("section_id") or "unknown"
        parts.append(f'{item["label"]} @ {section}')
    return ", ".join(parts)


def _summarize_section_engagement(section_times: dict[str, float], limit: int = 4) -> str:
    if not section_times:
        return "none"
    ordered = sorted(section_times.items(), key=lambda item: -float(item[1] or 0))
    return ", ".join(f"{section} ({int(round(total))}s)" for section, total in ordered[:limit] if total)


def _get_section_ranges(tsx: str) -> list[dict]:
    matches = list(re.finditer(r'data-landright-section\s*=\s*["\']([^"\']+)["\']', tsx, re.IGNORECASE))
    out: list[dict] = []
    for idx, match in enumerate(matches):
        section_id = _normalize_section_key(match.group(1))
        open_end = tsx.find(">", match.start())
        if open_end == -1:
            continue
        next_start = matches[idx + 1].start() if idx + 1 < len(matches) else len(tsx)
        out.append({
            "section_id": section_id,
            "open_end": open_end + 1,
            "start": match.start(),
            "end": next_start,
        })
    return out


def _section_for_pos(ranges: list[dict], pos: int) -> str | None:
    for rng in ranges:
        if rng["start"] <= pos < rng["end"]:
            return rng["section_id"]
    return None


def _find_matching_close_tag(tsx: str, open_match: re.Match[str]) -> int | None:
    tag = open_match.group("tag")
    token_re = re.compile(rf"</?{re.escape(tag)}\b[^>]*>", re.IGNORECASE)
    depth = 0
    for token in token_re.finditer(tsx, open_match.start()):
        text = token.group(0)
        is_close = text.startswith("</")
        self_closing = text.endswith("/>")
        if not is_close:
            depth += 1
            if self_closing:
                depth -= 1
        else:
            depth -= 1
            if depth == 0:
                return token.end()
    return None


def _get_section_blocks(tsx: str) -> list[dict]:
    pattern = re.compile(
        r"<(?P<tag>[A-Za-z][\w]*)\b(?P<attrs>[^>]*)data-landright-section\s*=\s*[\"'](?P<section_id>[^\"']+)[\"'](?P<attrs2>[^>]*)>",
        re.IGNORECASE,
    )
    blocks: list[dict] = []
    for match in pattern.finditer(tsx or ""):
        end = _find_matching_close_tag(tsx, match)
        if end is None:
            continue
        blocks.append({
            "section_id": _normalize_section_key(match.group("section_id")),
            "start": match.start(),
            "end": end,
            "block": tsx[match.start():end],
            "tag": match.group("tag"),
        })
    return blocks


def _select_alignment_sections(tsx: str, section_times: dict[str, float] | None = None, limit: int = 3) -> list[dict]:
    blocks = _get_section_blocks(tsx)
    if not blocks:
        return []
    section_times = section_times or {}
    candidates = _find_cta_candidates(tsx, _get_section_ranges(tsx))
    ranked_ids: list[str] = []
    for candidate in candidates:
        section_id = _normalize_section_key(candidate.get("section_id"))
        if section_id and section_id not in ranked_ids:
            ranked_ids.append(section_id)
    for section_id, _ in sorted(section_times.items(), key=lambda item: -float(item[1] or 0)):
        normalized = _normalize_section_key(section_id)
        if normalized and normalized not in ranked_ids:
            ranked_ids.append(normalized)
    for preferred in ("hero", "pricing", "cta", "footer"):
        if preferred not in ranked_ids and any(block["section_id"] == preferred for block in blocks):
            ranked_ids.append(preferred)
    selected: list[dict] = []
    for section_id in ranked_ids:
        block = next((b for b in blocks if b["section_id"] == section_id), None)
        if block and block not in selected:
            selected.append(block)
        if len(selected) >= limit:
            break
    if not selected:
        selected.append(blocks[0])
    return selected


def _extract_alignment_section_rewrites(raw: str) -> list[dict]:
    text = _strip_tsx_fences((raw or "").strip())
    if not text:
        return []
    pattern = re.compile(
        r"<!--\s*LANDRIGHT-SECTION:(?P<section_id>[\w\-]+)\s*-->\s*(?P<tsx>[\s\S]*?)\s*<!--\s*/LANDRIGHT-SECTION\s*-->",
        re.IGNORECASE,
    )
    out: list[dict] = []
    for match in pattern.finditer(text):
        section_id = _normalize_section_key(match.group("section_id"))
        tsx_block = (match.group("tsx") or "").strip()
        if section_id and tsx_block:
            out.append({"section_id": section_id, "tsx": _strip_tsx_fences(tsx_block)})
    return out


def _apply_alignment_section_rewrites(original_tsx: str, rewrites: list[dict]) -> str:
    if not rewrites:
        return ""
    blocks = _get_section_blocks(original_tsx)
    if not blocks:
        return ""
    replacement_by_id: dict[str, str] = {}
    for item in rewrites:
        section_id = _normalize_section_key(item.get("section_id"))
        tsx_block = (item.get("tsx") or "").strip()
        if not section_id or not tsx_block:
            continue
        tsx_block = re.sub(
            r'(data-landright-section\s*=\s*["\'])([^"\']+)(["\'])',
            lambda m: f"{m.group(1)}{section_id}{m.group(3)}",
            tsx_block,
            count=1,
            flags=re.IGNORECASE,
        )
        if f'data-landright-section="{section_id}"' not in tsx_block and f"data-landright-section='{section_id}'" not in tsx_block:
            continue
        replacement_by_id[section_id] = tsx_block
    if not replacement_by_id:
        return ""
    parts: list[str] = []
    cursor = 0
    applied = 0
    for block in sorted(blocks, key=lambda item: item["start"]):
        parts.append(original_tsx[cursor:block["start"]])
        replacement = replacement_by_id.get(block["section_id"])
        if replacement:
            parts.append(replacement)
            applied += 1
        else:
            parts.append(block["block"])
        cursor = block["end"]
    parts.append(original_tsx[cursor:])
    if applied == 0:
        return ""
    return "".join(parts)


def _find_cta_candidates(tsx: str, section_ranges: list[dict]) -> list[dict]:
    candidates: list[dict] = []
    pattern = re.compile(r"<(?P<tag>a|button|Button|Link)\b(?P<attrs>[^>]*)>(?P<inner>[\s\S]*?)</(?P=tag)>", re.IGNORECASE)
    for match in pattern.finditer(tsx):
        full_tag = match.group(0)
        label = _strip_tags(match.group("inner"))
        if not label or len(label) > 80:
            continue
        attrs = match.group("attrs") or ""
        attrs_lower = attrs.lower()
        tag_lower = (match.group("tag") or "").lower()
        context = tsx[max(0, match.start() - 250) : min(len(tsx), match.end() + 250)]
        lower_context = context.lower()
        if "calendly" in lower_context or "widget.js" in lower_context or "<script" in lower_context:
            continue
        cta_phrase = bool(re.search(r"(get started|start|sign up|book|contact|learn more|join|apply|try|free|demo|quote)", label, re.IGNORECASE))
        cta_like = (
            tag_lower in {"a", "button"}
            or "href=" in attrs_lower
            or "onclick" in attrs_lower
            or "data-cta" in attrs_lower
            or "role=\"button\"" in attrs_lower
            or "role='button'" in attrs_lower
            or "btn" in attrs_lower
            or "button" in attrs_lower
            or cta_phrase
        )
        if not cta_like:
            continue
        section_id = _section_for_pos(section_ranges, match.start())
        candidates.append({
            "tag": match.group("tag"),
            "attrs": attrs,
            "inner": match.group("inner"),
            "label": label,
            "start": match.start(),
            "end": match.end(),
            "full_tag": full_tag,
            "section_id": section_id,
        })
    return candidates


def _find_target_section(section_ranges: list[dict], requested: str | None) -> dict | None:
    normalized = _normalize_section_key(requested)
    if not normalized:
        return section_ranges[0] if section_ranges else None
    for rng in section_ranges:
        if rng["section_id"] == normalized or normalized in rng["section_id"]:
            return rng
    return section_ranges[0] if section_ranges else None


def _replace_inner_text(full_tag: str, new_label: str) -> str:
    match = re.match(r"<(?P<tag>a|button|Button|Link)\b(?P<attrs>[^>]*)>(?P<inner>[\s\S]*?)</(?P=tag)>", full_tag, re.IGNORECASE)
    if not match:
        return full_tag
    tag = match.group("tag")
    attrs = match.group("attrs")
    return f"<{tag}{attrs}>{new_label}</{tag}>"


def _insert_cta_into_section(tsx: str, target_section: dict, cta_tag: str) -> str:
    insert_at = target_section["open_end"]
    return tsx[:insert_at] + "\n" + cta_tag + tsx[insert_at:]


def _sanitize_cta_html(new_html: str, fallback_label: str = "") -> str:
    """Keep LLM-generated CTA markup when possible, but strip obviously unrunnable handlers."""
    snippet = (new_html or "").strip()
    if not snippet:
        return ""
    # Claude sometimes invents local state handlers that do not exist in the file.
    snippet = re.sub(r"\s+onClick=\{[^{}]*set[A-Z][^{}]*\}", "", snippet)
    snippet = re.sub(r"\s+onClick=\{[^{}]*(?:Calendly|Modal|Popup|Dialog|Open)[^{}]*\}", "", snippet)
    snippet = re.sub(r"\s+onClick=\"[^\"]*\"", "", snippet)
    snippet = re.sub(r"\s+onClick='[^']*'", "", snippet)
    if _contains_frozen_markup(snippet):
        return ""
    if re.search(r"<button\b", snippet, re.IGNORECASE) and not re.search(r"<button\b[^>]*\btype=", snippet, re.IGNORECASE):
        snippet = re.sub(r"<button\b", "<button type=\"button\"", snippet, count=1, flags=re.IGNORECASE)
    if re.search(r"<(?:a|button|Button|Link)\b", snippet, re.IGNORECASE):
        return snippet
    label = (fallback_label or "").strip() or "Get Started"
    return f'<button type="button" className="inline-flex items-center rounded-xl bg-zinc-900 px-6 py-3 text-sm font-semibold text-white">{label}</button>'


def _build_fallback_cta_ops(
    tsx: str,
    *,
    section_times: dict[str, float] | None = None,
    desired_cta_count: int | None = None,
) -> list[dict]:
    section_ranges = _get_section_ranges(tsx)
    candidates = _find_cta_candidates(tsx, section_ranges)
    if not candidates:
        return []
    section_times = section_times or {}
    current_count = len(candidates)
    primary = max(candidates, key=lambda c: float(section_times.get(c.get("section_id") or "", 0)))
    target_section = None
    if section_ranges:
        ranked_sections = sorted(
            [rng for rng in section_ranges if rng.get("section_id")],
            key=lambda rng: -float(section_times.get(rng["section_id"], 0)),
        )
        target_section = next(
            (rng for rng in ranked_sections if rng["section_id"] != primary.get("section_id")),
            None,
        ) or next(
            (rng for rng in section_ranges if rng["section_id"] and rng["section_id"] != primary.get("section_id")),
            None,
        )
    if desired_cta_count is not None and desired_cta_count < current_count:
        removal = min(candidates, key=lambda c: float(section_times.get(c.get("section_id") or "", 0)))
        return [{
            "op": "remove_cta",
            "source_label": removal["label"],
        }]
    if desired_cta_count is not None and desired_cta_count > current_count and target_section:
        return [{
            "op": "duplicate_cta",
            "source_label": primary["label"],
            "target_section": target_section["section_id"],
            "new_label": primary["label"],
        }]
    if target_section:
        return [{
            "op": "move_cta",
            "source_label": primary["label"],
            "target_section": target_section["section_id"],
            "new_label": primary["label"],
        }]
    return [{
        "op": "relabel_cta",
        "source_label": primary["label"],
        "new_label": primary["label"] if primary["label"].endswith(" Now") else f"{primary['label']} Now",
    }]


def _build_last_resort_cta_ops(tsx: str, section_times: dict[str, float] | None = None) -> list[dict]:
    """Always try to produce one tiny, safe CTA diff when normal planning cannot be applied."""
    section_ranges = _get_section_ranges(tsx)
    candidates = _find_cta_candidates(tsx, section_ranges)
    if not candidates:
        return []
    section_times = section_times or {}
    primary = max(candidates, key=lambda c: float(section_times.get(c.get("section_id") or "", 0)))
    label = primary["label"]
    normalized = _normalize_cta_label(label)
    if " now" not in f" {normalized} ":
        new_label = f"{label} Now"
    elif " today" not in f" {normalized} ":
        new_label = f"{label} Today"
    else:
        new_label = f"{label}!"
    return [{
        "op": "relabel_cta",
        "source_label": label,
        "new_label": new_label,
    }]


def _find_matching_cta_candidate(candidates: list[dict], source_label: str) -> dict | None:
    if not candidates:
        return None
    if not source_label:
        return candidates[0]
    exact = next((c for c in candidates if c["label"] == source_label), None)
    if exact:
        return exact
    normalized_source = _normalize_cta_label(source_label)
    if not normalized_source:
        return candidates[0]
    normalized_matches = [
        c for c in candidates
        if _normalize_cta_label(c.get("label") or "") == normalized_source
    ]
    if normalized_matches:
        return normalized_matches[0]
    partial_matches = [
        c for c in candidates
        if normalized_source in _normalize_cta_label(c.get("label") or "")
        or _normalize_cta_label(c.get("label") or "") in normalized_source
    ]
    if partial_matches:
        return partial_matches[0]
    return None


def _apply_cta_ops(tsx: str, operations: list[dict]) -> str:
    updated = tsx
    applied = 0
    for op in operations[:MAX_CTA_ADJUST_OPS]:
        section_ranges = _get_section_ranges(updated)
        candidates = _find_cta_candidates(updated, section_ranges)
        op_name = (op.get("op") or "").strip().lower()
        source_label = (op.get("source_label") or op.get("label") or "").strip()
        new_label = (op.get("new_label") or "").strip()
        new_html = (op.get("new_html") or "").strip()
        target_section = _find_target_section(section_ranges, op.get("target_section") or op.get("section"))
        safe_new_html = _sanitize_cta_html(new_html, new_label or source_label)

        source = _find_matching_cta_candidate(candidates, source_label)
        if op_name == "relabel_cta" and source and new_label:
            replacement = _replace_inner_text(source["full_tag"], new_label)
            updated = updated[: source["start"]] + replacement + updated[source["end"] :]
            applied += 1
        elif op_name == "remove_cta" and source:
            updated = updated[: source["start"]] + updated[source["end"] :]
            applied += 1
        elif op_name == "add_cta" and target_section:
            inserted = safe_new_html
            if not inserted and source:
                inserted = _replace_inner_text(source["full_tag"], new_label) if new_label else source["full_tag"]
            if inserted:
                updated = _insert_cta_into_section(updated, target_section, inserted)
                applied += 1
        elif op_name == "duplicate_cta" and source and target_section:
            duplicate = safe_new_html or (_replace_inner_text(source["full_tag"], new_label) if new_label else source["full_tag"])
            updated = _insert_cta_into_section(updated, target_section, duplicate)
            applied += 1
        elif op_name == "move_cta" and source and target_section:
            moved = safe_new_html or (_replace_inner_text(source["full_tag"], new_label) if new_label else source["full_tag"])
            without_source = updated[: source["start"]] + updated[source["end"] :]
            target_section_after_remove = _find_target_section(_get_section_ranges(without_source), op.get("target_section") or op.get("section"))
            if target_section_after_remove:
                updated = _insert_cta_into_section(without_source, target_section_after_remove, moved)
                applied += 1
        elif op_name == "replace_cta_block" and source and safe_new_html:
            updated = updated[: source["start"]] + safe_new_html + updated[source["end"] :]
            applied += 1
    if applied == 0:
        return ""
    if _count_changed_lines(tsx, updated) > MAX_CTA_ADJUST_CHANGED_LINES:
        log.warning(
            "Skipping CTA op result: diff too large (%s changed lines > %s)",
            _count_changed_lines(tsx, updated),
            MAX_CTA_ADJUST_CHANGED_LINES,
        )
        return ""
    return updated


def _call_claude_align_cta(
    design_skill: str,
    best_cta_description: str,
    underperforming_tsx: str,
    best_variant_id: str,
    experience_library: list[str] | None = None,
    temperature: float = 0.0,
    *,
    underperforming_variant_id: str | None = None,
    best_cta_count: int | None = None,
    best_clicks: int | None = None,
    best_time_sec: float | None = None,
    underperforming_clicks: int | None = None,
    underperforming_time_sec: float | None = None,
    best_section_times: dict[str, float] | None = None,
    underperforming_section_times: dict[str, float] | None = None,
) -> str:
    """Ask Claude to rewrite the full TSX with CTA-local structural improvements."""
    raw_tsx = (underperforming_tsx or "").strip()
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    import anthropic
    client = anthropic.Anthropic(
        timeout=float(CLAUDE_CTA_ALIGN_TIMEOUT_SECONDS),
        max_retries=2,
    )

    experiences_block = ""
    if experience_library:
        intro = "\n\nWhen aligning CTAs, consider this experiential knowledge (from past alignments):\n"
        max_experiences_chars = 10_000
        bullets = "\n".join(f"• {e}" for e in experience_library[:30])
        if len(bullets) > max_experiences_chars:
            bullets = bullets[: max_experiences_chars] + "\n• [additional entries omitted for length]"
        experiences_block = intro + bullets
    section_ranges = _get_section_ranges(raw_tsx)
    candidates = _find_cta_candidates(raw_tsx, section_ranges)
    tracked_sections = _extract_section_ids(raw_tsx)
    system = (
        design_skill
        + "\n\n---\n\n"
        + "You are aligning an underperforming landing variant to the CTA structure of the best-performing variant. "
        + "Return the complete modified TSX file, not JSON and not a patch. "
        + "You may change CTA count, CTA placement, CTA prominence, CTA labels, and CTA-local wrappers, but keep the same overall design language, layout personality, palette, typography, spacing feel, and variant identity. "
        + "Make the CTA strategy more similar to the winner, not identical to it. "
        + "Do not flatten the page into the winner's exact structure. "
        + "Do not introduce new React state, helper functions, modal toggles, undefined handlers, or synthetic embed behavior. "
        + "If the file already contains Calendly, scripts, imports, or data-landright-section attributes, preserve them. "
        + "Preserve every existing data-landright-section id and keep the tracked sections in the same order. "
        + "Preserve the file's existing imports and top-level structure. "
        + "Prefer self-contained CTA markup such as <a> or <button type=\"button\"> when introducing or upgrading CTAs. "
        + "Output only the final TSX file."
        + experiences_block
    )
    user_prefix_base = (
        f"The best-performing variant ({best_variant_id}) has this CTA structure:\n{best_cta_description}\n\n"
    )
    if best_clicks is not None or best_time_sec is not None or underperforming_clicks is not None or underperforming_time_sec is not None:
        parts = []
        if best_clicks is not None:
            parts.append(f"Best variant had {best_clicks} CTA clicks")
        if best_time_sec is not None and best_time_sec > 0:
            parts.append(f"{int(round(best_time_sec))}s total time on page")
        if parts:
            user_prefix_base += "The best variant had " + " and ".join(parts) + ".\n"
        metrics_under = []
        if underperforming_clicks is not None:
            metrics_under.append(f"{underperforming_clicks} CTA clicks")
        if underperforming_time_sec is not None and underperforming_time_sec > 0:
            metrics_under.append(f"{int(round(underperforming_time_sec))}s time on page")
        if underperforming_variant_id and metrics_under:
            user_prefix_base += f"The underperforming variant ({underperforming_variant_id}) had " + " and ".join(metrics_under) + ".\n"
        elif metrics_under:
            user_prefix_base += "The underperforming variant had " + " and ".join(metrics_under) + ".\n"
        user_prefix_base += "Prefer placing or reinforcing CTAs in sections that get more view time (e.g. Hero, above-fold) so engagement and time-on-page are both considered.\n\n"
    user_prefix_base += (
        f"Detected safe CTA candidates in the underperforming variant: {_summarize_cta_candidates(candidates)}.\n"
        f"Tracked sections that must still exist after editing: {', '.join(tracked_sections) if tracked_sections else 'none'}.\n"
        f"Highest-engagement sections in the underperforming variant: {_summarize_section_engagement(underperforming_section_times or {})}.\n"
        f"Highest-engagement sections in the best variant: {_summarize_section_engagement(best_section_times or {})}.\n"
    )
    user_prefix_base += (
        "Rewrite the full file while changing only what is needed to improve CTA structure. "
        "Keep the variant distinct from the winner outside CTA-local areas. "
        "Do not modify Calendly behavior, scripts, imports, data-landright-section attributes, or layout scaffolding. "
        "Do not output markdown or explanation."
    )

    max_chars = min(len(raw_tsx), MAX_VARIANT_CHARS_FOR_CTA_ALIGN)
    truncated = len(raw_tsx) > max_chars
    tsx_to_send = raw_tsx[:max_chars] + (TRUNCATION_SUFFIX if truncated else "")
    if truncated:
        log.warning(
            "Variant TSX truncated to %s chars for Claude request (200k token limit)",
            max_chars,
        )
        return _call_claude_align_cta_section_rewrite(
            design_skill,
            best_cta_description,
            raw_tsx,
            best_variant_id=best_variant_id,
            underperforming_variant_id=underperforming_variant_id,
            best_clicks=best_clicks,
            best_time_sec=best_time_sec,
            underperforming_clicks=underperforming_clicks,
            underperforming_time_sec=underperforming_time_sec,
            best_section_times=best_section_times,
            underperforming_section_times=underperforming_section_times,
            experience_library=experience_library,
            temperature=temperature,
        )

    # Only run count_tokens when we might be near token limit (saves round-trips for typical 70k cap).
    if max_chars > CHAR_THRESHOLD_FOR_TOKEN_CHECK:
        for attempt in range(5):
            prefix_with_note = user_prefix_base + (
                "\n\nThe file was truncated; preserve visible design and return a full TSX file that only changes visible CTA-local areas. Do not assume you can edit hidden sections." if truncated else ""
            )
            user = prefix_with_note + "\n\n" + tsx_to_send
            try:
                ct = client.messages.count_tokens(
                    model=ANTHROPIC_MODEL,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                input_tokens = ct.input_tokens
            except Exception as e:
                log.warning("count_tokens not available (%s), relying on char limit only", e)
                input_tokens = 0
            if input_tokens <= TARGET_INPUT_TOKENS or input_tokens == 0:
                break
            if max_chars <= 20_000:
                break
            ratio = TARGET_INPUT_TOKENS / max(input_tokens, 1)
            new_max = max(20_000, int(max_chars * ratio * 0.95))
            if new_max >= max_chars:
                new_max = max(20_000, max_chars - 30_000)
            max_chars = new_max
            truncated = True
            tsx_to_send = raw_tsx[:max_chars] + TRUNCATION_SUFFIX
            log.warning(
                "Prompt was %s tokens; truncating variant to %s chars to stay under %s",
                input_tokens, max_chars, TARGET_INPUT_TOKENS,
            )

    final_user_prefix = user_prefix_base + (
        "\n\nThe file was truncated; output a full TSX file and only change visible CTA-local areas while preserving the overall page design and structure." if truncated else ""
    )
    user = final_user_prefix + "\n\n" + tsx_to_send
    try:
        msg = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=7000,
            system=system,
            messages=[{"role": "user", "content": user}],
            temperature=temperature,
        )
    except Exception as e:
        log.warning("CTA-align LLM failed: %s", e)
        return ""
    text = ""
    for b in msg.content:
        if hasattr(b, "text"):
            text += b.text
    preview = (text.strip()[:300] + "…") if len(text.strip()) > 300 else text.strip()
    candidate = _extract_alignment_tsx(text.strip())
    ok, reason = _validate_alignment_candidate(raw_tsx, candidate)
    if not ok:
        log.warning("CTA-align returned invalid TSX (%s); preview=%r", reason, preview)
        return ""
    return candidate


def _strip_tsx_fences(raw: str) -> str:
    """Remove markdown code fences (```tsx ... ```) that Claude sometimes adds despite instructions."""
    s = raw.strip()
    if s.startswith("```"):
        first_nl = s.index("\n") if "\n" in s else len(s)
        s = s[first_nl + 1:]
    if s.endswith("```"):
        s = s[: -3]
    return s.strip()


def _validate_variant_tsx_runnable(content: str) -> tuple[bool, str]:
    """Validate that generated TSX is syntactically runnable enough to avoid pushing obvious build breakers."""
    normalized = _normalize_variant_tsx_for_vercel(content or "")
    if not normalized.strip():
        return False, "empty TSX output"
    if "[truncated for API length limit]" in normalized:
        return False, "output still contains truncation marker"

    repo_root = Path(__file__).resolve().parents[2]
    ts_module = repo_root / "landright-app" / "node_modules" / "typescript" / "lib" / "typescript.js"
    if not ts_module.exists():
        return False, f"TypeScript validator unavailable at {ts_module}"

    node_script = f"""
const fs = require("fs");
const ts = require({str(ts_module)!r});
const source = fs.readFileSync(0, "utf8");
const result = ts.transpileModule(source, {{
  fileName: "variant.tsx",
  reportDiagnostics: true,
  compilerOptions: {{
    target: ts.ScriptTarget.ES2020,
    module: ts.ModuleKind.ESNext,
    jsx: ts.JsxEmit.Preserve,
  }},
}});
const diagnostics = (result.diagnostics || []).filter((d) => d.category === ts.DiagnosticCategory.Error);
if (diagnostics.length === 0) {{
  process.stdout.write("OK");
  process.exit(0);
}}
const message = diagnostics
  .slice(0, 5)
  .map((d) => ts.flattenDiagnosticMessageText(d.messageText, "\\n"))
  .join("\\n");
process.stdout.write(message);
process.exit(1);
"""
    try:
        proc = subprocess.run(
            ["node", "-e", node_script],
            input=normalized,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except Exception as e:
        return False, f"TSX validation failed to run: {e}"

    if proc.returncode == 0:
        return True, "ok"

    reason = (proc.stdout or proc.stderr or "unknown TypeScript error").strip()
    return False, reason[:500]


def _push_variant_file(repo_full_name: str, variant_id: str, content: str, commit_message: str) -> None:
    path = f"app/variants/{variant_id}.tsx"
    content = _normalize_variant_tsx_for_vercel(content)
    repo = _get_github_repo(repo_full_name)
    branch = getattr(repo, "default_branch", None) or "main"
    log.info("Push: getting contents %s on branch %s for %s", path, branch, repo_full_name)
    existing = repo.get_contents(path, ref=branch)
    result = repo.update_file(path, commit_message, content, existing.sha, branch=branch)
    commit = result.get("commit") if isinstance(result, dict) else getattr(result, "commit", None)
    if commit is not None:
        sha = getattr(commit, "sha", None) or (commit.get("sha") if isinstance(commit, dict) else None)
        if sha:
            log.info("Pushed %s to %s branch %s commit %s", path, repo_full_name, branch, sha)
        else:
            log.info("Pushed %s to %s branch %s", path, repo_full_name, branch)
    else:
        log.info("Pushed %s to %s branch %s", path, repo_full_name, branch)


def _analyze_variant_structure(tsx: str) -> dict:
    """Mirror of backend _analyze_variant_structure: sections, CTAs, colors, fonts, responsive, animated, line count."""
    text = (tsx or "").strip()
    sections_found: list[str] = []
    for label in ("Navigation", "Hero", "Features", "Testimonials", "Social Proof", "Pricing", "FAQ", "Footer"):
        if re.search(rf"\b{re.escape(label)}\b", text, re.IGNORECASE):
            sections_found.append(label)
    cta_labels: list[str] = []
    for m in re.finditer(r">\s*([^<{]+?)\s*</(?:button|a)\s*>", text):
        label = m.group(1).strip()
        if label and len(label) < 80 and label not in cta_labels:
            cta_labels.append(label)
    for m in re.finditer(r'["\']([^"\']{2,50})["\']\s*[}>].*?(?:button|Button|CTA)', text, re.IGNORECASE | re.DOTALL):
        label = m.group(1).strip()
        if label and label not in cta_labels:
            cta_labels.append(label)
    color_classes: list[str] = []
    for m in re.finditer(r"\b(bg|text|border)-([a-z0-9\-]+?)(?:\s|\)|\"|')", text):
        full = f"{m.group(1)}-{m.group(2)}"
        if full not in color_classes and len(color_classes) < 12:
            color_classes.append(full)
    font_imports: list[str] = []
    if "next/font" in text:
        font_imports.append("next/font")
    for m in re.finditer(r"@import\s+[\"']([^\"']+)[\"']", text):
        font_imports.append(m.group(1).strip()[:60])
    responsive = bool(re.search(r"\b(sm|md|lg|xl|2xl):", text))
    animated = bool(re.search(r"\b(animate-|transition)", text))
    return {
        "sections": sections_found,
        "ctas": cta_labels[:20],
        "tailwindColors": color_classes,
        "fontImports": font_imports[:10],
        "responsive": responsive,
        "animated": animated,
        "lineCount": len(text.splitlines()),
    }


def _write_adjustment_log(
    repo_full_name: str,
    layer: str,
    best_variant_id: str,
    clicks_before: dict[str, int],
    times_before: dict[str, float] | None = None,
) -> None:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return
    try:
        from supabase import create_client
        client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        payload: dict = {
            "repo_full_name": repo_full_name,
            "layer": layer,
            "best_variant_id": best_variant_id,
            "clicks_before": clicks_before,
        }
        if times_before is not None:
            payload["times_before"] = times_before
        client.table("adjustment_log").insert(payload).execute()
    except Exception as e:
        log.warning("Failed to write adjustment_log: %s", e)


def _record_snapshot_supabase(repo_full_name: str, layer: str, variant_id: str, tsx_content: str, source: str = "agent_adjust") -> None:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return
    try:
        analysis = _analyze_variant_structure(tsx_content)
        from supabase import create_client
        client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        client.table("variant_snapshots").insert({
            "repo_full_name": repo_full_name,
            "layer": layer,
            "variant_id": variant_id,
            "source": source,
            "sections": analysis.get("sections") or [],
            "ctas": analysis.get("ctas") or [],
            "tailwind_colors": analysis.get("tailwindColors") or [],
            "font_imports": analysis.get("fontImports") or [],
            "responsive": bool(analysis.get("responsive")),
            "animated": bool(analysis.get("animated")),
            "line_count": analysis.get("lineCount"),
        }).execute()
    except Exception as e:
        log.warning("Failed to record variant_snapshot for %s: %s", variant_id, e)


def _append_experience_file(path_resolved: Path | None, entry: str) -> None:
    """Append one lesson to a JSON experience library file (list or { experienceLibrary: list })."""
    if not path_resolved or not path_resolved.exists() or not entry or not entry.strip():
        return
    import json
    try:
        raw = path_resolved.read_text(encoding="utf-8")
        data = json.loads(raw)
        if isinstance(data, list):
            data.append(entry.strip())
        elif isinstance(data, dict) and "experienceLibrary" in data:
            data["experienceLibrary"] = list(data["experienceLibrary"]) + [entry.strip()]
        else:
            data = [entry.strip()]
        path_resolved.write_text(json.dumps(data, indent=2), encoding="utf-8")
        log.info("Appended to %s", path_resolved.name)
    except Exception as e:
        log.warning("Failed to append experience file %s: %s", path_resolved, e)


def _insert_experience_entry_supabase(source: str, entry: str) -> None:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY or source not in ("generation", "cta", "data_analyst"):
        return
    try:
        from supabase import create_client
        client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        client.table("experience_library_entries").insert({"source": source, "entry": entry.strip()}).execute()
    except Exception as e:
        log.warning("Failed to insert experience_library_entries: %s", e)


ADJUSTMENT_EVALUATION_MIN_AGE_SEC = int(os.environ.get("ADJUSTMENT_EVALUATION_MIN_AGE_SEC", "3600"))
_GENERATION_LESSONS_WRITTEN: set[tuple[str, str, str]] = set()


def _get_time_by_section_map(client, repo: str, layer: str) -> dict[str, dict[str, float]]:
    """Load section-level time aggregates for a repo/layer as {variant_id: {section_id: total_seconds}}."""
    from collections import defaultdict

    out: dict[str, dict[str, float]] = defaultdict(dict)
    try:
        rows = (
            client.table("time_by_section")
            .select("variant_id,section_id,total_seconds")
            .eq("repo_full_name", repo)
            .eq("layer", layer)
            .execute()
        )
        for row in rows.data or []:
            vid = (row.get("variant_id") or "").strip()
            section_id = (row.get("section_id") or "").strip()
            if not vid or not section_id:
                continue
            out[vid][section_id] = float(row.get("total_seconds") or 0)
    except Exception as e:
        log.debug("time_by_section fetch failed for %s layer %s: %s", repo, layer, e)
    return dict(out)


def _top_section_summary(section_times: dict[str, float], limit: int = 3) -> str:
    """Human summary of top engaged sections, e.g. 'hero (120s), pricing (42s)'."""
    if not section_times:
        return ""
    ordered = sorted(section_times.items(), key=lambda item: -float(item[1] or 0))
    parts = [f"{section_id} ({int(round(total_seconds))}s)" for section_id, total_seconds in ordered[:limit] if total_seconds]
    return ", ".join(parts)


def _run_learning_step() -> None:
    """Evaluate unevaluated adjustment_log outcomes and best-variant diffs; update experience libraries.

    Each adjustment_log row is processed exactly once thanks to the `evaluated` boolean column.
    Experience library updates run on each cron (after _cron_check_and_adjust); rows are only
    evaluated after ADJUSTMENT_EVALUATION_MIN_AGE_SEC (default 1h) so outcomes have time to accumulate.
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return
    from supabase import create_client
    import json as _json
    from collections import defaultdict
    from datetime import datetime, timezone
    client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    now_sec = time.time()

    try:
        r = (
            client.table("adjustment_log")
            .select("id,repo_full_name,layer,adjusted_at,best_variant_id,clicks_before,times_before")
            .eq("evaluated", False)
            .order("adjusted_at", desc=True)
            .limit(50)
            .execute()
        )
        rows = list(r.data or [])
    except Exception as e:
        log.warning("Learning: could not fetch adjustment_log: %s", e)
        rows = []

    for row in rows:
        row_id = row.get("id")
        try:
            adjusted_at = row.get("adjusted_at")
            if not adjusted_at:
                continue
            if isinstance(adjusted_at, str):
                dt = datetime.fromisoformat(adjusted_at.replace("Z", "+00:00"))
            else:
                continue
            age_sec = now_sec - dt.timestamp()
            if age_sec < ADJUSTMENT_EVALUATION_MIN_AGE_SEC:
                continue
            repo = (row.get("repo_full_name") or "").strip()
            layer = (row.get("layer") or "").strip()
            best_before = (row.get("best_variant_id") or "").strip()
            clicks_before_raw = row.get("clicks_before")
            if isinstance(clicks_before_raw, str):
                clicks_before_raw = _json.loads(clicks_before_raw) if clicks_before_raw else {}
            clicks_before = _normalize_variant_clicks(clicks_before_raw) if isinstance(clicks_before_raw, dict) else {}
            times_before_raw = row.get("times_before")
            if isinstance(times_before_raw, str):
                times_before_raw = _json.loads(times_before_raw) if times_before_raw else None
            times_before_map: dict[str, float] = times_before_raw if isinstance(times_before_raw, dict) else {}
            if not repo or not layer or not best_before:
                continue

            cv = client.table("cta_by_variant").select("variant_id,cta_clicks").eq("repo_full_name", repo).eq("layer", layer).execute()
            current = {row_cv["variant_id"]: int(row_cv.get("cta_clicks") or 0) for row_cv in (cv.data or [])}
            current = _normalize_variant_clicks(current)
            time_after_map: dict[str, float] = {}
            try:
                tv = client.table("time_by_variant").select("variant_id,total_seconds").eq("repo_full_name", repo).eq("layer", layer).execute()
                time_after_map = {r["variant_id"]: float(r.get("total_seconds") or 0) for r in (tv.data or [])}
            except Exception:
                pass
            section_after_map = _get_time_by_section_map(client, repo, layer)
            total_before = sum(clicks_before.values())
            total_after = sum(current.values())
            best_before_clicks = clicks_before.get(best_before, 0)
            sorted_after = sorted(current.items(), key=lambda x: -x[1])
            best_after_id = sorted_after[0][0] if sorted_after else None
            best_after_clicks = sorted_after[0][1] if sorted_after else 0

            if total_before > 0 and (best_after_id != best_before or total_after < total_before):
                lesson = "Aligning underperforming variants to the previous best's CTA structure led to degradation (best changed or total clicks dropped). Avoid over-fitting to a single winner."
                best_after_sections = _top_section_summary(section_after_map.get(best_after_id or "", {}))
                if best_after_sections:
                    lesson += f" Use section-level engagement, not just totals: after adjustment the highest-attention sections were {best_after_sections}."
                _append_experience_file(EXPERIENCE_LIBRARY_DATA_ANALYST_PATH_RESOLVED, lesson)
                _insert_experience_entry_supabase("data_analyst", lesson)
            elif total_after > total_before and best_after_clicks >= best_before_clicks:
                lesson = "CTA structure alignment to the best-performing variant increased total clicks. Prefer matching CTA placement/count/prominence of the winner when data shows a clear gap."
                winner_sections = _top_section_summary(section_after_map.get(best_before, {}))
                if winner_sections:
                    lesson += f" Use section-level time aggregates for adjustments: the winner's highest-engagement sections were {winner_sections}."
                _append_experience_file(EXPERIENCE_LIBRARY_CTA_PATH_RESOLVED, lesson)
                _insert_experience_entry_supabase("cta", lesson)

            if row_id:
                client.table("adjustment_log").update({"evaluated": True}).eq("id", row_id).execute()
                log.info("Learning: marked adjustment_log row %s as evaluated", row_id)
        except Exception as e:
            log.warning("Learning: evaluation of adjustment_log row %s failed: %s", row_id, e)

    try:
        snap = client.table("variant_snapshots").select("repo_full_name,layer,variant_id,sections,ctas,tailwind_colors,font_imports,responsive,animated,line_count,snapshot_at").order("snapshot_at", desc=True).limit(500).execute()
        snap_rows = list(snap.data or [])
    except Exception as e:
        log.warning("Learning: could not fetch variant_snapshots: %s", e)
        snap_rows = []

    by_repo_layer: dict[tuple[str, str], dict[str, dict]] = defaultdict(dict)
    for sr in snap_rows:
        repo = (sr.get("repo_full_name") or "").strip()
        layer = (sr.get("layer") or "").strip()
        vid = (sr.get("variant_id") or "").strip()
        if not repo or not layer or not vid:
            continue
        key = (repo, layer)
        if vid not in by_repo_layer[key]:
            by_repo_layer[key][vid] = sr

    for (repo, layer), variants in by_repo_layer.items():
        if len(variants) < 2:
            continue
        cv = client.table("cta_by_variant").select("variant_id,cta_clicks").eq("repo_full_name", repo).eq("layer", layer).execute()
        clicks = {row_cv["variant_id"]: int(row_cv.get("cta_clicks") or 0) for row_cv in (cv.data or [])}
        if not clicks:
            continue
        time_map: dict[str, float] = {}
        try:
            tv = client.table("time_by_variant").select("variant_id,total_seconds").eq("repo_full_name", repo).eq("layer", layer).execute()
            time_map = {r["variant_id"]: float(r.get("total_seconds") or 0) for r in (tv.data or [])}
        except Exception:
            pass
        sorted_ids = sorted(clicks.keys(), key=lambda vid: (-(clicks.get(vid) or 0), -(time_map.get(vid) or 0)))
        best_id = sorted_ids[0] if sorted_ids else None
        best_snap = variants.get(best_id)
        if not best_snap:
            continue
        diff_parts = []
        if best_snap.get("sections"):
            diff_parts.append(f"sections {best_snap['sections']}")
        if best_snap.get("ctas"):
            diff_parts.append(f"CTAs {(best_snap['ctas'] or [])[:5]}")
        if best_snap.get("responsive"):
            diff_parts.append("responsive")
        if best_snap.get("animated"):
            diff_parts.append("animated")
        if diff_parts:
            dedup_key = (repo, layer, best_id)
            if dedup_key in _GENERATION_LESSONS_WRITTEN:
                continue
            lesson = f"When {best_id} outperformed (repo {repo}), it had: " + "; ".join(str(p) for p in diff_parts) + ". Prefer these patterns in future generations."
            _insert_experience_entry_supabase("generation", lesson)
            _GENERATION_LESSONS_WRITTEN.add(dedup_key)
            log.info("Learning: inserted generation lesson for %s %s", repo, layer)


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
    layer: str = "",
    time_by_variant: dict[str, float] | None = None,
) -> tuple[bool, str]:
    """LLM judge: given variant click data and CTA context, decide whether to run the adjust pipeline.
    Returns (run_adjust: bool, judge_response_preview: str)."""
    normalized = _normalize_variant_clicks(variant_clicks)
    times = time_by_variant or {}
    sorted_variants = sorted(
        normalized.items(),
        key=lambda x: (-x[1], -(times.get(x[0]) or 0)),
    )
    if len(sorted_variants) < 2:
        return False, "fewer than 2 variants"
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
    def _line(vid: str, clicks: int) -> str:
        t = times.get(vid)
        if t is not None and t > 0:
            return f"  {vid}: {clicks} clicks, {int(round(t))}s total time"
        return f"  {vid}: {clicks} clicks"
    variant_clicks_str = "\n".join(_line(k, normalized.get(k, 0)) for k in sorted(normalized.keys()))
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
        f"Variant click counts (and time on page when available):\n{variant_clicks_str}\n\n"
        f"Best variant: {best_id} ({best_clicks} CTA clicks"
        + (f", {int(round(times.get(best_id) or 0))}s total time" if times.get(best_id) else "")
        + f"). CTA structure: {best_cta_desc or 'unknown'}\n\n"
        f"Second variant: {second_id} ({second_clicks} CTA clicks"
        + (f", {int(round(times.get(second_id) or 0))}s total time" if times.get(second_id) else "")
        + f"). CTA structure: {second_cta_desc or 'unknown'}\n\n"
        "Should we run the CTA alignment pipeline? Follow the required output format."
    )
    if not ANTHROPIC_API_KEY:
        run = best_clicks - second_clicks >= CTA_THRESHOLD
        log.info("Judge: no API key, threshold fallback -> %s (gap=%s)", "RUN_ADJUST" if run else "SKIP", best_clicks - second_clicks)
        return run, "threshold_fallback"
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
        preview = (text.strip()[:200] + "…") if len(text.strip()) > 200 else text.strip()
        if "RUN_ADJUST" in raw:
            log.info("Judge: RUN_ADJUST for %s layer %s. Response preview: %s", repo_full_name, layer, preview)
            return True, preview
        if "SKIP" in raw:
            log.info("Judge: SKIP for %s layer %s. Response preview: %s", repo_full_name, layer, preview)
            return False, preview
        run = best_clicks - second_clicks >= CTA_THRESHOLD
        log.info("Judge: ambiguous, threshold fallback -> %s. Response preview: %s", "RUN_ADJUST" if run else "SKIP", preview)
        return run, preview
    except Exception as e:
        log.warning("Judge failed, using threshold fallback: %s", e)
        run = best_clicks - second_clicks >= CTA_THRESHOLD
        return run, f"judge_error: {e}"


def run_adjust_pipeline(repo_full_name: str, layer: str, variant_clicks: dict[str, int], force_run: bool = False, time_by_variant: dict[str, float] | None = None) -> int:
    """Run CTA alignment: fetch best variant, align others, push to GitHub. Returns number of variant files pushed (0 if judge said SKIP or error)."""
    normalized = _normalize_variant_clicks(variant_clicks)
    times = time_by_variant or {}
    # Sort by clicks descending, then by total_seconds descending (tiebreaker).
    sorted_variants = sorted(
        normalized.items(),
        key=lambda x: (-x[1], -(times.get(x[0]) or 0)),
    )
    if len(sorted_variants) < 2:
        log.info("run_adjust_pipeline: %s layer %s skipped (fewer than 2 variants)", repo_full_name, layer)
        return 0
    best_id, best_clicks = sorted_variants[0]
    second_id, second_clicks = sorted_variants[1]
    if not force_run:
        run, preview = _should_run_adjust_llm_judge(repo_full_name, variant_clicks, _get_data_analyst_experience_library(), layer, time_by_variant=times)
        if not run:
            log.info("run_adjust_pipeline: %s layer %s skipped by judge (SKIP)", repo_full_name, layer)
            return 0
        log.info("run_adjust_pipeline: %s layer %s judge said RUN_ADJUST, fetching files", repo_full_name, layer)
    try:
        files = _fetch_variant_files(repo_full_name)
    except Exception as e:
        log.warning("Adjust pipeline: GitHub fetch failed for %s: %s", repo_full_name, e)
        return 0
    log.info("run_adjust_pipeline: %s fetched %s variant files: %s", repo_full_name, len(files), list(files.keys()))
    if best_id not in files:
        log.warning("Best variant %s not in fetched files", best_id)
        return 0
    best_tsx = files[best_id]
    cta_description = _describe_cta_structure(best_tsx)
    section_time_by_variant = _get_time_by_section(repo_full_name, layer)
    best_cta_count = len(_find_cta_candidates(best_tsx, _get_section_ranges(best_tsx)))
    underperforming = [vid for vid, _ in sorted_variants[1:] if vid in files]
    if not underperforming:
        log.warning("run_adjust_pipeline: %s layer %s no underperforming variants in fetched files", repo_full_name, layer)
        return 0
    log.info("run_adjust_pipeline: %s layer %s best=%s underperforming=%s", repo_full_name, layer, best_id, underperforming)
    # Build stats line for commit message: CTA clicks and time on page (so we show both metrics).
    stats_parts = []
    clicks_str = ", ".join(f"{vid}={normalized.get(vid, 0)}" for vid in sorted(normalized.keys()))
    stats_parts.append(f"CTA clicks: {clicks_str}")
    if times:
        time_str = ", ".join(
            f"{vid}={int(round(times[vid]))}s"
            for vid in sorted(times.keys())
            if times.get(vid)
        )
        if time_str:
            stats_parts.append(f"time on page: {time_str}")
    stats_line = "; ".join(stats_parts)
    commit_msg = f"CTA align (best: {best_id}) — {stats_line}"
    pushed = 0
    experience_lib = _get_cta_experience_library()
    best_clicks_val = normalized.get(best_id, 0)
    best_time_val = times.get(best_id)
    # Run Claude CTA-align sequentially (max_workers=1) to avoid rate-limit retries; push each variant as it completes.
    log.info("Running CTA align for %s sequentially (%s variants)", repo_full_name, len(underperforming))
    with ThreadPoolExecutor(max_workers=1) as executor:
        future_to_vid = {
            executor.submit(
                _call_claude_align_cta,
                FRONTEND_DESIGN_SKILL,
                cta_description,
                files[vid],
                best_id,
                experience_library=experience_lib,
                underperforming_variant_id=vid,
                best_cta_count=best_cta_count,
                best_clicks=best_clicks_val,
                best_time_sec=best_time_val,
                underperforming_clicks=normalized.get(vid, 0),
                underperforming_time_sec=times.get(vid),
                best_section_times=section_time_by_variant.get(best_id, {}),
                underperforming_section_times=section_time_by_variant.get(vid, {}),
            ): vid
            for vid in underperforming
        }
        for future in as_completed(future_to_vid):
            vid = future_to_vid[future]
            try:
                new_tsx = future.result()
                log.info("Claude align completed for %s (%s)", vid, repo_full_name)
                if new_tsx:
                    is_runnable, validation_reason = _validate_variant_tsx_runnable(new_tsx)
                    if not is_runnable:
                        log.warning("Skipping push for %s: generated TSX is not runnable (%s)", vid, validation_reason)
                        _record_snapshot_supabase(repo_full_name, layer, vid, files[vid], "agent_adjust")
                        continue
                    log.info("Pushing %s for %s (branch: default)", vid, repo_full_name)
                    _push_variant_file(repo_full_name, vid, new_tsx, commit_msg)
                    _record_snapshot_supabase(repo_full_name, layer, vid, new_tsx, "agent_adjust")
                    pushed += 1
                    log.info("Pushed updated %s for %s layer %s", vid, repo_full_name, layer)
                else:
                    log.warning("Skipping push for %s: Claude returned no content", vid)
                    _record_snapshot_supabase(repo_full_name, layer, vid, files[vid], "agent_adjust")
            except Exception as e:
                if "timeout" in str(e).lower() or "timed out" in str(e).lower():
                    log.warning(
                        "Claude CTA-align timed out for %s (timeout=%ss). Increase CLAUDE_CTA_ALIGN_TIMEOUT_SECONDS if needed.",
                        vid, CLAUDE_CTA_ALIGN_TIMEOUT_SECONDS,
                    )
                log.exception("Failed to update %s: %s", vid, e)
                _record_snapshot_supabase(repo_full_name, layer, vid, files[vid], "agent_adjust")
    _record_snapshot_supabase(repo_full_name, layer, best_id, files[best_id], "agent_adjust")
    if pushed > 0:
        _write_adjustment_log(repo_full_name, layer, best_id, normalized, times_before=times if times else None)
    elif underperforming:
        log.warning(
            "Repo %s layer %s was NOT updated: no files pushed (check GITHUB_TOKEN has 'repo' scope for write, or GitHub App is installed with write access).",
            repo_full_name, layer,
        )
    return pushed


def _get_cta_by_variant() -> list[dict]:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        log.warning("Supabase not configured; cron skip")
        return []
    from supabase import create_client
    client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    r = client.table("cta_by_variant").select("repo_full_name,layer,variant_id,cta_clicks").execute()
    return list(r.data or [])


def _get_time_by_variant() -> list[dict]:
    """Fetch time_by_variant view (all sources). Returns list of {repo_full_name, layer, variant_id, total_seconds}."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return []
    try:
        from supabase import create_client
        client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        r = client.table("time_by_variant").select("repo_full_name,layer,variant_id,total_seconds").execute()
        return list(r.data or [])
    except Exception as e:
        log.debug("time_by_variant fetch failed (table may not exist yet): %s", e)
        return []


def _get_time_by_section(repo_full_name: str, layer: str) -> dict[str, dict[str, float]]:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return {}
    try:
        from supabase import create_client

        client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        return _get_time_by_section_map(client, repo_full_name, layer)
    except Exception as e:
        log.debug("time_by_section fetch failed for %s layer %s: %s", repo_full_name, layer, e)
        return {}


def _cron_check_and_adjust():
    rows = _get_cta_by_variant()
    if not rows:
        return
    from collections import defaultdict
    time_rows = _get_time_by_variant()
    by_repo_layer_time: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    for r in time_rows:
        repo = (r.get("repo_full_name") or "").strip()
        layer = (r.get("layer") or "").strip()
        vid = (r.get("variant_id") or "").strip()
        if repo and layer and vid:
            by_repo_layer_time[(repo, layer)][vid] = float(r.get("total_seconds") or 0)
    by_repo_layer: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        repo = (r.get("repo_full_name") or "").strip()
        layer = (r.get("layer") or "").strip()
        if repo and layer:
            by_repo_layer[(repo, layer)].append(r)
    for (repo, layer), group in by_repo_layer.items():
        if REPO_ALLOW_LIST and repo not in REPO_ALLOW_LIST:
            log.info("Skipping repo %s (layer %s): not in REPO_ALLOW_LIST", repo, layer)
            continue
        raw_clicks = {r["variant_id"]: int(r.get("cta_clicks") or 0) for r in group}
        variant_clicks = _normalize_variant_clicks(raw_clicks)
        state_key = (repo, layer)
        state = _ADJUST_RUNTIME_STATE.setdefault(state_key, {"last_signature": None, "commit_times": []})
        sig = _clicks_signature(variant_clicks)
        if state.get("last_signature") == sig:
            # No new data signal; avoid repeated commits on identical click snapshot.
            log.debug("Skipping %s layer %s: same click signature (no new data)", repo, layer)
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
            force_run = bool(os.environ.get("FORCE_RUN_ADJUST", "").strip().lower() in ("1", "true", "yes"))
            time_by_variant = by_repo_layer_time.get((repo, layer), {})
            pushed = run_adjust_pipeline(repo, layer, variant_clicks, force_run=force_run, time_by_variant=time_by_variant)
            # Only record this snapshot as processed when we actually pushed; otherwise next cron can retry (e.g. judge said SKIP).
            if pushed > 0:
                state["last_signature"] = sig
                state["commit_times"] = [*state.get("commit_times", []), now]
                log.info("Adjust pipeline pushed %s file(s) for %s layer %s", pushed, repo, layer)
        except Exception as e:
            log.exception("Adjust pipeline failed for %s layer %s: %s", repo, layer, e)
    try:
        _run_learning_step()
    except Exception as e:
        log.warning("Learning step failed: %s", e)


@app.post("/api/adjust-variants")
def api_adjust_variants(body: AdjustVariantsBody):
    rows = _get_cta_by_variant()
    variant_clicks = {
        r["variant_id"]: int(r.get("cta_clicks") or 0)
        for r in rows
        if (r.get("repo_full_name") or "").strip() == body.repo_full_name and (r.get("layer") or "").strip() == body.layer
    }
    variant_clicks = _normalize_variant_clicks(variant_clicks)
    time_rows = _get_time_by_variant()
    time_by_variant = {
        r["variant_id"]: float(r.get("total_seconds") or 0)
        for r in time_rows
        if (r.get("repo_full_name") or "").strip() == body.repo_full_name and (r.get("layer") or "").strip() == body.layer
    }
    try:
        pushed = run_adjust_pipeline(body.repo_full_name, body.layer, variant_clicks, force_run=body.force, time_by_variant=time_by_variant)
        return {"ok": True, "repo_full_name": body.repo_full_name, "layer": body.layer, "pushed": pushed}
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
