from __future__ import annotations

from urllib.parse import urlparse


KNOWN_ATS_HOST_HINTS = (
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

JOBBOARD_HOST_HINTS = (
    "indeed.",
    "stepstone.",
    "arbeitsagentur.de",
    "linkedin.",
    "xing.",
)

AGGREGATOR_HOST_HINTS = (
    "get-in-it.de",
)

SECONDARY_APPLY_PLATFORM_HINTS = (
    "recruitmentplatform.com",
    "persy.jobs",
    "lumessetalentlink.com",
)


def annotate_job_links(job: dict) -> dict:
    candidates = [
        ("url_company", (job.get("url_company") or "").strip()),
        ("apply_url", (job.get("apply_url") or "").strip()),
        ("url", (job.get("url") or "").strip()),
        ("discovery_url", (job.get("discovery_url") or "").strip()),
    ]

    best = None
    best_score = -10_000
    best_meta = None
    for field, url in candidates:
        meta = classify_link(url, source_field=field)
        if meta["score"] > best_score:
            best = url
            best_score = meta["score"]
            best_meta = meta

    best_meta = best_meta or classify_link("", source_field="")
    best_meta = _apply_manual_gate_overrides(job, best_meta)
    description_quality, description_reason = classify_description_source(job)
    return {
        "best_link": best or "",
        "best_link_source_field": best_meta["source_field"],
        "best_link_kind": best_meta["kind"],
        "best_link_quality": best_meta["quality"],
        "best_link_reason": best_meta["reason"],
        "description_quality": description_quality,
        "description_reason": description_reason,
    }


def _apply_manual_gate_overrides(job: dict, best_meta: dict) -> dict:
    source = (job.get("source") or "").strip().lower()
    if "arbeitsagentur" not in source:
        return best_meta

    source_field = str(best_meta.get("source_field") or "")
    kind = str(best_meta.get("kind") or "")
    if source_field in {"url_company", "apply_url"} and kind in {"direct_apply", "company_detail", "secondary_apply_platform"}:
        overridden = dict(best_meta)
        overridden["kind"] = "captcha_then_company_apply"
        overridden["reason"] = "arbeitsagentur_manual_gate_to_company_apply"
        if overridden.get("quality") == "low":
            overridden["quality"] = "medium"
        return overridden

    return best_meta


def classify_description_source(job: dict) -> tuple[str, str]:
    source = (job.get("source") or "").strip().lower()
    url = (job.get("url") or "").strip().lower()
    description = " ".join(str(job.get("description") or "").split())

    if not description:
        return "low", "missing_description"

    if "arbeitsagentur" in source and "/jobsuche/jobdetail/" in url:
        if len(description) >= 140:
            return "high", "arbeitsagentur_rich_description"
        return "medium", "arbeitsagentur_short_description"

    if len(description) >= 300:
        return "high", "rich_description"
    if len(description) >= 120:
        return "medium", "usable_description"
    return "low", "thin_description"


def classify_link(url: str, *, source_field: str) -> dict:
    host = _host(url)
    path = (urlparse(url).path or "").lower()

    if not url:
        return _meta(source_field, "missing", "none", "no_url", -10_000)

    if _looks_like_known_ats(host):
        return _meta(source_field, "direct_apply", "high", "known_ats", 100)

    if any(hint in host for hint in SECONDARY_APPLY_PLATFORM_HINTS):
        return _meta(source_field, "secondary_apply_platform", "medium", "secondary_apply_platform", 80)

    if "arbeitsagentur.de" in host and "/jobsuche/jobdetail/" in path:
        return _meta(source_field, "manual_contact_gate", "medium", "arbeitsagentur_jobdetail", 60)

    if any(hint in host for hint in AGGREGATOR_HOST_HINTS):
        return _meta(source_field, "aggregator_apply", "low", "aggregator_platform", 40)

    if any(hint in path for hint in ("career", "careers", "job", "jobs", "karriere", "bewerb", "apply", "application")) and not _is_jobboard(host):
        return _meta(source_field, "company_detail", "medium", "company_career_page", 70)

    if _is_jobboard(host):
        return _meta(source_field, "discovery_only", "low", "jobboard_url", 20)

    return _meta(source_field, "unknown", "low", "unclassified_url", 10)


def _meta(source_field: str, kind: str, quality: str, reason: str, score: int) -> dict:
    return {
        "source_field": source_field,
        "kind": kind,
        "quality": quality,
        "reason": reason,
        "score": score,
    }


def _host(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _looks_like_known_ats(host: str) -> bool:
    return any(hint in host for hint in KNOWN_ATS_HOST_HINTS)


def _is_jobboard(host: str) -> bool:
    return any(hint in host for hint in JOBBOARD_HOST_HINTS)
