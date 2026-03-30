import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from source.retrieval_context import retrieve_relevant_context
from source.vector_store import cosine_similarity


class VectorStoreTests(unittest.TestCase):
    def test_cosine_similarity_basic(self):
        self.assertAlmostEqual(cosine_similarity([1.0, 0.0], [1.0, 0.0]), 1.0)
        self.assertAlmostEqual(cosine_similarity([1.0, 0.0], [0.0, 1.0]), 0.0)

    def test_application_mode_excludes_market_strategy_snippets(self):
        job = {
            "title": "Industrial Data Scientist",
            "company": "Demo",
            "description": "Python machine learning for industrial test data and root cause analysis",
            "location": "Muenchen",
        }
        results = retrieve_relevant_context(job, limit=4, mode="application")
        categories = {item["category"] for item in results}
        self.assertNotIn("market_strategy", categories)

    def test_market_discovery_mode_can_surface_market_strategy(self):
        job = {
            "title": "Technical Consultant",
            "company": "Demo",
            "description": "Adjacent data, analytics, and operations roles outside pure AI or ML",
            "location": "Germany",
        }
        results = retrieve_relevant_context(job, limit=6, mode="market_discovery")
        categories = {item["category"] for item in results}
        self.assertIn("market_strategy", categories)

    def test_application_context_can_exclude_constraints_for_generation(self):
        job = {
            "title": "Machine Learning Engineer",
            "company": "Demo",
            "description": "Industrial machine learning with strong production relevance",
            "location": "Muenchen",
        }
        results = retrieve_relevant_context(
            job,
            limit=6,
            mode="application",
            exclude_categories={"constraint"},
        )
        categories = {item["category"] for item in results}
        self.assertNotIn("constraint", categories)


if __name__ == "__main__":
    unittest.main()
