import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "source"))

from score_jobs import score_job


class ScoreJobsErrorTests(unittest.TestCase):
    def test_scoring_errors_do_not_pollute_match_reason_contract(self):
        from unittest.mock import patch

        job = {"title": "Demo", "company": "DemoCo", "description": "Test"}
        with patch("score_jobs.llm_complete", side_effect=RuntimeError("network down")):
            result = score_job(job)

        self.assertEqual(result["score"], 0)
        self.assertEqual(result["match_reason"], "")
        self.assertEqual(result["score_status"], "error")
        self.assertIn("network down", result["scoring_error"])


if __name__ == "__main__":
    unittest.main()
