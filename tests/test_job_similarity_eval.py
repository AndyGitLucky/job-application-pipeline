import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from source import job_similarity_eval as jse


class JobSimilarityEvalTests(unittest.TestCase):
    def test_build_similarity_pairs_deduplicates_bidirectional_hints(self):
        jobs = [
            {
                "id": "a",
                "title": "ML Ops Engineer",
                "company": "BMW",
                "location": "München",
                "source": "stepstone",
                "similar_job_hints": [{"job_id": "b", "similarity": 0.81}],
            },
            {
                "id": "b",
                "title": "MLOps Engineer",
                "company": "BMW",
                "location": "München",
                "source": "bmw",
                "similar_job_hints": [{"job_id": "a", "similarity": 0.79}],
            },
        ]

        pairs = jse.build_similarity_pairs(jobs)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["pair_key"], jse.pair_key("a", "b"))
        self.assertEqual(pairs[0]["similarity"], 0.81)

    def test_record_similarity_decision_persists_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "job_similarity_eval.json"
            key = jse.record_similarity_decision("a", "b", "merge_ok", log_path=log_path)
            payload = json.loads(log_path.read_text(encoding="utf-8"))

        self.assertEqual(key, "a||b")
        self.assertEqual(payload["decisions"]["a||b"]["decision"], "merge_ok")

    def test_render_page_shows_clean_german_copy_and_batch_stats(self):
        jobs = [
            {
                "id": "a",
                "title": "ML Ops Engineer",
                "company": "BMW",
                "location": "München",
                "source": "stepstone",
                "score": 7,
                "best_link_kind": "discovery_only",
                "best_link": "https://example.com/a",
                "description": "Role A",
                "final_bucket": "needs_review",
                "similar_job_hints": [{"job_id": "b", "similarity": 0.81}],
            },
            {
                "id": "b",
                "title": "MLOps Engineer",
                "company": "BMW",
                "location": "München",
                "source": "bmw",
                "score": 7,
                "best_link_kind": "company_detail",
                "best_link": "https://example.com/b",
                "description": "Role B",
                "final_bucket": "needs_review",
                "similar_job_hints": [{"job_id": "a", "similarity": 0.79}],
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            jobs_path = Path(tmp) / "jobs_scored.json"
            jobs_path.write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")
            html = jse.render_similarity_eval_page(jobs_path=jobs_path, page=1, batch_size=1)

        self.assertIn("Ähnliche Jobs prüfen", html)
        self.assertIn("Paare gesamt", html)
        self.assertIn("Seite 1 von 1", html)
        self.assertIn("München", html)
        self.assertIn("Was die bisherigen Entscheidungen sagen", html)
        self.assertNotIn("Ã", html)

    def test_summary_groups_decisions_by_threshold(self):
        jobs = [
            {
                "id": "a",
                "title": "Role A",
                "company": "BMW",
                "location": "München",
                "similar_job_hints": [{"job_id": "b", "similarity": 0.86}],
            },
            {
                "id": "b",
                "title": "Role B",
                "company": "BMW",
                "location": "München",
                "similar_job_hints": [{"job_id": "a", "similarity": 0.86}, {"job_id": "c", "similarity": 0.74}],
            },
            {
                "id": "c",
                "title": "Role C",
                "company": "BMW",
                "location": "München",
                "similar_job_hints": [{"job_id": "b", "similarity": 0.74}],
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            jobs_path = Path(tmp) / "jobs_scored.json"
            log_path = Path(tmp) / "job_similarity_eval.json"
            jobs_path.write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")
            jse.record_similarity_decision("a", "b", "merge_ok", log_path=log_path)
            jse.record_similarity_decision("b", "c", "not_same_job", log_path=log_path)
            summary = jse.summarize_similarity_eval(
                jobs_path=jobs_path,
                log_path=log_path,
                thresholds=(0.85, 0.7),
            )

        self.assertEqual(summary[0]["total"], 1)
        self.assertEqual(summary[0]["merge_ok"], 1)
        self.assertEqual(summary[0]["merge_rate"], 1.0)
        self.assertEqual(summary[1]["total"], 2)
        self.assertEqual(summary[1]["not_same_job"], 1)


if __name__ == "__main__":
    unittest.main()
