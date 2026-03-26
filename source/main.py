"""
main.py
=======
Main orchestrator for the automated job application pipeline.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta

from contact_linker import enrich_jobs_with_contacts
from find_contacts import find_contacts
from find_jobs import find_jobs
from generate_application import generate_applications
from pipeline_state_manager import (
    append_run,
    load_pipeline_state,
    save_pipeline_state,
    sync_jobs,
)
from present_dashboard import generate_present_dashboard
from present_server import serve_present_ui
from project_paths import source_path
from score_jobs import score_jobs
from verify_jobs import verify_jobs

LOG_FILE = source_path("pipeline.log")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.root.handlers.clear()
logging.root.setLevel(logging.INFO)

formatter = logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%H:%M:%S")
console = logging.StreamHandler(sys.stdout)
console.setFormatter(formatter)
logging.root.addHandler(console)

file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
file_handler.setFormatter(formatter)
logging.root.addHandler(file_handler)

log = logging.getLogger(__name__)

CONFIG = {
    "loop_interval_hours": 24,
    "min_hours_between_runs": 12,
    "steps": {
        "find_jobs": True,
        "score_jobs": True,
        "find_contacts": False,
        "verify_jobs": True,
        "generate": False,
    },
}


def too_soon(state: dict) -> bool:
    if not state.get("last_run"):
        return False
    last_run = datetime.fromisoformat(state["last_run"])
    min_gap = timedelta(hours=CONFIG["min_hours_between_runs"])
    return (datetime.now() - last_run) < min_gap


def print_banner(run_number: int) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    width = 54
    log.info("+" + "=" * width + "+")
    log.info("|" + " Job Pipeline ".center(width) + "|")
    log.info("|" + f" Run #{run_number:<6} {now}".center(width) + "|")
    log.info("+" + "=" * width + "+")


def print_step(step: str) -> None:
    log.info("")
    log.info("-" * 60)
    log.info("  > %s", step)
    log.info("-" * 60)


def print_summary(stats: dict) -> None:
    log.info("")
    log.info("=" * 60)
    log.info("  SUMMARY")
    log.info("=" * 60)
    for key, value in stats.items():
        log.info("  %-30s %s", key, value)
    log.info("=" * 60)


def run_pipeline(dry_run: bool = False, steps_override: list[str] | None = None) -> dict:
    stats = {
        "Started": datetime.now().strftime("%H:%M:%S"),
        "Jobs found": 0,
        "Recommended": 0,
        "Contacts found": 0,
        "Jobs linked to contacts": 0,
        "Jobs verified": 0,
        "Applications generated": 0,
        "Applications processed": 0,
        "Pending review": 0,
        "Present UI": "",
        "Errors": 0,
    }
    steps = steps_override or [name for name, enabled in CONFIG["steps"].items() if enabled]
    state = load_pipeline_state()

    if "find_jobs" in steps:
        print_step("1 / 5 - find_jobs()")
        try:
            jobs = find_jobs()
            stats["Jobs found"] = len(jobs)
            sync_jobs(state, jobs, stage="discovered")
            save_pipeline_state(state)
        except Exception as exc:
            log.error("find_jobs failed: %s", exc)
            stats["Errors"] += 1

    if "score_jobs" in steps:
        print_step("2 / 5 - score_jobs()")
        try:
            recommended = score_jobs()
            stats["Recommended"] = len(recommended)
        except Exception as exc:
            log.error("score_jobs failed: %s", exc)
            stats["Errors"] += 1

    if "find_contacts" in steps:
        print_step("3 / 4 - find_contacts()")
        try:
            contacts = find_contacts()
            stats["Contacts found"] = len(contacts)
            stats["Jobs linked to contacts"] = enrich_jobs_with_contacts()
        except Exception as exc:
            log.error("find_contacts failed: %s", exc)
            stats["Errors"] += 1

    if "verify_jobs" in steps:
        print_step("4 / 4 - verify_jobs()")
        try:
            verified = verify_jobs()
            stats["Jobs verified"] = len(verified)
        except Exception as exc:
            log.error("verify_jobs failed: %s", exc)
            stats["Errors"] += 1

    if "generate" in steps:
        print_step("optional - generate_applications()")
        try:
            generated = generate_applications()
            stats["Applications generated"] = len(generated)
        except Exception as exc:
            log.error("generate_applications failed: %s", exc)
            stats["Errors"] += 1

    stats["Finished"] = datetime.now().strftime("%H:%M:%S")
    stats["Pending review"] = len(load_pipeline_state().get("review_queue", []))
    try:
        dashboard_path = generate_present_dashboard()
        stats["Present UI"] = str(dashboard_path)
    except Exception as exc:
        log.error("present_dashboard failed: %s", exc)
        stats["Errors"] += 1
    return stats


def run_loop(dry_run: bool = False) -> None:
    state = load_pipeline_state()
    run_number = len(state.get("runs", [])) + 1

    while True:
        if too_soon(state):
            next_run = datetime.fromisoformat(state["last_run"]) + timedelta(hours=CONFIG["min_hours_between_runs"])
            wait_seconds = max((next_run - datetime.now()).total_seconds(), 0)
            log.info("Zu frueh. Warte %.1fh bis %s", wait_seconds / 3600, next_run.strftime("%H:%M"))
            time.sleep(min(wait_seconds, 3600))
            state = load_pipeline_state()
            continue

        print_banner(run_number)
        stats = run_pipeline(dry_run=dry_run)
        print_summary(stats)

        state = load_pipeline_state()
        append_run(state, run_number, stats)
        save_pipeline_state(state)

        interval = CONFIG["loop_interval_hours"] * 3600
        next_dt = datetime.now() + timedelta(seconds=interval)
        log.info("Naechster Durchlauf: %s", next_dt.strftime("%d.%m.%Y %H:%M"))
        run_number += 1

        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            log.info("Pipeline gestoppt.")
            break


def main() -> None:
    parser = argparse.ArgumentParser(description="Jobsuche Pipeline")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--step", choices=["find_jobs", "score_jobs", "find_contacts", "verify_jobs", "generate"])
    parser.add_argument("--interval", type=int, default=CONFIG["loop_interval_hours"])
    parser.add_argument("--no-ui", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    if args.interval != CONFIG["loop_interval_hours"]:
        CONFIG["loop_interval_hours"] = args.interval
        CONFIG["min_hours_between_runs"] = max(1, args.interval // 2)

    steps_override = [args.step] if args.step else None

    if args.loop:
        run_loop(dry_run=args.dry_run)
        return

    state = load_pipeline_state()
    run_number = len(state.get("runs", [])) + 1
    print_banner(run_number)
    stats = run_pipeline(dry_run=args.dry_run, steps_override=steps_override)
    print_summary(stats)

    state = load_pipeline_state()
    append_run(state, run_number, stats)
    save_pipeline_state(state)

    should_launch_ui = not args.no_ui and not args.loop and not args.step
    if should_launch_ui:
        log.info("")
        log.info("Starte Present UI auf http://%s:%s", args.host, args.port)
        serve_present_ui(args.host, args.port, open_browser=True)


if __name__ == "__main__":
    main()
