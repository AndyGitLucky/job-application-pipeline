"""
Stores human and outcome feedback for jobs.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from source.project_paths import runtime_path

DEFAULT_PATH = runtime_path("feedback_log.json")


def load_feedback(path: str | Path = DEFAULT_PATH) -> dict:
    feedback_path = Path(path)
    if feedback_path.exists():
        return json.loads(feedback_path.read_text(encoding="utf-8"))
    return {}


def save_feedback(feedback: dict, path: str | Path = DEFAULT_PATH) -> None:
    Path(path).write_text(json.dumps(feedback, ensure_ascii=False, indent=2), encoding="utf-8")


def record_feedback(
    job_id: str,
    category: str,
    value: str,
    note: str = "",
    *,
    extra: dict | None = None,
    path: str | Path = DEFAULT_PATH,
) -> None:
    feedback = load_feedback(path)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "category": category,
        "value": value,
        "note": note,
    }
    if isinstance(extra, dict):
        for key, value in extra.items():
            if key not in entry and value not in (None, ""):
                entry[key] = value
    feedback.setdefault(job_id, []).append(entry)
    save_feedback(feedback, path)
