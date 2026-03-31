# Midterm Roadmap

Diese Roadmap beschreibt die naechsten sinnvollen Entwicklungsschritte fuer die Job Application Pipeline ueber die naechsten Sessions.

Sie ist bewusst nicht als starres Backlog formuliert, sondern als priorisierte Arbeitsrichtung mit:

- Zielbild
- konkretem Nutzen
- Risiken
- sinnvollen Reihenfolgen
- klaren "Definition of Done"-Ideen

Die Reihenfolge basiert auf dem aktuellen Stand des Projekts:

- saubere Repo-Struktur
- Human-in-the-loop Review Workbench
- Feedback-Layer
- Search Modes `normal` / `explore`
- erste semantische Rollen- und Jobschicht

## Leitgedanke

Das Projekt ist nicht mehr primaer "ein Scraper mit Bewerbungsautomation", sondern entwickelt sich zu einem System, das drei Fragen immer besser beantworten soll:

1. Welche Jobs sind operativ bewerbbar?
2. Welche Jobs passen wirklich zu Andreas?
3. Welche Rollen sollte Andreas vielleicht suchen, obwohl er sie heute noch nicht aktiv sucht?

Die Roadmap folgt genau diesen drei Achsen.

---

## Prioritaet 1: Profil als echte Single Source of Truth

### Warum das wichtig ist

Derzeit existiert das Kandidatenprofil in zwei Welten:

- strukturiert im Masterprofil
- verdichtet / historisch in `candidate_profile.py`

Das ist kurzfristig okay, langfristig aber gefaehrlich:

- Inkonsistenzen schleichen sich ein
- Scoring, Search und Retrieval lernen auf leicht unterschiedlichen Profilbildern
- neue Profilfelder muessen mehrfach gepflegt werden

### Ziel

Ein einziges Masterprofil ist die operative Quelle, aus der verschiedene Arbeitsprofile abgeleitet werden.

### Konkrete Arbeitspakete

1. `profile_store.py` ausbauen
   - `load_master_profile()`
   - `build_application_profile()`
   - `build_search_profile()`
   - `build_semantic_profile()`

2. `candidate_profile.py` reduzieren
   - erst Kompatibilitaetsschicht
   - spaeter Ablage historischer Default-Texte

3. Retrieval auf abgeleitete Profile umstellen
   - Scoring-Kontext
   - spaeter auch Search-Kontext

### Definition of Done

- Es gibt keine manuell gepflegte zweite Wahrheit mehr fuer das operative Kandidatenprofil.
- Search, Retrieval und LLM-Scoring greifen auf denselben Profilkern zu.
- Aenderungen am Masterprofil schlagen sichtbar und nachvollziehbar in mehreren Teilsystemen durch.

---

## Prioritaet 2: Cheap-first Priorisierung vor dem LLM

### Warum das wichtig ist

Die eigentliche knappe Ressource des Systems ist nicht das Finden, sondern das Bewerten.

Der groesste Hebel ist deshalb:

- moeglichst viele Jobs billig aussortieren oder vorpriorisieren
- nur die besten Kandidaten an das LLM schicken

### Ziel

Vor dem LLM gibt es einen leichten, schnellen Vorfilter / Vorrangscore.

### Konkrete Arbeitspakete

1. Pre-Ranking-Signal definieren
   - Quellenqualitaet
   - Beschreibungstiefe
   - Ortspassung
   - Suchmodus
   - Suchstrategie (`semantic`, `heuristic`, `default`)
   - Feedback-Malus / Bonus
   - Titelnahe / Rollennahe

2. `pre_score_rank` einfuehren
   - billiger numerischer Score vor dem LLM

3. Budget nur auf Top-Kandidaten anwenden
   - `normal`: 25
   - `explore`: 25

4. Deferred-Backlog explizit machen
   - nicht nur verstecken
   - sondern als bewusst aufgeschobene Kandidaten behandeln

### Definition of Done

- Das LLM sieht sichtbar bessere Kandidaten als heute.
- Ein Run mit vielen Rohjobs bleibt stabil im Budget.
- Die Auswahl fuer das LLM ist erklaerbar und testbar.

---

## Prioritaet 3: Search Modes messbar und lernbar machen

### Warum das wichtig ist

`normal` und `explore` sind jetzt produktisch interessant, aber noch nicht ausreichend ausgewertet.

Aktuell wissen wir:

- was gesucht wurde
- was gefunden wurde
- was bewertet wurde

