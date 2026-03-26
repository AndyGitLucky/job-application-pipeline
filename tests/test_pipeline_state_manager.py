import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "source"))

from pipeline_state_manager import (
    can_proceed_to_apply,
    load_pipeline_state,
    set_review_status,
    set_verification_status,
    sync_jobs,
    update_job_decision,
)


class PipelineStateManagerTests(unittest.TestCase):
    def test_review_queue_and_approval_gate(self):
        state = load_pipeline_state("missing.json")
        sync_jobs(state, [{"id": "job1", "title": "Test", "company": "Demo", "url": "https://example.com"}], stage="discovered")
        update_job_decision(
            state,
            "job1",
            {
                "decision": "review",
                "decision_reason": "degree_requirement_risk",
                "next_action": "hold_for_review",
                "score_band": "strong",
                "review_status": "pending",
                "score": 7,
                "recommended": True,
            },
        )
        self.assertIn("job1", state["review_queue"])
        self.assertFalse(can_proceed_to_apply(state, "job1"))

        set_review_status(state, "job1", "approved", "looks good")
        self.assertNotIn("job1", state["review_queue"])
        self.assertTrue(can_proceed_to_apply(state, "job1"))

    def test_verification_status_is_persisted_in_state(self):
        state = load_pipeline_state("missing.json")
        sync_jobs(state, [{"id": "job2", "title": "Test2", "company": "Demo", "url": "https://example.com"}], stage="discovered")
        set_verification_status(state, "job2", "dead_listing", "listing gone")
        self.assertEqual(state["jobs"]["job2"]["verification_status"], "dead_listing")
        self.assertEqual(state["jobs"]["job2"]["verification_note"], "listing gone")


if __name__ == "__main__":
    unittest.main()
