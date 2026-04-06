from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from market_explorer.paths import data_path as market_data_path
from source.candidate_profile import knowledge_items_for
from source.embeddings_client import embed_texts, embeddings_enabled
from source.profile_store import load_master_profile
from source.role_library import build_profile_semantic_text, rank_roles_for_profile
from source.search_plan import build_search_plan
from source.vector_store import cosine_similarity

log = logging.getLogger(__name__)

DEFAULT_MARKET_POOL_PATH = market_data_path("market_jobs.json")

TECH_CORE_ROLE_CLUSTERS = {
    "Data and AI",
    "Software and IT",
    "Engineering and Industrial",
}

TECH_ADJACENT_ROLE_CLUSTERS = {
    "Manufacturing and Production",
    "Skilled Trades and Construction",
    "Finance and Office",
}

BLOCKED_ROLE_CLUSTERS = {
    "Hospitality and Gastronomy",
    "Retail and Sales",
    "Healthcare and Nursing",
    "Education and Social Work",
    "Logistics and Transport",
}

PREFERRED_INDUSTRIES = {
    "Technology",
    "Manufacturing and Industrial",
    "Healthcare",
    "Mobility and Transport Infrastructure",
    "Professional Services",
}

BLOCKED_INDUSTRIES = {
    "Hospitality",
    "Retail and Consumer",
}

STRONG_TECH_KEYWORDS = [
    "python",
    "sql",
    "machine learning",
    "data engineer",
    "data scientist",
    "analytics",
    "ai",
    "computer vision",
    "tensorflow",
    "pytorch",
    "onnx",
    "cuda",
    "etl",
    "pipeline",
    "mlops",
    "software",
    "developer",
    "devops",
    "automation",
    "embedded",
    "firmware",
    "sps",
    "messtechnik",
    "measurement",
    "quality",
    "test engineer",
    "validation",
]

MARKET_POOL_STOPWORDS = {
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
    "stellenanzeige",
    "muenchen",
    "munich",
    "berlin",
    "hamburg",
    "dresden",
    "koeln",
    "germany",
    "deutschland",
}


@dataclass(frozen=True)
class MarketPoolModeConfig:
    selection_limit: int
    candidate_limit_for_embeddings: int
    gate_threshold: float
    allow_adjacent_roles: bool


MODE_CONFIG = {
    "normal": MarketPoolModeConfig(
        selection_limit=220,
        candidate_limit_for_embeddings=260,
        gate_threshold=2.8,
        allow_adjacent_roles=False,
    ),
    "explore": MarketPoolModeConfig(
        selection_limit=320,
        candidate_limit_for_embeddings=380,
        gate_threshold=1.8,
        allow_adjacent_roles=True,
    ),
}


class MarketPoolSelectionError(RuntimeError):
    pass


def select_market_pool_jobs(
    *,
    search_mode: str = "normal",
    pool_path: str | Path | None = None,
    locality_mode: str = "munich_only",
) -> list[dict]:
    mode = str(search_mode or "normal").strip().lower()
    if mode not in MODE_CONFIG:
        mode = "normal"
    config = MODE_CONFIG[mode]
    selected_locality_mode = _normalize_locality_mode(locality_mode)
    market_jobs = _load_market_pool_jobs(pool_path or DEFAULT_MARKET_POOL_PATH)
    profile = load_master_profile()
    search_plan = build_search_plan(mode)
    target_terms = _target_terms_from_plan(search_plan)
    role_scores = {item["term"]: float(item.get("score") or 0.0) for item in search_plan.get("semantic_roles", [])}
    profile_query = _build_market_profile_query(profile=profile, target_terms=target_terms)
    profile_tokens = _tokenize(profile_query)

    candidates: list[dict] = []
    rejected_count = 0
    for job in market_jobs:
        if _skip_market_job(job):
            rejected_count += 1
            continue
        stage = _score_market_job_stage_one(
            job,
            profile_tokens=profile_tokens,
            target_terms=target_terms,
            role_scores=role_scores,
            mode=mode,
            allow_adjacent_roles=config.allow_adjacent_roles,
            locality_mode=selected_locality_mode,
        )
        if stage["gate_score"] < config.gate_threshold:
            rejected_count += 1
            continue
        enriched = dict(job)
        enriched.update(
            {
                "market_pool_stage_score": stage["stage_score"],
                "market_pool_gate_score": stage["gate_score"],
                "market_pool_lexical_score": stage["lexical_score"],
                "market_pool_role_score": stage["role_score"],
                "market_pool_domain_score": stage["domain_score"],
                "market_pool_signals": stage["signals"],
            }
        )
        candidates.append(enriched)

    candidates.sort(
        key=lambda job: (
            -float(job.get("market_pool_stage_score") or 0.0),
            -float(job.get("market_score") or 0.0),
            str(job.get("title_clean") or job.get("title") or ""),
        )
    )
    embed_cap = min(config.candidate_limit_for_embeddings, len(candidates))
    _apply_semantic_ranking(candidates[:embed_cap], profile_query=profile_query)
    _apply_market_pool_final_rank(
        candidates,
        target_terms=target_terms,
        mode=mode,
    )
    selected = candidates[: config.selection_limit]

    prepared = [_prepare_job_for_main(job, rank=index + 1, mode=mode) for index, job in enumerate(selected)]
    _log_selection_summary(
        prepared,
        rejected_count=rejected_count,
        source_path=Path(pool_path or DEFAULT_MARKET_POOL_PATH),
        mode=mode,
        locality_mode=selected_locality_mode,
    )
    return prepared


