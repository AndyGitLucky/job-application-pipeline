"""
create_ats_testcase.py
======================
Erzeugt einen einzelnen Test-Bewerbungsordner unter ./applications/, damit man
den ATS-Flow gezielt mit genau 1 URL testen kann (ohne die normale Pipeline).

Nutzung (aus dem source/ Ordner):
  $env:ATS_TEST_URL="https://company.jobs.personio.de/job/12345"
  $env:ATS_TEST_COMPANY="Beispiel GmbH"
  $env:ATS_TEST_TITLE="Data Scientist (m/w/d)"
  $env:ATS_TEST_JOB_ID="ats_test_001"   # optional
  python create_ats_testcase.py

Danach:
  In .env setzen:
    AUTO_APPLY_REVIEW_MODE=true
    AUTO_APPLY_ENABLE_ATS=true
    AUTO_APPLY_ALLOWED_JOB_IDS=<ATS_TEST_JOB_ID>
  und dann:
    python archive/auto_apply.py
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path

from docx import Document
from docx2pdf import convert as docx2pdf_convert


def _slug(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"[^\w\-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_-")
    return text[:60] or "unbekannt"


def main() -> None:
    url = (os.getenv("ATS_TEST_URL") or "").strip()
    if not url:
        raise SystemExit("ATS_TEST_URL fehlt.")

    company = (os.getenv("ATS_TEST_COMPANY") or "ATS Test").strip()
    title = (os.getenv("ATS_TEST_TITLE") or "ATS Bewerbungstest").strip()
    job_id = (os.getenv("ATS_TEST_JOB_ID") or f"ats_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}").strip()

    base_dir = Path("applications")
    base_dir.mkdir(parents=True, exist_ok=True)

    folder = base_dir / f"{_slug(company)}_{job_id}"
    folder.mkdir(parents=True, exist_ok=True)

    meta = {
        "job_id": job_id,
        "title": title,
        "company": company,
        "url": url,
        "score": 10,
        "generated": datetime.now().isoformat(),
        "note": "ATS testcase (manual URL)",
    }
    (folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    anschreiben = (
        "Dies ist ein ATS-Testlauf im REVIEW-Modus.\n\n"
        "Bitte nichts absenden. Ziel: Felder, Uploads und Pflichtangaben pruefen.\n"
    )
    (folder / "anschreiben.txt").write_text(anschreiben, encoding="utf-8")

    # Optional: Erzeuge eine echte Datei fuer Upload-Felder (DOCX + PDF wenn moeglich).
    docx_path = folder / "anschreiben.docx"
    pdf_path = folder / "anschreiben.pdf"
    try:
        doc = Document()
        for para in anschreiben.split("\n\n"):
            doc.add_paragraph(para)
        doc.save(str(docx_path))
        try:
            docx2pdf_convert(str(docx_path.resolve()), str(pdf_path.resolve()))
        except Exception:
            pass
    except Exception:
        pass

    print(f"OK: erstellt {folder}")
    print(f"job_id: {job_id}")


if __name__ == "__main__":
    main()
