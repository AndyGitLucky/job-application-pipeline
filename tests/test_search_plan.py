import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from source.search_plan import build_search_plan


class SearchPlanTests(unittest.TestCase):
    @patch("source.search_plan.rank_roles_for_profile")
    @patch("source.search_plan.load_master_profile")
    def test_explore_mode_prefers_semantic_roles(self, load_master_profile, rank_roles_for_profile):
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
        rank_roles_for_profile.return_value = [
            {"term": "Perception Engineer", "score": 0.91, "strategy": "semantic", "provider": "lexical_fallback"},
            {"term": "Computer Vision Engineer", "score": 0.87, "strategy": "semantic", "provider": "lexical_fallback"},
        ]

        plan = build_search_plan("explore")

        self.assertEqual(plan["mode"], "explore")
        self.assertEqual(plan["explore_terms"][0], "Perception Engineer")
        self.assertEqual(plan["terms"][0]["strategy"], "semantic")
        self.assertGreater(plan["terms"][0]["semantic_score"], 0.8)
        self.assertIn("Data Engineer", plan["explore_terms"])
        self.assertTrue(all(item["bucket"] == "explore" for item in plan["terms"]))

    @patch("source.search_plan.load_master_profile")
    def test_invalid_mode_falls_back_to_normal(self, load_master_profile):
        load_master_profile.return_value = {"basics": {}, "skills": {}, "experience": [], "projects": []}
        plan = build_search_plan("something-else")
        self.assertEqual(plan["mode"], "normal")
        self.assertTrue(all(item["bucket"] == "core" for item in plan["terms"]))


if __name__ == "__main__":
    unittest.main()
