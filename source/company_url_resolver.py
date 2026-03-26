"""
company_url_resolver.py
======================
Best-effort Resolver fuer Jobboard-URLs (Indeed/StepStone/Arbeitsagentur, ...),
um einen "Apply on company site" / ATS-Link zu finden.

Strategie:
1) Ohne Netzwerk: URLs aus der Jobbeschreibung extrahieren (falls vorhanden).
2) Optional mit Netzwerk: Jobboard-Seite laden und externe Links heuristisch bewerten.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup
from requests import RequestException


_URL_RE = re.compile(r"https?://[^\s)>\"]+", re.IGNORECASE)


_BAD_HOST_HINTS = {
    "indeed.",
    "stepstone.",
    "arbeitsagentur.de",
    "google.",
    "linkedin.",
    "facebook.",
    "instagram.",
    "tiktok.",
    "x.com",
    "twitter.",
    "youtube.",
}

_GOOD_PATH_HINTS = {
    "apply",
    "application",
    "bewerb",
    "bewerbung",
    "career",
    "careers",
    "job",
    "jobs",
    "stellen",
    "karriere",
    "recruit",
    "recruiting",
}

_GOOD_ATS_HOST_HINTS = {
    "personio.",
    "greenhouse.io",
    "lever.co",
    "workable.com",
    "successfactors.",
    "smartrecruiters.",
    "myworkdayjobs.",
    "workday.",
}


def _norm_host(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _score_candidate(url: str) -> int:
    if not url:
        return -10_000
    host = _norm_host(url)
    path = (urlparse(url).path or "").lower()

    score = 0
    if any(hint in host for hint in _GOOD_ATS_HOST_HINTS):
        score += 100
    if any(hint in host for hint in _BAD_HOST_HINTS):
        score -= 50
    if any(hint in path for hint in _GOOD_PATH_HINTS):
        score += 20

    # Strong preference for concrete job posting URLs (avoid "Current openings" landing pages).
    if "greenhouse.io" in host and "/jobs/" in path:
        score += 40
        if re.search(r"/jobs/\\d+", path):
            score += 40

    # Prefer HTTPS.
    if url.lower().startswith("https://"):
        score += 2

    # Penalize very short / root-only links.
    if path in {"", "/"}:
        score -= 5

    return score


def extract_urls(text: str) -> list[str]:
    if not text:
        return []
    urls = _URL_RE.findall(text)
    # Strip trailing punctuation.
    cleaned = []
    for u in urls:
        u = u.rstrip(".,;]")
        cleaned.append(u)
    # Preserve order, unique.
    seen = set()
    out = []
    for u in cleaned:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def best_url(urls: Iterable[str]) -> str | None:
    best = None
    best_score = -10_000
    for u in urls:
        s = _score_candidate(u)
        if s > best_score:
            best = u
            best_score = s
    if best_score <= 0:
        return None
    return best


@dataclass
class ResolveResult:
    url: str | None
    source: str  # "description" | "html" | "none"
    failure_type: str = ""
    detail: str = ""
    http_status: int = 0


def resolve_company_apply_url(job_url: str, description: str = "") -> ResolveResult:
    # 1) No network: try from description.
    candidate = best_url(extract_urls(description or ""))
    if candidate:
        return ResolveResult(url=candidate, source="description")

    # 2) Optional network: fetch HTML and scan anchors.
    if os.getenv("AUTO_APPLY_RESOLVE_COMPANY_URL", "true").strip().lower() not in {"1", "true", "yes", "on"}:
        return ResolveResult(url=None, source="none", failure_type="resolver_disabled", detail="AUTO_APPLY_RESOLVE_COMPANY_URL=false")

    timeout = int(os.getenv("AUTO_APPLY_RESOLVE_TIMEOUT", "12"))
    max_bytes = int(os.getenv("AUTO_APPLY_RESOLVE_MAX_BYTES", str(2_000_000)))
    headers = {
        "User-Agent": os.getenv(
            "AUTO_APPLY_RESOLVE_UA",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36",
        )
    }

    try:
        resp = requests.get(job_url, headers=headers, timeout=timeout, allow_redirects=True)
        http_status = int(resp.status_code)
        resp.raise_for_status()
        html = resp.text
        if len(html.encode("utf-8", errors="ignore")) > max_bytes:
            html = html[: max_bytes // 2]
    except requests.Timeout:
        return ResolveResult(url=None, source="none", failure_type="timeout", detail=f"timeout={timeout}s")
    except requests.HTTPError as exc:
        response = getattr(exc, "response", None)
        status = int(getattr(response, "status_code", 0) or 0)
        failure_type = _failure_type_from_http(status)
        return ResolveResult(url=None, source="none", failure_type=failure_type, detail=str(exc), http_status=status)
    except RequestException as exc:
        failure_type = _failure_type_from_exception(exc)
        return ResolveResult(url=None, source="none", failure_type=failure_type, detail=str(exc))
    except Exception as exc:
        return ResolveResult(url=None, source="none", failure_type="request_error", detail=str(exc))

    soup = BeautifulSoup(html, "lxml")
    links = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href:
            continue
        abs_url = urljoin(resp.url, href)
        # Only keep http(s)
        if not abs_url.lower().startswith(("http://", "https://")):
            continue
        links.append(abs_url)

    html_failure = _failure_type_from_html(resp.url, html)
    if html_failure:
        return ResolveResult(url=None, source="html", failure_type=html_failure, detail=f"url={resp.url}", http_status=http_status)

    candidate = best_url(links)
    if candidate:
        return ResolveResult(url=candidate, source="html")
    return ResolveResult(
        url=None,
        source="html",
        failure_type="no_apply_link_found",
        detail=f"anchors={len(links)}",
        http_status=http_status,
    )


def _failure_type_from_http(status: int) -> str:
    if status == 403:
        return "http_forbidden"
    if status == 404:
        return "dead_listing"
    if status == 429:
        return "rate_limited"
    if 500 <= status < 600:
        return "source_unstable"
    return "http_error"


def _failure_type_from_exception(exc: RequestException) -> str:
    text = str(exc).lower()
    if "http2" in text:
        return "jobboard_unstable"
    if "timed out" in text or "timeout" in text:
        return "timeout"
    if "connection aborted" in text or "connection reset" in text:
        return "source_unstable"
    if "name or service not known" in text or "failed to establish a new connection" in text:
        return "network_error"
    if "ssl" in text or "certificate" in text:
        return "tls_error"
    return "request_error"


def _failure_type_from_html(final_url: str, html: str) -> str:
    haystack = " ".join([final_url or "", html[:20000]]).lower()
    if "captcha" in haystack or "sicherheitsabfrage" in haystack:
        return "captcha_blocked"
    if "cloudflare" in haystack or "attention required" in haystack:
        return "bot_protection"
    if "cookie" in haystack and "zustimmen" in haystack and "bewerb" in haystack:
        return "consent_required"
    if "unfortunately, the job or website you selected is no longer available" in haystack:
        return "listing_redirected_or_removed"
    if "die website ist nicht erreichbar" in haystack or "site can't be reached" in haystack:
        return "source_unstable"
    return ""
