import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "source"))

import manual_contact_capture


class ManualContactCaptureTests(unittest.TestCase):
    def test_capture_manual_contact_updates_contacts_and_jobs(self):
        with tempfile.TemporaryDirectory() as tmp:
            contacts = Path(tmp) / "contacts.json"
            raw_jobs = Path(tmp) / "jobs_raw.json"
            scored_jobs = Path(tmp) / "jobs_scored.json"

            contacts.write_text("[]", encoding="utf-8")
            raw_jobs.write_text(
                '[{"id":"job1","company":"Demo GmbH","title":"Data Scientist"}]',
                encoding="utf-8",
            )
            scored_jobs.write_text(
                '[{"id":"job1","company":"Demo GmbH","title":"Data Scientist","decision":"apply","job_status":"live","listing_status":"jobboard_listing","url":"https://www.arbeitsagentur.de/jobsuche/jobdetail/123"}]',
                encoding="utf-8",
            )

            with patch.object(manual_contact_capture, "CONTACTS_PATH", contacts):
                with patch.object(manual_contact_capture, "RAW_JOBS_PATH", raw_jobs):
                    with patch.object(manual_contact_capture, "SCORED_JOBS_PATH", scored_jobs):
                        manual_contact_capture.capture_manual_contact(
                            job_id="job1",
                            email="kim@example.com",
                            name="Kim",
                            note="captcha solved",
                            reference_number="ERGO02672",
                        )

            stored_contacts = json.loads(contacts.read_text(encoding="utf-8"))
            stored_scored = json.loads(scored_jobs.read_text(encoding="utf-8"))

            self.assertEqual(stored_contacts[0]["email"], "kim@example.com")
            self.assertEqual(stored_contacts[0]["source"], "manual_captcha_capture:job1")
            self.assertEqual(stored_scored[0]["contact_email"], "kim@example.com")
            self.assertEqual(stored_scored[0]["manual_effort_type"], "captcha_then_email")
            self.assertEqual(stored_scored[0]["reference_number"], "ERGO02672")
