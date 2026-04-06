from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from market_explorer.paths import data_path, runtime_path
from source.job_url_normalizer import normalize_job_url


DEFAULT_INPUT = data_path("market_jobs_collected.json")
FALLBACK_INPUT = runtime_path("jobs_scored.json")
DEFAULT_JOBS_OUTPUT = data_path("market_jobs.json")
DEFAULT_SUMMARY_OUTPUT = data_path("market_summary.json")

ROLE_PATTERNS = [
    (
        "Hospitality and Gastronomy",
        [r"\bkoch\b", r"\bköch", r"\bkuechen", r"\bküche", r"\bchef\b", r"\bsouschef\b", r"\bservicekraft\b", r"\bservicemitarbeiter\b", r"\brestaurantfach", r"\bhotelfach\b", r"\bbäcker\b", r"\bkonditor\b", r"\bfood stylist\b", r"\bkochschule\b", r"\bserviceleiter\b", r"\bhausdame\b"],
    ),
    (
        "Retail and Sales",
        [r"\bverkaeufer", r"\bverkäufer", r"\bverkauf\b", r"\bsales\b", r"\bshop\b", r"\bfilial", r"\beinzelhandel\b", r"\bkundenberater\b", r"\bkundenbetreuer\b", r"\btelefonischer kundenbetreuer\b", r"\bpromoter\b", r"\bvertrieb", r"\bautomobilverkäufer\b", r"\bverkaufstalent\b", r"\bkey account\b", r"\baußendienst", r"\bbusiness development\b", r"\bkassierer\b", r"\babteilungsleiter obst", r"\babteilungsleiter frischetheke", r"\bcallcenteragent\b"],
    ),
    (
        "Healthcare and Nursing",
        [r"\bpflege", r"\bpflegefachkraft", r"\baltenpfleger", r"\baltenpflegehelfer", r"\bkrankenschwester\b", r"\bgesundheits", r"\bmedical\b", r"\bklinik\b", r"\bota\b", r"\bfacharzt\b", r"\bzahnmedizin", r"\bzahnarzt\b", r"\bmfa\b", r"\bmedizinische fachangestellte\b", r"\bplasmaspende", r"\bphysiotherapeut", r"\bergotherapeut", r"\btherapeut", r"\boperationstechnischer assistent", r"\bsterilisationsassistent\b", r"\blaborant", r"\bchemielaborant", r"\bbiologe\b", r"\baugenoptiker\b"],
    ),
    (
        "Education and Social Work",
        [r"\berzieher", r"\bkinderpfleger", r"\bsozial", r"\blehrer\b", r"\bpaedagog", r"\bpädagog", r"\bkita\b", r"\barbeitserzieher", r"\bheilerziehung", r"\btrainer\b", r"\bfachtrainer\b", r"\bbetreuer", r"\bcase manager\b"],
    ),
    (
        "Skilled Trades and Construction",
        [r"\belektriker\b", r"\belektroniker\b", r"\belektroinstall", r"\belektrotechnik\b", r"\belektrotechniker\b", r"\belektrohelfer\b", r"\bindustrieelektriker\b", r"\belektroanlagenmonteur\b", r"\bbauelektriker\b", r"\bhandwerker\b", r"\bmonteur\b", r"\banlagenmechaniker\b", r"\bservicetechniker\b", r"\bschwei", r"\bstahlbau\b", r"\bgarten- und landschaftsbau", r"\bmetallbauer\b", r"\bprüfservice\b", r"\btischler\b", r"\bmaler\b", r"\blackierer\b", r"\bm[aä]lerhelfer\b", r"\bbodenleger\b", r"\bhausmeister\b", r"\bhaustechniker\b", r"\bschlosser\b", r"\bbetriebsschlosser\b", r"\bgas- und wasserinstallateur", r"\blüftungsmonteur", r"\bzentralheizungs- und lüftungsbauer\b", r"\bbauleiter\b", r"\bbauhelfer\b", r"\bbauzeichner\b", r"\barchitekt\b", r"\btiefbaufacharbeiter\b", r"\bpolier\b", r"\bkranführer\b", r"\bmaurer", r"\btrockenbaumonteur\b", r"\bvorrichter\b", r"\breinigungskraft", r"\breinigung\b", r"\bsicherheitsmitarbeiter\b", r"\bsicherungsposten\b", r"\bobjektleiter\b", r"\bgebäudereiniger\b", r"\bfacility\b", r"\breifenmonteur\b", r"\bger[üu]stbauer\b", r"\btrockenbauer\b", r"\bdachdecker\b", r"\bbaumaschinenführer\b"],
    ),
    (
        "Manufacturing and Production",
        [r"\bproduktion", r"\bproduktionsmitarbeiter\b", r"\bmaschinenbedien", r"\bfertigung", r"\bzerspan", r"\bcnc\b", r"\bdreher\b", r"\bschleifer\b", r"\barbeitsvorbereitung\b", r"\bprototypenbau\b", r"\bmaschinen- und anlagenf", r"\bmaschinenführer\b", r"\bkonstruktionsmechaniker\b", r"\bwerkzeugmechaniker\b", r"\bwerkzeugmacher\b", r"\bmontagemitarbeiter\b", r"\bchemikant\b", r"\bindustrielackierer\b", r"\bfahrzeuglackierer\b", r"\bverfahrensmechaniker\b", r"\binstandhaltungsmechaniker\b", r"\binstandhalter\b", r"\bkraftfahrzeugmechatroniker\b", r"\bgalvaniseur\b", r"\bmontierer\b", r"\bfeinwerkmechaniker\b", r"\bkarosseriebauer\b", r"\bautogenschweißer\b", r"\bl[öo]ter\b", r"\boberflächenbeschichter\b", r"\bqualitätsprüfer\b", r"\bholzmechaniker\b"],
    ),
    (
        "Logistics and Transport",
        [r"\blager", r"\bfachlager", r"\bstapler", r"\bfahrer\b", r"\blogistik\b", r"\bspedition", r"\bkommissionier", r"\bdisposition\b", r"\bspeditionskauf", r"\bauslieferungsfahrer\b", r"\btransport- und auslieferungsfahrer\b", r"\bexport", r"\bberufskraftfahrer\b", r"\bkraftfahrer\b", r"\bgabelstaplerfahrer\b", r"\bbusfahrer", r"\bkleinbusfahrer", r"\blinienverkehr\b", r"\blokführer\b", r"\btriebfahrzeugführer", r"\bflotten", r"\bfleet\b", r"\bpostbote\b"],
    ),
    (
        "Finance and Office",
        [r"\bbuchhalter\b", r"\bfinanzbuchhalter\b", r"\bbilanzbuchhalter\b", r"\blohnbuchhalter\b", r"\blohn- und gehaltsbuchhalter\b", r"\bsachbearbeiter", r"\bsachbearbeitung\b", r"\bcontroller\b", r"\boffice\b", r"\badministration\b", r"\bbüromanagement\b", r"\bbürokauf", r"\bbürokraft", r"\bteamassistenz\b", r"\bprojektassistenz\b", r"\brechtsanwaltsfachangestellte", r"\brechtsanwalt\b", r"\bsteuerberater\b", r"\bsteuerfachangestell", r"\bpersonalsachbearbeiter\b", r"\bpersonalberater\b", r"\brecruiter\b", r"\bpersonaldisponent\b", r"\bempfangsmitarbeiter\b", r"\bcall center agent\b", r"\brechnungswesen\b", r"\bfinanzen\b", r"\bcontrolling\b", r"\btelefonzentrale\b", r"\bassistenz\b", r"\beinkauf", r"\beinkäufer\b", r"\btechnischer einkäufer\b", r"\bstrategischer einkäufer\b", r"\boperativer einkäufer\b", r"\banalyst\b", r"\bworkflowmanagement", r"\bpayroll\b", r"\bproperty manager\b", r"\bweg-verwalter\b", r"\bimmobilienkaufmann\b", r"\bbetriebswirt\b", r"\baccount manager\b", r"\bniederlassungsleiter\b"],
    ),
    ("Engineering and Industrial", [r"\bingenieur\b", r"\bmechatroniker\b", r"\bindustriemechaniker\b", r"\bkonstrukteur\b", r"\btechniker\b", r"\bmesstechniker\b", r"\bprojektingenieur\b", r"\bsps-programmierer\b", r"\bwirtschaftsingenieur\b", r"\bfachkraft für arbeitssicherheit\b", r"\bprojektleiter\b", r"\btechnischer redakteur\b"]),
    ("Software and IT", [r"\bsoftware", r"\bdeveloper\b", r"\bdevops\b", r"\bplatform engineer\b", r"\bit support\b", r"\bfullstack\b", r"\binformatik\b", r"\binformatiker\b", r"\bsystemadministrator\b", r"\bit-administrator\b", r"\bfachinformatiker\b", r"\bfachinformatiker systemintegration\b", r"\bwirtschaftsinformatiker\b", r"\bdatenmigration\b"]),
    ("Data and AI", [r"\bdata analyst\b", r"\bdata scientist\b", r"\bdata engineer\b", r"\bmachine learning\b", r"\bml\b", r"\bai\b"]),
]

