from __future__ import annotations

import json
from pathlib import Path

import requests

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from source.find_jobs import make_job


def fetch_lever_site(site_name: str, *, company_name: str = "", location_hint: str = "") -> list[dict]:
    site = (site_name or "").strip()
    if not site:
        return []
    url = f"https://api.lever.co/v0/postings/{site}?mode=json"
    response = requests.get(url, timeout=25)
    response.raise_for_status()
    payload = json.loads(response.text)
    jobs = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        title = str(item.get("text") or "").strip()
        absolute_url = str(item.get("hostedUrl") or "").strip()
        if not title or not absolute_url:
            continue
        location = _lever_location(item) or location_hint
        content = _lever_content(item)
        job = make_job(
            title=title,
            company=company_name or str(item.get("categories", {}).get("team") or site),
            location=location,
            url=absolute_url,
            description=content,
            source="lever",
            date=str(item.get("createdAt") or item.get("updatedAt") or item.get("created_at") or item.get("updated_at") or "")[:10],
            discovery_url=absolute_url,
            apply_url=absolute_url,
            source_url_type="known_ats",
            apply_url_type="lever",
        )
        job["source_strategy"] = "ats_api"
        job["source_family"] = "lever"
        job["primary_source_score"] = 100
        job["ats_board"] = site
        jobs.append(job)
    return jobs


def _lever_location(item: dict) -> str:
    categories = item.get("categories") or {}
    if isinstance(categories, dict):
        return str(categories.get("location") or "").strip()
    return ""


def _lever_content(item: dict) -> str:
    parts = []
    for key in ("description", "descriptionPlain", "lists"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    if isinstance(item.get("additional"), str) and item["additional"].strip():
        parts.append(item["additional"].strip())
    return "\n".join(parts).strip()
