"""
Seed the CTA experience library with real CTA patterns so Claude's autonomous
adjustments are informed rather than random. Closes the self-learning loop by
giving the experience library a conversion-focused prior.

Run from backend directory:
  cd landright-app/backend && python scripts/build_cta_experience_library.py

Reads experience_library_default.json, appends new CTA patterns (urgency, social
proof, pricing anchors, Whop-specific), writes back. Skips items that are already
present (by normalized substring match).
"""
from __future__ import annotations

import json
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
LIBRARY_PATH = BACKEND_DIR / "experience_library_default.json"

# Real CTA patterns: urgency, social proof, pricing anchors, Whop-specific.
# Each string is one experience item (same format as experience_library_default.json).
CTA_SEED_ITEMS = [
    # Urgency triggers
    "Urgency in CTAs: Time-bound or scarcity language ('Limited spots', 'Join 500+', 'Only X left') increases intent when the offer is clear and the constraint feels genuine; avoid fake countdowns.",
    "Soft urgency over hard pressure: Phrases like 'Get started today' or 'Start your free trial' convert better than aggressive countdowns when the audience is considered; reserve strong scarcity for true limits.",
    "Deadline and availability: When there is a real cap or date, state it near the CTA (e.g. 'Enrollment closes Friday') so the CTA feels justified and not gimmicky.",
    # Social proof
    "Social proof next to the CTA: User counts, logos, or one short testimonial near the primary button increase trust and conversion without cluttering the main action.",
    "Social proof placement: Place testimonials or trust badges above or beside the hero CTA, not only in a separate section; proximity to the CTA reinforces the decision.",
    "Numbers that build trust: Specific numbers ('2,400+ creators', 'Used by teams at X and Y') near the CTA outperform vague claims and help justify the click.",
    # Pricing anchors
    "Pricing anchors near the CTA: Showing a higher price or plan next to the main offer improves perceived value when the comparison is clear and the primary CTA is still the focal action.",
    "Value framing: Frame the CTA around outcome or savings (e.g. 'Start free' or 'Save $X') when the numbers are real; anchors work when they are believable.",
    "Tier clarity: For multiple plans, one primary CTA (e.g. 'Start with Pro') with a short comparison nearby outperforms several equal-weight buttons.",
    # Whop-specific and creator/membership
    "Whop and creator products: Emphasize community size, creator name, and what they get (access, course, circle); CTAs like 'Get access' or 'Join the community' outperform generic 'Sign up'.",
    "Membership and gated content: Lead with the benefit of joining (e.g. 'Join 1,200+ members') and use a single clear CTA; avoid stacking multiple sign-up buttons.",
    "Creator-led landing pages: Pair the creator's face or name with the main CTA so the offer feels personal; 'Join [Creator]' or 'Get [Creator]'s course' aligns with how Whop and similar audiences decide.",
]

def _load_library() -> list[str]:
    if not LIBRARY_PATH.exists():
        return []
    try:
        data = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
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
    LIBRARY_PATH.write_text(json.dumps(library, indent=2), encoding="utf-8")


def _normalize(s: str) -> str:
    return " ".join(s.lower().split())


def _is_already_present(item: str, existing: list[str]) -> bool:
    n = _normalize(item)
    for e in existing:
        if n in _normalize(e) or _normalize(e) in n:
            return True
    return False


def main() -> None:
    existing = _load_library()
    added: list[str] = []
    for item in CTA_SEED_ITEMS:
        if not item.strip():
            continue
        if _is_already_present(item, existing):
            continue
        existing.append(item)
        added.append(item)
    if added:
        _save_library(existing)
        print(f"Appended {len(added)} CTA experience items to {LIBRARY_PATH}")
        for i, a in enumerate(added, 1):
            preview = a[:70] + "..." if len(a) > 70 else a
            print(f"  + {i}. {preview}")
    else:
        print("No new items to add; library already contains equivalent CTA patterns.")


if __name__ == "__main__":
    main()
