import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from source.job_visibility import should_hide_job
from source.score_jobs import score_jobs


class SearchModeScoringTests(unittest.TestCase):
    def test_explore_mode_scores_only_limited_number_of_new_jobs(self):
        jobs = [
            {
                "id": f"job-{idx}",
                "title": f"Role {idx}",
                "company": "DemoCo",
                "location": "Munich",
                "url": f"https://example.com/{idx}",
                "description": "rich description " * 30,
                "source": "stepstone",
                "search_term_bucket": "explore" if idx < 3 else "core",
                "search_origin": "stepstone",
                "job_status": "candidate",
            }
            for idx in range(4)
        ]

        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "jobs_raw.json"
            output_path = Path(tmp) / "jobs_scored.json"
            input_path.write_text(json.dumps(jobs), encoding="utf-8")

            scored_calls: list[str] = []

            def fake_score_job(job: dict) -> dict:
                scored_calls.append(job["id"])
                return {
                    "score": 7,
                    "degree_required": False,
                    "degree_note": "",
                    "match_reason": "good fit",
                    "keywords_matched": ["ml"],
                    "recommended": True,
                    "score_status": "ok",
                    "scoring_error": "",
                }

            with patch("source.score_jobs.refresh_feedback_summary", return_value={}), \
                patch("source.score_jobs.load_pipeline_state", return_value={}), \
                patch("source.score_jobs.save_pipeline_state"), \
                patch("source.score_jobs.sync_jobs"), \
                patch("source.score_jobs.update_job_decision"), \
                patch("source.score_jobs.update_job_stage"), \
                patch("source.score_jobs.prepare_job_decision", return_value={"decision": "review"}), \
                patch("source.score_jobs.classify_job", return_value={"final_bucket": "needs_review"}), \
                patch("source.score_jobs.annotate_job_similarity", return_value={"count": 0, "provider": "disabled"}), \
                patch("source.score_jobs.score_job", side_effect=fake_score_job):
                score_jobs(
                    input_file=str(input_path),
                    output_file=str(output_path),
                    search_mode="explore",
                    explore_new_job_limit=2,
                )

            scored_jobs = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(len(scored_calls), 2)
            self.assertEqual(scored_calls, ["job-0", "job-1"])

            deferred = [job for job in scored_jobs if job.get("score_status") == "deferred_explore_limit"]
            self.assertEqual(len(deferred), 2)
            self.assertTrue(all(should_hide_job(job, {}) for job in deferred))


if __name__ == "__main__":
    unittest.main()
