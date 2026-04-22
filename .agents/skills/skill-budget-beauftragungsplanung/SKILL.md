---
name: skill-budget-beauftragungsplanung
description: Beauftragungsplanung fuer Fremdvergaben auf Basis von SQLite + Excel-Config. Nutzt vorhandene BPLUS-Syncs (`budget_db.py`) maximal weiter, schreibt Stage-1/Stage-2-Ergebnisse in `budget.db`, materialisiert den letzten Optimierungsvorschlag nach `btl_opt` und stoesst danach automatisch die Target-Ist-Analyse auf `btl_opt` an. Verwenden fuer Anfragen wie Beauftragungsplanung, Fremdvergaben planen, Firma x Gewerk x Quartal auf EA verteilen, Referenzbeauftragungen nutzen, Stage 1/Stage 2 Budgetplanung.
---

# Skill: Beauftragungsplanung

Dieser Skill erstellt eine **zweistufige Beauftragungsplanung** fuer Fremdvergaben:

1. **Stage 1** bestimmt sinnvolle **EA-Jahresziele**
2. **Stage 2** verteilt diese auf **Firma x Gewerk x Quartal** mit **harten Quartalswerten** und **Schrittweiten**

Der Skill ist bewusst so gebaut, dass er **maximal mit der bestehenden Budget-Infrastruktur synergiert**:

- gleiche SQLite-DB: `userdata/budget.db`
- gleiche Report-Helfer: `scripts/budget/report_utils.py`
- gleiche Session-Reports: `userdata/sessions/`
- gleiche Sync-Mechanik ueber `scripts/budget/budget_db.py`
- gleiche Test-Logik via `pytest`

## Wann verwenden?

- Der User moechte eine **Beauftragungsplanung** fuer Fremdvergaben
- Der User moechte **Firma x Gewerk x Quartal** auf **EA** verteilen
- Der User erwaehnt **Referenzbeauftragungen**, **Schrittweiten**, **Quartalscaps**, **bestehende Beauftragungen**
- Der User moechte **moeglichst wenige Einzelbeauftragungen**
- Der User moechte **nicht in jedem Quartal dieselben EA** belasten

## Wann NICHT verwenden?

| Aufgabe | Stattdessen |
|---|---|
| Reine BTL-Auswertung / Abrufe / BM-Uebersicht | `$skill-budget-bplus-export` |
| EA-Stammdaten / DevOrders | `$skill-budget-ea-uebersicht` |
| EL-Planung / Mitarbeiterbuchung | `$skill-budget-eigenleistung-el` |
| Stundensaetze | `$skill-budget-stundensaetze` |

## Pflicht: Nur das Planungs-Script verwenden

> **WICHTIG:** Fuer Beauftragungsplanung immer **nur** dieses Script aufrufen:
>
> `python .agents/skills/skill-budget-beauftragungsplanung/report_beauftragungsplanung.py --jahr 2026`
>
> Der Agent soll **nicht** manuell in SQLite rechnen und **nicht** manuell aggregieren.
> Alle Summen, Stage-1-Ziele und Stage-2-Verteilungen muessen aus dem Python-Script kommen.

## Datenhaltung

Der Skill verwendet dieselbe DB `userdata/budget.db` und legt dort zusaetzlich eigene Tabellen an:

- `plan_company_targets`
- `plan_existing_orders`
- `plan_reference_orders`
- `plan_group_rules`
- `plan_group_members`
- `plan_ea_metadata`
- `plan_stage1_results`
- `plan_stage2_results`
- `plan_run_log`

### Was bleibt wo?

**In SQLite:**
- Referenzbeauftragungen
- bestehende Beauftragungen
- Stage-1-Ergebnisse
- Stage-2-Ergebnisse
- letzter Optimierungsvorschlag in `btl_opt`

