"""
Embedding client with provider-aware configuration.
Supports OpenRouter, OpenAI, and custom OpenAI-compatible endpoints.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import requests

from source.env_utils import load_dotenv

load_dotenv(Path(__file__))


def _provider() -> str:
    return os.getenv("EMBEDDING_PROVIDER", "openrouter").strip().lower()


def _api_key(provider: str) -> str:
    return (
        os.getenv("EMBEDDING_API_KEY")
        or (os.getenv("OPENROUTER_API_KEY", "") if provider == "openrouter" else "")
        or (os.getenv("OPENAI_API_KEY", "") if provider == "openai" else "")
        or os.getenv("OPENAI_API_KEY", "")
        or os.getenv("OPENROUTER_API_KEY", "")
    )


def _base_url(provider: str) -> str:
    explicit = os.getenv("EMBEDDING_BASE_URL", "").strip()
    if explicit:
        return explicit
    if provider == "openrouter":
        return "https://openrouter.ai/api/v1"
    return "https://api.openai.com/v1"


def _model(provider: str) -> str:
    explicit = os.getenv("EMBEDDING_MODEL", "").strip()
    if explicit:
        return explicit
    if provider == "openrouter":
        return "openai/text-embedding-3-small"
    return "text-embedding-3-small"


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


EMBEDDING_CONFIG = {
    "provider": _provider(),
    "api_key": _api_key(_provider()),
    "base_url": _base_url(_provider()),
    "model": _model(_provider()),
    "timeout": int(os.getenv("EMBEDDING_TIMEOUT", "60")),
    "enabled": _bool_env("EMBEDDING_ENABLED", False),
    "site_url": os.getenv("OPENROUTER_SITE_URL", ""),
    "app_name": os.getenv("OPENROUTER_APP_NAME", "Bewerbung"),
    "max_retries": int(os.getenv("EMBEDDING_MAX_RETRIES", "2")),
}


def embeddings_enabled() -> bool:
    return bool(EMBEDDING_CONFIG["enabled"] and EMBEDDING_CONFIG["api_key"])


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not embeddings_enabled():
        raise RuntimeError("Embeddings are not enabled")

    headers = {
        "Authorization": f"Bearer {EMBEDDING_CONFIG['api_key']}",
        "Content-Type": "application/json",
    }
    if EMBEDDING_CONFIG["provider"] == "openrouter":
        headers["X-Title"] = EMBEDDING_CONFIG["app_name"]
        if EMBEDDING_CONFIG["site_url"]:
            headers["HTTP-Referer"] = EMBEDDING_CONFIG["site_url"]

    payload = {"model": EMBEDDING_CONFIG["model"], "input": texts}
    url = f"{EMBEDDING_CONFIG['base_url'].rstrip('/')}/embeddings"

    retries = max(0, EMBEDDING_CONFIG["max_retries"])
    delay = 2.0
    for attempt in range(retries + 1):
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=EMBEDDING_CONFIG["timeout"],
        )
        if response.status_code != 429 or attempt == retries:
            response.raise_for_status()
            data = response.json()["data"]
            return [item["embedding"] for item in data]
        time.sleep(delay)
        delay *= 2

    raise RuntimeError("Embedding request failed unexpectedly")
