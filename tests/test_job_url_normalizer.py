import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "source"))

from job_url_normalizer import normalize_job_url


class JobUrlNormalizerTests(unittest.TestCase):
    def test_arbeitsagentur_search_url_becomes_jobdetail(self):
        url = (
            "https://www.arbeitsagentur.de/jobsuche/suche"
            "?kundennummer=abc&id=12874-123727-S&angebotsart=1"
        )
        self.assertEqual(
            normalize_job_url(url, source="arbeitsagentur"),
            "https://www.arbeitsagentur.de/jobsuche/jobdetail/12874-123727-S",
        )

    def test_indeed_keeps_only_jk(self):
        url = "https://de.indeed.com/viewjob?jk=abc123&utm_source=test&from=search"
        self.assertEqual(
            normalize_job_url(url, source="indeed"),
            "https://de.indeed.com/viewjob?jk=abc123",
        )

    def test_stepstone_strips_tracking_query(self):
        url = "https://www.stepstone.de/stellenangebote--demo-inline.html?cid=partner&utm_source=test"
        self.assertEqual(
            normalize_job_url(url, source="stepstone"),
            "https://www.stepstone.de/stellenangebote--demo-inline.html",
        )
