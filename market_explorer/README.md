# Market Explorer

Dieses Subprojekt ist eine getrennte Arbeitsflaeche fuer eine visuelle, interaktive Repraesentation des Arbeitsmarkts.

Es gehoert bewusst **nicht** zum operativen Bewerbungs-Workflow unter `source/`, kann aber spaeter vorhandene Logik aus dem Hauptprojekt wiederverwenden, zum Beispiel:

- Quellenbewertung
- URL-Normalisierung
- Dedupe
- Rollen- und Semantik-Bausteine
- Description Enrichment

## Produktidee

Ziel ist ein **Job Market Atlas**:

- grosse Mengen an Stellenanzeigen sammeln
- Rohdaten deduplizieren und normalisieren
- Rollen, Regionen, Firmen und Skills aggregieren
- daraus visuelle Insights erzeugen

Das Projekt soll den Arbeitsmarkt nicht als Liste einzelner Jobs zeigen, sondern als explorierbare Struktur:

- Wo wird eingestellt?
- Welche Rollen dominieren?
- Welche Skills clustern zusammen?
- Welche Firmen treiben Nachfrage?
- Wie veraendert sich das ueber die Zeit?

## V1 Scope

Die erste Version soll bewusst kleiner und belastbar sein.

Empfohlener Scope:

- Deutschland
- Fokus auf Tech / Data / AI / Engineering
- deduplizierte Online-Stellenanzeigen
- interaktive Exploration statt perfekter Vollabdeckung

## Abgrenzung zum Hauptprojekt

`source/`
- persoenlicher Bewerbungs- und Review-Workflow

`market_explorer/`
- Marktanalyse
- Aggregation
- Visualisierung
- explorative Insights

## Ziel fuer den ersten Meilenstein

Ein erstes MVP ist erreicht, wenn folgende Fragen beantwortbar sind:

- In welchen Regionen erscheinen aktuell die meisten relevanten Jobs?
- Welche Rollencluster sind am haeufigsten?
- Welche Firmen posten besonders viel?
- Welche Skills kommen in den Anzeigen am haeufigsten vor?
- Wie entwickeln sich Postings ueber die Zeit?

## Ordnerstruktur

- `app/`
  - Dashboard oder kleine interaktive Web-App
- `pipeline/`
  - Sammeln, Normalisieren, Enrichment, Aggregation
- `data/`
  - lokale Zwischen- und Analyse-Daten
- `exports/`
  - generierte Visualisierungen, HTML-Exports, Reports
- `notes/`
  - Scope, Annahmen, Metriken, offene Fragen

## Naechste Schritte

1. MVP-Produktfrage praezisieren
2. Datenmodell fuer Analyse-Jobs definieren
3. Wiederverwendbare Logik aus dem Hauptprojekt identifizieren
4. erste Sammelpipeline fuer einen begrenzten Quellensatz bauen
5. erste interaktive Visualisierung bauen

## Aktueller Stand

Die erste lokale Explorer-Version kann jetzt als breiter Deutschland-Scan gesammelt und gerendert werden:

```powershell
.\.venv\Scripts\python.exe .\market_explorer\run_market_explorer.py
```

Nur das Dashboard aus bereits gesammelten Daten neu rendern:

```powershell
.\.venv\Scripts\python.exe .\market_explorer\run_market_explorer.py --reuse-existing
```

Nur Agentur fuer Arbeit, breit ueber die grossen Staedte und ueber mehrere Seiten:

```powershell
.\.venv\Scripts\python.exe .\market_explorer\run_market_explorer.py --sources ba --ba-broad --ba-page-size 100 --variant plotly
```

Optional mit Seitenlimit zum ersten Laufzeittest:

```powershell
.\.venv\Scripts\python.exe .\market_explorer\run_market_explorer.py --sources ba --ba-broad --ba-page-size 100 --ba-max-pages 5 --variant plotly
```

Standard fuer den BA-Broad-Scan ist jetzt ein lokaler Stadtradius von `20 km`. Falls du das aendern willst:

```powershell
.\.venv\Scripts\python.exe .\market_explorer\run_market_explorer.py --sources ba --ba-broad --ba-radius-km 20 --ba-page-size 100 --variant plotly
```

Erzeugt:

- `market_explorer/data/market_jobs_collected.json`
- `market_explorer/data/market_jobs.json`
- `market_explorer/data/market_summary.json`
- `market_explorer/exports/market_explorer_dashboard.html`

Aktuell sammelt der Explorer breit ueber Deutschland aus:

- `stepstone`
- `arbeitsagentur`

Aktuelle Verbesserungen in Phase 2:

- zweite Quelle fuer breitere Marktdeckung
- heuristische Branchenzuordnung
- Company-Quality-Sicht mit `Employer`, `Staffing`, `Aggregator`
- freie Textsuche im Dashboard

## Connector-Architektur

Die Explorer-Quellen werden jetzt schrittweise auf eine modulare Struktur umgestellt:

- `market_explorer/connectors/ba_connector.py`
- `market_explorer/connectors/greenhouse_connector.py`
- `market_explorer/connectors/lever_connector.py`
- `market_explorer/connectors/jobposting_extractor.py`

Primärquellen koennen ueber `config/market_primary_sources.json` aktiviert werden.

Unterstuetzte Typen:

- `greenhouse`
- `lever`
- `jobposting`

Alle Beispiele in der Config sind standardmaessig deaktiviert und koennen gezielt aktiviert oder ersetzt werden.
