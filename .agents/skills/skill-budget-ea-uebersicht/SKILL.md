---
name: skill-budget-ea-uebersicht
description: Entwicklungsauftraege (EA) aus BPLUS-NG per API abrufen. Nutze diesen Skill wenn der User nach EA-Stammdaten, EA-Nummern, EA-Laufzeiten, Projektfamilien, Controllern oder der EA-Uebersicht fragt. NICHT verwenden fuer Fragen zu Firmen, Lieferanten, Dienstleistern, Buchungen auf EAs, Vorgaengen oder Abrufen — dafuer ist skill-budget-bplus-export zustaendig.
---

# Skill: BPLUS-NG Entwicklungsauftraege (EA-Uebersicht)

Dieser Skill laedt die **EA-Uebersicht** (Entwicklungsauftraege / DevOrders) aus BPLUS-NG per REST-API in die lokale SQLite-DB.

## Workflow

> 1. **Sync:** `python scripts/budget_db.py sync devorder` (Cache: 1 Tag, `--force` zum Erzwingen)
> 2. **Query:** `python scripts/budget_db.py query "SELECT ..." --output result.md --open` ausfuehren
> 3. Das Script schreibt eine **Markdown-Tabelle** in die Datei und oeffnet sie in VS Code

## Kontext

- Entspricht der Tabelle auf der BPLUS-NG Seite `InfoDevOrders.aspx`
- Liefert EA-Nummer, Titel, Laufzeit, SOP, Projektfamilie, Controller und Hierarchie

## Wann verwenden?

- Der User fragt nach **Entwicklungsauftraegen** (EA)
- Der User moechte eine **EA-Uebersicht** oder **EA-Liste** aus BPLUS-NG
- Der User sucht eine bestimmte **EA-Nummer** oder EAs einer **Projektfamilie**
- Der User erwaehnt **DevOrders** oder **InfoDevOrders**

## Disambiguierung: "Auf welche EA wird X gebucht?"

- Wenn die Anfrage ein Muster wie "auf welche EA wird <Name> gebucht" enthaelt:
  1. Zuerst pruefen: Ist <Name> eine Firma/Lieferant? → `skill-budget-bplus-export` (BTL-Daten, Feld `company`)
  2. Nur wenn kein Treffer bei company: Personenfelder pruefen
  3. Bei Doppeltreffern: User fragen, was gemeint ist.

## Tabellen-Schema (devorder)

| Spalte | Typ | Beschreibung | Beispiel |
|---|---|---|---|
| `ea_number` | TEXT | EA-Nummer | `0011953` |
| `title` | TEXT | Titel des EA | `MEB Antrieb Allrad/Heck ID Buzz` |
| `active` | BOOLEAN | Aktiv-Status | `1` / `0` |
| `date_from` | TEXT | Start-Datum | `2017-10-18` |
| `date_until` | TEXT | Ende-Datum | `2025-01-31` |
| `sop` | TEXT | SOP-Datum | `2024-04-04` |
| `project_family` | TEXT | Projektfamilie | `A_BEV` |
| `controller` | TEXT | Controller-Kuerzel | `VWTH3IE` |
| `hierarchy` | TEXT | TE-Hierarchie | `TE - Aggregate - ...` |

## Beispiel-SQL-Queries

```sql
-- Alle aktiven EAs
SELECT ea_number, title, project_family, date_from, date_until
FROM devorder WHERE active = 1 ORDER BY ea_number

-- EAs einer Projektfamilie
SELECT ea_number, title, date_until, sop
FROM devorder WHERE project_family = 'A_BEV' AND active = 1

-- EA suchen
SELECT * FROM devorder WHERE ea_number = '0011953'

-- EAs nach Projektfamilie gruppiert
SELECT project_family, COUNT(*) as anzahl
FROM devorder WHERE active = 1 GROUP BY project_family ORDER BY anzahl DESC

-- Auslaufende EAs (Ende vor 2026)
SELECT ea_number, title, date_until, project_family
FROM devorder WHERE active = 1 AND date_until < '2026-01-01' ORDER BY date_until
```

## URLs und API-Endpunkte

| Ressource | URL |
|---|---|
| EA-Uebersicht (Web) | `https://bplus-ng-mig.r02.vwgroup.com/ek-reports/InfoDevOrders.aspx?y={year}` |
| API: Alle DevOrders | `https://bplus-ng-mig.r02.vwgroup.com/ek/api/DevOrder/GetAll?year={year}` |

## Haeufige Probleme

| Problem | Loesung |
|---|---|
| API nicht erreichbar | VW-Netzwerk/VPN pruefen |
| Leere Antwort | Jahr pruefen (API liefert nur Daten fuer gueltige Jahre) |
| EA nicht gefunden | EA-Nummer mit fuehrenden Nullen angeben (z.B. `0011953`) |
