"""
SimGym pipeline: bootstrap (generate + write bundle locally) or run (bots → adjust → learn).
All behavior driven by config/env (SIMGYM_*, LANDRIGHT_BACKEND_URL). No hardcoded repo/layer/URLs.
Order guarantees bots never view pages while edits are in progress: each round runs bots → then adjust (writes files) → then learning → then optional post-edit delay (local) → next round. Next round's bots start only after all edits and delay have completed.
Usage: python pipeline.py bootstrap | python pipeline.py [--repo REPO] [--layer LAYER] ...
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import httpx

from config import (
    AGENT_DIR,
    SIMGYM_BEACON_URL,
    SIMGYM_BASE_URL,
    SIMGYM_N_GENERATIONS,
    SIMGYM_N_ROUNDS_PER_GENERATION,
    SIMGYM_N_BOTS_PER_ROUND,
    SIMGYM_POST_ROUND_DELAY_SECONDS,
    SIMGYM_POST_EDIT_DELAY_SECONDS,
    LANDRIGHT_BACKEND_URL,
    SIMGYM_EXPORT_DIR_RESOLVED,
    SIMGYM_VARIANT_SOURCE,
    SIMGYM_DEFAULT_REPO,
    SIMGYM_DEFAULT_LAYER,
    SIMGYM_SPEC_PATH_RESOLVED,
)

from simgym_browser import run_bots

log = logging.getLogger(__name__)


def run_bootstrap(spec_path: Path | None = None, export_dir: Path | None = None, backend_url: str | None = None, repo_full_name: str | None = None, layer: str | None = None) -> None:
    """Call Landright backend /generate then /build-export-bundle; write bundle to export_dir. Uses config for repo/layer/spec path unless overridden."""
    export_dir = export_dir or SIMGYM_EXPORT_DIR_RESOLVED
    backend_url = (backend_url or LANDRIGHT_BACKEND_URL).rstrip("/")
    repo_full_name = (repo_full_name or SIMGYM_DEFAULT_REPO).strip()
    layer = (layer or SIMGYM_DEFAULT_LAYER).strip()
    if not export_dir:
        raise RuntimeError("SIMGYM_EXPORT_DIR is not set")
    spec_path = spec_path or SIMGYM_SPEC_PATH_RESOLVED or (AGENT_DIR / "simgym_spec.json")
    if not spec_path or not spec_path.exists():
        raise FileNotFoundError(f"SimGym spec not found: {spec_path}")
    with open(spec_path, encoding="utf-8") as f:
        payload = json.load(f)
    spec = payload.get("spec")
    prompt_id = payload.get("promptId", "simgym-initial")
    if not spec or not prompt_id:
        raise ValueError("Spec file must contain 'spec' and 'promptId'")
    log.info("POST %s/generate with promptId=%s", backend_url, prompt_id)
    with httpx.Client(timeout=300.0) as client:
        r = client.post(
            f"{backend_url}/generate",
            json={"spec": spec, "promptId": prompt_id},
        )
        r.raise_for_status()
        data = r.json()
    variants = data.get("variants") or []
    if len(variants) != 4:
        raise RuntimeError(f"Expected 4 variants from /generate, got {len(variants)}")
    log.info("POST %s/build-export-bundle repo=%s layer=%s", backend_url, repo_full_name, layer)
    with httpx.Client(timeout=60.0) as client:
        r = client.post(
            f"{backend_url}/build-export-bundle",
            json={
                "variant_tsx_list": variants,
                "repo_full_name": repo_full_name,
                "layer": layer,
            },
        )
        r.raise_for_status()
        bundle = r.json()
    files = bundle.get("files") or {}
    if not files:
        raise RuntimeError("build-export-bundle returned no files")
    export_dir.mkdir(parents=True, exist_ok=True)
    for path_key, content in files.items():
        if not isinstance(content, str):
            content = str(content)
        out_path = export_dir / path_key
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        log.info("Wrote %s", out_path)
    log.info("Bootstrap complete: %s files in %s. Run: cd %s && npm install && npm run dev", len(files), export_dir, export_dir)


def _get_clicks_and_time_for_repo_layer(repo_full_name: str, layer: str):
    """Import main only when needed to avoid circular import and heavy deps at CLI parse time."""
    from main import _get_cta_by_variant, _get_time_by_variant, _normalize_variant_clicks

    rows = _get_cta_by_variant()
    time_rows = _get_time_by_variant()
    group = [r for r in rows if (r.get("repo_full_name") or "").strip() == repo_full_name and (r.get("layer") or "").strip() == layer]
    time_group = [r for r in time_rows if (r.get("repo_full_name") or "").strip() == repo_full_name and (r.get("layer") or "").strip() == layer]
    variant_clicks = _normalize_variant_clicks({r["variant_id"]: int(r.get("cta_clicks") or 0) for r in group})
    time_by_variant = {r["variant_id"]: float(r.get("total_seconds") or 0) for r in time_group}
    return variant_clicks, time_by_variant


def run_pipeline(
    repo_full_name: str,
    layer: str | None = None,
    n_generations: int | None = None,
    n_rounds_per_generation: int | None = None,
    n_bots_per_round: int | None = None,
    base_url: str | None = None,
    beacon_url: str | None = None,
    local_export_dir: Path | None = None,
) -> None:
    """Run SimGym: each round = bots (only after prior round's edits + optional post-edit delay) → adjust → round learning → learning step. Bots never run while edits are in progress."""
    layer = (layer or SIMGYM_DEFAULT_LAYER).strip()
    n_generations = n_generations if n_generations is not None else SIMGYM_N_GENERATIONS
    n_rounds_per_gen = n_rounds_per_generation if n_rounds_per_generation is not None else SIMGYM_N_ROUNDS_PER_GENERATION
    n_bots = n_bots_per_round if n_bots_per_round is not None else SIMGYM_N_BOTS_PER_ROUND
    base_url = (base_url or SIMGYM_BASE_URL).rstrip("/")
    beacon_url = (beacon_url or SIMGYM_BEACON_URL).rstrip("/")
    if local_export_dir is None and SIMGYM_VARIANT_SOURCE == "local":
        local_export_dir = SIMGYM_EXPORT_DIR_RESOLVED

    from main import (
        run_adjust_pipeline,
        _run_learning_step,
        _append_round_to_experience_libraries,
    )

    for gen in range(1, n_generations + 1):
        log.info("SimGym generation %s/%s", gen, n_generations)
        for round_num in range(1, n_rounds_per_gen + 1):
            round_label = f"gen{gen}_r{round_num}"
            log.info("  Round %s/%s: running %s bots", round_num, n_rounds_per_gen, n_bots)
            run_bots(
                n_bots=n_bots,
                repo_full_name=repo_full_name,
                layer=layer,
                base_url=base_url,
                beacon_url=beacon_url,
            )
            variant_clicks, time_by_variant = _get_clicks_and_time_for_repo_layer(repo_full_name, layer)
            log.info("  Round %s: cta_by_variant %s time_by_variant %s", round_num, variant_clicks, time_by_variant)
            pushed = run_adjust_pipeline(
                repo_full_name,
                layer,
                variant_clicks,
                force_run=False,
                time_by_variant=time_by_variant,
                local_export_dir=local_export_dir,
            )
            judge_decision = "RUN_ADJUST" if pushed > 0 else "SKIP"
            try:
                _append_round_to_experience_libraries(
                    repo_full_name=repo_full_name,
                    layer=layer,
                    variant_clicks=variant_clicks,
                    time_by_variant=time_by_variant,
                    judge_decision=judge_decision,
                    files_updated=pushed,
                    round_label=round_label,
                )
            except Exception as e:
                log.warning("Round experience append failed: %s", e)
            try:
                _run_learning_step()
            except Exception as e:
                log.warning("Learning step failed: %s", e)
            # So bots never view pages while being edited: wait for dev server to reload after local writes before next round
            if local_export_dir and pushed > 0 and SIMGYM_POST_EDIT_DELAY_SECONDS > 0:
                log.info("  Waiting %.1f s (post-edit) before next round so app can reload", SIMGYM_POST_EDIT_DELAY_SECONDS)
                time.sleep(SIMGYM_POST_EDIT_DELAY_SECONDS)
            if round_num < n_rounds_per_gen and SIMGYM_POST_ROUND_DELAY_SECONDS > 0:
                log.info("  Waiting %s s before next round", SIMGYM_POST_ROUND_DELAY_SECONDS)
                time.sleep(SIMGYM_POST_ROUND_DELAY_SECONDS)
    total_bots = n_generations * n_rounds_per_gen * n_bots
    log.info("SimGym pipeline complete: %s generations × %s rounds × %s bots = %s total", n_generations, n_rounds_per_gen, n_bots, total_bots)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SimGym: bootstrap (generate + write bundle) or run (bots → adjust → learn). All defaults from config."
    )
    parser.add_argument("command", nargs="?", default="run", choices=["bootstrap", "run"], help="bootstrap: generate and write bundle; run: run pipeline")
    parser.add_argument("--repo", default=None, help=f"Repo for Supabase (default from SIMGYM_DEFAULT_REPO: {SIMGYM_DEFAULT_REPO})")
    parser.add_argument("--layer", default=None, help=f"Layer (default from SIMGYM_DEFAULT_LAYER: {SIMGYM_DEFAULT_LAYER})")
    parser.add_argument("--generations", type=int, default=None, help=f"Generations (default {SIMGYM_N_GENERATIONS})")
    parser.add_argument("--rounds-per-generation", type=int, default=None, help=f"Rounds per generation (default {SIMGYM_N_ROUNDS_PER_GENERATION})")
    parser.add_argument("--bots", type=int, default=None, help=f"Bots per round (default {SIMGYM_N_BOTS_PER_ROUND})")
    parser.add_argument("--base-url", default=None, help=f"Preview app URL (default SIMGYM_BASE_URL)")
    parser.add_argument("--beacon-url", default=None, help=f"Backend URL for beacons (default SIMGYM_BEACON_URL)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    if args.command == "bootstrap":
        run_bootstrap()
        return
    repo = (args.repo or SIMGYM_DEFAULT_REPO).strip()
    layer = (args.layer or SIMGYM_DEFAULT_LAYER).strip()
    run_pipeline(
        repo_full_name=repo,
        layer=layer,
        n_generations=args.generations,
        n_rounds_per_generation=args.rounds_per_generation,
        n_bots_per_round=args.bots,
        base_url=args.base_url,
        beacon_url=args.beacon_url,
    )


if __name__ == "__main__":
    main()
