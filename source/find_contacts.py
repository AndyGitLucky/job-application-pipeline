"""
find_contacts.py
================
Sucht Hiring Manager / Head of Data / ML Lead Kontakte für Firmen
aus der Company List. Kombiniert mehrere Quellen:

1. Hunter.io API       – E-Mail-Suche nach Domain (kostenlos: 25/Monat)
2. LinkedIn via Google – Öffentliche Profile via Google-Suche
3. Company Website     – Impressum / About / Team Seiten
4. Clearbit API        – Firmendaten + Kontakte (kostenlos Tier)

Ausgabe: contacts.json + contacts.csv

Abhängigkeiten:
    pip install requests beautifulsoup4 lxml
"""

import json
import time
import logging
import re
import csv
from pathlib import Path
from urllib.parse import quote, urlparse

import requests
from bs4 import BeautifulSoup
if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from source.project_paths import resolve_runtime_path, runtime_path

# ─── Logging ───────────────────────────────────────────────────────────────────
log = logging.getLogger(__name__)

# ─── Konfiguration ─────────────────────────────────────────────────────────────
CONFIG = {
    "output_json":       str(runtime_path("contacts.json")),
    "output_csv":        str(runtime_path("contacts.csv")),
    "request_delay":     2.0,
    "hunter_api_key":    "",   # https://hunter.io → kostenlos registrieren (25 Suchen/Monat)
    "headers": {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )
    },
}

# ─── Zielrollen (Priorität absteigend) ────────────────────────────────────────
TARGET_ROLES = [
    "Head of Data",
    "Head of AI",
    "ML Lead",
    "Director of Engineering",
    "VP Engineering",
    "Chief Technology Officer",
    "CTO",
    "Data Science Lead",
    "Head of Machine Learning",
    "Hiring Manager",
    "Talent Acquisition",
    "Recruiter",
]

# ─── Firmenliste ───────────────────────────────────────────────────────────────
# Aus der Company List – hier ergänzen / anpassen
COMPANIES = [
    {"name": "KONUX",           "domain": "konux.com",          "website": "https://www.konux.com",           "tier": "A"},
    {"name": "TWAICE",          "domain": "twaice.com",         "website": "https://twaice.com",              "tier": "A"},
    {"name": "Blickfeld",       "domain": "blickfeld.com",      "website": "https://www.blickfeld.com",       "tier": "A"},
    {"name": "ImFusion",        "domain": "imfusion.com",       "website": "https://www.imfusion.com",        "tier": "A"},
    {"name": "Tensoreye",       "domain": "tensoreye.de",       "website": "https://www.tensoreye.de",        "tier": "A"},
    {"name": "Celonis",         "domain": "celonis.com",        "website": "https://www.celonis.com",         "tier": "A"},
    {"name": "Smartlane",       "domain": "smartlane.de",       "website": "https://www.smartlane.de",        "tier": "B"},
    {"name": "Kaia Health",     "domain": "kaiahealth.com",     "website": "https://www.kaiahealth.com",      "tier": "B"},
    {"name": "OroraTech",       "domain": "ororatech.com",      "website": "https://www.ororatech.com",       "tier": "B"},
    {"name": "Caresyntax",      "domain": "caresyntax.com",     "website": "https://www.caresyntax.com",      "tier": "B"},
    {"name": "ZenML",           "domain": "zenml.io",           "website": "https://www.zenml.io",            "tier": "B"},
    {"name": "CONXAI",          "domain": "conxai.com",         "website": "https://www.conxai.com",          "tier": "B"},
]


def load_companies_from_jobs(jobs_path: str | Path = runtime_path("jobs_scored.json")) -> list[dict]:
    path = resolve_runtime_path(jobs_path)
    if not path.exists():
        return []
    jobs = json.loads(path.read_text(encoding="utf-8"))
    companies = {}
    for job in jobs:
        company_name = (job.get("company") or "").strip()
        if not company_name:
            continue
        website = job.get("url", "")
        host = urlparse(website).netloc.lower().replace("www.", "")
        if host.startswith("jobs."):
            host = host[5:]
        companies.setdefault(
            company_name.lower(),
            {
                "name": company_name,
                "domain": host,
                "website": f"https://{host}" if host else website,
                "tier": "J",
            },
        )
    return list(companies.values())

# ─── Hilfsfunktionen ───────────────────────────────────────────────────────────

def extract_emails_from_text(text: str) -> list:
    """Findet alle E-Mail-Adressen in einem Text."""
    pattern = r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
    emails = re.findall(pattern, text)
    # Generische Adressen filtern
    skip = {"info@", "contact@", "hello@", "support@", "noreply@", "jobs@",
            "office@", "mail@", "admin@", "press@", "privacy@"}
    return [e for e in emails if not any(e.lower().startswith(s) for s in skip)]


