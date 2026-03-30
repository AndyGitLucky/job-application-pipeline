import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from source.link_extractor import annotate_job_links


class LinkExtractorTests(unittest.TestCase):
    def test_prefers_known_ats_url(self):
        job = {
            "url": "https://www.stepstone.de/stellenangebote--demo-inline.html",
            "apply_url": "https://boards.greenhouse.io/demo/jobs/123",
        }
        enriched = annotate_job_links(job)
        self.assertEqual(enriched["best_link_kind"], "direct_apply")
        self.assertEqual(enriched["best_link_quality"], "high")
        self.assertEqual(enriched["best_link_source_field"], "apply_url")

    def test_marks_arbeitsagentur_as_manual_contact_gate(self):
        job = {
            "url": "https://www.arbeitsagentur.de/jobsuche/jobdetail/12874-123727-S",
            "source": "arbeitsagentur",
            "description": "Ausführliche Arbeitsagentur-Beschreibung mit mehreren Sätzen, echten Anforderungen, Kontext zur Rolle und genug Substanz für eine sinnvolle Bewertung.",
        }
        enriched = annotate_job_links(job)
        self.assertEqual(enriched["best_link_kind"], "manual_contact_gate")
        self.assertEqual(enriched["best_link_quality"], "medium")
        self.assertEqual(enriched["description_quality"], "high")
        self.assertEqual(enriched["description_reason"], "arbeitsagentur_rich_description")

    def test_marks_jobboard_as_discovery_only(self):
        job = {
            "url": "https://de.indeed.com/viewjob?jk=abc123",
        }
        enriched = annotate_job_links(job)
        self.assertEqual(enriched["best_link_kind"], "discovery_only")
        self.assertEqual(enriched["best_link_quality"], "low")
