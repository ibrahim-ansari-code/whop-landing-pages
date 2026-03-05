"""
Landright generate API: refinement + generation. Design guidance from frontend-design-skill.md only.
Uses Anthropic Messages API (ANTHROPIC_API_KEY required for generation).
Beacon and analytics read from backend .env (SUPABASE_*, BEACON_BASE_URL).
"""
import base64
import ipaddress
import json
import logging
import os
import re
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from export_bundle import build_vercel_bundle

APP_DIR = Path(__file__).resolve().parent
# Load backend/.env so ANTHROPIC_API_KEY is available; override=True so .env wins over shell env
load_dotenv(APP_DIR / ".env", override=True)

# --- Config (env overrides; no hardcoded prompt text) -------------------------
ANTHROPIC_API_URL = os.environ.get("ANTHROPIC_API_URL", "https://api.anthropic.com/v1/messages")
ANTHROPIC_DEFAULT_MODEL = "claude-sonnet-4-6"
VALID_CTA = {"button", "call", "trial", "contact_form", "contact_mailto"}
LIMITS = {
    "business_info_min_length": int(os.environ.get("LIMIT_BUSINESS_INFO_MIN", "10")),
    "business_info_max_length": int(os.environ.get("LIMIT_BUSINESS_INFO_MAX", "2000")),
    "skills_max_length": int(os.environ.get("LIMIT_SKILLS_MAX", "500")),
    "goals_max_length": int(os.environ.get("LIMIT_GOALS_MAX", "500")),
    "change_request_max_length": int(os.environ.get("LIMIT_CHANGE_REQUEST_MAX", "1000")),
    "chosen_html_max_length": int(os.environ.get("LIMIT_CHOSEN_HTML_MAX", "500000")),
}
VARIANT_COUNT = int(os.environ.get("VARIANT_COUNT", "4"))
# Per-variant inspiration modes for initial generation (when inspiration present): 1–4
INSPIRATION_VARIANT_MODES_DEFAULT = [
    "same_color_similar_design",
    "same_color_diff_design",
    "diff_color_similar_design",
    "natural",
]
VALID_INSPIRATION_MODES = frozenset(INSPIRATION_VARIANT_MODES_DEFAULT)
EXCERPT_MAX_LEN = int(os.environ.get("EXCERPT_MAX_LEN", "3200"))
EXPERIENCE_EXCERPT_MAX = int(os.environ.get("EXPERIENCE_EXCERPT_MAX", "4000"))
EXPERIENCE_ITEMS_MAX = int(os.environ.get("EXPERIENCE_ITEMS_MAX", "15"))
# Max experience items to inject into prompts; older items drop off (decay).
EXPERIENCE_DECAY_MAX_ITEMS = int(os.environ.get("EXPERIENCE_DECAY_MAX_ITEMS", "20"))
HTTP_TIMEOUT = float(os.environ.get("ANTHROPIC_HTTP_TIMEOUT", "120"))
# Delay (seconds) between starting each variant call and after refinement to avoid rate limits.
PACE_DELAY_SEC = max(0.0, float(os.environ.get("ANTHROPIC_PACE_DELAY_SEC", "3")))
MAX_OUTPUT_TOKENS = int(os.environ.get("ANTHROPIC_MAX_TOKENS", "1024"))
SINGLE_VARIANT_MAX_TOKENS = int(os.environ.get("ANTHROPIC_SINGLE_VARIANT_MAX_TOKENS", "20480"))  # variant TSX can be long
DEFAULT_TEMPERATURE = float(os.environ.get("ANTHROPIC_TEMPERATURE", "0.3"))
# Training-Free GRPO: reward = alpha * user_choice + (1-alpha) * llm_score; default user-only
REWARD_USER_WEIGHT = max(0.0, min(1.0, float(os.environ.get("REWARD_USER_WEIGHT", "1.0"))))
USE_LLM_REWARD = os.environ.get("USE_LLM_REWARD", "false").strip().lower() in ("true", "1", "yes")

# Beacon, analytics (from backend .env)
SUPABASE_URL = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
BACKEND_PUBLIC_URL = (os.environ.get("BACKEND_PUBLIC_URL") or "http://localhost:8000").strip().rstrip("/")
BEACON_BASE_URL = (os.environ.get("BEACON_BASE_URL") or BACKEND_PUBLIC_URL).rstrip("/")
# Allowed targetComponent values for partial refinement (Hero, CTA, Features only)
TARGET_COMPONENT_ALLOWED = {"Hero", "CTA", "Features"}

# Allowed Google Fonts for variants (next/font/google; underscore form). Use only these so we never reference missing fonts.
FONT_WHITELIST_DISPLAY = [
    "Bebas_Neue", "Playfair_Display", "Oswald", "Anton", "Archivo_Black", "Barlow_Condensed",
    "DM_Serif_Display", "Righteous", "Teko", "Ultra", "Abril_Fatface", "Alfa_Slab_One",
]
FONT_WHITELIST_BODY = [
    "Manrope", "Source_Sans_3", "Nunito", "DM_Sans", "Outfit", "Sora", "Plus_Jakarta_Sans",
    "Lexend", "Figtree", "Work_Sans", "Karla", "Lora", "Open_Sans", "Raleway", "Poppins",
]
FONT_WHITELIST_ALL = sorted(set(FONT_WHITELIST_DISPLAY + FONT_WHITELIST_BODY))
FONT_WHITELIST_PROMPT = "Use only these fonts from next/font/google (import name with underscore): " + ", ".join(FONT_WHITELIST_ALL) + ". Never use Inter, Roboto, Arial, or Space Grotesk."

# --- Skill file: load from project only (backend/frontend-design-skill.md) ---
def _load_skill_content() -> str:
    path = APP_DIR / "frontend-design-skill.md"
    if not path.exists():
        return ""
    raw = path.read_text(encoding="utf-8").strip()
    if raw.startswith("vi---"):
        raw = "---" + raw[5:]
    return raw


FRONTEND_DESIGN_SKILL = _load_skill_content()

# --- Practice config (Training-Free GRPO): no hardcoded prompt text; from paper/repo + config ---
def _load_practice_config() -> dict:
    path_str = os.environ.get("PRACTICE_CONFIG_PATH", "").strip()
    path = Path(path_str).resolve() if path_str else APP_DIR / "practice_config.json"
    out: dict = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                out = {k: (v if isinstance(v, str) else "") for k, v in data.items()}
        except (json.JSONDecodeError, TypeError):
            pass
    for key in ("agent_objective", "learning_objective", "similar_variant_instruction", "round_note_template",
                "judge_system_preamble", "judge_tasks", "judge_output_format", "extract_system_preamble",
                "extract_bullets", "group_update_system_preamble",
                "summary_system_preamble", "summary_user_template",
                "group_advantage_system_preamble", "group_advantage_tasks", "group_advantage_output_format",
                "diversity_system_preamble", "diversity_user_template", "reward_scoring_preamble"):
        env_val = os.environ.get("GRPO_" + key.upper())
        if isinstance(env_val, str) and env_val.strip():
            out[key] = env_val.strip()
    return out


def _practice_config() -> dict:
    if not hasattr(_practice_config, "_cache"):
        _practice_config._cache = _load_practice_config()
    return _practice_config._cache


def _get_agent_objective() -> str:
    return _practice_config().get("agent_objective") or os.environ.get("GRPO_AGENT_OBJECTIVE", "").strip() or "Generate landing page variants that match the user's business and design direction."


def _get_learning_objective() -> str:
    return _practice_config().get("learning_objective") or os.environ.get("GRPO_LEARNING_OBJECTIVE", "").strip() or "Preserve good design aspects chosen by the user; steer new variants toward this direction."

# --- Prompts: from JSON file (no hardcoded list) -----------------------------
def _load_prompts() -> list[dict]:
    path_str = os.environ.get("PROMPTS_PATH", "").strip()
    path = Path(path_str).resolve() if path_str else APP_DIR / "prompts.json"
    if not path.exists():
        return [{"id": "default", "label": "Default", "system_prompt": "Generate a landing page. Follow the design skill above."}]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list) and data:
            return [{"id": str(p.get("id", "default")), "label": str(p.get("label", "Default")), "system_prompt": str(p.get("system_prompt", ""))} for p in data]
    except (json.JSONDecodeError, TypeError):
        pass
    return [{"id": "default", "label": "Default", "system_prompt": "Generate a landing page. Follow the design skill above."}]


PROMPTS = _load_prompts()


# --- Default (pre-built) experience library (paper: token prior from minimal ground-truth data) ---
def _get_default_experience_library() -> list[str]:
    """Load standard experience library from file; used when client sends empty experienceLibrary.
    Supports JSON (array or {experienceLibrary: [...]}) and .md (bullet/dash list parsed by _experience_brief_to_list).
    """
    path_str = os.environ.get("EXPERIENCE_LIBRARY_PATH", "").strip()
    path = Path(path_str).resolve() if path_str else APP_DIR / "experience_library_default.json"
    if not path.exists():
        # Optional: try same base name with .md (e.g. experience_library_default.md)
        if path_str or (APP_DIR / "experience_library_default.md").exists():
            md_path = (path.parent / (path.stem + ".md")) if path_str else APP_DIR / "experience_library_default.md"
            if md_path.exists():
                try:
                    text = md_path.read_text(encoding="utf-8")
                    return _experience_brief_to_list(text)
                except OSError:
                    pass
        return []
    try:
        suffix = path.suffix.lower()
        if suffix == ".md":
            text = path.read_text(encoding="utf-8")
            return _experience_brief_to_list(text)
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


def _get_prompt_system_text(prompt_id: str) -> str:
    for p in PROMPTS:
        if p["id"] == prompt_id and (p.get("system_prompt") or "").strip():
            return p["system_prompt"].strip()
    return PROMPTS[0]["system_prompt"].strip() if PROMPTS else "Generate a landing page. Follow the design skill above."

# --- Request/Response models -------------------------------------------------
class WebsiteInformation(BaseModel):
    name: str = ""
    tagline: str = ""
    whatTheyDo: str = ""
    valueProp: str | None = None
    logoDataUrl: str | None = None


class CtaEntry(BaseModel):
    type: str = "button"
    label: str = ""
    url: str = ""
    embedCalendly: bool = False
    contactEmail: str | None = None  # for contact_form and contact_mailto


class DesignSpec(BaseModel):
    websiteInformation: WebsiteInformation
    skillsOrNiches: list[str] = []
    goals: list[str] = []
    ctaType: str = "button"
    ctaEntries: list[CtaEntry] | None = None
    priorities: list[str] | None = None
    features: list[str] | None = None
    style: str | None = None
    colorScheme: dict | None = None
    theme: str | None = None
    fonts: dict | None = None
    referenceSites: list[str] | None = None
    socials: dict | None = None  # e.g. {"twitter": "...", "linkedin": "..."}
    privacyUrl: str | None = None
    termsUrl: str | None = None
    securityUrl: str | None = None
    logoDataUrl: str | None = None


class GenerateBody(BaseModel):
    spec: DesignSpec
    promptId: str
    chosenVariantHtml: str | None = None
    changeRequest: str | None = None
    selectedVariantIndex: int | None = None  # 0-based, 0-3
    experienceLibrary: list[str] | None = None  # E from previous rounds; used in generation with decay (JSON)
    experienceLibraryMd: str | None = None  # same as experienceLibrary but markdown/bullet text; parsed into list
    variantTsxList: list[str] | None = None  # all 4 variant TSX for "generate 4 similar"; used by LLM judge
    similarityRound: int | None = None  # 0-based; how many times "generate 4 similar" in this chain; drives convergence
    targetComponent: str | None = None  # optional: "Hero" | "CTA" | "Features" for partial refinement only
    competitorDna: dict | None = None  # ExtractedDesignSpec from /extract-design-spec (JSON)
    competitorDnaMd: str | None = None  # design inspiration in markdown; used for synthesis alongside or instead of competitorDna
    inspirationVariantModes: list[str] | None = None  # optional [1..4] modes for initial gen when inspiration present; else default
    useCritic: bool = True  # if False, skip critic audit (faster; no per-variant reasoning/conversionDrivers)


class BeaconBody(BaseModel):
    event: str  # button_click only (CTA)
    variant_id: str | None = None
    repo_full_name: str | None = None
    layer: str | None = None
    cta_label: str | None = None
    cta_id: str | None = None


class BuildExportBundleBody(BaseModel):
    variant_tsx_list: list[str]
    repo_full_name: str
    layer: str


class CreateRepoAndPushBody(BaseModel):
    github_access_token: str
    repo_name: str  # e.g. "my-landing" (repo created under authenticated user)
    variant_tsx_list: list[str]
    layer: str = "1"  # used for beacon and analytics


class GitHubOAuthExchangeBody(BaseModel):
    code: str
    redirect_uri: str | None = None  # must match the redirect used in the authorize request


# --- DesignSpecPipeline: God-Object Schema -----------------------------------
class CompetitorDna(BaseModel):
    palette: list[str] = []
    layout_pattern: str = "centered"
    hook: str = ""


class SectionHierarchy(BaseModel):
    section: str = ""
    intent: str = ""
    components: list[str] = []


class Diction(BaseModel):
    tone: str = ""
    triggers: list[str] = []


class ExtractedDesignSpec(BaseModel):
    dna: CompetitorDna = CompetitorDna()
    hierarchy: list[SectionHierarchy] = []
    diction: Diction = Diction()


class ExtractDesignSpecBody(BaseModel):
    screenshot: str | None = None  # base64 or data URL (required for inspiration)
    targetUrls: list[str] = []  # optional, unused when screenshot provided
    targetUrl: str | None = None  # optional, backward compat


# --- URL validation (SSRF protection) ----------------------------------------
_PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _validate_target_url(url: str) -> str | None:
    """Validate targetUrl for extract-design-spec. Returns error message or None."""
    url = url.strip()
    if not re.match(r"^https://", url):
        return "URL must use HTTPS (https://)"
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return "Malformed URL"
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return "URL has no hostname"
    if hostname in ("localhost", "0.0.0.0", "[::]"):
        return "localhost is not allowed"
    if hostname.endswith(".local") or hostname.endswith(".internal"):
        return "Internal hostnames are not allowed"
    try:
        ip = ipaddress.ip_address(hostname)
        if any(ip in net for net in _PRIVATE_NETS) or ip.is_reserved:
            return "Internal/private IP addresses are not allowed"
    except ValueError:
        pass  # hostname, not an IP literal
    return None


# --- Validation --------------------------------------------------------------
def validate_spec(spec: DesignSpec) -> str | None:
    wi = spec.websiteInformation
    if not wi or not wi.whatTheyDo or len(wi.whatTheyDo.strip()) < LIMITS["business_info_min_length"]:
        return "spec.websiteInformation.whatTheyDo too short"
    if len(wi.whatTheyDo) > LIMITS["business_info_max_length"]:
        return "spec.websiteInformation.whatTheyDo too long"
    skills_joined = "".join(spec.skillsOrNiches) if spec.skillsOrNiches else ""
    if len(skills_joined) > LIMITS["skills_max_length"]:
        return "spec.skillsOrNiches total length too long"
    goals_joined = "".join(spec.goals) if spec.goals else ""
    if len(goals_joined) > LIMITS["goals_max_length"]:
        return "spec.goals total length too long"
    if spec.ctaType not in VALID_CTA:
        return "spec.ctaType must be button, call, trial, contact_form, or contact_mailto"
    entries = spec.ctaEntries or []
    if entries:
        url_like = re.compile(r"^https?://[^\s]+$")
        email_like = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
        for i, e in enumerate(entries):
            if getattr(e, "type", None) not in VALID_CTA:
                return f"spec.ctaEntries[{i}].type must be button, call, trial, contact_form, or contact_mailto"
            if getattr(e, "type", None) in ("contact_form", "contact_mailto"):
                email = (getattr(e, "contactEmail", None) or "").strip()
                if not email:
                    return f"spec.ctaEntries[{i}].contactEmail is required"
                if not email_like.match(email):
                    return f"spec.ctaEntries[{i}].contactEmail must be a valid email"
            else:
                url = (getattr(e, "url", None) or "").strip()
                if not url:
                    return f"spec.ctaEntries[{i}].url is required"
                if not url_like.match(url):
                    return f"spec.ctaEntries[{i}].url must be a valid http(s) URL"
    else:
        pass
    if spec.referenceSites is not None and not isinstance(spec.referenceSites, list):
        return "spec.referenceSites must be an array"
    url_like = re.compile(r"^https?://[^\s]+$")
    if spec.privacyUrl and not url_like.match(spec.privacyUrl.strip()):
        return "spec.privacyUrl must be a valid http(s) URL"
    if spec.termsUrl and not url_like.match(spec.termsUrl.strip()):
        return "spec.termsUrl must be a valid http(s) URL"
    if spec.securityUrl and not url_like.match(spec.securityUrl.strip()):
        return "spec.securityUrl must be a valid http(s) URL"
    if spec.socials and isinstance(spec.socials, dict):
        for k, v in spec.socials.items():
            if v and isinstance(v, str) and v.strip() and not url_like.match(v.strip()):
                return f"spec.socials.{k} must be a valid http(s) URL"
    return None


