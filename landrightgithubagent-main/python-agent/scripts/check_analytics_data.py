#!/usr/bin/env python3
"""
Print what the data analyst (agent) sees from Supabase for a given repo.
Run from python-agent with .env loaded:
  python scripts/check_analytics_data.py [repo_full_name]

Example:
  python scripts/check_analytics_data.py ibrahim-ansari-code/s

If no repo given, defaults to ibrahim-ansari-code/s.
"""
from __future__ import annotations

import sys
from pathlib import Path

_AGENT_DIR = Path(__file__).resolve().parent.parent
if str(_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR))

from main import _get_cta_by_variant, _get_time_by_variant


def main() -> None:
    repo = (sys.argv[1] if len(sys.argv) > 1 else "").strip() or "ibrahim-ansari-code/s"
    layer = "1"

    print(f"Repo: {repo} (layer {layer})")
    print("-" * 50)

    rows = _get_cta_by_variant()
    clicks = [r for r in rows if (r.get("repo_full_name") or "").strip() == repo and (r.get("layer") or "").strip() == layer]
    if not clicks:
        print("CTA: no rows for this repo/layer")
    else:
        print("CTA (cta_by_variant):")
        for r in sorted(clicks, key=lambda x: -(x.get("cta_clicks") or 0)):
            print(f"  {r.get('variant_id')}: {r.get('cta_clicks')} clicks")

    time_rows = _get_time_by_variant()
    times = [r for r in time_rows if (r.get("repo_full_name") or "").strip() == repo and (r.get("layer") or "").strip() == layer]
    if not times:
        print("Time: no rows for this repo/layer")
    else:
        print("Time (time_by_variant):")
        for r in sorted(times, key=lambda x: -(float(x.get("total_seconds") or 0))):
            print(f"  {r.get('variant_id')}: {r.get('total_seconds')}s total")

    if clicks:
        from main import _normalize_variant_clicks
        raw = {r["variant_id"]: int(r.get("cta_clicks") or 0) for r in clicks}
        normalized = _normalize_variant_clicks(raw)
        times_map = {r["variant_id"]: float(r.get("total_seconds") or 0) for r in times}
        sorted_variants = sorted(
            normalized.items(),
            key=lambda x: (-x[1], -(times_map.get(x[0]) or 0)),
        )
        if sorted_variants:
            best_id, best_clicks = sorted_variants[0]
            print(f"\nAgent would pick best: {best_id} ({best_clicks} clicks, {times_map.get(best_id, 0):.0f}s time)")


if __name__ == "__main__":
    main()
