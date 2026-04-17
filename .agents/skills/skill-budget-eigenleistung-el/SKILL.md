---
name: skill-budget-eigenleistung-el
description: Eigenleistungsplanung (EL) aus BPLUS-NG abrufen und mit Fremdleistung kombinieren. Analysefragen laufen ueber report_el.py auf Basis der lokalen SQLite-DB. Das Script erzeugt strukturierte Berichte, schreibt Logs und faellt bei Sync-Fehlern auf vorhandene DB-Daten mit Warnhinweis zurueck. Nutze diesen Skill fuer Fragen wie "Auf welche EAs bucht ein Mitarbeiter seine Stunden?", "Welche geplanten EAs sind noch mit Buchungssperren?", "Jahressicht Eigenleistung pro EA", oder "EL vs. Fremdleistung Gesamtuebersicht".
---

# Skill: BPLUS-NG Eigenleistung (EL) — Planung, Analyse & sichere Aenderung

## Kontext

- **Standard-OE:** EKEK/1 (OrgUnit-ID: 161)
- **Standard-Jahr:** Automatisch aktuelles Jahr (optional mit `--jahr` setzen)

## Wann verwenden?

- User fragt nach **Eigenleistungsplanung** oder **EL-Planung**
- User fragt **"Auf welche EA bucht [Mitarbeitername]?"**
- User fragt nach **Buchungssperren** oder **blockierten EAs**
- User moechte **Jahressicht Eigenleistung** (EUR pro EA)
- User moechte **EL vs. Fremdleistung Vergleich** pro EA
- User moechte **bestehende EL-Monate** einer vorhandenen EA-Zeile aendern oder auf `0` setzen
- Keywords: `EL`, `Eigenleistung`, `auf welche EA`, `Buchungssperren`, `gesperrt`, `Planung`

## Disambiguierung

**"Auf welche EA bucht X?"** hat zwei Interpretationen:

1. **X = Mitarbeitername** (z.B. "Bachmann") → **dieser Skill** (EL-Planung)
2. **X = Firmenname** (z.B. "Mustermann GmbH") → `skill-budget-bplus-export` (BTL-Daten, Feld `company`)

Bei Unsicherheit: User fragen, ob Mitarbeiterbuchung (EL) oder Firmenbuchung (Fremdleistung/BTL) gemeint ist.

## Pflicht: Analyse-Script verwenden

> **WICHTIG:** Bei EL-Analysefragen IMMER `report_el.py` verwenden.
> Das Script muss bei JEDER Anfrage neu ausgefuehrt werden.
> Es synchronisiert `el_planning` bei Bedarf selbst, fuer `gesamt-uebersicht` zusaetzlich `btl`.
>
> **Workflow:**
> 1. `python .agents/skills/skill-budget-eigenleistung-el/report_el.py --usecase ...`
> 2. Das Script schreibt IMMER eine Ergebnis-Datei nach `userdata/sessions/`.
> 3. Das Script gibt NUR den Pfad zur Ergebnis-Datei auf stdout aus.
> 4. **NUR folgenden Satz im Chat an den User ausgeben:**
>    `Den Ergebnisbericht habe ich erstellt und hier fuer Dich abgelegt:` gefolgt von einem klickbaren Markdown-Link.
> 5. **Im Chat NICHTS weiter ausgeben** — keine Tabellen, keine Zahlen, keine Zusammenfassung.
> 6. Bei Sync-/Timeout-Problemen nutzt es vorhandene DB-Daten weiter und schreibt Warnhinweise in den Bericht.
> 7. Logs liegen unter `userdata/tmp/logs/`.

## Pflicht: Aenderungs-Script fuer bestehende EA-Zeilen verwenden

> **WICHTIG:** Bei EL-Aenderungen an einer **bestehenden EA-Zeile** IMMER `el_change.py` verwenden.
>
> **Standardverhalten:**
> 1. Default ist **dry-run**
> 2. Ein echter Write passiert **nur** mit `--apply`
> 3. Das Script schreibt IMMER einen Markdown-Bericht nach `userdata/sessions/`
> 4. Das Script gibt NUR den Pfad zur Ergebnis-Datei auf stdout aus
> 5. Nach `--apply` erfolgt immer ein **Readback** gegen BPLUS
>
> **v1-Scope:**
> - `set-months`: ausgewaehlte Monate einer bestehenden EA-Zeile setzen
> - `reset-ea`: alle Monate einer bestehenden EA-Zeile auf `0` setzen
>
> **Nicht in v1 enthalten:**
> - EA-Zuordnung hinzufuegen
> - EA-Zuordnung loeschen
> - Person zuweisen / Planungsposition / Transfer

