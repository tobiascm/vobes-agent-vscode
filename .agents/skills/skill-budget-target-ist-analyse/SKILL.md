---
name: skill-budget-target-ist-analyse
description: "Budget Target/Ist-Analyse EKEK/1: Aufgabenbereiche und Firmen mit 2025, Target 2026, Ist 2026, Delta. Maßnahmen-Spalte bleibt leer — Agent befüllt sie nach User-Vorgaben."
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
| `report_massnahmenplan.py` | Erzeugt den Markdown-Report |
| `target.csv` | 2025-Referenzwerte + 2026-Targets (editierbar, Semikolon-getrennt) |
| `praemissen.md` | Zuordnungsregeln, Split-Logik, feste Werte (wird in Report eingebettet) |

## Workflow

1. **Script ausführen:**
   ```bash
   python .agents/skills/skill-budget-target-ist-analyse/report_massnahmenplan.py
   ```
2. Das Script:
   - Lädt 2025 + Target aus `target.csv`
   - Lädt Prämissen-Text aus `praemissen.md`
   - Synchronisiert BTL-Daten (aktuelles Jahr) aus BPLUS-NG
   - Ordnet BMs den Aufgabenbereichen zu (Firma→Bereich-Mapping inkl. Split-Logik)
   - Schreibt Markdown nach `userdata/budget/`
   - Gibt NUR den Dateipfad auf stdout aus
3. **Agent liest die erzeugte Datei** und präsentiert sie dem User.
4. **User gibt Maßnahmen vor** → Agent füllt die Maßnahmen-Spalte per Datei-Edit.

## Ausgabe-Struktur

1. **Header** — Titel, BPLUS-Stand, Erstelldatum
2. **Prämissen** — aus `praemissen.md` + Sync-Zeitpunkt
3. **Tabelle: Aufgabenbereiche** — 2025, Target, Ist, Delta, Maßnahmen (leer)
4. **Tabelle: Firmen-Übersicht** — Firma, Anzahl BMs, Ist, Maßnahmen (leer)
5. **Gesamtübersicht** — Ist vs. Target, Delta

## Wichtig

- **Maßnahmen NIE automatisch befüllen** — immer dem User überlassen.
- **IMMER** `report_massnahmenplan.py` ausführen, NIE eine vorhandene Datei wiederverwenden.
- Targets ändern → `target.csv` editieren, kein Scriptumbau nötig.
- Prämissen ändern → `praemissen.md` editieren.
- Das Script verwendet `budget_db.py` für DB-Sync und SQL-Queries.