**In Excel-Config** (`userdata/budget/planning/beauftragungsplanung_config.xlsx`):
- Sheet "Solver-Parameter": Gewichte, Strafkosten, Modus-Flags
- Sheet "Firmenziele": Jahresziel T€, Quartalsverteilung, Schrittweiten pro Firma
- Sheet "Sondervorgaben": Themen mit EA-Zuordnung, Kadenz, erlaubte/priorisierte Firmen
- Sheet "Praemissen": Freitext-Notizen

## Standard-Workflow

### 1. Einmalig initialisieren

```bash
python .agents/skills/skill-budget-beauftragungsplanung/report_beauftragungsplanung.py --init
```

Das macht:
- Planungsschema in `budget.db` anlegen
- Default-Config-Excel erzeugen, falls sie noch fehlt

### 2. Eingabedaten in SQLite pflegen

Pflichtdaten:
- `plan_company_targets` oder Auto-Bootstrap aus Config-Excel Sheet "Firmenziele"
- `plan_existing_orders` oder Auto-Bootstrap aus `btl`
- `plan_reference_orders` oder Auto-Bootstrap aus `btl_all` mit Status `07_In Planen-BM: Bestellt`
- optional Gruppenregeln in `plan_group_rules` / `plan_group_members`

### 3. Planung rechnen

```bash
python .agents/skills/skill-budget-beauftragungsplanung/report_beauftragungsplanung.py --jahr 2026
```

Optional:
```bash
python .agents/skills/skill-budget-beauftragungsplanung/report_beauftragungsplanung.py --jahr 2026 --config userdata/budget/planning/beauftragungsplanung_config.xlsx --output userdata/sessions/planung_2026.md
```

Fuer Debug-/Testzwecke kann die Planung trotz aktuellem Datum auf das gesamte Jahr erweitert werden:

```bash
python .agents/skills/skill-budget-beauftragungsplanung/report_beauftragungsplanung.py --jahr 2026 --volljahr
```

Die Behandlung harter Sondervorgaben ist per CLI steuerbar:

```bash
python .agents/skills/skill-budget-beauftragungsplanung/report_beauftragungsplanung.py --jahr 2026 --sondervorgaben-mode catchup
python .agents/skills/skill-budget-beauftragungsplanung/report_beauftragungsplanung.py --jahr 2026 --sondervorgaben-mode strict
```

Standard ist `catchup`:
- Quartals-/Halbjahres-Unterdeckung wird als Warnung protokolliert
- Restmengen werden automatisch in spaetere erlaubte Quartale verschoben
- wenn Jahres-Sondervorgaben mit den Quartalstargets kollidieren, haben die Quartalstargets Vorrang; die Jahresabweichung wird als Warnung protokolliert

## Was das Script automatisch macht

- legt das Planungsschema an
- liest die Config-Excel
- synchronisiert bei Bedarf `devorder` und `btl` ueber das bestehende `budget_db.py`
- bootstrapped Firmen-/Gewerk-Targets aus Config-Excel Sheet "Firmenziele"
- bootstrapped bestehende Positionen aus `btl`, wenn `plan_existing_orders` leer ist
- bootstrapped Referenzen aus `btl_all` mit Status `07_In Planen-BM: Bestellt`, wenn `plan_reference_orders` leer ist
- berechnet Stage 1
- berechnet Stage 2
- schreibt Stage-1- und Stage-2-Ergebnisse nach `budget.db`
- loescht `btl_opt` vor jedem Lauf komplett und schreibt den aktuellen Optimierungsvorschlag neu hinein
- schreibt einen Markdown-Bericht nach `userdata/sessions/`
- stoesst danach automatisch die Target-Ist-Analyse gegen `btl_opt` an
- gibt **nur den Pfad** zum Bericht auf stdout aus

## Ergebnis-Ausgabe im Chat

Nach erfolgreichem Lauf im Chat **nur**:

`Den Ergebnisbericht habe ich erstellt und hier fuer Dich abgelegt:` gefolgt von einem klickbaren Markdown-Link.