# --- Prompts: all design guidance from FRONTEND_DESIGN_SKILL only ------------
def get_refinement_system_prompt(diversity_instruction: str = "", target_component: str | None = None) -> str:
    diversity_block = f"\n\nDiversity/convergence (follow this): {diversity_instruction}" if diversity_instruction else ""
    component_block = ""
    if target_component and target_component in TARGET_COMPONENT_ALLOWED:
        component_block = f"\n\nFocus refinement only on the {target_component} section. Do not modify other sections (e.g. nav, other sections, footer); preserve their structure and content to save tokens and keep the rest of the page stable."
    return f"""Output ONLY the design brief (plain text). No greetings or commentary.

Use the design skill above. The brief will drive 4 landing page variants.{diversity_block}{component_block}

Brief must include: (1) Business: name, one sentence, tagline, CTA label from spec. (2) For each of the 4 variants, assign one aesthetic direction (e.g. dark cinematic, light minimal, bold editorial, refined typography) consistent with the diversity instruction. (3) Per variant: colors (hex), display + body fonts from the allowed list only ({FONT_WHITELIST_PROMPT}), layout hint, one signature visual. (4) Copy: headline, subhead, 3 feature bullets—real copy only, no Lorem. (5) Only the spec CTAs and footer links may be clickable; no links to /features, /pricing, /about or other non-existent pages."""


def _get_single_variant_system_prompt_uncached(prompt_id: str, variant_index: int, diversity_instruction: str = "", target_component: str | None = None) -> str:
    base = _get_prompt_system_text(prompt_id)
    diversity_block = f"\n\nDiversity/convergence (follow for how much to vary): {diversity_instruction}" if diversity_instruction else ""
    component_block = ""
    if target_component and target_component in TARGET_COMPONENT_ALLOWED:
        component_block = f"\n\nFocus refinement only on the {target_component} section. Do not modify other sections (e.g. nav, other sections, footer); preserve their structure and content to save tokens and keep the rest of the page stable."
    return f"""Follow the design skill above. {base}

Variant {variant_index} of {VARIANT_COUNT}. Use the aesthetic and specs for variant {variant_index} from the brief.{diversity_block}{component_block}

All CTA buttons and links must use the exact labels and URLs provided in the user message (from the spec). Do not use href=\"#\" or placeholder URLs for those CTAs. Only include as clickable links/buttons the CTAs and footer links listed in the user message—do not add navigation links to routes like /features, /pricing, /about (those pages do not exist).

Output: single JSON only: {{ "tsx": "<full TSX string>" }}. No markdown, no preamble. Full page: nav (logo+links+CTA), hero (headline+sub+CTA(s)), ≥2 sections, footer. next/font/google + Tailwind. {FONT_WHITELIST_PROMPT} Real copy from brief; no Lorem. Code must run in any browser: use only browser-safe APIs, no Node/server-only. Must be responsive: use Tailwind sm:/md:/lg: for layout and type so it works on mobile and desktop. Valid React/JSX only.

If the user message says a logo image is provided, use an <img> element in the nav with src="__LOGO_URL__" (exactly that placeholder), alt set to the company name, and appropriate sizing classes (e.g. h-8 w-auto). Place it where the company name/logo text would normally go. You may keep the company name as text next to the image or hide it—choose what looks best for the design."""


