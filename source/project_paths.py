from __future__ import annotations

from pathlib import Path

SOURCE_DIR = Path(__file__).resolve().parent
ROOT_DIR = SOURCE_DIR.parent
RUNTIME_DIR = ROOT_DIR / "runtime"
ARTIFACTS_DIR = ROOT_DIR / "artifacts"
CONFIG_DIR = ROOT_DIR / "config"
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def source_path(*parts: str) -> Path:
    return SOURCE_DIR.joinpath(*parts)


def resolve_source_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return source_path(*candidate.parts)


def runtime_path(*parts: str) -> Path:
    return RUNTIME_DIR.joinpath(*parts)


def resolve_runtime_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return runtime_path(*candidate.parts)


def artifacts_path(*parts: str) -> Path:
    return ARTIFACTS_DIR.joinpath(*parts)


def resolve_artifacts_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return artifacts_path(*candidate.parts)


def config_path(*parts: str) -> Path:
    return CONFIG_DIR.joinpath(*parts)


def resolve_config_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return config_path(*candidate.parts)
