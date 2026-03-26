import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "source"))

from text_guardrails import find_negative_self_disclosure


class TextGuardrailTests(unittest.TestCase):
    def test_detects_negative_degree_disclosure(self):
        text = "Ich bringe zwar keinen klassischen Hochschulabschluss mit, dafuer aber Praxiserfahrung."
        findings = find_negative_self_disclosure(text)
        self.assertTrue(findings)

    def test_allows_positive_positioning(self):
        text = "Ich bringe langjaehrige Industrieerfahrung, Python, SQL und ML-Deployment mit."
        findings = find_negative_self_disclosure(text)
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
