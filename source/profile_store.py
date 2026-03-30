from __future__ import annotations

import json
from pathlib import Path

from source.project_paths import ROOT_DIR

PROFILE_DIR = ROOT_DIR / "profile"
MASTER_PROFILE_PATH = PROFILE_DIR / "master_profile.json"
MASTER_PROFILE_EXAMPLE_PATH = PROFILE_DIR / "master_profile.example.json"


def profile_exists() -> bool:
    return MASTER_PROFILE_PATH.exists()


def load_master_profile(*, allow_example_fallback: bool = True) -> dict:
    if MASTER_PROFILE_PATH.exists():
        return _load_json(MASTER_PROFILE_PATH)
    if allow_example_fallback and MASTER_PROFILE_EXAMPLE_PATH.exists():
        return _load_json(MASTER_PROFILE_EXAMPLE_PATH)
    raise FileNotFoundError(f"Master profile not found: {MASTER_PROFILE_PATH}")


def master_profile_paths() -> dict[str, Path]:
    return {
        "profile_dir": PROFILE_DIR,
        "master_profile": MASTER_PROFILE_PATH,
        "master_profile_example": MASTER_PROFILE_EXAMPLE_PATH,
    }


def _load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Profile payload must be an object: {path}")
    return payload
