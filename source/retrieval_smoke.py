"""
Quick smoke test for retrieval quality.
"""

from __future__ import annotations

import argparse
import json

if __package__ in {None, ""}:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from source.project_paths import runtime_path
from source.retrieval_context import retrieve_relevant_context


def main() -> None:
    parser = argparse.ArgumentParser(description="Show retrieval snippets for selected jobs")
    parser.add_argument("--mode", choices=["application", "market_discovery"], default="application")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--job-indexes", default="0,1,4")
    args = parser.parse_args()

    jobs = json.loads(runtime_path("jobs_scored.json").read_text(encoding="utf-8"))
    indexes = [int(item.strip()) for item in args.job_indexes.split(",") if item.strip()]
    for index in indexes:
        if index >= len(jobs):
            continue
        job = jobs[index]
        print(f"JOB {index}: {job['title']} @ {job['company']}")
        for item in retrieve_relevant_context(job, limit=args.limit, mode=args.mode):
            print(f"- [{item['category']}] {item['text']}")
        print("-" * 60)


if __name__ == "__main__":
    main()