Aber wir wissen noch nicht gut genug:

- welcher Begriff bringt gute Review-Kandidaten?
- welche Explore-Rolle produziert fast nur Muell?
- welche semantischen Vorschlaege fuehren zu echten Freigaben?

### Ziel

Die Search Modes werden zu einem messbaren Experimentierraum.

### Konkrete Arbeitspakete

1. Search Attribution pro Job behalten
   - `search_mode`
   - `search_term`
   - `search_strategy`
   - `search_origin`
   - `search_semantic_score`

2. Search-Performance-Report bauen
   - Treffer pro Term
   - empfohlene Jobs pro Term
   - Freigaben / Rejects pro Term
   - `manual_apply_ready` pro Term

3. Search-Term-Retirement vorbereiten
   - Terme mit dauerhaft schlechter Yield spaeter abwerten

### Definition of Done

- Nach einem Run ist sichtbar, welche Suchterme wirklich Wert liefern.
- `explore` ist nicht mehr nur "interessant", sondern auswertbar.
- Wir koennen einzelne Begriffe gezielt hoch- oder runterdrehen.

---

## Prioritaet 4: Echten semantischen Explore-Modus ausbauen

### Warum das wichtig ist

Das ist der spannendste neue Produktpfad:

- nicht nur bekannte Jobtitel suchen
- sondern den passenden Suchraum fuer Andreas entdecken

### Aktueller Stand

Es gibt bereits:

- eine Rollenbibliothek
- ein semantisches Rollenranking
- einen Explore-Search-Plan

Derzeit ist das aber noch ein kontrollierter erster Schritt. Je nach Lauf kann lexical fallback oder echter Embedding-Provider greifen.

### Ziel

`explore` wird zu einem belastbaren "surprise me"-Modus, der:

- neue Rollenfamilien vorschlaegt
- aber nicht unkontrolliert wird

### Konkrete Arbeitspakete

1. Rollenbibliothek ausbauen
   - nicht nur mehr Rollen
   - sondern klarere Rollentexte
   - evtl. Cluster wie:
     - perception
     - platform
     - optimization
     - analytics
     - industrial AI

2. Semantische Rollenbewertung transparenter machen
   - Top-Rollen inkl. Score im Log
   - spaeter in UI oder Report

3. Explore-Terme schichten
   - `adjacent`
   - `stretch`
   - spaeter evtl. `wildcard`

4. Geraeuscharme Exploration
   - nicht nur "mehr neue Titel"
   - sondern "unerwartet passend, aber noch plausibel"

### Definition of Done

- Der semantische Explore-Plan liefert nachvollziehbar andere Rollen als die reine Heuristik.
- Ueber mehrere Runs werden gute neue Rollenfamilien sichtbar.
- Explore fuehlt sich wie ein kontrolliertes Discovery-Instrument an, nicht wie Zufall.

---

## Prioritaet 5: Duplicate Detection von Role Similarity trennen

### Warum das wichtig ist

Die bisherigen Embedding-Eval-Laeufe haben klar gezeigt:

- aehnliche Jobs sind nicht automatisch derselbe Job

Diese Trennung ist produktisch wichtig.

### Ziel

Zwei getrennte Systeme:

1. `Role Similarity`
   - fuer Discovery
   - fuer "surprise me"
   - fuer Profil-Matching

2. `Duplicate Detection`
   - fuer Best-source-Merge
   - konservativ
   - stark eingegrenzt

### Konkrete Arbeitspakete

1. Duplicate-Pairs enger generieren
   - gleiche Firma / Alias
   - gleicher Ort
   - gleiche oder sehr aehnliche Quelle / Titelbasis

2. Similarity nur auf plausiblen Kandidatenpaaren anwenden

3. Eval-UI spaeter splitten
   - `same job?`
   - `similar role?`

### Definition of Done

- Die Duplicate-Logik versucht nicht mehr, globale Rollenaehnlichkeit als Merge-Signal zu missbrauchen.
- Stepstone-/Indeed-/AA-Varianten koennen spaeter gezielter verschwinden, wenn bessere Firmenquellen da sind.

---

## Prioritaet 6: Review Workbench staerker als Arbeitsoberflaeche denken

### Warum das wichtig ist

Die UI ist schon gut, aber sie ist noch nicht voll nach Arbeitsmodus aufgeteilt.

Gerade mit `normal`, `explore` und Deferred-Backlogs wird das wichtiger.

