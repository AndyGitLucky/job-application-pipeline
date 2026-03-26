"""
Links discovered contacts back to scored jobs.
"""

from __future__ import annotations

import json
from pathlib import Path

from job_buckets import classify_job
from pipeline_state_manager import attach_job_artifact, load_pipeline_state, save_pipeline_state
from project_paths import resolve_source_path, source_path

ROLE_PRIORITY = [
    "head of data",
    "head of ai",
    "ml lead",
    "data science lead",
    "head of engineering",
    "talent acquisition",
    "recruiter",
]


def enrich_jobs_with_contacts(
    jobs_path: str | Path = source_path("jobs_scored.json"),
    contacts_path: str | Path = source_path("contacts.json"),
    state_path: str | Path = source_path("pipeline_state.json"),
) -> int:
    jobs_file = resolve_source_path(jobs_path)
    contacts_file = resolve_source_path(contacts_path)
    if not jobs_file.exists() or not contacts_file.exists():
        return 0

    jobs = json.loads(jobs_file.read_text(encoding="utf-8"))
    contacts = json.loads(contacts_file.read_text(encoding="utf-8"))
    by_company = {}
    for contact in contacts:
        by_company.setdefault((contact.get("company") or "").strip().lower(), []).append(contact)

    linked = 0
    state = load_pipeline_state(state_path)
    for job in jobs:
        candidates = by_company.get((job.get("company") or "").strip().lower(), [])
        best = choose_best_contact(candidates)
        if not best:
            continue
        job["contact_email"] = best.get("email", "")
        job["contact_name"] = best.get("name", "")
        job["contact_role"] = best.get("role", "")
        job["contact_source"] = best.get("source", "")
        job.update(classify_job(job))
        if best.get("email"):
            linked += 1
            attach_job_artifact(state, job["id"], "contact_email", best["email"])

    jobs_file.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")
    save_pipeline_state(state, state_path)
    return linked


def choose_best_contact(candidates: list[dict]) -> dict | None:
    if not candidates:
        return None
    scored = []
    for contact in candidates:
        role = (contact.get("role") or "").lower()
        email = contact.get("email") or ""
        source = contact.get("source") or ""
        score = 0
        for index, token in enumerate(ROLE_PRIORITY):
            if token in role:
                score += 100 - index * 10
        if email:
            score += 30
        if "guessed" not in source:
            score += 10
        scored.append((score, contact))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]
