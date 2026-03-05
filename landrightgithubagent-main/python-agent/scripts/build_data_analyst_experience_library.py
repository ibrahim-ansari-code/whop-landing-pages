"""
Training-Free GRPO pipeline to build the data analyst experience library.

Run from python-agent (with venv activated):
  python scripts/build_data_analyst_experience_library.py

Requires: ANTHROPIC_API_KEY, Supabase (SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY) and
GitHub (GITHUB_TOKEN or App) so cta_by_variant and variant files can be fetched.
For each (repo, layer) with 2+ variants: G rollouts = LLM decides RUN_ADJUST or SKIP with reason;
reward = ground truth (1 if best_clicks - second_clicks >= CTA_THRESHOLD else 0); summarize;
extract semantic advantage; merge into library. 2 epochs, save to experience_library_data_analyst.json.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_AGENT_DIR = Path(__file__).resolve().parent.parent
if str(_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR))

from config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    CTA_THRESHOLD,
    EXPERIENCE_LIBRARY_DATA_ANALYST_PATH_RESOLVED,
    REPO_ALLOW_LIST,
)
from main import (
    FRONTEND_DESIGN_SKILL,
    _describe_cta_structure,
    _fetch_variant_files,
    _get_cta_by_variant,
)

GROUP_SIZE = 3
EPOCHS = 2
EXPERIENCE_ITEMS_MAX = 15
EXPERIENCE_DECAY_MAX_ITEMS = 50
ROLLOUT_TEMPERATURE = 0.7
REWARD_MIN_VARIANCE = 0.01


def _load_library() -> list[str]:
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


def _save_library(library: list[str]) -> None:
    path = EXPERIENCE_LIBRARY_DATA_ANALYST_PATH_RESOLVED or (_AGENT_DIR / "experience_library_data_analyst.json")
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


def _run_rollout(
    variant_clicks_str: str,
    best_id: str,
    best_clicks: int,
    second_id: str,
    second_clicks: int,
    best_cta_desc: str,
    second_cta_desc: str,
    experience_library: list[str],
) -> str:
    """One data analyst rollout: decide whether to adjust, and how to change pages based on data."""
    experiences_block = ""
    if experience_library:
        bullets = "\n".join(f"• {e}" for e in experience_library[:20])
        experiences_block = "\n\nConsider this experiential knowledge:\n" + bullets
    system = (
        "You are a data analyst for a landing page A/B test. Given variant CTA click counts and CTA structure summaries, "
        "decide whether to run the CTA alignment pipeline (align underperforming variants to the best variant's CTA structure). "
        "If you recommend running it, also specify what should change in the underperforming pages based on the data (CTA placement/count/prominence). "
        "Output format:\n"
        "Decision: RUN_ADJUST or SKIP\n"
        "Update: comma-separated variant ids to update (or NONE)\n"
        "Plan: 2-4 short bullets describing what CTA changes to make, grounded in the best variant's CTA structure.\n"
        + experiences_block
    )
    user = (
        f"Variant click counts:\n{variant_clicks_str}\n\n"
        f"Best variant: {best_id} ({best_clicks} CTA clicks). CTA structure: {best_cta_desc}\n\n"
        f"Second variant: {second_id} ({second_clicks} CTA clicks). CTA structure: {second_cta_desc}\n\n"
        "Should we run the CTA alignment pipeline? Follow the required output format."
    )
    return _call_claude(system, user, max_tokens=512, temperature=ROLLOUT_TEMPERATURE)


def _parse_run_skip(response: str) -> bool:
    """True if model said RUN_ADJUST."""
    raw = (response or "").strip().upper()
    if "RUN_ADJUST" in raw:
        return True
    if "SKIP" in raw and "RUN_ADJUST" not in raw:
        return False
    return "RUN" in raw and "ADJUST" in raw


def _summarize_rollout(rollout_text: str, reward: float) -> str:
    system = (
        "Summarize this data analyst rollout for group-advantage analysis. "
        "Output 2-4 sentences: the decision (RUN_ADJUST or SKIP), what pages would be updated and how (CTA placement/count/prominence), and outcome (reward)."
    )
    user = f"Reward: {reward:.2f}\n\nRollout output:\n{rollout_text[:2000]}\n\nOutput a short summary."
    return _call_claude(system, user, max_tokens=512)


def _score_rollout_quality(
    rollout_text: str,
    best_cta_desc: str,
    second_cta_desc: str,
) -> float:
    """LLM scores 0–1 for actionable, data-grounded page-change guidance."""
    system = (
        "You score a data analyst recommendation for how to change landing page variants based on CTA click data. "
        "Score high when the output contains a clear Decision, a sensible Update set, and a specific Plan with actionable CTA placement/count/prominence changes grounded in the best variant's CTA structure. "
        "Score low when vague, not actionable, or not grounded in data. Output only a number 0.0 to 1.0."
    )
    user = (
        f"Best CTA structure:\n{(best_cta_desc or '')[:1200]}\n\n"
        f"Second CTA structure:\n{(second_cta_desc or '')[:1200]}\n\n"
        f"Recommendation:\n{(rollout_text or '')[:2000]}\n\n"
        "Output only a number 0.0 to 1.0."
    )
    raw = _call_claude(system, user, max_tokens=64)
    s = re.sub(r"[^\d.]", "", raw.strip())
    try:
        return max(0.0, min(1.0, float(s))) if s else 0.5
    except ValueError:
        return 0.5


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
    summarized_rollouts: list[tuple[str, float]],
    experience_library: list[str],
) -> list[str]:
    system = (
        "You extract group-relative semantic advantage from data analyst rollouts. "
        "Compare the summarized decisions and rewards; output generalizable lessons about how to read CTA metrics, when to run or skip alignment, and how to design page-change plans based on the data, "
        "without hard-coding specific CTA counts or layout patterns. "
        "Focus on meta-principles of analysis and adjustment, not a single \"optimal\" CTA configuration. "
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


def _build_queries() -> list[tuple[str, str, dict[str, int], str, int, str, int, str, str]]:
    """Returns list of (repo, layer, variant_clicks, best_id, best_clicks, second_id, second_clicks, best_cta_desc, second_cta_desc)."""
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
    queries: list[tuple[str, str, dict[str, int], str, int, str, int, str, str]] = []
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
        best_id, best_clicks = sorted_variants[0]
        second_id, second_clicks = sorted_variants[1]
        best_cta_desc = ""
        second_cta_desc = ""
        try:
            files = _fetch_variant_files(repo)
            if best_id in files:
                best_cta_desc = _describe_cta_structure(files[best_id])
            if second_id in files:
                second_cta_desc = _describe_cta_structure(files[second_id])
        except Exception:
            pass
        queries.append((repo, layer, variant_clicks, best_id, best_clicks, second_id, second_clicks, best_cta_desc, second_cta_desc))
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
        for q_idx, (repo, layer, variant_clicks, best_id, best_clicks, second_id, second_clicks, best_cta_desc, second_cta_desc) in enumerate(queries):
            variant_clicks_str = "\n".join(f"  {k}: {v} clicks" for k, v in sorted(variant_clicks.items()))
            should_adjust_truth = (best_clicks - second_clicks) >= CTA_THRESHOLD
            rollouts: list[str] = []
            for _ in range(group_size):
                try:
                    out = _run_rollout(
                        variant_clicks_str,
                        best_id,
                        best_clicks,
                        second_id,
                        second_clicks,
                        best_cta_desc,
                        second_cta_desc,
                        library,
                    )
                    if out:
                        rollouts.append(out)
                except Exception as e:
                    print(f"  Rollout failed query {q_idx+1} {repo}/{layer}: {e}")
            if len(rollouts) < 2:
                continue
            # Reward each rollout by whether its decision matches the proxy ground truth.
            rewards = []
            for r in rollouts:
                match = 1.0 if _parse_run_skip(r) == should_adjust_truth else 0.0
                quality = _score_rollout_quality(r, best_cta_desc, second_cta_desc)
                rewards.append(0.5 * match + 0.5 * quality)
            # Unlike math/web tasks in the paper, in this domain rewards can be low-variance for small groups.
            # We still extract experiences so the library can learn actionable page-change heuristics.
            summarized = [
                (_summarize_rollout(r[:2000], rewards[i]), rewards[i])
                for i, r in enumerate(rollouts)
            ]
            new_exp = _group_advantage_extraction(summarized, library)
            if new_exp:
                library = _group_experience_update(library, new_exp)
                print(f"  Query {q_idx+1} ({repo} {layer}): {len(new_exp)} new experiences -> library size {len(library)}")
    return library


def main() -> None:
    library = run_pipeline()
    _save_library(library)
    out_path = EXPERIENCE_LIBRARY_DATA_ANALYST_PATH_RESOLVED or (_AGENT_DIR / "experience_library_data_analyst.json")
    print(f"Saved {len(library)} experiences to {out_path}")


if __name__ == "__main__":
    main()
