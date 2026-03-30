"""
Local JSON-backed vector store for structured candidate knowledge.
"""

from __future__ import annotations

import json
import math
import re

from source.candidate_profile import knowledge_items_for
from source.embeddings_client import embed_texts, embeddings_enabled
from source.project_paths import runtime_path

STORE_PATH = runtime_path("knowledge_store.json")

CATEGORY_BOOSTS = {
    "application": {
        "profile_core": 0.16,
        "industry_domain": 0.18,
        "project": 0.12,
        "domain_preference": 0.08,
        "constraint": 0.10,
        "market_strategy": -0.20,
    },
    "market_discovery": {
        "profile_core": 0.12,
        "industry_domain": 0.10,
        "project": 0.08,
        "domain_preference": 0.08,
        "constraint": 0.08,
        "market_strategy": 0.12,
    },
}

STOPWORDS = {
    "and", "oder", "der", "die", "das", "mit", "fuer", "und", "ein", "eine",
    "the", "job", "role", "data", "machine", "learning", "engineer", "scientist",
    "senior", "junior", "company", "unternehmen", "muenchen", "munich",
}


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[A-Za-z0-9_+-]{3,}", (text or "").lower())
    return {word for word in words if word not in STOPWORDS}


def _knowledge_items() -> list[dict]:
    return knowledge_items_for("application") + knowledge_items_for("market_discovery")


def ensure_store(force_rebuild: bool = False) -> dict:
    if STORE_PATH.exists() and not force_rebuild:
        existing = json.loads(STORE_PATH.read_text(encoding="utf-8"))
        if existing.get("provider") == "embedding_api" or not embeddings_enabled():
            return existing

    items = _knowledge_items()
    store = {"provider": "disabled", "model": "", "items": []}
    if embeddings_enabled():
        vectors = embed_texts([item["text"] for item in items])
        store = {
            "provider": "embedding_api",
            "model": "configured",
            "items": [{**item, "vector": vector} for item, vector in zip(items, vectors)],
        }
    else:
        store["items"] = [{**item, "vector": []} for item in items]

    STORE_PATH.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    return store


def semantic_search(query: str, limit: int = 4, mode: str = "application") -> list[dict]:
    store = ensure_store()
    items = _filter_items(store.get("items", []), mode)
    if not items:
        return []

    query_tokens = _tokenize(query)
    if store.get("provider") == "embedding_api" and embeddings_enabled():
        try:
            query_vector = embed_texts([query])[0]
            scored = [
                _score_item(item, cosine_similarity(query_vector, item.get("vector", [])), query_tokens, mode)
                for item in items
            ]
        except Exception:
            scored = [_score_item(item, 0.0, query_tokens, mode) for item in items]
    else:
        scored = [_score_item(item, 0.0, query_tokens, mode) for item in items]

    scored.sort(key=lambda item: item["score"], reverse=True)
    results = [item for item in scored[:limit] if item["score"] > 0]
    return _ensure_mode_coverage(results, items, mode, limit)


def _filter_items(items: list[dict], mode: str) -> list[dict]:
    return [item for item in items if mode in item.get("use_cases", [])]


def _ensure_mode_coverage(results: list[dict], items: list[dict], mode: str, limit: int) -> list[dict]:
    if mode != "market_discovery":
        return results
    if any(item.get("category") == "market_strategy" for item in results):
        return results
    fallback = next((item for item in items if item.get("category") == "market_strategy"), None)
    if not fallback:
        return results
    if len(results) < limit:
        return results + [{**fallback, "score": fallback.get("priority", 0) / 100}]
    return results[:-1] + [{**fallback, "score": fallback.get("priority", 0) / 100}]


def _score_item(item: dict, semantic_score: float, query_tokens: set[str], mode: str) -> dict:
    item_tokens = _tokenize(" ".join([item.get("text", ""), " ".join(item.get("tags", []))]))
    overlap = len(query_tokens & item_tokens)
    overlap_score = min(overlap * 0.05, 0.20)
    priority_score = float(item.get("priority", 0)) / 100
    category_score = CATEGORY_BOOSTS.get(mode, {}).get(item.get("category", ""), 0.0)
    total = semantic_score + overlap_score + priority_score + category_score
    return {**item, "score": round(total, 4)}


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)
