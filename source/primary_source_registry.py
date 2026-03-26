from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from project_paths import resolve_source_path, source_path


def infer_primary_source(url: str, *, company: str = "", location: str = "") -> dict | None:
    parsed = urlparse((url or "").strip())
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path_parts = [part for part in (parsed.path or "").split("/") if part]

    if "boards.greenhouse.io" in host and path_parts:
        return {
            "type": "greenhouse",
            "company": company or path_parts[0],
            "board_token": path_parts[0],
            "location": location or "",
        }

    if "jobs.lever.co" in host and path_parts:
        return {
            "type": "lever",
            "company": company or path_parts[0],
            "site": path_parts[0],
            "location": location or "",
        }

    if host.endswith(".recruitee.com"):
        subdomain = host.split(".", 1)[0]
        if subdomain:
            return {
                "type": "recruitee",
                "company": company or subdomain,
                "subdomain": subdomain,
                "location": location or "",
            }

    return None


def load_primary_sources(path: str | Path | None = None) -> list[dict]:
    source_file = resolve_source_path(path or _default_primary_sources_file())
    if not source_file.exists():
        return []
    try:
        raw = json.loads(source_file.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def remember_primary_source(
    url: str,
    *,
    company: str = "",
    location: str = "",
    path: str | Path | None = None,
) -> dict | None:
    inferred = infer_primary_source(url, company=company, location=location)
    if not inferred:
        return None

    source_file = resolve_source_path(path or _default_primary_sources_file())
    existing = load_primary_sources(source_file)
    dedupe_key = _primary_source_key(inferred)
    if not dedupe_key:
        return None

    for item in existing:
        if _primary_source_key(item) == dedupe_key:
            if not item.get("company") and company:
                item["company"] = company
            if not item.get("location") and location:
                item["location"] = location
            source_file.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
            return item

    existing.append(inferred)
    source_file.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    return inferred


def _primary_source_key(item: dict) -> tuple[str, str] | None:
    source_type = (item.get("type") or "").strip().lower()
    if source_type == "greenhouse":
        token = (item.get("board_token") or "").strip().lower()
        return (source_type, token) if token else None
    if source_type == "lever":
        token = (item.get("site") or "").strip().lower()
        return (source_type, token) if token else None
    if source_type == "recruitee":
        token = (item.get("subdomain") or "").strip().lower()
        return (source_type, token) if token else None
    return None


def _default_primary_sources_file() -> str:
    import os

    return os.getenv("PRIMARY_SOURCES_FILE", str(source_path("primary_sources.json")))
