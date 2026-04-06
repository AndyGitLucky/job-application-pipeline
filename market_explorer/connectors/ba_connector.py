from __future__ import annotations

import logging
import re
import time
from pathlib import Path

import requests
from requests import HTTPError

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from source.find_jobs import fetch_arbeitsagentur, make_job


log = logging.getLogger(__name__)

BA_SEARCH_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs"
BA_API_KEY = "jobboerse-jobsuche"
BA_DEFAULT_PAGE_SIZE = 100

BA_TEXT_REPLACEMENTS = {
    "Muenchen": "M\u00fcnchen",
    "Koeln": "K\u00f6ln",
    "Nuernberg": "N\u00fcrnberg",
    "Duesseldorf": "D\u00fcsseldorf",
    "Wuerzburg": "W\u00fcrzburg",
    "Kuechenhilfe": "K\u00fcchenhilfe",
    "Verkaeufer": "Verk\u00e4ufer",
    "Kaufmaennischer": "Kaufm\u00e4nnischer",
    "Sozialpaedagoge": "Sozialp\u00e4dagoge",
    "Kindergaertner": "Kinderg\u00e4rtner",
}


def fetch_ba_jobs(
    term: str,
    location: str,
    *,
    all_pages: bool = False,
    radius_km: int = 20,
    size: int = BA_DEFAULT_PAGE_SIZE,
    max_pages: int | None = None,
    delay_seconds: float = 0.0,
) -> list[dict]:
    result = fetch_ba_jobs_with_meta(
        term,
        location,
        all_pages=all_pages,
        radius_km=radius_km,
        size=size,
        max_pages=max_pages,
        delay_seconds=delay_seconds,
    )
    return result["jobs"]


def fetch_ba_jobs_with_meta(
    term: str,
    location: str,
    *,
    all_pages: bool = False,
    radius_km: int = 20,
    size: int = BA_DEFAULT_PAGE_SIZE,
    max_pages: int | None = None,
    delay_seconds: float = 0.0,
) -> dict:
    normalized_term = _normalize_ba_text(term)
    normalized_location = _normalize_ba_text(location)
    page_size = max(1, min(int(size or BA_DEFAULT_PAGE_SIZE), 100))
    page = 1
    pages_fetched = 0
    all_jobs: list[dict] = []

    try:
        while True:
            try:
                payload = _request_ba_search(
                    normalized_term,
                    normalized_location,
                    page=page,
                    size=page_size,
                    radius_km=radius_km,
                )
            except HTTPError as exc:
                if _is_ba_page_limit_error(exc) and all_jobs:
                    log.info(
                        "BA API stopped at page %s for %r in %r; keeping %s jobs collected so far",
                        page,
                        normalized_term,
                        normalized_location,
                        len(all_jobs),
                    )
                    break
                raise
            jobs = _parse_ba_search_payload(payload, location_hint=normalized_location)
            all_jobs.extend(jobs)
            pages_fetched += 1

            if not all_pages:
                break
            if not jobs or len(jobs) < page_size:
                break
            if max_pages and pages_fetched >= max_pages:
                break

            page += 1
            if delay_seconds > 0:
                time.sleep(delay_seconds)

        return {
            "jobs": _enrich_ba_jobs(all_jobs),
            "pages": pages_fetched,
            "mode": "api",
        }
    except Exception as exc:
        log.warning("BA API search failed for %r in %r: %s", normalized_term, normalized_location, exc)
        fallback_jobs = fetch_arbeitsagentur(normalized_term, normalized_location)
        return {
            "jobs": _enrich_ba_jobs(fallback_jobs),
            "pages": 1 if fallback_jobs else 0,
            "mode": "selenium_fallback",
        }


def _enrich_ba_jobs(jobs: list[dict]) -> list[dict]:
    enriched = []
    for job in jobs:
        updated = dict(job)
        updated["source_strategy"] = "official_public_portal"
        updated["source_family"] = "bundesagentur"
        updated["primary_source_score"] = 80
        enriched.append(updated)
    return enriched