SKILL_PATTERNS = {
    "Python": [r"\bpython\b"],
    "SQL": [r"\bsql\b"],
    "AWS": [r"\baws\b", r"\bamazon web services\b"],
    "Azure": [r"\bazure\b"],
    "GCP": [r"\bgcp\b", r"\bgoogle cloud\b"],
    "Docker": [r"\bdocker\b"],
    "Kubernetes": [r"\bkubernetes\b", r"\bk8s\b"],
    "Airflow": [r"\bairflow\b"],
    "Spark": [r"\bspark\b", r"\bpyspark\b"],
    "TensorFlow": [r"\btensorflow\b"],
    "PyTorch": [r"\bpytorch\b"],
    "OpenCV": [r"\bopencv\b"],
    "C++": [r"\bc\+\+\b"],
    "Java": [r"\bjava\b"],
    "Databricks": [r"\bdatabricks\b"],
    "Snowflake": [r"\bsnowflake\b"],
    "dbt": [r"\bdbt\b"],
    "LLM": [r"\bllm\b", r"\bgenai\b", r"\bgenerative ai\b", r"\blangchain\b", r"\brag\b"],
}

INDUSTRY_PATTERNS = [
    ("Healthcare", [r"\bklinik\b", r"\bhospital\b", r"\bpflege\b", r"\bmedical\b", r"\bgesundheit\b", r"\bradiolog", r"\bkrankenhaus\b", r"\bphysiotherapeut", r"\bergotherapeut", r"\btherapie\b", r"\bzahnarzt\b", r"\blabor\b", r"\bcase manager\b"]),
    ("Technology", [r"\bsoftware\b", r"\bdeveloper\b", r"\bit\b", r"\bdata\b", r"\bai\b", r"\bcloud\b", r"\bcyber\b", r"\bsaas\b", r"\bsystemadministrator\b", r"\bfachinformatiker\b", r"\binformatiker\b"]),
    ("Finance and Insurance", [r"\bfinanz\b", r"\bversicherung\b", r"\bbank\b", r"\bbuchhalt", r"\bsteuer", r"\baudit\b", r"\baccount", r"\brechtsanwaltsfachangestellte", r"\brechtsanwalt\b", r"\bsteuerberater\b", r"\bsteuerfachangestell", r"\bbilanzbuchhalter\b", r"\blohnbuchhalter\b", r"\bpayroll\b", r"\beinkäufer\b"]),
    (
        "Professional Services",
        [
            r"\bconsult",
            r"\bberatung\b",
            r"\bwirtschaftspr",
            r"\bpayroll\b",
            r"\bpersonalmanagement\b",
            r"\bsteuerberatung\b",
            r"\baccounting\b",
        ],
    ),
    (
        "Public, Education and Social Services",
        [
            r"\buniversit",
            r"\bstadt\b",
            r"\blandeshauptstadt\b",
            r"\bawo\b",
            r"\bkita\b",
            r"\bschule\b",
            r"\berzieher\b",
            r"\bsozial",
            r"\bjugendhilfe\b",
            r"\bstiftung\b",
            r"\bkirche\b",
            r"\bkindertages",
        ],
    ),
    ("Hospitality", [r"\bhotel\b", r"\brestaurant\b", r"\bgastronomie\b", r"\bkoch\b", r"\bkueche\b", r"\bcatering\b"]),
    ("Retail and Consumer", [r"\brewe\b", r"\baldi\b", r"\blidl\b", r"\bverkauf\b", r"\bfiliale\b", r"\bsupermarkt\b", r"\boptik\b", r"\bkassierer\b", r"\bobst & gemüse\b", r"\bfrischetheke\b", r"\bfriseur\b"]),
    ("Real Estate and Property", [r"\bimmobil", r"\bproperty\b", r"\bhausverwaltung\b", r"\bwohn", r"\bfacility\b", r"\bhausmeister\b", r"\bhaustechnik\b", r"\bobjektleiter\b", r"\bgebäudereiniger\b", r"\breinigungskraft\b", r"\bweg-verwalter\b", r"\bimmobilienkaufmann\b"]),
    ("Logistics", [r"\blogistik\b", r"\bdachser\b", r"\bspedition\b", r"\blager\b", r"\bwarehouse\b", r"\brhenus\b", r"\bgabelstaplerfahrer\b", r"\bberufskraftfahrer\b", r"\bkraftfahrer\b", r"\bpostbote\b"]),
    (
        "Mobility and Transport Infrastructure",
        [
            r"\bbahn\b",
            r"\bdeutsche bahn\b",
            r"\beisenbahn\b",
            r"\bstellwerk\b",
            r"\bbusfahrer",
            r"\bberufskraftfahrer",
            r"\bkraftfahrer",
            r"\bfernverkehr\b",
            r"\bnahverkehr\b",
            r"\baviation\b",
            r"\bautomobile\b",
            r"\bautohaus\b",
            r"\bkfz\b",
            r"\bfahrzeug\b",
            r"\brail\b",
            r"\bsicherungsposten\b",
        ],
    ),
    ("Manufacturing and Industrial", [r"\bbmw\b", r"\bmercedes\b", r"\bman truck\b", r"\bindustrie\b", r"\bfertigung\b", r"\bproduktion\b", r"\bmaschinenbau\b", r"\bmaschinen- und anlagenf", r"\bkonstruktionsmechaniker\b", r"\bwerkzeugmechaniker\b", r"\bchemikant\b", r"\bindustrielackierer\b", r"\bfahrzeuglackierer\b", r"\bverfahrensmechaniker\b", r"\binstandhaltungsmechaniker\b", r"\bkraftfahrzeugmechatroniker\b", r"\bgalvaniseur\b", r"\bmontierer\b", r"\bfeinwerkmechaniker\b", r"\bkarosseriebauer\b", r"\bautogenschweißer\b"]),
    ("Construction and Field Service", [r"\belektriker\b", r"\bmonteur\b", r"\bpruefservice\b", r"\bservicetechn", r"\banlagen\b", r"\bhandwerk\b", r"\btischler\b", r"\bmaler\b", r"\bm[aä]lerhelfer\b", r"\bbodenleger\b", r"\bbauleiter\b", r"\bbauzeichner\b", r"\barchitekt\b", r"\bschlosser\b", r"\bgas- und wasserinstallateur", r"\blüftungsmonteur", r"\bger[üu]stbauer\b", r"\btrockenbauer\b", r"\bdachdecker\b", r"\bbaumaschinenführer\b", r"\breifenmonteur\b"]),
]

