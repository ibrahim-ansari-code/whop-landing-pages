"""
Training-Free GRPO pipeline to extend experience_library_default.json with CTA positioning experiences.

Run from backend directory (with venv if used):
  cd landright-app/backend && python scripts/build_experience_library_cta_positioning.py

Requires: ANTHROPIC_API_KEY. Uses a fixed set of minimal design specs (no Supabase/GitHub).
Loads experience_library_default.json, runs 2 epochs: for each spec, G rollouts (generate one variant
with CTA positioning emphasis), LLM score for CTA impact, summarize, extract experiences, merge.
Writes updated library back to experience_library_default.json.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env", override=True)

from main import (
    DesignSpec,
    WebsiteInformation,
    FRONTEND_DESIGN_SKILL,
    EXPERIENCE_DECAY_MAX_ITEMS,
    EXPERIENCE_EXCERPT_MAX,
    SINGLE_VARIANT_MAX_TOKENS,
    call_claude,
    _get_similar_variant_system_blocks,
    build_similar_variant_user_message,
    _group_advantage_extraction,
    _group_experience_update,
    _parse_experiences_from_response,
    _strip_tsx_fences,
)

GROUP_SIZE = 3
EPOCHS = 2
EXPERIENCE_ITEMS_MAX = 15
REWARD_MIN_VARIANCE = 0.01
CTA_BRIEF = (
    "Emphasize CTA positioning: vary where and how CTAs appear (hero vs mid vs footer), "
    "their prominence and count. Make changes that are noticeable and impact CTA visibility and conversion."
)
CTA_DIVERSITY = "Focus on CTA placement and prominence variation across variants (hero, mid, footer; number and size of CTAs)."


def _load_library() -> list[str]:
    path = BACKEND_DIR / "experience_library_default.json"
    if not path.exists():
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


def _save_library(library: list[str]) -> None:
    path = BACKEND_DIR / "experience_library_default.json"
    path.write_text(json.dumps(library, indent=2), encoding="utf-8")


def _build_specs() -> list[DesignSpec]:
    """Fixed set of minimal design specs for CTA positioning rollouts."""
    return [
        DesignSpec(
            websiteInformation=WebsiteInformation(
                name="SaaS Tool",
                tagline="Simplify your workflow",
                whatTheyDo="We help teams automate repetitive tasks and ship faster with a single dashboard.",
            ),
        ),
        DesignSpec(
            websiteInformation=WebsiteInformation(
                name="Design Studio",
                tagline="Brands that convert",
                whatTheyDo="We create landing pages and brand assets that drive signups and sales.",
            ),
        ),
    ]


def _generate_one_variant(
    api_key: str,
    spec: DesignSpec,
    experience_library: list[str],
    temperature: float = 0.7,
) -> str:
    """Generate one variant with CTA positioning emphasis. Returns TSX string."""
    experience_decayed = (experience_library or [])[:EXPERIENCE_DECAY_MAX_ITEMS]
    system_blocks = _get_similar_variant_system_blocks(
        CTA_BRIEF,
        experience_library_decayed=experience_decayed,
        similarity_round=0,
        diversity_instruction=CTA_DIVERSITY,
    )
    user_msg = build_similar_variant_user_message(
        CTA_BRIEF,
        spec,
        variant_index=1,
        experience_library_decayed=experience_decayed,
        similarity_round=0,
        diversity_instruction=CTA_DIVERSITY,
    )
    old_temp = os.environ.get("ANTHROPIC_TEMPERATURE")
    try:
        os.environ["ANTHROPIC_TEMPERATURE"] = str(temperature)
        raw = call_claude(
            api_key,
            system_blocks,
            user_msg,
            max_tokens_override=SINGLE_VARIANT_MAX_TOKENS,
        )
    finally:
        if old_temp is not None:
            os.environ["ANTHROPIC_TEMPERATURE"] = old_temp
        else:
            os.environ.pop("ANTHROPIC_TEMPERATURE", None)
    try:
        parsed = json.loads(raw.strip())
        if isinstance(parsed.get("tsx"), str):
            return _strip_tsx_fences(parsed["tsx"].strip())
    except (json.JSONDecodeError, TypeError):
        pass
    return _strip_tsx_fences(raw.strip())


def _score_cta_positioning(api_key: str, spec_json: str, tsx_excerpt: str) -> float:
    """LLM score 0-1 for CTA positioning impact and noticeable change."""
    system = (
        "You score a landing variant TSX for CTA positioning impact. "
        "Consider: placement (hero vs mid vs footer), prominence, number of CTAs, and whether the change is noticeable and likely to impact conversion. "
        "Output only a single number between 0 and 1. 1 = strong CTA positioning impact; 0 = minimal or no clear CTA focus."
    )
    user = (
        f"Spec (context):\n{spec_json[:1500]}\n\n"
        f"Variant TSX (excerpt):\n{tsx_excerpt[:EXPERIENCE_EXCERPT_MAX]}\n\n"
        "Output only a number 0.0 to 1.0."
    )
    raw = call_claude(api_key, system, user, max_tokens_override=64)
    s = re.sub(r"[^\d.]", "", raw.strip())
    try:
        return max(0.0, min(1.0, float(s))) if s else 0.5
    except ValueError:
        return 0.5


def _summarize_rollout(api_key: str, tsx_excerpt: str, reward: float) -> str:
    """Summarize rollout for group-advantage: what CTA choices were made and outcome."""
    system = (
        "Summarize this variant rollout for CTA positioning analysis. "
        "Output 2-4 sentences: where CTAs appear (hero/mid/footer), their prominence and count, and outcome (reward)."
    )
    user = f"Reward: {reward:.2f}\n\nVariant TSX (excerpt):\n{tsx_excerpt[:EXPERIENCE_EXCERPT_MAX]}\n\nOutput a short summary."
    return call_claude(api_key, system, user, max_tokens_override=512)


def run_pipeline(epochs: int = EPOCHS, group_size: int = GROUP_SIZE) -> list[str]:
    api_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        print("ANTHROPIC_API_KEY not set; skipping pipeline.")
        return _load_library()

    library = _load_library()
    specs = _build_specs()
    if not specs:
        print("No specs; exiting.")
        return library

    print(f"Loaded {len(library)} experiences; {len(specs)} specs; {epochs} epochs; group_size={group_size}")
    for epoch in range(epochs):
        print(f"Epoch {epoch + 1}/{epochs}")
        for spec_idx, spec in enumerate(specs):
            spec_json = spec.model_dump_json()
            rollouts: list[str] = []
            for _ in range(group_size):
                try:
                    tsx = _generate_one_variant(api_key, spec, library)
                    if tsx:
                        rollouts.append(tsx)
                except Exception as e:
                    print(f"  Rollout failed spec {spec_idx+1}: {e}")
            if len(rollouts) < 2:
                continue
            rewards = [_score_cta_positioning(api_key, spec_json, r) for r in rollouts]
            if sum((x - sum(rewards) / len(rewards)) ** 2 for x in rewards) / max(len(rewards), 1) < REWARD_MIN_VARIANCE ** 2:
                continue
            summarized = [
                (_summarize_rollout(api_key, r[:EXPERIENCE_EXCERPT_MAX], rewards[i]), rewards[i])
                for i, r in enumerate(rollouts)
            ]
            new_exp = _group_advantage_extraction(api_key, spec, summarized, library)
            if new_exp:
                library = _group_experience_update(api_key, library, new_exp)
                print(f"  Spec {spec_idx+1} ({spec.websiteInformation.name}): {len(new_exp)} new experiences -> library size {len(library)}")
    return library


def main() -> None:
    library = run_pipeline()
    _save_library(library)
    print(f"Saved {len(library)} experiences to {BACKEND_DIR / 'experience_library_default.json'}")


if __name__ == "__main__":
    main()
