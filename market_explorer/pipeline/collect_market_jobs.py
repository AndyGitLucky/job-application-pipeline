from __future__ import annotations

import json
import logging
import shutil
import time
from pathlib import Path

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from market_explorer.connectors.ba_connector import fetch_ba_jobs_with_meta
from market_explorer.connectors.greenhouse_connector import fetch_greenhouse_board
from market_explorer.connectors.jobposting_extractor import fetch_jobposting_url
from market_explorer.connectors.lever_connector import fetch_lever_site
from market_explorer.paths import config_path, data_path
from source.find_jobs import deduplicate, fetch_stepstone, validate_jobs
from source.link_extractor import annotate_job_links

log = logging.getLogger(__name__)


DEFAULT_OUTPUT = data_path("market_jobs_collected.json")
DEFAULT_PRIMARY_SOURCES_CONFIG = config_path("market_primary_sources.json")

GERMANY_CITIES = [
    "Berlin",
    "Hamburg",
    "Muenchen",
    "Koeln",
    "Frankfurt am Main",
    "Stuttgart",
    "Dresden",
    "Leipzig",
    "Hannover",
    "Nuernberg",
]

MARKET_QUERY_BUCKETS = [
    {"bucket": "hospitality", "terms": ["Koch", "Kuechenhilfe", "Servicekraft", "Hotelfachkraft"]},
    {"bucket": "retail_sales", "terms": ["Verkaeufer", "Einzelhandelskaufmann", "Kundenberater", "Vertriebsmitarbeiter"]},
    {"bucket": "healthcare", "terms": ["Pflegefachkraft", "Altenpfleger", "Gesundheits und Krankenpfleger", "Medizinische Fachangestellte"]},
    {"bucket": "education_social", "terms": ["Erzieher", "Sozialpaedagoge", "Kinderpfleger", "Heilerziehungspfleger"]},
    {"bucket": "trades_field", "terms": ["Elektriker", "Elektroniker", "Servicetechniker", "Anlagenmechaniker"]},
    {"bucket": "manufacturing", "terms": ["Mechatroniker", "Industriemechaniker", "Produktionsmitarbeiter", "Zerspanungsmechaniker"]},
    {"bucket": "logistics_transport", "terms": ["Lagerist", "Fachkraft Lagerlogistik", "Berufskraftfahrer", "Kommissionierer", "Speditionskaufmann"]},
    {"bucket": "office_finance", "terms": ["Sachbearbeiter", "Buchhalter", "Finanzbuchhalter", "Controller", "Kaufmaennischer Mitarbeiter"]},
    {"bucket": "engineering", "terms": ["Ingenieur", "Techniker", "Konstrukteur"]},
    {"bucket": "technology_data", "terms": ["Softwareentwickler", "Software Engineer", "Data Analyst", "Data Scientist", "Systemadministrator"]},
]

SECONDARY_SOURCE_CITIES = [
    "Berlin",
    "Hamburg",
    "Muenchen",
    "Dresden",
    "Koeln",
]

SECONDARY_SOURCE_QUERY_BUCKETS = [
    {"bucket": "hospitality", "terms": ["Koch", "Servicekraft"]},
    {"bucket": "retail_sales", "terms": ["Verkaeufer", "Kundenberater"]},
    {"bucket": "healthcare", "terms": ["Pflegefachkraft", "Altenpfleger"]},
    {"bucket": "education_social", "terms": ["Erzieher", "Sozialpaedagoge"]},
    {"bucket": "trades_field", "terms": ["Elektriker", "Elektroniker"]},
    {"bucket": "manufacturing", "terms": ["Mechatroniker", "Industriemechaniker"]},
    {"bucket": "logistics_transport", "terms": ["Berufskraftfahrer", "Fachkraft Lagerlogistik"]},
    {"bucket": "office_finance", "terms": ["Sachbearbeiter", "Finanzbuchhalter"]},
    {"bucket": "technology_data", "terms": ["Softwareentwickler", "Data Analyst"]},
]

BUCKET_LABELS = {
    "hospitality": "Hospitality",
    "retail_sales": "Retail & Sales",
    "healthcare": "Healthcare",
    "education_social": "Education & Social",
    "trades_field": "Trades & Field Service",
    "manufacturing": "Manufacturing",
    "logistics_transport": "Logistics & Transport",
    "office_finance": "Office & Finance",
    "engineering": "Engineering",
    "technology_data": "Tech & Data",
    "all_jobs": "All jobs",
    "custom": "Custom",
    "primary_source": "Primary source",
}


