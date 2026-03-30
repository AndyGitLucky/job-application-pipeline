"""
Small observability report for current pipeline state.
"""

from __future__ import annotations

import json
from collections import Counter

if __package__ in {None, ""}:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from source.pipeline_state_manager import load_pipeline_state
from source.project_paths import runtime_path


def main() -> None:
    state = load_pipeline_state()
    jobs = state.get("jobs", {})
    stage_counter = Counter()
    decision_counter = Counter()
    review_counter = Counter()
    bucket_counter = Counter()

    jobs_scored_by_id = {}
    scored_path = runtime_path("jobs_scored.json")
    if scored_path.exists():
        try:
            jobs_scored = json.loads(scored_path.read_text(encoding="utf-8"))
            jobs_scored_by_id = {str(job.get("id", "")): job for job in jobs_scored if job.get("id")}
        except Exception:
            jobs_scored_by_id = {}

    for job_id, job in jobs.items():
        stage_counter[(job.get("current_stage"), job.get("stage_status"))] += 1
        decision_counter[(job.get("decision") or {}).get("decision", "unknown")] += 1
        review_counter[job.get("review_status", "unknown")] += 1
        scored_job = jobs_scored_by_id.get(job_id, {})
        bucket = (
            job.get("metrics", {}).get("final_bucket")
            or scored_job.get("final_bucket")
            or "unknown"
        )
        bucket_counter[bucket] += 1

    print("stage_status_counts")
    for key, value in sorted(stage_counter.items()):
        print(f"{key[0]}::{key[1]}={value}")

    print("decision_counts")
    for key, value in sorted(decision_counter.items()):
        print(f"{key}={value}")

    print("review_counts")
    for key, value in sorted(review_counter.items()):
        print(f"{key}={value}")

    print("bucket_counts")
    for key, value in sorted(bucket_counter.items()):
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
