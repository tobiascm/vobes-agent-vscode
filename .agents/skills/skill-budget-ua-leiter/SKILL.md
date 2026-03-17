---
name: skill-budget-ua-leiter
description: Unterabteilungsleiter (UA-Leiter) aus BPLUS-NG abrufen. Nutze diesen Skill wenn der User nach Leitungen, UA-Leitern oder Ansprechpartnern einer OE fragt.
---

# Skill: BPLUS-NG Unterabteilungsleiter (UA-Leiter)

Dieser Skill findet die **Leitungen**/**Führungskräfte** aus den BPLUS-NG OrgUnit-Daten (alle OEs mit zugeordneter Mail-Adresse).

## Workflow

> 1. **Sync:** `python scripts/budget/budget_db.py sync ua_leiter` (Cache: 1 Tag, `--force` zum Erzwingen)
> 2. **Query:** `python scripts/budget/budget_db.py query "SELECT ..." --output result.md --open` ausfuehren
> 3. Das Script schreibt eine **Markdown-Tabelle** in die Datei und oeffnet sie in VS Code

## Kontext

- Datenquelle: REST-API `OrgUnit/GetAll` (alle OEs mit Mail-Adresse und Level).
- Jede OE mit zugeordneter Mail-Adresse wird als Leitung gefuehrt.
- Level-Mapping: 2=Bereich, 3=Hauptabteilung, 4=Abteilung, 5=Unterabteilung.

## Wann verwenden?

- Der User fragt nach **Unterabteilungsleitern** (UA-Leitern)
- Der User sucht den **Leiter** / **Ansprechpartner** einer OE
- Der User moechte wissen, wer eine bestimmte OE leitet

## Tabellen-Schema (ua_leiter)

| Spalte | Typ | Beschreibung | Beispiel |
|---|---|---|---|
| `oe` | TEXT | Organisationseinheit | `EKEK/1` |
| `ebene` | TEXT | Hierarchie-Ebene | `Unterabteilung`, `Abteilung`, `Hauptabteilung`, `Bereich` |
| `mail` | TEXT | E-Mail der Leitung | `max.mustermann@volkswagen.de` |

## Beispiel-SQL-Queries

```sql
-- Alle Leitungen
SELECT * FROM ua_leiter ORDER BY oe

-- Leiter einer OE
SELECT oe, ebene, mail FROM ua_leiter WHERE oe = 'EKEK/1'

-- Alle Abteilungsleiter
SELECT oe, mail FROM ua_leiter WHERE ebene = 'Abteilung' ORDER BY oe
```

## API-Endpunkte

| Ressource | URL |
|---|---|
| OrgUnit (alle OEs) | `GET /ek/api/OrgUnit/GetAll?year={year}` |

Basis-URL: `https://bplus-ng-mig.r02.vwgroup.com`

## Haeufige Probleme

| Problem | Loesung |
|---|---|
| Seite nicht erreichbar | VW-Netzwerk/VPN pruefen |
| Keine Ergebnisse | OE-Schreibweise pruefen (exakt, z.B. `EKEK/1`) |
