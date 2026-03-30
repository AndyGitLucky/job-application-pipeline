"""
Retrieval layer for candidate evidence and context snippets.
"""

from __future__ import annotations

import re

from source.candidate_profile import PROFILE_FACTS, knowledge_items_for
from source.vector_store import semantic_search

STOPWORDS = {
    "and", "oder", "der", "die", "das", "mit", "fuer", "und", "ein", "eine",
    "the", "job", "role", "data", "machine", "learning", "engineer", "scientist",
    "manager", "senior", "junior", "muenchen", "munich", "remote", "hybrid",
    "company", "unternehmen",
}


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[A-Za-z0-9_+-]{3,}", (text or "").lower())
    return {word for word in words if word not in STOPWORDS}


def retrieve_relevant_context(
    job: dict,
    limit: int = 4,
    mode: str = "application",
    exclude_categories: set[str] | None = None,
) -> list[dict]:
    query_text = " ".join(
        [
            job.get("title", ""),
            job.get("company", ""),
            job.get("location", ""),
            job.get("description", "")[:2000],
        ]
    )
    exclude_categories = exclude_categories or set()
    semantic_results = _filter_categories(
        semantic_search(query_text, limit=max(limit * 2, limit), mode=mode),
        exclude_categories,
    )[:limit]
    if semantic_results:
        return semantic_results
    return _keyword_fallback(query_text, limit=limit, mode=mode, exclude_categories=exclude_categories)


def format_retrieval_context(
    job: dict,
    limit: int = 4,
    mode: str = "application",
    exclude_categories: set[str] | None = None,
) -> str:
    snippets = retrieve_relevant_context(job, limit=limit, mode=mode, exclude_categories=exclude_categories)
    return "\n".join(f"- [{item['category']}] {item['text']}" for item in snippets)


def _keyword_fallback(query_text: str, limit: int, mode: str, exclude_categories: set[str]) -> list[dict]:
    query_tokens = _tokenize(query_text)
    scored = []
    for item in knowledge_items_for(mode):
        if item.get("category") in exclude_categories:
            continue
        item_tokens = _tokenize(" ".join([item.get("text", ""), " ".join(item.get("tags", []))]))
        overlap = len(query_tokens & item_tokens)
        if overlap:
            scored.append((overlap + item.get("priority", 0) / 100, item))

    scored.sort(key=lambda item: item[0], reverse=True)
    items = [item for _, item in scored[:limit]]
    if mode == "market_discovery" and not any(item.get("category") == "market_strategy" for item in items):
        market_item = next(
            (
                item for item in knowledge_items_for(mode)
                if item.get("category") == "market_strategy" and item.get("category") not in exclude_categories
            ),
            None,
        )
        if market_item:
            if len(items) < limit:
                items.append(market_item)
            elif items:
                items[-1] = market_item
    if items:
        return items

    base = [item for item in knowledge_items_for(mode) if item.get("category") not in exclude_categories][:limit]
    if base:
        return base

    return [{"text": text, "category": "profile_core"} for text in PROFILE_FACTS[:limit]]


def _filter_categories(items: list[dict], exclude_categories: set[str]) -> list[dict]:
    return [item for item in items if item.get("category") not in exclude_categories]
