import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("feedparser", types.SimpleNamespace())

from source.find_jobs import (
    _build_man_rss_url,
    _extract_bmw_location,
    _extract_conrad_location,
    _extract_infineon_location,
    _extract_siemens_location,
    _matches_company_search_term,
    _normalize_rss_entry_date,
    _parse_man_title_and_location,
    enrich_job_description,
    load_company_search_sources,
    load_primary_sources,
    make_job,
)


class PrimarySourcesTests(unittest.TestCase):
    def test_load_primary_sources_reads_json_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "primary_sources.json"
            path.write_text(
                json.dumps(
                    [
                        {"type": "greenhouse", "company": "Example", "board_token": "example"},
                        {"type": "lever", "company": "Example2", "site": "example2"},
                    ]
                ),
                encoding="utf-8",
            )
            sources = load_primary_sources(path)
            self.assertEqual(len(sources), 2)
            self.assertEqual(sources[0]["type"], "greenhouse")

    def test_load_company_search_sources_reads_json_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "company_search_sources.json"
            path.write_text(
                json.dumps(
                    [
                        {"company": "SWM", "type": "career_search_portal", "url": "https://www.swm.de/karriere"},
                        {"company": "Siemens Energy", "type": "career_search_portal", "url": "https://jobs.siemens-energy.com/de_DE/jobs"},
                    ]
                ),
                encoding="utf-8",
            )
            sources = load_company_search_sources(path)
            self.assertEqual(len(sources), 2)
            self.assertEqual(sources[0]["company"], "SWM")

    def test_make_job_keeps_discovery_and_apply_urls(self):
        job = make_job(
            title="AI Engineer",
            company="Demo",
            location="Munich",
            url="https://boards.greenhouse.io/demo/jobs/123",
            description="desc",
            source="greenhouse",
            discovery_url="https://boards-api.greenhouse.io/v1/boards/demo/jobs?content=true",
            apply_url="https://boards.greenhouse.io/demo/jobs/123",
            source_url_type="known_ats",
            apply_url_type="greenhouse",
        )
        self.assertEqual(job["discovery_url"], "https://boards-api.greenhouse.io/v1/boards/demo/jobs?content=true")
        self.assertEqual(job["apply_url"], "https://boards.greenhouse.io/demo/jobs/123")
        self.assertEqual(job["source_url_type"], "known_ats")
        self.assertEqual(job["apply_url_type"], "greenhouse")

    def test_make_job_normalizes_arbeitsagentur_url(self):
        job = make_job(
            title="AI Engineer",
            company="Demo",
            location="Munich",
            url="https://www.arbeitsagentur.de/jobsuche/suche?id=12874-123727-S&kundennummer=abc",
            description="desc",
            source="arbeitsagentur",
        )
        self.assertEqual(job["url"], "https://www.arbeitsagentur.de/jobsuche/jobdetail/12874-123727-S")
        self.assertEqual(job["discovery_url"], "https://www.arbeitsagentur.de/jobsuche/jobdetail/12874-123727-S")
        self.assertEqual(job["apply_url"], "https://www.arbeitsagentur.de/jobsuche/jobdetail/12874-123727-S")

    def test_make_job_infers_company_from_indeed_description(self):
        job = make_job(
            title="ML Engineer",
            company="",
            location="München",
            url="https://de.indeed.com/viewjob?jk=abc",
            description=(
                "About us\n\n"
                "At Pruna, we're on a mission to make AI more efficient.\n\n"
                "As an ML Engineer at Pruna AI, you will bridge the gap between research and application."
            ),
            source="indeed",
        )
        self.assertEqual(job["company"], "Pruna")

    def test_matches_company_search_term_accepts_partial_overlap(self):
        self.assertTrue(_matches_company_search_term("AI Engineer", "Senior AI Platform Engineer", "Informatik / Vollzeit"))
        self.assertFalse(_matches_company_search_term("AI Engineer", "Busfahrer*in", "Fahrdienst / Vollzeit"))

    def test_extract_siemens_location(self):
        text = "Über die Aufgabe Standort Deutschland Bayern Munich Remote oder Büro Nur Büro/Standort Unternehmen Siemens Energy"
        self.assertEqual(_extract_siemens_location(text), "Deutschland Bayern Munich")

    def test_extract_infineon_location(self):
        text = "Apply now Standort: Neubiberg Job ID HRC12345 Contact"
        self.assertEqual(_extract_infineon_location(text), "Neubiberg")

    def test_extract_bmw_location(self):
        text = "Datum: 23.02.2026 Standort: München, BY, DE, 80809 Unternehmen: BMW Group ARE YOU PREPARED FOR THE FUTURE?"
        self.assertEqual(_extract_bmw_location(text), "München, BY, DE, 80809")

    def test_extract_conrad_location(self):
        text = (
            "AI Engineer - Generative AI (m/w/d/pixelhead) fuer unsere Tochterfirma RE-IN "
            "bei RE-INvent Retail GmbH RE-INvent Retail GmbH Nuernberg Vollzeit Jetzt bewerben"
        )
        self.assertEqual(_extract_conrad_location(text, company="RE-INvent Retail GmbH"), "Nuernberg")

    def test_build_man_rss_url_quotes_search_term(self):
        self.assertEqual(
            _build_man_rss_url("https://jobs.man.eu/", "Machine Learning Engineer"),
            "https://jobs.man.eu/services/rss/job/?locale=de_DE&keywords=(Machine%20Learning%20Engineer)",
        )

    def test_parse_man_title_and_location(self):
        title, location = _parse_man_title_and_location(
            "Planer Digitalisierung/ Digitaler Zwilling in der Produktion (w/m/d) (München, DE, 80995)"
        )
        self.assertEqual(title, "Planer Digitalisierung/ Digitaler Zwilling in der Produktion (w/m/d)")
        self.assertEqual(location, "München, DE, 80995")

    def test_normalize_rss_entry_date(self):
        self.assertEqual(
            _normalize_rss_entry_date({"published": "Thu, 02 Apr 2026 2:00:00 GMT"}),
            "2026-04-02",
        )

    def test_enrich_job_description_prefers_richer_detail_text(self):
        from source import find_jobs

        original = find_jobs.fetch_arbeitsagentur_job_description
        try:
            find_jobs.fetch_arbeitsagentur_job_description = lambda url: "Das ist eine lange Detailbeschreibung mit relevanten Anforderungen " * 8
            job = make_job(
                title="AI Engineer",
                company="Demo",
                location="München",
                url="https://www.arbeitsagentur.de/jobsuche/jobdetail/12345-1-S",
                description="Kurzer Kartentext",
                source="arbeitsagentur",
            )
            enriched = enrich_job_description(job)
            self.assertGreater(len(enriched["description"]), len(job["description"]))
            self.assertIn("lange Detailbeschreibung", enriched["description"])
        finally:
            find_jobs.fetch_arbeitsagentur_job_description = original


if __name__ == "__main__":
    unittest.main()
