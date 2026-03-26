from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from feedback_store import load_feedback
from project_paths import source_path


DEFAULT_FEEDBACK_SUMMARY = source_path("feedback_summary.json")
DEFAULT_SCORED_JOBS = source_path("jobs_scored.json")


def normalize_feedback_reason(note: str) -> str:
    text = " ".join(str(note or "").lower().split())
    if not text:
        return "unspecified"

    patterns = (
        ("zu_research_lastig", (r"\bresearch\b", r"\bforschung\b", r"\bphd\b", r"\badas\b", r"\bautonomous\b")),
        ("zu_senior", (r"\bzu senior\b", r"\bsenior\b", r"\blead\b", r"\bprincipal\b", r"\bstaff\b", r"\bhead\b")),
        ("falsche_spezialisierung", (r"\bfalsche richtung\b", r"\bspezialisierung\b", r"\barchitect\b", r"\bconsult", r"\bmanager\b")),
        ("studium_hart_erforderlich", (r"\bmaster\b", r"\bstudium\b", r"\bdegree\b", r"\babschluss\b")),
        ("zu_viel_consulting", (r"\bconsult", r"\bberatung\b", r"\bkund", r"\bclient facing\b")),
        ("zu_wenig_infos", (r"\bzu wenig info", r"\bdünn\b", r"\bduenn\b", r"\bthin\b", r"\bunclar\b")),
        ("link_kaputt", (r"\blink kaputt\b", r"\bbroken\b", r"\bunreach", r"\b404\b", r"\bprotocol\b")),
        ("falscher_ort", (r"\bstandort\b", r"\bort\b", r"\bremote\b", r"\bumzug\b")),
    )
    for label, exprs in patterns:
        if any(re.search(expr, text) for expr in exprs):
            return label
    return "other"


def refresh_feedback_summary(
    jobs_path: str | Path = DEFAULT_SCORED_JOBS,
    *,
    feedback_path: str | Path = source_path("feedback_log.json"),
    output_path: str | Path = DEFAULT_FEEDBACK_SUMMARY,
) -> dict:
    jobs = _load_jobs(jobs_path)
    feedback = load_feedback(feedback_path)
    by_job = {str(job.get("id") or ""): job for job in jobs if job.get("id")}

    summary = {
        "totals": Counter(),
        "reasons": Counter(),
        "by_source": defaultdict(Counter),
        "by_link_kind": defaultdict(Counter),
    }

    for job_id, entries in feedback.items():
        job = by_job.get(str(job_id), {})
        source = str(job.get("source") or _best_effort_field(entries, "source") or "unknown")
        link_kind = str(job.get("best_link_kind") or _best_effort_field(entries, "best_link_kind") or "unknown")
        for entry in entries:
            value = str(entry.get("value") or "")
            note = str(entry.get("note") or "")
            reason = normalize_feedback_reason(note)
            summary["totals"][value] += 1
            summary["reasons"][reason] += 1
            summary["by_source"][source][value] += 1
            summary["by_link_kind"][link_kind][value] += 1

    result = {
        "totals": dict(summary["totals"]),
        "reasons": dict(summary["reasons"]),
        "by_source": {key: dict(value) for key, value in summary["by_source"].items()},
        "by_link_kind": {key: dict(value) for key, value in summary["by_link_kind"].items()},
    }
    Path(output_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def load_feedback_summary(path: str | Path = DEFAULT_FEEDBACK_SUMMARY) -> dict:
    target = Path(path)
    if target.exists():
        try:
            return json.loads(target.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def feedback_delta_for_job(job: dict, summary: dict | None) -> tuple[float, list[str]]:
    if not summary:
        return 0.0, []

    delta = 0.0
    signals: list[str] = []
    source = str(job.get("source") or "unknown")
    kind = str(job.get("best_link_kind") or "unknown")
    title = str(job.get("title") or "").lower()
    description = str(job.get("description") or "").lower()
    haystack = f"{title} {description}"

    delta, signals = _apply_summary_bias(delta, signals, summary.get("by_source", {}).get(source, {}), f"source:{source}")
    delta, signals = _apply_summary_bias(delta, signals, summary.get("by_link_kind", {}).get(kind, {}), f"kind:{kind}")

    reasons = summary.get("reasons", {})
    if _matches_seniority_risk(haystack):
        delta -= min(1.0, 0.2 * int(reasons.get("zu_senior", 0)))
        if int(reasons.get("zu_senior", 0)) > 0:
            signals.append("reason:zu_senior")
    if _matches_research_risk(haystack):
        delta -= min(1.0, 0.2 * int(reasons.get("zu_research_lastig", 0)))
        if int(reasons.get("zu_research_lastig", 0)) > 0:
            signals.append("reason:zu_research_lastig")
    if _matches_specialization_risk(haystack):
        delta -= min(0.8, 0.2 * int(reasons.get("falsche_spezialisierung", 0)))
        if int(reasons.get("falsche_spezialisierung", 0)) > 0:
            signals.append("reason:falsche_spezialisierung")
    if _matches_degree_risk(haystack):
        delta -= min(0.8, 0.2 * int(reasons.get("studium_hart_erforderlich", 0)))
        if int(reasons.get("studium_hart_erforderlich", 0)) > 0:
            signals.append("reason:studium_hart_erforderlich")

    delta = max(-2.0, min(1.5, delta))
    return round(delta, 2), sorted(set(signals))


def _apply_summary_bias(delta: float, signals: list[str], counts: dict, label: str) -> tuple[float, list[str]]:
    rejects = int(counts.get("reject", 0))
    deads = int(counts.get("dead-listing", 0))
    applies = int(counts.get("sent", 0))
    approvals = int(counts.get("verify-ready", 0))

    if rejects or deads:
        penalty = min(1.2, rejects * 0.15 + deads * 0.3)
        delta -= penalty
        signals.append(label)
    if applies or approvals:
        bonus = min(0.9, applies * 0.2 + approvals * 0.15)
        delta += bonus
        signals.append(label)
    return delta, signals


def _load_jobs(path: str | Path) -> list[dict]:
    target = Path(path)
    if not target.exists():
        return []
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return []
    return data if isinstance(data, list) else []


def _best_effort_field(entries: list[dict], field: str) -> str:
    for entry in reversed(entries):
        value = str(entry.get(field) or "").strip()
        if value:
            return value
    return ""


def _matches_seniority_risk(text: str) -> bool:
    return bool(re.search(r"\b(senior|lead|principal|staff|head)\b", text))


def _matches_research_risk(text: str) -> bool:
    return bool(re.search(r"\b(research|phd|adas|autonomous|perception|foundation model)\b", text))


def _matches_specialization_risk(text: str) -> bool:
    return bool(re.search(r"\b(architect|consultant|manager|sales|account manager|business analyst)\b", text))


def _matches_degree_risk(text: str) -> bool:
    return bool(re.search(r"\b(master|phd|degree required|doctoral)\b", text))
