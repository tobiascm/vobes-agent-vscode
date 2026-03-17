---
name: skill-budget-bplus-export
description: Export und Analyse aus BPLUS-NG (Vorgangsuebersicht, Abrufuebersicht, BM-Uebersicht, Konzeptuebersicht) per API oder Playwright. Analysefragen laufen ueber report_bplus.py auf Basis der lokalen SQLite-DB. Fuer expliziten Excel-Export bleibt der Web-/Playwright-Pfad erhalten. Auch ohne expliziten Exportwunsch ist dieser Skill zustaendig, wenn die Antwort auf BTL-Daten (company, concept, ea, planned_value) basiert — z.B. auf welche EA eine Firma/Lieferant/Dienstleister gebucht ist, welche Vorgaenge/Abrufe eine bestimmte Firma hat, wo ein externer Partner zugeordnet ist, oder Budget-/Ausgabenfragen zu Firmen und Konzepten.
---

# Skill: BPLUS-NG Export

Dieser Skill hat zwei Pfade:

1. **Analyse / Reporting** (Standard)
   BTL-Daten nach `budget.db` synchronisieren und strukturierten Markdown-Bericht erzeugen
2. **Expliziter Datei-Export** (Ausnahme)
   CSV/Excel direkt aus BPLUS herunterladen. **Excel bleibt separater Web-/Playwright-Pfad.**
   BPLUS URL: https://bplus-ng-mig.r02.vwgroup.com/ek/btl

## Kontext

- Der Standard-Export umfasst ausschliesslich das Team **EKEK/1**. Der Export kann auf ganz EK ausgeweitet werden.
- Ersteller im Team: **Bachmann Armin**, **Bartels Timo**, **Junge Christian**.
- **Standard-Jahr:** Wenn der User kein Jahr nennt, wird immer das **aktuelle Jahr** verwendet.

## Wann verwenden?

- Der User moechte eine BM / Budget / Abruf Uebersicht aus BPLUS-NG
- Der User erwaehnt BPLUS, Budget, Vorgangsuebersicht, Abrufuebersicht, BM-Uebersicht oder Konzeptuebersicht
- Der User fragt, auf welche EA eine **Firma/Lieferant/Dienstleister** gebucht ist
- Der User fragt nach Vorgaengen/Abrufen einer bestimmten Firma
- Der User stellt Budget-/Ausgabenfragen zu Firmen und Konzepten

## Pflicht: Analyse-Script verwenden

> **WICHTIG:** Bei Analysefragen zu BPLUS-Daten IMMER `report_bplus.py` verwenden.
> Tabellen, Summen und Status-Aufschluesselungen NIEMALS manuell berechnen.
> **NIEMALS eine vorhandene Ergebnis-Datei wiederverwenden.** Das Script wird bei JEDER Anfrage neu ausgefuehrt.
>
> **Workflow Analyse:**
> 1. `python .agents/skills/skill-budget-bplus-export/report_bplus.py ...`
> 2. Das Script synchronisiert `btl` selbst bei Bedarf.
> 3. Das Script schreibt IMMER eine Ergebnis-Datei nach `userdata/sessions/`.
> 4. Das Script gibt NUR den Pfad zur Ergebnis-Datei auf stdout aus.
> 5. **NUR folgenden Satz im Chat an den User ausgeben:**
>    `Den Ergebnisbericht habe ich erstellt und hier fuer Dich abgelegt:` gefolgt von einem klickbaren Markdown-Link.
> 6. **Im Chat NICHTS weiter ausgeben** — keine Tabellen, keine Zahlen, keine Zusammenfassung.

## Begriffsklaerung: "Export"

- **Bei Analysefragen** bedeutet "Export" hier: BPLUS-Daten in die lokale DB synchronisieren.
- **Wenn der User explizit eine Datei moechte**, ist echter Datei-Export gemeint.
- **Excel-Export** bleibt erhalten und laeuft NICHT ueber `budget_db.py`.

## Analyse-Beispiele

