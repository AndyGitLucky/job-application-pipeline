import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from source.role_library import build_profile_semantic_text, rank_roles_for_profile


class RoleLibraryTests(unittest.TestCase):
    def test_build_profile_semantic_text_includes_key_sections(self):
        profile = {
            "basics": {"title": "Machine Learning / Data Scientist"},
            "summary_candidates": ["Applied ML in technical environments."],
            "skills": {"ml": ["TensorFlow"], "data": ["SQL"]},
            "experience": [{"role": "Analyst", "tags": ["measurement"], "tech": ["Python"]}],
            "projects": [{"name": "CV Project", "tags": ["computer vision"], "tech": ["OpenCV"]}],
            "certifications_or_topics": ["optimization"],
        }
        text = build_profile_semantic_text(profile)
        self.assertIn("Machine Learning / Data Scientist", text)
        self.assertIn("computer vision", text)
        self.assertIn("optimization", text)

    @patch("source.role_library.embeddings_enabled", return_value=False)
    def test_rank_roles_for_profile_uses_lexical_fallback(self, _embeddings_enabled):
        profile = {
            "basics": {"title": "Machine Learning / Data Scientist"},
            "summary_candidates": ["Computer vision and real-time inference for technical systems."],
            "skills": {"ml": ["Deep Learning"], "tools": ["OpenCV", "CUDA"]},
            "experience": [{"role": "Analyst", "tags": ["technical systems"], "tech": ["Python"]}],
            "projects": [{"name": "Vision", "tags": ["computer vision", "real-time inference"], "tech": ["OpenCV", "CUDA"]}],
            "certifications_or_topics": ["inference"],
        }
        ranked = rank_roles_for_profile(profile, top_k=8)
        terms = [item["term"] for item in ranked]
        self.assertIn("Computer Vision Engineer", terms)
        self.assertTrue(
            any(term in terms for term in {"Inference Engineer", "Perception Engineer", "ML Systems Engineer"})
        )


if __name__ == "__main__":
    unittest.main()
