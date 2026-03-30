"""
Prioritizes `needs_review` jobs into a small live-verification queue.
"""

from __future__ import annotations

import json
from pathlib import Path

from source.project_paths import resolve_runtime_path, runtime_path


NEGATIVE_RISK_FLAGS = {
    "degree_required": 30,
    "research_risk": 40,
    "seniority_risk": 18,
    "software_focus_risk": 10,
    "thin_description": 8,
}


def verification_priority(job: dict) -> tuple[int, list[str]]:
    score = int(job.get("score") or 0) * 10
    reasons: list[str] = []

    if (job.get("final_bucket") or "") != "needs_review":
        return -999, ["not_in_review_bucket"]

    decision = (job.get("decision") or "").lower()
    if decision == "reject" or (job.get("job_status") or "").lower() == "invalid":
        return -999, ["rejected_or_invalid"]

    priority = score
    reasons.append(f"score={job.get('score', 0)}")

    listing_status = (job.get("listing_status") or "").lower()
    if listing_status == "jobboard_listing":
        priority -= 5
        reasons.append("jobboard_listing")
    elif listing_status == "verified_direct":
        priority += 20
        reasons.append("verified_direct")

    if (job.get("source") or "").lower() == "stepstone":
        priority += 3
        reasons.append("stepstone_source")

    if not job.get("degree_required"):
        priority += 8
        reasons.append("no_degree_gate")

    company = (job.get("company") or "").strip().lower()
    if company and company != "nan":
        priority += 2
        reasons.append("named_company")
    else:
        priority -= 10
        reasons.append("missing_company")

    for flag in job.get("risk_flags", []) or []:
        penalty = NEGATIVE_RISK_FLAGS.get(flag, 0)
        if penalty:
            priority -= penalty
            reasons.append(f"risk:{flag}")

    if (job.get("apply_path_status") or "").lower() == "unresolved":
        priority -= 4
        reasons.append("unresolved_apply_path")

    return priority, reasons


def build_verification_queue(
    input_file: str | Path = runtime_path("jobs_scored.json"),
    limit: int = 10,
) -> list[dict]:
    input_path = resolve_runtime_path(input_file)
    if not input_path.exists():
        return []

    jobs = json.loads(input_path.read_text(encoding="utf-8"))
    queue = []
    for job in jobs:
        priority, reasons = verification_priority(job)
        if priority < 0:
            continue
        queue.append(
            {
                "id": job.get("id"),
                "company": job.get("company"),
                "title": job.get("title"),
                "score": job.get("score"),
                "source": job.get("source"),
                "listing_status": job.get("listing_status"),
                "apply_path_status": job.get("apply_path_status"),
                "risk_flags": job.get("risk_flags", []),
                "url": job.get("url"),
                "verification_priority": priority,
                "verification_reasons": reasons,
            }
        )

    queue.sort(key=lambda item: item["verification_priority"], reverse=True)
    return queue[:limit]


def main() -> None:
    queue = build_verification_queue()
    print("verification_queue")
    for idx, item in enumerate(queue, start=1):
        print(
            f"{idx}. [{item['verification_priority']}] {item['company']} | "
            f"{item['title']} | score={item['score']} | "
            f"listing={item['listing_status']} | apply_path={item['apply_path_status']}"
        )
        print(f"   why: {', '.join(item['verification_reasons'])}")
        print(f"   url: {item['url']}")


if __name__ == "__main__":
    main()