```bash
python .agents/skills/skill-budget-bplus-export/report_bplus.py --firma edag
python .agents/skills/skill-budget-bplus-export/report_bplus.py --status bestellt
python .agents/skills/skill-budget-bplus-export/report_bplus.py --ea 0043402
python .agents/skills/skill-budget-bplus-export/report_bplus.py --projekt MEB
python .agents/skills/skill-budget-bplus-export/report_bplus.py --oe EKEK/1
python .agents/skills/skill-budget-bplus-export/report_bplus.py --firma edag --status bestellt --top 5
```

## Status-Mapping

| API `workFlowStatus` | Anzeige-Status | Im Standard-Filter |
|---|---|---|
| `WF_Created` | 01_In Erstellung | Ja |
| `WF_In_process_BM_Team` | 06_In Bearbeitung BM-Team | Ja |
| `WF_In_Planen_BM` | 07_In Planen-BM: {detail} | Ja |
| `WF_Rejected` | 97_Abgelehnt | Ja |
| `WF_Canceled` | 98_Storniert | Ja |
| `WF_Archived` | 99_Archiviert | **Nein** (ausgeschlossen) |

## Darstellungsregeln (im Report)

Der Report enthaelt automatisch:
- **Einzelvorgaenge** als Markdown-Tabelle (Konzept, EA-Nummer, EA-Titel, BM-Titel, Wert, Firma, Status) mit Summenzeile
- **Status-Verteilung** als Tabelle + Mermaid Pie-Chart
- **Firmen-Verteilung** (wenn kein Firma-Filter aktiv)
- **EA-Verteilung** (wenn mehrere EAs)

## Excel-Export behalten

Wenn der User **explizit Excel** verlangt:

1. Analysepfad NICHT verwenden
2. Web-/Playwright-Pfad verwenden
3. In BPLUS auf **Export** → **Export als Excel** gehen
4. Ergebnisdatei nach `userdata/bplus/` verschieben
5. Erzeuge NIEMALS Bilder und schaue NIEMALS Bilder an.

Kurzregel:

- **Analysefrage** → `report_bplus.py`
- **"als Excel herunterladen"** → Web-/Playwright-Export

## API-Endpunkte

| Ressource | URL |
|---|---|
| BTL-Daten | `GET /ek/api/Btl/GetAll?year={year}` |

## Flexible SQL-Abfrage (budget_db.py query)

> Der Agent entscheidet SELBST, ob `report_bplus.py` oder `budget_db.py query` verwendet wird.
> Der User muss NICHT explizit "per SQL" sagen.

### Automatische Entscheidungslogik

**`report_bplus.py` verwenden wenn:**
- Einfacher Filter nach genau EINEM Kriterium (Firma, Status, EA, Projekt, OE)
- Der User fragt "Zeig mir alle BMs von Firma X" oder "Was hat Status bestellt?"
- Kein Vergleich, keine Aggregation, kein JOIN noetig

**`budget_db.py query --stdout --no-file --sync` verwenden wenn:**
- Aggregationen gefragt sind (SUM, COUNT, AVG, GROUP BY)
- Vergleiche oder Rankings ("Top 5", "groesste", "meiste", "Verteilung")
- Daten aus mehreren Tabellen kombiniert werden muessen (JOIN btl + devorder + el_planning)
- Komplexe WHERE-Bedingungen (AND/OR, Subqueries, HAVING)
- Der User nach Summen, Anteilen oder Verhältnissen fragt
- Die Frage nicht mit einem einzelnen report_bplus.py-Filter beantwortbar ist
- Der User explizit SQL oder eine freie Abfrage verlangt

### Workflow

1. **Schema erkunden** (einmalig pro Session):
   ```bash
   python scripts/budget/budget_db.py schema
   python scripts/budget/budget_db.py schema --table btl
   ```
2. **SQL ausfuehren**:
   ```bash
   python scripts/budget/budget_db.py query "SELECT ..." --stdout --no-file --sync
   ```
3. Ergebnis direkt aus stdout verwenden und dem User praesentieren.

