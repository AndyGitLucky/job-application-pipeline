"""
CLI for handling manual review decisions in the pipeline.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from feedback_store import record_feedback
from job_buckets import classify_job
from pipeline_state_manager import (
    load_pipeline_state,
    save_pipeline_state,
    set_review_status,
    set_verification_status,
)
from primary_source_registry import remember_primary_source
from project_paths import source_path


def list_pending() -> int:
    state = load_pipeline_state()
    pending_ids = state.get("review_queue", [])
    for job_id in pending_ids:
        job = state["jobs"].get(job_id, {})
        decision = job.get("decision", {})
        print(
            json.dumps(
                {
                    "job_id": job_id,
                    "company": job.get("company"),
                    "title": job.get("title"),
                    "reason": decision.get("decision_reason"),
                    "score": job.get("metrics", {}).get("score"),
                    "risk_flags": decision.get("risk_flags", []),
                },
                ensure_ascii=False,
            )
        )
    return len(pending_ids)


def list_verification_queue(limit: int = 20) -> int:
    scored_path = source_path("jobs_scored.json")
    if not scored_path.exists():
        print("verification_queue_jobs=0")
        return 0

    jobs = json.loads(scored_path.read_text(encoding="utf-8"))
    queued = [job for job in jobs if job.get("final_bucket") == "needs_review"]
    queued.sort(key=lambda item: (item.get("score") or 0), reverse=True)
    for job in queued[:limit]:
        print(
            json.dumps(
                {
                    "job_id": job.get("id"),
                    "company": job.get("company"),
                    "title": job.get("title"),
                    "score": job.get("score"),
                    "decision": job.get("decision"),
                    "listing_status": job.get("listing_status"),
                    "apply_path_status": job.get("apply_path_status"),
                    "verification_status": job.get("verification_status", "unverified"),
                    "risk_flags": job.get("risk_flags", []),
                },
                ensure_ascii=False,
            )
        )
    print(f"verification_queue_jobs={len(queued)}")
    return len(queued)


def decide(job_id: str, action: str, note: str = "") -> None:
    state = load_pipeline_state()
    status_map = {
        "approve": "approved",
        "reject": "rejected",
        "hold": "pending",
    }
    review_status = status_map[action]
    set_review_status(state, job_id, review_status, note=note or action)
    update_job_record(job_id, action, note)
    if action == "approve":
        state["jobs"][job_id].setdefault("decision", {})["decision"] = "apply"
        state["jobs"][job_id]["decision"]["decision_reason"] = note or "manual_approval"
    elif action == "reject":
        state["jobs"][job_id].setdefault("decision", {})["decision"] = "reject"
        state["jobs"][job_id]["decision"]["decision_reason"] = note or "manual_rejection"
    save_pipeline_state(state)
    record_feedback(job_id, "review", action, note)


def verify(job_id: str, action: str, note: str = "") -> None:
    state = load_pipeline_state()
    verification_map = {
        "verify-ready": "verified_ready",
        "verify-reject": "verified_reject",
        "dead-listing": "dead_listing",
    }
    verification_status = verification_map[action]
    state = set_verification_status(state, job_id, verification_status, note=note or action)
    update_job_record(job_id, action, note)
    save_pipeline_state(state)
    record_feedback(job_id, "verification", action, note)


def update_job_record(job_id: str, action: str, note: str = "") -> None:
    scored_path = source_path("jobs_scored.json")
    if not scored_path.exists():
        return

    jobs = json.loads(scored_path.read_text(encoding="utf-8"))
    target_job = None
    for job in jobs:
        if str(job.get("id")) == job_id:
            target_job = job
            break
    if not target_job:
        return

    if action == "approve":
        target_job["decision"] = "apply"
        target_job["decision_reason"] = note or "manual_approval"
        target_job["review_status"] = "approved"
    elif action == "reject":
        target_job["decision"] = "reject"
        target_job["decision_reason"] = note or "manual_rejection"
        target_job["review_status"] = "rejected"
    elif action == "hold":
        target_job["review_status"] = "pending"
    elif action == "verify-ready":
        target_job["verification_status"] = "verified_ready"
        target_job["verification_note"] = note or "manually_verified_ready"
        target_job["listing_status"] = "verified_direct"
        target_job["review_status"] = "approved"
        target_job["decision"] = "apply"
        target_job["decision_reason"] = note or "manually_verified_ready"
        learned = remember_primary_source(
            target_job.get("url_company") or target_job.get("apply_url") or target_job.get("url") or "",
            company=target_job.get("company", ""),
            location=target_job.get("location", ""),
        )
        if learned:
            target_job["primary_source_learned"] = True
            target_job["primary_source_type"] = learned.get("type", "")
    elif action == "verify-reject":
        target_job["verification_status"] = "verified_reject"
        target_job["verification_note"] = note or "manually_verified_reject"
        target_job["decision"] = "reject"
        target_job["decision_reason"] = note or "verified_reject"
    elif action == "dead-listing":
        target_job["verification_status"] = "dead_listing"
        target_job["verification_note"] = note or "dead_listing"
        target_job["job_status"] = "invalid"
        target_job["validation_reason"] = note or "dead_listing"
        target_job["decision"] = "reject"
        target_job["decision_reason"] = note or "dead_listing"

    target_job.update(classify_job(target_job))
    scored_path.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")
    _update_meta_if_present(target_job)


def _update_meta_if_present(job: dict) -> None:
    applications_dir = source_path("applications")
    if not applications_dir.exists():
        return
    job_id = str(job.get("id") or "").strip()
    if not job_id:
        return
    matches = list(applications_dir.glob(f"*_{job_id}"))
    if not matches:
        return
    meta_path = matches[0] / "meta.json"
    if not meta_path.exists():
        return
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        meta = {}
    for key in (
        "decision",
        "decision_reason",
        "review_status",
        "verification_status",
        "verification_note",
        "primary_source_learned",
        "primary_source_type",
        "job_status",
        "validation_reason",
        "listing_status",
        "apply_path_status",
        "final_bucket",
    ):
        if key in job:
            meta[key] = job[key]
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manual review handling for pipeline jobs")
    parser.add_argument("--list", action="store_true", help="List pending review jobs")
    parser.add_argument("--list-verification", action="store_true", help="List jobs that still need live verification")
    parser.add_argument("--job-id", default="", help="Job id to update")
    parser.add_argument(
        "--action",
        choices=["approve", "reject", "hold", "verify-ready", "verify-reject", "dead-listing"],
        help="Review or verification action",
    )
    parser.add_argument("--note", default="", help="Optional review note")
    args = parser.parse_args()

    if args.list:
        count = list_pending()
        print(f"pending_review_jobs={count}")
        return

    if args.list_verification:
        list_verification_queue()
        return

    if not args.job_id or not args.action:
        parser.error("--job-id and --action are required unless --list is used")
    if args.action in {"approve", "reject", "hold"}:
        decide(args.job_id, args.action, args.note)
    else:
        verify(args.job_id, args.action, args.note)
    print(f"updated {args.job_id} -> {args.action}")


if __name__ == "__main__":
    main()
