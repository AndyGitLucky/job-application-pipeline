import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from source.search_plan import build_search_plan


class SearchPlanTests(unittest.TestCase):
    @patch("source.search_plan.load_master_profile")
    def test_explore_mode_includes_adjacent_terms_from_profile_signals(self, load_master_profile):
        load_master_profile.return_value = {
            "basics": {"title": "Machine Learning / Data Scientist"},
            "skills": {
                "ml": ["Machine Learning", "Deep Learning"],
                "data": ["SQL", "Pandas"],
                "tools": ["OpenCV"],
            },
            "experience": [
                {
                    "tags": ["data engineering", "quality"],
                    "tech": ["pipeline", "statistics"],
                }
            ],
            "projects": [
                {
                    "tags": ["computer vision", "real-time inference"],
                    "tech": ["CUDA", "OpenCV"],
                }
            ],
            "certifications_or_topics": ["optimization"],
        }

        plan = build_search_plan("explore")

        self.assertEqual(plan["mode"], "explore")
        self.assertIn("Data Engineer", plan["explore_terms"])
        self.assertIn("ML Systems Engineer", plan["explore_terms"])
        self.assertIn("Decision Scientist", plan["explore_terms"])
        self.assertTrue(all(item["bucket"] == "explore" for item in plan["terms"]))

    @patch("source.search_plan.load_master_profile")
    def test_invalid_mode_falls_back_to_normal(self, load_master_profile):
        load_master_profile.return_value = {"basics": {}, "skills": {}, "experience": [], "projects": []}
        plan = build_search_plan("something-else")
        self.assertEqual(plan["mode"], "normal")
        self.assertTrue(all(item["bucket"] == "core" for item in plan["terms"]))


if __name__ == "__main__":
    unittest.main()