def make_contact(name, role, email, company, source, confidence=None, linkedin=None):
    return {
        "name":       name.strip() if name else "",
        "role":       role.strip() if role else "",
        "email":      email.strip().lower() if email else "",
        "company":    company,
        "source":     source,
        "confidence": confidence,
        "linkedin":   linkedin or "",
        "outreach_sent": False,
        "replied":    False,
    }


# ─── Source 1: Hunter.io API ───────────────────────────────────────────────────

def fetch_hunter(company: dict) -> list:
    """
    Hunter.io Domain Search – findet alle bekannten E-Mails einer Domain.
    Kostenlos: 25 Suchen/Monat. API-Key unter https://hunter.io/api-keys
    """
    if not CONFIG["hunter_api_key"]:
        log.debug("  Hunter.io: kein API-Key, überspringe")
        return []

    url = "https://api.hunter.io/v2/domain-search"
    params = {
        "domain":  company["domain"],
        "api_key": CONFIG["hunter_api_key"],
        "limit":   10,
        "type":    "personal",
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json().get("data", {})
        contacts = []
        for person in data.get("emails", []):
            role = person.get("position", "")
            # Nur relevante Rollen
            if not any(t.lower() in role.lower() for t in
                       ["data", "ml", "engineer", "tech", "ai", "recruit", "talent", "cto", "vp"]):
                continue
            contacts.append(make_contact(
                name=f"{person.get('first_name','')} {person.get('last_name','')}".strip(),
                role=role,
                email=person.get("value", ""),
                company=company["name"],
                source="hunter.io",
                confidence=person.get("confidence"),
                linkedin=person.get("linkedin", ""),
            ))
        log.info(f"  Hunter.io: {len(contacts)} relevante Kontakte")
        return contacts
    except Exception as e:
        log.warning(f"  Hunter.io Fehler: {e}")
        return []


# ─── Source 2: Google-Suche nach LinkedIn-Profilen ────────────────────────────

def fetch_linkedin_via_google(company: dict) -> list:
    """
    Sucht LinkedIn-Profile via Google.
    Kein LinkedIn-Login nötig – nur öffentliche Ergebnisse.
    Gibt Namen + LinkedIn-URL zurück (keine E-Mails direkt).
    """
    contacts = []
    for role in TARGET_ROLES[:5]:  # Nur Top-5 Rollen um nicht zu viele Requests zu machen
        query = f'site:linkedin.com/in "{company["name"]}" "{role}"'
        url   = f"https://www.google.com/search?q={quote(query)}&num=5"
        try:
            r = requests.get(url, headers=CONFIG["headers"], timeout=10)
            soup = BeautifulSoup(r.text, "lxml")

            for result in soup.select("div.g")[:3]:
                link_el = result.select_one("a[href]")
                title_el = result.select_one("h3")
                if not (link_el and title_el):
                    continue
                href = link_el["href"]
                if "linkedin.com/in/" not in href:
                    continue
                title = title_el.get_text()
                # Name aus Titel extrahieren (Format: "Vorname Nachname - Rolle - Firma | LinkedIn")
                name = title.split(" - ")[0].strip() if " - " in title else title
                contacts.append(make_contact(
                    name=name,
                    role=role,
                    email="",   # Keine E-Mail aus LinkedIn öffentlich
                    company=company["name"],
                    source="linkedin_google",
                    linkedin=href,
                ))
            time.sleep(CONFIG["request_delay"])
        except Exception as e:
            log.warning(f"  Google/LinkedIn Fehler ({role}): {e}")

    log.info(f"  LinkedIn via Google: {len(contacts)} Profile")
    return contacts


# ─── Source 3: Company Website (Team / About / Impressum) ─────────────────────

TEAM_PAGE_PATHS = [
    "/team", "/about", "/about-us", "/company", "/people",
    "/uber-uns", "/karriere", "/jobs",
]

def fetch_from_website(company: dict) -> list:
    """Scrapt Team-Seiten der Firmenseite nach Namen und E-Mails."""
    contacts = []
    base = company["website"].rstrip("/")

    pages_to_check = [base] + [base + p for p in TEAM_PAGE_PATHS]

    for page_url in pages_to_check:
        try:
            r = requests.get(page_url, headers=CONFIG["headers"], timeout=8)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "lxml")
            text = soup.get_text(separator=" ")

            # E-Mails direkt im Text
            emails = extract_emails_from_text(text)
            for email in emails:
                contacts.append(make_contact(
                    name="",
                    role="",
                    email=email,
                    company=company["name"],
                    source=f"website:{page_url}",
                ))

            # Namen aus Team-Sektionen extrahieren
            for el in soup.select("[class*='team'], [class*='Team'], [class*='people'], [class*='staff']"):
                # Suche nach Name + Rolle Kombinationen
                name_el = el.select_one("h3, h4, strong, [class*='name']")
                role_el = el.select_one("p, span, [class*='role'], [class*='title'], [class*='position']")
                if name_el:
                    name = name_el.get_text().strip()
                    role = role_el.get_text().strip() if role_el else ""
                    if (len(name) > 3 and
                        any(t.lower() in role.lower() for t in
                            ["data", "ml", "engineer", "tech", "ai", "cto", "head", "lead", "director"])):
                        contacts.append(make_contact(
                            name=name,
                            role=role,
                            email="",
                            company=company["name"],
                            source=f"website_team:{page_url}",
                        ))

            if emails or contacts:
                break  # Gefunden – nicht weiter scrapen
            time.sleep(0.5)

        except Exception:
            continue

    log.info(f"  Website: {len(contacts)} Kontakte/E-Mails")
    return contacts