def collect_market_jobs(
    *,
    cities: list[str] | None = None,
    terms: list[str] | None = None,
    delay_seconds: float = 0.4,
    source_scope: str = "all",
    include_secondary_source: bool = True,
    include_primary_sources: bool = True,
    primary_sources_config_path: str | Path | None = None,
    ba_broad: bool = False,
    ba_radius_km: int = 20,
    ba_page_size: int = 100,
    ba_max_pages: int | None = None,
    output_path: str | Path | None = None,
) -> dict:
    target_cities = list(cities or GERMANY_CITIES)
    query_plan = _build_market_query_plan(custom_terms=terms)
    secondary_query_plan = _build_secondary_query_plan()
    out_path = Path(output_path) if output_path else DEFAULT_OUTPUT
    selected_scope = str(source_scope or "all").strip().lower() or "all"
    use_stepstone = selected_scope in {"all", "stepstone"}
    use_ba = include_secondary_source and selected_scope in {"all", "ba"}
    use_primary_sources = include_primary_sources and selected_scope in {"all", "primary"}

    all_jobs: list[dict] = []
    query_log: list[dict] = []

    total_queries = 0
    if use_stepstone:
        total_queries += len(target_cities) * len(query_plan)
    if use_ba:
        total_queries += len(SECONDARY_SOURCE_CITIES) if ba_broad else len(SECONDARY_SOURCE_CITIES) * len(secondary_query_plan)
    primary_sources = _load_primary_sources(primary_sources_config_path or DEFAULT_PRIMARY_SOURCES_CONFIG) if use_primary_sources else []
    total_queries += len(primary_sources)
    current_query = 0

    if use_stepstone:
        for city in target_cities:
            for query in query_plan:
                term = query["term"]
                current_query += 1
                _print_progress_start(current_query, total_queries, source="Stepstone", city=city, bucket=query["bucket"], term=term)
                log.info("[%s/%s] Stepstone %r in %r", current_query, total_queries, term, city)
                jobs = fetch_stepstone(term, city)
                tagged = _tag_market_metadata(jobs, term=term, city=city, bucket=query["bucket"], source_label="stepstone")
                all_jobs.extend(tagged)
                _print_progress_end(len(tagged), len(all_jobs))
                query_log.append(
                    {
                        "source": "stepstone",
                        "term": term,
                        "bucket": query["bucket"],
                        "city": city,
                        "count": len(tagged),
                    }
                )
                if delay_seconds > 0:
                    time.sleep(delay_seconds)

    if use_ba:
        if ba_broad:
            for city in SECONDARY_SOURCE_CITIES:
                current_query += 1
                _print_progress_start(current_query, total_queries, source="Arbeitsagentur", city=city, bucket="all_jobs", term="ALL")
                log.info("[%s/%s] Arbeitsagentur broad city scan in %r", current_query, total_queries, city)
                result = fetch_ba_jobs_with_meta(
                    "",
                    city,
                    all_pages=True,
                    radius_km=ba_radius_km,
                    size=ba_page_size,
                    max_pages=ba_max_pages,
                    delay_seconds=max(delay_seconds, 0.1),
                )
                jobs = result["jobs"]
                tagged = _tag_market_metadata(jobs, term="", city=city, bucket="all_jobs", source_label="arbeitsagentur")
                all_jobs.extend(tagged)
                _print_progress_end(len(tagged), len(all_jobs))
                query_log.append(
                    {
                        "source": "arbeitsagentur",
                        "term": "",
                        "bucket": "all_jobs",
                        "city": city,
                        "count": len(tagged),
                        "pages": int(result.get("pages") or 0),
                        "mode": str(result.get("mode") or "unknown"),
                        "radius_km": ba_radius_km,
                        "page_size": ba_page_size,
                    }
                )
                if delay_seconds > 0:
                    time.sleep(delay_seconds)
        else:
            for city in SECONDARY_SOURCE_CITIES:
                for query in secondary_query_plan:
                    term = query["term"]
                    current_query += 1
                    _print_progress_start(current_query, total_queries, source="Arbeitsagentur", city=city, bucket=query["bucket"], term=term)
                    log.info("[%s/%s] Arbeitsagentur %r in %r", current_query, total_queries, term, city)
                    result = fetch_ba_jobs_with_meta(term, city, radius_km=ba_radius_km, size=ba_page_size)
                    jobs = result["jobs"]
                    tagged = _tag_market_metadata(jobs, term=term, city=city, bucket=query["bucket"], source_label="arbeitsagentur")
                    all_jobs.extend(tagged)
                    _print_progress_end(len(tagged), len(all_jobs))
                    query_log.append(
                        {
                            "source": "arbeitsagentur",
                            "term": term,
                            "bucket": query["bucket"],
                            "city": city,
                            "count": len(tagged),
                            "pages": int(result.get("pages") or 0),
                            "mode": str(result.get("mode") or "unknown"),
                            "radius_km": ba_radius_km,
                            "page_size": ba_page_size,
                        }
                    )
                    if delay_seconds > 0:
                        time.sleep(delay_seconds)

    for source in primary_sources:
        current_query += 1
        source_name = str(source.get("name") or source.get("kind") or "primary_source")
        _print_progress_start(
            current_query,
            total_queries,
            source="Primary source",
            city=str(source.get("location_hint") or source.get("company") or ""),
            bucket="primary_source",
            term=source_name,
        )
        log.info("[%s/%s] Primary source %r", current_query, total_queries, source_name)
        try:
            jobs = _fetch_primary_source_jobs(source)
        except Exception as exc:
            log.warning("Primary source %r failed: %s", source_name, exc)
            jobs = []
        tagged = _tag_primary_source_jobs(jobs, source=source)
        all_jobs.extend(tagged)
        _print_progress_end(len(tagged), len(all_jobs))
        query_log.append(
            {
                "source": str(source.get("kind") or "primary"),
                "term": "",
                "city": str(source.get("location_hint") or source.get("company") or ""),
                "count": len(tagged),
                "name": source_name,
                "status": "ok" if tagged else "empty_or_failed",
            }
        )
        if delay_seconds > 0:
            time.sleep(delay_seconds)

    deduped = deduplicate(all_jobs)
    live_jobs, invalid_jobs = validate_jobs(deduped)
    final_jobs = []
    for job in live_jobs + invalid_jobs:
        merged = dict(job)
        merged.update(annotate_job_links(job))
        final_jobs.append(merged)

    if not final_jobs:
        existing = _load_existing_payload(out_path)
        existing_jobs = existing.get("jobs", []) if isinstance(existing, dict) else []
        if existing_jobs:
            log.warning("Collector produced zero jobs; preserving existing dataset at %s", out_path)
            return {
                "output_path": str(out_path),
                "raw_jobs": len(all_jobs),
                "deduped_jobs": len(existing_jobs),
                "invalid_jobs": 0,
                "query_count": total_queries,
                "preserved_existing": True,
            }
        log.warning("Collector produced zero jobs and no previous dataset was available; skipping write to %s", out_path)
        return {
            "output_path": str(out_path),
            "raw_jobs": len(all_jobs),
            "deduped_jobs": 0,
            "invalid_jobs": 0,
            "query_count": total_queries,
            "preserved_existing": False,
        }

    _backup_existing_file(out_path)

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "sources": sorted({entry["source"] for entry in query_log}),
        "cities": target_cities,
        "terms": [query["term"] for query in query_plan],
        "query_plan": query_plan,
        "secondary_query_plan": secondary_query_plan if include_secondary_source else [],
        "query_log": query_log,
        "jobs": final_jobs,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "output_path": str(out_path),
        "raw_jobs": len(all_jobs),
        "deduped_jobs": len(final_jobs),
        "invalid_jobs": len(invalid_jobs),
        "query_count": total_queries,
    }


