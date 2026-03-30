# Job Pipeline - Project State

Aktiver Kern heute:

`find_jobs -> score_jobs -> verify_jobs -> Review Workbench`

Das Projekt ist operativ kein Auto-Apply-System mehr. Jobboards dienen vor allem als Discovery-Schicht; die eigentliche Arbeit passiert ueber Quellbewertung, Review, UI-Aktionen und gezielte Unterlagen-Generierung.

## Aktiver Standard-Flow

Ein normaler Lauf ueber `python source/main.py` macht heute standardmaessig:

1. `find_jobs`
2. `score_jobs`
3. `verify_jobs`
4. Dashboard-Erzeugung
5. Start der lokalen Present-UI

Optionale, aber nicht standardmaessige Zusatzpfade:

- `find_contacts.py`
- `generate_application.py` als Batch-Schritt

Unterlagen werden im Alltag bewusst pro Job aus der UI ueber `Unterlagen` erzeugt.

## Kernmodule

- `main.py`: orchestriert den Default-Flow bis zur Review-UI
- `find_jobs.py`: Ingestion, URL-Normalisierung, Description Enrichment, Best-source-Dedupe
- `score_jobs.py`: LLM-Scoring, Decision Preparation, Feedback-Delta, Ranking
- `verify_jobs.py`: prueft Top-Kandidaten auf belastbare Apply-Pfade
- `present_dashboard.py`: rendert die Review-Workbench
- `present_server.py`: lokaler UI-Server
- `job_actions.py`: UI-Aktionen wie `Freigeben`, `Reject`, `Dead Listing`, `Beworben`, `Unterlagen`
- `generate_application.py`: gezielte Unterlagen-Generierung fuer einzelne Jobs oder Batch-Laeufe
- `feedback_store.py`: persistiert Review-/Apply-Feedback
- `feedback_learning.py`: verdichtet Feedback zu Ranking-Signalen
- `pipeline_state_manager.py`: Run-Historie, Queue und Job-State
- `decision_engine.py`: Bucket-/Entscheidungslogik
- `retrieval_context.py`: baut Kandidatenkontext fuer Scoring und Unterlagen
- `vector_store.py`: lokaler semantischer Knowledge-Store
- `build_vector_store.py`: baut oder aktualisiert den lokalen Store
- `verify_jobs.py`: priorisiert echte Bewerbungswege gegenueber Discovery-Links

Archiviert und bewusst nicht mehr Teil des Kernpfads:

- `archive/auto_apply.py`
- `archive/agent_roles.py`
- `archive/cleanup_jobs.py`
- `archive/create_ats_testcase.py`

## State und Artefakte

Wichtige Laufzeitdateien unter `runtime/`:

- `jobs_raw.json`: aktueller Rohbestand pro Run
- `jobs_scored.json`: gescorte Jobs inkl. Bucket, Ranking und persistierten Entscheidungen
- `pipeline_state.json`: Run-Historie, Review-Queue, Job-History
- `feedback_log.json`: einzelne Review-/Apply-Entscheidungen
- `feedback_summary.json`: aggregierte Feedback-Signale
- `apply_log.json`: beworbene Jobs mit Timestamp/Status
- `contacts.json`: manuell oder spaeter wiederverwendbare Kontakte
- `cache/`: Performance-Caches, z. B. fuer BMW-Discovery/Details

Wichtige Beobachtung:

Code, Laufzeitdaten und Artefakte sind jetzt grob getrennt:

- `source/` = Python-Code
- `runtime/` = aktiver Zustand und persistierte Pipeline-Daten
- `artifacts/` = generierte HTML- und Bewerbungsartefakte
- `docs/` = interne technische Doku
- `config/` = quellenbezogene Konfiguration
- `archive/` = archivierte, nicht mehr aktive Altpfade

## Review-Workbench

Die lokale UI unter `http://127.0.0.1:8765` ist heute der operative Mittelpunkt.

Dort koennen Jobs direkt markiert werden als:

- `Beworben`
- `Freigeben`
- `Reject`
- `Dead Listing`
- `Unterlagen`

Wichtige Semantik:

- `Freigeben` bedeutet: Job ist menschlich bestaetigt und wird zu `manual_apply_ready`
- `Beworben` bedeutet: Bewerbung ist raus und der Job verschwindet aus der aktiven Arbeitsliste
- `Reject` oeffnet ein Modal mit strukturierten Ablehnungsgruenden
- `Unterlagen` erzeugt TXT/DOCX/PDF gezielt fuer genau diesen Job

Die UI blendet erledigte oder finale Jobs standardmaessig aus, z. B.:

- `sent` in `apply_log.json`
- `rejected`
- `verified_reject`
- `dead_listing`

## Feedback-Loop

Der Loop ist heute noch leichtgewichtig, aber real:

- UI-Aktionen schreiben strukturiertes Feedback
- Reject-Notizen werden in Kategorien normalisiert
- `feedback_summary.json` verdichtet Muster
- `score_jobs.py` berechnet daraus `feedback_delta` und `ranking_score`

Das System lernt also noch nicht hart oder autonom, aber es priorisiert spaetere Runs bereits leicht anders auf Basis menschlicher Entscheidungen.

## Quellenlogik

Die wichtigste Produktannahme heute:

- Jobboards = Discovery
- Firmenportal / ATS / captcha-gatete Firmenpfade = operativ wertvoll

Typische Linktypen:

- `company_detail`
- `captcha_then_company_apply`
- `manual_contact_gate`
- `jobboard_redirect`
- `discovery_only`

Konsequenz:

- kaputte Jobboard-Links bedeuten nicht automatisch `dead_listing`
- Discovery und Primaerquelle muessen bewusst getrennt werden
- Best-source-Dedupe ist zentral

## Optional genutzte Zusatzmodule

Diese Module sind noch im Projekt und koennen sinnvoll sein, gehoeren aber nicht zum taeglichen Kernpfad:

- `find_contacts.py`
- `contact_linker.py`
- `pipeline_report.py`
- `retrieval_smoke.py`

## Typische Checks

```powershell
.\.venv\Scripts\python.exe -m unittest discover tests
.\.venv\Scripts\python.exe -m compileall source
.\.venv\Scripts\python.exe source\main.py
```

## Naechste sinnvolle Verbesserungen

- Discovery-only-Quellen haerter aus Top-Ansichten herausdruecken
- semantische Dedupe-Stufe fuer Grenzfaelle spaeter pruefen
- langsame Firmenquellen wie BMW weiter optimieren
