---
name: skill-budget-eigenleistung-el
description: Eigenleistungsplanung (EL) aus BPLUS-NG abrufen und mit Fremdleistung kombinieren. Analysefragen laufen ueber report_el.py auf Basis der lokalen SQLite-DB. Bestehende EL-Monate aendern, auf 0 setzen oder Rebalancing durchfuehren ueber el_change.py (Schreibzugriff auf BPLUS-NG). Monate koennen nur ab dem aktuellen Monat geaendert werden, nicht rueckwirkend. Nutze diesen Skill fuer Fragen wie "Auf welche EAs bucht ein Mitarbeiter seine Stunden?", "Welche geplanten EAs sind noch mit Buchungssperren?", "Jahressicht Eigenleistung pro EA", "EL vs. Fremdleistung Gesamtuebersicht", "EL auf 0 setzen", "EL aendern" oder "EL in BPLUS schreiben".
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
> 3. Das Script schreibt IMMER einen Markdown-Bericht nach `userdata/sessions/`. Der Dateiname endet auf `_dryrun.md` bzw. `_apply.md`, sodass beide Laeufe nebeneinander existieren.
> 4. stdout enthaelt zwei Zeilen: Zeile 1 ist die Tab-separierte STATUS-Zeile, Zeile 2 der absolute Pfad zum Markdown-Bericht.
> 5. Nach `--apply` erfolgt immer ein **Readback** gegen BPLUS
>
> **stdout-Format (Zeile 1):**
> `STATUS\tMODE=dryrun|apply\tREADBACK=ok|failed|n/a\tCHANGES=<int>\tBLOCKED=<int>\tRUN_ID=<hex>\tPATH=<abs>`
>
> Bei Fehlern schreibt das Script stattdessen eine `STATUS`-Zeile mit `READBACK=failed` und `ERROR=<kurzmsg>` auf **stderr** (plus die vollstaendige Fehlermeldung) und beendet sich mit Exit 1.
>
> **Agent-Workflow:**
> 1. STATUS-Zeile parsen und pruefen.
> 2. **Dry-Run (MODE=dryrun):** Den Markdown-Bericht lesen und die Aenderungstabelle(n) im Chat anzeigen, damit der User die geplanten Aenderungen sofort sieht. Danach fragen, ob mit `--apply` geschrieben werden soll.
> 3. **Apply (MODE=apply, READBACK=ok):** Den Satz `Den Ergebnisbericht habe ich erstellt und hier fuer Dich abgelegt:` mit klickbarem Markdown-Link zum Pfad ausgeben. Zusaetzlich eine kurze Zusammenfassung (Anzahl Aenderungen, betroffene EAs) im Chat zeigen.
> 4. Bei `READBACK=failed` den `ERROR`-Wert und ggf. die erste Section des Berichts ("Status") im Chat zeigen und nicht einfach weiterlaufen.
> 5. Wenn der User im EKEK/1-Workspace keinen Mitarbeiternamen nennt, zuerst `$skill-orga-ekek1` lesen und den Default-Mitarbeiter aus `orga.md` im Abschnitt `Eigene Rolle` ableiten.
>
> **v2-Scope:**
> - `set-months`: ausgewaehlte Monate einer bestehenden EA-Zeile setzen
> - `reset-ea`: alle Monate einer bestehenden EA-Zeile auf `0` setzen
> - `plan-changes`: mehrere EA-Aenderungen und optionales Rebalancing in einem Lauf
>
> **Buchungsrecht-Sperren:**
> - Gesperrte Monate duerfen auf `0` gesetzt werden, wenn der resultierende Gesamt-Payload konsistent bleibt.
> - Das gilt fuer `reset-ea`, `plan-changes --zero-ea` und `set-months --value 0`.
> - Andere Zielwerte auf gesperrten Monaten bleiben blockiert.
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
Gesperrte Monate duerfen dabei ebenfalls auf `0` gesetzt werden; die Monatssummen muessen danach trotzdem konsistent bleiben.

### 8. Ganze EA-Zeile auf 0 setzen und schreiben

```bash
python .agents/skills/skill-budget-eigenleistung-el/el_change.py --year 2026 --apply reset-ea --mitarbeiter "Mueller, Tobias Carsten" --ea 0048207
```

### 9. Standardfall: ab aktuellem Monat EAs auf 0 setzen und andere hochziehen

```bash
python .agents/skills/skill-budget-eigenleistung-el/el_change.py --year 2026 plan-changes --mitarbeiter "Mueller, Tobias Carsten" --zero-ea 0000170
```

