"""
auto_apply.py
=============
Versendet generierte Bewerbungen auf zwei Wegen:

1. EMAIL   – direkt via SMTP (Gmail / Outlook / eigene Domain)
2. FORMULAR – Selenium-basiertes Ausfüllen von Bewerbungsformularen

WICHTIG: Review-Modus ist standardmäßig AN.
Bei review_mode=True werden keine E-Mails gesendet / keine Formulare abgeschickt.
Erst nach manuellem Freigeben (review_mode=False) läuft alles automatisch.

Abhängigkeiten:
    pip install selenium webdriver-manager
    + Chrome oder Firefox installiert
"""

import json
import time
import logging
import os
import smtplib
import ssl
import base64
from pathlib import Path
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

from ats_handlers import apply_with_ats, detect_ats
from company_url_resolver import resolve_company_apply_url
from env_utils import load_dotenv, env_flag, env_csv
from feedback_store import record_feedback
from job_buckets import classify_job
from pipeline_state_manager import (
    can_proceed_to_apply,
    load_pipeline_state,
    save_pipeline_state,
    update_job_stage,
)
from project_paths import resolve_source_path, source_path

# Microsoft OAuth (optional; only required if SMTP_AUTH_MODE=oauth)
try:
    import msal  # type: ignore
    MSAL_AVAILABLE = True
except ImportError:
    msal = None
    MSAL_AVAILABLE = False

# Selenium (optional – nur für Formular-Bewerbungen nötig)
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

# ─── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


load_dotenv(Path(__file__))


def _get_token_cache():
    if not MSAL_AVAILABLE:
        raise RuntimeError("msal ist nicht installiert. Installiere es oder nutze SMTP_AUTH_MODE=basic.")
    cache = msal.SerializableTokenCache()
    cache_path = Path(os.getenv("MICROSOFT_TOKEN_CACHE_PATH", ".tokens/msal_token_cache.json"))
    if not cache_path.is_absolute():
        cache_path = Path(__file__).resolve().parent.parent / cache_path
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if cache_path.exists():
        cache.deserialize(cache_path.read_text(encoding="utf-8"))
    return cache, cache_path


def _save_token_cache(cache, cache_path: Path) -> None:
    if cache.has_state_changed:
        cache_path.write_text(cache.serialize(), encoding="utf-8")


def _build_xoauth2_string(username: str, access_token: str) -> str:
    raw = f"user={username}\x01auth=Bearer {access_token}\x01\x01"
    return base64.b64encode(raw.encode("utf-8")).decode("ascii")


def _get_microsoft_access_token() -> str:
    if not MSAL_AVAILABLE:
        raise RuntimeError("msal ist nicht installiert. Installiere es oder nutze SMTP_AUTH_MODE=basic.")
    smtp_cfg = CONFIG["smtp"]
    if not smtp_cfg["oauth_client_id"]:
        raise RuntimeError(
            "MICROSOFT_CLIENT_ID fehlt. Registriere eine Public Client App und trage die Client-ID in .env ein."
        )
    cache, cache_path = _get_token_cache()
    authority = f"https://login.microsoftonline.com/{smtp_cfg['oauth_tenant_id']}"

    app = msal.PublicClientApplication(
        client_id=smtp_cfg["oauth_client_id"],
        authority=authority,
        token_cache=cache,
    )

    accounts = app.get_accounts(username=smtp_cfg["user"])
    result = None
    if accounts:
        result = app.acquire_token_silent(smtp_cfg["oauth_scopes"], account=accounts[0])

    if not result:
        flow = app.initiate_device_flow(scopes=smtp_cfg["oauth_scopes"])
        if "user_code" not in flow:
            raise RuntimeError(f"Microsoft Device Flow konnte nicht gestartet werden: {flow}")

        print(flow["message"])
        result = app.acquire_token_by_device_flow(flow)

    _save_token_cache(cache, cache_path)

    if "access_token" not in result:
        raise RuntimeError(f"Microsoft OAuth fehlgeschlagen: {result}")

    return result["access_token"]

