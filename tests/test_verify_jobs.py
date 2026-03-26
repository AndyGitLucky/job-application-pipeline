import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "source"))

import verify_jobs as vj


class VerifyJobsTests(unittest.TestCase):
    def test_verify_jobs_promotes_resolved_apply_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs_path = Path(tmp) / "jobs_scored.json"
            primary_sources_path = Path(tmp) / "primary_sources.json"
            primary_sources_path.write_text("[]", encoding="utf-8")
            jobs_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "job1",
                            "title": "AI Engineer",
                            "company": "Demo",
                            "url": "https://www.stepstone.de/stellenangebote--demo-inline.html",
                            "description": "Some text",
                            "recommended": True,
                            "score": 8,
                            "decision": "apply",
                            "job_status": "live",
                            "listing_status": "jobboard_listing",
                            "apply_path_status": "unresolved",
                            "final_bucket": "needs_review",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"PRIMARY_SOURCES_FILE": str(primary_sources_path)}):
                with patch(
                    "verify_jobs.resolve_company_apply_url",
                    return_value=SimpleNamespace(
                        url="https://demo.recruitee.com/o/ai-engineer",
                        source="html",
                        failure_type="",
                        detail="",
                        http_status=0,
                    ),
                ):
                    verified = vj.verify_jobs(str(jobs_path), str(jobs_path), limit=5)

            jobs = json.loads(jobs_path.read_text(encoding="utf-8"))
            learned_sources = json.loads(primary_sources_path.read_text(encoding="utf-8"))
            self.assertEqual(len(verified), 1)
            self.assertEqual(jobs[0]["verification_status"], "verified_ready")
            self.assertEqual(jobs[0]["final_bucket"], "manual_apply_ready")
            self.assertEqual(jobs[0]["url_company"], "https://demo.recruitee.com/o/ai-engineer")
            self.assertTrue(jobs[0]["primary_source_learned"])
            self.assertEqual(jobs[0]["primary_source_type"], "recruitee")
            self.assertEqual(learned_sources[0]["type"], "recruitee")
            self.assertEqual(learned_sources[0]["subdomain"], "demo")


if __name__ == "__main__":
    unittest.main()
