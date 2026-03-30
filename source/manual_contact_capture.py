from __future__ import annotations

import argparse
import json
from pathlib import Path

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from source.job_buckets import classify_job
from source.project_paths import runtime_path


CONTACTS_PATH = runtime_path("contacts.json")
RAW_JOBS_PATH = runtime_path("jobs_raw.json")
SCORED_JOBS_PATH = runtime_path("jobs_scored.json")


def capture_manual_contact(
    *,
    job_id: str,
    email: str,
    name: str = "",
    role: str = "",
    phone: str = "",
    note: str = "",
    employer_apply_url: str = "",
    reference_number: str = "",
) -> None:
    raw_jobs = _load_json_list(RAW_JOBS_PATH)
    scored_jobs = _load_json_list(SCORED_JOBS_PATH)

    raw_job = _find_job(raw_jobs, job_id)
    scored_job = _find_job(scored_jobs, job_id)
    base_job = scored_job or raw_job
    if not base_job:
        raise ValueError(f"Job {job_id} nicht gefunden")

    company = (base_job.get("company") or "").strip()
    if not company:
        raise ValueError(f"Job {job_id} hat keinen Firmennamen")

    source_tag = f"manual_captcha_capture:{job_id}"
    contact = {
        "name": name.strip(),
        "role": role.strip(),
        "email": email.strip().lower(),
        "company": company,
        "source": source_tag,
        "confidence": 1.0,
        "linkedin": "",
        "outreach_sent": False,
        "replied": False,
        "phone": phone.strip(),
        "note": note.strip(),
        "reference_number": reference_number.strip(),
        "employer_apply_url": employer_apply_url.strip(),
    }
    _upsert_contact(contact)

    for collection in (raw_jobs, scored_jobs):
        job = _find_job(collection, job_id)
        if not job:
            continue
        job["contact_email"] = contact["email"]
        job["contact_name"] = contact["name"]
        job["contact_role"] = contact["role"]
        job["contact_source"] = source_tag
        job["contact_phone"] = contact["phone"]
        job["contact_note"] = contact["note"]
        job["manual_effort_type"] = "captcha_then_email"
        if employer_apply_url.strip():
            job["url_company"] = employer_apply_url.strip()
        if reference_number.strip():
            job["reference_number"] = reference_number.strip()
        if collection is scored_jobs:
            job.update(classify_job(job))

    _write_json_list(RAW_JOBS_PATH, raw_jobs)
    _write_json_list(SCORED_JOBS_PATH, scored_jobs)


def _find_job(jobs: list[dict], job_id: str) -> dict | None:
    for job in jobs:
        if str(job.get("id") or "").strip() == str(job_id).strip():
            return job
    return None


def _upsert_contact(contact: dict) -> None:
    contacts = _load_json_list(CONTACTS_PATH)
    key = ((contact.get("company") or "").strip().lower(), (contact.get("email") or "").strip().lower())
    updated = False
    for existing in contacts:
        existing_key = (
            (existing.get("company") or "").strip().lower(),
            (existing.get("email") or "").strip().lower(),
        )
        if existing_key != key:
            continue
        existing.update({k: v for k, v in contact.items() if v not in ("", None)})
        updated = True
        break
    if not updated:
        contacts.append(contact)
    _write_json_list(CONTACTS_PATH, contacts)


def _load_json_list(path: str | Path) -> list[dict]:
    file_path = Path(path)
    if not file_path.exists():
        return []
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _write_json_list(path: str | Path, rows: list[dict]) -> None:
    Path(path).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Speichert manuell gelesene CAPTCHA-Kontaktdaten")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default="")
    parser.add_argument("--role", default="")
    parser.add_argument("--phone", default="")
    parser.add_argument("--note", default="")
    parser.add_argument("--employer-apply-url", default="")
    parser.add_argument("--reference-number", default="")
    args = parser.parse_args()

    capture_manual_contact(
        job_id=args.job_id,
        email=args.email,
        name=args.name,
        role=args.role,
        phone=args.phone,
        note=args.note,
        employer_apply_url=args.employer_apply_url,
        reference_number=args.reference_number,
    )
    print(f"manual contact stored for {args.job_id}")


if __name__ == "__main__":
    main()