def _tag_market_metadata(jobs: list[dict], *, term: str, city: str, bucket: str, source_label: str) -> list[dict]:
    tagged: list[dict] = []
    for job in jobs:
        enriched = dict(job)
        enriched["market_search_term"] = term
        enriched["market_search_city"] = city
        enriched["market_search_bucket"] = bucket
        enriched["market_search_source"] = source_label
        enriched["market_source_kind"] = "broad_market_scan"
        tagged.append(enriched)
    return tagged


def _tag_primary_source_jobs(jobs: list[dict], *, source: dict) -> list[dict]:
    tagged: list[dict] = []
    source_name = str(source.get("name") or source.get("kind") or "primary_source")
    source_kind = str(source.get("kind") or "primary").strip().lower()
    filtered_jobs = _filter_primary_source_jobs(jobs, source=source)
    for job in filtered_jobs:
        enriched = dict(job)
        enriched["market_search_term"] = enriched.get("market_search_term") or ""
        enriched["market_search_city"] = enriched.get("market_search_city") or str(source.get("location_hint") or "")
        enriched["market_source_kind"] = "primary_source_feed"
        enriched["primary_source_name"] = source_name
        enriched["primary_source_kind"] = source_kind
        enriched["source_group_override"] = "Primary Source"
        tagged.append(enriched)
    return tagged