def _load_market_pool_jobs(path: str | Path) -> list[dict]:
    target = Path(path)
    if not target.exists():
        raise MarketPoolSelectionError(
            f"Market pool not found: {target}. Run market_explorer first to build market_jobs.json."
        )
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise MarketPoolSelectionError(f"Market pool payload must be a list of jobs: {target}")
    jobs = [item for item in payload if isinstance(item, dict)]
    if not jobs:
        raise MarketPoolSelectionError(f"Market pool is empty: {target}")
    return jobs


def _skip_market_job(job: dict) -> bool:
    if bool(job.get("exclude_from_market_view")):
        return True
    if str(job.get("job_status") or "").strip().lower() == "invalid":
        return True
    if str(job.get("final_bucket") or "").strip().lower() in {"rejected", "dead_listing"}:
        return True
    title = str(job.get("title_clean") or job.get("title") or "").strip().lower()
    return not title


def _build_market_profile_query(*, profile: dict, target_terms: list[str]) -> str:
    knowledge = [
        str(item.get("text") or "").strip()
        for item in knowledge_items_for("market_discovery")
        if str(item.get("text") or "").strip()
    ]
    profile_text = build_profile_semantic_text(profile)
    parts = [
        profile_text,
        "Target roles: " + ", ".join(target_terms[:8]),
        "Market discovery context: " + " ".join(knowledge[:6]),
    ]
    return "\n".join(part for part in parts if part.strip())


def _target_terms_from_plan(search_plan: dict) -> list[str]:
    terms = []
    for item in search_plan.get("terms", []):
        term = str(item.get("term") or "").strip()
        if term:
            terms.append(term)
    if not terms:
        profile = load_master_profile()
        terms = [item["term"] for item in rank_roles_for_profile(profile, top_k=8)]
    seen: set[str] = set()
    unique: list[str] = []
    for term in terms:
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(term)
    return unique


