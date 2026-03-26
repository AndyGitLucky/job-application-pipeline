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

CAREER_PATH_HINTS = (
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
)


def classify_job(job: dict, ats_allowed: set[str] | None = None) -> dict:
    ats_allowed = ats_allowed or {
        "personio",
        "greenhouse",
        "lever",
        "workable",
        "successfactors",
        "smartrecruiters",
        "workday",
        "recruitee",
    }

    decision = (job.get("decision") or "").strip().lower()
    job_status = (job.get("job_status") or "").strip().lower()
    listing_status = (job.get("listing_status") or "").strip().lower()
    verification_status = (job.get("verification_status") or "").strip().lower()
    contact_email = (job.get("contact_email") or "").strip()
    contact_source = (job.get("contact_source") or "").strip().lower()
    ats_type = (job.get("ats_type") or "").strip().lower()
    url_company = (job.get("url_company") or "").strip()
    url = (job.get("url") or "").strip()

    fit_status = _fit_status(decision, job_status, verification_status)
    listing_status = _listing_status(listing_status=listing_status, url_company=url_company, url=url, job_status=job_status)
    apply_path_status = _apply_path_status(
        contact_email=contact_email,
        contact_source=contact_source,
        ats_type=ats_type,
        ats_allowed=ats_allowed,
        url_company=url_company,
        url=url,
        listing_status=listing_status,
    )
    final_bucket = _final_bucket(fit_status, listing_status, apply_path_status, verification_status)

    return {
        "fit_status": fit_status,
        "listing_status": listing_status,
        "apply_path_status": apply_path_status,
        "final_bucket": final_bucket,
    }


def _fit_status(decision: str, job_status: str, verification_status: str) -> str:
    if verification_status in {"verified_reject", "dead_listing"}:
        return "rejected"
    if job_status == "invalid" or decision == "reject":
        return "rejected"
    if decision == "apply":
        return "approved"
    return "review"


def _listing_status(*, listing_status: str, url_company: str, url: str, job_status: str) -> str:
    if job_status == "invalid":
        return "invalid"
    if listing_status:
        base = listing_status
    elif url_company or _looks_like_known_ats(url) or _looks_like_company_apply_page(url):
        base = "verified_direct"
    elif _is_jobboard_url(url):
        base = "jobboard_listing"
    else:
        base = "unverified"

    if url_company and (_looks_like_known_ats(url_company) or _looks_like_company_apply_page(url_company)):
        return "verified_direct"
    return base


def _apply_path_status(
    *,
    contact_email: str,
    contact_source: str,
    ats_type: str,
    ats_allowed: set[str],
    url_company: str,
    url: str,
    listing_status: str,
) -> str:
    if contact_email:
        if "manual_captcha_capture" in contact_source or "captcha" in contact_source:
            return "manual"
        return "auto"
    if ats_type and ats_type in ats_allowed:
        return "auto"
    if _looks_like_known_ats(url_company):
        return "auto"
    if _looks_like_known_ats(url):
        return "auto"
    if url_company and _looks_like_company_apply_page(url_company):
        return "manual"
    if listing_status == "verified_direct" and _looks_like_company_apply_page(url):
        return "manual"
    if _is_jobboard_url(url) or listing_status in {"jobboard_listing", "unverified"}:
        return "unresolved"
    return "unresolved"


def _final_bucket(fit_status: str, listing_status: str, apply_path_status: str, verification_status: str) -> str:
    if fit_status == "rejected":
        return "rejected"
    if fit_status == "review":
        return "needs_review"
    if verification_status == "verified_ready":
        return "manual_apply_ready"
    if apply_path_status == "auto":
        return "autoapply_ready"
    if listing_status == "verified_direct" and apply_path_status == "manual":
        return "manual_apply_ready"
    return "needs_review"


def _looks_like_known_ats(url: str) -> bool:
    host = _host(url)
    return any(hint in host for hint in KNOWN_ATS_HOST_HINTS)


def _is_jobboard_url(url: str) -> bool:
    host = _host(url)
    return any(hint in host for hint in JOBBOARD_HOST_HINTS)


def _looks_like_company_apply_page(url: str) -> bool:
    if not url:
        return False
    if _is_jobboard_url(url):
        return False
    host = _host(url)
    path = (urlparse(url).path or "").lower()
    return bool(host) and any(hint in path for hint in CAREER_PATH_HINTS)


def _host(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host