# ─── Konfiguration ─────────────────────────────────────────────────────────────
CONFIG = {
    "applications_dir":  os.getenv("APPLICATIONS_DIR", str(source_path("applications"))),
    "log_file":          os.getenv("APPLY_LOG_FILE", str(source_path("apply_log.json"))),

    # ── Review-Modus ──────────────────────────────────────────────────────────
    # True  = nur anzeigen, nichts senden (EMPFOHLEN zum Testen)
    # False = live senden / abschicken
    "review_mode": env_flag("AUTO_APPLY_REVIEW_MODE", True),
    "max_emails_per_run": int(os.getenv("AUTO_APPLY_MAX_EMAILS_PER_RUN", "1")),
    "allowed_job_ids": set(env_csv("AUTO_APPLY_ALLOWED_JOB_IDS")),
    "enable_ats": env_flag("AUTO_APPLY_ENABLE_ATS", False),
    "ats_allowed": set(
        env_csv("AUTO_APPLY_ATS_ALLOWED")
        or ["personio", "greenhouse", "lever", "workable", "successfactors"]
    ),

    # ── E-Mail SMTP ───────────────────────────────────────────────────────────
    "smtp": {
        "host":     os.getenv("SMTP_HOST", "smtp.gmail.com"),
        "port":     int(os.getenv("SMTP_PORT", "465")),
        "use_ssl":  env_flag("SMTP_USE_SSL", True),
        "user":     os.getenv("SMTP_USER", ""),
        "password": os.getenv("SMTP_PASSWORD", ""),
        "auth_mode": os.getenv("SMTP_AUTH_MODE", "basic"),
        "oauth_client_id": os.getenv("MICROSOFT_CLIENT_ID", ""),
        "oauth_tenant_id": os.getenv("MICROSOFT_TENANT_ID", "consumers"),
        "oauth_scopes": [
            scope.strip()
            for scope in os.getenv(
                "MICROSOFT_OAUTH_SCOPES",
                "https://outlook.office.com/SMTP.Send,offline_access,openid,profile",
            ).split(",")
            if scope.strip()
        ],
        # Gmail:   https://myaccount.google.com/apppasswords
        # Outlook: https://account.microsoft.com/security → App-Kennwörter
    },

    # ── Absender ──────────────────────────────────────────────────────────────
    "sender": {
        "name":      os.getenv("SENDER_NAME", "Andreas Eichmann"),
        "email":     os.getenv("SENDER_EMAIL", ""),
        "cv_path":   os.getenv("SENDER_CV_PATH", str(source_path("..", "CVs", "Andreas_Eichmann_CV.pdf"))),
    },

    # ── Selenium ──────────────────────────────────────────────────────────────
    "selenium": {
        "headless":        env_flag("SELENIUM_HEADLESS", False),
        "page_load_wait":  int(os.getenv("SELENIUM_PAGE_LOAD_WAIT", "10")),
        "field_wait":      int(os.getenv("SELENIUM_FIELD_WAIT", "5")),
    },

    "request_delay": float(os.getenv("AUTO_APPLY_REQUEST_DELAY", "2.0")),
}

# ─── Log-Datei ─────────────────────────────────────────────────────────────────

