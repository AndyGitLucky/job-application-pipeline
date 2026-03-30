import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from source.feedback_learning import feedback_delta_for_job, normalize_feedback_reason, refresh_feedback_summary


class FeedbackLearningTests(unittest.TestCase):
    def test_normalize_feedback_reason(self):
        self.assertEqual(normalize_feedback_reason("zu research lastig"), "zu_research_lastig")
        self.assertEqual(normalize_feedback_reason("falsche Richtung oder Spezialisierung"), "falsche_spezialisierung")
        self.assertEqual(normalize_feedback_reason("Master vorausgesetzt"), "studium_hart_erforderlich")

    def test_refresh_feedback_summary_and_delta(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs_path = Path(tmp) / "jobs_scored.json"
            feedback_path = Path(tmp) / "feedback_log.json"
            summary_path = Path(tmp) / "feedback_summary.json"

            jobs_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "1",
                            "title": "Senior AI Research Engineer",
                            "source": "arbeitsagentur",
                            "best_link_kind": "manual_contact_gate",
                        },
                        {
                            "id": "2",
                            "title": "AI Engineer",
                            "source": "bmw",
                            "best_link_kind": "company_detail",
                        },
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            feedback_path.write_text(
                json.dumps(
                    {
                        "1": [
                            {"value": "reject", "note": "zu research lastig"},
                            {"value": "reject", "note": "zu senior"},
                        ],
                        "2": [
                            {"value": "verify-ready", "note": "passt gut"},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            summary = refresh_feedback_summary(jobs_path, feedback_path=feedback_path, output_path=summary_path)
            self.assertEqual(summary["reasons"]["zu_research_lastig"], 1)
            self.assertEqual(summary["by_source"]["arbeitsagentur"]["reject"], 2)
            self.assertEqual(summary["by_link_kind"]["company_detail"]["verify-ready"], 1)

            delta, signals = feedback_delta_for_job(
                {
                    "title": "Senior AI Research Engineer",
                    "description": "",
                    "source": "arbeitsagentur",
                    "best_link_kind": "manual_contact_gate",
                },
                summary,
            )
            self.assertLess(delta, 0)
            self.assertTrue(signals)
