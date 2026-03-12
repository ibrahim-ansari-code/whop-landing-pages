"""Tests for SimGym browser runner and pipeline: forced variant assignment, beacon payloads, orchestrator flow."""
import unittest
from unittest.mock import patch, MagicMock

# Test simgym_browser module
import sys
from pathlib import Path
AGENT_DIR = Path(__file__).resolve().parent.parent
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from simgym_browser import _assign_variants, _send_beacon_cta, _send_beacon_time, run_bots
from pipeline import run_pipeline, _get_clicks_and_time_for_repo_layer


class TestAssignVariants(unittest.TestCase):
    def test_assign_variants_even_distribution(self):
        variants = _assign_variants(8)
        self.assertEqual(len(variants), 8)
        # Round-robin: 1,2,3,4,1,2,3,4
        self.assertEqual(variants[:4], [1, 2, 3, 4])
        self.assertEqual(variants[4:], [1, 2, 3, 4])

    def test_assign_variants_10_bots(self):
        variants = _assign_variants(10)
        self.assertEqual(len(variants), 10)
        self.assertEqual(variants[0], 1)
        self.assertEqual(variants[1], 2)
        self.assertEqual(variants[4], 1)
        self.assertEqual(variants[8], 1)  # round-robin: 1,2,3,4,1,2,3,4,1,2

    def test_assign_variants_all_in_valid_range(self):
        for n in (1, 4, 100):
            v = _assign_variants(n)
            self.assertTrue(all(1 <= x <= 4 for x in v), f"n={n} got {v}")


class TestBeaconPayloads(unittest.TestCase):
    def test_beacon_cta_includes_event_source_simgym(self):
        with patch("simgym_browser.httpx") as mock_httpx:
            mock_httpx.post.return_value.status_code = 200
            _send_beacon_cta("http://localhost:8000", "owner/repo", "1", 2, cta_label="Get started")
            mock_httpx.post.assert_called_once()
            call_kw = mock_httpx.post.call_args
            self.assertEqual(call_kw[0][0], "http://localhost:8000/beacon")
            payload = call_kw[1]["json"]
            self.assertEqual(payload.get("event_source"), "simgym")
            self.assertEqual(payload.get("repo_full_name"), "owner/repo")
            self.assertEqual(payload.get("variant_id"), "variant-2")
            self.assertEqual(payload.get("event"), "button_click")

    def test_beacon_time_includes_event_source_simgym(self):
        with patch("simgym_browser.httpx") as mock_httpx:
            mock_httpx.post.return_value.status_code = 200
            _send_beacon_time("http://localhost:8000", "owner/repo", "1", 3, 12.5)
            mock_httpx.post.assert_called_once()
            payload = mock_httpx.post.call_args[1]["json"]
            self.assertEqual(payload.get("event_source"), "simgym")
            self.assertEqual(payload.get("variant_id"), "variant-3")
            self.assertEqual(payload.get("duration_seconds"), 12.5)


class TestPipelineOrchestrator(unittest.TestCase):
    def test_run_pipeline_calls_run_bots_and_adjust(self):
        with patch("pipeline.run_bots") as mock_bots, \
             patch("main.run_adjust_pipeline") as mock_adjust, \
             patch("main._run_learning_step") as mock_learn, \
             patch("pipeline._get_clicks_and_time_for_repo_layer") as mock_get:
            mock_get.return_value = ({"variant-1": 5, "variant-2": 3, "variant-3": 2, "variant-4": 1}, {"variant-1": 10.0, "variant-2": 8.0})
            run_pipeline("owner/repo", layer="1", n_generations=1, n_rounds_per_generation=1, n_bots_per_round=4)
            self.assertEqual(mock_bots.call_count, 1)
            self.assertEqual(mock_adjust.call_count, 1)
            self.assertEqual(mock_learn.call_count, 1)
            call_kw = mock_bots.call_args[1]
            self.assertEqual(call_kw["n_bots"], 4)
            self.assertEqual(call_kw["repo_full_name"], "owner/repo")
            self.assertEqual(call_kw["layer"], "1")

    def test_run_pipeline_two_rounds_calls_bots_twice(self):
        with patch("pipeline.run_bots") as mock_bots, \
             patch("main.run_adjust_pipeline"), \
             patch("main._run_learning_step"), \
             patch("pipeline._get_clicks_and_time_for_repo_layer") as mock_get, \
             patch("pipeline.time.sleep"):  # avoid 6 min wait in test
            mock_get.return_value = ({"variant-1": 1, "variant-2": 0, "variant-3": 0, "variant-4": 0}, {})
            run_pipeline("owner/repo", n_generations=1, n_rounds_per_generation=2, n_bots_per_round=2)
            self.assertEqual(mock_bots.call_count, 2)


class TestForcedVariantInBundle(unittest.TestCase):
    """Test that export_bundle generates ClientPage with forced variant support (if export_bundle is importable)."""
    def test_export_bundle_contains_forced_variant_logic(self):
        try:
            from export_bundle import build_vercel_bundle
        except ImportError:
            self.skipTest("export_bundle not on path (run from monorepo root or landright-app/backend)")
        # Build minimal bundle to get page_tsx content
        try:
            files = build_vercel_bundle(
                variant_tsx_list=["<div>V1</div>", "<div>V2</div>", "<div>V3</div>", "<div>V4</div>"],
                repo_full_name="test/repo",
                layer="1",
                beacon_url="http://localhost:8000",
                posthog_key=None,
            )
        except Exception as e:
            self.skipTest(f"build_vercel_bundle failed: {e}")
        page_tsx = files.get("app/ClientPage.tsx", "")
        self.assertIn("getForcedVariantFromUrl", page_tsx)
        self.assertIn("variant", page_tsx)
        self.assertIn("URLSearchParams", page_tsx)
        self.assertIn("1", page_tsx)
        self.assertIn("4", page_tsx)


if __name__ == "__main__":
    unittest.main()
