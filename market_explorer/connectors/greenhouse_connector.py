from __future__ import annotations

import json
from pathlib import Path

import requests

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from source.find_jobs import make_job


def fetch_greenhouse_board(board_token: str, *, company_name: str = "", location_hint: str = "") -> list[dict]:
    token = (board_token or "").strip()
    if not token:
        return []
    url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
    response = requests.get(url, timeout=25)
    response.raise_for_status()
    payload = json.loads(response.text)
    jobs = []
    for item in payload.get("jobs", []):
        title = str(item.get("title") or "").strip()
        absolute_url = str(item.get("absolute_url") or "").strip()
        if not title or not absolute_url:
            continue
        location = _greenhouse_location(item) or location_hint
        content = _greenhouse_content(item)
        job = make_job(
            title=title,
            company=company_name or token,
            location=location,
            url=absolute_url,
            description=content,
            source="greenhouse",
            date=str(item.get("updated_at") or item.get("updatedAt") or item.get("created_at") or item.get("createdAt") or "")[:10],
            discovery_url=absolute_url,
            apply_url=absolute_url,
            source_url_type="known_ats",
            apply_url_type="greenhouse",
        )
        job["source_strategy"] = "ats_api"
        job["source_family"] = "greenhouse"
        job["primary_source_score"] = 100
        job["ats_board"] = token
        jobs.append(job)
    return jobs


def _greenhouse_location(item: dict) -> str:
    location = item.get("location") or {}
    if isinstance(location, dict):
        return str(location.get("name") or "").strip()
    return str(location or "").strip()


def _greenhouse_content(item: dict) -> str:
    content = item.get("content") or ""
    metadata_values = []
    for bucket in item.get("metadata", []) or []:
        name = str(bucket.get("name") or "").strip()
        value = str(bucket.get("value") or "").strip()
        if name and value:
            metadata_values.append(f"{name}: {value}")
    tail = "\n".join(metadata_values)
    return "\n".join(part for part in [str(content).strip(), tail] if part).strip()
