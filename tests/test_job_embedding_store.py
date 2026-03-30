import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from source import job_embedding_store as jes


class JobEmbeddingStoreTests(unittest.TestCase):
    def test_builds_store_and_marks_possible_duplicates_with_lexical_fallback(self):
        jobs = [
            {
                "id": "a",
                "title": "ML Ops Engineer - Implementation",
                "company": "BMW",
                "location": "München",
                "source": "stepstone",
                "description": "Build ML ops platform and deployment workflows for BMW.",
                "score": 7,
                "recommended": True,
                "final_bucket": "needs_review",
                "best_link_kind": "discovery_only",
            },
            {
                "id": "b",
                "title": "MLOps Engineer Implementation",
                "company": "BMW",
                "location": "München",
                "source": "bmw",
                "description": "Build MLOps platform and deployment workflows for BMW Group.",
                "score": 7,
                "recommended": True,
                "final_bucket": "manual_apply_ready",
                "best_link_kind": "company_detail",
            },
            {
                "id": "c",
                "title": "Data Analyst",
                "company": "Other",
                "location": "Berlin",
                "source": "indeed",
                "description": "Reporting and dashboards.",
                "score": 4,
                "recommended": False,
                "final_bucket": "rejected",
                "best_link_kind": "discovery_only",
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            original_store = jes.STORE_PATH
            jes.STORE_PATH = Path(tmp) / "job_embedding_store.json"
            try:
                store = jes.annotate_job_similarity(jobs, min_score=6, top_k=2, min_similarity=0.2)
            finally:
                jes.STORE_PATH = original_store

        self.assertEqual(store["provider"], "disabled")
        self.assertEqual(store["count"], 2)
        self.assertTrue(jobs[0]["similar_job_hints"])
        self.assertEqual(jobs[0]["similar_job_hints"][0]["job_id"], "b")
        self.assertEqual(jobs[0]["possible_duplicate_of"], "b")
        self.assertGreaterEqual(jobs[0]["possible_duplicate_score"], 0.68)
        self.assertEqual(jobs[2]["similar_job_hints"], [])

    def test_build_job_embedding_text_contains_core_fields(self):
        text = jes.build_job_embedding_text(
            {
                "title": "ML Engineer",
                "company": "Pruna",
                "location": "München",
                "source": "indeed",
                "best_link_kind": "discovery_only",
                "description": "Optimize and deploy models.",
            }
        )
        self.assertIn("title: ML Engineer", text)
        self.assertIn("company: Pruna", text)
        self.assertIn("link_kind: discovery_only", text)


if __name__ == "__main__":
    unittest.main()
