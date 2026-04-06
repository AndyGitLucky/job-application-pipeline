from __future__ import annotations

import json
from pathlib import Path

import requests
from bs4 import BeautifulSoup

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from source.find_jobs import make_job


def fetch_jobposting_url(url: str, *, company_name: str = "", source_name: str = "direct_jobposting") -> list[dict]:
    target = (url or "").strip()
    if not target:
        return []
    response = requests.get(target, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")
    postings = _extract_jsonld_jobpostings(soup)
    jobs = []
    for item in postings:
        title = str(item.get("title") or "").strip()
        description = str(item.get("description") or "").strip()
        if not title:
            continue
        hiring_org = item.get("hiringOrganization") or {}
        company = company_name or str(hiring_org.get("name") or "").strip()
        location = _jobposting_location(item)
        detail_url = str(item.get("url") or target).strip()
        date_posted = str(item.get("datePosted") or "").strip()[:10]
        job = make_job(
            title=title,
            company=company,
            location=location,
            url=detail_url,
            description=description,
            source=source_name,
            discovery_url=target,
            apply_url=detail_url,
            source_url_type="company_career_page",
            apply_url_type="company_career_page",
            date=date_posted or None,
        )
        job["source_strategy"] = "jobposting_jsonld"
        job["source_family"] = "jobposting"
        job["primary_source_score"] = 90
        jobs.append(job)
    return jobs


def _extract_jsonld_jobpostings(soup: BeautifulSoup) -> list[dict]:
    postings = []
    for node in soup.select("script[type='application/ld+json']"):
        raw = (node.string or node.get_text() or "").strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        for item in _flatten_jsonld(payload):
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                postings.append(item)
    return postings


def _flatten_jsonld(payload: object) -> list[object]:
    if isinstance(payload, list):
        items = []
        for entry in payload:
            items.extend(_flatten_jsonld(entry))
        return items
    if isinstance(payload, dict):
        if isinstance(payload.get("@graph"), list):
            return _flatten_jsonld(payload["@graph"])
        return [payload]
    return []


def _jobposting_location(item: dict) -> str:
    location = item.get("jobLocation")
    locations = location if isinstance(location, list) else [location]
    names = []
    for entry in locations:
        if not isinstance(entry, dict):
            continue
        address = entry.get("address") or {}
        locality = str(address.get("addressLocality") or "").strip()
        region = str(address.get("addressRegion") or "").strip()
        country = str(address.get("addressCountry") or "").strip()
        parts = [part for part in (locality, region, country) if part]
        if parts:
            names.append(", ".join(parts))
    return " | ".join(names)