def _score_market_job_stage_one(
    job: dict,
    *,
    profile_tokens: set[str],
    target_terms: list[str],
    role_scores: dict[str, float],
    mode: str,
    allow_adjacent_roles: bool,
    locality_mode: str,
) -> dict:
    title = str(job.get("title_clean") or job.get("title") or "")
    description = str(job.get("description") or "")
    role_cluster = str(job.get("role_cluster") or "Other")
    industry = str(job.get("industry") or "Other")
    region = str(job.get("region") or "")
    remote_mode = str(job.get("remote_mode") or "")
    skills = [str(skill).strip() for skill in job.get("skills", []) if str(skill).strip()]
    haystack = _market_job_text(job).lower()
    tokens = _tokenize(haystack)

    score = 0.0
    gate_score = 0.0
    signals: list[str] = []

    role_score = 0.0
    if role_cluster in TECH_CORE_ROLE_CLUSTERS:
        role_score += 4.6
        gate_score += 4.6
        signals.append(f"role:{role_cluster}")
    elif role_cluster in TECH_ADJACENT_ROLE_CLUSTERS and allow_adjacent_roles:
        role_score += 2.4
        gate_score += 2.4
        signals.append(f"role:adjacent:{role_cluster}")
    elif role_cluster in BLOCKED_ROLE_CLUSTERS:
        role_score -= 4.0
        gate_score -= 4.0
        signals.append(f"role:block:{role_cluster}")

    tech_keyword_hits = [keyword for keyword in STRONG_TECH_KEYWORDS if keyword in haystack]
    if tech_keyword_hits:
        tech_bonus = min(4.0, 1.2 + len(tech_keyword_hits) * 0.45)
        score += tech_bonus
        gate_score += tech_bonus
        signals.append(f"tech:{', '.join(tech_keyword_hits[:4])}")

    lexical_overlap = len(profile_tokens & tokens)
    lexical_score = min(2.6, lexical_overlap * 0.22)
    if lexical_score:
        score += lexical_score
        gate_score += min(1.8, lexical_score)
        signals.append(f"lexical:{lexical_overlap}")

    title_role_score = 0.0
    title_lower = title.lower()
    for term in target_terms:
        if term.lower() in title_lower:
            title_role_score = max(title_role_score, 1.8)
            signals.append(f"target:{term}")
            break
    if not title_role_score:
        for term, term_score in role_scores.items():
            normalized = term.lower()
            if normalized in haystack:
                title_role_score = max(title_role_score, min(1.6, 0.8 + term_score))
    if title_role_score:
        score += title_role_score
        gate_score += title_role_score

    domain_score = 0.0
    if industry in PREFERRED_INDUSTRIES:
        domain_score += 1.0
        signals.append(f"industry:{industry}")
    elif industry in BLOCKED_INDUSTRIES:
        domain_score -= 1.2
        signals.append(f"industry:block:{industry}")

    if region == "Munich Region":
        domain_score += 0.8
        signals.append("region:munich")
    elif locality_mode == "munich_only":
        domain_score -= 3.4
        gate_score -= 4.2
        signals.append(f"region:block:{region or 'Unknown'}")
    elif locality_mode == "prefer_munich":
        domain_score -= 1.1
        gate_score -= 0.9
        signals.append(f"region:deprioritize:{region or 'Unknown'}")
    elif region in {"Berlin", "Hamburg", "Dresden Region", "Cologne Region"} and mode == "explore":
        domain_score += 0.25

    if remote_mode in {"Remote", "Hybrid"}:
        domain_score += 0.45
        signals.append(f"remote:{remote_mode.lower()}")

    if skills:
        skill_bonus = min(1.4, len(skills) * 0.28)
        domain_score += skill_bonus
        signals.append(f"skills:{', '.join(skills[:4])}")

    score += role_score + domain_score
    if role_cluster in BLOCKED_ROLE_CLUSTERS and not tech_keyword_hits:
        gate_score = min(gate_score, -1.0)

    return {
        "stage_score": round(score, 4),
        "gate_score": round(gate_score, 4),
        "lexical_score": round(lexical_score, 4),
        "role_score": round(role_score, 4),
        "domain_score": round(domain_score, 4),
        "signals": signals[:8],
    }


def _market_job_text(job: dict) -> str:
    parts = [
        str(job.get("title_clean") or job.get("title") or ""),
        str(job.get("company_clean") or job.get("company") or ""),
        str(job.get("role_cluster") or ""),
        str(job.get("industry") or ""),
        str(job.get("region") or ""),
        str(job.get("remote_mode") or ""),
        ", ".join(str(skill) for skill in job.get("skills", []) if str(skill).strip()),
        str(job.get("description") or "")[:1800],
    ]
    return "\n".join(part for part in parts if part.strip())


def _apply_semantic_ranking(candidates: list[dict], *, profile_query: str) -> None:
    if not candidates:
        return
    if not embeddings_enabled():
        for candidate in candidates:
            candidate["market_pool_semantic_score"] = 0.0
        return

    texts = [_market_job_text(job) for job in candidates]
    try:
        query_vector = embed_texts([profile_query])[0]
    except Exception as exc:
        log.warning("Market pool semantic query embedding failed: %s", exc)
        for candidate in candidates:
            candidate["market_pool_semantic_score"] = 0.0
        return

    vectors: list[list[float]] = []
    batch_size = 48
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        try:
            vectors.extend(embed_texts(batch))
        except Exception as exc:
            log.warning("Market pool job embeddings failed for batch %s-%s: %s", start, start + len(batch), exc)
            vectors.extend([[] for _ in batch])
    for candidate, vector in zip(candidates, vectors):
        candidate["market_pool_semantic_score"] = round(cosine_similarity(query_vector, vector), 4)