INDUSTRY_FALLBACK_BY_ROLE = {
    "Hospitality and Gastronomy": "Hospitality",
    "Retail and Sales": "Retail and Consumer",
    "Healthcare and Nursing": "Healthcare",
    "Education and Social Work": "Public, Education and Social Services",
    "Skilled Trades and Construction": "Construction and Field Service",
    "Manufacturing and Production": "Manufacturing and Industrial",
    "Logistics and Transport": "Logistics",
    "Finance and Office": "Professional Services",
    "Engineering and Industrial": "Manufacturing and Industrial",
    "Software and IT": "Technology",
    "Data and AI": "Technology",
}

AGGREGATOR_COMPANY_PATTERNS = [
    r"\bmeinestadt\.de\b",
    r"\bjobninja\b",
    r"\bstellenonline\b",
    r"\bkimeta\b",
]

STAFFING_COMPANY_PATTERNS = [
    r"\bgmbh\b.*\bpersonaldienst",
    r"\bferchau\b",
    r"\bexpertum\b",
    r"\bpiening\b",
    r"\bbindan\b",
    r"\bamadeus fire\b",
    r"\bhays\b",
]

SENIORITY_PATTERNS = [
    ("Senior", [r"\bsenior\b", r"\blead\b", r"\bstaff\b", r"\bprincipal\b"]),
    ("Mid", [r"\bengineer\b", r"\bscientist\b", r"\banalyst\b", r"\bdeveloper\b"]),
    ("Junior", [r"\bjunior\b", r"\bentry\b", r"\bgraduate\b", r"\btrainee\b", r"\bintern\b"]),
]

