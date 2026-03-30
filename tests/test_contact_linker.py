import json
import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from source.contact_linker import choose_best_contact, enrich_jobs_with_contacts


class ContactLinkerTests(unittest.TestCase):
    def test_best_contact_prefers_relevant_role_and_email(self):
        candidates = [
            {"name": "Recruiter", "role": "Recruiter", "email": "", "source": "linkedin"},
            {"name": "Dana", "role": "Head of Data", "email": "dana@example.com", "source": "website"},
        ]
        best = choose_best_contact(candidates)
        self.assertEqual(best["name"], "Dana")

    def test_enrich_jobs_with_contacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs_path = Path(tmp) / "jobs_scored.json"
            contacts_path = Path(tmp) / "contacts.json"
            state_path = Path(tmp) / "pipeline_state.json"
            jobs_path.write_text(
                json.dumps([{"id": "1", "company": "DemoCo", "title": "DS", "url": "https://demo.example/jobs"}]),
                encoding="utf-8",
            )
            contacts_path.write_text(
                json.dumps([{"company": "DemoCo", "name": "Alex", "role": "Head of Data", "email": "alex@demo.example", "source": "website"}]),
                encoding="utf-8",
            )
            linked = enrich_jobs_with_contacts(jobs_path, contacts_path, state_path)
            jobs = json.loads(jobs_path.read_text(encoding="utf-8"))
            self.assertEqual(linked, 1)
            self.assertEqual(jobs[0]["contact_email"], "alex@demo.example")


if __name__ == "__main__":
    unittest.main()
