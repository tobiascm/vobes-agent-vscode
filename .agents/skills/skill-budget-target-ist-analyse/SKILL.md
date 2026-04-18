---
name: skill-budget-target-ist-analyse
description: "Budget Target/Ist-Analyse EKEK/1: Aufgabenbereiche und Firmen mit 2025, Target 2026, Ist 2026, Delta. Kann standardmaessig aus `btl` oder optional aus `btl_opt` lesen; bei `btl_opt` wird der Report deutlich als Optimierungsvorschlag markiert. Maßnahmen-Spalte bleibt leer — Agent befüllt sie nach User-Vorgaben."
---

# Skill: Budget Target/Ist-Analyse EKEK/1

## Zweck

Erzeugt eine Markdown-Arbeitstabelle mit Budget-Vergleich (Vorjahr → Target → Ist → Delta) für EKEK/1.
Die Tabelle hat zwei Sichten: **nach Aufgabenbereich** und **nach Firma**.
Die Spalte **Maßnahmen** bleibt initial leer und wird durch den Agent nach User-Vorgaben befüllt.

## Trigger

- Budget-Maßnahmenplan, Maßnahmenplanung, Budget-Vergleich Aufgabenbereiche, Budgetübersicht mit Maßnahmen
- "Erstelle mir den Maßnahmenplan", "Budget-Arbeitstabelle"

## Dateien

| Datei | Zweck |
|---|---|
| `report_massnahmenplan.py` | Erzeugt den Markdown- und XLSX-Report; PDF nur explizit mit `--pdf` |
| `userdata/budget/vorgaben/target.csv` | 2025-Referenzwerte + 2026-Targets (editierbar, Semikolon-getrennt) |
| `userdata/budget/vorgaben/praemissen.md` | Zuordnungsregeln, Split-Logik, feste Werte (wird in Report eingebettet) |

## Workflow

1. **Script ausführen:**
   ```bash
   python .agents/skills/skill-budget-target-ist-analyse/report_massnahmenplan.py
   ```
   Fuer Validierung eines Optimierungsvorschlags:
   ```bash
   python .agents/skills/skill-budget-target-ist-analyse/report_massnahmenplan.py --source-table btl_opt
   ```
   Für zusätzlichen PDF-Export:
   ```bash
   python .agents/skills/skill-budget-target-ist-analyse/report_massnahmenplan.py --pdf
   ```
2. Das Script:
   - Lädt 2025 + Target aus `userdata/budget/vorgaben/target.csv`
   - Lädt Prämissen-Text aus `userdata/budget/vorgaben/praemissen.md`
   - Synchronisiert BTL-Daten (aktuelles Jahr) aus BPLUS-NG
   - Liest standardmäßig aus `btl`, optional aus `btl_opt`
   - Ordnet BMs den Aufgabenbereichen zu (Firma→Bereich-Mapping inkl. Split-Logik)
   - Schreibt standardmäßig Markdown und XLSX nach `userdata/budget/`
   - Kennzeichnet Reports aus `btl_opt` oben fett und rot als Optimierungsvorschlag
   - Erzeugt nur mit `--pdf` und installierter Dependency `markdown-pdf` zusätzlich eine PDF-Datei
   - Übernimmt in der XLSX manuelle Notizen/Aktionen aus der letzten älteren Maßnahmenplan-Datei (oder optional via `--inherit-notes-from <xlsx>`) per stabilem Schlüssel
   - Gibt die erzeugten Dateipfade auf stdout aus (Markdown, XLSX, optional PDF nur bei `--pdf`)
3. **Agent liest die erzeugte Datei** und präsentiert sie dem User.
4. **User gibt Maßnahmen vor** → Agent füllt die Maßnahmen-Spalte per Datei-Edit.

## Ausgabe-Struktur

1. **Header** — Titel, BPLUS-Stand, Erstelldatum
2. **Prämissen** — aus `userdata/budget/vorgaben/praemissen.md` + Sync-Zeitpunkt
3. **Tabelle: Aufgabenbereiche** — 2025, Target, Ist, Delta, Maßnahmen (leer)
4. **Tabelle: Firmen-Übersicht** — Firma, Anzahl BMs, Ist, Maßnahmen (leer)
5. **Korrektur Überplanung** — Pro überplanter Firma werden zuerst stornierte Vorgänge mit Aktion `löschen` aufgeführt. Danach folgen Quartals-Korrektur (im Durchlauf → bestellt) und Jahres-Korrektur (01 Erstellung → im Durchlauf) mit Priorisierung.
6. **Gesamtübersicht** — Ist vs. Target, Delta

## Wichtig

- **Maßnahmen in der Firmen-Übersicht** werden automatisch befüllt (Quartal/Jahr überplant bzw. zu gering).
- **Aktion-Spalte in Korrektur Überplanung NIE automatisch befüllen** — immer dem User überlassen.
- PDF-Export ist optional und nur mit `--pdf` aktiv. Er bleibt Best-effort im A4-Querformat; Fehler oder fehlendes `markdown-pdf` werden auf stderr gewarnt und dürfen Markdown/XLSX nicht abbrechen.
- **IMMER** `report_massnahmenplan.py` ausführen, NIE eine vorhandene Datei wiederverwenden.
- In der XLSX werden manuelle Notizen/Aktionen aus der Vor-Datei fortgeschrieben:
  - Bereiche über Aufgabenbereich
  - Firmen über Firmenname
  - Korrekturen über Firma + Blocktyp + Vorgangsnummer (`Konzept`)
- Targets ändern → `userdata/budget/vorgaben/target.csv` editieren, kein Scriptumbau nötig.
- Feste Firmen-Targets können optional direkt in `userdata/budget/vorgaben/target.csv` ergänzt werden, z.B. zusätzliche Spalten wie `Bertrandt_Target_2026`.
- Prämissen ändern → `userdata/budget/vorgaben/praemissen.md` editieren.
- Das Script verwendet `budget_db.py` für DB-Sync und SQL-Queries.
