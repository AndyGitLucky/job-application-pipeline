"""
find_jobs.py
============
Sucht Jobs auf Indeed (RSS), Stepstone und der Bundesagentur für Arbeit API.
Gibt eine Liste von Job-Dicts zurück und speichert sie als jobs_raw.json.

Abhängigkeiten:
    pip install requests beautifulsoup4 feedparser lxml
"""

import json
import os
import time
import hashlib
import logging
import math
import re
import html
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
import feedparser
from bs4 import BeautifulSoup
if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from source.env_utils import load_dotenv
from source.job_url_normalizer import normalize_job_url
from source.link_extractor import annotate_job_links
from source.project_paths import (
    config_path,
    resolve_config_path,
    resolve_runtime_path,
    runtime_path,
    source_path,
)

# --- Logging -------------------------------------------------------------------
log = logging.getLogger(__name__)

load_dotenv(Path(__file__))

# --- Konfiguration -------------------------------------------------------------
CONFIG = {
    "search_terms": [
        "Data Scientist",
        "ML Engineer",
        "Machine Learning Engineer",
        "Data Analyst",
        "Applied Data Scientist",
        "AI Engineer",
    ],
    "location": "München",
    "location_strategy": "munich_only",  # munich_only | prefer_munich | all
    "priority_locations": ["muenchen", "münchen"],
    "radius_km": 30,
    "output_file": str(runtime_path("jobs_raw.json")),
    "primary_sources_file": os.getenv("PRIMARY_SOURCES_FILE", str(config_path("primary_sources.json"))),
    "company_search_sources_file": os.getenv("COMPANY_SEARCH_SOURCES_FILE", str(config_path("company_search_sources.json"))),
    "request_delay": 1.5,      # Sekunden zwischen Requests (fair use)
    "bmw_detail_request_limit": 10,
    "bmw_cache_ttl_hours": 12,
    "bmw_url_cache_file": str(runtime_path("cache", "bmw_job_urls.json")),
    "bmw_detail_cache_file": str(runtime_path("cache", "bmw_job_details.json")),
    "headers": {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )
    },
}

# --- Hilfsfunktionen -----------------------------------------------------------

def job_id(url: str) -> str:
    """Stabiler Deduplizierungs-Key aus URL."""
    return hashlib.md5(url.encode()).hexdigest()[:12]


def _safe_text_value(value: object, fallback: str = "") -> str:
    if value is None:
        return fallback
    if isinstance(value, float) and math.isnan(value):
        return fallback
    text = str(value).strip()
    return fallback if text.lower() == "nan" else text


def _cache_now() -> datetime:
    return datetime.now()


def _cache_cutoff() -> datetime:
    return _cache_now().timestamp() - (CONFIG["bmw_cache_ttl_hours"] * 3600)


