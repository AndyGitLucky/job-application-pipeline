"""
score_jobs.py
=============
Reads jobs_raw.json, scores each job via the configured LLM and writes the
enriched output to jobs_scored.json.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from candidate_profile import PROFILE_TEXT
from decision_engine import prepare_job_decision
from feedback_learning import feedback_delta_for_job, refresh_feedback_summary
from job_buckets import classify_job
from llm_client import llm_complete
from pipeline_state_manager import (
    load_pipeline_state,
    save_pipeline_state,
    sync_jobs,
    update_job_decision,
    update_job_stage,
)
from project_paths import resolve_source_path, source_path
from retrieval_context import format_retrieval_context

log = logging.getLogger(__name__)

CONFIG = {
    "input_file": str(source_path("jobs_raw.json")),
    "output_file": str(source_path("jobs_scored.json")),
    "min_score": 6,
    "request_delay": 0.5,
    "filter_degree_required": False,
}

CANDIDATE_PROFILE = PROFILE_TEXT


def _safe_log_text(value: object, limit: int | None = None) -> str:
    text = str(value or "")
    if limit is not None:
        text = text[:limit]
    return "".join(ch if ch.isprintable() or ch in {" ", "\t"} else "?" for ch in text)

SCORING_PROMPT = """Du bewertest eine Stellenanzeige fuer einen Kandidaten.

KANDIDATENPROFIL:
{profile}

RELEVANTE KONTEXT-HINWEISE:
{retrieval_context}

STELLENANZEIGE:
Titel: {title}
Unternehmen: {company}
Beschreibung:
{description}

Bewerte die Stelle auf einer Skala von 0-10 und antworte NUR mit einem JSON-Objekt.
Kein Text davor oder danach, nur JSON.

Kriterien:
- 0-3: Schlechte Passung (z.B. reines SWE, Management, klar abgelehntes Profil)
- 4-5: Schwache Passung (interessant aber problematisch, z.B. Studium Pflicht)
- 6-7: Gute Passung (passt zum Profil, Studium nicht zwingend oder vergleichbar)
- 8-9: Sehr gute Passung (Industrie/IoT/MedTech + ML + kein harter Studiumsfilter)
- 10: Perfekte Passung (Elektrotechnik-Domaene + ML + kein harter Studiumsfilter)

