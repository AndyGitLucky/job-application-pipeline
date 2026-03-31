import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from source.job_visibility import should_hide_job
from source.score_jobs import pre_score_job, score_jobs


class SearchModeScoringTests(unittest.TestCase):
    def test_pre_score_prefers_stronger_source_and_link_signals(self):
        feedback_summary = {}
        strong_job = {
            "title": "AI Engineer",
            "company": "Demo",
            "location": "Muenchen",
            "source": "arbeitsagentur",
            "best_link_quality": "medium",
            "best_link_kind": "captcha_then_company_apply",
            "description_quality": "high",
            "search_term_bucket": "core",
        }
        weak_job = {
            "title": "AI Engineer",
            "company": "Demo",
            "location": "Remote",
            "source": "stepstone",
            "best_link_quality": "low",
            "best_link_kind": "discovery_only",
            "description_quality": "medium",
            "search_term_bucket": "core",
        }
        strong_score, strong_signals = pre_score_job(strong_job, feedback_summary=feedback_summary, mode="normal")
        weak_score, weak_signals = pre_score_job(weak_job, feedback_summary=feedback_summary, mode="normal")

        self.assertGreater(strong_score, weak_score)
        self.assertIn("kind:captcha_then_company_apply", strong_signals)
        self.assertIn("kind:discovery_only", weak_signals)

    def test_pre_score_penalizes_explore_bucket_in_normal_mode(self):
        feedback_summary = {}
        core_job = {
            "title": "ML Engineer",
            "company": "Demo",
            "location": "Muenchen",
            "source": "arbeitsagentur",
            "best_link_quality": "medium",
            "best_link_kind": "manual_contact_gate",
            "description_quality": "high",
            "search_term_bucket": "core",
        }
        explore_job = dict(core_job)
        explore_job["search_term_bucket"] = "explore"

        core_score, _ = pre_score_job(core_job, feedback_summary=feedback_summary, mode="normal")
        explore_score, explore_signals = pre_score_job(explore_job, feedback_summary=feedback_summary, mode="normal")

        self.assertGreater(core_score, explore_score)
        self.assertIn("bucket:explore", explore_signals)

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

    def test_normal_mode_prefers_higher_pre_score_job(self):
        jobs = [
            {
                "id": "job-weak",
                "title": "Role Weak",
                "company": "DemoCo",
                "location": "Remote",
                "url": "https://example.com/weak",
                "description": "usable description " * 10,
                "source": "stepstone",
                "search_term_bucket": "core",
                "search_origin": "stepstone",
                "job_status": "candidate",
                "best_link_quality": "low",
                "best_link_kind": "discovery_only",
                "description_quality": "medium",
            },
            {
                "id": "job-strong",
                "title": "Role Strong",
                "company": "DemoCo",
                "location": "Muenchen",
                "url": "https://example.com/strong",
                "description": "rich description " * 40,
                "source": "arbeitsagentur",
                "search_term_bucket": "core",
                "search_origin": "arbeitsagentur",
                "job_status": "candidate",
                "best_link_quality": "medium",
                "best_link_kind": "manual_contact_gate",
                "description_quality": "high",
            },
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
                    search_mode="normal",
                    normal_new_job_limit=1,
                )

            self.assertEqual(scored_calls, ["job-strong"])
            scored_jobs = json.loads(output_path.read_text(encoding="utf-8"))
            by_id = {job["id"]: job for job in scored_jobs}
            self.assertEqual(by_id["job-strong"]["pre_score_selection_status"], "selected")
            self.assertEqual(by_id["job-weak"]["pre_score_selection_status"], "deferred")
            self.assertEqual(by_id["job-strong"]["pre_score_selection_rank"], 1)
            self.assertIn("kind:manual_contact_gate", by_id["job-strong"]["pre_score_selection_reason"])


if __name__ == "__main__":
    unittest.main()