def _load_primary_sources(path: str | Path) -> list[dict]:
    target = Path(path)
    if not target.exists():
        return []
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict) and item.get("enabled")]


def _fetch_primary_source_jobs(source: dict) -> list[dict]:
    kind = str(source.get("kind") or "").strip().lower()
    if kind == "greenhouse":
        return fetch_greenhouse_board(
            str(source.get("board_token") or ""),
            company_name=str(source.get("company") or ""),
            location_hint=str(source.get("location_hint") or ""),
        )
    if kind == "lever":
        return fetch_lever_site(
            str(source.get("site_name") or ""),
            company_name=str(source.get("company") or ""),
            location_hint=str(source.get("location_hint") or ""),
        )
    if kind == "jobposting":
        return fetch_jobposting_url(
            str(source.get("url") or ""),
            company_name=str(source.get("company") or ""),
            source_name=str(source.get("source_name") or "direct_jobposting"),
        )
    return []


def _filter_primary_source_jobs(jobs: list[dict], *, source: dict) -> list[dict]:
    keywords = [str(item).strip().lower() for item in source.get("include_location_keywords", []) if str(item).strip()]
    if not keywords:
        return jobs
    filtered = []
    for job in jobs:
        haystack = " ".join(
            [
                str(job.get("title") or ""),
                str(job.get("location") or ""),
                str(job.get("description") or "")[:1200],
            ]
        ).lower()
        if any(keyword in haystack for keyword in keywords):
            filtered.append(job)
    return filtered


def _build_market_query_plan(*, custom_terms: list[str] | None = None) -> list[dict]:
    if custom_terms:
        return [{"term": term, "bucket": "custom"} for term in _unique_terms(custom_terms)]
    return _flatten_query_buckets(MARKET_QUERY_BUCKETS)


def _build_secondary_query_plan() -> list[dict]:
    return _flatten_query_buckets(SECONDARY_SOURCE_QUERY_BUCKETS)


def _flatten_query_buckets(buckets: list[dict]) -> list[dict]:
    seen: set[str] = set()
    plan: list[dict] = []
    for bucket in buckets:
        bucket_name = str(bucket.get("bucket") or "unknown").strip().lower() or "unknown"
        for raw_term in bucket.get("terms", []):
            term = str(raw_term or "").strip()
            key = term.lower()
            if not term or key in seen:
                continue
            seen.add(key)
            plan.append({"term": term, "bucket": bucket_name})
    return plan


def _unique_terms(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = str(value or "").strip()
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


def _load_existing_payload(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _backup_existing_file(path: Path) -> None:
    if not path.exists():
        return
    backup_path = path.with_name(f"{path.stem}.backup{path.suffix}")
    try:
        shutil.copy2(path, backup_path)
    except Exception:
        log.warning("Could not create backup for %s", path)


def _print_progress_start(current: int, total: int, *, source: str, city: str, bucket: str, term: str) -> None:
    bucket_label = BUCKET_LABELS.get(str(bucket).strip().lower(), str(bucket or "Unknown").strip() or "Unknown")
    print(f"[{current:03d}/{total:03d}] {source:<14} {city:<18} {bucket_label:<22} {term} ...", end="", flush=True)


def _print_progress_end(count: int, raw_total: int) -> None:
    print(f" {count:>4} hits | raw {raw_total}", flush=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = collect_market_jobs()
    print(result)
