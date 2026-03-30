import unittest
import sys
from pathlib import Path
from unittest.mock import patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from source.company_url_resolver import resolve_company_apply_url


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
        with patch("company_url_resolver.requests.get", side_effect=requests.Timeout()):
            result = resolve_company_apply_url("https://example.com/job")
        self.assertEqual(result.failure_type, "timeout")

    def test_rate_limit_is_classified(self):
        with patch("company_url_resolver.requests.get", return_value=_Response(status_code=429)):
            result = resolve_company_apply_url("https://example.com/job")
        self.assertEqual(result.failure_type, "rate_limited")
        self.assertEqual(result.http_status, 429)

    def test_captcha_is_classified_from_html(self):
        html = "<html><body><h1>Sicherheitsabfrage</h1><p>Bitte geben Sie die Zeichen ein</p></body></html>"
        with patch("company_url_resolver.requests.get", return_value=_Response(text=html)):
            result = resolve_company_apply_url("https://www.arbeitsagentur.de/jobsuche/jobdetail/123")
        self.assertEqual(result.failure_type, "captcha_blocked")

    def test_missing_apply_link_is_classified(self):
        html = "<html><body><a href='https://www.stepstone.de/jobs'>More jobs</a></body></html>"
        with patch("company_url_resolver.requests.get", return_value=_Response(text=html)):
            result = resolve_company_apply_url("https://www.stepstone.de/stellenangebote--foo-inline.html")
        self.assertEqual(result.failure_type, "no_apply_link_found")


if __name__ == "__main__":
    unittest.main()
