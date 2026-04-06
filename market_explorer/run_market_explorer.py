from __future__ import annotations

import argparse
from pathlib import Path

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from market_explorer.app.render_dashboard import render_market_dashboard
from market_explorer.pipeline.collect_market_jobs import collect_market_jobs
from market_explorer.pipeline.build_market_dataset import build_market_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect and render a broad Germany-focused market explorer.")
    parser.add_argument("--reuse-existing", action="store_true", help="Reuse the last collected market dataset instead of fetching live.")
    parser.add_argument("--variant", choices=["signal", "classic", "plotly"], default="signal", help="Choose the dashboard visual variant.")
    parser.add_argument("--sources", choices=["all", "ba", "stepstone", "primary"], default="all", help="Limit the live collection to a specific source scope.")
    parser.add_argument("--ba-broad", action="store_true", help="Run Agentur fuer Arbeit as a city-first broad scan without job-title query terms.")
    parser.add_argument("--ba-radius-km", type=int, default=20, help="Radius in kilometers for Agentur fuer Arbeit queries.")
    parser.add_argument("--ba-page-size", type=int, default=100, help="Page size for Agentur fuer Arbeit API requests (max 100).")
    parser.add_argument("--ba-max-pages", type=int, default=0, help="Optional page cap for Agentur fuer Arbeit broad scans. Use 0 for no cap.")
    args = parser.parse_args()

    if not args.reuse_existing:
        collection = collect_market_jobs(
            source_scope=args.sources,
            include_secondary_source=True,
            include_primary_sources=args.sources in {"all", "primary"},
            ba_broad=args.ba_broad,
            ba_radius_km=args.ba_radius_km,
            ba_page_size=args.ba_page_size,
            ba_max_pages=(args.ba_max_pages or None),
        )
        print(f"Collected raw jobs: {collection['raw_jobs']}")
        print(f"Deduped jobs: {collection['deduped_jobs']}")
        print(f"Collection file: {collection['output_path']}")

    result = build_market_dataset()
    dashboard_path = render_market_dashboard(variant=args.variant)
    print(f"Market dataset: {result['job_count']} jobs")
    print(f"Jobs JSON: {result['jobs_path']}")
    print(f"Summary JSON: {result['summary_path']}")
    print(f"Dashboard: {dashboard_path}")


if __name__ == "__main__":
    main()