def _request_ba_search(term: str, location: str, *, page: int, size: int, radius_km: int) -> dict:
    headers = {
        "X-API-Key": BA_API_KEY,
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }
    params = {
        "angebotsart": 1,
        "wo": location,
        "umkreis": max(1, int(radius_km or 20)),
        "page": page,
        "size": size,
        "pav": "false",
    }
    if term:
        params["was"] = term
    response = requests.get(BA_SEARCH_URL, headers=headers, params=params, timeout=25)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Unexpected BA response type")
    return payload


def _is_ba_page_limit_error(exc: HTTPError) -> bool:
    response = getattr(exc, "response", None)
    if response is None or response.status_code != 400:
        return False
    request = getattr(response, "request", None)
    if request is None:
        return False
    url = str(getattr(request, "url", "") or "")
    return "rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs" in url and "page=" in url


def _parse_ba_search_payload(payload: dict, *, location_hint: str) -> list[dict]:
    raw_jobs = payload.get("stellenangebote")
    if not isinstance(raw_jobs, list):
        return []

    jobs: list[dict] = []
    for item in raw_jobs:
        if not isinstance(item, dict):
            continue

        refnr = _first_text(item, "refnr", "referenznummer")
        title = _first_text(item, "stellenangebotsTitel", "titel", "beruf")
        url = _build_ba_jobdetail_url(refnr)
        if not title or not url:
            continue

        company = _first_text(item, "arbeitgeber", "arbeitgeberName", "firma")
        location = _ba_location(item) or location_hint
        description = _ba_description(item, location=location)
        published_at = _first_text(
            item,
            "aktuelleVeroeffentlichungsdatum",
            "aktuelleVeroeffentlichung",
            "modifikationsTimestamp",
            "modifiziertAm",
            "erstelltAm",
        )

        jobs.append(
            make_job(
                title=title,
                company=company,
                location=location,
                url=url,
                description=description,
                source="arbeitsagentur",
                date=published_at[:10],
                discovery_url=url,
                apply_url=url,
                source_url_type="jobboard",
                apply_url_type="arbeitsagentur",
            )
        )

    return jobs


def _ba_location(item: dict) -> str:
    place = item.get("arbeitsort")
    if isinstance(place, dict):
        parts = [
            str(place.get("ort") or "").strip(),
            str(place.get("region") or "").strip(),
        ]
        return ", ".join(part for part in parts if part)

    places = item.get("arbeitsorte")
    if isinstance(places, list):
        for entry in places:
            if isinstance(entry, dict):
                parts = [
                    str(entry.get("ort") or "").strip(),
                    str(entry.get("region") or "").strip(),
                ]
                value = ", ".join(part for part in parts if part)
                if value:
                    return value
    return ""


def _ba_description(item: dict, *, location: str) -> str:
    parts = [
        _first_text(item, "stellenangebotsTitel", "titel", "beruf"),
        _first_text(item, "arbeitgeber", "arbeitgeberName", "firma"),
        location,
        _first_text(item, "eintrittsdatum", "aktuelleVeroeffentlichungsdatum", "modifikationsTimestamp"),
    ]

    for key in ("arbeitszeitmodelle", "befristung", "verguetung", "berufserfahrung", "schulbildung"):
        value = item.get(key)
        if isinstance(value, list):
            text = ", ".join(str(entry).strip() for entry in value if str(entry).strip())
            if text:
                parts.append(f"{key}: {text}")
        else:
            text = str(value or "").strip()
            if text:
                parts.append(f"{key}: {text}")

    teaser = _first_text(item, "suchbegriffe", "beruf", "arbeitsortText")
    if teaser:
        parts.append(teaser)

    return " | ".join(part for part in parts if part).strip()


def _build_ba_jobdetail_url(refnr: str) -> str:
    reference = str(refnr or "").strip()
    if not reference:
        return ""
    return f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{reference}"


def _first_text(item: dict, *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _normalize_ba_text(text: str) -> str:
    normalized = str(text or "").strip()
    if not normalized:
        return normalized
    for source_text, target_text in sorted(BA_TEXT_REPLACEMENTS.items(), key=lambda item: len(item[0]), reverse=True):
        normalized = re.sub(rf"\b{re.escape(source_text)}\b", target_text, normalized)
    return normalized
