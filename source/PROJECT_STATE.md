# Jobsuche Pipeline - Project State

Automatisierter Jobsuche-Prozess: Scraping -> Scoring -> Kontakte -> Anschreiben -> Versand.

## Was jetzt neu ist

- Expliziter Job-State in `pipeline_state.json`
- Entscheidungen pro Job: `apply`, `review`, `reject`
- Review-Queue mit manueller Freigabe ueber `review_pipeline.py`
- Feedback-Log in `feedback_log.json`
- Kontakt-Rueckverknuepfung von `contacts.json` nach `jobs_scored.json`
- Kleiner Report ueber `pipeline_report.py`

## Kernmodule

- `main.py`: Orchestrator
- `find_jobs.py`: Ingestion Layer
- `score_jobs.py`: Scoring + Decision Preparation
- `find_contacts.py`: Kontakt-Suche
- `contact_linker.py`: mappt Kontakte auf Jobs
- `generate_application.py`: Application Generation
- `archive/auto_apply.py`: archivierte Auto-Apply-Experimente
- `review_pipeline.py`: manuelle Review-Entscheidungen
- `pipeline_state_manager.py`: aktives State-Tracking
- `feedback_store.py`: speichert Review-/Apply-Feedback
- `decision_engine.py`: explizite Entscheidungslogik
- `retrieval_context.py`: Retrieval-Vorstufe
- `vector_store.py`: lokaler semantischer Knowledge-Store
- `build_vector_store.py`: baut/aktualisiert den lokalen Vector-Store
- `archive/agent_roles.py`: archivierte Rollenabgrenzung aus frueheren Agent-Experimenten
- `pipeline_report.py`: kompakte Observability-Ausgabe
- `verify_jobs.py`: prueft Top-Kandidaten auf echte Apply-Pfade

## State-Modell

`pipeline_state.json` enthaelt:

- `runs`
- `review_queue`
- `jobs.<job_id>.current_stage`
- `jobs.<job_id>.stage_status`
- `jobs.<job_id>.decision`
- `jobs.<job_id>.review_status`
- `jobs.<job_id>.retry_count`
- `jobs.<job_id>.artifacts`
- `jobs.<job_id>.history`

## Review-Workflow

Pending Review anzeigen:

```bash
python review_pipeline.py --list
```

Job freigeben:

```bash
python review_pipeline.py --job-id <ID> --action approve --note "passt trotz Risiko"
```

Job ablehnen:

```bash
python review_pipeline.py --job-id <ID> --action reject --note "zu senior"
```

`archive/auto_apply.py` ist nicht mehr Teil des Standard-Flows.

Die Present-UI blendet ausserdem Jobs standardmaessig aus, die
- bereits erfolgreich verschickt wurden (`apply_log.json`, z. B. `sent`)
- oder final auf `rejected` / `verified_reject` / `dead_listing` stehen

So tauchen erledigte oder abgelehnte Stellen nicht dauernd wieder in der Arbeitsliste auf.

## Lokale Present-UI mit Aktionen

Neben der statischen HTML-Datei gibt es jetzt auch einen kleinen lokalen Server:

```bash
python source/present_server.py
```

Danach ist die UI unter `http://127.0.0.1:8765` erreichbar.

Dort koennen Jobs direkt markiert werden als:
- `Beworben`
- `Verify Ready`
- `Reject`
- `Dead Listing`

Die Buttons schreiben den Status direkt in die bestehenden JSON-Dateien zurueck.

## Monitoring und Tests

Report:

```bash
python pipeline_report.py
```

Tests:

```bash
python -m unittest discover tests
```

Semantischen Store bauen:

```bash
python build_vector_store.py
```

Ohne konfigurierten Embedding-Provider faellt der Store automatisch auf lokale Snippets ohne Vektoren zurueck.

Retrieval schnell pruefen:

```bash
python retrieval_smoke.py --mode application
python retrieval_smoke.py --mode market_discovery
```

