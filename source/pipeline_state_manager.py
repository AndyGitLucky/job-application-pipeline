"""
Active state tracking for the job application pipeline.

The file format keeps the legacy run history while adding explicit per-job state.
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from project_paths import source_path

DEFAULT_STATE = {
    "last_run": None,
    "runs": [],
    "jobs": {},
    "review_queue": [],
}


def load_pipeline_state(path: str | Path = source_path("pipeline_state.json")) -> dict:
    state_path = Path(path)
    if not state_path.exists():
        return deepcopy(DEFAULT_STATE)

    raw = json.loads(state_path.read_text(encoding="utf-8"))
    state = deepcopy(DEFAULT_STATE)
    state.update(raw)
    state.setdefault("jobs", {})
    state.setdefault("runs", [])
    state.setdefault("review_queue", [])
    return state


def save_pipeline_state(state: dict, path: str | Path = source_path("pipeline_state.json")) -> None:
    Path(path).write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def sync_jobs(state: dict, jobs: list[dict], stage: str = "discovered") -> dict:
    now = datetime.now().isoformat()
    current_job_ids: set[str] = set()
    for job in jobs:
        job_id = str(job.get("id") or "").strip()
        if not job_id:
            continue
        current_job_ids.add(job_id)

        entry = state["jobs"].setdefault(job_id, _new_job_state(job, stage, now))
        entry["title"] = job.get("title", entry.get("title", ""))
        entry["company"] = job.get("company", entry.get("company", ""))
        entry["location"] = job.get("location", entry.get("location", ""))
        entry["source"] = job.get("source", entry.get("source", ""))
        entry["job_url"] = job.get("url", entry.get("job_url", ""))
        entry["last_seen_at"] = now
        entry["current_stage"] = stage
        entry["stage_status"] = "ready"

    _refresh_review_queue_for_current_jobs(state, current_job_ids)
    return state


def update_job_stage(
    state: dict,
    job_id: str,
    stage: str,
    status: str,
    *,
    message: str = "",
    error: str = "",
    extras: dict | None = None,
) -> dict:
    entry = state["jobs"].setdefault(job_id, _new_job_state({}, stage, datetime.now().isoformat()))
    now = datetime.now().isoformat()

    entry["current_stage"] = stage
    entry["stage_status"] = status
    entry["updated_at"] = now
    if error:
        entry["last_error"] = error
        entry["retry_count"] = int(entry.get("retry_count", 0)) + 1

    history_item = {
        "timestamp": now,
        "stage": stage,
        "status": status,
    }
    if message:
        history_item["message"] = message
    if error:
        history_item["error"] = error
    if extras:
        history_item["extras"] = extras
        entry.setdefault("metrics", {}).update(extras)

    entry.setdefault("history", []).append(history_item)
    return state


def update_job_decision(state: dict, job_id: str, decision: dict) -> dict:
    entry = state["jobs"].setdefault(job_id, _new_job_state({}, "decision", datetime.now().isoformat()))
    entry["decision"] = decision
    entry["review_status"] = decision.get("review_status", entry.get("review_status", "not_required"))
    entry.setdefault("metrics", {}).update(
        {
            "score": decision.get("score"),
            "score_band": decision.get("score_band"),
            "recommended": decision.get("recommended"),
        }
    )
    update_job_stage(
        state,
        job_id,
        "decision",
        "completed",
        message=decision.get("decision_reason", ""),
        extras={"decision": decision.get("decision"), "next_action": decision.get("next_action")},
    )
    _refresh_review_queue(state, job_id)
    return state


def attach_job_artifact(state: dict, job_id: str, artifact_name: str, artifact_path: str) -> dict:
    entry = state["jobs"].setdefault(job_id, _new_job_state({}, "artifact", datetime.now().isoformat()))
    entry.setdefault("artifacts", {})[artifact_name] = artifact_path
    entry["updated_at"] = datetime.now().isoformat()
    return state


def append_run(state: dict, run_number: int, stats: dict) -> dict:
    now = datetime.now().isoformat()
    state["last_run"] = now
    state.setdefault("runs", []).append({"run": run_number, "time": now, "stats": stats})
    return state


def set_review_status(state: dict, job_id: str, review_status: str, note: str = "") -> dict:
    entry = state["jobs"].setdefault(job_id, _new_job_state({}, "review", datetime.now().isoformat()))
    entry["review_status"] = review_status
    update_job_stage(state, job_id, "review", "completed", message=note or review_status)
    _refresh_review_queue(state, job_id)
    return state


def set_verification_status(
    state: dict,
    job_id: str,
    verification_status: str,
    note: str = "",
    *,
    extras: dict | None = None,
) -> dict:
    entry = state["jobs"].setdefault(job_id, _new_job_state({}, "verification", datetime.now().isoformat()))
    entry["verification_status"] = verification_status
    entry["verification_note"] = note
    update_job_stage(
        state,
        job_id,
        "verification",
        "completed",
        message=note or verification_status,
        extras={"verification_status": verification_status, **(extras or {})},
    )
    return state


def can_proceed_to_apply(state: dict, job_id: str) -> bool:
    entry = state.get("jobs", {}).get(job_id, {})
    decision = (entry.get("decision") or {}).get("decision")
    review_status = entry.get("review_status", "not_required")
    if decision == "reject":
        return False
    if review_status in {"approved", "not_required"}:
        return True
    return decision == "apply" and review_status == "not_required"


def get_jobs_for_stage(state: dict, stage: str, *, statuses: set[str] | None = None) -> list[tuple[str, dict]]:
    results = []
    for job_id, job_state in state.get("jobs", {}).items():
        if job_state.get("current_stage") != stage:
            continue
        if statuses and job_state.get("stage_status") not in statuses:
            continue
        results.append((job_id, job_state))
    return results


def _new_job_state(job: dict, stage: str, now: str) -> dict:
    return {
        "title": job.get("title", ""),
        "company": job.get("company", ""),
        "location": job.get("location", ""),
        "source": job.get("source", ""),
        "job_url": job.get("url", ""),
        "current_stage": stage,
        "stage_status": "ready",
        "decision": {},
        "metrics": {},
        "artifacts": {},
        "history": [],
        "last_error": "",
        "retry_count": 0,
        "review_status": "pending" if stage == "review" else "not_required",
        "verification_status": "unverified",
        "verification_note": "",
        "created_at": now,
        "updated_at": now,
        "last_seen_at": now,
    }


def _refresh_review_queue(state: dict, job_id: str) -> None:
    queue = [item for item in state.get("review_queue", []) if item != job_id]
    entry = state.get("jobs", {}).get(job_id, {})
    if entry.get("review_status") == "pending":
        queue.append(job_id)
    state["review_queue"] = queue


def _refresh_review_queue_for_current_jobs(state: dict, current_job_ids: set[str]) -> None:
    state["review_queue"] = [
        job_id
        for job_id in current_job_ids
        if state.get("jobs", {}).get(job_id, {}).get("review_status") == "pending"
    ]
