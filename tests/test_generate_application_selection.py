import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from source import generate_application as ga


class GenerateApplicationSelectionTests(unittest.TestCase):
    def test_clean_cover_letter_body_removes_subject_and_salutation_boilerplate(self):
        text = (
            "Betreff: Bewerbung als AI Forward Deployed Engineer (m/w/d)\n\n"
            "Sehr geehrtes CANCOM-Team,\n\n"
            "Ich bringe relevante Erfahrung mit.\n\n"
            "- Punkt eins\n- Punkt zwei"
        )

        cleaned = ga.clean_cover_letter_body(text)

        self.assertNotIn("Betreff:", cleaned)
        self.assertNotIn("Sehr geehrtes", cleaned)
        self.assertTrue(cleaned.startswith("Ich bringe relevante Erfahrung mit."))

    def test_clean_cover_letter_body_removes_title_like_heading(self):
        text = (
            "Bewerbung als AI Forward Deployed Engineer bei CANCOM SE\n\n"
            "CANCOM gestaltet IT-Lösungen mit echtem Mehrwert."
        )

        cleaned = ga.clean_cover_letter_body(text)

        self.assertNotIn("Bewerbung als AI Forward Deployed Engineer", cleaned)
        self.assertEqual(cleaned, "CANCOM gestaltet IT-Lösungen mit echtem Mehrwert.")

    def test_cover_letter_pdf_path_uses_central_directory_and_stable_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            original_dir = ga.CONFIG["cover_letter_dir"]
            ga.CONFIG["cover_letter_dir"] = str(Path(tmp) / "Cover Letters")
            try:
                pdf_path = ga.make_cover_letter_pdf_path({"company": "IBM Client Innovation Center Germany GmbH"})
            finally:
                ga.CONFIG["cover_letter_dir"] = original_dir

            self.assertIn("Cover Letters", str(pdf_path))
            self.assertTrue(pdf_path.name.startswith("Andreas_Eichmann_CL_"))
            self.assertTrue(pdf_path.name.endswith(".pdf"))

    def test_only_apply_jobs_are_generated_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            jobs_path = tmp_path / "jobs_scored.json"
            output_dir = tmp_path / "applications"
            cover_dir = tmp_path / "Cover Letters"
            jobs = [
                {
                    "id": "apply1",
                    "title": "Apply Job",
                    "company": "Demo",
                    "url": "https://example.com/apply",
                    "description": "Strong fit",
                    "recommended": True,
                    "score": 8,
                    "decision": "apply",
                    "final_bucket": "manual_apply_ready",
                    "job_status": "live",
                },
                {
                    "id": "review1",
                    "title": "Review Job",
                    "company": "Demo",
                    "url": "https://example.com/review",
                    "description": "Needs review",
                    "recommended": True,
                    "score": 7,
                    "decision": "review",
                    "final_bucket": "needs_review",
                    "job_status": "live",
                },
            ]
            jobs_path.write_text(json.dumps(jobs), encoding="utf-8")

            original_call_llm = ga.call_llm
            original_pdf = ga.save_docx_as_pdf
            original_output_dir = ga.CONFIG["output_dir"]
            original_cover_dir = ga.CONFIG["cover_letter_dir"]
            try:
                ga.CONFIG["output_dir"] = str(output_dir)
                ga.CONFIG["cover_letter_dir"] = str(cover_dir)
                ga.call_llm = lambda prompt, quality=False: "Testtext"
                ga.save_docx_as_pdf = lambda docx_path, pdf_path: pdf_path.write_text("pdf", encoding="utf-8")
                generated = ga.generate_applications(str(jobs_path), limit=10)
            finally:
                ga.call_llm = original_call_llm
                ga.save_docx_as_pdf = original_pdf
                ga.CONFIG["output_dir"] = original_output_dir
                ga.CONFIG["cover_letter_dir"] = original_cover_dir

            generated_ids = {job["id"] for job in generated}
            self.assertEqual(generated_ids, {"apply1"})

    def test_generation_keeps_central_pdf_and_local_anschreiben_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            jobs_path = tmp_path / "jobs_scored.json"
            output_dir = tmp_path / "applications"
            cover_dir = tmp_path / "Cover Letters"
            jobs = [
                {
                    "id": "apply1",
                    "title": "Apply Job",
                    "company": "BMW AG",
                    "url": "https://example.com/apply",
                    "description": "Strong fit",
                    "recommended": True,
                    "score": 8,
                    "decision": "apply",
                    "final_bucket": "manual_apply_ready",
                    "job_status": "live",
                }
            ]
            jobs_path.write_text(json.dumps(jobs), encoding="utf-8")

            original_call_llm = ga.call_llm
            original_pdf = ga.save_docx_as_pdf
            original_output_dir = ga.CONFIG["output_dir"]
            original_cover_dir = ga.CONFIG["cover_letter_dir"]
            try:
                ga.CONFIG["output_dir"] = str(output_dir)
                ga.CONFIG["cover_letter_dir"] = str(cover_dir)
                ga.call_llm = lambda prompt, quality=False: "Testtext"
                ga.save_docx_as_pdf = lambda docx_path, pdf_path: pdf_path.write_text("pdf", encoding="utf-8")
                generated = ga.generate_applications(str(jobs_path), limit=10)
            finally:
                ga.call_llm = original_call_llm
                ga.save_docx_as_pdf = original_pdf
                ga.CONFIG["output_dir"] = original_output_dir
                ga.CONFIG["cover_letter_dir"] = original_cover_dir

            self.assertEqual(len(generated), 1)
            generated_job = generated[0]
            central_pdf = Path(generated_job["cover_letter_pdf"])
            local_pdf = Path(generated_job["cover_letter_pdf_local"])

            self.assertTrue(central_pdf.exists())
            self.assertTrue(local_pdf.exists())
            self.assertEqual(local_pdf.name, "anschreiben.pdf")
            self.assertIn("Cover Letters", str(central_pdf))


if __name__ == "__main__":
    unittest.main()