Keine manuelle Nachrechnung, keine zweite Tabelle im Chat.

## Stage-1-Logik

Stage 1 ist bewusst **heuristisch und schlank**:

- nutzt bestehenden Bestand als Floor
- nutzt Referenzen als Attraktivitaet / Priorisierung
- bevorzugt wenige aktive EA
- verteilt Restbudget chunk-basiert
- gibt **weiche** EA-Jahresziele aus
- markiert harte Einzelziele nur dort, wo sie fachlich explizit hart sind

## Stage-2-Logik

Stage 2 verwendet ausschliesslich **HiGHS via `highspy`**. Es gibt keinen Heuristik-Fallback.

Die Quartalssteuerung orientiert sich an der realen Budget-Sicht **Q1-X**:

- Config-Excel Sheet "Firmenziele" liefert die Jahresziele und Quartalsverteilung pro Firma
- fuer die Planung werden daraus **interne Einzelquartale Q1..Q4** abgeleitet
- die Steuerungslogik bleibt dabei kompatibel zur kumulierten Budget-Sicht `Q1-X`
- standardmaessig werden bereits vergangene Quartale eingefroren; mit `--volljahr` laesst sich das fuer Debug/Test abschalten
- standardmaessig laufen Sondervorgaben im Modus `catchup`; mit `--sondervorgaben-mode strict` werden Quartals-/Halbjahresregeln wieder hart erzwungen

### Harte Regeln in Stage 2

- Firmenzielwerte pro Quartal
- Schrittweiten je Firma/Gewerk
- fixe bestehende Beauftragungen
- harte Gruppensummen
- harte Einzelziele aus Gruppenregeln

### Weiche Regeln in Stage 2

- Stage-1-Ziele pro EA
- wenige aktive EA pro Quartal
- wenige Einzelbeauftragungen
- Rotation der EA zwischen Quartalen
- Stoppen laufender Positionen nur mit hoher Strafe

## Config-Excel

Die erzeugte Datei `userdata/budget/planning/beauftragungsplanung_config.xlsx` enthaelt 4 Sheets:

### Sheet "Solver-Parameter"
Key-Value-Paare (Parameter / Wert / Standard / Beschreibung). Fehlende Keys werden mit Standardwerten ergaenzt.

### Sheet "Firmenziele"
Firma / Jahresziel_TE / Q1 / Q2 / Q3 / Q4 / Schrittweite. Quartale als Anteil (0.25 = 25%).

### Sheet "Sondervorgaben"
Thema / EA / EL / FL / Kadenz / Erlaubte_Firmen / Prioritaet_Firmen / Bemerkung / Hinweise.

### Sheet "Praemissen"
Freitext in Zelle A1.

## Wichtige Grenzen / Ehrlichkeit

- Wenn `target_value` nicht durch `step_value` teilbar ist, bricht der Lauf mit Fehler ab
- Wenn harte bestehende Beauftragungen ein Quartalsziel bereits ueberfuellen, wird das offen gemeldet
- Wenn `plan_stage1_results` fuer das Jahr leer ist, bricht der Lauf mit Fehler ab

## Beispiele fuer Eingabe-Fragen

- „Erstelle eine Beauftragungsplanung fuer 2026.“
- „Verteile Firma x Gewerk x Quartal auf EA mit moeglichst wenigen Einzelbeauftragungen.“
- „Nutze Referenzbeauftragungen aus BTL als Orientierung.“
- „Plane so, dass pro Quartal nur wenige EA aktiv sind.“

## Technische Dateien

- `.agents/skills/skill-budget-beauftragungsplanung/SKILL.md`
- `.agents/skills/skill-budget-beauftragungsplanung/report_beauftragungsplanung.py`
- `scripts/budget/beauftragungsplanung_core.py`
- `scripts/budget/planning_config_io.py`
- `tests/test_beauftragungsplanung.py`