def _get_refinement_system_blocks(diversity_instruction: str = "", target_component: str | None = None) -> list[dict]:
    return [
        {"type": "text", "text": FRONTEND_DESIGN_SKILL, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": get_refinement_system_prompt(diversity_instruction, target_component)},
    ]


def _get_single_variant_system_blocks(
    prompt_id: str,
    variant_index: int,
    diversity_instruction: str = "",
    target_component: str | None = None,
    competitor_dna: dict | None = None,
    competitor_dna_md: str | None = None,
    use_inspiration_structure_line: bool = False,
) -> list[dict]:
    blocks = [
        {"type": "text", "text": FRONTEND_DESIGN_SKILL, "cache_control": {"type": "ephemeral"}},
    ]
    inspiration_block = _build_inspiration_system_block(
        competitor_dna, include_structure_line=use_inspiration_structure_line
    )
    if inspiration_block:
        blocks.append(inspiration_block)
    md_block = _build_inspiration_md_block(competitor_dna_md)
    if md_block:
        blocks.append(md_block)
    blocks.append({"type": "text", "text": _get_single_variant_system_prompt_uncached(prompt_id, variant_index, diversity_instruction, target_component)})
    return blocks


def _build_inspiration_directive(dna: dict | None) -> dict | None:
    """Compress inspiration data into a compact, tiered JSON directive for the LLM.

    Returns a small dict with two tiers:
      - APPLY: design tokens to directly use (palette, shadows, radii, buttons, typography)
      - FOLLOW: structural patterns to emulate (layout, sections, persuasion)
    Returns None if no inspiration data.
    """
    if not dna:
        return None

    apply_tier: dict = {}  # direct design tokens
    follow_tier: dict = {}  # structural patterns

    # Tier 1 — APPLY: theme_overrides are direct design tokens
    to = dna.get("theme_overrides", {})
    if isinstance(to, dict):
        for key in ("palette", "accent", "shadow_depths", "border_radius", "gradients",
                     "animation_style", "hover_effects", "button_style", "card_style",
                     "headline_style", "body_style"):
            val = to.get(key)
            if val and val != "none":
                apply_tier[key] = val

    # Fill from design_system if theme_overrides didn't have them
    ds = dna.get("design_system", {})
    if isinstance(ds, dict):
        color = ds.get("color", {}) if isinstance(ds.get("color"), dict) else {}
        if not apply_tier.get("palette") and color.get("palette"):
            apply_tier["palette"] = color["palette"][:8]
        if not apply_tier.get("accent") and color.get("accent"):
            apply_tier["accent"] = color["accent"]
        typo = ds.get("typography", {}) if isinstance(ds.get("typography"), dict) else {}
        if not apply_tier.get("headline_style") and typo.get("headline_style"):
            apply_tier["headline_style"] = typo["headline_style"]
        if not apply_tier.get("body_style") and typo.get("body_style"):
            apply_tier["body_style"] = typo["body_style"]
        comps = ds.get("components", {}) if isinstance(ds.get("components"), dict) else {}
        if not apply_tier.get("button_style") and comps.get("buttons"):
            apply_tier["button_style"] = comps["buttons"]
        if not apply_tier.get("card_style") and comps.get("cards"):
            apply_tier["card_style"] = comps["cards"]
        if ds.get("layout"):
            follow_tier["layout"] = ds["layout"]

    # Tier 2 — FOLLOW: structural patterns
    hero = dna.get("hero", {})
    if isinstance(hero, dict) and hero.get("layout"):
        follow_tier["hero"] = hero["layout"]
        if hero.get("visual_type"):
            follow_tier["hero_visual"] = hero["visual_type"]

    sp = dna.get("social_proof", {})
    if isinstance(sp, dict) and sp.get("type"):
        follow_tier["social_proof"] = sp["type"]

    sections = dna.get("sections", [])
    if isinstance(sections, list) and sections:
        follow_tier["sections"] = [
            s.get("content_type", s.get("id", "unknown"))
            for s in sections[:10] if isinstance(s, dict)
        ]

    diction = dna.get("diction", {})
    if isinstance(diction, dict):
        if diction.get("tone"):
            follow_tier["tone"] = diction["tone"]
        if diction.get("triggers"):
            follow_tier["triggers"] = diction["triggers"][:6]

    nav = dna.get("nav", {})
    if isinstance(nav, dict) and nav.get("style"):
        follow_tier["nav_style"] = nav["style"]

    if not apply_tier and not follow_tier:
        return None

    return {"APPLY": apply_tier, "FOLLOW": follow_tier}


def _build_inspiration_system_block(dna: dict | None, include_structure_line: bool = False) -> dict | None:
    """Build a cached system prompt block containing the inspiration directive.

    By placing inspiration in a cached system block (instead of in each user message),
    Anthropic's prompt caching processes it once and shares across all 4 parallel variant calls.
    This cuts prompt tokens by ~75% for the inspiration portion.
    When include_structure_line is True, appends explicit page-order instruction from FOLLOW (initial generation only).
    """
    directive = _build_inspiration_directive(dna)
    if not directive:
        return None
    compact_json = json.dumps(directive, separators=(",", ":"))
    text = f"""Design inspiration directive (synthesize — do NOT copy branding/copy):
{compact_json}

APPLY tier = direct design tokens. Use these exact styles (palette, shadows, radii, buttons, typography, gradients).
FOLLOW tier = structural patterns. Emulate these patterns (layout, section order, social proof type, tone) but adapt for the user's business.
Create your own unique design that channels these patterns."""
    if include_structure_line:
        structure_line = _inspiration_structure_line(directive)
        if structure_line:
            text = text + "\n\n" + structure_line
    return {"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}


def _build_inspiration_md_block(md: str | None) -> dict | None:
    """Build a system prompt block for markdown design inspiration (synthesis). Used when competitorDnaMd is provided."""
    if not md or not md.strip():
        return None
    text = f"""Design inspiration (markdown — synthesize, do NOT copy branding/copy):
{md.strip()}

Use these patterns and tone; adapt for the user's business. Create your own unique design that channels this."""
    return {"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}


def _inspiration_structure_line(directive: dict) -> str:
    """Build one or two sentences stating required page structure when following inspiration. Returns '' if FOLLOW is empty."""
    follow = directive.get("FOLLOW") if isinstance(directive, dict) else None
    if not follow or not isinstance(follow, dict):
        return ""
    parts: list[str] = []
    hero = follow.get("hero")
    if hero:
        parts.append(f"hero (layout: {hero})")
    sections = follow.get("sections")
    if sections and isinstance(sections, list):
        parts.append(f"then sections in order: {', '.join(str(s) for s in sections[:10])}")
    if not parts:
        return ""
    order = ", then ".join(parts) + ", then footer."
    out = f"When following inspiration structure, build the page in this order: {order}"
    if follow.get("social_proof") or follow.get("nav_style"):
        extras = [e for e in (follow.get("social_proof"), follow.get("nav_style")) if e]
        if extras:
            out += f" Match {', '.join(extras)} from FOLLOW."
    return out


def _inspiration_mode_instruction(mode: str) -> str:
    """Return one short sentence for the user message: how this variant should use APPLY/FOLLOW. Used only in initial generation when inspiration present."""
    if mode == "same_color_similar_design":
        return "This variant: use APPLY palette and FOLLOW structure (section order, hero layout, social proof, nav)."
    if mode == "same_color_diff_design":
        return "This variant: use APPLY palette only; do not follow FOLLOW structure; choose your own layout and section order."
    if mode == "diff_color_similar_design":
        return "This variant: follow FOLLOW structure only; do not use APPLY palette; choose a different color palette."
    if mode == "natural":
        return "This variant: ignore inspiration; generate from the brief and spec only."
    return ""


def _get_logo_url(spec: DesignSpec | None) -> str | None:
    """Extract logo data URL from spec (checked at both top-level and websiteInformation)."""
    if not spec:
        return None
    url = getattr(spec, "logoDataUrl", None)
    if url:
        return url
    wi = getattr(spec, "websiteInformation", None)
    if wi:
        return getattr(wi, "logoDataUrl", None)
    return None


def _logo_instruction(spec: DesignSpec | None) -> str:
    """Return a prompt note about the logo image if one is provided."""
    if not _get_logo_url(spec):
        return ""
    return '\n\nA logo image is provided. In the nav bar, render an <img> element with src="__LOGO_URL__" (exactly that placeholder string), alt set to the company name, and sizing classes like h-8 w-auto. Place it where the text logo would go.'


def _spec_for_prompt(spec: DesignSpec) -> str:
    """Return spec as JSON with logo data removed to avoid blowing context (base64 can be 500k+ tokens)."""
    d = spec.model_dump()
    d.pop("logoDataUrl", None)
    wi = d.get("websiteInformation")
    if isinstance(wi, dict):
        wi.pop("logoDataUrl", None)
    return json.dumps(d)


def build_single_variant_user_message(
    refined_brief: str,
    variant_index: int,
    chosen_html: str | None = None,
    change_request: str | None = None,
    selected_variant_index: int | None = None,
    experience_library_decayed: list[str] | None = None,
    diversity_instruction: str = "",
    spec: DesignSpec | None = None,
    target_component: str | None = None,
    inspiration_mode_instruction: str = "",
) -> str:
    n = VARIANT_COUNT
    extra = _format_experience_for_prompt(experience_library_decayed or [])
    div_note = f"\n\nDiversity: {diversity_instruction}" if diversity_instruction else ""
    component_note = f"\n\nRefine only the {target_component} section; leave all other sections unchanged." if (target_component and target_component in TARGET_COMPONENT_ALLOWED) else ""
    cta_block = _format_cta_and_links_for_prompt(spec) if spec else ""
    cta_instruction = f"\n\nUse these exact CTAs and links in the page (no href=\"#\" or placeholders):{cta_block}" if cta_block else ""
    logo_note = _logo_instruction(spec)
    inspiration_note = f"\n\n{inspiration_mode_instruction}" if inspiration_mode_instruction else ""
    if not chosen_html and not change_request:
        return f"""Brief:\n{refined_brief}{extra}{div_note}{component_note}{cta_instruction}{logo_note}{inspiration_note}\n\nVariant {variant_index}/{n}. Use the brief's direction for this variant. Respond with JSON only: {{ "tsx": "..." }}"""
    variant_label = ""
    if selected_variant_index is not None and 0 <= selected_variant_index < n:
        variant_label = f"User chose variant {selected_variant_index + 1}/{n}. "
    excerpt = (chosen_html or "")[:EXCERPT_MAX_LEN]
    return f"""Brief:\n{refined_brief}{extra}{div_note}{component_note}{cta_instruction}{logo_note}{inspiration_note}\n\n{variant_label}Iterate: apply change request to chosen variant; keep what works. Variant {variant_index}/{n}. Full page, real copy. Keep code browser-safe and responsive (Tailwind sm:/md:/lg:).\n\nChosen TSX (excerpt):\n{excerpt}\n\nChange: {change_request}\n\nRespond with JSON only: {{ "tsx": "..." }}"""


def _strip_leading_clarification(text: str) -> str:
    t = text.strip()
    lower = t.lower()
    for start in ("before i ", "would you ", "may i ", "let me clarify", "to clarify", "one question"):
        if lower.startswith(start) or f"\n{start}" in lower:
            idx = lower.index(start) if lower.startswith(start) else lower.index("\n" + start) + 1
            after = t[idx + len(start) :].strip()
            double = after.find("\n\n")
            if double > 0:
                return after[double:].strip()
            return after
    return t


def build_refinement_user_message(
    spec: DesignSpec,
    chosen_html: str | None,
    change_request: str | None,
    selected_variant_index: int | None = None,
    experience_library_decayed: list[str] | None = None,
    diversity_instruction: str = "",
    target_component: str | None = None,
) -> str:
    spec_block = _spec_for_prompt(spec)
    cta_block = _format_cta_and_links_for_prompt(spec)
    n = VARIANT_COUNT
    extra = _format_experience_for_prompt(experience_library_decayed or [])
    div_note = f"\n\nDiversity/convergence: {diversity_instruction}" if diversity_instruction else ""
    component_note = f"\n\nFocus refinement only on the {target_component} section; leave all other sections unchanged." if (target_component and target_component in TARGET_COMPONENT_ALLOWED) else ""
    if not chosen_html or not change_request:
        base = f"Spec:\n{spec_block}\n\nProduce the design brief. For the next {n} variants assign one aesthetic direction each (use the design skill above). Include in the brief that every variant MUST use exactly these CTAs and links (exact labels and URLs; no placeholder # or generic links):{cta_block or ' (none in spec)'}{div_note}{component_note}"
        return base + extra if extra else base
    variant_label = ""
    if selected_variant_index is not None and 0 <= selected_variant_index < n:
        variant_label = f"User chose variant {selected_variant_index + 1}/{n}. "
    excerpt = chosen_html[:3200]
    return f"{variant_label}Apply user changes; output updated brief only (plain text). Keep what works; direct generator for {n} variant(s).{div_note}{component_note}\n\nChanges: {change_request}\n\nChosen TSX (excerpt):\n{excerpt}" + (extra if extra else "")


# --- Experience: LLM judge (group relative semantic advantage) + extraction (single chosen) ---
# All prompt text from practice_config.json / env; see youtu-agent SINGLE_QUERY_GROUP_ADVANTAGE
def _get_llm_judge_system() -> str:
    cfg = _practice_config()
    preamble = (cfg.get("judge_system_preamble") or "Extract useful experiences from variant rollouts.").strip()
    raw_tasks = cfg.get("judge_tasks") or "Compare variants by reward (1=selected, 0=not); extract experiences."
    tasks = raw_tasks.replace("{{VARIANT_COUNT}}", str(VARIANT_COUNT)).replace("{{EXPERIENCE_ITEMS_MAX}}", str(EXPERIENCE_ITEMS_MAX))
    out_fmt = (cfg.get("judge_output_format") or "Output <Experiences>...</Experiences> with numbered items.").strip()
    return f"""Use the design skill above. {preamble}

Agent objective:
{_get_agent_objective()}

Learning objective:
{_get_learning_objective()}

{tasks}

{out_fmt}"""


def _parse_experiences_from_response(response: str) -> list[str]:
    """Extract experience list from <Experiences>...</Experiences> block (youtu-agent pattern)."""
    match = re.search(r"<Experiences>\s*([\s\S]*?)\s*</Experiences>", response, re.IGNORECASE)
    if match:
        block = match.group(1).strip()
        items: list[str] = []
        for line in block.split("\n"):
            line = line.strip()
            if not line:
                continue
            # Remove leading "1. ", "2. ", etc.
            part = re.sub(r"^\d+[.)]\s*", "", line).strip()
            if part and len(part) > 10:
                items.append(part)
                if len(items) >= EXPERIENCE_ITEMS_MAX:
                    return items
        return items[:EXPERIENCE_ITEMS_MAX]
    return []


def _judge_variants(
    api_key: str,
    spec: DesignSpec,
    variant_tsx_list: list[str],
    selected_index: int,
) -> tuple[str, list[str]]:
    """Run LLM judge on all variants (group relative semantic advantage); return (raw response, parsed experience list)."""
    spec_block = _spec_for_prompt(spec)
    excerpts = []
    for i, tsx in enumerate(variant_tsx_list[:VARIANT_COUNT]):
        reward = 1 if i == selected_index else 0
        label = "Selected by user — reward 1" if reward else "Not selected — reward 0"
        excerpts.append(f"Variant {i + 1} ({label}):\n{(tsx or '')[:EXPERIENCE_EXCERPT_MAX]}")
    user_msg = f"""Spec (business context):\n{spec_block}\n\nVariants (user chose variant {selected_index + 1}):\n\n""" + "\n\n".join(excerpts) + "\n\nOutput your analysis and the <Experiences>...</Experiences> block as described."
    raw = call_claude(
        api_key,
        [{"type": "text", "text": FRONTEND_DESIGN_SKILL}, {"type": "text", "text": _get_llm_judge_system()}],
        user_msg,
        max_tokens_override=MAX_OUTPUT_TOKENS,
    )
    parsed = _parse_experiences_from_response(raw)
    if not parsed:
        parsed = _experience_brief_to_list(raw)
    return raw, parsed


def _get_experience_extraction_system() -> str:
    cfg = _practice_config()
    preamble = (cfg.get("extract_system_preamble") or "Extract experiences to guide future landing page generation.").strip()
    bullets = (cfg.get("extract_bullets") or "Aesthetic direction; Layout; Typography; Color and mood; Tone and copy; Visual elements.").strip()
    return f"""Use the design skill above. {preamble}

Agent objective:
{_get_agent_objective()}

Learning objective:
{_get_learning_objective()}

Analyze the given TSX and output a concise experience brief (plain text, short bullets or paragraphs) that captures: {bullets}

This brief will be used to generate 4 new variants that follow this direction but must be four distinct designs. Output plain text only, no JSON."""


def _extract_experience(api_key: str, spec: DesignSpec, chosen_tsx: str) -> tuple[str, list[str]]:
    """Extract experience from a single chosen TSX (fallback when no variant list). Returns (brief, experience_list)."""
    excerpt = chosen_tsx[:EXPERIENCE_EXCERPT_MAX]
    spec_block = _spec_for_prompt(spec)
    user_msg = f"""Spec (business context):\n{spec_block}\n\nChosen landing page TSX (excerpt):\n{excerpt}\n\nOutput the experience brief (plain text) as described in the system prompt."""
    raw = call_claude(
        api_key,
        [{"type": "text", "text": FRONTEND_DESIGN_SKILL}, {"type": "text", "text": _get_experience_extraction_system()}],
        user_msg,
        max_tokens_override=MAX_OUTPUT_TOKENS,
    )
    experience_list = _experience_brief_to_list(raw)
    return raw, experience_list


def _experience_brief_to_list(brief: str, max_items: int | None = None) -> list[str]:
    if max_items is None:
        max_items = EXPERIENCE_ITEMS_MAX
    """Turn plain-text experience brief into a list of experience items (for experienceLibrary)."""
    lines = [ln.strip() for ln in brief.strip().split("\n") if ln.strip()]
    items: list[str] = []
    for ln in lines:
        for part in re.split(r"[\•\-]\s+", ln):
            part = part.strip()
            if part and len(part) > 10:
                items.append(part)
                if len(items) >= max_items:
                    return items
    if not items and brief.strip():
        items = [brief.strip()[:500]]
    return items[:max_items]


# --- Reward model R(q, oi): user choice + optional LLM score (paper-aligned) ---
def _compute_rewards(
    api_key: str,
    spec: DesignSpec,
    variant_tsx_list: list[str],
    selected_index: int | None,
) -> list[float]:
    """Compute scalar reward per variant: alpha * user_choice + (1-alpha) * llm_score. Default user-only."""
    n = min(len(variant_tsx_list), VARIANT_COUNT)
    user_rewards = [1.0 if i == selected_index else 0.0 for i in range(n)]
    if n < VARIANT_COUNT:
        user_rewards.extend([0.0] * (VARIANT_COUNT - n))
    if not USE_LLM_REWARD or REWARD_USER_WEIGHT >= 1.0:
        return user_rewards[:VARIANT_COUNT]
    # Optional LLM scoring per variant (0-1)
    llm_scores: list[float] = []
    cfg = _practice_config()
    preamble = (cfg.get("reward_scoring_preamble") or "Score this landing page variant 0.0 to 1.0 for spec alignment and design quality. Output only a number.").strip()
    spec_block = _spec_for_prompt(spec)
    for i in range(n):
        excerpt = (variant_tsx_list[i] or "")[:EXPERIENCE_EXCERPT_MAX]
        user_msg = f"""Spec:\n{spec_block}\n\nVariant TSX (excerpt):\n{excerpt}\n\nOutput only a single number between 0 and 1."""
        try:
            raw = call_claude(
                api_key,
                [{"type": "text", "text": FRONTEND_DESIGN_SKILL}, {"type": "text", "text": preamble}],
                user_msg,
                max_tokens_override=64,
            )
            s = re.sub(r"[^\d.]", "", raw.strip())
            val = float(s) if s else 0.5
            llm_scores.append(max(0.0, min(1.0, val)))
        except Exception:
            llm_scores.append(0.5)
    if len(llm_scores) < n:
        llm_scores.extend([0.5] * (n - len(llm_scores)))
    alpha = REWARD_USER_WEIGHT
    return [alpha * u + (1.0 - alpha) * l for u, l in zip(user_rewards[:n], llm_scores[:n])][:VARIANT_COUNT]


# --- Per-rollout summarization si = M(psummary, q, oi) (paper-aligned) ---
def _summarize_rollout(
    api_key: str,
    spec: DesignSpec,
    tsx_excerpt: str,
    reward_label: str,
) -> str:
    """Summarize one variant rollout for group-advantage analysis. Returns short structured summary si."""
    cfg = _practice_config()
    preamble = (cfg.get("summary_system_preamble") or "Summarize this landing page variant for group-advantage analysis.").strip()
    tpl = (cfg.get("summary_user_template") or "Spec:\n{{spec}}\n\nVariant TSX:\n{{tsx_excerpt}}\n\nReward: {{reward_label}}\n\nOutput a short summary (2-4 sentences).").strip()
    user_msg = tpl.replace("{{spec}}", _spec_for_prompt(spec)).replace("{{tsx_excerpt}}", tsx_excerpt[:EXPERIENCE_EXCERPT_MAX]).replace("{{reward_label}}", reward_label)
    system_blocks = [
        {"type": "text", "text": FRONTEND_DESIGN_SKILL},
        {"type": "text", "text": preamble},
    ]
    raw = call_claude(api_key, system_blocks, user_msg, max_tokens_override=512)
    return raw.strip()


# --- Group advantage extraction Atext = M(pextract, q, s1..sG, E) (paper-aligned) ---
def _group_advantage_extraction(
    api_key: str,
    spec: DesignSpec,
    summarized_rollouts: list[tuple[str, float]],
    experience_library: list[str],
) -> list[str]:
    """Given summaries and rewards, extract natural-language experiences (Atext). Uses current E in prompt."""
    cfg = _practice_config()
    preamble = (cfg.get("group_advantage_system_preamble") or "Extract group-relative semantic advantage from summarized rollouts.").strip()
    raw_tasks = cfg.get("group_advantage_tasks") or "Compare rollouts and extract experiences."
    tasks = raw_tasks.replace("{{VARIANT_COUNT}}", str(VARIANT_COUNT)).replace("{{EXPERIENCE_ITEMS_MAX}}", str(EXPERIENCE_ITEMS_MAX))
    out_fmt = (cfg.get("group_advantage_output_format") or "Output <Experiences>...</Experiences>.").strip()
    system_text = f"""Use the design skill above. {preamble}

Agent objective:
{_get_agent_objective()}

Learning objective:
{_get_learning_objective()}

{tasks}

{out_fmt}"""
    spec_block = _spec_for_prompt(spec)
    attempts_block = "\n\n".join(
        f"Attempt {i + 1} (Reward {r:.1f}):\n{s}" for i, (s, r) in enumerate(summarized_rollouts[:VARIANT_COUNT])
    )
    experiences_block = "\n".join(f"[{i}]. {e}" for i, e in enumerate(experience_library[:EXPERIENCE_DECAY_MAX_ITEMS])) if experience_library else "(none yet)"
    user_msg = f"""Spec (business context):\n{spec_block}\n\nSummarized rollouts:\n{attempts_block}\n\nCurrent experiential knowledge E:\n{experiences_block}\n\nOutput your analysis and the <Experiences>...</Experiences> block as described."""
    raw = call_claude(
        api_key,
        [{"type": "text", "text": FRONTEND_DESIGN_SKILL}, {"type": "text", "text": system_text}],
        user_msg,
        max_tokens_override=MAX_OUTPUT_TOKENS,
    )
    parsed = _parse_experiences_from_response(raw)
    if not parsed:
        parsed = _experience_brief_to_list(raw)
    return parsed


# --- Group experience update: merge new with existing (youtu-agent GROUP_EXPERIENCE_UPDATE) ---
def _get_group_experience_update_system() -> str:
    preamble = (_practice_config().get("group_update_system_preamble") or "Merge new experiences with existing ones.").strip()
    return f"""{preamble}

Agent objective:
{_get_agent_objective()}

Learning objective:
{_get_learning_objective()}

You will receive:
- Existing experiences: a list with indices [0], [1], ...
- New experiences: from the current round (user selected a variant; we extracted experiences)

For each new experience, decide one operation (ADD, UPDATE, DELETE, NONE). Output a JSON array: one object per new experience.

- ADD: new information not in any existing experience; content is the new experience text.
- UPDATE: refines an existing experience; set "id" to the existing index (0, 1, ...), "content" to the merged/improved text.
- DELETE: new experience contradicts or invalidates an existing one; set "id" to that index, "content" to empty string.
- NONE: redundant or already covered; "id" null, "content" empty.

Output only a valid JSON array of objects: {{ "operation": "ADD"|"UPDATE"|"DELETE"|"NONE", "id": number|null, "content": "string" }}. No markdown."""


def _group_experience_update(
    api_key: str,
    existing_library: list[str],
    new_experiences: list[str],
) -> list[str]:
    """Merge new experiences with existing via ADD/UPDATE/DELETE (youtu-agent experience_updater pattern)."""
    if not new_experiences:
        return existing_library or []
    if not existing_library:
        return new_experiences[:EXPERIENCE_DECAY_MAX_ITEMS]

    existing_formatted = "\n".join([f"[{i}]. {e}" for i, e in enumerate(existing_library)])
    new_formatted = "\n".join([f"- {e}" for e in new_experiences])
    user_msg = f"""Existing experiences:\n{existing_formatted}\n\nNew experiences from this round:\n{new_formatted}\n\nOutput the JSON array of operations (one per new experience)."""

    raw = call_claude(
        api_key,
        [{"type": "text", "text": _get_group_experience_update_system()}],
        user_msg,
        max_tokens_override=2048,
    )
    # Parse JSON array from response (may be inside ```json)
    try:
        json_str = raw.strip()
        if "```json" in json_str:
            json_str = json_str.split("```json")[-1].split("```")[0].strip()
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0].strip()
        operations = json.loads(json_str)
        if not isinstance(operations, list):
            fallback = new_experiences + existing_library[: max(0, EXPERIENCE_DECAY_MAX_ITEMS - len(new_experiences))]
            return fallback[:EXPERIENCE_DECAY_MAX_ITEMS]
    except (json.JSONDecodeError, TypeError):
        log.warning("group_experience_update: failed to parse JSON, prepending new experiences")
        fallback = new_experiences + (existing_library or [])[: max(0, EXPERIENCE_DECAY_MAX_ITEMS - len(new_experiences))]
        return fallback[:EXPERIENCE_DECAY_MAX_ITEMS]

    # Apply operations strictly: only ADD, UPDATE, DELETE, NONE; ignore unknown operation values
    new_list: list[str | None] = list(existing_library)
    for op in operations:
        if not isinstance(op, dict):
            continue
        operation = (op.get("operation") or "NONE").upper()
        if operation not in ("ADD", "UPDATE", "DELETE", "NONE"):
            continue
        op_id = op.get("id")
        content = (op.get("content") or "").strip()
        idx = None
        if op_id is not None:
            try:
                idx = int(op_id) if isinstance(op_id, int) else int(str(op_id))
            except (ValueError, TypeError):
                pass
        if operation == "ADD" and content:
            new_list.append(content)
        elif operation == "UPDATE" and idx is not None and 0 <= idx < len(new_list) and content:
            new_list[idx] = content
        elif operation == "DELETE" and idx is not None and 0 <= idx < len(new_list):
            new_list[idx] = None
    out = [x for x in new_list if x is not None]
    return out[:EXPERIENCE_DECAY_MAX_ITEMS]


def _apply_decay(experience_library: list[str], max_items: int | None = None) -> list[str]:
    """Use only the first max_items (newest first). Older items drop off so past preferences matter less."""
    if max_items is None:
        max_items = EXPERIENCE_DECAY_MAX_ITEMS
    return (experience_library or [])[:max_items]


def _format_experience_for_prompt(decayed_items: list[str]) -> str:
    if not decayed_items:
        return ""
    bullets = "\n".join(f"• {item}" for item in decayed_items)
    return f"\n\nPast preferences (older items matter less; user may not want them anymore):\n{bullets}"


def _format_cta_and_links_for_prompt(spec: DesignSpec) -> str:
    """Format spec CTAs and footer links so the LLM uses exactly these in generated TSX (no placeholder #)."""
    parts: list[str] = []
    entries = spec.ctaEntries or []
    if entries:
        parts.append("CTAs (use these exact label + url in buttons/links; do not use href=\"#\" or placeholder):")
        for e in entries:
            typ = getattr(e, "type", "button")
            label = (e.label or "").strip() or "Get started"
            if typ in ("contact_form", "contact_mailto"):
                email = (getattr(e, "contactEmail", None) or "").strip()
                url = f"mailto:{email}" if email else "mailto:"
                if typ == "contact_form":
                    parts.append(f"  - Contact form (label \"{label}\", recipient {email}): render a form with name/email/message that opens mailto:{email} on submit")
                else:
                    parts.append(f"  - \"{label}\" -> {url}")
            else:
                url = (e.url or "").strip() or "#"
                if typ == "call" and getattr(e, "embedCalendly", False):
                    parts.append(
                        f'  - "{label}" -> Calendly: render a BUTTON (not a link) that when clicked opens the Calendly widget. Do NOT embed the widget visible by default. Use useState to hide the Calendly embed initially; on button click set state to show it (e.g. in a modal or an expandable section below the button). The button must be a <button> or <button type="button"> with the label "{label}". Include the Calendly script (Script from next/script or load https://assets.calendly.com/assets/external/widget.js) and a div with className="calendly-inline-widget" and data-url="{url}" that is only rendered/visible after the button is clicked, so CTA clicks can be tracked before opening the widget.'
                    )
                else:
                    parts.append(f"  - \"{label}\" -> {url}")
    if spec.socials and isinstance(spec.socials, dict):
        for k, v in (spec.socials or {}).items():
            if v and isinstance(v, str) and v.strip():
                parts.append(f"  - Footer social \"{k}\" -> {v.strip()}")
    if spec.privacyUrl and spec.privacyUrl.strip():
        parts.append(f"  - Footer \"Privacy\" -> {spec.privacyUrl.strip()}")
    if spec.termsUrl and spec.termsUrl.strip():
        parts.append(f"  - Footer \"Terms\" -> {spec.termsUrl.strip()}")
    if spec.securityUrl and spec.securityUrl.strip():
        parts.append(f"  - Footer \"Security\" -> {spec.securityUrl.strip()}")
    if not parts:
        return ""
    parts.append("Only these items should be clickable links or buttons. Do not add links to pages that do not exist (e.g. /features, /pricing, /about).")
    return "\n\n" + "\n".join(parts)


def _get_diversity_instruction(
    api_key: str,
    spec: DesignSpec,
    experience_decayed: list[str],
    similarity_round: int,
) -> str:
    """Compute diversity/convergence instruction from E and round. Scale variation: Bold Variation for new/early rounds, Micro-Refinement for established winners."""
    round_val = max(0, similarity_round)
    if round_val >= 2:
        variation_mode = "Micro-Refinement"
        mode_sentence = "This is an established direction (later round): favor micro-refinements; keep strong elements stable and vary only where it clearly improves conversion."
    else:
        variation_mode = "Bold Variation"
        mode_sentence = "This is a new project / early round: favor bold variation across the four variants; explore distinct aesthetics and layouts."
    cfg = _practice_config()
    preamble = (cfg.get("diversity_system_preamble") or "Output 1-3 sentences on how much to align vs vary across four variants, given experiences and round.").strip()
    tpl = (cfg.get("diversity_user_template") or "Experiences:\n{{experiences}}\n\nRound: {{round}}\n\nSpec: {{spec}}\n\nOutput the diversity instruction.").strip()
    experiences_str = "\n".join(f"• {e}" for e in experience_decayed) if experience_decayed else "(none)"
    user_msg = tpl.replace("{{experiences}}", experiences_str).replace("{{round}}", str(round_val)).replace("{{spec}}", _spec_for_prompt(spec))
    if "{{variation_mode}}" in tpl:
        user_msg = user_msg.replace("{{variation_mode}}", variation_mode)
    else:
        user_msg = user_msg + "\n\n" + mode_sentence
    try:
        raw = call_claude(
            api_key,
            [{"type": "text", "text": preamble}],
            user_msg,
            max_tokens_override=256,
        )
        return raw.strip()
    except Exception as e:
        log.warning("diversity_instruction fallback: %s", e)
        return "Balance alignment with the preferred direction (from experiences) with moderate variation across the four variants; incorporate good aspects from previously rejected variants where the experience library encodes them."


def _get_similar_variant_system_blocks(
    experience_brief: str,
    experience_library_decayed: list[str] | None = None,
    similarity_round: int = 0,
    diversity_instruction: str = "",
    competitor_dna: dict | None = None,
    competitor_dna_md: str | None = None,
) -> list[dict]:
    cfg = _practice_config()
    instruction = (cfg.get("similar_variant_instruction") or "Follow the experience brief and past preferences as the token prior; generate one of four variants.").strip()
    round_tpl = (cfg.get("round_note_template") or "").strip()
    round_note = ""
    if round_tpl and "{{round}}" in round_tpl:
        round_note = "\n\n" + round_tpl.replace("{{round}}", str(max(0, similarity_round)))
    extra = _format_experience_for_prompt(experience_library_decayed or [])
    token_prior_note = (f" If past preferences are listed, consider them but weight them less than the current brief (they may be outdated)." if extra else "")
    diversity_block = f"\n\nDiversity/convergence (follow for how much to vary): {diversity_instruction}" if diversity_instruction else ""
    blocks = [
        {"type": "text", "text": FRONTEND_DESIGN_SKILL, "cache_control": {"type": "ephemeral"}},
    ]
    inspiration_block = _build_inspiration_system_block(competitor_dna)
    if inspiration_block:
        blocks.append(inspiration_block)
    md_block = _build_inspiration_md_block(competitor_dna_md)
    if md_block:
        blocks.append(md_block)
    blocks.append({
        "type": "text",
        "text": f"""Follow the design skill above. {instruction}{round_note}{token_prior_note}{diversity_block}

Output: single JSON only: {{ "tsx": "<full TSX string>" }}. No markdown, no preamble. Full page: nav, hero, ≥2 sections, footer. next/font/google + Tailwind. {FONT_WHITELIST_PROMPT} Browser-only, responsive (Tailwind sm:/md:/lg:), valid React/JSX. Only use as clickable links/buttons the CTAs and footer links from the user message—do not add links to /features, /pricing, /about or other non-existent routes.""",
    })
    return blocks


def build_similar_variant_user_message(
    experience_brief: str,
    spec: DesignSpec,
    variant_index: int,
    experience_library_decayed: list[str] | None = None,
    similarity_round: int = 0,
    diversity_instruction: str = "",
) -> str:
    spec_block = _spec_for_prompt(spec)
    extra = _format_experience_for_prompt(experience_library_decayed or [])
    cfg = _practice_config()
    instruction = (cfg.get("similar_variant_instruction") or "Follow the experience brief and past preferences.").strip()
    round_tpl = (cfg.get("round_note_template") or "").strip()
    round_note = ""
    if round_tpl and "{{round}}" in round_tpl:
        round_note = "\n\n" + round_tpl.replace("{{round}}", str(max(0, similarity_round)))
    diversity_block = f"\n\nDiversity: {diversity_instruction}" if diversity_instruction else ""
    cta_block = _format_cta_and_links_for_prompt(spec)
    cta_instruction = f"\n\nUse these exact CTAs and links in the page (no href=\"#\" or placeholders):{cta_block}" if cta_block else ""
    logo_note = _logo_instruction(spec)
    return f"""Experience brief (token prior—follow this direction):\n{experience_brief}{extra}\n\n{instruction}{round_note}{diversity_block}\n\nBusiness/spec (for copy):\n{spec_block}{cta_instruction}{logo_note}\n\nYou are generating variant {variant_index} of 4. Output JSON only: {{ "tsx": "..." }}."""


def _strip_tsx_fences(value: str) -> str:
    trimmed = value.strip()
    m = re.search(r"^```(?:tsx|ts|jsx)?\s*\n?([\s\S]*?)\n?```$", trimmed)
    if m:
        return m.group(1).strip()
    return trimmed


LOGO_PLACEHOLDER = "__LOGO_URL__"


def _inject_logo_url(tsx: str, spec: DesignSpec | None) -> str:
    """Replace the __LOGO_URL__ placeholder in generated TSX with the actual logo data URL."""
    if not spec or LOGO_PLACEHOLDER not in tsx:
        return tsx
    logo_url = _get_logo_url(spec)
    if not logo_url:
        return tsx
    return tsx.replace(LOGO_PLACEHOLDER, logo_url)


def _validate_tsx_variant(value: str) -> bool:
    s = _strip_tsx_fences(value).strip()
    if s.startswith("<!DOCTYPE") or s.startswith("<html"):
        return False
    if "export default" not in s:
        return False
    return True


def _parse_single_variant_response(text: str) -> str | None:
    trimmed = text.strip()
    try:
        code_block = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", trimmed)
        to_parse = code_block.group(1).strip() if code_block else trimmed
        parsed = json.loads(to_parse)
        if isinstance(parsed.get("tsx"), str):
            return parsed["tsx"]
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass
    tsx_block = re.search(r"```(?:tsx|ts|jsx)?\s*\n?([\s\S]*?)\n?```", trimmed)
    if tsx_block:
        return tsx_block.group(1).strip()
    if "export default" in trimmed:
        return trimmed
    return None


# --- LLM API (Anthropic Messages) ---------------------------------------------
class RateLimitError(Exception):
    """Raised when Anthropic returns 429 and retries are exhausted."""
    def __init__(self, message: str, retry_after: int | None = None):
        super().__init__(message)
        self.retry_after = retry_after


def call_claude(
    api_key: str,
    system: str | list[dict],
    user_content: str,
    max_tokens_override: int | None = None,
) -> str:
    model = os.environ.get("ANTHROPIC_MODEL", ANTHROPIC_DEFAULT_MODEL)
    max_tokens = max_tokens_override or int(os.environ.get("ANTHROPIC_MAX_TOKENS", MAX_OUTPUT_TOKENS))
    raw_temp = os.environ.get("ANTHROPIC_TEMPERATURE")
    try:
        temperature = float(raw_temp) if raw_temp not in (None, "") else DEFAULT_TEMPERATURE
    except (TypeError, ValueError):
        temperature = DEFAULT_TEMPERATURE
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": [{"role": "user", "content": user_content}],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    max_attempts = 3
    with httpx.Client(timeout=HTTP_TIMEOUT) as client:
        for attempt in range(max_attempts):
            try:
                if attempt > 0:
                    log.info("call_claude attempt %s/%s", attempt + 1, max_attempts)
                resp = client.post(ANTHROPIC_API_URL, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                content = data.get("content") or []
                parts = [b["text"] for b in content if b.get("type") == "text" and isinstance(b.get("text"), str)]
                text = "".join(parts).strip()
                if not text:
                    raise RuntimeError("Empty response from Anthropic")
                log.info("call_claude ok len=%s", len(text))
                return text
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                log.warning("call_claude HTTP %s attempt %s", status, attempt + 1)
                if status == 429:
                    retry_header = e.response.headers.get("Retry-After")
                    retry_after_sec = int(retry_header) if retry_header and retry_header.isdigit() else None
                    if attempt == max_attempts - 1:
                        raise RateLimitError(
                            "Rate limit exceeded after retries",
                            retry_after=retry_after_sec,
                        ) from e
                    delay = retry_after_sec if retry_after_sec is not None else (2 ** (attempt + 1))
                    log.info("call_claude 429 backoff %.1fs", min(delay, 60))
                    time.sleep(min(delay, 60))
                    continue
                if status >= 500 and attempt < max_attempts - 1:
                    time.sleep(2)
                    continue
                # Surface Anthropic's error body for 4xx (e.g. 400 invalid request / model)
                err_body = ""
                try:
                    err_body = (e.response.text or "").strip()
                    if err_body:
                        parsed = e.response.json()
                        err_msg = parsed.get("error", {}).get("message") if isinstance(parsed.get("error"), dict) else parsed.get("message")
                        if err_msg:
                            err_body = str(err_msg)
                except Exception:
                    pass
                raise RuntimeError(f"Anthropic API {status}: {err_body or e.response.reason_phrase or str(e)}") from e
            except (httpx.RequestError, httpx.TimeoutException) as e:
                log.warning("call_claude request error attempt %s: %s", attempt + 1, e)
                if attempt == max_attempts - 1:
                    raise
                time.sleep(2)
                continue


# --- Template fallback (no API key): TSX only ---------------------------------
def _esc(s: str) -> str:
    """Escape for safe use inside TSX string (quotes and backslashes)."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")


def _cta_copy(cta_type: str) -> str:
    if cta_type == "call":
        return "Book a call"
    if cta_type == "trial":
        return "Start free trial"
    if cta_type in ("contact_form", "contact_mailto"):
        return "Contact us"
    return "Get started"


def _get_cta_list(spec: DesignSpec) -> list[tuple[str, str, bool, bool, str | None]]:
    """Returns list of (label, url, embed_calendly, is_contact_inline, contact_email)."""
    entries = spec.ctaEntries or []
    if not entries:
        label = _cta_copy(spec.ctaType)
        return [(label, "#", False, False, None)]
    out: list[tuple[str, str, bool, bool, str | None]] = []
    for e in entries:
        label = (e.label or "").strip() or _cta_copy(e.type)
        if getattr(e, "type", None) == "contact_form":
            email = (getattr(e, "contactEmail", None) or "").strip()
            out.append((label, "#", False, True, email or None))
        elif getattr(e, "type", None) == "contact_mailto":
            email = (getattr(e, "contactEmail", None) or "").strip()
            out.append((label, "mailto:" + email if email else "#", False, False, None))
        else:
            url = (e.url or "").strip() or "#"
            embed = getattr(e, "embedCalendly", False) and bool(url)
            out.append((label, url, embed, False, None))
    return out


def _build_cta_block(spec: DesignSpec, btn_class: str) -> tuple[str, bool]:
    """Returns (jsx_fragment_for_ctas, needs_calendly_script). Uses _esc for strings in JSX."""
    ctas = _get_cta_list(spec)
    parts: list[str] = []
    needs_calendly = False
    for label, url, embed_calendly, is_contact_inline, contact_email in ctas:
        if embed_calendly:
            needs_calendly = True
            # Button opens Calendly so we track the click (beacon) before showing the widget.
            # Template must define showCalendly, setShowCalendly (see _build_template_variant).
            parts.append(
                f'<button type="button" className={{`rounded-lg {btn_class} px-6 py-3 font-medium`}} onClick={{() => setShowCalendly(true)}}>{_esc(label)}</button>'
                f'{{showCalendly && <div className="calendly-inline-widget" data-url={json.dumps(url)} style={{{{ minWidth: 320, height: 700 }}}}></div>}}'
            )
        elif is_contact_inline and contact_email:
            # Inline contact form: name, email, message; submit opens mailto with body
            email_js = json.dumps(contact_email)
            parts.append(
                f'<form onSubmit={{(e) => {{ e.preventDefault(); const f = e.currentTarget; const body = encodeURIComponent("Name: " + (f.querySelector("[name=\\"name\\"]")?.value ?? "") + "\\nEmail: " + (f.querySelector("[name=\\"email\\"]")?.value ?? "") + "\\nMessage: " + (f.querySelector("[name=\\"message\\"]")?.value ?? "")); window.location.href = "mailto:" + {email_js} + "?subject=Contact&body=" + body; }}; }} className="space-y-3 text-left max-w-md">'
                f'<input name="name" placeholder="Full name" className="w-full rounded border border-zinc-300 px-3 py-2" required />'
                f'<input name="email" type="email" placeholder="Your email" className="w-full rounded border border-zinc-300 px-3 py-2" required />'
                f'<textarea name="message" placeholder="Message" rows={{3}} className="w-full rounded border border-zinc-300 px-3 py-2" required />'
                f'<button type="submit" className={{`rounded-lg {btn_class} px-6 py-3 font-medium`}}>{_esc(label)}</button>'
                f'</form>'
            )
        else:
            parts.append(
                f'<a href={json.dumps(url)} className="inline-block rounded-lg {btn_class} px-6 py-3 font-medium">{_esc(label)}</a>'
            )
    return "\n        ".join(parts), needs_calendly


def _footer_block(spec: DesignSpec, muted_class: str) -> str:
    """JSX for footer: social links + legal (privacy, terms, security). Empty if none."""
    parts: list[str] = []
    socials = spec.socials or {}
    for key, url in socials.items():
        if url and isinstance(url, str) and url.strip():
            label = key.replace("_", " ").title()
            parts.append(f'<a href={json.dumps(url.strip())} className="{muted_class} hover:underline" target="_blank" rel="noopener noreferrer">{_esc(label)}</a>')
    legal: list[tuple[str, str]] = []
    if spec.privacyUrl and spec.privacyUrl.strip():
        legal.append(("Privacy", spec.privacyUrl.strip()))
    if spec.termsUrl and spec.termsUrl.strip():
        legal.append(("Terms", spec.termsUrl.strip()))
    if spec.securityUrl and spec.securityUrl.strip():
        legal.append(("Security", spec.securityUrl.strip()))
    for label, url in legal:
        parts.append(f'<a href={json.dumps(url)} className="{muted_class} hover:underline" target="_blank" rel="noopener noreferrer">{_esc(label)}</a>')
    if not parts:
        return ""
    links = "\n        ".join(parts)
    return f'''<footer className="mt-16 py-8 border-t border-zinc-200 text-center text-sm flex flex-wrap justify-center gap-4 {muted_class}">
        {links}
      </footer>'''


def _palette(spec: DesignSpec) -> tuple[str, str, str, str]:
    preset = (spec.colorScheme or {}).get("preset", "neutral")
    if preset == "dark":
        return "bg-gray-900", "text-white", "text-gray-400", "bg-white text-gray-900 hover:bg-gray-100"
    if preset == "warm":
        return "bg-stone-50", "text-stone-900", "text-stone-600", "bg-amber-700 text-white hover:bg-amber-800"
    if preset == "cool":
        return "bg-slate-50", "text-slate-900", "text-slate-600", "bg-slate-700 text-white hover:bg-slate-800"
    return "bg-white", "text-gray-900", "text-gray-600", "bg-gray-900 text-white hover:bg-gray-800"


def _logo_jsx(spec: DesignSpec) -> str:
    """Return JSX for the logo: an <img> if logoDataUrl is present, otherwise the company name text."""
    wi = spec.websiteInformation or WebsiteInformation(whatTheyDo="")
    name = wi.name or "Your Company"
    logo_url = _get_logo_url(spec)
    if logo_url:
        return f'<img src={json.dumps(logo_url)} alt={json.dumps(name)} className="h-8 w-auto" />'
    return _esc(name)


def _build_template_variant(spec: DesignSpec, variant_index: int) -> str:
    wi = spec.websiteInformation or WebsiteInformation(whatTheyDo="")
    name = wi.name or "Your Company"
    tagline = wi.tagline or ""
    what = wi.whatTheyDo or ""
    goals = spec.goals or ["Learn more"]
    features = spec.features or spec.skillsOrNiches or []
    body_class, text_class, muted_class, btn_class = _palette(spec)
    cta_block, needs_calendly = _build_cta_block(spec, btn_class)
    footer_jsx = _footer_block(spec, muted_class)
    logo_element = _logo_jsx(spec)
    # When Calendly embed is used, CTA is a button that shows widget on click; need state in Page
    use_client = '"use client";\n\n' if needs_calendly else ""
    use_state_import = 'import { useState } from "react";\n\n' if needs_calendly else ""
    state_line = "  const [showCalendly, setShowCalendly] = useState(false);\n  " if needs_calendly else "  "

    if variant_index == 0:
        tag = f'<p className="mt-2 text-xl {muted_class}">{_esc(tagline)}</p>' if tagline else ""
        return f'''{use_client}{use_state_import}export default function Page() {{
{state_line}return (
    <div className="min-h-screen {body_class} {text_class}">
      <nav className="flex items-center justify-between max-w-4xl mx-auto px-6 py-4">
        <span className="text-xl font-bold">{logo_element}</span>
        {cta_block}
      </nav>
      <main className="max-w-4xl mx-auto px-6 py-16 text-center">
        <h1 className="text-4xl font-bold tracking-tight">{_esc(name)}</h1>
        {tag}
        <p className="mt-6 {muted_class}">{_esc(what)}</p>
        <div className="flex flex-wrap gap-3 justify-center">
        {cta_block}
        </div>
      </main>
      {footer_jsx}
    </div>
  );
}}
'''

    if variant_index == 1:
        tag = f'<p className="mt-2 text-lg {muted_class}">{_esc(tagline)}</p>' if tagline else ""
        return f'''{use_client}{use_state_import}export default function Page() {{
{state_line}return (
    <div className="min-h-screen {body_class} {text_class}">
      <nav className="flex items-center justify-between max-w-5xl mx-auto px-6 py-4">
        <span className="text-xl font-bold">{logo_element}</span>
        {cta_block}
      </nav>
      <main className="max-w-5xl mx-auto px-6 py-20">
        <div className="flex flex-col md:flex-row md:items-center md:gap-12">
          <div className="flex-1">
            <h1 className="text-4xl font-bold">{_esc(name)}</h1>
            {tag}
            <p className="mt-4 {muted_class}">{_esc(what)}</p>
            <div className="flex flex-wrap gap-3 mt-4">
            {cta_block}
            </div>
          </div>
          <div className="mt-8 md:mt-0 flex-1 h-48 bg-gray-200 rounded-lg flex items-center justify-center text-gray-500">Visual</div>
        </div>
      </main>
      {footer_jsx}
    </div>
  );
}}
'''

    if variant_index == 2:
        tag = f'<p className="mt-1 {muted_class}">{_esc(tagline)}</p>' if tagline else ""
        feats = "".join(
            f'<li key={json.dumps(_esc(f))} className="flex items-center gap-2"><span className="text-green-600">✓</span>{_esc(f)}</li>\n        '
            for f in features[:3]
        )
        return f'''{use_client}{use_state_import}export default function Page() {{
{state_line}return (
    <div className="min-h-screen {body_class} {text_class}">
      <nav className="flex items-center justify-between max-w-4xl mx-auto px-6 py-4">
        <span className="text-xl font-bold">{logo_element}</span>
        {cta_block}
      </nav>
      <main className="max-w-4xl mx-auto px-6 py-16">
        <h1 className="text-3xl font-bold">{_esc(name)}</h1>
        {tag}
        <p className="mt-4">{_esc(what)}</p>
        <ul className="mt-6 space-y-2">{feats.rstrip()}</ul>
        <div className="flex flex-wrap gap-3 mt-6">
        {cta_block}
        </div>
      </main>
      {footer_jsx}
    </div>
  );
}}
'''

    dark_muted = "text-gray-400" if "gray-900" in body_class else muted_class
    tag = f'<p className="mt-2 {dark_muted}">{_esc(tagline)}</p>' if tagline else ""
    goals_list = "".join(f'<li key={json.dumps(_esc(g))}>{_esc(g)}</li>\n        ' for g in goals[:3])
    return f'''{use_client}{use_state_import}export default function Page() {{
{state_line}return (
    <div className="min-h-screen {body_class} {text_class}">
      <nav className="flex items-center justify-between max-w-4xl mx-auto px-6 py-4">
        <span className="text-xl font-bold">{logo_element}</span>
        {cta_block}
      </nav>
      <main className="max-w-4xl mx-auto px-6 py-20 text-center">
        <h1 className="text-4xl font-bold">{_esc(name)}</h1>
        {tag}
        <p className="mt-6 {dark_muted}">{_esc(what)}</p>
        <ul className="mt-6 list-disc list-inside text-left max-w-sm mx-auto {dark_muted}">{goals_list.rstrip()}</ul>
        <div className="flex flex-wrap gap-3 justify-center mt-6">
        {cta_block}
        </div>
      </main>
      {footer_jsx}
    </div>
  );
}}
'''


def generate_template_variants(spec: DesignSpec) -> list[str]:
    return [_build_template_variant(spec, i) for i in range(VARIANT_COUNT)]


# --- FastAPI app -------------------------------------------------------------
app = FastAPI(title="Landright Generate API", version="0.1.0")


class BeaconCORSMiddleware(BaseHTTPMiddleware):
    """Allow any origin for POST /beacon so customer-deployed sites can send CTA clicks to our backend."""

    async def dispatch(self, request, call_next):
        if request.url.path != "/beacon":
            return await call_next(request)
        origin = request.headers.get("origin", "").strip() or "*"
        if request.method == "OPTIONS":
            return Response(
                status_code=200,
                headers={
                    "Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Methods": "POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type",
                    "Access-Control-Max-Age": "86400",
                },
            )
        response = await call_next(request)
        response.headers["Access-Control-Allow-Origin"] = origin
        return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
app.add_middleware(BeaconCORSMiddleware)  # outermost: allow any origin for /beacon only


# --- Critic Agent (Shadow-Mode Internal Audit) --------------------------------
CRITIC_THRESHOLD = float(os.environ.get("CRITIC_THRESHOLD", "0.85"))
CRITIC_MAX_RETRIES = int(os.environ.get("CRITIC_MAX_RETRIES", "2"))

def _build_critic_system_prompt(inspiration_triggers: list[str] | None = None) -> str:
    """Build critic system prompt, optionally incorporating persuasion triggers as hard constraints."""
    trigger_block = ""
    if inspiration_triggers:
        trigger_list = ", ".join(inspiration_triggers[:8])
        trigger_block = f"""

HARD CONSTRAINTS from inspiration scan — if the variant is missing any of these elements, it MUST be flagged for re-generation:
  Required persuasion elements: {trigger_list}
  Check: Does the variant include a risk-reversal element (e.g. 'no credit card required', 'free trial', guarantee)?
  Check: Does the variant include social proof (e.g. customer count, logos, testimonials)?
  Check: Does the variant use authority signals (e.g. trust badges, certifications, 'trusted by X')?
  If ANY required element from the scan is missing, set that axis score below 0.85 and list the missing element in issues."""

    return f"""You are a landing page conversion expert and design critic. Score the given TSX landing page variant on two axes.

Output ONLY a valid JSON object (no markdown, no commentary):
{{
  "friction": 0.0-1.0,
  "clarity": 0.0-1.0,
  "reasoning": "One sentence explaining why this variant is better than the original seed. Be specific about conversion improvements (e.g. 'Simplified the footer to reduce exit-path friction').",
  "issues": ["list of specific issues if friction or clarity is below 0.85"],
  "conversion_drivers": ["top 3 conversion-driving design patterns used in this variant (e.g. 'Gradient CTA with hover lift', 'Social Proof Marquee', 'Bento Grid Layout')"]
}}

Scoring guide:
- friction (INVERTED: 1.0 = zero friction, 0.0 = maximum friction):
  * 1.0: Crystal clear CTA, minimal distractions, zero unnecessary form fields or steps.
  * 0.85: Good but minor issues — one unclear label, slightly competing CTAs.
  * 0.7: Noticeable friction — multiple CTAs compete, unclear value prop, too many nav links.
  * <0.5: Significant friction — confusing layout, broken flow, unclear next step.

- clarity (1.0 = perfectly clear, 0.0 = completely confusing):
  * 1.0: Headline instantly communicates value, hierarchy is obvious, visual flow is natural.
  * 0.85: Good but one element is ambiguous — subhead doesn't support headline, or section order is off.
  * 0.7: Multiple clarity issues — jargon, unclear headline, competing messages.
  * <0.5: Fundamentally unclear — user can't tell what the product does in 5 seconds.

- reasoning: Explain what makes this variant beat the seed / generic landing page. Be specific about conversion. One or two sentences max.
- conversion_drivers: Name exactly 3 specific design patterns that drive conversion in this variant.{trigger_block}

Output ONLY the JSON object."""


def _critic_score_variant(
    api_key: str, tsx: str, spec: DesignSpec, variant_index: int,
    inspiration_triggers: list[str] | None = None,
) -> dict:
    """Score a single variant on friction and clarity. Returns {friction, clarity, reasoning, issues, conversion_drivers}."""
    excerpt = tsx[:8000]
    spec_summary = f"Company: {spec.websiteInformation.name}, Does: {spec.websiteInformation.whatTheyDo[:200]}"
    user_msg = f"Score this landing page variant (variant {variant_index + 1}/4).\n\nBusiness: {spec_summary}\n\nTSX (excerpt):\n{excerpt}"
    system_prompt = _build_critic_system_prompt(inspiration_triggers)
    try:
        raw = call_claude(api_key, system_prompt, user_msg, max_tokens_override=512)
        text = raw.strip()
        if "```json" in text:
            text = text.split("```json")[-1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        result = json.loads(text)
        return {
            "friction": float(result.get("friction", 0.5)),
            "clarity": float(result.get("clarity", 0.5)),
            "reasoning": str(result.get("reasoning", "")),
            "issues": result.get("issues", []),
            "conversion_drivers": result.get("conversion_drivers", []),
        }
    except Exception as e:
        log.warning("critic_score_variant %d failed: %s", variant_index, e)
        return {"friction": 0.9, "clarity": 0.9, "reasoning": "Scoring unavailable", "issues": [], "conversion_drivers": []}


def _extract_inspiration_triggers(competitor_dna: dict | None) -> list[str]:
    """Pull persuasion triggers from inspiration data to use as critic constraints."""
    if not competitor_dna:
        return []
    diction = competitor_dna.get("diction", {})
    triggers = diction.get("triggers", []) if isinstance(diction, dict) else []
    return [str(t) for t in triggers[:10]] if isinstance(triggers, list) else []


def _run_critic_audit(
    api_key: str,
    variants: list[str | None],
    spec: DesignSpec,
    regenerate_fn,
    competitor_dna: dict | None = None,
) -> tuple[list[str | None], list[dict]]:
    """Run critic audit on all variants. Re-generate any below threshold. Returns (variants, reasoning_list)."""
    n = len(variants)
    reasoning_list: list[dict] = [{"reasoning": "", "friction": 0.0, "clarity": 0.0, "conversion_drivers": []}] * n
    current_variants = list(variants)
    inspiration_triggers = _extract_inspiration_triggers(competitor_dna)
    if inspiration_triggers:
        log.info("critic_audit: using %d inspiration triggers as constraints: %s", len(inspiration_triggers), inspiration_triggers)

    for attempt in range(1 + CRITIC_MAX_RETRIES):
        scores: list[dict] = [None] * n

        def score_one(i: int) -> tuple[int, dict]:
            if current_variants[i]:
                sc = _critic_score_variant(api_key, current_variants[i], spec, i, inspiration_triggers)
                return (i, sc)
            return (i, {"friction": 0.0, "clarity": 0.0, "reasoning": "Variant generation failed", "issues": ["empty"]})

        with ThreadPoolExecutor(max_workers=n) as executor:
            future_to_i = {executor.submit(score_one, i): i for i in range(n)}
            for future in as_completed(future_to_i):
                idx, score = future.result()
                scores[idx] = score

        reasoning_list = scores
        failing = [
            i for i in range(n)
            if current_variants[i]
            and (scores[i]["friction"] < CRITIC_THRESHOLD or scores[i]["clarity"] < CRITIC_THRESHOLD)
        ]

        if not failing or attempt >= CRITIC_MAX_RETRIES:
            break

        log.info("critic_audit attempt %d: %d variants below %.2f, regenerating", attempt + 1, len(failing), CRITIC_THRESHOLD)

        for i in failing:
            issues_str = "; ".join(scores[i].get("issues", [])[:3])
            feedback = f"Critic feedback: friction={scores[i]['friction']:.2f}, clarity={scores[i]['clarity']:.2f}. Issues: {issues_str}. Fix these issues."
            try:
                new_tsx = regenerate_fn(i + 1, feedback)
                current_variants[i] = new_tsx
                log.info("critic_audit: regenerated variant %d", i + 1)
            except Exception as e:
                log.warning("critic_audit: failed to regenerate variant %d: %s", i + 1, e)

    return current_variants, reasoning_list


# --- DesignSpecPipeline: extractDesignSpec ------------------------------------
_EXTRACT_SYSTEM_PROMPT = """You are an expert landing page design analyst. Given the HTML content (or screenshot) of a website, extract a comprehensive, structured design specification.

Output ONLY a valid JSON object with this schema (no markdown, no commentary):
{
  "brand": {
    "name": "string",
    "tagline": "string",
    "value_prop": "string"
  },
  "hero": {
    "layout": "two_column | centered | split | asymmetric",
    "headline": "string",
    "subheadline": "string",
    "primary_cta": "string",
    "trust_note": "string or null",
    "visual_type": "product_mockup | illustration | video | gradient | none",
    "visual_elements": ["string"]
  },
  "nav": {
    "position": "top_fixed | top_static | sidebar",
    "items": ["string"],
    "style": "string"
  },
  "social_proof": {
    "headline": "string or null",
    "type": "logo_strip | testimonials | stats | combined",
    "elements": ["string"]
  },
  "sections": [
    {
      "id": "string",
      "title": "string",
      "content_type": "features | steps | benefits | testimonials | pricing | security | integrations | faq | cta_banner",
      "elements": ["string"],
      "highlights": ["string"]
    }
  ],
  "design_system": {
    "layout": "string describing overall layout approach",
    "typography": {
      "headline_style": "string",
      "body_style": "string",
      "alignment": "left | center | mixed"
    },
    "color": {
      "background": "string",
      "text": "string",
      "accent": "string",
      "palette": ["#hex1", "#hex2", ...]
    },
    "components": {
      "buttons": "string describing button style",
      "cards": "string describing card style",
      "other": ["string"]
    }
  },
  "footer": {
    "cta_banner": { "headline": "string or null", "primary_cta": "string or null" },
    "columns": ["string"],
    "extras": ["string"]
  },
  "diction": {
    "tone": "string",
    "triggers": ["string"]
  },
  "theme_overrides": {
    "shadow_depths": "string describing shadow usage (e.g. 'subtle soft shadows on cards, heavy drop-shadow on hero CTA')",
    "border_radius": "string describing border-radius patterns (e.g. 'rounded-2xl cards, pill buttons, sharp nav')",
    "animation_style": "string describing animation/motion patterns (e.g. 'fade-in on scroll, hover scale on cards, gradient shift on buttons')",
    "transition_timing": "string (e.g. 'ease-out 300ms', 'spring-like 200ms')",
    "hover_effects": "string describing hover behaviors (e.g. 'cards lift with shadow, buttons darken, links underline')",
    "glassmorphism": "boolean - true if frosted glass effects are used",
    "gradients": "string describing gradient usage or 'none'"
  }
}

Rules:
- Extract EVERY section visible on the page in order.
- palette: 4-8 dominant hex colors.
- sections[].elements: list specific UI components and content used (cards, grids, icons, images, badges, etc.).
- sections[].highlights: key copy points or feature names listed.
- diction.triggers: specific persuasion techniques (social proof, urgency, authority, trust badges, risk reversal, scarcity, etc.).
- theme_overrides: Identify SIGNATURE AESTHETICS — the distinctive visual details that give the site its character. Look at shadow depths/styles, border-radius patterns across components, animation types and timing, hover effects, gradient usage, and any glassmorphism.
- Be thorough: capture design patterns, visual elements, component styles, and content structure.
- Output ONLY the JSON object. No preamble, no explanation."""

# Playwright: optional for JS-rendered fetch (install with: pip install playwright && playwright install chromium)
_playwright_sync: object = None


def _get_playwright():
    """Lazy-load Playwright sync API. Returns None if not installed or install incomplete."""
    global _playwright_sync
    if _playwright_sync is not None:
        return _playwright_sync
    try:
        from playwright.sync_api import sync_playwright
        _playwright_sync = sync_playwright
        return _playwright_sync
    except ImportError:
        return None


def _fetch_page_html_with_js(url: str, timeout_ms: int = 30_000) -> str | None:
    """Fetch page HTML after JS runs (normal load). Returns None if Playwright unavailable or fails."""
    pw = _get_playwright()
    if not pw:
        return None
    try:
        with pw() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_load_state("networkidle", timeout=min(15000, timeout_ms))
                html = page.content()
                return html
            finally:
                browser.close()
    except Exception as e:
        log.warning("Playwright fetch failed for %s: %s", url, e)
        return None


def _fetch_page_screenshot(url: str, timeout_ms: int = 30_000) -> str | None:
    """Load URL with Playwright and return a full-page screenshot as base64 PNG. Returns None if unavailable or fails."""
    pw = _get_playwright()
    if not pw:
        return None
    try:
        with pw() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.set_viewport_size({"width": 1280, "height": 720})
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_load_state("networkidle", timeout=min(15000, timeout_ms))
                raw = page.screenshot(type="png", full_page=False)
                if raw:
                    return base64.b64encode(raw).decode("ascii")
                return None
            finally:
                browser.close()
    except Exception as e:
        log.warning("Playwright screenshot failed for %s: %s", url, e)
        return None


def _extract_signals_from_html(html: str) -> str:
    """Extract structured text signals from HTML using BeautifulSoup. Accurate, attribute-order agnostic."""
    soup = BeautifulSoup(html, "html.parser")
    # Remove script/style so we don't include their text
    for tag in soup.find_all(["script", "style"]):
        tag.decompose()

    signals: list[str] = []

    # Title
    if soup.title and soup.title.string:
        signals.append(f"[title] {soup.title.string.strip()}")

    # Meta description (any attribute order)
    for meta in soup.find_all("meta", attrs={"name": "description"}):
        c = meta.get("content")
        if c and c.strip():
            signals.append(f"[meta-description] {c.strip()}")
            break
    else:
        for meta in soup.find_all("meta"):
            if (meta.get("property") or "").strip().lower() == "og:description":
                c = meta.get("content")
                if c and c.strip():
                    signals.append(f"[meta-description] {c.strip()}")
                    break

    # Headings
    for tag in soup.find_all(re.compile(r"^h[1-6]$", re.I)):
        text = tag.get_text(separator=" ", strip=True)
        if text:
            signals.append(f"[{tag.name}] {text}")

    # Paragraphs (first 20)
    for i, tag in enumerate(soup.find_all("p")):
        if i >= 20:
            break
        text = tag.get_text(separator=" ", strip=True)
        if text and len(text) > 10:
            signals.append(f"[p] {text[:300]}")

    # Buttons
    for tag in soup.find_all("button"):
        text = tag.get_text(separator=" ", strip=True)
        if text:
            signals.append(f"[button] {text}")

    # Links with visible text (first 30)
    for i, tag in enumerate(soup.find_all("a", href=True)):
        if i >= 30:
            break
        text = tag.get_text(separator=" ", strip=True)
        if text and len(text) > 1:
            signals.append(f"[link] {text}")

    # List items (first 30)
    for i, tag in enumerate(soup.find_all("li")):
        if i >= 30:
            break
        text = tag.get_text(separator=" ", strip=True)
        if text:
            signals.append(f"[li] {text[:200]}")

    # Image alt
    for tag in soup.find_all("img", alt=True):
        alt = (tag.get("alt") or "").strip()
        if alt and len(alt) > 2:
            signals.append(f"[img-alt] {alt}")

    # Layout class hints
    layout_keywords = ("grid", "flex", "hero", "card", "testimonial", "footer", "nav", "banner", "gradient", "shadow", "rounded")
    seen: set[str] = set()
    for tag in soup.find_all(True, class_=True):
        for c in tag.get("class") or []:
            c = c.lower()
            if c in layout_keywords and c not in seen:
                seen.add(c)
    if seen:
        signals.append(f"[layout-hints] {', '.join(sorted(seen)[:15])}")

    return "\n".join(signals)[:25000]


def _fetch_page_content(url: str) -> str:
    """Fetch target page (with JS so it loads as normal), then extract structured text signals.

    Tries Playwright first for JS-rendered content; falls back to plain HTTP if Playwright
    is unavailable or fails. Airgap: LLM receives only extracted semantic content, not raw HTML.
    """
    html: str | None = _fetch_page_html_with_js(url)
    if not html:
        with httpx.Client(timeout=15.0, follow_redirects=True, trust_env=False) as client:
            resp = client.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; Landright/1.0)"})
            resp.raise_for_status()
            html = resp.text
    return _extract_signals_from_html(html)


def _extract_design_spec_from_html(api_key: str, content: str, url: str) -> dict:
    """Use Claude to extract the rich inspiration spec from sanitized page content."""
    user_msg = f"Analyze this landing page and extract the full design specification.\n\nURL: {url}\n\nExtracted page content (headings, text, buttons, links, layout signals):\n{content}"
    raw = call_claude(api_key, _EXTRACT_SYSTEM_PROMPT, user_msg, max_tokens_override=4096)
    return _parse_extracted_spec(raw)


def _extract_design_spec_from_screenshot(api_key: str, image_data: str, url: str) -> dict:
    """Use Claude Vision to extract the rich inspiration spec from a screenshot."""
    if image_data.startswith("data:"):
        parts = image_data.split(",", 1)
        media_match = re.match(r"data:(image/\w+);base64", parts[0])
        media_type = media_match.group(1) if media_match else "image/png"
        b64 = parts[1] if len(parts) > 1 else ""
    else:
        media_type = "image/png"
        b64 = image_data

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": b64},
                },
                {
                    "type": "text",
                    "text": f"Analyze this competitor landing page screenshot and extract the design specification.\n\nURL: {url}",
                },
            ],
        }
    ]
    model = os.environ.get("ANTHROPIC_MODEL", ANTHROPIC_DEFAULT_MODEL)
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": 4096,
        "temperature": 0.2,
        "system": _EXTRACT_SYSTEM_PROMPT,
        "messages": messages,
    }
    with httpx.Client(timeout=HTTP_TIMEOUT) as client:
        resp = client.post(ANTHROPIC_API_URL, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        parts = [b["text"] for b in (data.get("content") or []) if b.get("type") == "text"]
        raw = "".join(parts).strip()
    return _parse_extracted_spec(raw)


def _parse_extracted_spec(raw: str) -> dict:
    """Parse Claude's JSON response into a dict (rich inspiration schema)."""
    text = raw.strip()
    if "```json" in text:
        text = text.split("```json")[-1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        log.warning("extract_design_spec: failed to parse JSON from response")
        return {}


def _merge_inspiration_results(results: list[dict]) -> dict:
    """Merge multiple inspiration extractions into a single combined spec."""
    if not results:
        return {}
    if len(results) == 1:
        return results[0]
    merged: dict = {}
    for key in ("brand", "hero", "nav", "social_proof", "footer", "diction"):
        for r in results:
            if key in r and r[key]:
                if key not in merged:
                    merged[key] = r[key]
    all_sections: list[dict] = []
    for r in results:
        for s in r.get("sections", []):
            all_sections.append(s)
    if all_sections:
        merged["sections"] = all_sections
    ds_list = [r.get("design_system", {}) for r in results if r.get("design_system")]
    if ds_list:
        merged_ds = ds_list[0].copy()
        all_palettes: list[str] = []
        for ds in ds_list:
            all_palettes.extend(ds.get("color", {}).get("palette", []))
        if all_palettes and "color" in merged_ds:
            merged_ds["color"]["palette"] = list(dict.fromkeys(all_palettes))[:12]
        merged["design_system"] = merged_ds
    return merged


@app.post("/extract-design-spec")
def extract_design_spec(body: ExtractDesignSpecBody):
    """Extract a rich inspiration spec from an uploaded screenshot (Vision)."""
    api_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip() or None
    if not api_key:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY is required for inspiration extraction")

    screenshot = (body.screenshot or "").strip()
    if not screenshot:
        raise HTTPException(status_code=400, detail="Provide a screenshot (base64 or data URL)")

    results: list[dict] = []
    errors: list[str] = []
    try:
        log.info("extract_inspiration: using uploaded screenshot (Vision)")
        result = _extract_design_spec_from_screenshot(api_key, screenshot, "uploaded screenshot")
        results.append(result)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            raise HTTPException(status_code=503, detail="Rate limit exceeded; try again shortly") from e
        err_detail = ""
        try:
            body = e.response.json()
            err_detail = (body.get("error") or {}).get("message") if isinstance(body.get("error"), dict) else body.get("message") or ""
            if not err_detail and isinstance(body.get("error"), str):
                err_detail = body["error"]
        except Exception:
            err_detail = (e.response.text or "").strip()[:500]
        msg = err_detail.strip() if err_detail else f"Vision API returned HTTP {e.response.status_code}"
        if e.response.status_code == 400:
            raise HTTPException(status_code=400, detail=msg) from e
        errors.append(f"screenshot: {msg}")
    except Exception as e:
        errors.append(str(e))

    if not results and errors:
        raise HTTPException(status_code=502, detail="; ".join(errors))

    merged = _merge_inspiration_results(results)
    log.info("extract_inspiration: done, %d sources, %d errors", len(results), len(errors))

    # Ghost Processing: auto-map Signature Aesthetics + Design System into theme_overrides
    ghost_theme: dict = {}
    ds = merged.get("design_system", {})
    to = merged.get("theme_overrides", {})
    if ds or to:
        ghost_theme = {**(to if isinstance(to, dict) else {})}
        if isinstance(ds, dict):
            color = ds.get("color", {})
            if isinstance(color, dict) and color.get("palette"):
                ghost_theme["palette"] = color["palette"]
            if isinstance(color, dict) and color.get("accent"):
                ghost_theme["accent"] = color["accent"]
            typo = ds.get("typography", {})
            if isinstance(typo, dict):
                if typo.get("headline_style"):
                    ghost_theme["headline_style"] = typo["headline_style"]
                if typo.get("body_style"):
                    ghost_theme["body_style"] = typo["body_style"]
            comps = ds.get("components", {})
            if isinstance(comps, dict):
                if comps.get("buttons"):
                    ghost_theme["button_style"] = comps["buttons"]
                if comps.get("cards"):
                    ghost_theme["card_style"] = comps["cards"]
            if ds.get("layout"):
                ghost_theme["layout"] = ds["layout"]

    # Derive top-3 conversion drivers from the scan
    drivers: list[str] = []
    hero = merged.get("hero", {})
    if isinstance(hero, dict) and hero.get("layout"):
        layout_name = str(hero["layout"]).replace("_", " ").title()
        drivers.append(f"{layout_name} Hero Layout")
    if isinstance(to, dict) and to.get("gradients") and to["gradients"] != "none":
        drivers.append("Gradient CTAs")
    sp = merged.get("social_proof", {})
    if isinstance(sp, dict) and sp.get("type"):
        sp_name = str(sp["type"]).replace("_", " ").title()
        drivers.append(f"{sp_name} Social Proof")
    sections = merged.get("sections", [])
    if isinstance(sections, list):
        for s in sections:
            if not isinstance(s, dict):
                continue
            ct = s.get("content_type", "")
            if ct == "testimonials" and "Testimonials Section" not in drivers:
                drivers.append("Testimonials Section")
            elif ct == "steps" and "Step-by-Step Flow" not in drivers:
                drivers.append("Step-by-Step Flow")
            elif ct == "security" and "Trust & Security Badges" not in drivers:
                drivers.append("Trust & Security Badges")
            elif ct == "pricing" and "Pricing Table" not in drivers:
                drivers.append("Pricing Table")
            if len(drivers) >= 5:
                break
    if isinstance(ds, dict) and ds.get("layout") and len(drivers) < 3:
        layout_desc = str(ds["layout"])
        if "bento" in layout_desc.lower():
            drivers.append("Bento Grid Layout")
        elif "grid" in layout_desc.lower():
            drivers.append("Grid-Based Layout")
    diction = merged.get("diction", {})
    triggers = diction.get("triggers", []) if isinstance(diction, dict) else []
    if isinstance(triggers, list):
        for t in triggers:
            t_str = str(t).title()
            if t_str not in drivers and len(drivers) < 5:
                drivers.append(f"{t_str} Strategy")

    resp: dict = {
        "inspiration": merged,
        "sources": len(results),
        "themeOverrides": ghost_theme,
        "conversionDrivers": drivers[:5],
    }
    if errors:
        resp["warnings"] = errors
    return resp


@app.post("/generate")
def generate(body: GenerateBody):
    # Stateless: experienceLibrary is ingested from the request body, decay is applied, and the updated
    # semantic advantages are returned in the response; no server-side persistence of experience.
    api_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip() or None
    spec = body.spec
    prompt_id = body.promptId
    chosen_html = body.chosenVariantHtml
    change_request = body.changeRequest
    selected_variant_index = body.selectedVariantIndex
    target_component = (body.targetComponent or "").strip() or None
    if target_component and target_component not in TARGET_COMPONENT_ALLOWED:
        raise HTTPException(status_code=400, detail="targetComponent must be Hero, CTA, or Features")

    company = (spec.websiteInformation.name or "") if spec and spec.websiteInformation else ""
    log.info(
        "generate request: company=%r promptId=%r has_chosen=%s has_change_request=%s selected_index=%s api_key=%s",
        company,
        prompt_id,
        bool(chosen_html),
        bool(change_request and change_request.strip()),
        selected_variant_index,
        "set" if api_key else "missing",
    )

    if not spec or not (prompt_id or "").strip():
        raise HTTPException(status_code=400, detail="spec and promptId are required")
    err = validate_spec(spec)
    if err:
        raise HTTPException(status_code=400, detail=err)
    if chosen_html is not None and len(chosen_html) > LIMITS["chosen_html_max_length"]:
        raise HTTPException(status_code=400, detail="chosenVariantHtml too long")
    if change_request is not None and len(change_request) > LIMITS["change_request_max_length"]:
        raise HTTPException(status_code=400, detail="changeRequest too long")
    # "Generate 4 similar": chosen + selectedIndex, no changeRequest. Otherwise refinement with change needs index.
    is_similar_path = chosen_html and selected_variant_index is not None and (not change_request or not change_request.strip())
    if chosen_html and change_request and change_request.strip():
        if selected_variant_index is None or selected_variant_index < 0 or selected_variant_index >= VARIANT_COUNT:
            raise HTTPException(
                status_code=400,
                detail="selectedVariantIndex (0–3) required when chosenVariantHtml and changeRequest are sent",
            )

    if not api_key:
        log.info("generate: no API key, returning template variants")
        variants = generate_template_variants(spec)
        return {"variants": variants, "source": "template", "experienceLibrary": []}

    # Pre-built library when client sends empty (paper: token prior). Accept JSON (experienceLibrary) or MD (experienceLibraryMd).
    if body.experienceLibrary is not None and len(body.experienceLibrary) > 0:
        effective_library = body.experienceLibrary
    elif body.experienceLibraryMd and body.experienceLibraryMd.strip():
        effective_library = _experience_brief_to_list(body.experienceLibraryMd.strip())
    else:
        effective_library = _get_default_experience_library()

    max_tokens = SINGLE_VARIANT_MAX_TOKENS

    if is_similar_path:
        log.info("generate: path=similar (rewards → variance → summarization/group advantage or extract + 4 variants)")
        variant_tsx_list = body.variantTsxList or []
        try:
            # Paper: reward ri = R(q, oi); we use user choice + optional LLM score
            rewards = _compute_rewards(api_key, spec, variant_tsx_list, selected_variant_index)
            n_r = len(rewards)
            mean_r = sum(rewards) / n_r if n_r else 0.0
            std_r = (sum((x - mean_r) ** 2 for x in rewards) / n_r) ** 0.5 if n_r else 0.0
            has_variance = (0 < mean_r < 1) or std_r > 0
            experience_brief: str
            experience_list: list[str]
            if has_variance and len(variant_tsx_list) >= VARIANT_COUNT:
                # Paper: only when clear winners/losers — per-rollout summarization then group advantage
                def do_summary(i: int) -> tuple[str, float]:
                    label = "Selected by user — reward 1" if i == selected_variant_index else "Not selected — reward 0"
                    r = rewards[i] if i < len(rewards) else 0.0
                    s = _summarize_rollout(
                        api_key, spec,
                        (variant_tsx_list[i] or "")[:EXPERIENCE_EXCERPT_MAX],
                        label,
                    )
                    return s, r
                summaries_with_rewards = []
                for i in range(VARIANT_COUNT):
                    s, r = do_summary(i)
                    summaries_with_rewards.append((s, r))
                experience_list = _group_advantage_extraction(
                    api_key, spec, summaries_with_rewards, effective_library
                )
                experience_brief = "\n".join(f"• {e}" for e in experience_list) if experience_list else "Follow the preferred direction from past choices."
                log.info("generate: group advantage (summarization + extraction) ran on %s variants", VARIANT_COUNT)
            else:
                experience_brief, experience_list = _extract_experience(api_key, spec, chosen_html)
                log.info("generate: no reward variance or missing variant list, single-variant extract")
            full_library = _group_experience_update(
                api_key, effective_library, experience_list
            )
        except RateLimitError as e:
            raise HTTPException(
                status_code=503,
                detail={"error": "rate_limit", "details": str(e), "retry_after": e.retry_after},
            ) from e
        except Exception as e:
            raise HTTPException(status_code=502, detail={"error": "Experience extraction failed", "details": str(e)})
        experience_decayed = _apply_decay(full_library)
        similarity_round = body.similarityRound if body.similarityRound is not None else 0
        log.info("generate: similarity_round=%s (token prior from config)", similarity_round)
        try:
            diversity_instruction = _get_diversity_instruction(api_key, spec, experience_decayed, similarity_round)
        except Exception as e:
            log.warning("generate: diversity_instruction fallback: %s", e)
            diversity_instruction = ""
        if PACE_DELAY_SEC > 0:
            time.sleep(PACE_DELAY_SEC)

        def generate_similar_variant(n: int) -> str:
            if PACE_DELAY_SEC > 0:
                time.sleep((n - 1) * PACE_DELAY_SEC)
            system_blocks = _get_similar_variant_system_blocks(
                experience_brief, experience_decayed, similarity_round, diversity_instruction,
                competitor_dna=body.competitorDna,
                competitor_dna_md=body.competitorDnaMd,
            )
            user_content = build_similar_variant_user_message(
                experience_brief, spec, n, experience_decayed, similarity_round, diversity_instruction,
            )
            raw_text = call_claude(api_key, system_blocks, user_content, max_tokens_override=max_tokens)
            tsx_raw = None
            try:
                parsed = json.loads(raw_text.strip())
                if isinstance(parsed.get("tsx"), str):
                    tsx_raw = parsed["tsx"]
            except (json.JSONDecodeError, TypeError):
                tsx_raw = _parse_single_variant_response(raw_text)
            if tsx_raw is None:
                raise RuntimeError(f"Variant {n}: Claude did not return valid TSX")
            tsx = _strip_tsx_fences(tsx_raw.strip())
            if _validate_tsx_variant(tsx):
                return tsx
            raise RuntimeError(f"Variant {n}: invalid or truncated TSX")

        variants = [None] * VARIANT_COUNT
        with ThreadPoolExecutor(max_workers=VARIANT_COUNT) as executor:
            future_to_n = {executor.submit(generate_similar_variant, n): n for n in range(1, VARIANT_COUNT + 1)}
            for future in as_completed(future_to_n):
                n = future_to_n[future]
                try:
                    variants[n - 1] = future.result()
                except RateLimitError as e:
                    raise HTTPException(
                        status_code=503,
                        detail={"error": "rate_limit", "details": str(e), "retry_after": e.retry_after},
                    ) from e
                except Exception as e:
                    raise HTTPException(
                        status_code=502,
                        detail={"error": "Generation failed", "details": str(e), "variantIndex": n},
                    )
        log.info("generate: similar path done, variants=%s, experience_library_len=%s", len(variants), len(full_library))
        variants = [_inject_logo_url(v, spec) if v else v for v in variants]

        # Critic Agent: audit and auto-fix
        def _regen_similar(n: int, feedback: str) -> str:
            system_blocks = _get_similar_variant_system_blocks(
                experience_brief, experience_decayed, similarity_round, diversity_instruction,
                competitor_dna=body.competitorDna,
                competitor_dna_md=body.competitorDnaMd,
            )
            base_msg = build_similar_variant_user_message(
                experience_brief, spec, n, experience_decayed, similarity_round, diversity_instruction,
            )
            user_content = base_msg + f"\n\n{feedback}"
            raw_text = call_claude(api_key, system_blocks, user_content, max_tokens_override=max_tokens)
            tsx_raw = _parse_single_variant_response(raw_text)
            if tsx_raw is None:
                raise RuntimeError(f"Variant {n}: re-generation failed")
            tsx = _strip_tsx_fences(tsx_raw.strip())
            return _inject_logo_url(tsx, spec)

        if body.useCritic:
            variants, reasoning_list = _run_critic_audit(api_key, variants, spec, _regen_similar, competitor_dna=body.competitorDna)
        else:
            n = len(variants)
            reasoning_list = [{"reasoning": "", "conversion_drivers": []} for _ in range(n)]
        reasoning_strings = [r.get("reasoning", "") for r in reasoning_list]
        conversion_drivers = [r.get("conversion_drivers", []) for r in reasoning_list]
        return {"variants": variants, "source": "anthropic", "experienceLibrary": full_library, "reasoning": reasoning_strings, "conversionDrivers": conversion_drivers}

    # Initial or refinement-with-change-request: design brief then 4 variants.
    log.info("generate: path=refinement (brief + 4 variants)")
    change_request_str = (change_request or "").strip()
    is_initial_generation = not chosen_html and not change_request_str
    has_dna = bool(body.competitorDna)
    use_inspiration_structure_line = is_initial_generation and has_dna
    inspiration_modes: list[str] = []
    if is_initial_generation and has_dna:
        raw_modes = body.inspirationVariantModes
        if raw_modes and len(raw_modes) == VARIANT_COUNT and all(m in VALID_INSPIRATION_MODES for m in raw_modes):
            inspiration_modes = raw_modes[:VARIANT_COUNT]
        else:
            inspiration_modes = list(INSPIRATION_VARIANT_MODES_DEFAULT)

    experience_decayed = _apply_decay(effective_library)
    try:
        diversity_instruction_refinement = _get_diversity_instruction(api_key, spec, experience_decayed, 0)
    except Exception as e:
        log.warning("refinement diversity_instruction fallback: %s", e)
        diversity_instruction_refinement = ""
    try:
        raw_brief = call_claude(
            api_key,
            _get_refinement_system_blocks(diversity_instruction_refinement, target_component),
            build_refinement_user_message(
                spec, chosen_html, change_request, selected_variant_index, experience_decayed, diversity_instruction_refinement, target_component
            ),
        )
        refined_brief = _strip_leading_clarification(raw_brief)
    except RateLimitError as e:
        raise HTTPException(
            status_code=503,
            detail={"error": "rate_limit", "details": str(e), "retry_after": e.retry_after},
        ) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail={"error": "Refinement failed", "details": str(e)})

    if PACE_DELAY_SEC > 0:
        time.sleep(PACE_DELAY_SEC)

    def generate_one_variant(n: int) -> str:
        """Generate one variant (n in 1..VARIANT_COUNT). Returns TSX string or raises."""
        if PACE_DELAY_SEC > 0:
            time.sleep((n - 1) * PACE_DELAY_SEC)
        mode_instruction = _inspiration_mode_instruction(inspiration_modes[n - 1]) if n <= len(inspiration_modes) else ""
        system_blocks = _get_single_variant_system_blocks(
            prompt_id, n, diversity_instruction_refinement, target_component,
            competitor_dna=body.competitorDna, competitor_dna_md=body.competitorDnaMd,
            use_inspiration_structure_line=use_inspiration_structure_line,
        )
        user_content = build_single_variant_user_message(
            refined_brief, n, chosen_html, change_request, selected_variant_index, experience_decayed,
            diversity_instruction_refinement, spec, target_component,
            inspiration_mode_instruction=mode_instruction,
        )
        raw_text = call_claude(
            api_key,
            system_blocks,
            user_content,
            max_tokens_override=max_tokens,
        )

        tsx_raw = None
        try:
            parsed = json.loads(raw_text.strip())
            if isinstance(parsed.get("tsx"), str):
                tsx_raw = parsed["tsx"]
        except (json.JSONDecodeError, TypeError):
            tsx_raw = _parse_single_variant_response(raw_text)

        if tsx_raw is None:
            raise RuntimeError(f"Variant {n}: Claude did not return valid TSX")

        tsx = _strip_tsx_fences(tsx_raw.strip())
        if _validate_tsx_variant(tsx):
            return tsx

        raise RuntimeError(f"Variant {n}: invalid or truncated TSX")

    variants = [None] * VARIANT_COUNT
    with ThreadPoolExecutor(max_workers=VARIANT_COUNT) as executor:
        future_to_n = {
            executor.submit(generate_one_variant, n): n
            for n in range(1, VARIANT_COUNT + 1)
        }
        for future in as_completed(future_to_n):
            n = future_to_n[future]
            try:
                variants[n - 1] = future.result()
            except RateLimitError as e:
                raise HTTPException(
                    status_code=503,
                    detail={"error": "rate_limit", "details": str(e), "retry_after": e.retry_after},
                ) from e
            except Exception as e:
                raise HTTPException(
                    status_code=502,
                    detail={"error": "Generation failed", "details": str(e), "variantIndex": n},
                )

    experience_lib = effective_library
    log.info("generate: refinement path done, variants=%s", len(variants))
    variants = [_inject_logo_url(v, spec) if v else v for v in variants]

    # Critic Agent: audit and auto-fix
    def _regen_refinement(n: int, feedback: str) -> str:
        mode_instruction = _inspiration_mode_instruction(inspiration_modes[n - 1]) if n <= len(inspiration_modes) else ""
        system_blocks = _get_single_variant_system_blocks(
            prompt_id, n, diversity_instruction_refinement, target_component,
            competitor_dna=body.competitorDna, competitor_dna_md=body.competitorDnaMd,
            use_inspiration_structure_line=use_inspiration_structure_line,
        )
        base_msg = build_single_variant_user_message(
            refined_brief, n, chosen_html, change_request, selected_variant_index, experience_decayed,
            diversity_instruction_refinement, spec, target_component,
            inspiration_mode_instruction=mode_instruction,
        )
        user_content = base_msg + f"\n\n{feedback}"
        raw_text = call_claude(api_key, system_blocks, user_content, max_tokens_override=max_tokens)
        tsx_raw = _parse_single_variant_response(raw_text)
        if tsx_raw is None:
            raise RuntimeError(f"Variant {n}: re-generation failed")
        tsx = _strip_tsx_fences(tsx_raw.strip())
        return _inject_logo_url(tsx, spec)

    if body.useCritic:
        variants, reasoning_list = _run_critic_audit(api_key, variants, spec, _regen_refinement, competitor_dna=body.competitorDna)
    else:
        n = len(variants)
        reasoning_list = [{"reasoning": "", "conversion_drivers": []} for _ in range(n)]
    reasoning_strings = [r.get("reasoning", "") for r in reasoning_list]
    conversion_drivers = [r.get("conversion_drivers", []) for r in reasoning_list]
    return {"variants": variants, "source": "anthropic", "experienceLibrary": experience_lib, "reasoning": reasoning_strings, "conversionDrivers": conversion_drivers}


@app.get("/experience-library")
def get_experience_library(format: str = ""):
    """Return the default (pre-built) experience library for session start.
    Accepts optional ?format=md to also return experienceLibraryMd (markdown bullets) for frontend.
    """
    library = _get_default_experience_library()
    out: dict = {"experienceLibrary": library}
    if format.strip().lower() == "md":
        out["experienceLibraryMd"] = "\n".join(f"• {item}" for item in library)
    return out


# --- Beacon (Supabase): CTA-only (button_click) → cta_events ----------------
@app.post("/beacon")
def beacon(body: BeaconBody):
    """Record CTA (button) click into Supabase cta_events. Config from backend .env. Only button_click accepted."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=503, detail="Analytics not configured (SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY in .env)")
    if body.event != "button_click":
        raise HTTPException(status_code=400, detail="event must be button_click (CTA only)")
    if not (body.repo_full_name or "").strip() or not (body.layer or "").strip() or not (body.variant_id or "").strip():
        raise HTTPException(status_code=400, detail="repo_full_name, layer, and variant_id are required")
    row = {
        "repo_full_name": (body.repo_full_name or "").strip(),
        "layer": (body.layer or "").strip(),
        "variant_id": (body.variant_id or "").strip(),
        "cta_label": (body.cta_label or "").strip() or None,
        "cta_id": (body.cta_id or "").strip() or None,
        "occurred_at": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
    }
    url = f"{SUPABASE_URL}/rest/v1/cta_events"
    with httpx.Client() as client:
        r = client.post(
            url,
            json=row,
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            timeout=10.0,
        )
    if r.status_code >= 400:
        log.warning("beacon Supabase insert failed: %s %s", r.status_code, r.text)
        raise HTTPException(status_code=500, detail="Analytics write failed")
    return {"ok": True}


# --- Analytics (Supabase): cta_by_variant for bot / dashboard ------------------
@app.get("/analytics")
def analytics(repo: str = "", layer: str = ""):
    """Query CTA clicks by variant (repo + optional layer). Reads from cta_by_variant."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=503, detail="Analytics not configured (SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY in .env)")
    if not (repo or "").strip():
        raise HTTPException(status_code=400, detail="Query param repo is required (e.g. ?repo=owner/name)")
    url = f"{SUPABASE_URL}/rest/v1/cta_by_variant"
    params: dict[str, str] = {
        "repo_full_name": f"eq.{repo.strip()}",
        "select": "repo_full_name,layer,variant_id,cta_clicks",
    }
    if (layer or "").strip():
        params["layer"] = f"eq.{layer.strip()}"
    with httpx.Client() as client:
        r = client.get(
            url,
            params=params,
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                "Accept": "application/json",
            },
            timeout=10.0,
        )
    if r.status_code >= 400:
        log.warning("analytics Supabase query failed: %s %s", r.status_code, r.text)
        raise HTTPException(status_code=500, detail="Analytics query failed")
    return {"data": r.json()}


def _analyze_variant_structure(tsx: str) -> dict:
    """Run regex analyzer on variant TSX: sections, CTAs, Tailwind colors, fonts, responsive/animated flags, line count."""
    text = (tsx or "").strip()
    sections_found: list[str] = []
    for label in ("Navigation", "Hero", "Features", "Testimonials", "Social Proof", "Pricing", "FAQ", "Footer"):
        if re.search(rf"\b{re.escape(label)}\b", text, re.IGNORECASE):
            sections_found.append(label)
    # CTA-like text: button children, links
    cta_labels: list[str] = []
    for m in re.finditer(r">\s*([^<{]+?)\s*</(?:button|a)\s*>", text):
        label = m.group(1).strip()
        if label and len(label) < 80 and label not in cta_labels:
            cta_labels.append(label)
    for m in re.finditer(r'["\']([^"\']{2,50})["\']\s*[}>].*?(?:button|Button|CTA)', text, re.IGNORECASE | re.DOTALL):
        label = m.group(1).strip()
        if label and label not in cta_labels:
            cta_labels.append(label)
    # Dominant Tailwind colors (first few)
    color_classes: list[str] = []
    for m in re.finditer(r"\b(bg|text|border)-([a-z0-9\-]+?)(?:\s|\)|\"|')", text):
        full = f"{m.group(1)}-{m.group(2)}"
        if full not in color_classes and len(color_classes) < 12:
            color_classes.append(full)
    # Font imports
    font_imports: list[str] = []
    if "next/font" in text:
        font_imports.append("next/font")
    for m in re.finditer(r"@import\s+[\"']([^\"']+)[\"']", text):
        font_imports.append(m.group(1).strip()[:60])
    # Responsive / animated
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


class AnalyzeVariantsBody(BaseModel):
    variants: list[str] = []


@app.post("/analyze-variants")
def analyze_variants(body: AnalyzeVariantsBody):
    """Accept { variants: string[] }, run _analyze_variant_structure on each TSX; return analysis list."""
    if not body.variants:
        return {"analyses": []}
    analyses = [_analyze_variant_structure(v) for v in body.variants]
    return {"analyses": analyses}


@app.get("/dashboard-data")
def dashboard_data(repo: str = ""):
    """Query cta_by_variant + cta_events for repo; return structured data for dashboard (KPIs, win rates, timeline)."""
    repo = (repo or "").strip()
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return {
            "variants": [],
            "totalClicks": 0,
            "topVariantId": None,
            "events": [],
            "error": "Analytics not configured",
        }
    if not repo:
        return {"variants": [], "totalClicks": 0, "topVariantId": None, "events": []}
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Accept": "application/json",
    }
    # cta_by_variant
    url_variant = f"{SUPABASE_URL}/rest/v1/cta_by_variant"
    params_variant = {"repo_full_name": f"eq.{repo}", "select": "repo_full_name,layer,variant_id,cta_clicks"}
    with httpx.Client() as client:
        rv = client.get(url_variant, params=params_variant, headers=headers, timeout=10.0)
        if rv.status_code >= 400:
            log.warning("dashboard-data cta_by_variant failed: %s %s", rv.status_code, rv.text)
            return {"variants": [], "totalClicks": 0, "topVariantId": None, "events": [], "error": "Analytics query failed"}
        raw = rv.json()
        rows = raw if isinstance(raw, list) else []
        total_clicks = sum((r.get("cta_clicks") or 0) for r in rows)
        variants_out: list[dict] = []
        for r in rows:
            clicks = r.get("cta_clicks") or 0
            share = round(clicks / total_clicks * 100, 1) if total_clicks else 0.0
            variants_out.append({
                "variant_id": r.get("variant_id"),
                "layer": r.get("layer"),
                "cta_clicks": clicks,
                "share_percent": share,
            })
        variants_out.sort(key=lambda x: x["cta_clicks"], reverse=True)
        for i, v in enumerate(variants_out):
            v["rank"] = i + 1
        top_variant_id = variants_out[0].get("variant_id") if variants_out else None
    # cta_events (recent for timeline)
    url_events = f"{SUPABASE_URL}/rest/v1/cta_events"
    params_events = {
        "repo_full_name": f"eq.{repo}",
        "select": "id,variant_id,cta_label,cta_id,occurred_at",
        "order": "occurred_at.desc",
        "limit": "100",
    }
    with httpx.Client() as client:
        re_ = client.get(url_events, params=params_events, headers=headers, timeout=10.0)
        events_list: list[dict] = []
        if re_.status_code < 400:
            raw = re_.json()
            events_list = raw if isinstance(raw, list) else []
        else:
            log.warning("dashboard-data cta_events failed: %s %s", re_.status_code, re_.text)
    return {
        "variants": variants_out,
        "totalClicks": total_clicks,
        "topVariantId": top_variant_id,
        "events": events_list,
    }


# --- GitHub OAuth: exchange code for access token -----------------------------
GITHUB_CLIENT_ID = (os.environ.get("GITHUB_CLIENT_ID") or "").strip()
GITHUB_CLIENT_SECRET = (os.environ.get("GITHUB_CLIENT_SECRET") or "").strip()


@app.post("/github-oauth-exchange")
def github_oauth_exchange(body: GitHubOAuthExchangeBody):
    """Exchange GitHub OAuth code for access token. Requires GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET in .env."""
    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        raise HTTPException(status_code=503, detail="GitHub OAuth not configured (GITHUB_CLIENT_ID / GITHUB_CLIENT_SECRET)")
    code = (body.code or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="code is required")
    payload: dict[str, str] = {
        "client_id": GITHUB_CLIENT_ID,
        "client_secret": GITHUB_CLIENT_SECRET,
        "code": code,
    }
    if (body.redirect_uri or "").strip():
        payload["redirect_uri"] = body.redirect_uri.strip()
    with httpx.Client(timeout=15.0) as client:
        r = client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json=payload,
        )
    if r.status_code >= 400:
        log.warning("github oauth exchange: %s %s", r.status_code, r.text)
        raise HTTPException(status_code=502, detail="GitHub OAuth exchange failed")
    data = r.json()
    access_token = data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail=data.get("error_description", "No access_token in response"))
    return {"access_token": access_token}