## Use Cases

### 1. MA-Planung: "Auf welche EAs bucht ein Mitarbeiter?"

```bash
python .agents/skills/skill-budget-eigenleistung-el/report_el.py --usecase ma-planung --mitarbeiter "Bachmann, Armin"
```

Output: Tabelle pro Mitarbeiter mit EA-Nummer, EA-Titel, Projektfamilie, Avg %, Sperrungen, Jahresstunden, Stundensatz.

### 2. Buchungssperren: "Welche geplanten EAs sind gesperrt?"

```bash
python .agents/skills/skill-budget-eigenleistung-el/report_el.py --usecase buchungssperren
```

Output: Alle MA mit Buchungssperren, EA-Zuordnung und gesperrte Monate.

### 3. Jahressicht: "Wie viel EL pro EA (EUR)?"

```bash
python .agents/skills/skill-budget-eigenleistung-el/report_el.py --usecase jahressicht
```

Output: Aggregation pro EA ueber alle MA. Formel: Summe(Prozente x Jahresstunden x Stundensatz).

### 4. Gesamt-Uebersicht: "EL vs. Fremdleistung pro EA"

```bash
python .agents/skills/skill-budget-eigenleistung-el/report_el.py --usecase gesamt-uebersicht
```

Output: Join EL-Planungsdaten + BTL-Abrufe (Fremdleistung) auf EA-Nummer. Mermaid Pie-Chart EL vs. Fremdleistung.

## Use Cases: EL aendern

### 5. Einzelne Monate einer bestehenden EA-Zeile setzen

```bash
python .agents/skills/skill-budget-eigenleistung-el/el_change.py --year 2026 set-months --mitarbeiter "Mueller, Tobias Carsten" --ea 0048207 --months apr,may,jun,jul --value 0
```

Dry-run mit Delta-Vorschau und Write-Endpoint im Bericht.

### 6. Einzelne Monate wirklich schreiben

```bash
python .agents/skills/skill-budget-eigenleistung-el/el_change.py --year 2026 --apply set-months --mitarbeiter "Mueller, Tobias Carsten" --ea 0048207 --months apr,may,jun,jul --value 0
```

Fuehrt den Write aus und verifiziert danach die Zielmonate per Readback.

### 7. Ganze EA-Zeile auf 0 setzen

```bash
python .agents/skills/skill-budget-eigenleistung-el/el_change.py --year 2026 reset-ea --mitarbeiter "Mueller, Tobias Carsten" --ea 0048207
```

Setzt in dry-run alle Monate auf `0`.

### 8. Ganze EA-Zeile auf 0 setzen und schreiben

```bash
python .agents/skills/skill-budget-eigenleistung-el/el_change.py --year 2026 --apply reset-ea --mitarbeiter "Mueller, Tobias Carsten" --ea 0048207
```

## Verhalten / Guardrails

- Mitarbeiter-Match: erst exakter Name, dann eindeutiger Teilstring
- EA-Match: erst exakte EA-Nummer, dann eindeutiger Treffer in Beschreibung
- Mehrdeutige Treffer fuehren zum Abbruch
- Ohne `--apply` wird **nie** geschrieben
- Write-Pfad in v1: `POST /ek/api/PlanningException/UpdatePlanningExceptions`
- Das Script arbeitet auf Basis des kompletten `GetPlanningExceptionsForUser`-Payloads und aendert nur die Zielmonate der gematchten EA-Zeile

## API-Endpunkte

| Endpunkt | URL | Beschreibung |
|---|---|---|
| EmployeeHours | `GET /ek/api/EmployeeHours?orgUnitId=161&year={year}` | Alle MA + Wochenstunden |
| PlanningException | `GET /ek/api/PlanningException/GetPlanningExceptionsForUser?userId={id}&year={year}&orgUnitId=161` | EA-Zuordnungen + Monats-Prozente pro MA |
| PlanningException Update | `POST /ek/api/PlanningException/UpdatePlanningExceptions` | Schreibt geaenderte Monatswerte fuer bestehende EA-Zeilen |

Basis-URL: `https://bplus-ng-mig.r02.vwgroup.com`
