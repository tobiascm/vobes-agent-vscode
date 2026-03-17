---
name: skill-budget-stundensaetze
description: Stundensaetze (Hourly Rates) aus BPLUS-NG abrufen. Nutze diesen Skill wenn der User nach Stundensaetzen, Kostenstellen oder OE-Stundensaetzen fragt.
---

# Skill: BPLUS-NG Stundensaetze

Dieser Skill beschreibt den Workflow, um **Stundensaetze** (Hourly Rates) aus BPLUS-NG/EK-Reports in die lokale SQLite-DB zu laden.

## Workflow

> 1. **Sync:** `python scripts/budget_db.py sync stundensaetze` (Cache: 1 Tag, `--force` zum Erzwingen)
> 2. **Query:** `python scripts/budget_db.py query "SELECT ..." --output result.md --open` ausfuehren
> 3. Das Script schreibt eine **Markdown-Tabelle** in die Datei und oeffnet sie in VS Code

## Kontext

- Die Daten stammen aus den REST-APIs `OrgUnit/GetAll` (OE + KST) und `CostCenter/GetCostCenter2HourlyRates` (Stundensaetze pro KST).
- Die Daten enthalten Stundensaetze pro OE, Kostenstelle und Jahr.

## Wann verwenden?

- Der User fragt nach **Stundensaetzen** (Hourly Rates)
- Der User moechte wissen, welchen Stundensatz eine OE / Kostenstelle hat
- Der User erwaehnt InfoDepartments, Kostenstellen-Saetze oder OE-Stundensaetze

## Tabellen-Schema (stundensaetze)

| Spalte | Typ | Beschreibung | Beispiel |
|---|---|---|---|
| `jahr` | INTEGER | Jahr | `2026` |
| `kst` | TEXT | Kostenstelle | `1721` |
| `oe` | TEXT | Organisationseinheit | `EKEK/1` |
| `stundensatz` | REAL | Stundensatz in EUR | `153.35` |

## Beispiel-SQL-Queries

```sql
-- Stundensatz einer OE
SELECT oe, stundensatz FROM stundensaetze WHERE oe = 'EKEK/1'

-- Alle Stundensaetze
SELECT oe, kst, stundensatz FROM stundensaetze ORDER BY oe

-- Stundensaetze nach OE gruppiert
SELECT oe, AVG(stundensatz) as avg_rate, COUNT(*) as kst_count
FROM stundensaetze GROUP BY oe ORDER BY avg_rate DESC
```

## API-Endpunkte

| Ressource | URL |
|---|---|
| OrgUnit (OE + KST) | `GET /ek/api/OrgUnit/GetAll?year={year}` |
| Stundensaetze (KST → Rate) | `GET /ek/api/CostCenter/GetCostCenter2HourlyRates` |

Basis-URL: `https://bplus-ng-mig.r02.vwgroup.com`

## Haeufige Probleme

| Problem | Loesung |
|---|---|
| API nicht erreichbar | VW-Netzwerk/VPN pruefen |
| Keine Daten fuer ein Jahr | Jahr pruefen (ggf. noch keine Daten hinterlegt) |
