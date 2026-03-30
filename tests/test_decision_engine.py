import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from source.decision_engine import prepare_job_decision


class DecisionEngineTests(unittest.TestCase):
    def test_high_fit_job_is_apply(self):
        job = {
            "score": 9,
            "recommended": True,
            "degree_required": False,
            "title": "Applied Data Scientist",
            "description": "Industrial machine learning for sensor data in production. "
            "Python, SQL, anomaly detection, manufacturing analytics, ETL, experimentation, "
            "cross-functional work with product and operations teams, deployment of models, "
            "stakeholder collaboration, KPI tracking, root-cause analysis, and hands-on analysis "
            "of test and measurement data in an applied environment.",
        }
        decision = prepare_job_decision(job, min_score=6)
        self.assertEqual(decision["decision"], "apply")
        self.assertEqual(decision["review_status"], "not_required")

    def test_risky_senior_job_goes_to_review(self):
        job = {
            "score": 8,
            "recommended": True,
            "degree_required": False,
            "title": "Principal AI Scientist",
            "description": "Foundation model research roadmap and scientific leadership",
        }
        decision = prepare_job_decision(job, min_score=6)
        self.assertEqual(decision["decision"], "review")
        self.assertEqual(decision["review_status"], "pending")


if __name__ == "__main__":
    unittest.main()
