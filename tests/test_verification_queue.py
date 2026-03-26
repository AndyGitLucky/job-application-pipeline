import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "source"))

from verification_queue import verification_priority


class VerificationQueueTests(unittest.TestCase):
    def test_degree_and_research_penalties_push_priority_down(self):
        strong = {
            "final_bucket": "needs_review",
            "decision": "review",
            "job_status": "live",
            "score": 8,
            "source": "stepstone",
            "company": "Example GmbH",
            "listing_status": "jobboard_listing",
            "apply_path_status": "unresolved",
            "degree_required": False,
            "risk_flags": [],
        }
        weak = {
            **strong,
            "degree_required": True,
            "risk_flags": ["degree_required", "research_risk"],
        }
        strong_priority, _ = verification_priority(strong)
        weak_priority, _ = verification_priority(weak)
        self.assertGreater(strong_priority, weak_priority)


if __name__ == "__main__":
    unittest.main()