### Ziel

Die UI zeigt nicht nur offene Jobs, sondern unterstuetzt unterschiedliche Review-Aufgaben.

### Konkrete Arbeitspakete

1. Sektionen einfuehren
   - neue normale Funde
   - neue Explore-Funde
   - offene Kandidaten
   - freigegebene Jobs

2. Deferred-Backlog sichtbar, aber getrennt
   - nicht im Hauptreview
   - aber als eigener Arbeitsstapel

3. Search- und Similarity-Erklaerungen besser zeigen
   - warum wurde dieser Job gefunden?
   - warum ist dieser Job Explore?
   - warum gilt diese Rolle als semantisch passend?

### Definition of Done

- Die Workbench unterstuetzt reale Arbeitsmodi besser als nur eine sortierte Gesamtliste.
- `explore` fuehlt sich wie ein eigener Kanal an.

---

## Prioritaet 7: `find_jobs.py` schrittweise zerlegen

### Warum das wichtig ist

Die Datei ist heute funktional stark, aber strukturell zu breit.

Sie enthaelt:

- Search-Orchestration
- Quelladapter
- Dedupe
- Description-Enrichment
- BMW-Sonderlogik
- Filter
- Validierung

Das verlangsamt jede Weiterentwicklung.

### Ziel

`find_jobs.py` bleibt Orchestrator, die eigentlichen Schichten wandern in Teilmodule.

### Moegliche Zielstruktur

- `sources/` fuer Quelladapter
- `dedupe.py`
- `enrichment.py`
- `validation.py`
- `search_orchestration.py`

### Definition of Done

- Neue Features in der Jobsuche brauchen nicht mehr dieselbe Riesendatei.
- Tests koennen viel gezielter auf einzelne Teilprobleme gehen.

---

## Prioritaet 8: Quellenqualitaet feiner modellieren

### Warum das wichtig ist

Viele echte Produktentscheidungen haengen nicht am Titel, sondern am Bewerbungsweg.

### Ziel

Quellen werden nicht nur als `high/medium/low` gefuehlt, sondern systematisch behandelt.

### Konkrete Arbeitspakete

1. Feiner zwischen Discovery-Faellen unterscheiden
   - guter Content, aber unaufgeloeste Quelle
   - kaputter Discovery-Link
   - echter Firmenpfad hinter Gate

2. Bessere Sichtbarkeit in UI und Ranking

3. Spaeter evtl. Link-Health fuer verbleibende schwache Quellen

### Definition of Done

- Gute Inhalte mit schwachem Link werden nicht mit schlechtem Job verwechselt.
- Kaputte Discovery-Links werden frueher als solche erkannt.

---

## Drei sinnvolle naechste Sessions

### Session A: Explore messbar machen

Fokus:

- Search-Term-Report
- Term-Yield
- kleine Auswertung fuer `normal` vs `explore`

Warum:

- schnellster Produktgewinn
- hilft direkt bei Kalibrierung

### Session B: Profil vereinheitlichen

Fokus:

- `profile_store.py` ausbauen
- `candidate_profile.py` entkoppeln
- Search / Retrieval / Application sauber auf dasselbe Profil setzen

Warum:

- strukturell wichtig
- senkt langfristig Pflegekosten

### Session C: Pre-Ranking vor dem LLM

Fokus:

- billige Vorranglogik
- bessere 25er-Auswahl

Warum:

- groesster Effizienzgewinn
- reduziert Modellkosten und Review-Rauschen

---

## Nicht jetzt, aber spaeter

Diese Ideen sind gut, aber noch nicht die naechsten drei Sessions:

- vollautomatische semantische Job-zu-Profil-Gesamtrangliste
- aggressive semantische Auto-Merges
- komplexe Lernmodelle fuer Feedback
- vollstaendige ATS-/Captcha-Automation

Sie bleiben interessant, aber sollten erst kommen, wenn Profil, Search Attribution und Pre-Ranking stabil sind.

---

## Zusammenfassung

Die mittelfristige Richtung ist klar:

- Profil vereinheitlichen
- Search intelligenter und messbarer machen
- LLM-Budget besser schuetzen
- Explore zu einem echten Discovery-Kanal entwickeln
- Duplicate Detection sauber von Role Similarity trennen

Wenn diese Punkte gut sitzen, wird das Projekt nicht nur ein besseres Bewerbungswerkzeug, sondern auch ein deutlich staerkeres technisches Portfolio-Stueck.
