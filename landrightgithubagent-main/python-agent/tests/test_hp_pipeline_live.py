import copy
import json
import unittest
from pathlib import Path

import main


class HpPipelineLiveTests(unittest.TestCase):
    def test_hp_full_pipeline_pushes_and_updates_experience_library(self):
        repo = "ibrahim-ansari-code/hp"
        layer = "1"
        before_files = main._fetch_variant_files(repo)
        tracked_before = {k: before_files[k] for k in ("variant-2", "variant-3", "variant-4")}

        experience_path = main.EXPERIENCE_LIBRARY_DATA_ANALYST_PATH_RESOLVED
        self.assertIsNotNone(experience_path)
        assert experience_path is not None
        before_experience = json.loads(Path(experience_path).read_text(encoding="utf-8"))
        before_len = len(before_experience)
        generation_path = main.EXPERIENCE_LIBRARY_GENERATION_PATH_RESOLVED
        self.assertIsNotNone(generation_path)
        assert generation_path is not None
        before_generation = json.loads(Path(generation_path).read_text(encoding="utf-8"))
        before_generation_len = len(before_generation)

        clicks = {"variant-1": 60, "variant-2": 24, "variant-3": 18, "variant-4": 12}
        times = {"variant-1": 300.0, "variant-2": 140.0, "variant-3": 110.0, "variant-4": 90.0}

        original_age = main.ADJUSTMENT_EVALUATION_MIN_AGE_SEC
        main.ADJUSTMENT_EVALUATION_MIN_AGE_SEC = 0
        pushed = main.run_adjust_pipeline(repo, layer, copy.deepcopy(clicks), force_run=True, time_by_variant=copy.deepcopy(times))
        self.assertEqual(pushed, 3)

        after_files = main._fetch_variant_files(repo)
        changed = [variant_id for variant_id in tracked_before if tracked_before[variant_id] != after_files[variant_id]]
        self.assertEqual(set(changed), {"variant-2", "variant-3", "variant-4"})

        main._run_learning_step()
        main.ADJUSTMENT_EVALUATION_MIN_AGE_SEC = original_age

        after_experience = json.loads(Path(experience_path).read_text(encoding="utf-8"))
        self.assertGreater(len(after_experience), before_len)
        self.assertIn("Avoid over-fitting", after_experience[-1])
        after_generation = json.loads(Path(generation_path).read_text(encoding="utf-8"))
        self.assertGreater(len(after_generation), before_generation_len)
        self.assertIn("Prefer these patterns in future generations", after_generation[-1])


if __name__ == "__main__":
    unittest.main()
