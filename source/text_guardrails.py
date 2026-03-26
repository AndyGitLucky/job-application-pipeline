"""
Post-generation text guardrails for application assets.
"""

from __future__ import annotations

import re

NEGATIVE_SELF_DISCLOSURE_PATTERNS = [
    r"\bkein(?:en|em|er)?\s+(?:abgeschlossen\w*\s+)?hochschulabschluss\b",
    r"\bkein(?:en|em|er)?\s+klassisch\w*\s+hochschulabschluss\b",
    r"\bkein(?:en|em|er)?\s+studienabschluss\b",
    r"\bohne\s+(?:abgeschlossen\w*\s+)?hochschulabschluss\b",
    r"\bnur\s+weiterbildung\b",
    r"\bnicht\s+klassisch(?:er|en|em)?\s+werdegang\b",
    r"\bkein\s+klassisch(?:er|en|em)?\s+werdegang\b",
    r"\bformale\s+defizite\b",
    r"\bich\s+bringe\s+keinen\b",
    r"\bich\s+habe\s+keinen\b",
]


def find_negative_self_disclosure(text: str) -> list[str]:
    findings = []
    haystack = text or ""
    for pattern in NEGATIVE_SELF_DISCLOSURE_PATTERNS:
        match = re.search(pattern, haystack, flags=re.IGNORECASE)
        if match:
            findings.append(match.group(0))
    return findings
