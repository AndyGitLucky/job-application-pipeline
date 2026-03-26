"""
llm_client.py
=============
Einheitlicher LLM-Client fuer OpenRouter.

Konfiguration via Umgebungsvariablen:
    setx OPENROUTER_API_KEY "sk-or-..."
    setx OPENROUTER_MODEL "anthropic/claude-haiku-4.5"
    setx OPENROUTER_MODEL_QUALITY "anthropic/claude-sonnet-4.6"

Verwendung:
    from llm_client import llm_complete

    response = llm_complete("Schreib ein Anschreiben fuer...")
"""

import logging
import os
from pathlib import Path

import requests

from env_utils import load_dotenv

log = logging.getLogger(__name__)


load_dotenv(Path(__file__))

LLM_CONFIG = {
    "provider": "openrouter",
    "openrouter": {
        "api_key": os.getenv("OPENROUTER_API_KEY", ""),
        "base_url": os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        "model": os.getenv("OPENROUTER_MODEL", "anthropic/claude-haiku-4.5"),
        "model_quality": os.getenv("OPENROUTER_MODEL_QUALITY", "anthropic/claude-sonnet-4.6"),
        "max_tokens": int(os.getenv("OPENROUTER_MAX_TOKENS", "1024")),
        "site_url": os.getenv("OPENROUTER_SITE_URL", ""),
        "app_name": os.getenv("OPENROUTER_APP_NAME", "Bewerbung"),
        "timeout": int(os.getenv("OPENROUTER_TIMEOUT", "120")),
    },
}


def _get_openrouter_config() -> dict:
    cfg = LLM_CONFIG["openrouter"]
    if not cfg["api_key"]:
        raise ValueError(
            "OPENROUTER_API_KEY nicht gesetzt. Beispiel: setx OPENROUTER_API_KEY \"sk-or-...\""
        )
    return cfg


def _extract_text(response_json: dict) -> str:
    choices = response_json.get("choices") or []
    if not choices:
        raise ValueError(f"Unerwartete OpenRouter-Antwort ohne choices: {response_json}")

    message = choices[0].get("message") or {}
    content = message.get("content", "")

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        text_parts = [
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        if text_parts:
            return "".join(text_parts).strip()

    raise ValueError(f"Antwortinhalt konnte nicht gelesen werden: {response_json}")


def llm_complete(prompt: str, quality: bool = False) -> str:
    """
    Sendet einen Prompt an OpenRouter.

    Args:
        prompt:  Der Prompt-Text
        quality: False = schnelles/guenstiges Modell
                 True  = besseres Modell

    Returns:
        Antwort als String
    """
    provider = LLM_CONFIG["provider"]
    log.debug(f"LLM-Call via {provider} (quality={quality})")
    return _call_openrouter(prompt, quality)


def _call_openrouter(prompt: str, quality: bool) -> str:
    cfg = _get_openrouter_config()
    model = cfg["model_quality"] if quality else cfg["model"]
    url = f"{cfg['base_url'].rstrip('/')}/chat/completions"

    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
        "X-Title": cfg["app_name"],
    }
    if cfg["site_url"]:
        headers["HTTP-Referer"] = cfg["site_url"]

    payload = {
        "model": model,
        "max_tokens": cfg["max_tokens"],
        "messages": [{"role": "user", "content": prompt}],
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=cfg["timeout"],
    )

    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        try:
            details = response.json()
        except ValueError:
            details = response.text[:500]
        raise RuntimeError(
            f"OpenRouter-Fehler ({response.status_code}) fuer Modell {model}: {details}"
        ) from exc

    return _extract_text(response.json())


def print_active_provider():
    provider = LLM_CONFIG["provider"]
    cfg = LLM_CONFIG[provider]
    key = cfg["api_key"]
    key_hint = f"{key[:8]}...{key[-4:]}" if len(key) > 12 else "(nicht gesetzt)"
    log.info(
        f"LLM Provider: {provider.upper()} | Modell: {cfg['model']} | "
        f"Qualitaet: {cfg['model_quality']} | Key: {key_hint}"
    )
