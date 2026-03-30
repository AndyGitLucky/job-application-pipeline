import unittest
import sys
from pathlib import Path
import types

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("feedparser", types.SimpleNamespace())
sys.modules.setdefault("bs4", types.SimpleNamespace(BeautifulSoup=object))

from source.find_jobs import (
    deduplicate_by_content,
    invalid_job_reason,
    listing_status,
    select_best_stepstone_link,
    should_exclude_job,
)


class _FakeAnchor:
    def __init__(self, href: str):
        self.href = href

    def get(self, key: str, default=None):
        if key == "href":
            return self.href
        return default


class _FakeCard:
    def __init__(self, hrefs: list[str]):
        self.hrefs = hrefs

    def select(self, selector: str):
        return [_FakeAnchor(href) for href in self.hrefs]


class JobValidationTests(unittest.TestCase):
    def test_invalidates_stepstone_company_jobs_overview(self):
        job = {
            "title": "Machine Learning Engineer",
            "url": "https://www.stepstone.de/cmp/de/simi-reality-motion-systems-gmbh-5130649/jobs",
            "description": "Some scraped card text",
        }
        self.assertEqual(invalid_job_reason(job), "stepstone_company_listing")

    def test_select_best_stepstone_link_prefers_job_detail(self):
        card = _FakeCard(
            [
                "/cmp/de/example-company-123/jobs",
                "/stellenangebote--machine-learning-engineer-muenchen-example-123456-inline.html",
            ]
        )
        href = select_best_stepstone_link(card)
        self.assertIn("stellenangebote--machine-learning-engineer", href)

    def test_excludes_research_heavy_phd_role(self):
        job = {
            "title": "Machine Learning Scientist",
            "description": (
                "PhD in machine learning required. Strong publication record in top-tier venues. "
                "Collaborate with academic and clinical institutions and publish at scientific conferences."
            ),
        }
        self.assertTrue(should_exclude_job(job))

    def test_excludes_sales_role_early(self):
        job = {
            "title": "Sales Engineer / Vertriebsingenieur (m/w/d)",
            "description": (
                "Drive business development, customer acquisition and technical sales for AI products. "
                "Own key accounts and support presales activities."
            ),
        }
        self.assertTrue(should_exclude_job(job))

    def test_excludes_science_manager_early(self):
        job = {
            "title": "Science Manager (m/w/d) Drittmittelakquise",
            "description": (
                "Coordinate research funding proposals, Drittmittelakquise and scientific collaboration "
                "for academic programs."
            ),
        }
        self.assertTrue(should_exclude_job(job))

    def test_excludes_research_engineer_early(self):
        job = {
            "title": "Senior Research Engineer - Robot Learning",
            "description": (
                "Drive research on robot learning and publish scientific results with academic partners."
            ),
        }
        self.assertTrue(should_exclude_job(job))

    def test_excludes_thesis_role_early(self):
        job = {
            "title": "Master Thesis in Data Science",
            "description": "Abschlussarbeit in machine learning and AI prototyping.",
        }
        self.assertTrue(should_exclude_job(job))

    def test_marks_jobboard_listing_status(self):
        job = {
            "title": "AI Engineer",
            "url": "https://www.arbeitsagentur.de/jobsuche/jobdetail/123",
        }
        self.assertEqual(listing_status(job), "jobboard_listing")

    def test_marks_known_ats_as_verified_direct(self):
        job = {
            "title": "AI Engineer",
            "url": "https://company.recruitee.com/o/ai-engineer",
        }
        self.assertEqual(listing_status(job), "verified_direct")

    def test_content_dedupe_prefers_better_source(self):
        jobs = [
            {
                "id": "aa1",
                "title": "Data Engineer - Schwerpunkt AI (m/w/d)",
                "company": "FALKEN Group GmbH",
                "location": "München",
                "source": "arbeitsagentur",
                "source_url_type": "jobboard",
                "apply_url": "https://www.arbeitsagentur.de/jobsuche/jobdetail/123",
                "apply_url_type": "",
                "description": "x" * 400,
            },
            {
                "id": "cc1",
                "title": "Data Engineer Schwerpunkt AI",
                "company": "FALKEN Group",
                "location": "Munich",
                "source": "infineon",
                "source_url_type": "company_career_page",
                "apply_url": "https://example.com/jobs/123",
                "apply_url_type": "company_career_page",
                "description": "x" * 600,
            },
        ]
        deduped = deduplicate_by_content(jobs)
        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0]["id"], "cc1")


if __name__ == "__main__":
    unittest.main()