Default:
- Aenderungen nur ab aktuellem Monat bis Jahresende
- offene/in `devorder` aktive EAs bevorzugen
- gesperrte Monate duerfen fuer `--zero-ea` auf `0` gesetzt werden
- `--rebalance` ist bei `--zero-ea` automatisch aktiv; mit `--no-rebalance` kann es explizit abgeschaltet werden
- Referenz-Preset default: `btl_all_ek`

### 10. Mehrere EAs manuell erhoehen / verringern

```bash
python .agents/skills/skill-budget-eigenleistung-el/el_change.py --year 2026 plan-changes --mitarbeiter "Mueller, Tobias Carsten" --increase-ea 0043898=1 --decrease-ea 0000163=1
```

### 11. Mehrere Mitarbeiter in einem Lauf

```bash
python .agents/skills/skill-budget-eigenleistung-el/el_change.py --year 2026 --apply plan-changes --mitarbeiter "Mueller, Tobias Carsten" --mitarbeiter "Bachmann, Armin" --zero-ea 0000170
```

## Fast Path fuer typische User-Formulierungen

- Formulierung `EL ... auf null setzen` plus **eine** EA ueber die ganze Zeile:
  `reset-ea`
- Formulierung `EL ... auf null setzen` plus **mehrere** EAs:
  `plan-changes --zero-ea ...`
- Formulierung `in BPlus schreiben`, `wirklich schreiben`, `speichern`:
  immer `--apply`
- Fehlendes Jahr:
  aktuelles Jahr
- Fehlender Mitarbeiter im EKEK/1-Workspace:
  zuerst `$skill-orga-ekek1` lesen und aus `.agents/skills/skill-orga-ekek1/orga.md` den aktuellen User aus `Eigene Rolle` aufloesen; in diesem Workspace ist das `Mueller, Tobias Carsten`
- Fehlende Monate bei `plan-changes`:
  aktueller Monat bis Dezember

## Beispiel fuer den hier typischen Standardfall

User-Formulierung:
`Bitte die EL 0000170, 0000237, 0000268, 0000505, 0000506, 0087795 auf null setzen und in BPlus schreiben.`

Agent-Ableitung:
- mehrere EAs -> `plan-changes --zero-ea`
- `in BPlus schreiben` -> `--apply`
- kein Mitarbeiter genannt -> `Mueller, Tobias Carsten` aus `$skill-orga-ekek1`
- keine Monate genannt -> aktueller Monat bis Dezember

```bash
python .agents/skills/skill-budget-eigenleistung-el/el_change.py --year 2026 --apply plan-changes --mitarbeiter "Mueller, Tobias Carsten" --zero-ea 0000170 --zero-ea 0000237 --zero-ea 0000268 --zero-ea 0000505 --zero-ea 0000506 --zero-ea 0087795
```

## Verhalten / Guardrails

- Mitarbeiter-Match: erst exakter Name, dann eindeutiger Teilstring
- EA-Match: erst exakte EA-Nummer, dann eindeutiger Treffer in Beschreibung
- Mehrdeutige Treffer fuehren zum Abbruch
- Ohne `--apply` wird **nie** geschrieben
- Es duerfen **nie** Monate vor dem aktuellen Monat geaendert werden
- Das Script schlaegt keine rueckwirkenden Aenderungen vor und fuehrt auch keine aus
- Fuer alle betroffenen Monate muss die resultierende Monatssumme **exakt 100** sein
- Wenn eine Aenderung zu Monatssummen ungleich `100` fuehrt, bricht das Script mit Fehlermeldung ab und schreibt nicht
- Buchungsrecht-gesperrte Monate duerfen nur dann beschrieben werden, wenn der Zielwert `0` ist
- Nach jedem echten Write erfolgt immer ein **Readback**
- Auch das Readback prueft zusaetzlich wieder die Monatssummen auf `100`
- Nach Dry-run und Apply wird `scripts/hooks/notify.ps1` mit dem Ergebnis aufgerufen
- Write-Pfad in v1: `POST /ek/api/PlanningException/UpdatePlanningExceptions`
- Das Script arbeitet auf Basis des kompletten `GetPlanningExceptionsForUser`-Payloads und aendert nur die Zielmonate der gematchten EA-Zeile

## API-Endpunkte

| Endpunkt | URL | Beschreibung |
|---|---|---|
| EmployeeHours | `GET /ek/api/EmployeeHours?orgUnitId=161&year={year}` | Alle MA + Wochenstunden |
| PlanningException | `GET /ek/api/PlanningException/GetPlanningExceptionsForUser?userId={id}&year={year}&orgUnitId=161` | EA-Zuordnungen + Monats-Prozente pro MA |
| PlanningException Update | `POST /ek/api/PlanningException/UpdatePlanningExceptions` | Schreibt geaenderte Monatswerte fuer bestehende EA-Zeilen |

Basis-URL: `https://bplus-ng-mig.r02.vwgroup.com`