JSON-Format:
{{
  "score": <int 0-10>,
  "degree_required": <true/false>,
  "degree_note": "<kurze Notiz>",
  "match_reason": "<max 15 Woerter>",
  "keywords_matched": ["<keyword1>", "<keyword2>"],
  "recommended": <true/false>
}}
"""


def score_job(job: dict) -> dict:
    prompt = SCORING_PROMPT.format(
        profile=CANDIDATE_PROFILE,
        retrieval_context=format_retrieval_context(job, mode="application"),
        title=job.get("title", ""),
        company=job.get("company", ""),
        description=(job.get("description") or "")[:1500],
    )

    try:
        raw = llm_complete(prompt, quality=False)
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        result = json.loads(raw)
        result.setdefault("score", 0)
        result.setdefault("degree_required", False)
        result.setdefault("degree_note", "")
        result.setdefault("match_reason", "")
        result.setdefault("keywords_matched", [])

        passes_degree_filter = (
            not CONFIG["filter_degree_required"]
            or not result.get("degree_required", False)
        )
        result.setdefault(
            "recommended",
            result["score"] >= CONFIG["min_score"] and passes_degree_filter,
        )
        result.setdefault("score_status", "ok")
        result.setdefault("scoring_error", "")
        return result

    except json.JSONDecodeError as exc:
        log.warning("JSON error while scoring %r: %s", job.get("title", ""), exc)
        return {
            "score": 0,
            "degree_required": False,
            "degree_note": "",
            "match_reason": "",
            "keywords_matched": [],
            "recommended": False,
            "score_status": "error",
            "scoring_error": f"json_parse_error: {exc}",
        }
    except Exception as exc:
        log.warning("LLM error while scoring %r: %s", job.get("title", ""), exc)
        return {
            "score": 0,
            "degree_required": False,
            "degree_note": "",
            "match_reason": "",
            "keywords_matched": [],
            "recommended": False,
            "score_status": "error",
            "scoring_error": str(exc),
        }


def score_jobs(input_file: str | None = None, output_file: str | None = None) -> list:
    input_path = resolve_source_path(input_file or CONFIG["input_file"])
    output_path = resolve_source_path(output_file or CONFIG["output_file"])

    if not input_path.exists():
        log.error("Input-Datei nicht gefunden: %s", input_path)
        return []

    jobs = json.loads(input_path.read_text(encoding="utf-8"))
    feedback_summary = refresh_feedback_summary(output_path=source_path("feedback_summary.json"))
    preserved = _load_preserved_scores(output_path)
    for job in jobs:
        existing = preserved.get(job.get("id"))
        if existing:
            for key, value in existing.items():
                if key not in {"description", "url", "title", "company", "location", "source", "date"}:
                    job[key] = value
    log.info("Lade %s Jobs aus %s", len(jobs), input_path)

    state = load_pipeline_state()
    sync_jobs(state, jobs, stage="scoring")

    already_scored = 0
    to_score = []
    for job in jobs:
        if job.get("job_status") == "invalid":
            continue
        if job.get("score") is not None and job.get("score", 0) > 0:
            already_scored += 1
            job["recommended"] = bool(job.get("recommended")) or job.get("score", 0) >= CONFIG["min_score"]
            decision = prepare_job_decision(job, CONFIG["min_score"])
            decision["score"] = job.get("score", 0)
            decision["recommended"] = job.get("recommended", False)
            job.update(decision)
            job.update(classify_job(job))
            _apply_feedback_learning(job, feedback_summary)
            update_job_decision(state, job["id"], decision)
        else:
            to_score.append(job)

    if already_scored:
        log.info("%s Jobs bereits bewertet, werden uebernommen", already_scored)
    log.info("%s Jobs werden bewertet", len(to_score))

    for idx, job in enumerate(to_score, start=1):
        log.info(
            "[%3d/%3d] %s @ %s",
            idx,
            len(to_score),
            _safe_log_text(job["title"], 45),
            _safe_log_text(job["company"], 25),
        )
        update_job_stage(state, job["id"], "scoring", "in_progress", message="llm_scoring_started")

        scoring = score_job(job)
        job.update(scoring)
        job["recommended"] = bool(job.get("recommended")) or job.get("score", 0) >= CONFIG["min_score"]

        decision = prepare_job_decision(job, CONFIG["min_score"])
        decision["score"] = job["score"]
        decision["recommended"] = job["recommended"]
        job.update(decision)
        job.update(classify_job(job))
        _apply_feedback_learning(job, feedback_summary)

        update_job_decision(state, job["id"], decision)
        update_job_stage(
            state,
            job["id"],
            "scoring",
            "completed",
            message=job.get("match_reason", "") or job.get("score_status", "ok"),
            extras={
                "score": job["score"],
                "recommended": job["recommended"],
                "score_status": job.get("score_status", "ok"),
                "fit_status": job.get("fit_status", ""),
                "apply_path_status": job.get("apply_path_status", ""),
                "final_bucket": job.get("final_bucket", ""),
            },
        )

        status = "OK" if job["recommended"] else "NO"
        log.info(
            "      %s score=%s/10 | degree=%s | %s",
            status,
            job["score"],
            "yes" if job["degree_required"] else "no",
            job["match_reason"][:60],
        )
        time.sleep(CONFIG["request_delay"])

    output_path.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")
    save_pipeline_state(state)

    recommended = [job for job in jobs if job.get("recommended")]
    filtered = [job for job in jobs if not job.get("recommended")]
    degree_only = [job for job in jobs if job.get("degree_required")]

    log.info("Gespeichert: %s", output_path.resolve())
    log.info("Gesamt: %s | Empfohlen: %s | Ausgefiltert: %s", len(jobs), len(recommended), len(filtered))
    log.info(
        "Studium Pflicht: %s | Filter aktiv: %s",
        len(degree_only),
        CONFIG["filter_degree_required"],
    )

    for job in sorted(recommended, key=lambda item: item["score"], reverse=True)[:10]:
        log.info(
            "[%s/10] %s @ %s | %s",
            job["score"],
            job["title"][:40],
            job["company"][:25],
            job.get("final_bucket", job["decision"]),
        )

    return recommended


def _apply_feedback_learning(job: dict, feedback_summary: dict) -> None:
    delta, signals = feedback_delta_for_job(job, feedback_summary)
    base_score = float(job.get("score") or 0)
    ranking_score = round(base_score + delta, 2)
    job["feedback_delta"] = delta
    job["feedback_signals"] = signals
    job["ranking_score"] = ranking_score


def _load_preserved_scores(output_path: Path) -> dict[str, dict]:
    preserved: dict[str, dict] = {}
    if output_path.exists():
        try:
            existing_jobs = json.loads(output_path.read_text(encoding="utf-8"))
            for job in existing_jobs:
                job_id = str(job.get("id", "")).strip()
                if job_id:
                    preserved[job_id] = job
        except Exception:
            pass

    applications_dir = source_path("applications")
    if applications_dir.exists():
        for meta_path in applications_dir.glob("*/meta.json"):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            job_id = str(meta.get("job_id", "")).strip()
            if not job_id:
                continue
            preserved.setdefault(job_id, {})
            preserved[job_id].update(
                {
                    "score": meta.get("score"),
                    "application_generated": True,
                    "application_dir": str(meta_path.parent),
                    "decision": meta.get("decision"),
                    "contact_email": meta.get("contact_email", ""),
                    "contact_name": meta.get("contact_name", ""),
                    "contact_role": meta.get("contact_role", ""),
                }
            )
    return preserved


if __name__ == "__main__":
    recommended_jobs = score_jobs()
    print(f"\nOK. {len(recommended_jobs)} empfohlene Jobs in jobs_scored.json")
