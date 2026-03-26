"""
Cleanup and revalidation for existing job datasets.
"""

from __future__ import annotations

import json
from pathlib import Path

from pipeline_state_manager import load_pipeline_state, save_pipeline_state, update_job_stage
from find_jobs import invalid_job_reason
from project_paths import resolve_source_path, source_path


def cleanup_jobs(scored_path: str | Path = source_path("jobs_scored.json")) -> dict:
    path = resolve_source_path(scored_path)
    if not path.exists():
        return {"cleaned": 0, "invalidated": 0}

    jobs = json.loads(path.read_text(encoding="utf-8"))
    state = load_pipeline_state()
    cleaned = 0
    invalidated = 0

    for job in jobs:
        reason = invalid_job_reason(job)
        if reason:
            job["job_status"] = "invalid"
            job["validation_reason"] = reason
            job["recommended"] = False
            job["decision"] = "reject"
            job["decision_reason"] = reason
            invalidated += 1
            update_job_stage(
                state,
                str(job.get("id", "")),
                "validation",
                "completed",
                message=reason,
                extras={"job_status": "invalid"},
            )
        else:
            if job.get("job_status") == "invalid":
                cleaned += 1
            job["job_status"] = "live"
            job["validation_reason"] = ""

    path.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")
    save_pipeline_state(state)
    return {"cleaned": cleaned, "invalidated": invalidated}


if __name__ == "__main__":
    result = cleanup_jobs()
    print(result)
