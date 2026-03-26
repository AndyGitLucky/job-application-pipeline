import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "source"))

from job_buckets import classify_job


class JobBucketTests(unittest.TestCase):
    def test_autoapply_ready_for_known_ats(self):
        job = {
            "decision": "apply",
            "job_status": "live",
            "listing_status": "verified_direct",
            "url": "https://nucsai.recruitee.com/o/machine-learning-scientist",
        }
        result = classify_job(job)
        self.assertEqual(result["fit_status"], "approved")
        self.assertEqual(result["listing_status"], "verified_direct")
        self.assertEqual(result["apply_path_status"], "auto")
        self.assertEqual(result["final_bucket"], "autoapply_ready")

    def test_manual_ready_for_company_career_page(self):
        job = {
            "decision": "apply",
            "job_status": "live",
            "listing_status": "verified_direct",
            "url_company": "https://company.example/careers/ai-engineer",
            "url": "https://www.arbeitsagentur.de/jobsuche/jobdetail/123",
        }
        result = classify_job(job)
        self.assertEqual(result["final_bucket"], "manual_apply_ready")

    def test_review_stays_in_review_bucket(self):
        job = {
            "decision": "review",
            "job_status": "live",
            "contact_email": "jobs@example.com",
        }
        result = classify_job(job)
        self.assertEqual(result["final_bucket"], "needs_review")

    def test_reject_stays_rejected(self):
        job = {
            "decision": "reject",
            "job_status": "live",
            "contact_email": "jobs@example.com",
        }
        result = classify_job(job)
        self.assertEqual(result["final_bucket"], "rejected")

    def test_apply_with_unresolved_jobboard_path_stays_in_review_bucket(self):
        job = {
            "decision": "apply",
            "job_status": "live",
            "listing_status": "jobboard_listing",
            "url": "https://www.arbeitsagentur.de/jobsuche/jobdetail/123",
        }
        result = classify_job(job)
        self.assertEqual(result["apply_path_status"], "unresolved")
        self.assertEqual(result["final_bucket"], "needs_review")

    def test_verified_ready_promotes_apply_job_to_manual_ready(self):
        job = {
            "decision": "apply",
            "job_status": "live",
            "verification_status": "verified_ready",
            "listing_status": "jobboard_listing",
            "url": "https://www.stepstone.de/stellenangebote--foo-inline.html",
        }
        result = classify_job(job)
        self.assertEqual(result["final_bucket"], "manual_apply_ready")

    def test_verified_reject_forces_rejected_bucket(self):
        job = {
            "decision": "apply",
            "job_status": "live",
            "verification_status": "verified_reject",
            "url": "https://company.example/jobs/foo",
        }
        result = classify_job(job)
        self.assertEqual(result["fit_status"], "rejected")
        self.assertEqual(result["final_bucket"], "rejected")

    def test_manual_captcha_contact_stays_manual(self):
        job = {
            "decision": "apply",
            "job_status": "live",
            "contact_email": "jobs@example.com",
            "contact_source": "manual_captcha_capture:abc123",
            "listing_status": "jobboard_listing",
            "url": "https://www.arbeitsagentur.de/jobsuche/jobdetail/123",
        }
        result = classify_job(job)
        self.assertEqual(result["apply_path_status"], "manual")
        self.assertEqual(result["final_bucket"], "needs_review")


if __name__ == "__main__":
    unittest.main()