def _load_json_cache(path: str) -> dict:
    cache_path = resolve_runtime_path(path)
    if not cache_path.exists():
        return {}
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _save_json_cache(path: str, payload: dict) -> None:
    cache_path = resolve_runtime_path(path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _cache_is_fresh(timestamp: object) -> bool:
    if not timestamp:
        return False
    try:
        return datetime.fromisoformat(str(timestamp)).timestamp() >= _cache_cutoff()
    except Exception:
        return False


def clean_job_title(title: str) -> str:
    """Entfernt Suchergebnis-Praefixe und andere Scraper-Artefakte aus Jobtiteln."""
    cleaned = title.strip()
    cleaned = re.sub(r"^\s*\d+\.\s*Ergebnis:\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^\s*Ergebnis:\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" -|")


def clean_company_name(company: str) -> str:
    cleaned = company.strip()
    cleaned = re.sub(r"^\s*Arbeitgeber:\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" -|:")


def extract_company_from_text(text: str) -> str:
    match = re.search(
        r"Arbeitgeber:\s*(.+?)(?=\s+(?:Arbeitsort:|Anstellungsart:|Beginn\b|Befristung:)|\s+\d+\s*[€EUR]|\s*$)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    return clean_company_name(match.group(1))


def make_job(
    title,
    company,
    location,
    url,
    description,
    source,
    date=None,
    *,
    discovery_url: str | None = None,
    apply_url: str | None = None,
    source_url_type: str = "jobboard",
    apply_url_type: str = "",
):
    raw_url = (url or "").strip()
    discovery_url = normalize_job_url(discovery_url or raw_url, source=source)
    apply_url = normalize_job_url(apply_url or raw_url, source=source)
    canonical_url = normalize_job_url(raw_url, source=source)
    return {
        "id":          job_id(canonical_url or raw_url),
        "title":       clean_job_title(title),
        "company":     clean_company_name(company),
        "location":    location.strip(),
        "url":         canonical_url,
        "discovery_url": discovery_url,
        "apply_url":   apply_url,
        "source_url_type": source_url_type,
        "apply_url_type": apply_url_type,
        "description": description.strip()[:2000],  # Länge begrenzen
        "source":      source,
        "date":        date or datetime.today().strftime("%Y-%m-%d"),
        "score":       None,   # wird von score_jobs.py befüllt
        "filtered":    False,
        "job_status":  "candidate",
        "listing_status": "unverified",
        "validation_reason": "",
    }


def deduplicate(jobs: list) -> list:
    seen = set()
    unique = []
    for job in jobs:
        if job["id"] not in seen:
            seen.add(job["id"])
            unique.append(job)
    return deduplicate_by_content(unique)


def deduplicate_by_content(jobs: list) -> list:
    grouped: dict[tuple[str, str, str], list[dict]] = {}
    passthrough = []

    for job in jobs:
        key = content_dedupe_key(job)
        if key is None:
            passthrough.append(job)
            continue
        grouped.setdefault(key, []).append(job)

    deduped = list(passthrough)
    for group in grouped.values():
        best = max(group, key=job_source_rank_tuple)
        deduped.append(best)
    return deduped


def content_dedupe_key(job: dict) -> tuple[str, str, str] | None:
    company = normalize_company_for_dedupe(job.get("company", ""))
    title = normalize_title_for_dedupe(job.get("title", ""))
    location = normalize_location_for_dedupe(job.get("location", ""))
    if not company or not title or not location:
        return None
    return (company, title, location)


def normalize_company_for_dedupe(company: str) -> str:
    text = (company or "").lower().strip()
    text = _repair_known_mojibake(text)
    text = _normalize_unicode_like_text(text)
    text = text.replace("&", " and ")
    text = re.sub(r"\bgroup\b", " ", text)
    text = re.sub(r"\bbayerische motoren werke\b", " bmw ", text)
    text = re.sub(r"\bbmw group\b", " bmw ", text)
    text = re.sub(r"\bbmw ag\b", " bmw ", text)
    text = re.sub(r"\b(gmbh|ag|se|inc|llc|kg|co|mbh|corporation|corp)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_title_for_dedupe(title: str) -> str:
    text = clean_job_title(title or "").lower()
    text = _repair_known_mojibake(text)
    text = _normalize_unicode_like_text(text)
    text = re.sub(r"\((?:m|w|d|f|x|div|gn|all genders|all gender)[^)]*\)", " ", text, flags=re.IGNORECASE)
    text = text.replace("&", " and ")
    text = re.sub(r"\bml\s+ops\b", " mlops ", text)
    text = re.sub(r"\bm l ops\b", " mlops ", text)
    text = re.sub(r"\bai\s*/\s*ml\b", " ai ml ", text)
    text = re.sub(r"\bml\s*/\s*ai\b", " ai ml ", text)
    text = re.sub(r"\bmachine learning operations\b", " mlops ", text)
    text = text.replace("/", " ")
    text = text.replace("|", " ")
    text = re.sub(r"[\-–—:]", " ", text)
    text = re.sub(r"\b(senior|junior|lead|principal|staff)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_location_for_dedupe(location: str) -> str:
    text = (location or "").lower().strip()
    text = _repair_known_mojibake(text)
    text = _normalize_unicode_like_text(text)
    text = (
        text.replace("münchen", "munich")
        .replace("muenchen", "munich")
    )
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _repair_known_mojibake(text: str) -> str:
    return (
        text.replace("mã¼nchen", "münchen")
        .replace("ã¼", "ü")
        .replace("ã¶", "ö")
        .replace("ã¤", "ä")
        .replace("ãß", "ß")
    )


def _normalize_unicode_like_text(text: str) -> str:
    return text.replace("ü", "ue").replace("ö", "oe").replace("ä", "ae").replace("ß", "ss")


def job_source_rank_tuple(job: dict) -> tuple[int, int, int, int]:
    return (
        source_type_rank(job),
        source_rank(job),
        apply_url_rank(job),
        description_length_rank(job),
    )


def source_type_rank(job: dict) -> int:
    source_url_type = (job.get("source_url_type") or "").strip().lower()
    if source_url_type == "known_ats":
        return 5
    if source_url_type == "company_career_page":
        return 4
    if source_url_type == "jobboard":
        return 2
    return 1


def source_rank(job: dict) -> int:
    source = (job.get("source") or "").strip().lower()
    if source in {"greenhouse", "lever", "recruitee"}:
        return 6
    if source in {"infineon", "siemens_energy", "swm"} or source.startswith("direct_"):
        return 5
    if source == "arbeitsagentur":
        return 4
    if source == "stepstone":
        return 3
    if source == "indeed":
        return 2
    if source == "xing":
        return 1
    return 0


def apply_url_rank(job: dict) -> int:
    apply_url_type = (job.get("apply_url_type") or "").strip().lower()
    if apply_url_type in {"greenhouse", "lever", "recruitee"}:
        return 3
    if apply_url_type == "company_career_page":
        return 2
    return 1 if job.get("apply_url") else 0


def description_length_rank(job: dict) -> int:
    length = len((job.get("description") or "").strip())
    if length >= 500:
        return 3
    if length >= 180:
        return 2
    if length >= 60:
        return 1
    return 0


def enrich_job_descriptions(jobs: list) -> list:
    enriched = []
    for job in jobs:
        enriched.append(enrich_job_description(job))
    return enriched


def enrich_job_description(job: dict) -> dict:
    description = (job.get("description") or "").strip()
    if len(description) >= 250:
        return job

    url = (job.get("url") or "").strip()
    source = (job.get("source") or "").strip().lower()

    detail_text = ""
    if source == "arbeitsagentur" and "/jobsuche/jobdetail/" in url:
        detail_text = fetch_arbeitsagentur_job_description(url)
    elif should_fetch_generic_detail(job):
        detail_text = fetch_generic_job_detail_text(url)

    detail_text = (detail_text or "").strip()
    if len(detail_text) > len(description):
        updated = dict(job)
        updated["description"] = detail_text[:2000]
        return updated
    return job


def should_fetch_generic_detail(job: dict) -> bool:
    url = (job.get("url") or "").strip().lower()
    source = (job.get("source") or "").strip().lower()
    source_url_type = (job.get("source_url_type") or "").strip().lower()
    if not url:
        return False
    if source in {"indeed", "stepstone", "linkedin", "xing"}:
        return False
    if source_url_type in {"known_ats", "company_career_page"}:
        return True
    return any(token in url for token in ["/job/", "/jobs/", "/career", "/careers", "/karriere"])


def fetch_arbeitsagentur_job_description(url: str) -> str:
    try:
        r = requests.get(url, headers=CONFIG["headers"], timeout=20)
        r.raise_for_status()
    except Exception:
        return ""

    soup = BeautifulSoup(r.text, "lxml")
    text = ""

    for selector in [
        "main",
        "[data-testid='job-details']",
        "[class*='jobdetail']",
        "[class*='stellenbeschreibung']",
        "[class*='beschreibung']",
    ]:
        node = soup.select_one(selector)
        if node:
            candidate = _html_to_text(node.get_text(separator=" ", strip=True))
            if len(candidate) > len(text):
                text = candidate

    if len(text) < 250:
        text = extract_jobposting_description(soup) or text

    if len(text) < 250:
        text = _html_to_text(soup.get_text(separator=" ", strip=True)[:20000])

    return text[:12000]


def fetch_generic_job_detail_text(url: str) -> str:
    try:
        r = requests.get(url, headers=CONFIG["headers"], timeout=20)
        r.raise_for_status()
    except Exception:
        return ""

    soup = BeautifulSoup(r.text, "lxml")
    text = extract_jobposting_description(soup)
    if text and len(text) >= 250:
        return text[:12000]

    for selector in ["main", "[role='main']", "article", ".job-description", ".jobdetail", ".description"]:
        node = soup.select_one(selector)
        if node:
            text = _html_to_text(node.get_text(separator=' ', strip=True))
            if len(text) >= 250:
                return text[:12000]

    return _html_to_text(soup.get_text(separator=" ", strip=True)[:12000])


def extract_jobposting_description(soup: BeautifulSoup) -> str:
    for script in soup.select("script[type='application/ld+json']"):
        raw = (script.string or script.get_text() or "").strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        candidates = payload if isinstance(payload, list) else [payload]
        for item in candidates:
            if not isinstance(item, dict):
                continue
            if item.get("@type") == "JobPosting":
                description = item.get("description") or ""
                if description:
                    return _html_to_text(html.unescape(str(description)))
    return ""


def source_counts(jobs: list) -> dict[str, int]:
    counts: dict[str, int] = {}
    for job in jobs:
        source = (job.get("source") or "unknown").strip() or "unknown"
        counts[source] = counts.get(source, 0) + 1
    return counts


EXCLUDED_JOB_PATTERNS = [
    r"\bphd\b",
    r"\bph\.d\b",
    r"\bdoctor(?:al|ate)?\b",
    r"\bdoktorand(?:in)?\b",
    r"\bintern(?:ship)?s?\b",
    r"\bpraktik(?:um|ant|antin)\b",
    r"\bstudentische?\s+aushilfe\b",
    r"\bstudent\s+assistant\b",
    r"\bstudent\s+worker\b",
    r"\bstudent(?:in)?\b",
    r"\bworking student\b",
    r"\bwerkstudent(?:in)?\b",
    r"\bsales\b",
    r"\bvertrieb\b",
    r"\bbusiness development\b",
    r"\baccount executive\b",
    r"\baccount manager\b",
    r"\bkey account\b",
    r"\bkey account manager\b",
    r"\bsales manager\b",
    r"\bvertriebsingenieur\b",
    r"\bsales engineer\b",
    r"\bpresales\b",
    r"\bpre-sales\b",
    r"\btechnical sales\b",
    r"\bscience manager\b",
    r"\bdrittmittelakquise\b",
    r"\bprincipal researcher\b",
    r"\bresearch engineer\b",
    r"\babschlussarbeit\b",
    r"\bthesis\b",
    r"\bmaster(?:'s)? thesis\b",
    r"\bbachelor(?:'s)? thesis\b",
]

RESEARCH_EXCLUSION_PATTERNS = [
    r"\bphd\s+(?:in|is|required|preferred)\b",
    r"\bstrong publication record\b",
    r"\bpublication record\b",
    r"\bpeer[- ]reviewed science\b",
    r"\btop-tier venues\b",
    r"\bscientific conferences\b",
    r"\bacademic and clinical institutions\b",
    r"\bacademic research partners\b",
    r"\bresearch collaborations\b",
    r"\bclinical validation studies\b",
    r"\bprincipal investigator\b",
    r"\bpostdoc(?:toral)?\b",
]


def should_exclude_job(job: dict) -> bool:
    """Filtert PhD-, Internship- und Werkstudenten-Rollen vor dem Scoring aus."""
    haystack = " ".join([
        job.get("title", ""),
        job.get("description", "")[:2000],
    ])
    exclusion_patterns = EXCLUDED_JOB_PATTERNS + RESEARCH_EXCLUSION_PATTERNS
    return any(re.search(pattern, haystack, flags=re.IGNORECASE) for pattern in exclusion_patterns)


def filter_jobs(jobs: list) -> tuple[list, list]:
    kept = []
    excluded = []
    for job in jobs:
        if should_exclude_job(job):
            excluded.append(job)
        else:
            kept.append(job)
    return kept, excluded


def is_priority_location(job: dict) -> bool:
    location = (job.get("location") or "").lower()
    return any(keyword in location for keyword in CONFIG["priority_locations"])


def apply_location_strategy(jobs: list) -> tuple[list, int]:
    strategy = CONFIG.get("location_strategy", "all")

    if strategy == "all":
        return jobs, 0

    priority_jobs = [job for job in jobs if is_priority_location(job)]
    other_jobs = [job for job in jobs if not is_priority_location(job)]

    if strategy == "munich_only":
        return priority_jobs, len(other_jobs)

    if strategy == "prefer_munich":
        return priority_jobs + other_jobs, 0

    log.warning(f"Unbekannte location_strategy={strategy!r} - verwende 'all'")
    return jobs, 0


def validate_jobs(jobs: list) -> tuple[list, list]:
    live = []
    invalid = []
    for job in jobs:
        reason = invalid_job_reason(job)
        if reason:
            job["job_status"] = "invalid"
            job["listing_status"] = "invalid"
            job["validation_reason"] = reason
            invalid.append(job)
        else:
            job["job_status"] = "live"
            job["listing_status"] = listing_status(job)
            job["validation_reason"] = ""
            live.append(job)
    return live, invalid


def listing_status(job: dict) -> str:
    url = (job.get("apply_url") or job.get("url") or "").strip().lower()
    if not url:
        return "invalid"
    source_url_type = (job.get("source_url_type") or "").strip().lower()
    if source_url_type in {"known_ats", "company_career_page", "primary"}:
        return "verified_direct"
    if _looks_like_known_ats_url(url):
        return "verified_direct"
    if _is_jobboard_url(url):
        return "jobboard_listing"
    return "direct_listing"


def invalid_job_reason(job: dict) -> str:
    url = (job.get("url") or "").lower()
    description = (job.get("description") or "").lower()
    title = (job.get("title") or "").strip()

    if not title:
        return "missing_title"
    if not url.startswith(("http://", "https://")):
        return "missing_job_url"
    if "stepstone.de/cmp/" in url and url.rstrip("/").endswith("/jobs"):
        return "stepstone_company_listing"
    if any(marker in description for marker in ["es passt gerade kein job", "kein job zu deiner suche"]):
        return "empty_results_page"
    if "jobs" in urlparse(url).path.lower() and "/cmp/" in url:
        return "company_jobs_overview"
    return ""


def _host(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _is_jobboard_url(url: str) -> bool:
    host = _host(url)
    return any(
        hint in host
        for hint in (
            "indeed.",
            "stepstone.",
            "arbeitsagentur.de",
            "linkedin.",
            "xing.",
            "jobware.",
            "monster.",
        )
    )


def _looks_like_known_ats_url(url: str) -> bool:
    host = _host(url)
    return any(
        hint in host
        for hint in (
            "personio.",
            "greenhouse.io",
            "lever.co",
            "workable.com",
            "successfactors.",
            "smartrecruiters.",
            "myworkdayjobs.",
            "workday.",
            "recruitee.com",
        )
    )


def select_best_stepstone_link(card) -> str:
    best_href = ""
    best_score = -10_000
    for anchor in card.select("a[href]"):
        href = (anchor.get("href") or "").strip()
        if not href:
            continue
        href_l = href.lower()
        score = 0
        if "stellenangebote--" in href_l:
            score += 120
        if "/job/" in href_l:
            score += 100
        if "/cmp/" in href_l and href_l.rstrip("/").endswith("/jobs"):
            score -= 150
        if "click" in href_l or "apply" in href_l:
            score += 10
        if href_l.startswith("/"):
            score += 2
        if score > best_score:
            best_score = score
            best_href = href
    return best_href


# --- Source 1: JobSpy (LinkedIn + Indeed + Google Jobs) ------------------------------------------------------

def fetch_jobspy(term: str, location: str) -> list:
    """
    JobSpy – scrapt LinkedIn, Indeed und Google Jobs gleichzeitig.
    pip install jobspy
    Kein API-Key nötig, aktiv gewartet (2025).
    """
    log.info(f"JobSpy (LinkedIn+Indeed): {term!r}")
    try:
        from jobspy import scrape_jobs
        df = scrape_jobs(
            site_name=["linkedin", "indeed"],
            search_term=term,
            location=location,
            results_wanted=25,
            hours_old=72,
            country_indeed="Germany",
            verbose=0,
        )
        jobs = []
        for _, row in df.iterrows():
            jobs.append(make_job(
                title=_safe_text_value(row.get("title", "")),
                company=_safe_text_value(row.get("company", "")),
                location=_safe_text_value(row.get("location", location), location),
                url=_safe_text_value(row.get("job_url", "")),
                description=_safe_text_value(row.get("description", "") or "")[:2000],
                source=_safe_text_value(row.get("site", "jobspy"), "jobspy"),
                date=_safe_text_value(row.get("date_posted", ""))[:10],
            ))
        log.info(f"  → {len(jobs)} Jobs gefunden")
        return jobs
    except ImportError:
        log.warning("  JobSpy nicht installiert. Bitte: pip install jobspy")
        return []
    except Exception as e:
        log.warning(f"  JobSpy Fehler: {e}")
        return []

# --- Source 2: Bundesagentur für Arbeit (offizielle API) ----------------------

def fetch_arbeitsagentur(term: str, location: str) -> list:
    """
    Scrapet die Arbeitsagentur-Jobsuche via Selenium.
    Die Seite ist JavaScript-gerendert – requests allein reicht nicht.
    URL: https://www.arbeitsagentur.de/jobsuche/suche?was=...&wo=...
    """
    log.info(f"Arbeitsagentur: {term!r}")
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        import logging as _logging
        _logging.getLogger("WDM").setLevel(_logging.ERROR)

        url = (
            f"https://www.arbeitsagentur.de/jobsuche/suche"
            f"?was={requests.utils.quote(term)}"
            f"&wo={requests.utils.quote(location)}"
            f"&umkreis={CONFIG['radius_km']}"
            f"&angebotsart=1"
        )

        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument(f"user-agent={CONFIG['headers']['User-Agent']}")

        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options,
        )

        jobs = []
        try:
            driver.get(url)
            # Cookie-Banner wegklicken falls vorhanden
            try:
                WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR,
                        "button[data-pp-leuaid='cookie-einstellungen-bestaetigen'], "
                        "button[class*='cookie'], button[id*='cookie']"))
                ).click()
            except Exception:
                pass

            # Warten bis Jobkarten geladen sind
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR,
                    "app-ergebnis-liste-item, [class*='ergebnis'], [data-testid*='job']"))
            )
            time.sleep(2)

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(driver.page_source, "lxml")

            # Arbeitsagentur nutzt Angular – Selektoren können sich ändern
            cards = (
                soup.select("app-ergebnis-liste-item") or
                soup.select("[class*='ergebnisliste-item']") or
                soup.select("[class*='job-result']")
            )

            for card in cards:
                title_el   = (card.select_one("h3, h2, [class*='titel'], [class*='title']"))
                company_el = (card.select_one("[class*='arbeitgeber'], [class*='company'], [class*='firma']"))
                link_el    = card.select_one("a[href]")
                card_text  = card.get_text(separator=" ", strip=True)

                title   = title_el.get_text(strip=True)   if title_el   else ""
                company = company_el.get_text(strip=True)  if company_el else ""
                company = clean_company_name(company) or extract_company_from_text(card_text)
                href    = link_el["href"]                  if link_el    else url

                if not href.startswith("http"):
                    href = "https://www.arbeitsagentur.de" + href

                if title:
                    jobs.append(make_job(
                        title=title,
                        company=company,
                        location=location,
                        url=href,
                        description=card_text[:1000],
                        source="arbeitsagentur",
                    ))
        finally:
            driver.quit()

        log.info(f"  → {len(jobs)} Jobs gefunden")
        return jobs

    except Exception as e:
        log.warning(f"  Arbeitsagentur Fehler: {e}")
        return []


