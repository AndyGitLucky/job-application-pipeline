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

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from source.candidate_profile import PROFILE_TEXT
from source.decision_engine import prepare_job_decision
from source.feedback_learning import feedback_delta_for_job, refresh_feedback_summary
from source.job_embedding_store import annotate_job_similarity
from source.job_buckets import classify_job
from source.llm_client import llm_complete
from source.pipeline_state_manager import (
    load_pipeline_state,
    save_pipeline_state,
    sync_jobs,
    update_job_decision,
    update_job_stage,
)
from source.project_paths import artifacts_path, resolve_runtime_path, runtime_path
from source.retrieval_context import format_retrieval_context

log = logging.getLogger(__name__)

CONFIG = {
    "input_file": str(runtime_path("jobs_raw.json")),
    "output_file": str(runtime_path("jobs_scored.json")),
    "min_score": 6,
    "request_delay": 0.5,
    "filter_degree_required": False,
    "normal_new_job_limit": 25,
    "explore_new_job_limit": 25,
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


def score_jobs(
    input_file: str | None = None,
    output_file: str | None = None,
    *,
    search_mode: str = "normal",
    normal_new_job_limit: int | None = None,
    explore_new_job_limit: int | None = None,
) -> list:
    input_path = resolve_runtime_path(input_file or CONFIG["input_file"])
    output_path = resolve_runtime_path(output_file or CONFIG["output_file"])
    mode = str(search_mode or "normal").strip().lower()
    if mode not in {"normal", "explore"}:
        mode = "normal"

    if not input_path.exists():
        log.error("Input-Datei nicht gefunden: %s", input_path)
        return []

    jobs = json.loads(input_path.read_text(encoding="utf-8"))
    feedback_summary = refresh_feedback_summary(output_path=runtime_path("feedback_summary.json"))
    preserved = _load_preserved_scores(output_path)
    for job in jobs:
        existing = preserved.get(job.get("id"))
        if existing:
            for key, value in existing.items():
                if key not in {"description", "url", "title", "company", "location", "source", "date"}:
                    job[key] = value
        _apply_pre_score_learning(job, feedback_summary, mode=mode)
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
    selected_to_score = list(to_score)
    deferred_jobs: list[dict] = []
    if mode in {"normal", "explore"}:
        mode_limit = (
            max(0, int(explore_new_job_limit or CONFIG["explore_new_job_limit"]))
            if mode == "explore"
            else max(0, int(normal_new_job_limit or CONFIG["normal_new_job_limit"]))
        )
        prioritizer = _prioritize_explore_jobs if mode == "explore" else _prioritize_normal_jobs
        prioritized_jobs = prioritizer(to_score)
        selected_to_score = prioritized_jobs[:mode_limit]
        selected_ids = {str(job.get("id") or "") for job in selected_to_score}
        deferred_jobs = [job for job in prioritized_jobs if str(job.get("id") or "") not in selected_ids]
        _attach_pre_score_selection_metadata(
            prioritized_jobs,
            selected_ids=selected_ids,
            mode=mode,
            mode_limit=mode_limit,
        )
        for job in deferred_jobs:
            job["score_status"] = f"deferred_{mode}_limit"
            job["scoring_error"] = ""
            job["recommended"] = False
            job["explore_deferred"] = mode == "explore"
            job["normal_deferred"] = mode == "normal"
        _log_pre_score_selection_report(
            prioritized_jobs,
            selected_to_score,
            deferred_jobs,
            mode=mode,
            mode_limit=mode_limit,
        )
        if deferred_jobs:
            log.info(
                "%s-Modus: %s neue Jobs werden bewertet, %s bleiben vorerst im %s-Backlog",
                mode.capitalize(),
                len(selected_to_score),
                len(deferred_jobs),
                mode,
            )
    log.info("%s Jobs werden bewertet", len(selected_to_score))

    for idx, job in enumerate(selected_to_score, start=1):
        log.info(
            "[%3d/%3d] %s @ %s",
            idx,
            len(selected_to_score),
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

    try:
        store = annotate_job_similarity(jobs, min_score=CONFIG["min_score"])
        output_path.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info(
            "Job-Semantik aktualisiert: %s gute Jobs im Store (%s)",
            store.get("count", 0),
            store.get("provider", "disabled"),
        )
    except Exception as exc:
        log.warning("Job-Semantik konnte nicht aktualisiert werden: %s", exc)

    return recommended


def _prioritize_explore_jobs(jobs: list[dict]) -> list[dict]:
    def sort_key(job: dict) -> tuple[float, int, int, float, int, int, str]:
        bucket = str(job.get("search_term_bucket") or "").strip().lower()
        origin = str(job.get("search_origin") or "").strip().lower()
        source = str(job.get("source") or "").strip().lower()
        strategy = str(job.get("search_strategy") or "").strip().lower()
        semantic_score = float(job.get("search_semantic_score") or 0.0)
        pre_score_rank = float(job.get("pre_score_rank") or 0.0)
        bucket_rank = 0 if bucket == "explore" else 1
        strategy_rank = 0 if strategy == "semantic" else 1
        origin_rank = 0 if origin in {"jobspy", "arbeitsagentur", "stepstone", "company_search"} else 1
        source_rank = 0 if source not in {"greenhouse", "lever", "recruitee"} else 1
        return (-pre_score_rank, bucket_rank, strategy_rank, -semantic_score, origin_rank, source_rank, str(job.get("title") or ""))

    return sorted(jobs, key=sort_key)


def _prioritize_normal_jobs(jobs: list[dict]) -> list[dict]:
    def sort_key(job: dict) -> tuple[float, int, int, int, int, str]:
        bucket = str(job.get("search_term_bucket") or "").strip().lower()
        origin = str(job.get("search_origin") or "").strip().lower()
        source = str(job.get("source") or "").strip().lower()
        description_length = len(str(job.get("description") or ""))
        pre_score_rank = float(job.get("pre_score_rank") or 0.0)
        bucket_rank = 0 if bucket in {"core", "primary", "direct"} else 1
        origin_rank = 0 if origin in {"company_search", "primary_source", "direct_source", "arbeitsagentur"} else 1
        source_rank = 0 if source in {"bmw", "infineon", "siemens_energy", "swm", "arbeitsagentur"} else 1
        return (-pre_score_rank, bucket_rank, origin_rank, source_rank, -description_length, str(job.get("title") or ""))

    return sorted(jobs, key=sort_key)


def _apply_feedback_learning(job: dict, feedback_summary: dict) -> None:
    delta, signals = feedback_delta_for_job(job, feedback_summary)
    base_score = float(job.get("score") or 0)
    ranking_score = round(base_score + delta, 2)
    job["feedback_delta"] = delta
    job["feedback_signals"] = signals
    job["ranking_score"] = ranking_score


def _apply_pre_score_learning(job: dict, feedback_summary: dict, *, mode: str) -> None:
    score, signals = pre_score_job(job, feedback_summary=feedback_summary, mode=mode)
    job["pre_score_rank"] = score
    job["pre_score_signals"] = signals


def _attach_pre_score_selection_metadata(
    prioritized_jobs: list[dict],
    *,
    selected_ids: set[str],
    mode: str,
    mode_limit: int,
) -> None:
    for rank, job in enumerate(prioritized_jobs, start=1):
        selected = str(job.get("id") or "") in selected_ids
        job["pre_score_selection_mode"] = mode
        job["pre_score_selection_rank"] = rank
        job["pre_score_selection_limit"] = mode_limit
        job["pre_score_selection_status"] = "selected" if selected else "deferred"
        job["pre_score_selection_reason"] = " | ".join(job.get("pre_score_signals") or [])


def _log_pre_score_selection_report(
    prioritized_jobs: list[dict],
    selected_jobs: list[dict],
    deferred_jobs: list[dict],
    *,
    mode: str,
    mode_limit: int,
) -> None:
    if not prioritized_jobs:
        return
    log.info(
        "%s pre-score selection: %s candidates ranked, top %s selected for LLM",
        mode.capitalize(),
        len(prioritized_jobs),
        min(mode_limit, len(prioritized_jobs)),
    )

    def emit(label: str, jobs: list[dict]) -> None:
        if not jobs:
            return
        log.info("  %s:", label)
        for job in jobs[:5]:
            log.info(
                "    #%s pre=%.2f | %s @ %s | %s",
                job.get("pre_score_selection_rank", "-"),
                float(job.get("pre_score_rank") or 0.0),
                _safe_log_text(job.get("title"), 55),
                _safe_log_text(job.get("company"), 28),
                _safe_log_text(" | ".join(job.get("pre_score_signals") or []), 140),
            )

    emit("Selected for scoring", selected_jobs)
    emit("Deferred by budget", deferred_jobs)


def pre_score_job(job: dict, *, feedback_summary: dict, mode: str) -> tuple[float, list[str]]:
    score = 0.0
    signals: list[str] = []

    link_quality = str(job.get("best_link_quality") or "").strip().lower()
    if link_quality == "high":
        score += 3.0
        signals.append("link:high")
    elif link_quality == "medium":
        score += 2.0
        signals.append("link:medium")
    elif link_quality == "low":
        score += 0.5
        signals.append("link:low")

    link_kind = str(job.get("best_link_kind") or "").strip().lower()
    if link_kind in {"direct_apply", "company_detail", "captcha_then_company_apply"}:
        score += 2.0
        signals.append(f"kind:{link_kind}")
    elif link_kind in {"manual_contact_gate", "secondary_apply_platform"}:
        score += 1.2
        signals.append(f"kind:{link_kind}")
    elif link_kind == "discovery_only":
        score -= 0.6
        signals.append("kind:discovery_only")

    description_quality = str(job.get("description_quality") or "").strip().lower()
    if description_quality == "high":
        score += 2.0
        signals.append("desc:high")
    elif description_quality == "medium":
        score += 1.0
        signals.append("desc:medium")

    source = str(job.get("source") or "").strip().lower()
    if source in {"bmw", "infineon", "siemens_energy", "swm", "conrad"}:
        score += 1.8
        signals.append(f"source:{source}")
    elif source == "arbeitsagentur":
        score += 1.2
        signals.append("source:arbeitsagentur")

    location = str(job.get("location") or "").strip().lower()
    if any(token in location for token in ("münchen", "muenchen", "munich")):
        score += 1.0
        signals.append("location:munich")

    bucket = str(job.get("search_term_bucket") or "").strip().lower()
    strategy = str(job.get("search_strategy") or "").strip().lower()
    semantic_score = float(job.get("search_semantic_score") or 0.0)

    if mode == "explore":
        if bucket == "explore":
            score += 1.0
            signals.append("bucket:explore")
        if strategy == "semantic":
            score += 1.2
            signals.append("strategy:semantic")
        elif strategy == "heuristic":
            score += 0.4
            signals.append("strategy:heuristic")
        score += min(1.5, semantic_score * 2.0)
        if semantic_score:
            signals.append(f"semantic:{round(semantic_score, 3)}")
    else:
        if bucket in {"core", "primary", "direct"}:
            score += 1.5
            signals.append(f"bucket:{bucket}")
        elif bucket == "explore":
            score -= 2.0
            signals.append("bucket:explore")

    feedback_delta, _ = feedback_delta_for_job(job, feedback_summary)
    if feedback_delta:
        score += feedback_delta * 0.5
        signals.append(f"feedback:{round(feedback_delta, 2)}")

    return (round(score, 2), signals)


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

    applications_dir = artifacts_path("applications")
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