# ─── Source 4: E-Mail-Muster raten (wenn Name bekannt) ────────────────────────

EMAIL_PATTERNS = [
    "{first}.{last}@{domain}",
    "{first}@{domain}",
    "{f}{last}@{domain}",
    "{first}{last}@{domain}",
]

def guess_email(first: str, last: str, domain: str) -> list:
    """Generiert mögliche E-Mail-Adressen basierend auf gängigen Mustern."""
    first = first.lower().strip()
    last  = last.lower().strip()
    f     = first[0] if first else ""
    return [
        p.format(first=first, last=last, f=f, domain=domain)
        for p in EMAIL_PATTERNS
    ]


def enrich_with_guessed_emails(contacts: list, domain: str) -> list:
    """
    Ergänzt Kontakte ohne E-Mail mit generierten E-Mail-Kandidaten.
    Diese müssen noch verifiziert werden (z.B. via Hunter.io Email Verifier).
    """
    enriched = []
    for c in contacts:
        if c["email"] or not c["name"]:
            enriched.append(c)
            continue
        parts = c["name"].split()
        if len(parts) >= 2:
            guesses = guess_email(parts[0], parts[-1], domain)
            c["email_guesses"] = guesses
            c["email"] = guesses[0]  # Häufigster Pattern als Primär
            c["source"] += "+guessed_email"
        enriched.append(c)
    return enriched


# ─── Deduplizierung ────────────────────────────────────────────────────────────

def deduplicate_contacts(contacts: list) -> list:
    seen_emails = set()
    seen_names  = set()
    unique = []
    for c in contacts:
        key_email = c["email"].lower() if c["email"] else None
        key_name  = c["name"].lower()  if c["name"]  else None
        if key_email and key_email in seen_emails:
            continue
        if key_name and key_name in seen_names and not c["email"]:
            continue
        if key_email:
            seen_emails.add(key_email)
        if key_name:
            seen_names.add(key_name)
        unique.append(c)
    return unique


# ─── Hauptfunktion ─────────────────────────────────────────────────────────────

def find_contacts(companies: list = None) -> list:
    companies = companies or (load_companies_from_jobs() or COMPANIES)
    all_contacts = []

    for company in companies:
        log.info(f"\n[{company['tier']}] {company['name']} ({company['domain']})")

        contacts = []
        contacts += fetch_hunter(company)
        time.sleep(CONFIG["request_delay"])

        contacts += fetch_linkedin_via_google(company)
        time.sleep(CONFIG["request_delay"])

        contacts += fetch_from_website(company)
        time.sleep(CONFIG["request_delay"])

        # E-Mails für Kontakte ohne E-Mail schätzen
        contacts = enrich_with_guessed_emails(contacts, company["domain"])
        contacts = deduplicate_contacts(contacts)

        log.info(f"  ─ Gesamt: {len(contacts)} Kontakte für {company['name']}")
        all_contacts.extend(contacts)

    # Global deduplizieren
    all_contacts = deduplicate_contacts(all_contacts)

    # JSON speichern
    resolve_runtime_path(CONFIG["output_json"]).write_text(
        json.dumps(all_contacts, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # CSV speichern (für Excel / Tracker)
    with open(resolve_runtime_path(CONFIG["output_csv"]), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "name", "role", "email", "company", "source",
            "confidence", "linkedin", "outreach_sent", "replied"
        ])
        writer.writeheader()
        for c in all_contacts:
            writer.writerow({k: c.get(k, "") for k in writer.fieldnames})

    log.info(f"\n{'─'*50}")
    log.info(f"Gesamt: {len(all_contacts)} Kontakte")
    log.info(f"Mit E-Mail: {sum(1 for c in all_contacts if c['email'])}")
    log.info(f"Nur LinkedIn: {sum(1 for c in all_contacts if c['linkedin'] and not c['email'])}")
    log.info(f"Gespeichert: {CONFIG['output_json']} + {CONFIG['output_csv']}")

    return all_contacts


# ─── Direkt ausführbar ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    contacts = find_contacts()
    print(f"\n✓ {len(contacts)} Kontakte gefunden.")
    print("\nErste 5:")
    for c in contacts[:5]:
        print(f"  {c['name']:<25} {c['role']:<30} {c['email']:<35} [{c['source']}]")
