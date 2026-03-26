"""
Explicit decision preparation for job scoring and application routing.
"""

from __future__ import annotations

import re


def prepare_job_decision(job: dict, min_score: int, apply_score_threshold: int = 8) -> dict:
    score = int(job.get("score") or 0)
    degree_required = bool(job.get("degree_required"))
    recommended = bool(job.get("recommended"))
    has_contact = bool(job.get("contact_email"))
    title = (job.get("title") or "").lower()
    description = (job.get("description") or "").lower()

    role_risk = _detect_role_risk(title, description)
    description_thin = len((job.get("description") or "").strip()) < 250

    if score < min_score or not recommended:
        decision = "reject"
        reason = "score_below_threshold"
    elif role_risk:
        decision = "review"
        reason = role_risk
    elif description_thin:
        decision = "review"
        reason = "insufficient_job_detail"
    elif degree_required and score < apply_score_threshold:
        decision = "review"
        reason = "degree_requirement_risk"
    elif score >= apply_score_threshold:
        decision = "apply"
        reason = "high_fit"
    else:
        decision = "review"
        reason = "needs_human_review"

    next_action = "generate"
    if decision == "apply" and has_contact:
        next_action = "contact_and_generate"
    elif decision == "apply":
        next_action = "generate_then_resolve_apply_path"
    elif decision == "review":
        next_action = "hold_for_review"
    else:
        next_action = "archive"

    review_status = "pending" if decision == "review" else "not_required"

    return {
        "decision": decision,
        "decision_reason": reason,
        "next_action": next_action,
        "score_band": _score_band(score),
        "review_status": review_status,
        "risk_flags": [flag for flag in [role_risk, "degree_required" if degree_required else "", "thin_description" if description_thin else ""] if flag],
    }


def _score_band(score: int) -> str:
    if score >= 9:
        return "excellent"
    if score >= 7:
        return "strong"
    if score >= 6:
        return "good"
    if score >= 4:
        return "weak"
    return "poor"


def _detect_role_risk(title: str, description: str) -> str:
    haystack = " ".join([title, description])
    patterns = {
        "seniority_risk": r"\b(staff|principal|lead research|director|vp|head of)\b",
        "research_risk": r"\b(phd|foundation model|research roadmap|research scientist)\b",
        "software_focus_risk": r"\bbackend|distributed systems|full[- ]stack|software engineer\b",
    }
    for label, pattern in patterns.items():
        if re.search(pattern, haystack):
            return label
    return ""
