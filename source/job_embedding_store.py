"""
Semantic job store for good-enough jobs.

First step only:
- embed or lexically represent promising jobs
- persist them in runtime/job_embedding_store.json
- attach similarity hints to jobs without auto-merging
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from source.embeddings_client import embed_texts, embeddings_enabled
from source.project_paths import runtime_path
from source.vector_store import cosine_similarity

STORE_PATH = runtime_path("job_embedding_store.json")
DUPLICATE_HINT_THRESHOLD = 0.68

STOPWORDS = {
    "and",
    "oder",
    "der",
    "die",
    "das",
    "mit",
    "fuer",
    "und",
    "ein",
    "eine",
    "the",
    "job",
    "role",
    "company",
    "unternehmen",
    "muenchen",
    "munich",
    "gmbh",
    "ag",
    "mbh",
    "senior",
    "junior",
}


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[A-Za-z0-9_+-]{3,}", (text or "").lower())
    return {word for word in words if word not in STOPWORDS}


def build_job_embedding_text(job: dict) -> str:
    parts = [
        f"title: {job.get('title', '')}",
        f"company: {job.get('company', '')}",
        f"location: {job.get('location', '')}",
        f"source: {job.get('source', '')}",
        f"link_kind: {job.get('best_link_kind', '')}",
        f"description: {(job.get('description') or '')[:1200]}",
    ]
    return "\n".join(part for part in parts if part.strip())


def _is_good_enough(job: dict, min_score: int = 6) -> bool:
    score = int(job.get("score") or 0)
    bucket = str(job.get("final_bucket") or "").strip().lower()
    return (
        score >= min_score
        or bucket in {"needs_review", "manual_apply_ready", "autoapply_ready"}
        or bool(job.get("recommended"))
    )


def _jaccard_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def _base_hint_fields(job: dict) -> dict:
    return {
        "job_id": job.get("id", ""),
        "title": job.get("title", ""),
        "company": job.get("company", ""),
        "location": job.get("location", ""),
        "source": job.get("source", ""),
        "final_bucket": job.get("final_bucket", ""),
    }


def rebuild_job_embedding_store(jobs: list[dict], *, min_score: int = 6) -> dict:
    candidates = [job for job in jobs if _is_good_enough(job, min_score=min_score)]
    items = []
    for job in candidates:
        text = build_job_embedding_text(job)
        items.append(
            {
                **_base_hint_fields(job),
                "text": text,
                "tokens": sorted(_tokenize(text)),
                "vector": [],
            }
        )

    provider = "disabled"
    if items and embeddings_enabled():
        try:
            vectors = embed_texts([item["text"] for item in items])
            for item, vector in zip(items, vectors):
                item["vector"] = vector
            provider = "embedding_api"
        except Exception:
            provider = "disabled"

    store = {
        "provider": provider,
        "count": len(items),
        "items": items,
    }
    STORE_PATH.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    return store


def load_job_embedding_store() -> dict:
    if not STORE_PATH.exists():
        return {"provider": "disabled", "count": 0, "items": []}
    try:
        return json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"provider": "disabled", "count": 0, "items": []}


def annotate_job_similarity(
    jobs: list[dict],
    *,
    min_score: int = 6,
    top_k: int = 3,
    min_similarity: float = 0.42,
) -> dict:
    store = rebuild_job_embedding_store(jobs, min_score=min_score)
    items = store.get("items", [])
    item_by_id = {item.get("job_id"): item for item in items}
    provider = store.get("provider", "disabled")

    for job in jobs:
        job["similar_job_hints"] = []
        job["possible_duplicate_of"] = ""
        job["possible_duplicate_score"] = 0.0

        item = item_by_id.get(job.get("id"))
        if not item:
            continue

        hints = []
        for other in items:
            if other.get("job_id") == item.get("job_id"):
                continue
            if provider == "embedding_api":
                similarity = cosine_similarity(item.get("vector", []), other.get("vector", []))
            else:
                similarity = _jaccard_similarity(set(item.get("tokens", [])), set(other.get("tokens", [])))
            if similarity < min_similarity:
                continue
            hints.append(
                {
                    "job_id": other.get("job_id", ""),
                    "title": other.get("title", ""),
                    "company": other.get("company", ""),
                    "source": other.get("source", ""),
                    "similarity": round(float(similarity), 4),
                }
            )

        hints.sort(key=lambda item: item["similarity"], reverse=True)
        job["similar_job_hints"] = hints[:top_k]

        duplicate_hint = next(
            (
                hint
                for hint in hints
                if hint.get("company") == job.get("company")
                and hint.get("similarity", 0.0) >= DUPLICATE_HINT_THRESHOLD
            ),
            None,
        )
        if duplicate_hint:
            job["possible_duplicate_of"] = duplicate_hint["job_id"]
            job["possible_duplicate_score"] = duplicate_hint["similarity"]

    return store