`application` priorisiert konkrete Bewerbungs-Evidenz.
`market_discovery` darf breiter denken und auch angrenzende Rollen/Fallback-Signale einbeziehen.

Generierte Anschreiben und Outreach-Texte laufen zusaetzlich durch Guardrails gegen
negative Selbstauskunft wie fehlender Hochschulabschluss, "nur Weiterbildung"
oder "nicht klassischer Werdegang".

OpenRouter-Embeddings aktivieren:

```bash
EMBEDDING_ENABLED=true
EMBEDDING_PROVIDER=openrouter
EMBEDDING_MODEL=openai/text-embedding-3-small
```

Danach den Store neu bauen:

```bash
python build_vector_store.py
```

## Primaerquellen statt nur Jobboards

Der aktuelle Markt zeigt klar:
- Jobboards sind gut fuer Discovery
- echte ATS-/Karriereseiten sind besser fuer `job_description + apply_url`

`find_jobs.py` kann deshalb zusaetzlich Primaerquellen laden:
- Greenhouse Job Board API
- Lever Postings API

Konfiguration:

1. `source/primary_sources.example.json` nach `source/primary_sources.json` kopieren
2. passende Boards eintragen

Beispiel:

```json
[
  {
    "type": "greenhouse",
    "company": "Example Greenhouse Company",
    "board_token": "example-company",
    "location": "Munich"
  },
  {
    "type": "lever",
    "company": "Example Lever Company",
    "site": "example-company",
    "location": "Munich"
  }
]
```

Die Jobs aus diesen Quellen kommen bereits mit direkter ATS-/Apply-URL in die Pipeline
und sind daher deutlich wertvoller als reine Jobboard-Funde.

Neue Primaerquellen werden zusaetzlich automatisch gelernt, wenn im Run eine
echte ATS-Quelle gefunden wird oder du in `review_pipeline.py` manuell
`verify-ready` setzt.

Aktuell werden dabei konservativ nur klar erkennbare Primaerquellen uebernommen:
- Greenhouse
- Lever
- Recruitee

## Firmen-Karriereportale mit Suchfeld

Neben festen ATS-Boards gibt es Firmenportale, bei denen die Suchbegriffe direkt
in ein Suchfeld eingegeben werden muessen, z. B. Siemens Energy oder SWM.

Dafuer gibt es:
- `source/company_search_sources.example.json`
- `source/company_search_sources.json`

Diese Quellen sind getrennt von `primary_sources.json`, weil sie keine festen
Board-APIs sind, sondern interaktive Karriereportale.

Fuer SWM, Siemens Energy, Infineon und BMW Group gibt es bereits erste funktionierende Portal-Fetcher.
Die Datei kann ausserdem als priorisierte Firmenliste genutzt werden, z. B. mit:
- `priority`
- `status`
- `implemented`
- `notes`

So koennen bereits interessante Firmen mit offizieller Karriereseite aufgenommen
werden, auch wenn ihr spezifischer Fetcher noch nicht implementiert ist.
Nicht implementierte oder vorerst pausierte Firmen koennen in derselben Liste
stehen, ohne die Runs zuzuspammen:
- `status=active` + `implemented=true` -> wird im Run durchsucht
- `status=planned` -> bleibt als Kandidat in der Liste, wird aber nicht ausgefuehrt
- `status=paused` oder `status=rejected` -> dokumentiert, aber nicht aktiv

Dabei werden Treffer aus den jeweiligen Firmen-Listen gezogen, gegen die
Suchbegriffe gefiltert und die Detailseiten fuer die Beschreibung nachgeladen.

OpenAI direkt geht weiterhin auch:

```bash
EMBEDDING_ENABLED=true
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=sk-proj-...
EMBEDDING_MODEL=text-embedding-3-small
```

## Noch offen

- spaetere Migration auf einen Graph-Orchestrator
- weitere Verfeinerung von Retrieval-Qualitaet, Quellenabdeckung und Human-in-the-loop-Workflows
