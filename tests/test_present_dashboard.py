import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "source"))

from present_dashboard import generate_present_dashboard, render_present_dashboard


class PresentDashboardTests(unittest.TestCase):
    def test_generates_html_dashboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "jobs_raw.json"
            scored = Path(tmp) / "jobs_scored.json"
            out = Path(tmp) / "present_dashboard.html"
            apply_log = Path(tmp) / "apply_log.json"
            raw.write_text(
                '[{"id":"1","title":"AI Engineer","company":"Demo","location":"Munich","url":"https://de.indeed.com/viewjob?jk=abc","apply_url":"https://boards.greenhouse.io/demo/jobs/1","description":"desc","source":"indeed"}]',
                encoding="utf-8",
            )
            scored.write_text(
                '[{"id":"1","score":8,"final_bucket":"manual_apply_ready"}]',
                encoding="utf-8",
            )
            apply_log.write_text("{}", encoding="utf-8")

            path = generate_present_dashboard(raw, scored, out, apply_log)
            html = path.read_text(encoding="utf-8")

            self.assertEqual(path, out)
            self.assertIn("Review Workbench", html)
            self.assertIn("Top 5 Jobs Heute", html)
            self.assertIn("Warum Diese Jobs", html)
            self.assertIn("Welche Quellen Liefern Wert", html)
            self.assertIn("AI Engineer", html)

    def test_hides_applied_and_rejected_jobs(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "jobs_raw.json"
            scored = Path(tmp) / "jobs_scored.json"
            out = Path(tmp) / "present_dashboard.html"
            apply_log = Path(tmp) / "apply_log.json"
            raw.write_text(
                (
                    '[{"id":"1","title":"Shown Job","company":"Demo","location":"Munich","url":"https://example.com/jobs/1","description":"desc","source":"company"},'
                    '{"id":"2","title":"Applied Job","company":"Demo","location":"Munich","url":"https://example.com/jobs/2","description":"desc","source":"company"},'
                    '{"id":"3","title":"Rejected Job","company":"Demo","location":"Munich","url":"https://example.com/jobs/3","description":"desc","source":"company"}]'
                ),
                encoding="utf-8",
            )
            scored.write_text(
                (
                    '[{"id":"1","score":8,"final_bucket":"manual_apply_ready"},'
                    '{"id":"2","score":9,"final_bucket":"manual_apply_ready"},'
                    '{"id":"3","score":9,"final_bucket":"rejected","decision":"reject"}]'
                ),
                encoding="utf-8",
            )
            apply_log.write_text(
                '{"2":{"status":"sent","method":"email","timestamp":"2026-03-19T10:00:00"}}',
                encoding="utf-8",
            )

            path = generate_present_dashboard(raw, scored, out, apply_log)
            html = path.read_text(encoding="utf-8")

            self.assertIn("Shown Job", html)
            self.assertNotIn("Applied Job", html)
            self.assertNotIn("Rejected Job", html)
            self.assertIn("Resolved", html)
            self.assertIn("applied:sent", html)
            self.assertIn("rejected", html)

    def test_interactive_dashboard_renders_action_forms(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "jobs_raw.json"
            scored = Path(tmp) / "jobs_scored.json"
            apply_log = Path(tmp) / "apply_log.json"
            raw.write_text(
                '[{"id":"1","title":"Action Job","company":"Demo","location":"Munich","url":"https://example.com/jobs/1","description":"desc","source":"company"}]',
                encoding="utf-8",
            )
            scored.write_text(
                '[{"id":"1","score":8,"final_bucket":"manual_apply_ready"}]',
                encoding="utf-8",
            )
            apply_log.write_text("{}", encoding="utf-8")

            html = render_present_dashboard(raw, scored, apply_log, interactive=True)

            self.assertIn('action="/action"', html)
            self.assertIn('value="mark_applied"', html)
            self.assertIn("Beworben", html)
            self.assertIn("Research-lastig", html)
            self.assertIn('data-note="zu senior"', html)

    def test_repairs_mojibake_in_display(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "jobs_raw.json"
            scored = Path(tmp) / "jobs_scored.json"
            out = Path(tmp) / "present_dashboard.html"
            apply_log = Path(tmp) / "apply_log.json"
            raw.write_text(
                '[{"id":"1","title":"BÃ¼ro Engineer","company":"BÃ¼ro GmbH","location":"MÃ¼nchen","url":"https://example.com/jobs/1","description":"Arbeit im BÃ¼ro â€“ mit echten Daten.","source":"company"}]',
                encoding="utf-8",
            )
            scored.write_text(
                '[{"id":"1","score":8,"final_bucket":"manual_apply_ready"}]',
                encoding="utf-8",
            )
            apply_log.write_text("{}", encoding="utf-8")

            path = generate_present_dashboard(raw, scored, out, apply_log)
            html = path.read_text(encoding="utf-8")

            self.assertIn("Büro Engineer", html)
            self.assertIn("Büro GmbH", html)
            self.assertIn("München", html)
            self.assertIn("Arbeit im Büro – mit echten Daten.", html)
            self.assertNotIn("BÃ¼ro", html)
