"""
Verification layer between scoring and generation.

Goal:
- best-effort resolve a real apply path
- persist verification status
- only promote truly verified jobs toward generation
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from source.ats_handlers import detect_ats
from source.company_url_resolver import (
    looks_like_known_ats_url,
    looks_like_specific_company_apply_url,
    resolve_company_apply_url,
)
from source.job_buckets import classify_job
from source.pipeline_state_manager import (
    load_pipeline_state,
    save_pipeline_state,
    set_verification_status,
    sync_jobs,
    update_job_stage,
)
from source.primary_source_registry import remember_primary_source
from source.project_paths import resolve_runtime_path, runtime_path

log = logging.getLogger(__name__)

CONFIG = {
    "input_file": str(runtime_path("jobs_scored.json")),
    "output_file": str(runtime_path("jobs_scored.json")),
    "max_jobs": 25,
}


def verify_jobs(
    input_file: str | Path | None = None,
    output_file: str | Path | None = None,
    *,
    limit: int | None = None,
) -> list[dict]:
    input_path = resolve_runtime_path(input_file or CONFIG["input_file"])
    output_path = resolve_runtime_path(output_file or CONFIG["output_file"])
    if not input_path.exists():
        log.error("Input-Datei nicht gefunden: %s", input_path)
        return []

    jobs = json.loads(input_path.read_text(encoding="utf-8"))
    state = load_pipeline_state()
    sync_jobs(state, jobs, stage="verification")

    candidates = [
        job for job in jobs
        if job.get("recommended")
        and job.get("job_status", "live") != "invalid"
        and (job.get("verification_status") or "unverified") not in {"verified_ready", "verified_reject", "dead_listing"}
    ]
    candidates.sort(key=lambda item: int(item.get("score") or 0), reverse=True)
    max_jobs = limit if limit is not None else CONFIG["max_jobs"]
    candidates = candidates[: max(0, int(max_jobs))]

    verified: list[dict] = []
    for idx, job in enumerate(candidates, start=1):
        job_id = str(job.get("id") or "").strip()
        if not job_id:
            continue
        update_job_stage(state, job_id, "verification", "in_progress", message="verification_started")
        try:
            resolved = resolve_company_apply_url(
                job.get("url", ""),
                job.get("description", ""),
                company=job.get("company", ""),
                title=job.get("title", ""),
            )
            if resolved.url:
                resolved_ats_type = detect_ats(resolved.url)
                if not (
                    looks_like_known_ats_url(resolved.url)
                    or looks_like_specific_company_apply_url(resolved.url, job.get("title", ""))
                ):
                    job.setdefault("verification_status", "unverified")
                    job["verification_note"] = "generic_company_page"
                    job["verification_failure_type"] = "generic_company_page"
                    job["verification_detail"] = resolved.url
                    job["verification_http_status"] = int(resolved.http_status or 0)
                    update_job_stage(
                        state,
                        job_id,
                        "verification",
                        "completed",
                        message="generic_company_page",
                        extras={
                            "verification_status": job.get("verification_status", "unverified"),
                            "verification_failure_type": "generic_company_page",
                            "verification_http_status": int(resolved.http_status or 0),
                        },
                    )
                    job.update(classify_job(job))
                    verified.append(job)
                    continue
                job["url_company"] = resolved.url
                job["url_company_source"] = resolved.source
                job["ats_type"] = resolved_ats_type
                learned = remember_primary_source(
                    resolved.url,
                    company=job.get("company", ""),
                    location=job.get("location", ""),
                )
                job["verification_status"] = "verified_ready"
                job["verification_note"] = f"resolved_via_{resolved.source}"
                job["verification_failure_type"] = ""
                job["verification_detail"] = ""
                job["verification_http_status"] = 0
                if learned:
                    job["primary_source_learned"] = True
                    job["primary_source_type"] = learned.get("type", "")
                state = set_verification_status(
                    state,
                    job_id,
                    "verified_ready",
                    f"resolved_via_{resolved.source}",
                    extras={
                        "url_company": resolved.url,
                        "ats_type": job.get("ats_type", ""),
                        "primary_source_type": job.get("primary_source_type", ""),
                    },
                )
            else:
                job.setdefault("verification_status", "unverified")
                failure_type = resolved.failure_type or "unverified"
                detail = resolved.detail or ""
                http_status = int(resolved.http_status or 0)
                job["verification_note"] = failure_type
                job["verification_failure_type"] = failure_type
                job["verification_detail"] = detail
                job["verification_http_status"] = http_status
                update_job_stage(
                    state,
                    job_id,
                    "verification",
                    "completed",
                    message=failure_type,
                    extras={
                        "verification_status": job.get("verification_status", "unverified"),
                        "verification_failure_type": failure_type,
                        "verification_http_status": http_status,
                    },
                )

            job.update(classify_job(job))
            verified.append(job)
            log.info(
                "[%s/%s] %s @ %s -> %s / %s",
                idx,
                len(candidates),
                job.get("title", "")[:50],
                job.get("company", "")[:30],
                job.get("verification_status", "unverified"),
                job.get("final_bucket", "unknown"),
            )
        except Exception as exc:
            update_job_stage(state, job_id, "verification", "failed", error=str(exc))
            log.warning("verification failed for %s: %s", job.get("title", ""), exc)

    output_path.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")
    save_pipeline_state(state)
    return verified


if __name__ == "__main__":
    verify_jobs()
