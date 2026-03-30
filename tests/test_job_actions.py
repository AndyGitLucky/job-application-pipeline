import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from source import job_actions


class JobActionsTests(unittest.TestCase):
    def test_mark_job_applied_writes_apply_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            apply_log = Path(tmp) / "apply_log.json"

            with patch.object(job_actions, "APPLY_LOG_PATH", apply_log):
                with patch.object(job_actions, "load_pipeline_state", return_value={"jobs": {}}):
                    with patch.object(job_actions, "save_pipeline_state"):
                        with patch.object(job_actions, "update_job_stage"):
                            with patch.object(job_actions, "record_feedback"):
                                with patch.object(job_actions, "refresh_feedback_summary"):
                                    job_actions.mark_job_applied("abc123", "manual test")

            data = json.loads(apply_log.read_text(encoding="utf-8"))
            self.assertEqual(data["abc123"]["status"], "sent")
            self.assertEqual(data["abc123"]["method"], "manual_ui")

    def test_perform_ui_action_dispatches(self):
        with patch.object(job_actions, "mark_job_applied") as applied:
            message = job_actions.perform_ui_action("abc123", "mark_applied")
            applied.assert_called_once()
            self.assertIn("beworben", message.lower())

    def test_set_state_decision_updates_nested_decision(self):
        state = {"jobs": {"abc123": {"decision": {"decision": "review"}}}}
        job_actions._set_state_decision(state, "abc123", "reject", "manual_ui_dead_listing")
        self.assertEqual(state["jobs"]["abc123"]["decision"]["decision"], "reject")
        self.assertEqual(state["jobs"]["abc123"]["decision"]["decision_reason"], "manual_ui_dead_listing")

    def test_perform_ui_action_can_generate_assets(self):
        with patch.object(job_actions, "generate_job_assets", return_value="Unterlagen erzeugt.") as generate:
            message = job_actions.perform_ui_action("abc123", "generate_application")
            generate.assert_called_once_with("abc123", "")
            self.assertIn("Unterlagen", message)