# --- Export bundle and create repo (GitHub OAuth) -----------------------------
def _github_create_repo(access_token: str, repo_name: str) -> str:
    """Create a new repo under the authenticated user. Returns full name (owner/name)."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=30.0) as client:
        r = client.get("https://api.github.com/user", headers=headers)
        r.raise_for_status()
        user = r.json()
        owner = user.get("login")
        if not owner:
            raise RuntimeError("Could not get GitHub user login")
        if "/" in repo_name.strip():
            full_name = repo_name.strip()
            owner, name = full_name.split("/", 1)
        else:
            name = repo_name.strip()
            full_name = f"{owner}/{name}"
        r = client.post(
            "https://api.github.com/user/repos",
            headers=headers,
            json={"name": name, "private": False, "auto_init": False},
        )
        if r.status_code == 422:
            body_resp = r.json()
            if "name already exists" in (body_resp.get("message") or "").lower():
                raise RuntimeError(f"Repo {full_name} already exists; choose a different repo name")
            raise RuntimeError(body_resp.get("message", "Cannot create repo"))
        r.raise_for_status()
        created = r.json()
        return created.get("full_name") or full_name


def _github_push_files(access_token: str, full_name: str, files: dict[str, str]) -> None:
    """Push files to an existing repo via Contents API."""
    owner, name = full_name.split("/", 1)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=30.0) as client:
        for path, content in files.items():
            payload = {
                "message": f"Add {path}",
                "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            }
            r = client.put(
                f"https://api.github.com/repos/{owner}/{name}/contents/{path}",
                headers=headers,
                json=payload,
            )
            if r.status_code not in (200, 201):
                log.warning("github put file %s: %s %s", path, r.status_code, r.text)
                r.raise_for_status()


@app.post("/build-export-bundle")
def build_export_bundle(body: BuildExportBundleBody):
    """Build a Vercel-ready Next.js bundle (random 1-4 variant + 4 variant files). Returns file map."""
    if len(body.variant_tsx_list) != 4:
        raise HTTPException(status_code=400, detail="variant_tsx_list must have exactly 4 elements")
    beacon_url = BEACON_BASE_URL or "http://localhost:8000"
    try:
        files = build_vercel_bundle(
            body.variant_tsx_list,
            body.repo_full_name.strip(),
            body.layer.strip(),
            beacon_url,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"files": files}


@app.post("/create-repo-and-push")
def create_repo_and_push(body: CreateRepoAndPushBody):
    """Create a new GitHub repo under the user and push the Vercel-ready bundle. Uses OAuth token."""
    token = (body.github_access_token or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="github_access_token is required")
    if len(body.variant_tsx_list) != 4:
        raise HTTPException(status_code=400, detail="variant_tsx_list must have exactly 4 elements")
    beacon_url = BEACON_BASE_URL or "http://localhost:8000"
    try:
        # Create repo first to get full_name (owner/name)
        full_name = _github_create_repo(token, body.repo_name.strip())
    except RuntimeError as e:
        if "already exists" in str(e):
            raise HTTPException(status_code=422, detail=str(e)) from e
        raise HTTPException(status_code=502, detail=str(e)) from e
    except httpx.HTTPStatusError as e:
        log.warning("github create failed: %s %s", e.response.status_code, e.response.text)
        if e.response.status_code == 401:
            raise HTTPException(status_code=401, detail="Invalid or expired GitHub token") from e
        raise HTTPException(status_code=502, detail=f"GitHub API error: {e.response.text}") from e

    try:
        files = build_vercel_bundle(
            body.variant_tsx_list,
            full_name,
            (body.layer or "1").strip(),
            beacon_url,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    try:
        _github_push_files(token, full_name, files)
    except httpx.HTTPStatusError as e:
        log.warning("github push failed: %s %s", e.response.status_code, e.response.text)
        raise HTTPException(status_code=502, detail=f"GitHub push error: {e.response.text}") from e
    return {"repo_full_name": full_name, "ok": True}


@app.post("/webhook/github")
def github_webhook():
    """Stub for GitHub App webhook URL (required by GitHub). Returns 200; no events subscribed."""
    return {"ok": True}


class DeployBody(BaseModel):
    tsx: str
    reasoning: str = ""
    conversionDrivers: list[str] = []
    companyName: str = ""
    variantIndex: int = 0


@app.post("/deploy")
def deploy(body: DeployBody):
    """Accept a selected variant + reasoning for deployment. Forwards to sync agent on port 4000 if configured."""
    log.info("deploy: company=%r variant=%d reasoning=%r drivers=%s", body.companyName, body.variantIndex, body.reasoning[:80], body.conversionDrivers)
    sync_agent_url = os.environ.get("SYNC_AGENT_URL", "").strip().rstrip("/")
    if sync_agent_url:
        payload = {
            "tsx": body.tsx,
            "reasoning": body.reasoning,
            "conversionDrivers": body.conversionDrivers,
            "companyName": body.companyName,
            "variantIndex": body.variantIndex,
        }
        try:
            with httpx.Client(timeout=30.0) as client:
                r = client.post(f"{sync_agent_url}/deploy", headers={"Content-Type": "application/json"}, json=payload)
                if r.status_code < 400:
                    log.info("deploy: forwarded to sync agent, status=%d", r.status_code)
                    return {"ok": True, "forwarded": True, "agentStatus": r.status_code}
                log.warning("deploy: sync agent returned %d: %s", r.status_code, r.text[:200])
        except Exception as e:
            log.warning("deploy: could not reach sync agent: %s", e)
    return {
        "ok": True,
        "forwarded": False,
        "companyName": body.companyName,
        "variantIndex": body.variantIndex,
        "reasoning": body.reasoning,
        "conversionDrivers": body.conversionDrivers,
    }


@app.get("/health")
def health():
    api_key_set = bool((os.environ.get("ANTHROPIC_API_KEY") or "").strip())
    return {"status": "ok", "skill_loaded": bool(FRONTEND_DESIGN_SKILL), "api_key_set": api_key_set}