# --- Source 3: Stepstone (HTML-Scraping) --------------------------------------

def fetch_stepstone(term: str, location: str) -> list:
    """
    Stepstone hat keine offizielle API – wir scrapen die Suchergebnisseite.
    Hinweis: Stepstone ändert gelegentlich ihre HTML-Struktur.
    """
    url = (
        f"https://www.stepstone.de/jobs/{requests.utils.quote(term.replace(' ', '-'))}"
        f"/in-{requests.utils.quote(location.replace(' ', '-'))}"
    )
    log.info(f"Stepstone: {term!r}")
    try:
        r = requests.get(url, headers=CONFIG["headers"], timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")

        jobs = []
        # Stepstone job cards (Selektor kann sich ändern)
        cards = soup.select("article[data-at='job-item']")
        if not cards:
            # Fallback-Selektor
            cards = soup.select("[class*='JobCard']")

        for card in cards:
            title_el   = card.select_one("[data-at='job-item-title']") or card.select_one("h2")
            company_el = card.select_one("[data-at='job-item-company-name']") or card.select_one("[class*='company']")
            href       = select_best_stepstone_link(card)

            if not (title_el and href):
                continue

            if not href.startswith("http"):
                href = "https://www.stepstone.de" + href

            jobs.append(make_job(
                title=title_el.get_text(),
                company=company_el.get_text() if company_el else "",
                location=location,
                url=href,
                description=card.get_text(separator=" "),
                source="stepstone",
            ))

        log.info(f"  → {len(jobs)} Jobs gefunden")
        return jobs
    except Exception as e:
        log.warning(f"  Stepstone Fehler: {e}")
        return []


# --- Source 4: Firmenseiten direkt (erweiterbar) ------------------------------

DIRECT_SOURCES = [
    {
        "name":     "KONUX",
        "url":      "https://www.konux.com/careers/",
        "selector": "a[href*='job'], a[href*='career'], h3, h2",
    },
    {
        "name":     "TWAICE",
        "url":      "https://twaice.com/careers/",
        "selector": "a[href*='job'], h3",
    },
    {
        "name":     "Blickfeld",
        "url":      "https://www.blickfeld.com/company/careers/",
        "selector": "a[href*='job'], h3",
    },
    {
        "name":     "Agile Robots (Personio)",
        "url":      "https://agile-robots-se.jobs.personio.de/?filters=eyJvZmZpY2VfaWQiOlszODI5MjUsMzc4OTMxN10sImVtcGxveW1lbnRfdHlwZSI6WyJwZXJtYW5lbnQiXSwic3ViY29tcGFueV9pZCI6WzE3Njg0XX0=",
        "selector": "a[href*='job'], a[href*='/job/'], h3, h2",
    },
]

DIRECT_SOURCE_BLOCKLIST = [
    "career",
    "careers",
    "learn about careers",
    "life at",
    "recruitment process",
    "tech stack",
    "view jobs",
    "open positions",
    "open postions",
    "why ",
    "team",
]

DIRECT_SOURCE_ROLE_HINTS = [
    "engineer",
    "scientist",
    "analyst",
    "developer",
    "machine learning",
    "data ",
    "ai ",
    "ml ",
    "architect",
    "specialist",
]


def is_promising_direct_job(title: str, href: str, description: str) -> bool:
    text = " ".join([title, href, description]).lower()

    if any(blocked in text for blocked in DIRECT_SOURCE_BLOCKLIST):
        return any(hint in text for hint in DIRECT_SOURCE_ROLE_HINTS)

    return any(hint in text for hint in DIRECT_SOURCE_ROLE_HINTS)

def fetch_direct(source: dict) -> list:
    """Direktes Scraping einzelner Firmenseiten."""
    log.info(f"Direkt: {source['name']}")
    try:
        r = requests.get(source["url"], headers=CONFIG["headers"], timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        jobs = []
        for el in soup.select(source["selector"])[:20]:
            text = el.get_text().strip()
            href = el.get("href", source["url"])
            if not href.startswith("http"):
                href = source["url"].rstrip("/") + "/" + href.lstrip("/")
            if len(text) > 5 and is_promising_direct_job(text, href, text):
                jobs.append(make_job(
                    title=text[:100],
                    company=source["name"],
                    location="München",
                    url=href,
                    description=text,
                    source=f"direct_{source['name'].lower()}",
                    discovery_url=source["url"],
                    apply_url=href,
                    source_url_type="company_career_page",
                    apply_url_type="company_career_page",
                ))
        log.info(f"  → {len(jobs)} Einträge")
        return jobs
    except Exception as e:
        log.warning(f"  {source['name']} Fehler: {e}")
        return []


def load_primary_sources(path: str | Path | None = None) -> list[dict]:
    source_file = resolve_config_path(path or CONFIG["primary_sources_file"])
    if not source_file.exists():
        return []
    try:
        raw = json.loads(source_file.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return [item for item in raw if isinstance(item, dict)]
    except Exception as exc:
        log.warning("Primary sources konnten nicht geladen werden: %s", exc)
    return []


def load_company_search_sources(path: str | Path | None = None) -> list[dict]:
    source_file = resolve_config_path(path or CONFIG["company_search_sources_file"])
    if not source_file.exists():
        return []
    try:
        raw = json.loads(source_file.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return [item for item in raw if isinstance(item, dict)]
    except Exception as exc:
        log.warning("Company search sources konnten nicht geladen werden: %s", exc)
    return []


def fetch_company_search_source(source: dict, term: str) -> list:
    company = source.get("company") or "unknown_company_search_source"
    source_type = (source.get("type") or "").strip().lower()
    search_mode = (source.get("search_mode") or "").strip().lower()
    status = str(source.get("status", "active")).strip().lower()
    implemented = bool(source.get("implemented", True))

    if status != "active":
        return []
    if not implemented:
        return []

    log.info("Company search source: %s / %s", company, term)

    if source_type == "swm_portal":
        return fetch_swm_portal(source, term)
    if source_type == "siemens_energy_portal":
        return fetch_siemens_energy_portal(source, term)
    if source_type == "infineon_portal":
        return fetch_infineon_portal(source, term)
    if source_type == "bmw_portal":
        return fetch_bmw_portal(source, term)

    if search_mode != "onsite_search":
        log.warning("  Unbekannter search_mode=%r fuer %s", search_mode, company)
        return []

    # Platzhalter fuer weitere Karriereportale mit Suchfeld.
    return []


def fetch_swm_portal(source: dict, term: str) -> list:
    base_url = (source.get("url") or "https://www.swm.de/karriere/jobboerse").strip()
    company = source.get("company") or "SWM"
    location_override = source.get("location") or CONFIG["location"]
    try:
        r = requests.get(base_url, headers=CONFIG["headers"], timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
    except Exception as exc:
        log.warning("  SWM Fehler (%s): %s", company, exc)
        return []

    jobs = []
    for item in soup.select("a.jobboerse--liste--item"):
        title_el = item.select_one(".headline-s")
        details_el = item.select_one(".jobboerse--liste--item__details")
        href = (item.get("href") or "").strip()
        title = title_el.get_text(" ", strip=True) if title_el else ""
        details = details_el.get_text(" ", strip=True) if details_el else ""
        if not title or not href:
            continue
        detail_url = requests.compat.urljoin(base_url, href)
        if not _matches_company_search_term(term, title, details):
            continue
        description = fetch_swm_job_description(detail_url)
        jobs.append(
            make_job(
                title=title,
                company=company,
                location=_swm_location_from_text(details) or location_override,
                url=detail_url,
                description=description or details,
                source="swm",
                discovery_url=base_url,
                apply_url=detail_url,
                source_url_type="company_career_page",
                apply_url_type="company_career_page",
            )
        )
    log.info("  → %s SWM-Jobs gefunden", len(jobs))
    return jobs


def fetch_siemens_energy_portal(source: dict, term: str) -> list:
    base_url = (source.get("url") or "https://jobs.siemens-energy.com/de_DE/jobs/searchJobsGermany").strip()
    company = source.get("company") or "Siemens Energy"
    location_override = source.get("location") or CONFIG["location"]
    try:
        r = requests.get(base_url, headers=CONFIG["headers"], timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
    except Exception as exc:
        log.warning("  Siemens Energy Fehler (%s): %s", company, exc)
        return []

    jobs = []
    for article in soup.select("article.article--result"):
        title_el = article.select_one("h3 a")
        apply_el = article.select_one("a.button.button--secondary")
        title = title_el.get_text(" ", strip=True) if title_el else ""
        detail_url = (title_el.get("href") or "").strip() if title_el else ""
        apply_url = (apply_el.get("href") or "").strip() if apply_el else ""
        if not title or not detail_url:
            continue
        detail_url = requests.compat.urljoin(base_url, detail_url)
        apply_url = requests.compat.urljoin(base_url, apply_url) if apply_url else detail_url
        if not _matches_company_search_term(term, title):
            continue
        description = fetch_siemens_energy_job_description(detail_url)
        jobs.append(
            make_job(
                title=title,
                company=company,
                location=_extract_siemens_location(description) or location_override,
                url=detail_url,
                description=description or title,
                source="siemens_energy",
                discovery_url=base_url,
                apply_url=apply_url,
                source_url_type="company_career_page",
                apply_url_type="company_career_page",
            )
        )
    log.info("  → %s Siemens-Energy-Jobs gefunden", len(jobs))
    return jobs


def fetch_infineon_portal(source: dict, term: str) -> list:
    base_url = (
        source.get("url")
        or "https://jobs.infineon.com/careers?hl=de&start=0&pid=563808970053685&sort_by=timestamp"
    ).strip()
    company = source.get("company") or "Infineon"
    location_override = source.get("location") or CONFIG["location"]
    try:
        r = requests.get(base_url, headers=CONFIG["headers"], timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
    except Exception as exc:
        log.warning("  Infineon Fehler (%s): %s", company, exc)
        return []

    jobs = []
    seen_urls = set()
    anchors = []
    for selector in [
        "a[href*='careers/job']",
        "a[href*='job/']",
        "a[href*='jobId=']",
        "a[data-ph-at-id='job-link']",
        "a[data-gtm='job']",
        "a",
    ]:
        found = soup.select(selector)
        if found:
            anchors = found
            if selector != "a":
                break

    for anchor in anchors:
        href = (anchor.get("href") or "").strip()
        title = anchor.get_text(" ", strip=True)
        if not href or not title or len(title) < 6:
            continue

        lower_title = title.lower()
        lower_href = href.lower()
        if "job" not in lower_href and not any(
            keyword in lower_title
            for keyword in ["engineer", "scientist", "analyst", "developer", "architect", "ai", "ml", "data"]
        ):
            continue

        detail_url = requests.compat.urljoin(base_url, href)
        if detail_url in seen_urls:
            continue
        seen_urls.add(detail_url)

        if not _matches_company_search_term(term, title):
            continue

        description = fetch_infineon_job_description(detail_url)
        jobs.append(
            make_job(
                title=title,
                company=company,
                location=_extract_infineon_location(description) or location_override,
                url=detail_url,
                description=description or title,
                source="infineon",
                discovery_url=base_url,
                apply_url=detail_url,
                source_url_type="company_career_page",
                apply_url_type="company_career_page",
            )
        )

    log.info("  → %s Infineon-Jobs gefunden", len(jobs))
    return jobs


def fetch_bmw_portal(source: dict, term: str) -> list:
    base_url = (source.get("url") or "https://jobs.bmwgroup.com/").strip()
    company = source.get("company") or "BMW Group"
    location_override = source.get("location") or CONFIG["location"]

    job_urls = discover_bmw_job_urls(base_url, term)
    if not job_urls:
        log.warning("  BMW Fehler (%s): keine Job-URLs gefunden", company)
        return []

    jobs = []
    for detail_url in job_urls[: CONFIG["bmw_detail_request_limit"]]:
        detail = fetch_bmw_job_detail(detail_url)
        title = detail.get("title", "").strip()
        description = detail.get("description", "").strip()
        location = detail.get("location", "").strip() or location_override
        apply_url = detail.get("apply_url", "").strip() or detail_url
        if not title:
            continue
        if not _matches_company_search_term(term, title, description):
            continue
        jobs.append(
            make_job(
                title=title,
                company=company,
                location=location,
                url=detail_url,
                description=description or title,
                source="bmw",
                discovery_url=base_url,
                apply_url=apply_url,
                source_url_type="company_career_page",
                apply_url_type="company_career_page",
            )
        )

    log.info("  → %s BMW-Jobs gefunden", len(jobs))
    return jobs


def discover_bmw_job_urls(base_url: str, term: str = "") -> list[str]:
    cache = _load_json_cache(CONFIG["bmw_url_cache_file"])
    cache_key = (base_url or "").strip() or "https://jobs.bmwgroup.com/"
    cached_entry = cache.get(cache_key, {})
    if _cache_is_fresh(cached_entry.get("timestamp")):
        cached_urls = cached_entry.get("urls", [])
        if isinstance(cached_urls, list) and cached_urls:
            return _rank_bmw_urls_for_term(cached_urls, term)[:40]

    seeds = []
    parsed = urlparse(base_url)
    host_root = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else "https://jobs.bmwgroup.com"
    for url in [
        f"{host_root}/robots.txt",
        f"{host_root}/sitemap.xml",
        f"{host_root}/sitemap_index.xml",
        "https://www.bmwgroup.jobs/robots.txt",
        "https://www.bmwgroup.jobs/sitemap.xml",
        "https://www.bmwgroup.jobs/sitemap_index.xml",
    ]:
        if url not in seeds:
            seeds.append(url)

    sitemap_urls = []
    nested_sitemaps = []

    for seed in seeds:
        try:
            r = requests.get(seed, headers=CONFIG["headers"], timeout=20)
            if r.status_code >= 400:
                continue
            text = r.text
        except Exception:
            continue

        if seed.endswith("robots.txt"):
            for line in text.splitlines():
                if line.lower().startswith("sitemap:"):
                    sitemap_url = line.split(":", 1)[1].strip()
                    if sitemap_url and sitemap_url not in nested_sitemaps:
                        nested_sitemaps.append(sitemap_url)
            continue

        if "<urlset" in text or "<sitemapindex" in text:
            nested_sitemaps.append(seed)

    seen_sitemaps = set()
    queue = list(nested_sitemaps)
    while queue and len(seen_sitemaps) < 25:
        sitemap_url = queue.pop(0)
        if sitemap_url in seen_sitemaps:
            continue
        seen_sitemaps.add(sitemap_url)
        try:
            r = requests.get(sitemap_url, headers=CONFIG["headers"], timeout=20)
            r.raise_for_status()
            root = ET.fromstring(r.content)
        except Exception:
            continue

        tag = root.tag.lower()
        if tag.endswith("sitemapindex"):
            for loc in root.findall(".//{*}loc"):
                child = (loc.text or "").strip()
                if child and child not in seen_sitemaps and "bmw" in child.lower():
                    queue.append(child)
            continue

        for loc in root.findall(".//{*}loc"):
            job_url = (loc.text or "").strip()
            if not job_url:
                continue
            lower = job_url.lower()
            if "/job/" in lower or "/jobfinder/job-description" in lower:
                sitemap_urls.append(job_url)

    unique_urls = list(dict.fromkeys(sitemap_urls))
    cache[cache_key] = {
        "timestamp": _cache_now().isoformat(),
        "urls": unique_urls,
    }
    _save_json_cache(CONFIG["bmw_url_cache_file"], cache)
    ranked_urls = _rank_bmw_urls_for_term(unique_urls, term)
    return ranked_urls[:40]


def fetch_bmw_job_detail(url: str) -> dict:
    cache = _load_json_cache(CONFIG["bmw_detail_cache_file"])
    cached_entry = cache.get(url, {})
    if _cache_is_fresh(cached_entry.get("timestamp")):
        detail = cached_entry.get("detail", {})
        if isinstance(detail, dict) and detail.get("title"):
            return detail

    try:
        r = requests.get(url, headers=CONFIG["headers"], timeout=8)
        r.raise_for_status()
    except Exception:
        return {}

    soup = BeautifulSoup(r.text, "lxml")
    title = ""
    title_el = soup.select_one("h1")
    if title_el:
        title = title_el.get_text(" ", strip=True)
    if not title:
        page_title = (soup.title.get_text(" ", strip=True) if soup.title else "").strip()
        title = re.sub(r"\s*(?:Stellendetails|Job Details)\s*\|\s*BMW Group\s*$", "", page_title, flags=re.IGNORECASE).strip()

    text = _html_to_text(soup.get_text(separator=" ", strip=True)[:20000])
    apply_url = url
    for anchor in soup.select("a[href]"):
        label = anchor.get_text(" ", strip=True).lower()
        href = (anchor.get("href") or "").strip()
        if not href:
            continue
        if "apply" in label or "bewerben" in label:
            apply_url = requests.compat.urljoin(url, href)
            break

    detail = {
        "title": title,
        "description": text,
        "location": _extract_bmw_location(text),
        "apply_url": apply_url,
    }
    cache[url] = {
        "timestamp": _cache_now().isoformat(),
        "detail": detail,
    }
    _save_json_cache(CONFIG["bmw_detail_cache_file"], cache)
    return detail


def _rank_bmw_urls_for_term(urls: list[str], term: str) -> list[str]:
    tokens = _term_tokens(term)
    if not tokens:
        return urls

    def score(url: str) -> tuple[int, int, str]:
        lowered = url.lower()
        token_hits = sum(1 for token in tokens if token in lowered)
        role_hits = sum(
            1
            for marker in ("data", "ai", "ml", "analytics", "engineer", "scientist", "machine-learning")
            if marker in lowered
        )
        return (-token_hits, -role_hits, lowered)

    return sorted(urls, key=score)


def fetch_swm_job_description(url: str) -> str:
    try:
        r = requests.get(url, headers=CONFIG["headers"], timeout=15)
        r.raise_for_status()
    except Exception:
        return ""

    soup = BeautifulSoup(r.text, "lxml")
    for script in soup.select("script[type='application/ld+json']"):
        raw = (script.string or script.get_text() or "").strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        candidates = payload if isinstance(payload, list) else [payload]
        for item in candidates:
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                description = item.get("description") or ""
                if description:
                    return _html_to_text(html.unescape(str(description)))
    return _html_to_text(soup.get_text(separator=" ", strip=True)[:12000])


def fetch_infineon_job_description(url: str) -> str:
    try:
        r = requests.get(url, headers=CONFIG["headers"], timeout=20)
        r.raise_for_status()
    except Exception:
        return ""

    soup = BeautifulSoup(r.text, "lxml")
    for script in soup.select("script[type='application/ld+json']"):
        raw = (script.string or script.get_text() or "").strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        candidates = payload if isinstance(payload, list) else [payload]
        for item in candidates:
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                description = item.get("description") or ""
                if description:
                    return _html_to_text(html.unescape(str(description)))

    main = soup.select_one("main")
    if main:
        text = main.get_text(separator=" ", strip=True)
        if text:
            return text[:12000]
    article = soup.select_one("article")
    if article:
        text = article.get_text(separator=" ", strip=True)
        if text:
            return text[:12000]
    return _html_to_text(soup.get_text(separator=" ", strip=True)[:12000])


def fetch_siemens_energy_job_description(url: str) -> str:
    try:
        r = requests.get(url, headers=CONFIG["headers"], timeout=20)
        r.raise_for_status()
    except Exception:
        return ""

    soup = BeautifulSoup(r.text, "lxml")
    main = soup.select_one("main")
    if main:
        text = main.get_text(separator=" ", strip=True)
        if text:
            return text[:12000]
    return _html_to_text(soup.get_text(separator=" ", strip=True)[:12000])


def _matches_company_search_term(term: str, title: str, details: str = "") -> bool:
    haystack = " ".join([title, details]).lower()
    term_l = (term or "").strip().lower()
    if not term_l:
        return True
    if term_l in haystack:
        return True

    tokens = _term_tokens(term_l)
    if not tokens:
        return False
    matched = sum(1 for token in tokens if token in haystack)
    return matched >= max(1, min(2, len(tokens)))


def _term_tokens(term: str) -> list[str]:
    return [token for token in re.findall(r"[a-zA-ZäöüÄÖÜ]+", (term or "").strip().lower()) if len(token) >= 3]


def _swm_location_from_text(text: str) -> str:
    parts = [part.strip() for part in (text or "").split("/") if part.strip()]
    if not parts:
        return ""
    return parts[-1]


def _extract_siemens_location(text: str) -> str:
    haystack = " ".join((text or "").split())
    match = re.search(r"Standort\s+(.+?)\s+Remote oder Büro", haystack, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ""


def _extract_infineon_location(text: str) -> str:
    haystack = " ".join((text or "").split())
    for pattern in [
        r"Standort\s*[:\-]?\s*(.+?)(?=\s+(?:Job\s+ID|Apply|Jetzt\s+bewerben|Bewerben|Kontakt)\b|$)",
        r"Location\s*[:\-]?\s*(.+?)(?=\s+(?:Job\s+ID|Apply|Jetzt\s+bewerben|Bewerben|Contact)\b|$)",
    ]:
        match = re.search(pattern, haystack, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip(" ,;-")
    return ""


def _extract_bmw_location(text: str) -> str:
    haystack = " ".join((text or "").split())
    for pattern in [
        r"Standort\s*:\s*(.+?)(?=\s+Unternehmen\s*:|\s+ARE YOU|\s+INNOVATION|\s+Was Sie erwartet|\s+What you will do|$)",
        r"Location\s*:\s*(.+?)(?=\s+Company\s*:|\s+ARE YOU|\s+INNOVATION|\s+What you will do|$)",
    ]:
        match = re.search(pattern, haystack, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip(" ,;-")
    return ""

def fetch_primary_source(source: dict) -> list:
    source_type = (source.get("type") or "").strip().lower()
    if source_type == "greenhouse":
        return fetch_greenhouse_board(source)
    if source_type == "lever":
        return fetch_lever_board(source)
    if source_type == "recruitee":
        return fetch_recruitee_board(source)
    log.warning("Unbekannter primary source type=%r", source_type)
    return []


def fetch_greenhouse_board(source: dict) -> list:
    board_token = (source.get("board_token") or "").strip()
    if not board_token:
        return []
    api_url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
    company = source.get("company") or board_token
    location_override = source.get("location", "")
    log.info("Greenhouse board: %s", company)
    try:
        r = requests.get(api_url, headers=CONFIG["headers"], timeout=15)
        r.raise_for_status()
        payload = r.json()
    except Exception as exc:
        log.warning("  Greenhouse Fehler (%s): %s", company, exc)
        return []

    jobs = []
    for item in payload.get("jobs", []):
        title = str(item.get("title", "")).strip()
        absolute_url = str(item.get("absolute_url", "")).strip()
        content = _html_to_text(item.get("content", ""))
        location = (
            (item.get("location") or {}).get("name")
            if isinstance(item.get("location"), dict)
            else location_override
        ) or location_override
        if not title or not absolute_url:
            continue
        jobs.append(
            make_job(
                title=title,
                company=company,
                location=location or CONFIG["location"],
                url=absolute_url,
                description=content,
                source="greenhouse",
                discovery_url=api_url,
                apply_url=absolute_url,
                source_url_type="known_ats",
                apply_url_type="greenhouse",
            )
        )
    log.info("  → %s Jobs gefunden", len(jobs))
    return jobs


def fetch_lever_board(source: dict) -> list:
    site = (source.get("site") or "").strip()
    if not site:
        return []
    api_url = f"https://api.lever.co/v0/postings/{site}?mode=json"
    company = source.get("company") or site
    location_override = source.get("location", "")
    log.info("Lever board: %s", company)
    try:
        r = requests.get(api_url, headers=CONFIG["headers"], timeout=15)
        r.raise_for_status()
        payload = r.json()
    except Exception as exc:
        log.warning("  Lever Fehler (%s): %s", company, exc)
        return []

    jobs = []
    for item in payload:
        title = str(item.get("text", "")).strip()
        apply_url = str(item.get("hostedUrl", "")).strip()
        description = _html_to_text(item.get("descriptionPlain") or item.get("description") or "")
        categories = item.get("categories") or {}
        location = (
            categories.get("location")
            if isinstance(categories, dict)
            else location_override
        ) or location_override
        if not title or not apply_url:
            continue
        jobs.append(
            make_job(
                title=title,
                company=company,
                location=location or CONFIG["location"],
                url=apply_url,
                description=description,
                source="lever",
                discovery_url=api_url,
                apply_url=apply_url,
                source_url_type="known_ats",
                apply_url_type="lever",
            )
        )
    log.info("  → %s Jobs gefunden", len(jobs))
    return jobs


def fetch_recruitee_board(source: dict) -> list:
    subdomain = (source.get("subdomain") or "").strip()
    if not subdomain:
        return []
    api_url = f"https://{subdomain}.recruitee.com/api/offers/"
    company = source.get("company") or subdomain
    location_override = source.get("location", "")
    log.info("Recruitee board: %s", company)
    try:
        r = requests.get(api_url, headers=CONFIG["headers"], timeout=15)
        r.raise_for_status()
        payload = r.json()
    except Exception as exc:
        log.warning("  Recruitee Fehler (%s): %s", company, exc)
        return []

    offers = payload.get("offers", []) if isinstance(payload, dict) else payload
    jobs = []
    for item in offers or []:
        title = str(item.get("title", "")).strip()
        careers_url = str(item.get("careers_url") or item.get("url") or "").strip()
        description = _html_to_text(item.get("description") or item.get("description_plain") or "")
        location = (
            (item.get("location") or {}).get("name")
            if isinstance(item.get("location"), dict)
            else location_override
        ) or location_override
        if not title or not careers_url:
            continue
        jobs.append(
            make_job(
                title=title,
                company=company,
                location=location or CONFIG["location"],
                url=careers_url,
                description=description,
                source="recruitee",
                discovery_url=api_url,
                apply_url=careers_url,
                source_url_type="known_ats",
                apply_url_type="recruitee",
            )
        )
    log.info("  → %s Jobs gefunden", len(jobs))
    return jobs


def _html_to_text(value: str) -> str:
    if not value:
        return ""
    soup = BeautifulSoup(str(value), "lxml")
    return soup.get_text(separator=" ", strip=True)


# --- Hauptfunktion -------------------------------------------------------------

def find_jobs() -> list:
    all_jobs = []

    primary_sources = load_primary_sources()
    for primary_source in primary_sources:
        all_jobs += fetch_primary_source(primary_source)
        time.sleep(CONFIG["request_delay"])

    company_search_sources = load_company_search_sources()

    for term in CONFIG["search_terms"]:
        for company_source in company_search_sources:
            all_jobs += fetch_company_search_source(company_source, term)
            time.sleep(CONFIG["request_delay"])

        all_jobs += fetch_jobspy(term, CONFIG["location"])
        time.sleep(CONFIG["request_delay"])

        all_jobs += fetch_arbeitsagentur(term, CONFIG["location"])
        time.sleep(CONFIG["request_delay"])

        all_jobs += fetch_stepstone(term, CONFIG["location"])
        time.sleep(CONFIG["request_delay"])

    for source in DIRECT_SOURCES:
        all_jobs += fetch_direct(source)
        time.sleep(CONFIG["request_delay"])

    all_jobs = enrich_job_descriptions(all_jobs)

    # Deduplizieren
    unique = deduplicate(all_jobs)
    filtered, excluded = filter_jobs(unique)
    location_filtered, location_excluded = apply_location_strategy(filtered)
    validated, invalid_jobs = validate_jobs(location_filtered)
    validated = [dict(job, **annotate_job_links(job)) for job in validated]
    discovered_by_source = source_counts(all_jobs)
    deduped_by_source = source_counts(unique)
    filtered_out_by_source = source_counts(excluded)
    kept_after_filter_by_source = source_counts(filtered)
    kept_after_location_by_source = source_counts(location_filtered)
    log.info(f"\n{'─'*50}")
    log.info(f"Gesamt: {len(all_jobs)} Jobs → {len(unique)} nach Deduplizierung")
    log.info(f"Gefiltert: {len(excluded)} PhD/Internship/Werkstudent → {len(filtered)} verbleiben")
    log.info(
        f"Standortstrategie: {CONFIG['location_strategy']} → {len(location_filtered)} Jobs"
        + (f" ({location_excluded} ausgeschlossen)" if location_excluded else "")
    )
    log.info("Quellenreport:")
    all_sources = sorted(
        set(discovered_by_source)
        | set(deduped_by_source)
        | set(filtered_out_by_source)
        | set(kept_after_filter_by_source)
        | set(kept_after_location_by_source)
    )
    for source in all_sources:
        discovered = discovered_by_source.get(source, 0)
        deduped = deduped_by_source.get(source, 0)
        filtered_out = filtered_out_by_source.get(source, 0)
        kept_after_filter = kept_after_filter_by_source.get(source, 0)
        kept_after_location = kept_after_location_by_source.get(source, 0)
        location_removed = max(0, kept_after_filter - kept_after_location)
        log.info(
            "  - %s: found=%s | deduped=%s | filtered_out=%s | location_removed=%s | kept=%s",
            source,
            discovered,
            deduped,
            filtered_out,
            location_removed,
            kept_after_location,
        )

    # Speichern
    log.info(f"Validierung: {len(validated)} echte Stellen → {len(invalid_jobs)} verworfen")

    output = resolve_runtime_path(CONFIG["output_file"])
    output.write_text(json.dumps(validated, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"Gespeichert: {output.resolve()}")

    return validated


# --- Direkt ausführbar ---------------------------------------------------------

if __name__ == "__main__":
    jobs = find_jobs()
    print(f"\n✓ {len(jobs)} Jobs gefunden und in jobs_raw.json gespeichert.")
    print("\nErste 3 Ergebnisse:")
    for job in jobs[:3]:
        print(f"  [{job['source']}] {job['title']} @ {job['company']} — {job['url']}")
