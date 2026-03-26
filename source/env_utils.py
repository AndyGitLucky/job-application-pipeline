"""
env_utils.py
============
Kleine Hilfsfunktionen fuer .env und Umgebungsvariablen.

Ziel: gleiche .env-Ladelogik an einer Stelle (LLM + Mail + ATS).
"""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(search_from: Path | None = None) -> None:
    """Laedt einfache KEY=VALUE Eintraege aus einer .env, falls Variablen noch nicht gesetzt sind."""
    base = (search_from or Path(__file__).resolve()).resolve()
    if base.is_file():
        script_dir = base.parent
    else:
        script_dir = base

    cwd = Path.cwd().resolve()
    env_files = [
        cwd / ".env",
        cwd.parent / ".env",
        script_dir / ".env",
        script_dir.parent / ".env",
    ]

    seen: set[Path] = set()
    for env_file in env_files:
        env_file = env_file.resolve()
        if env_file in seen:
            continue
        seen.add(env_file)

        if not env_file.exists():
            continue

        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("\"'")
            if key and key not in os.environ:
                os.environ[key] = value

        # Nur die erste gefundene .env laden (wie bisher)
        return


def env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_csv(name: str) -> list[str]:
    value = os.getenv(name, "")
    return [item.strip() for item in value.split(",") if item.strip()]

