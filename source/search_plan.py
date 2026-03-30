from __future__ import annotations

import re

from source.profile_store import load_master_profile

DEFAULT_NORMAL_TERMS = [
    "Data Scientist",
    "ML Engineer",
    "Machine Learning Engineer",
    "Applied Data Scientist",
    "AI Engineer",
    "Data Analyst",
]

DEFAULT_EXPLORE_TERMS = [
    "AI Platform Engineer",
    "MLOps Engineer",
    "ML Systems Engineer",
    "Analytics Engineer",
    "Decision Scientist",
    "Optimization Engineer",
    "Inference Engineer",
    "Computer Vision Engineer",
]


def build_search_plan(search_mode: str = "normal") -> dict:
    mode = str(search_mode or "normal").strip().lower()
    if mode not in {"normal", "explore"}:
        mode = "normal"

    profile = load_master_profile()
    title = str((profile.get("basics") or {}).get("title") or "")
    skills = _flatten_skills(profile.get("skills") or {})
    tags = _collect_tags(profile)
    certification_topics = [str(item).strip() for item in profile.get("certifications_or_topics", []) if str(item).strip()]

    normal_terms = _unique_terms(
        [
            *_terms_from_title(title),
            *_normal_terms_from_signals(skills, tags, certification_topics),
            *DEFAULT_NORMAL_TERMS,
        ]
    )[:8]
    explore_terms = _unique_terms(
        [
            *_explore_terms_from_signals(skills, tags, certification_topics),
            *DEFAULT_EXPLORE_TERMS,
        ]
    )[:8]

    if mode == "explore":
        terms = [{"term": term, "bucket": "explore"} for term in explore_terms]
    else:
        terms = [{"term": term, "bucket": "core"} for term in normal_terms]

    return {
        "mode": mode,
        "terms": terms,
        "normal_terms": normal_terms,
        "explore_terms": explore_terms,
    }


def _flatten_skills(skills: dict) -> list[str]:
    values: list[str] = []
    for items in skills.values():
        if isinstance(items, list):
            values.extend(str(item).strip() for item in items if str(item).strip())
    return values


def _collect_tags(profile: dict) -> list[str]:
    tags: list[str] = []
    for section in ("experience", "projects"):
        for item in profile.get(section, []) or []:
            tags.extend(str(tag).strip() for tag in item.get("tags", []) if str(tag).strip())
            tags.extend(str(tag).strip() for tag in item.get("tech", []) if str(tag).strip())
    return tags


def _terms_from_title(title: str) -> list[str]:
    lowered = (title or "").lower()
    terms = []
    if "ml" in lowered or "machine learning" in lowered:
        terms.extend(["ML Engineer", "Machine Learning Engineer"])
    if "ai" in lowered:
        terms.extend(["AI Engineer", "Applied AI Engineer"])
    if "data" in lowered:
        terms.extend(["Data Scientist", "Applied Data Scientist"])
    return terms


def _normal_terms_from_signals(skills: list[str], tags: list[str], topics: list[str]) -> list[str]:
    haystack = _signal_text(skills, tags, topics)
    terms = []
    if _has_any(haystack, ["deep learning", "machine learning", "tensorflow"]):
        terms.extend(["ML Engineer", "Machine Learning Engineer"])
    if _has_any(haystack, ["data engineering", "etl", "sql", "pandas"]):
        terms.extend(["Applied Data Scientist", "Data Analyst"])
    if _has_any(haystack, ["computer vision", "opencv", "cnn"]):
        terms.append("Computer Vision Engineer")
    return terms


def _explore_terms_from_signals(skills: list[str], tags: list[str], topics: list[str]) -> list[str]:
    haystack = _signal_text(skills, tags, topics)
    terms = []
    if _has_any(haystack, ["data engineering", "etl", "sql", "pipeline"]):
        terms.extend(["Analytics Engineer", "Data Engineer"])
    if _has_any(haystack, ["gpu", "cuda", "deployment", "onnx", "inference"]):
        terms.extend(["ML Systems Engineer", "Inference Engineer"])
    if _has_any(haystack, ["computer vision", "opencv", "cnn"]):
        terms.extend(["Computer Vision Engineer", "AI Solutions Engineer"])
    if _has_any(haystack, ["hardware", "electronics", "manufacturing", "root cause", "testing"]):
        terms.extend(["Industrial AI Engineer", "Optimization Engineer"])
    if _has_any(haystack, ["statistics", "analytics", "measurement", "quality"]):
        terms.extend(["Decision Scientist", "Analytics Engineer"])
    return terms


def _signal_text(*parts: list[str]) -> str:
    return " ".join(" ".join(group).lower() for group in parts)


def _has_any(haystack: str, needles: list[str]) -> bool:
    return any(needle in haystack for needle in needles)


def _unique_terms(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for term in terms:
        cleaned = re.sub(r"\s+", " ", str(term or "").strip())
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        unique.append(cleaned)
    return unique
