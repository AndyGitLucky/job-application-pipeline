from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from source.feedback_store import record_feedback
from source.feedback_learning import refresh_feedback_summary
from source.generate_application import generate_applications
from source.pipeline_state_manager import (
    load_pipeline_state,
    save_pipeline_state,
    set_review_status,
    set_verification_status,
    update_job_stage,
)
from source.project_paths import runtime_path
from source.review_pipeline import update_job_record


APPLY_LOG_PATH = runtime_path("apply_log.json")
SCORED_JOBS_PATH = runtime_path("jobs_scored.json")


def _job_feedback_context(job_id: str) -> dict:
    try:
        jobs = json.loads(Path(SCORED_JOBS_PATH).read_text(encoding="utf-8"))
    except Exception:
        return {}
    for job in jobs:
        if str(job.get("id") or "") == str(job_id):
            return {
                "title": job.get("title", ""),
                "company": job.get("company", ""),
                "source": job.get("source", ""),
                "best_link_kind": job.get("best_link_kind", ""),
                "final_bucket": job.get("final_bucket", ""),
                "score": job.get("score", ""),
            }
    return {}


def generate_job_assets(job_id: str, note: str = "") -> str:
    generated = generate_applications(force=True, job_ids={job_id}, limit=1)
    if not generated:
        raise ValueError("Keine Unterlagen erzeugt")

    state = load_pipeline_state()
    update_job_stage(
        state,
        job_id,
        "generation",
        "completed",
        message=note or "manual_ui_generation",
    )
    save_pipeline_state(state)
    record_feedback(job_id, "generation", "generated", note or "manual_ui_generation", extra=_job_feedback_context(job_id))
    refresh_feedback_summary()

    cover_letter_pdf = str(generated[0].get("cover_letter_pdf") or "").strip()
    if cover_letter_pdf:
        return f"Unterlagen erzeugt: {cover_letter_pdf}"
    application_dir = str(generated[0].get("application_dir") or "").strip()
    if application_dir:
        return f"Unterlagen erzeugt: {application_dir}"
    return "Unterlagen erzeugt."


def mark_job_applied(job_id: str, note: str = "") -> None:
    _write_apply_log(job_id, status="sent", method="manual_ui", note=note)

    state = load_pipeline_state()
    update_job_stage(
        state,
        job_id,
        "apply",
        "completed",
        message=note or "manual_ui:sent",
        extras={"method": "manual_ui", "apply_status": "sent"},
    )
    save_pipeline_state(state)
    record_feedback(job_id, "apply", "sent", note or "manual_ui", extra=_job_feedback_context(job_id))
    refresh_feedback_summary()


def reject_job(job_id: str, note: str = "") -> None:
    state = load_pipeline_state()
    set_review_status(state, job_id, "rejected", note=note or "manual_ui_rejection")
    _set_state_decision(state, job_id, "reject", note or "manual_ui_rejection")
    save_pipeline_state(state)
    update_job_record(job_id, "reject", note or "manual_ui_rejection")
    record_feedback(job_id, "review", "reject", note or "manual_ui_rejection", extra=_job_feedback_context(job_id))
    refresh_feedback_summary()


def mark_dead_listing(job_id: str, note: str = "") -> None:
    state = load_pipeline_state()
    set_verification_status(state, job_id, "dead_listing", note=note or "manual_ui_dead_listing")
    _set_state_decision(state, job_id, "reject", note or "manual_ui_dead_listing")
    save_pipeline_state(state)
    update_job_record(job_id, "dead-listing", note or "manual_ui_dead_listing")
    record_feedback(job_id, "verification", "dead-listing", note or "manual_ui_dead_listing", extra=_job_feedback_context(job_id))
    refresh_feedback_summary()


def verify_job_ready(job_id: str, note: str = "") -> None:
    state = load_pipeline_state()
    set_verification_status(state, job_id, "verified_ready", note=note or "manual_ui_verified_ready")
    set_review_status(state, job_id, "approved", note=note or "manual_ui_verified_ready")
    _set_state_decision(state, job_id, "apply", note or "manual_ui_verified_ready")
    save_pipeline_state(state)
    update_job_record(job_id, "verify-ready", note or "manual_ui_verified_ready")
    record_feedback(job_id, "verification", "verify-ready", note or "manual_ui_verified_ready", extra=_job_feedback_context(job_id))
    refresh_feedback_summary()


def _set_state_decision(state: dict, job_id: str, decision: str, reason: str) -> None:
    entry = state.setdefault("jobs", {}).setdefault(job_id, {})
    existing = entry.get("decision")
    if not isinstance(existing, dict):
        existing = {}
        entry["decision"] = existing
    existing["decision"] = decision
    existing["decision_reason"] = reason


def perform_ui_action(job_id: str, action: str, note: str = "") -> str:
    normalized = action.strip().lower().replace("-", "_")
    if normalized == "generate_application":
        return generate_job_assets(job_id, note)
    if normalized == "mark_applied":
        mark_job_applied(job_id, note)
        return "Job als beworben markiert."
    if normalized == "reject":
        reject_job(job_id, note)
        return "Job als ungeeignet markiert."
    if normalized == "dead_listing":
        mark_dead_listing(job_id, note)
        return "Job als Dead Listing markiert."
    if normalized == "verify_ready":
        verify_job_ready(job_id, note)
        return "Job freigegeben."
    raise ValueError(f"Unbekannte Aktion: {action}")


def _write_apply_log(job_id: str, *, status: str, method: str, note: str) -> None:
    path = Path(APPLY_LOG_PATH)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    else:
        data = {}

    data[str(job_id)] = {
        "method": method,
        "status": status,
        "note": note,
        "timestamp": datetime.now().isoformat(),
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
