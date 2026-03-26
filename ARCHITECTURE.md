# Architecture

Kompakte Uebersicht ueber die aktive Pipeline.

## Diagramm

```mermaid
flowchart LR
    classDef source fill:#eef7f8,stroke:#9ccfd0,color:#18324a,stroke-width:1px;
    classDef process fill:#ffffff,stroke:#cfdde6,color:#18324a,stroke-width:1px;
    classDef store fill:#f7f9fc,stroke:#bfd0dc,color:#18324a,stroke-width:1px;
    classDef ui fill:#f2f8f6,stroke:#abd0c0,color:#18324a,stroke-width:1px;

    subgraph S["Sources"]
        direction TB
        S1["Jobboards"]
        S2["Arbeitsagentur"]
        S3["Firmenseiten"]
        S4["Firmenportale"]
    end

    subgraph I["Ingestion"]
        direction TB
        FJ["find_jobs.py"]
        I1["URL-Normalisierung"]
        I2["Description Enrichment"]
        I3["Best-source Dedupe"]
    end

    subgraph D["Scoring + Learning"]
        direction TB
        SJ["score_jobs.py"]
        D1["Candidate Profile"]
        D2["Retrieval Context"]
        D3["LLM Scoring"]
        D4["feedback_learning.py"]
        D5["ranking_score / feedback_delta"]
    end

    subgraph V["Verification"]
        direction TB
        VJ["verify_jobs.py"]
    end

    subgraph U["Review Workbench"]
        direction TB
        PD["present_dashboard.py"]
        PS["present_server.py<br/>Review Workbench"]
        JA["UI Actions<br/>Unterlagen / Beworben / Freigeben / Reject / Dead Listing"]
        MC["manual_contact_capture.py"]
    end

    subgraph G["Application Generation"]
        direction TB
        GA["generate_application.py"]
    end

    subgraph M["Persistent State"]
        direction TB
        JR["jobs_raw.json"]
        JS["jobs_scored.json"]
        PST["pipeline_state.json"]
        FB["feedback_log.json<br/>feedback_summary.json"]
        AL["apply_log.json"]
        CT["contacts.json"]
        AF["Application Folder<br/>TXT / DOCX / PDF / meta.json"]
        CL["Cover Letters<br/>stable PDF copies"]
    end

    S1 --> FJ
    S2 --> FJ
    S3 --> FJ
    S4 --> FJ

    FJ --> I1 --> I2 --> I3 --> JR

    JR --> SJ
    D1 --> SJ
    D2 --> SJ
    D3 --> SJ
    D4 --> SJ
    SJ --> D5 --> JS

    JR --> VJ
    JS --> VJ
    VJ --> PST

    JR --> PD
    JS --> PD
    PST --> PD
    PD --> PS
    PS --> JA
    JA --> PST
    JA --> AL
    JA --> FB
    FB --> D4

    JA --> GA
    GA --> AF
    GA --> CL

    PS --> MC
    MC --> CT

    class S1,S2,S3,S4 source;
    class FJ,I1,I2,I3,SJ,D1,D2,D3,D4,D5,VJ,GA,JA,MC process;
    class JR,JS,PST,FB,AL,CT,AF,CL store;
    class PD,PS ui;
```

## Lesart

- **Sources** liefern Rohfunde aus Jobboards, Arbeitsagentur und Firmenportalen.
- **Ingestion** normalisiert Links, laedt bessere Detailtexte nach und versucht die beste Quelle pro Stelle zu behalten.
- **Scoring + Learning** kombiniert Kandidatenprofil, Retrieval-Kontext, LLM-Bewertung und Feedback-Signale aus frueheren Entscheidungen.
- **Verification** schreibt operative Zustaende in den Pipeline-State.
- **Review Workbench** ist das Arbeitszentrum fuer menschliche Entscheidungen.
- **Application Generation** wird heute bewusst aus der UI heraus pro Job ausgeloest.

## Kernidee

- Discovery ist breit und opportunistisch.
- Verlaesslichkeit entsteht erst durch Quellenbewertung, Enrichment und Review.
- Die Review-UI ist kein Add-on, sondern das operative Zentrum.
- Vollautomation wurde bewusst zugunsten eines robusteren Human-in-the-loop-Flows reduziert.

## Aktive Module

- `source/find_jobs.py`
- `source/score_jobs.py`
- `source/verify_jobs.py`
- `source/present_dashboard.py`
- `source/present_server.py`
- `source/job_actions.py`
- `source/generate_application.py`
- `source/feedback_learning.py`
- `source/candidate_profile.py`

## Persistente Daten

- `source/jobs_raw.json`
- `source/jobs_scored.json`
- `source/pipeline_state.json`
- `source/apply_log.json`
- `source/feedback_log.json`
- `source/feedback_summary.json`
- `source/contacts.json`
