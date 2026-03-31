import unittest
import sys
from pathlib import Path
from unittest.mock import patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from source.company_url_resolver import (
    looks_like_known_ats_url,
    looks_like_specific_company_apply_url,
    resolve_company_apply_url,
)


class _Response:
    def __init__(self, text: str = "", status_code: int = 200, url: str = "https://example.com/job"):
        self.text = text
        self.status_code = status_code
        self.url = url

    def raise_for_status(self):
        if self.status_code >= 400:
            exc = requests.HTTPError(f"{self.status_code} error")
            exc.response = self
            raise exc


class CompanyUrlResolverTests(unittest.TestCase):
    def test_timeout_is_classified(self):
        with patch("source.company_url_resolver.requests.get", side_effect=requests.Timeout()):
            result = resolve_company_apply_url("https://example.com/job")
        self.assertEqual(result.failure_type, "timeout")

    def test_timeout_can_fallback_to_search(self):
        with patch("source.company_url_resolver.requests.get", side_effect=requests.Timeout()):
            with patch("source.company_url_resolver._search_company_apply_url", return_value="https://noxon.io/career/"):
                result = resolve_company_apply_url(
                    "https://example.com/job",
                    company="Noxon GmbH",
                    title="Junior Produktentwickler",
                )
        self.assertEqual(result.source, "search")
        self.assertEqual(result.url, "https://noxon.io/career/")

    def test_rate_limit_is_classified(self):
        with patch("source.company_url_resolver.requests.get", return_value=_Response(status_code=429)):
            result = resolve_company_apply_url("https://example.com/job")
        self.assertEqual(result.failure_type, "rate_limited")
        self.assertEqual(result.http_status, 429)

    def test_captcha_is_classified_from_html(self):
        html = "<html><body><h1>Sicherheitsabfrage</h1><p>Bitte geben Sie die Zeichen ein</p></body></html>"
        with patch("source.company_url_resolver.requests.get", return_value=_Response(text=html)):
            result = resolve_company_apply_url("https://www.arbeitsagentur.de/jobsuche/jobdetail/123")
        self.assertEqual(result.failure_type, "captcha_blocked")

    def test_missing_apply_link_is_classified(self):
        html = "<html><body><a href='https://www.stepstone.de/jobs'>More jobs</a></body></html>"
        with patch("source.company_url_resolver.requests.get", return_value=_Response(text=html)):
            result = resolve_company_apply_url("https://www.stepstone.de/stellenangebote--foo-inline.html")
        self.assertEqual(result.failure_type, "no_apply_link_found")

    def test_html_failure_can_fallback_to_search(self):
        html = "<html><body><h1>Die Website ist nicht erreichbar</h1></body></html>"
        with patch("source.company_url_resolver.requests.get", return_value=_Response(text=html)):
            with patch("source.company_url_resolver._search_company_apply_url", return_value="https://noxon.io/career/"):
                result = resolve_company_apply_url(
                    "https://www.stepstone.de/stellenangebote--foo-inline.html",
                    company="Noxon GmbH",
                    title="Junior Produktentwickler",
                )
        self.assertEqual(result.source, "search")
        self.assertEqual(result.url, "https://noxon.io/career/")

    def test_no_apply_link_can_fallback_to_search(self):
        html = "<html><body><a href='https://www.stepstone.de/jobs'>More jobs</a></body></html>"
        with patch("source.company_url_resolver.requests.get", return_value=_Response(text=html)):
            with patch("source.company_url_resolver._search_company_apply_url", return_value="https://join.com/companies/noxonio/job"):
                result = resolve_company_apply_url(
                    "https://www.stepstone.de/stellenangebote--foo-inline.html",
                    company="Noxon GmbH",
                    title="Junior Produktentwickler",
                )
        self.assertEqual(result.source, "search")
        self.assertEqual(result.url, "https://join.com/companies/noxonio/job")

    def test_generic_career_page_is_not_specific_job_url(self):
        self.assertFalse(
            looks_like_specific_company_apply_url(
                "https://www.bridging-it.de/karriere/das-bietet-bridgingit/",
                "Data Engineers, Analysts & Scientists (w|m|d)",
            )
        )

    def test_concrete_join_job_url_counts_as_specific(self):
        self.assertTrue(
            looks_like_specific_company_apply_url(
                "https://join.com/companies/noxonio/15877071-junior-product-engineer-wearables-full-time-munich-germany",
                "Junior Product Engineer Wearables",
            )
        )

    def test_recruitee_url_counts_as_known_ats(self):
        self.assertTrue(looks_like_known_ats_url("https://demo.recruitee.com/o/ai-engineer"))


if __name__ == "__main__":
    unittest.main()
