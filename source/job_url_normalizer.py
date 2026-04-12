from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
    "trk",
    "trackingid",
    "trackingId",
}


def normalize_job_url(url: str, *, source: str = "") -> str:
    raw = (url or "").strip()
    if not raw:
        return ""

    parsed = urlparse(raw)
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    source_l = (source or "").strip().lower()

    if "arbeitsagentur.de" in host or source_l == "arbeitsagentur":
        aa_id = _extract_arbeitsagentur_id(parsed)
        if aa_id:
            return f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{aa_id}"

    if "indeed." in host or source_l == "indeed":
        job_key = parse_qs(parsed.query).get("jk", [""])[0].strip()
        if job_key:
            locale_host = host or "de.indeed.com"
            return f"https://{locale_host}/viewjob?jk={job_key}"

    if "stepstone." in host or source_l == "stepstone":
        normalized = _strip_query_and_fragment(parsed, keep_query_keys=set())
        return _normalize_stepstone_detail_url(normalized)

    if "linkedin." in host or source_l == "linkedin":
        return _strip_query_and_fragment(parsed, keep_query_keys=set())

    return _strip_tracking_params(parsed)


def _extract_arbeitsagentur_id(parsed) -> str:
    path_parts = [part for part in (parsed.path or "").split("/") if part]
    if "jobdetail" in path_parts:
        idx = path_parts.index("jobdetail")
        if idx + 1 < len(path_parts):
            return path_parts[idx + 1]

    query = parse_qs(parsed.query)
    aa_id = query.get("id", [""])[0].strip()
    if aa_id:
        return aa_id
    return ""


def _strip_query_and_fragment(parsed, *, keep_query_keys: set[str]) -> str:
    query = parse_qs(parsed.query, keep_blank_values=False)
    filtered = []
    for key in keep_query_keys:
        if key in query:
            for value in query[key]:
                filtered.append((key, value))
    new_query = urlencode(filtered, doseq=True)
    return urlunparse((parsed.scheme or "https", parsed.netloc, parsed.path, "", new_query, ""))


def _strip_tracking_params(parsed) -> str:
    query = parse_qs(parsed.query, keep_blank_values=False)
    filtered = []
    for key, values in query.items():
        if key in TRACKING_PARAMS:
            continue
        for value in values:
            filtered.append((key, value))
    new_query = urlencode(filtered, doseq=True)
    return urlunparse((parsed.scheme or "https", parsed.netloc, parsed.path, "", new_query, ""))


def _normalize_stepstone_detail_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path or ""
    if path.endswith("-inline.html"):
        path = path[: -len("-inline.html")] + "-.html"
    return urlunparse((parsed.scheme or "https", parsed.netloc, path, "", parsed.query, ""))