def _apply_market_pool_final_rank(candidates: list[dict], *, target_terms: list[str], mode: str) -> None:
    for job in candidates:
        stage_score = float(job.get("market_pool_stage_score") or 0.0)
        semantic_score = float(job.get("market_pool_semantic_score") or 0.0)
        market_score = float(job.get("market_score") or 0.0)
        final_score = stage_score + (semantic_score * 4.0) + min(1.8, market_score * 0.12)
        if mode == "normal" and str(job.get("role_cluster") or "") in TECH_CORE_ROLE_CLUSTERS:
            final_score += 0.6
        if any(term.lower() in str(job.get("title_clean") or job.get("title") or "").lower() for term in target_terms[:4]):
            final_score += 0.5
        job["market_pool_selector_score"] = round(final_score, 4)

    candidates.sort(
        key=lambda job: (
            -float(job.get("market_pool_selector_score") or 0.0),
            -float(job.get("market_pool_semantic_score") or 0.0),
            -float(job.get("market_pool_stage_score") or 0.0),
            str(job.get("title_clean") or job.get("title") or ""),
        )
    )


def _prepare_job_for_main(job: dict, *, rank: int, mode: str) -> dict:
    enriched = dict(job)
    selector_signals = list(job.get("market_pool_signals") or [])
    enriched.update(
        {
            "search_mode": mode,
            "search_term": "",
            "search_term_bucket": "market_pool",
            "search_origin": "market_pool",
            "search_strategy": "semantic_market_pool",
            "search_semantic_score": round(float(job.get("market_pool_semantic_score") or 0.0), 4),
            "pre_score_rank": round(float(job.get("market_pool_selector_score") or 0.0), 4),
            "market_pool_rank": rank,
            "market_pool_mode": mode,
            "market_pool_selector_score": round(float(job.get("market_pool_selector_score") or 0.0), 4),
            "market_pool_stage_score": round(float(job.get("market_pool_stage_score") or 0.0), 4),
            "market_pool_gate_score": round(float(job.get("market_pool_gate_score") or 0.0), 4),
            "market_pool_semantic_score": round(float(job.get("market_pool_semantic_score") or 0.0), 4),
            "market_pool_signals": selector_signals,
            "market_role_cluster": str(job.get("role_cluster") or ""),
            "market_industry": str(job.get("industry") or ""),
            "market_source_display": str(job.get("source_display") or job.get("source") or ""),
        }
    )
    return enriched


def _log_selection_summary(
    selected: list[dict],
    *,
    rejected_count: int,
    source_path: Path,
    mode: str,
    locality_mode: str,
) -> None:
    role_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    for job in selected:
        role = str(job.get("market_role_cluster") or "Other")
        source = str(job.get("market_source_display") or job.get("source") or "Unknown")
        role_counts[role] = role_counts.get(role, 0) + 1
        source_counts[source] = source_counts.get(source, 0) + 1

    top_roles = ", ".join(f"{label}={count}" for label, count in sorted(role_counts.items(), key=lambda item: (-item[1], item[0]))[:6])
    top_sources = ", ".join(f"{label}={count}" for label, count in sorted(source_counts.items(), key=lambda item: (-item[1], item[0]))[:6])
    log.info(
        "Market pool intake (%s, %s): %s Jobs ausgewaehlt aus %s | verworfen=%s",
        mode,
        locality_mode,
        len(selected),
        source_path,
        rejected_count,
    )
    if top_roles:
        log.info("Market pool Rollenmix: %s", top_roles)
    if top_sources:
        log.info("Market pool Quellenmix: %s", top_sources)


def _normalize_locality_mode(value: str) -> str:
    mode = str(value or "munich_only").strip().lower() or "munich_only"
    if mode not in {"munich_only", "prefer_munich", "all"}:
        return "munich_only"
    return mode


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[A-Za-z0-9_+-]{3,}", str(text or "").lower())
    return {word for word in words if word not in MARKET_POOL_STOPWORDS}