REMOTE_PATTERNS = {
    "Remote": [r"\bremote\b", r"\bfully remote\b", r"\bhome office\b", r"\bwork from home\b"],
    "Hybrid": [r"\bhybrid\b", r"\bflexible working\b", r"\bremote option\b"],
    "Onsite": [r"\bonsite\b", r"\bon-site\b", r"\bvor ort\b"],
}

APPRENTICESHIP_PATTERNS = [
    r"\bausbildung\b",
    r"\bausbildungsplatz\b",
    r"\bauszubild",
    r"\bazubi\b",
    r"\bduales?\s+studium\b",
    r"\bwerkstudent",
    r"\bpraktik",
    r"\btrainee\b",
    r"\btraineeship\b",
    r"\bintern\b",
    r"\binternship\b",
    r"\bgraduate program\b",
    r"\banerkennungsjahr\b",
    r"\banerkennungspraktik",
]


def build_market_dataset(
    input_path: str | Path | None = None,
    jobs_output_path: str | Path | None = None,
    summary_output_path: str | Path | None = None,
) -> dict:
    jobs_path = Path(input_path) if input_path else _resolve_input_path()
    jobs_output = Path(jobs_output_path) if jobs_output_path else DEFAULT_JOBS_OUTPUT
    summary_output = Path(summary_output_path) if summary_output_path else DEFAULT_SUMMARY_OUTPUT

    payload = _load_input_payload(jobs_path)
    jobs = payload["jobs"]
    enriched_jobs = [_enrich_job(job) for job in jobs]
    enriched_jobs.sort(
        key=lambda job: (
            job.get("date_sort_key", ""),
            float(job.get("ranking_score") or job.get("score") or 0.0),
        ),
        reverse=True,
    )

    summary = _build_summary(enriched_jobs, query_log=payload.get("query_log", []))
    jobs_output.write_text(json.dumps(enriched_jobs, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "jobs_path": str(jobs_output),
        "summary_path": str(summary_output),
        "job_count": len(enriched_jobs),
    }


def _resolve_input_path() -> Path:
    if DEFAULT_INPUT.exists():
        default_jobs = _load_jobs(DEFAULT_INPUT)
        if default_jobs:
            return DEFAULT_INPUT
    return FALLBACK_INPUT


def _load_input_payload(path: Path) -> dict:
    if not path.exists():
        return {"jobs": [], "query_log": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        jobs = payload.get("jobs") if isinstance(payload.get("jobs"), list) else []
        query_log = payload.get("query_log") if isinstance(payload.get("query_log"), list) else []
        return {
            "jobs": [item for item in jobs if isinstance(item, dict)],
            "query_log": [item for item in query_log if isinstance(item, dict)],
        }
    if isinstance(payload, list):
        return {"jobs": [item for item in payload if isinstance(item, dict)], "query_log": []}
    return {"jobs": [], "query_log": []}


def _load_jobs(path: Path) -> list[dict]:
    return _load_input_payload(path)["jobs"]


def _enrich_job(job: dict) -> dict:
    title = _clean_text(job.get("title"))
    company = _clean_text(job.get("company"))
    location = _clean_text(job.get("location"))
    description = _clean_text(job.get("description"))
    source = _clean_text(job.get("source")).lower() or "unknown"
    date_value = _resolve_job_date(job)
    normalized_region = _normalize_region(location)

    enriched = dict(job)
    company_display = _normalize_company_display(company, source=source)
    role_cluster = _classify_role(title, description)
    industry = _infer_industry(title, company_display, description, role_cluster)
    company_kind = _classify_company_kind(company_display, source=source)
    enriched.update(
        {
            "canonical_url": normalize_job_url(job.get("url", ""), source=source),
            "title_clean": title,
            "company_clean": company_display,
            "location_clean": location,
            "role_cluster": role_cluster,
            "seniority": _classify_seniority(title, description),
            "remote_mode": _infer_remote_mode(title, location, description),
            "region": normalized_region["region"],
            "city": normalized_region["city"],
            "country": normalized_region["country"],
            "skills": _extract_skills(title, description),
            "industry": industry,
            "company_kind": company_kind,
            "market_score": _market_score(job),
            "date_sort_key": date_value,
            "date_label": date_value or "unknown",
            "has_description": bool(description),
            "source_group": _source_group(source, source_group_override=_clean_text(job.get("source_group_override"))),
            "source_display": _source_display_name(
                source,
                primary_source_name=_clean_text(job.get("primary_source_name")),
                company_name=company_display,
            ),
            "source_strategy": _clean_text(job.get("source_strategy")),
            "source_family": _clean_text(job.get("source_family")),
            "primary_source_name": _clean_text(job.get("primary_source_name")),
            "primary_source_kind": _clean_text(job.get("primary_source_kind")),
            "primary_source_score": int(job.get("primary_source_score") or 0),
            "exclude_from_market_view": _is_apprenticeship_listing(title),
            "market_exclusion_reason": "apprenticeship" if _is_apprenticeship_listing(title) else "",
        }
    )
    return enriched


def _build_summary(jobs: list[dict], *, query_log: list[dict] | None = None) -> dict:
    visible_jobs = [
        job for job in jobs
        if not _is_hidden_bucket(job.get("final_bucket", ""))
        and str(job.get("job_status") or "").strip().lower() != "invalid"
        and not bool(job.get("exclude_from_market_view"))
    ]
    source_counts = Counter(job.get("source_display") or "Unknown" for job in visible_jobs)
    source_strategy_counts = Counter(job.get("source_strategy") or "unknown" for job in visible_jobs)
    region_counts = Counter(job.get("region") or "Unknown" for job in visible_jobs)
    role_counts = Counter(job.get("role_cluster") or "Other" for job in visible_jobs)
    remote_counts = Counter(job.get("remote_mode") or "Unknown" for job in visible_jobs)
    seniority_counts = Counter(job.get("seniority") or "Unknown" for job in visible_jobs)
    company_counts = Counter(job.get("company_clean") or "Unknown" for job in visible_jobs)
    skill_counts = Counter(skill for job in visible_jobs for skill in job.get("skills", []))
    industry_counts = Counter(job.get("industry") or "Other" for job in visible_jobs)
    company_kind_counts = Counter(job.get("company_kind") or "Employer" for job in visible_jobs)
    timeline_counts = Counter(job.get("date_label") or "unknown" for job in visible_jobs)

    jobs_by_role_region: dict[str, Counter] = defaultdict(Counter)
    jobs_by_skill_role: dict[str, Counter] = defaultdict(Counter)
    for job in visible_jobs:
        jobs_by_role_region[job.get("role_cluster") or "Other"][job.get("region") or "Unknown"] += 1
        for skill in job.get("skills", []):
            jobs_by_skill_role[skill][job.get("role_cluster") or "Other"] += 1

    searched_source_counts = Counter()
    searched_source_hits = Counter()
    for row in query_log or []:
        display_name = _query_log_source_name(row)
        searched_source_counts[display_name] += 1
        searched_source_hits[display_name] += int(row.get("count") or 0)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "total_jobs": len(jobs),
        "visible_jobs": len(visible_jobs),
        "top_regions": _counter_rows(region_counts, limit=12),
        "top_roles": _counter_rows(role_counts, limit=12),
        "top_sources": _counter_rows(source_counts, limit=12),
        "top_source_strategies": _counter_rows(source_strategy_counts, limit=12),
        "top_remote_modes": _counter_rows(remote_counts, limit=8),
        "top_seniority": _counter_rows(seniority_counts, limit=8),
        "top_companies": _counter_rows(company_counts, limit=20),
        "top_skills": _counter_rows(skill_counts, limit=25),
        "top_industries": _counter_rows(industry_counts, limit=20),
        "top_company_kinds": _counter_rows(company_kind_counts, limit=10),
        "searched_sources": [
            {
                "label": label,
                "queries": int(searched_source_counts[label]),
                "hits": int(searched_source_hits[label]),
            }
            for label, _ in sorted(searched_source_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "timeline": _counter_rows(timeline_counts, limit=120, sort_labels=True),
        "role_region_matrix": {
            role: _counter_rows(counter, limit=10)
            for role, counter in sorted(jobs_by_role_region.items())
        },
        "skill_role_matrix": {
            skill: _counter_rows(counter, limit=10)
            for skill, counter in sorted(jobs_by_skill_role.items())
        },
        "filter_options": {
            "sources": _sorted_unique(job.get("source_display") or "Unknown" for job in visible_jobs),
            "source_strategies": _sorted_unique(job.get("source_strategy") or "unknown" for job in visible_jobs),
            "regions": _sorted_unique(job.get("region") or "Unknown" for job in visible_jobs),
            "roles": _sorted_unique(job.get("role_cluster") or "Other" for job in visible_jobs),
            "remote_modes": _sorted_unique(job.get("remote_mode") or "Unknown" for job in visible_jobs),
            "seniority": _sorted_unique(job.get("seniority") or "Unknown" for job in visible_jobs),
            "industries": _sorted_unique(job.get("industry") or "Other" for job in visible_jobs),
            "company_kinds": _sorted_unique(job.get("company_kind") or "Employer" for job in visible_jobs),
        },
    }


def _is_hidden_bucket(bucket: str) -> bool:
    bucket_text = str(bucket or "").strip().lower()
    return bucket_text in {"rejected", "dead_listing"}


def _source_display_name(source: str, *, primary_source_name: str = "", company_name: str = "") -> str:
    source_key = str(source or "").strip().lower()
    if source_key == "stepstone":
        return "Stepstone"
    if source_key == "arbeitsagentur":
        return "Agentur für Arbeit"
    if source_key in {"greenhouse", "lever"}:
        return primary_source_name or company_name or ("Greenhouse" if source_key == "greenhouse" else "Lever")
    if source_key:
        return str(source).strip().title()
    return "Unknown"


def _query_log_source_name(row: dict) -> str:
    source_key = str(row.get("source") or "").strip().lower()
    if source_key == "greenhouse":
        return str(row.get("name") or "Employer career pages").strip()
    if source_key == "lever":
        return str(row.get("name") or "Lever employer source").strip()
    if source_key == "jobposting":
        return str(row.get("name") or "Direct job posting feed").strip()
    return _source_display_name(source_key)


def _market_score(job: dict) -> float:
    score = float(job.get("ranking_score") or job.get("score") or 0.0)
    link_bonus = {"medium": 1.0, "high": 1.5, "low": 0.2}.get(str(job.get("best_link_quality") or "").lower(), 0.0)
    desc_bonus = {"high": 1.0, "medium": 0.5, "low": 0.1}.get(str(job.get("description_quality") or "").lower(), 0.0)
    source_strategy = str(job.get("source_strategy") or "").strip().lower()
    source_group_override = str(job.get("source_group_override") or "").strip().lower()
    source_name = str(job.get("source") or "").strip().lower()
    company_kind = _classify_company_kind(_clean_text(job.get("company")), source=source_name)

    source_bonus = 0.0
    if source_strategy == "ats_api" or source_group_override == "primary source":
        source_bonus += 2.5
    elif source_strategy == "official_public_portal" or source_name == "arbeitsagentur":
        source_bonus += 1.5
    elif source_name == "stepstone":
        source_bonus -= 0.2

    company_penalty = {"Aggregator": -1.0, "Staffing": -0.4}.get(company_kind, 0.0)
    return round(score + link_bonus + desc_bonus + source_bonus + company_penalty, 2)


def _classify_role(title: str, description: str) -> str:
    haystack = f"{title}\n{description}".lower()
    for role_name, patterns in ROLE_PATTERNS:
        if any(re.search(pattern, haystack) for pattern in patterns):
            return role_name
    return "Other"


def _classify_seniority(title: str, description: str) -> str:
    haystack = f"{title}\n{description}".lower()
    for label, patterns in SENIORITY_PATTERNS:
        if any(re.search(pattern, haystack) for pattern in patterns):
            return label
    return "Unknown"


def _infer_remote_mode(title: str, location: str, description: str) -> str:
    haystack = f"{title}\n{location}\n{description}".lower()
    for label, patterns in REMOTE_PATTERNS.items():
        if any(re.search(pattern, haystack) for pattern in patterns):
            return label
    if "remote" in location.lower():
        return "Remote"
    return "Unknown"


def _is_apprenticeship_listing(title: str) -> bool:
    text = title.strip().lower()
    if not text:
        return False
    if "ohne ausbildung" in text:
        return False
    return any(re.search(pattern, text) for pattern in APPRENTICESHIP_PATTERNS)


def _normalize_region(location: str) -> dict[str, str]:
    text = location.strip()
    lowered = text.lower()
    if not text:
        return {"city": "Unknown", "region": "Unknown", "country": "Unknown"}
    if "münchen" in lowered or "munich" in lowered or "garching" in lowered or "muenchen" in lowered:
        return {"city": "Munich", "region": "Munich Region", "country": "Germany"}
    if "berlin" in lowered:
        return {"city": "Berlin", "region": "Berlin", "country": "Germany"}
    if "hamburg" in lowered:
        return {"city": "Hamburg", "region": "Hamburg", "country": "Germany"}
    if "dresden" in lowered:
        return {"city": "Dresden", "region": "Dresden Region", "country": "Germany"}
    if "leipzig" in lowered:
        return {"city": "Leipzig", "region": "Leipzig Region", "country": "Germany"}
    if "hannover" in lowered:
        return {"city": "Hannover", "region": "Hannover Region", "country": "Germany"}
    if "nürnberg" in lowered or "nuernberg" in lowered or "nuremberg" in lowered:
        return {"city": "Nuernberg", "region": "Nuernberg Region", "country": "Germany"}
    if "stuttgart" in lowered:
        return {"city": "Stuttgart", "region": "Stuttgart Region", "country": "Germany"}
    if "köln" in lowered or "koeln" in lowered or "cologne" in lowered:
        return {"city": "Cologne", "region": "Cologne Region", "country": "Germany"}
    if "frankfurt" in lowered:
        return {"city": "Frankfurt", "region": "Frankfurt Region", "country": "Germany"}
    if "dortmund" in lowered:
        return {"city": "Dortmund", "region": "Dortmund Region", "country": "Germany"}
    if "bremen" in lowered:
        return {"city": "Bremen", "region": "Bremen Region", "country": "Germany"}
    if "deutschland" in lowered or "germany" in lowered:
        return {"city": "Germany", "region": "Germany", "country": "Germany"}
    city = text.split(",")[0].strip() or "Unknown"
    return {"city": city, "region": city, "country": "Germany"}


def _extract_skills(title: str, description: str) -> list[str]:
    haystack = f"{title}\n{description}".lower()
    matches = []
    for skill, patterns in SKILL_PATTERNS.items():
        if any(re.search(pattern, haystack) for pattern in patterns):
            matches.append(skill)
    return sorted(matches)


def _source_group(source: str, *, source_group_override: str = "") -> str:
    if source_group_override:
        return source_group_override
    if source in {"indeed", "stepstone", "linkedin"}:
        return "Jobboard"
    if source == "arbeitsagentur":
        return "Public Portal"
    if source in {"greenhouse", "lever"}:
        return "Primary Source"
    if source:
        return "Company or ATS"
    return "Unknown"


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    text = str(value).strip()
    for _ in range(2):
        if not any(marker in text for marker in ("\u00c3", "\u00c2", "\u00e2", "\u00f0", "\ufffd")):
            break
        repaired = _try_redecode(text)
        if not repaired or repaired == text:
            break
        text = repaired
    replacements = {
        "\u00a0": " ",
        "â€“": "–",
        "â€”": "—",
        "â€ž": "„",
        "â€œ": "“",
        "â€š": "‚",
        "â€™": "’",
        "â€˜": "‘",
        "â€¦": "…",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def _parse_date(value: object) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d.%m.%Y"):
        try:
            return datetime.strptime(text[:19], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return text[:10]


def _resolve_job_date(job: dict) -> str:
    direct = _parse_date(job.get("date"))
    description = _clean_text(job.get("description"))
    inferred = _extract_date_from_text(description)
    if _is_plausible_market_date(inferred):
        return inferred
    if _is_plausible_market_date(direct):
        return direct
    return ""


def _extract_date_from_text(text: str) -> str:
    haystack = str(text or "").lower()
    if not haystack:
        return ""

    today = datetime.today().date()
    if re.search(r"\bheute\b|\btoday\b", haystack):
        return today.strftime("%Y-%m-%d")
    if re.search(r"\bgestern\b|\byesterday\b", haystack):
        return (today - timedelta(days=1)).strftime("%Y-%m-%d")

    day_match = re.search(r"\bvor\s+(\d+)\s+tag(?:en)?\b|\b(\d+)\s+days?\s+ago\b", haystack)
    if day_match:
        days = int(day_match.group(1) or day_match.group(2) or 0)
        return (today - timedelta(days=days)).strftime("%Y-%m-%d")

    week_match = re.search(r"\bvor\s+(\d+)\s+woche(?:n)?\b|\b(\d+)\s+weeks?\s+ago\b", haystack)
    if week_match:
        weeks = int(week_match.group(1) or week_match.group(2) or 0)
        return (today - timedelta(days=weeks * 7)).strftime("%Y-%m-%d")

    if re.search(r"\bvor\s+\d+\s+stund(?:e|en)\b|\b\d+\s+hours?\s+ago\b", haystack):
        return today.strftime("%Y-%m-%d")
    if re.search(r"\bvor\s+\d+\s+min(?:ute|uten)?\b|\b\d+\s+minutes?\s+ago\b", haystack):
        return today.strftime("%Y-%m-%d")
    return ""


def _is_plausible_market_date(value: str) -> bool:
    text = _parse_date(value)
    if not text:
        return False
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return False
    today = datetime.today().date()
    age_days = (today - parsed).days
    return -1 <= age_days <= 365


def _counter_rows(counter: Counter, *, limit: int, sort_labels: bool = False) -> list[dict]:
    items = list(counter.items())
    if sort_labels:
        items.sort(key=lambda item: item[0])
    else:
        items.sort(key=lambda item: (-item[1], item[0]))
    return [{"label": str(label), "count": int(count)} for label, count in items[:limit]]


def _sorted_unique(values) -> list[str]:
    return sorted({str(value) for value in values if str(value).strip()})


def _infer_industry(title: str, company: str, description: str, role_cluster: str) -> str:
    haystack = f"{title}\n{company}\n{description}".lower()
    for label, patterns in INDUSTRY_PATTERNS:
        if any(re.search(pattern, haystack) for pattern in patterns):
            return label
    fallback = INDUSTRY_FALLBACK_BY_ROLE.get(role_cluster)
    if fallback:
        return fallback
    return "Other"


def _normalize_company_display(company: str, *, source: str) -> str:
    text = company.strip()
    text = re.sub(r"\s+", " ", text)
    text = text.replace("Bee/Partment", "[Bee]Partment")
    if not text:
        return "Unknown"
    if source == "stepstone" and re.search(r"\bmeinestadt\.de\b", text, flags=re.IGNORECASE):
        return "meinestadt.de"
    return text


def _classify_company_kind(company: str, *, source: str) -> str:
    text = company.lower()
    if any(re.search(pattern, text) for pattern in AGGREGATOR_COMPANY_PATTERNS):
        return "Aggregator"
    if any(re.search(pattern, text) for pattern in STAFFING_COMPANY_PATTERNS):
        return "Staffing"
    if source == "arbeitsagentur":
        return "Employer or Public Listing"
    return "Employer"


def _try_redecode(text: str) -> str:
    for source_encoding in ("latin-1", "cp1252"):
        try:
            return text.encode(source_encoding).decode("utf-8")
        except Exception:
            continue
    return text


if __name__ == "__main__":
    result = build_market_dataset()
    print(f"Market dataset written for {result['job_count']} jobs.")
