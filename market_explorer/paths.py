from __future__ import annotations

from pathlib import Path


MARKET_EXPLORER_DIR = Path(__file__).resolve().parent
ROOT_DIR = MARKET_EXPLORER_DIR.parent
DATA_DIR = MARKET_EXPLORER_DIR / "data"
EXPORTS_DIR = MARKET_EXPLORER_DIR / "exports"
NOTES_DIR = MARKET_EXPLORER_DIR / "notes"
APP_DIR = MARKET_EXPLORER_DIR / "app"
PIPELINE_DIR = MARKET_EXPLORER_DIR / "pipeline"
CONFIG_DIR = ROOT_DIR / "config"
RUNTIME_DIR = ROOT_DIR / "runtime"

for directory in (DATA_DIR, EXPORTS_DIR, NOTES_DIR, APP_DIR, PIPELINE_DIR, CONFIG_DIR):
    directory.mkdir(parents=True, exist_ok=True)


def data_path(*parts: str) -> Path:
    return DATA_DIR.joinpath(*parts)


def exports_path(*parts: str) -> Path:
    return EXPORTS_DIR.joinpath(*parts)


def runtime_path(*parts: str) -> Path:
    return RUNTIME_DIR.joinpath(*parts)


def config_path(*parts: str) -> Path:
    return CONFIG_DIR.joinpath(*parts)
