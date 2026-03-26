from __future__ import annotations

from pathlib import Path

SOURCE_DIR = Path(__file__).resolve().parent
ROOT_DIR = SOURCE_DIR.parent


def source_path(*parts: str) -> Path:
    return SOURCE_DIR.joinpath(*parts)


def resolve_source_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return source_path(*candidate.parts)
