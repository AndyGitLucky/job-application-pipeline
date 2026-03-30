# Master Profile

Dieser Ordner ist jetzt die **aktive Source of Truth** fuer persoenliche Profildaten im Projekt.

## Dateien

- `master_profile.json`
  - die reale, private Profilquelle
  - **nicht** fuer Git gedacht
  - wird lokal fuer Suche, Matching, Retrieval und spaeter Schreiben genutzt
- `master_profile.example.json`
  - oeffentliche Vorlage ohne private Kontaktdaten

## Rolle im Projekt

Die Idee ist:

- `master_profile.json` = komplette Rohwahrheit ueber Andreas
- `source/profile_store.py` = laedt und normalisiert diese Daten
- abgeleitete Profile = unterschiedliche Arbeitsansichten fuer:
  - Jobsuche
  - Matching
  - Retrieval-Kontext
  - Bewerbungsartefakte

Damit vermeiden wir mehrere manuell gepflegte Wahrheiten an verschiedenen Stellen.

## Herkunft

Der fruehere `cv_generator` war eine aeltere, getrennte Experimentierspur.
Die dortige Profildatei wurde hierher uebernommen, weil sie weiterhin die reichste strukturierte Datenquelle ueber Andreas ist.

Der alte Generator selbst liegt jetzt unter:

- `archive/legacy_cv_generator/`

und ist **nicht** mehr der aktive Kern des Projekts.
