"""
Training-Free GRPO–style pipeline to build the CTA alignment experience library.

Run from python-agent (with venv activated):
  python scripts/build_cta_experience_library.py

Requires: ANTHROPIC_API_KEY, Supabase (SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY) and
GitHub (GITHUB_TOKEN or App) so cta_by_variant and variant files can be fetched.
Uses Supabase cta_by_variant + GitHub variant files to form queries. For each query,
runs G rollouts (Claude with temperature), scores with LLM, extracts semantic
group advantage, and merges experiences into the library. Repeats for E epochs
and saves experience_library_cta.json. If no queries are available (e.g. no
repo/layer with 2+ variants), leaves the existing library unchanged and saves it.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Run from python-agent; parent is python-agent
_AGENT_DIR = Path(__file__).resolve().parent.parent
if str(_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR))

from config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    EXPERIENCE_LIBRARY_CTA_PATH_RESOLVED,
    REPO_ALLOW_LIST,
)
from main import (
    FRONTEND_DESIGN_SKILL,
    _call_claude_align_cta,
    _describe_cta_structure,
    _fetch_variant_files,
    _get_cta_by_variant,
)

# Pipeline constants (paper-aligned: small group, few epochs)
GROUP_SIZE = 3
EPOCHS = 2
EXPERIENCE_EXCERPT_MAX = 6000
EXPERIENCE_ITEMS_MAX = 15
EXPERIENCE_DECAY_MAX_ITEMS = 50
ROLLOUT_TEMPERATURE = 0.7
REWARD_MIN_VARIANCE = 0.01


def _load_library() -> list[str]:
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


def _save_library(library: list[str]) -> None:
    path = EXPERIENCE_LIBRARY_CTA_PATH_RESOLVED or (_AGENT_DIR / "experience_library_cta.json")
    path = Path(str(path)).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(library, indent=2), encoding="utf-8")


def _call_claude(system: str, user: str, max_tokens: int = 4096, temperature: float = 0.0) -> str:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    import anthropic
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        temperature=temperature,
    )
    text = ""
    for b in msg.content:
        if hasattr(b, "text"):
            text += b.text
    return text.strip()


def _score_rollout(best_cta_description: str, rewritten_tsx: str) -> float:
    """LLM scores 0–1 for CTA alignment and code quality."""
    system = (
        "You score a rewritten landing variant TSX for CTA alignment and code quality. "
        "Output only a single number between 0 and 1. 1 = excellent alignment and valid TSX; 0 = poor."
    )
    user = (
        f"Target CTA structure:\n{best_cta_description[:2000]}\n\n"
        f"Rewritten TSX (excerpt):\n{(rewritten_tsx or '')[:EXPERIENCE_EXCERPT_MAX]}\n\n"
        "Output only a number 0.0 to 1.0."
    )
    raw = _call_claude(system, user, max_tokens=64)
    s = re.sub(r"[^\d.]", "", raw.strip())
    try:
        return max(0.0, min(1.0, float(s))) if s else 0.5
    except ValueError:
        return 0.5


def _summarize_rollout(tsx_excerpt: str, reward: float) -> str:
    system = (
        "Summarize this CTA-alignment rollout for group-advantage analysis. "
        "Output 2–4 sentences: what was changed (placement, count, prominence) and outcome."
    )
    user = f"Reward: {reward:.2f}\n\nVariant TSX (excerpt):\n{tsx_excerpt[:EXPERIENCE_EXCERPT_MAX]}\n\nOutput a short summary."
    return _call_claude(system, user, max_tokens=512)


def _parse_experiences_from_response(response: str) -> list[str]:
    match = re.search(r"<Experiences>\s*([\s\S]*?)\s*</Experiences>", response, re.IGNORECASE)
    if match:
        block = match.group(1).strip()
        items: list[str] = []
        for line in block.split("\n"):
            line = line.strip()
            if not line:
                continue
            part = re.sub(r"^\d+[.)]\s*", "", line).strip()
            if part and len(part) > 10:
                items.append(part)
                if len(items) >= EXPERIENCE_ITEMS_MAX:
                    return items
        return items[:EXPERIENCE_ITEMS_MAX]
    # Fallback: bullet lines
    lines = [ln.strip() for ln in response.strip().split("\n") if ln.strip()]
    out: list[str] = []
    for ln in lines:
        for part in re.split(r"[\•\-]\s+", ln):
            part = part.strip()
            if part and len(part) > 10:
                out.append(part)
                if len(out) >= EXPERIENCE_ITEMS_MAX:
                    return out
    return out[:EXPERIENCE_ITEMS_MAX]


def _group_advantage_extraction(
    best_cta_description: str,
    summarized_rollouts: list[tuple[str, float]],
    experience_library: list[str],
) -> list[str]:
    system = (
        "You extract group-relative semantic advantage from CTA alignment rollouts. "
        "Compare the summarized rollouts and rewards; output generalizable lessons for future CTA alignment. "
        "Output <Experiences>...</Experiences> with numbered items (short, actionable)."
    )
    attempts_block = "\n\n".join(
        f"Attempt {i + 1} (Reward {r:.2f}):\n{s}" for i, (s, r) in enumerate(summarized_rollouts)
    )
    experiences_block = (
        "\n".join(f"[{i}]. {e}" for i, e in enumerate(experience_library[:EXPERIENCE_DECAY_MAX_ITEMS]))
        if experience_library
        else "(none yet)"
    )
    user = (
        f"Target CTA structure:\n{best_cta_description[:2000]}\n\n"
        f"Summarized rollouts:\n{attempts_block}\n\n"
        f"Current experiential knowledge E:\n{experiences_block}\n\n"
        "Output your analysis and the <Experiences>...</Experiences> block."
    )
    raw = _call_claude(
        FRONTEND_DESIGN_SKILL + "\n\n---\n\n" + system,
        user,
        max_tokens=2048,
    )
    return _parse_experiences_from_response(raw)


def _group_experience_update(existing_library: list[str], new_experiences: list[str]) -> list[str]:
    if not new_experiences:
        return existing_library or []
    if not existing_library:
        return new_experiences[:EXPERIENCE_DECAY_MAX_ITEMS]
    system = (
        "Merge new experiences with existing ones. For each new experience, output one operation: "
        "ADD (new content), UPDATE (refine existing; set id to index), DELETE (id to remove), NONE (redundant). "
        "Output only a valid JSON array: [{\"operation\": \"ADD\"|\"UPDATE\"|\"DELETE\"|\"NONE\", \"id\": number|null, \"content\": \"string\"}]. No markdown."
    )
    existing_formatted = "\n".join([f"[{i}]. {e}" for i, e in enumerate(existing_library)])
    new_formatted = "\n".join([f"- {e}" for e in new_experiences])
    user = f"Existing experiences:\n{existing_formatted}\n\nNew experiences:\n{new_formatted}\n\nOutput the JSON array."
    raw = _call_claude(system, user, max_tokens=2048)
    try:
        json_str = raw.strip()
        if "```json" in json_str:
            json_str = json_str.split("```json")[-1].split("```")[0].strip()
        elif "```" in json_str:
            parts = json_str.split("```")
            if len(parts) >= 2:
                json_str = parts[1].split("```")[0].strip()
        operations = json.loads(json_str)
        if not isinstance(operations, list):
            return (new_experiences + existing_library)[:EXPERIENCE_DECAY_MAX_ITEMS]
    except (json.JSONDecodeError, TypeError):
        return (new_experiences + existing_library)[:EXPERIENCE_DECAY_MAX_ITEMS]
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


def _build_queries() -> list[tuple[str, str, str, str, str, str]]:
    """Returns list of (repo, layer, best_id, best_cta_description, underperforming_id, underperforming_tsx)."""
    rows = _get_cta_by_variant()
    if not rows:
        return []
    from collections import defaultdict
    by_repo_layer: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        repo = (r.get("repo_full_name") or "").strip()
        layer = (r.get("layer") or "").strip()
        if repo and layer:
            by_repo_layer[(repo, layer)].append(r)
    queries: list[tuple[str, str, str, str, str, str]] = []
    for (repo, layer), group in by_repo_layer.items():
        if REPO_ALLOW_LIST and repo not in REPO_ALLOW_LIST:
            continue
        variant_clicks = {r["variant_id"]: int(r.get("cta_clicks") or 0) for r in group}
        if len(variant_clicks) < 2:
            continue

        def to_file_key(vid: str) -> str:
            vid = (vid or "").strip()
            if vid.startswith("variant-"):
                return vid
            return f"variant-{vid}" if (isinstance(vid, str) and vid.isdigit()) else vid

        normalized = {to_file_key(k): v for k, v in variant_clicks.items()}
        sorted_variants = sorted(normalized.items(), key=lambda x: -x[1])
        best_id = sorted_variants[0][0]
        try:
            files = _fetch_variant_files(repo)
        except Exception:
            continue
        if best_id not in files:
            continue
        best_tsx = files[best_id]
        best_cta_description = _describe_cta_structure(best_tsx)
        for vid, _ in sorted_variants[1:]:
            if vid not in files:
                continue
            queries.append((repo, layer, best_id, best_cta_description, vid, files[vid]))
    return queries


def run_pipeline(epochs: int = EPOCHS, group_size: int = GROUP_SIZE) -> list[str]:
    library = _load_library()
    queries = _build_queries()
    if not queries:
        print(
            "No queries from cta_by_variant (need Supabase + 2+ variants per repo/layer). Returning existing library."
        )
        return library
    print(f"Loaded {len(library)} experiences; {len(queries)} queries; {epochs} epochs; group_size={group_size}")
    for epoch in range(epochs):
        print(f"Epoch {epoch + 1}/{epochs}")
        for q_idx, (repo, layer, best_id, best_cta_description, under_id, under_tsx) in enumerate(queries):
            rollouts: list[str] = []
            for _ in range(group_size):
                try:
                    out = _call_claude_align_cta(
                        FRONTEND_DESIGN_SKILL,
                        best_cta_description,
                        under_tsx,
                        best_id,
                        experience_library=library,
                        temperature=ROLLOUT_TEMPERATURE,
                    )
                    if out:
                        rollouts.append(out)
                except Exception as e:
                    print(f"  Rollout failed query {q_idx+1} {under_id}: {e}")
            if len(rollouts) < 2:
                continue
            rewards = [_score_rollout(best_cta_description, r) for r in rollouts]
            import statistics
            if statistics.stdev(rewards) < REWARD_MIN_VARIANCE:
                continue
            summarized = [
                (_summarize_rollout(r[:EXPERIENCE_EXCERPT_MAX], rewards[i]), rewards[i])
                for i, r in enumerate(rollouts)
            ]
            new_exp = _group_advantage_extraction(best_cta_description, summarized, library)
            if new_exp:
                library = _group_experience_update(library, new_exp)
                print(f"  Query {q_idx+1} ({under_id}): {len(new_exp)} new experiences -> library size {len(library)}")
    return library


def main() -> None:
    library = run_pipeline()
    _save_library(library)
    out_path = EXPERIENCE_LIBRARY_CTA_PATH_RESOLVED or (_AGENT_DIR / "experience_library_cta.json")
    print(f"Saved {len(library)} experiences to {out_path}")


if __name__ == "__main__":
    main()