### CLI-Flags fuer `query`

| Flag | Beschreibung |
|---|---|
| `--stdout` | Ergebnis (SQL + Tabelle + Zeilenanzahl) auf stdout ausgeben |
| `--no-file` | Kein Markdown-Report erzeugen (nur mit --stdout sinnvoll) |
| `--limit N` | Max. Zeilen auf stdout (Default: 200, 0=unbegrenzt). Markdown-Datei enthaelt immer ALLE Zeilen. |
| `--sync` | Referenzierte Tabellen vor Query synchronisieren (falls nicht fresh) |
| `--year Y` | Jahr fuer Auto-Sync (Default: aktuelles Jahr) |
| `--output PATH` | Pfad fuer Report-Datei (optional) |
| `--title TEXT` | Titel des Reports (Default: "Budget-Auswertung") |

### Tabellen-Uebersicht

| Tabelle | Inhalt | Wichtige Spalten |
|---|---|---|
| `btl` | Beschaffungsvorgaenge (BMs) | concept, dev_order, ea, title, planned_value, company, status, creator |
| `devorder` | Entwicklungsauftraege (EAs) | ea_number, title, project_family, date_from, date_until, controller |
| `el_planning` | Eigenleistungsplanung | user_name, ea_number, pct_jan..pct_dec, year_work_hours, hourly_rate |
| `stundensaetze` | Stundensaetze pro KST/OE | jahr, kst, oe, stundensatz |
| `ua_leiter` | UA-Leiter pro OE | oe, ebene, mail |

### Beispiel-Queries

```bash
# Top-10 Firmen nach Gesamtbudget
python scripts/budget/budget_db.py query "SELECT company, COUNT(*) AS anzahl, SUM(planned_value) AS summe FROM btl GROUP BY company ORDER BY summe DESC LIMIT 10" --stdout --no-file --sync

# Alle Vorgaenge einer bestimmten EA mit Status
python scripts/budget/budget_db.py query "SELECT title, planned_value, company, status FROM btl WHERE dev_order = '0043402'" --stdout --no-file

# Join: BMs mit EA-Details (Laufzeit, Projektfamilie)
python scripts/budget/budget_db.py query "SELECT b.concept, b.title, b.planned_value, b.company, d.project_family, d.date_until FROM btl b LEFT JOIN devorder d ON b.dev_order = d.ea_number ORDER BY b.planned_value DESC LIMIT 20" --stdout --no-file

# Status-Verteilung als Aggregation
python scripts/budget/budget_db.py query "SELECT status, COUNT(*) AS anzahl, SUM(planned_value) AS summe FROM btl GROUP BY status ORDER BY summe DESC" --stdout --no-file
```

### Sicherheit

- **Nur SELECT/CTE** erlaubt — INSERT, UPDATE, DELETE, DROP, ALTER, ATTACH, PRAGMA werden geblockt.
- SQL kommt als fertiger String — kein dynamisches SQL-Building noetig.

### Wichtig: Wann `report_bplus.py` vs. `query`

| Situation | Tool |
|---|---|
| Standard-Filter (Firma, Status, EA, Projekt, OE) | `report_bplus.py` |
| Aggregationen, JOINs, beliebige WHERE-Bedingungen | `budget_db.py query` |
| Joins ueber mehrere Tabellen (btl + devorder + el_planning) | `budget_db.py query` |
| User will explizit SQL-Abfrage | `budget_db.py query` |
| Verfuegbare Jahre | `GET /ek/api/Year` |


### Ausgabe bei SQL-Abfragen

- Bei `--stdout --no-file`: Ergebnis direkt im Chat an den User ausgeben (Tabelle + Interpretation).
- Bei `--stdout` (ohne `--no-file`): Zusaetzlich Report-Datei erzeugen und verlinken.
- **Im Gegensatz zu `report_bplus.py`** darf und soll der Agent die SQL-Ergebnisse direkt im Chat praesentieren.

Basis-URL: `https://bplus-ng-mig.r02.vwgroup.com`