def load_log() -> dict:
    p = resolve_source_path(CONFIG["log_file"])
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def save_log(log_data: dict):
    resolve_source_path(CONFIG["log_file"]).write_text(
        json.dumps(log_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def mark_applied(job_id: str, method: str, status: str, note: str = ""):
    log_data = load_log()
    log_data[job_id] = {
        "method":    method,
        "status":    status,
        "note":      note,
        "timestamp": datetime.now().isoformat(),
    }
    save_log(log_data)
    state = load_pipeline_state()
    state_status = "completed" if status in ("sent", "review", "filled_not_submitted") else "skipped"
    if status == "error":
        state_status = "failed"
    update_job_stage(
        state,
        job_id,
        "apply",
        state_status,
        message=f"{method}:{status}",
        error=note if status == "error" else "",
        extras={"method": method, "apply_status": status},
    )
    save_pipeline_state(state)
    record_feedback(job_id, "apply", status, note)


# ─── E-Mail versenden ──────────────────────────────────────────────────────────

def build_email(to: str, subject: str, body: str, attach_cv: bool = True) -> MIMEMultipart:
    msg = MIMEMultipart()
    msg["From"]    = f"{CONFIG['sender']['name']} <{CONFIG['sender']['email']}>"
    msg["To"]      = to
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain", "utf-8"))

    # CV anhängen
    if attach_cv:
        cv_path = resolve_source_path(CONFIG["sender"]["cv_path"])
        if cv_path.exists():
            with open(cv_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename={cv_path.name}",
            )
            msg.attach(part)
        else:
            log.warning(f"  CV nicht gefunden: {cv_path}")

    return msg


def send_email(to: str, subject: str, body: str, job_id: str, attach_cv: bool = True) -> bool:
    msg = build_email(to, subject, body, attach_cv)

    if CONFIG["review_mode"]:
        log.info(f"  [REVIEW] E-Mail würde gesendet an: {to}")
        log.info(f"  [REVIEW] Betreff: {subject}")
        log.info(f"  [REVIEW] Vorschau:\n{body[:200]}...")
        mark_applied(job_id, "email", "review", f"to={to}")
        return True

    try:
        smtp_cfg = CONFIG["smtp"]
        context  = ssl.create_default_context()

        if smtp_cfg["use_ssl"]:
            with smtplib.SMTP_SSL(smtp_cfg["host"], smtp_cfg["port"], context=context) as server:
                if smtp_cfg["auth_mode"] == "oauth":
                    access_token = _get_microsoft_access_token()
                    auth_string = _build_xoauth2_string(smtp_cfg["user"], access_token)
                    code, response = server.docmd("AUTH", "XOAUTH2 " + auth_string)
                    if code != 235:
                        raise RuntimeError(f"SMTP OAuth fehlgeschlagen: {code} {response}")
                else:
                    server.login(smtp_cfg["user"], smtp_cfg["password"])
                server.sendmail(CONFIG["sender"]["email"], to, msg.as_string())
        else:
            with smtplib.SMTP(smtp_cfg["host"], smtp_cfg["port"]) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                if smtp_cfg["auth_mode"] == "oauth":
                    access_token = _get_microsoft_access_token()
                    auth_string = _build_xoauth2_string(smtp_cfg["user"], access_token)
                    code, response = server.docmd("AUTH", "XOAUTH2 " + auth_string)
                    if code != 235:
                        raise RuntimeError(f"SMTP OAuth fehlgeschlagen: {code} {response}")
                else:
                    server.login(smtp_cfg["user"], smtp_cfg["password"])
                server.sendmail(CONFIG["sender"]["email"], to, msg.as_string())

        log.info(f"  ✓ E-Mail gesendet an {to}")
        mark_applied(job_id, "email", "sent", f"to={to}")
        return True

    except Exception as e:
        log.error(f"  E-Mail Fehler: {e}")
        mark_applied(job_id, "email", "error", str(e))
        return False


# ─── Betreff generieren ────────────────────────────────────────────────────────

def make_subject(job: dict) -> str:
    return f"Bewerbung als {job['title']} – Andreas Eichmann"


# ─── Selenium Formular-Bewerbung ───────────────────────────────────────────────

def get_driver():
    if not SELENIUM_AVAILABLE:
        raise ImportError("Selenium nicht installiert: pip install selenium webdriver-manager")
    options = webdriver.ChromeOptions()
    if CONFIG["selenium"]["headless"]:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options,
    )
    driver.implicitly_wait(CONFIG["selenium"]["field_wait"])
    return driver


def fill_field(driver, selectors: list, value: str):
    """Versucht mehrere CSS/XPath-Selektoren um ein Feld zu finden und auszufüllen."""
    for selector in selectors:
        try:
            if selector.startswith("//"):
                el = driver.find_element(By.XPATH, selector)
            else:
                el = driver.find_element(By.CSS_SELECTOR, selector)
            el.clear()
            el.send_keys(value)
            return True
        except Exception:
            continue
    return False


def upload_file(driver, selectors: list, file_path: str):
    """Datei-Upload in ein input[type=file] Feld."""
    for selector in selectors:
        try:
            el = driver.find_element(By.CSS_SELECTOR, selector)
            el.send_keys(str(Path(file_path).resolve()))
            return True
        except Exception:
            continue
    return False


# Generische Felder die auf den meisten Bewerbungsformularen vorkommen
GENERIC_FORM_FIELDS = {
    "first_name": {
        "value": "Andreas",
        "selectors": [
            "input[name*='first'], input[name*='vorname'], input[id*='first']",
            "//input[@placeholder[contains(.,'Vorname') or contains(.,'First')]]",
        ],
    },
    "last_name": {
        "value": "Eichmann",
        "selectors": [
            "input[name*='last'], input[name*='nachname'], input[id*='last']",
            "//input[@placeholder[contains(.,'Nachname') or contains(.,'Last')]]",
        ],
    },
    "email": {
        "value": CONFIG["sender"]["email"],
        "selectors": [
            "input[type='email'], input[name*='email'], input[id*='email']",
        ],
    },
    "phone": {
        "value": "01763 8663585",
        "selectors": [
            "input[type='tel'], input[name*='phone'], input[name*='telefon']",
        ],
    },
    "city": {
        "value": "München",
        "selectors": [
            "input[name*='city'], input[name*='ort'], input[id*='city']",
        ],
    },
    "linkedin": {
        "value": "https://linkedin.com/in/andreas-eichmann",
        "selectors": [
            "input[name*='linkedin'], input[placeholder*='LinkedIn']",
        ],
    },
    "portfolio": {
        "value": "https://andygitlucky.github.io",
        "selectors": [
            "input[name*='portfolio'], input[name*='website'], input[name*='github']",
        ],
    },
}


def apply_via_form(job: dict, anschreiben: str) -> bool:
    """
    Versucht ein Bewerbungsformular automatisch auszufüllen.
    Funktioniert auf Standard-Formularen (Greenhouse, Lever, Workable, eigene).
    """
    if not SELENIUM_AVAILABLE:
        log.warning("  Selenium nicht verfügbar – Formular-Bewerbung übersprungen")
        return False

    url = job["url"]
    log.info(f"  Öffne: {url}")

    if CONFIG["review_mode"]:
        log.info(f"  [REVIEW] Formular würde ausgefüllt für: {job['title']} @ {job['company']}")
        mark_applied(job["id"], "form", "review", f"url={url}")
        return True

    driver = None
    try:
        driver = get_driver()
        driver.get(url)
        time.sleep(CONFIG["selenium"]["page_load_wait"])

        # Generische Felder ausfüllen
        filled = 0
        for field_name, field_cfg in GENERIC_FORM_FIELDS.items():
            if fill_field(driver, field_cfg["selectors"], field_cfg["value"]):
                filled += 1
                log.info(f"    ✓ Feld: {field_name}")

        # Anschreiben / Cover Letter
        cover_selectors = [
            "textarea[name*='cover'], textarea[name*='anschreiben'], textarea[id*='cover']",
            "//textarea[@placeholder[contains(.,'Cover') or contains(.,'Anschreiben') or contains(.,'Motivation')]]",
        ]
        if fill_field(driver, cover_selectors, anschreiben):
            log.info("    ✓ Anschreiben eingetragen")
            filled += 1

        # CV hochladen
        cv_upload_selectors = [
            "input[type='file'][name*='cv'], input[type='file'][name*='resume']",
            "input[type='file'][accept*='.pdf'], input[type='file'][accept*='.doc']",
        ]
        cv_path = CONFIG["sender"]["cv_path"]
        if Path(cv_path).exists():
            if upload_file(driver, cv_upload_selectors, cv_path):
                log.info("    ✓ CV hochgeladen")
                filled += 1

        log.info(f"    {filled} Felder ausgefüllt")

        # Absenden – ERST nach manuellem Check
        # submit_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        # submit_btn.click()
        # → Auskommentiert: erst nach eigenem Test aktivieren!

        time.sleep(3)
        mark_applied(job["id"], "form", "filled_not_submitted", f"url={url}, fields={filled}")
        log.info("  Formular ausgefüllt – NICHT automatisch abgeschickt (Submit auskommentiert)")
        return True

    except Exception as e:
        log.error(f"  Formular-Fehler: {e}")
        mark_applied(job["id"], "form", "error", str(e))
        return False
    finally:
        if driver:
            time.sleep(2)
            driver.quit()


# ─── Hauptfunktion ─────────────────────────────────────────────────────────────

def auto_apply(applications_dir: str = None) -> dict:
    base_dir  = resolve_source_path(applications_dir or CONFIG["applications_dir"])
    apply_log = load_log()
    pipeline_state = load_pipeline_state()

    if not base_dir.exists():
        log.error(f"applications/ Ordner nicht gefunden. Erst generate_application.py ausführen.")
        return {}

    results = {"sent": [], "review": [], "skipped": [], "errors": [], "manual": []}

    # Optional: load job details for description-based URL extraction.
    jobs_by_id = {}
    scored_path = source_path("jobs_scored.json")
    try:
        if scored_path.exists():
            jobs = json.loads(scored_path.read_text(encoding="utf-8"))
            jobs_by_id = {j.get("id"): j for j in jobs if j.get("id")}
    except Exception:
        jobs_by_id = {}

    app_dirs = sorted(base_dir.iterdir())
    log.info(f"{len(app_dirs)} Bewerbungsordner gefunden")
    if CONFIG["max_emails_per_run"] > 0:
        log.info(f"Mail-Limit pro Lauf: {CONFIG['max_emails_per_run']}")
    if CONFIG["allowed_job_ids"]:
        log.info(f"Job-ID-Whitelist aktiv: {len(CONFIG['allowed_job_ids'])} IDs")
    if CONFIG["enable_ats"]:
        log.info(f"ATS erlaubt: {', '.join(sorted(CONFIG['ats_allowed']))}")

    if CONFIG["review_mode"]:
        log.warning("⚠  REVIEW-MODUS AKTIV – nichts wird wirklich gesendet")

    email_attempts = 0

    for app_dir in app_dirs:
        if not app_dir.is_dir():
            continue

        meta_path        = app_dir / "meta.json"
        anschreiben_path = app_dir / "anschreiben.txt"

        if not meta_path.exists():
            continue

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        job_id = meta["job_id"]

        if not can_proceed_to_apply(pipeline_state, job_id):
            log.info(f"  [SKIP] {meta['company']} - wartet auf Review/Freigabe")
            mark_applied(job_id, "apply_gate", "skipped", "review_pending_or_rejected")
            results["skipped"].append(job_id)
            continue

        if CONFIG["allowed_job_ids"] and job_id not in CONFIG["allowed_job_ids"]:
            log.info(f"  [SKIP] {meta['company']} – nicht in AUTO_APPLY_ALLOWED_JOB_IDS")
            results["skipped"].append(job_id)
            continue

        # Bereits verarbeitet?
        if job_id in apply_log and apply_log[job_id]["status"] in ("sent", "filled_not_submitted"):
            log.info(f"  [SKIP] {meta['company']} – bereits verarbeitet")
            results["skipped"].append(job_id)
            continue

        log.info(f"\n→ {meta['title']} @ {meta['company']}  (Score: {meta['score']}/10)")

        anschreiben = ""
        if anschreiben_path.exists():
            anschreiben = anschreiben_path.read_text(encoding="utf-8")

        # Kontakt aus contacts.json laden (falls vorhanden)
        contact_email = meta.get("contact_email") or load_contact_email(meta["company"])

        if contact_email:
            # ── E-Mail Bewerbung ──────────────────────────────────────────────
            if (
                not CONFIG["review_mode"]
                and CONFIG["max_emails_per_run"] > 0
                and email_attempts >= CONFIG["max_emails_per_run"]
            ):
                log.info("  [SKIP] Mail-Limit für diesen Lauf erreicht")
                results["skipped"].append(job_id)
                continue
            log.info(f"  Methode: E-Mail → {contact_email}")
            subject = make_subject(meta)
            ok = send_email(contact_email, subject, anschreiben, job_id)
            if ok:
                if not CONFIG["review_mode"]:
                    email_attempts += 1
                results["sent" if not CONFIG["review_mode"] else "review"].append(job_id)
            else:
                results["errors"].append(job_id)
        else:
            # ── Formular-Bewerbung ────────────────────────────────────────────
            if not CONFIG["enable_ats"]:
                log.info("  [SKIP] Keine Kontakt-E-Mail und AUTO_APPLY_ENABLE_ATS=false")
                mark_applied(job_id, "form", "skipped", "no_contact_email")
                results["skipped"].append(job_id)
                continue

            original_url = meta.get("url", "")
            job_details = jobs_by_id.get(job_id, {})
            description = job_details.get("description", "") if isinstance(job_details, dict) else ""

            # Cached (falls schon mal resolved / klassifiziert)
            cached_apply_url = (meta.get("url_company") or "").strip()
            cached_ats = (meta.get("ats_type") or "").strip()
            if cached_apply_url and cached_ats:
                resolved = None
                apply_url = cached_apply_url
                ats = cached_ats
                log.info(f"  ATS (cached): {ats} → {apply_url}")
            else:
                pre_ats = detect_ats(original_url)
                if pre_ats in CONFIG["ats_allowed"]:
                    # URL ist bereits ein "echter" ATS-Link (z.B. Greenhouse/Personio/...) – nicht umleiten.
                    resolved = None
                    apply_url = original_url
                    ats = pre_ats
                    log.info(f"  ATS-URL direkt genutzt: {ats} → {apply_url}")
                else:
                    resolved = resolve_company_apply_url(original_url, description=description)
                    apply_url = resolved.url or original_url
                    if resolved.url:
                        log.info(f"  URL-Resolver: {resolved.source} → {apply_url}")
                    ats = detect_ats(apply_url)
                # Cache Resolver-Ergebnis in meta.json, damit Folge-Runs nicht erneut resolven muessen.
                if resolved and resolved.url:
                    meta["url_company"] = apply_url
                    meta["url_company_source"] = resolved.source
                    meta["ats_type"] = ats
                    meta.update(classify_job(meta, CONFIG["ats_allowed"]))
                    try:
                        meta_path.write_text(
                            json.dumps(meta, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                    except Exception:
                        pass
            if ats not in CONFIG["ats_allowed"]:
                log.info(f"  [SKIP] ATS '{ats}' nicht in AUTO_APPLY_ATS_ALLOWED (manual)")
                note = f"manual_ats={ats}"
                if resolved and resolved.url:
                    note += f", url_company={apply_url}"
                mark_applied(job_id, "form", "skipped", note)
                results["manual"].append(
                    {"job_id": job_id, "company": meta.get("company", ""), "title": meta.get("title", ""), "ats": ats, "url": apply_url}
                )
                results["skipped"].append(job_id)
                continue
            log.info(f"  Methode: Formular → {apply_url}")
            cover_path = ""
            for candidate in [
                app_dir / "anschreiben.pdf",
                app_dir / "anschreiben.docx",
            ]:
                if candidate.exists():
                    cover_path = str(candidate)
                    break

            meta2 = dict(meta)
            meta2["url"] = apply_url
            if cover_path:
                meta2["cover_letter_path"] = cover_path
            ok = apply_with_ats(meta2, anschreiben)
            if ok:
                results["sent" if not CONFIG["review_mode"] else "review"].append(job_id)
            else:
                results["errors"].append(job_id)

        time.sleep(CONFIG["request_delay"])

    log.info(f"\n{'─'*50}")
    log.info(f"Gesendet:     {len(results['sent'])}")
    log.info(f"Review:       {len(results['review'])}")
    log.info(f"Übersprungen: {len(results['skipped'])}")
    log.info(f"Fehler:       {len(results['errors'])}")
    if results.get("manual"):
        log.info(f"Manual:       {len(results['manual'])}  (Jobboard/unknown ATS)")
        for m in results["manual"][:10]:
            log.info(f"  [MANUAL] {m.get('company')} | {m.get('title')} | {m.get('ats')} | {m.get('url')}")

    return results


def load_contact_email(company_name: str) -> str:
    """Lädt E-Mail-Adresse aus contacts.json wenn vorhanden."""
    contacts_path = source_path("contacts.json")
    if not contacts_path.exists():
        return ""
    contacts = json.loads(contacts_path.read_text(encoding="utf-8"))
    for c in contacts:
        if (c.get("company", "").lower() == company_name.lower()
                and c.get("email")
                and "guessed" not in c.get("source", "")):
            return c["email"]
    return ""


# ─── Direkt ausführbar ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    results = auto_apply()
    mode = "REVIEW" if CONFIG["review_mode"] else "LIVE"
    print(f"\n✓ auto_apply fertig [{mode}]")
    print(f"  Gesendet/Review: {len(results.get('sent', [])) + len(results.get('review', []))}")
    print(f"  Fehler:          {len(results.get('errors', []))}")
    if CONFIG["review_mode"]:
        print("\n  → review_mode=True: nichts wurde wirklich gesendet.")
        print("  → Zum Aktivieren: CONFIG['review_mode'] = False")
