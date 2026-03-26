from __future__ import annotations

import json
from pathlib import Path

from project_paths import resolve_source_path, source_path


DEFAULT_APPLY_LOG = source_path("apply_log.json")

HIDDEN_APPLY_STATUSES = {
    "sent",
}

HIDDEN_REVIEW_STATUSES = {
    "rejected",
}

HIDDEN_VERIFICATION_STATUSES = {
    "verified_reject",
    "dead_listing",
}

HIDDEN_FINAL_BUCKETS = {
    "rejected",
}

HIDDEN_DECISIONS = {
    "reject",
}


def load_apply_log(path: str | Path | None = None) -> dict[str, dict]:
    log_path = resolve_source_path(path or DEFAULT_APPLY_LOG)
    if not log_path.exists():
        return {}
    try:
        data = json.loads(log_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): value for key, value in data.items() if isinstance(value, dict)}


def should_hide_job(job: dict, apply_log: dict[str, dict] | None = None) -> bool:
    if _is_rejected(job):
        return True

    job_id = str(job.get("id") or "").strip()
    if not job_id or not apply_log:
        return False

    entry = apply_log.get(job_id, {})
    apply_status = str(entry.get("status") or "").strip().lower()
    return apply_status in HIDDEN_APPLY_STATUSES


def hidden_reason(job: dict, apply_log: dict[str, dict] | None = None) -> str:
    if _is_rejected(job):
        return "rejected"

    job_id = str(job.get("id") or "").strip()
    if not job_id or not apply_log:
        return ""

    entry = apply_log.get(job_id, {})
    apply_status = str(entry.get("status") or "").strip().lower()
    if apply_status in HIDDEN_APPLY_STATUSES:
        return f"applied:{apply_status}"
    return ""


def _is_rejected(job: dict) -> bool:
    decision = str(job.get("decision") or "").strip().lower()
    review_status = str(job.get("review_status") or "").strip().lower()
    verification_status = str(job.get("verification_status") or "").strip().lower()
    final_bucket = str(job.get("final_bucket") or "").strip().lower()

    return any(
        (
            decision in HIDDEN_DECISIONS,
            review_status in HIDDEN_REVIEW_STATUSES,
            verification_status in HIDDEN_VERIFICATION_STATUSES,
            final_bucket in HIDDEN_FINAL_BUCKETS,
        )
    )
