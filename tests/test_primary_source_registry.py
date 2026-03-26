import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "source"))

from primary_source_registry import infer_primary_source, remember_primary_source


class PrimarySourceRegistryTests(unittest.TestCase):
    def test_infer_greenhouse_source(self):
        source = infer_primary_source(
            "https://boards.greenhouse.io/examplecompany/jobs/12345",
            company="Example Company",
            location="Munich",
        )
        self.assertEqual(source["type"], "greenhouse")
        self.assertEqual(source["board_token"], "examplecompany")

    def test_infer_recruitee_source(self):
        source = infer_primary_source(
            "https://nucsai.recruitee.com/o/machine-learning-scientist",
            company="Nucs AI",
            location="Munich",
        )
        self.assertEqual(source["type"], "recruitee")
        self.assertEqual(source["subdomain"], "nucsai")

    def test_remember_primary_source_deduplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "primary_sources.json"
            path.write_text("[]", encoding="utf-8")

            remember_primary_source(
                "https://jobs.lever.co/example/abc",
                company="Example",
                location="Munich",
                path=path,
            )
            remember_primary_source(
                "https://jobs.lever.co/example/def",
                company="Example",
                location="Munich",
                path=path,
            )

            stored = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(len(stored), 1)
            self.assertEqual(stored[0]["type"], "lever")
            self.assertEqual(stored[0]["site"], "example")
