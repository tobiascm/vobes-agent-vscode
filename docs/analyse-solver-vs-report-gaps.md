# Analyse: Solver vs. Report — Ampellogik & Gaps

> Stand: 20.04.2026 — **Alle 6 Gaps geschlossen**

## 1. Ampelregeln im Excel-Report

### Gesamtübersicht — "Delta Ist vs. Target" (B8–F8)

| Bedingung | Farbe |
|---|---|
| `Ist > Target` (Überplanung) | Rot Schrift + Rosa Fill (`FFC7CE`) |
| `Ist < Target` (Unterplanung) | Schwarz Schrift + Grün Fill (`C6EFCE`) |
| `Ist == Target` | Keine Sonderfarbe |

Berechnung: `Delta = Σ area_te[area] − Σ TARGET_2026[area]` (aus `target.csv`).

### Firmen-Übersicht — DIFF Ges. (E29–E39)

Berechnung: `diff_planung = ist − soll` (in T€, gerundet).

**Soll-Kaskade** (3 Stufen, Priorität absteigend):

1. **Manual Override** — `*_Target_2026`-Spalte in `target.csv` (z.B. `Bertrandt_Target_2026`)
2. **Thiesen Spezial** — Summe der beiden Thiesen-Areas × 1000
3. **Proportional** — Firma-Anteil am Area-Ist × Area-Target, abzüglich Overrides

> Kein Cell-Fill — nur Excel-Number-Format `[Red]` für negative Werte.

### Firmen-Übersicht — DIFF Q1-2 (K29–K39)

Berechnung: `diff_q = soll_q − period_ist`.

- `period_ist = bestellt + durchlauf` (bei `num_q ≤ 2`)
- Ab Q3: `period_ist += konzept_quarters[Q3]`
- `soll_q` wird per `_scale_distribution_to_target` auf den Quartals-Split skaliert, dann ggf. durch `plan_company_targets` überschrieben

> Kein Cell-Fill — gleich wie DIFF Ges.

### Sondervereinbarungen — DIFF Ges. + DIFF Q1-2 (E42–K68)

Funktion `_diff_band_status(actual, target, ok_ratio=0.01, warn_ratio=0.10)`:

| Band | Bedingung | Fill |
|---|---|---|
| **OK** | `ratio < 1%` | Grün (`C6EFCE`) |
| **WARN** | `1% ≤ ratio ≤ 10%` | Gelb (`FFEB9C`) |
| **X** | `ratio > 10%` | Rot (`FFC7CE`) |
| **-** | Target = None | Grau (`D9D9D9`) |

- DIFF Ges.: `actual = sum_te` (alle Status), `target = fl_target_annual`
- DIFF Q1-2: `actual = bestellt_te + durchlauf_te`, `target = fl_target_period` (cadence-abhängig)

---

## 2. Solver-Constraints (Stage 2)

| Constraint | Typ | Beschreibung |
|---|---|---|
| Firmen-Jahressumme = Target | **HART** | `Σ(company, all Q) == hard_company_annual_target` |
| Firmen-Quartalswert ≈ Target | **WEICH** (Penalty 10) | `Σ(company, Q) + pos − neg == effective_target(Q)` |
| Sondervorgaben FL = Target | **HART** | `Σ(EAs) == rule.target_amount` |
| Sondervorgaben PMT Periode = Target | **HART** | `Σ(period EAs) == period_target` (nur PMT) |
| Bestellt-Floor | **HART** | `n_var >= ordered_units` |
| Im-Durchlauf-Schutz | **WEICH** (Penalty 2500×step) | Reduktion bestraft, nicht verboten |

---

## 3. Gap-Analyse

### Gap 1: Soll-Diskrepanz bei proportionaler Verteilung (4SOFT 974 vs. 854 T€)

- **Report** (`report_massnahmenplan.py`): Verteilt Area-Targets proportional nach `firm_area_ist`. Wenn eine Firma in einem Bereich keine BMs hat (z.B. RuleChecker in `btl_opt` vor Q3), wird das Target nicht zugewiesen.
- **Solver** (`beauftragungsplanung_core.py`): Nutzt `COMPANY_AREA_MAP` mit fester Zuordnung → RuleChecker (120 T€) zählt immer zu 4SOFT.
- **Auswirkung**: 4SOFT Soll = 854 T€ (Report) vs. 974 T€ (Solver). Gesamt-Soll: 4.313 vs. 4.433 T€.
- **Betroffene Zellen**: E29 (4SOFT DIFF Ges.), B8 (Gesamtübersicht Delta)
- **Fix**: Fallback auf `COMPANY_AREA_MAP` wenn Area-Ist für eine Firma leer.

### Gap 2: Quartals-Targets nur weich

- **Report**: Erwartet exakte Quartals-Einhaltung für grüne Ampel.
- **Solver**: Quartals-Constraints sind weich (Penalty 10 pro € Abweichung). Solver darf zugunsten des Gesamtoptimums Quartale verschieben.
- **Betroffene Zellen**: K29–K39 (DIFF Q1-2)
- **Fix**: `soft_target_penalty` erhöhen oder Quartals-Constraints für das aktuelle Quartal härten.

### Gap 3: Perioden-Constraint nur bei PMT

- **Report**: Bewertet DIFF Q1-2 per `_diff_band_status` für alle Sondervorgaben.
- **Solver**: Nur PMT hat `enforce_period_exact=True`. Digi-budget, VCTC, NE Space Crafter, NE ID Buzz AD haben keinen Perioden-Constraint.
- **Betroffene Zellen**: K42–K68 (Sonder DIFF Q1-2)
- **Fix**: `enforce_period_exact` für alle Sondervorgaben mit Perioden-Target aktivieren, oder weichen Perioden-Constraint einbauen.

### Gap 4: Status neuer Solver-Rows = "01_In Erstellung" (Konzept)

- **Report**: `period_ist = bestellt + durchlauf`. Konzept zählt erst ab Q3.
- **Solver**: Neue Rows in `btl_opt` bekommen `_status_for_new_planned_row()` → "01_In Erstellung" bzw. "02_Freigabe Kostenstelle" für das aktuelle Quartal. Das sind Konzept-Status und werden vom Report bei Q1-2 nicht als `period_ist` gezählt.
- **Betroffene Zellen**: K29–K39 (DIFF Q1-2 viel zu hoch)
- **Fix**: `_status_for_new_planned_row` sollte für das aktuelle Quartal einen Status setzen, der als "im Durchlauf" klassifiziert wird, oder der Report sollte Solver-Rows anders behandeln.

### Gap 5: Rundungsresiduen bei Sondervorgaben

- **Solver**: Arbeitet in Step-Units (z.B. step=1000 → 1 Unit = 1 T€). Exakte Constraint `== target_amount`.
- **Report**: `_diff_band_status` mit `ok_ratio=0.01`. Bei kleinem Target (z.B. 45 T€ VCTC): 1 T€ Abweichung = 2.2% → WARN.
- **Betroffene Zellen**: E42–E68
- **Fix**: Marginal. Ggf. `ok_ratio` anheben oder step-aware Rundung im Report.

### Gap 6: EL-Regeln nicht im Solver

- **Report**: IO/nIO-Hints prüfen EL-Targets (Stunden/T€), Quartalsweise EL, EL-Obergrenze.
- **Solver**: Plant nur FL, keine EL. EL wird separat über `el_change.py` geplant.
- **Betroffene Zellen**: IO/nIO-Spalte in Sondervereinbarungen
- **Fix**: Kein Solver-Fix nötig — EL muss separat stimmen.

---

## 4. Priorisierung & Status

| Prio | Gap | Status | Fix |
|---|---|---|---|
| **1** | #1 Soll-Diskrepanz (proportional vs. COMPANY_AREA_MAP) | ✅ Geschlossen | `COMPANY_AREA_MAP` Import + Fallback-Soll in `report_massnahmenplan.py` |
| **2** | #4 Status neuer Rows ("Konzept" statt "im Durchlauf") | ✅ Geschlossen | `_status_for_new_planned_row`: `q_num <= current_q` → `CURRENT_QUARTER_TODO_STATUS` |
| **3** | #3 Perioden-Constraint nur PMT | ✅ Geschlossen | `enforce_period_exact` für alle Regeln mit `period_target_te > 0` |
| **4** | #2 Quartals-Softness | ✅ Geschlossen | `soft_target_penalty` 10→100 (DEFAULT_RULE_ROWS + rules.csv + Fallback) |
| **5** | #5 Rundungsresiduen | ✅ Geschlossen | `ok_ratio` 0.01→0.025 in `_diff_band_status` |
| **6** | #6 EL nicht im Solver | ✅ Out of scope | Separate EL-Planung über `el_change.py` |

### Zusätzliche Fixes (Session 20.04.2026)

| Fix | Beschreibung |
|---|---|
| Import-Bug | `report_massnahmenplan.py`: Try-Block gesplittet, 5 Helper-Funktionen auf Modul-Level verschoben |
| Firm-Farben | `cell_statuses` mit `_diff_band_status` für Firmen-Rows (DIFF Ges. + DIFF Q1-2) |
| EDAG/AUDI | `EDAG_Target_2026=1088` direkt in target.csv (analog Bertrandt), AUDI_AREA-Sonderlogik entfernt |
| Bootstrap-Guard | `_bootstrap_company_targets` refresht immer aus CSV (`ON CONFLICT DO UPDATE`) |
| Penalty-Inkonsistenz | `soft_target_penalty` konsistent auf 100 in SolverConfig, DEFAULT_RULE_ROWS, load_solver_config Fallback, rules.csv |

### Verbleibende Q1-2 Quartalsabweichungen (strukturell, kein Code-Bug)

Q1-2 DIFF-Zellen für Firmen bleiben ROT/GELB wegen struktureller Constraints:
- Q1 ist Vergangenheit → BMs eingefroren (echte BPLUS-Daten, nicht änderbar)
- Area-Starttermine: RuleChecker (4SOFT, 120 T€) startet erst Q3, aber Q1-2 Soll enthält proportionalen Anteil
- Solver optimal in 30s mit Penalty=100 → Quartals-Verteilung ist bereits bestmöglich

### E2E-Ergebnis (20.04.2026)

```
Solver: optimal, 30.4s, Objective 107.674.050
Firmen: Alle 7 aktive → DIFF Ges. = 0 (GRÜN)
Sonder: Alle 5 → DIFF Ges. + Q1-2 = GRÜN
Gesamt: Soll=Ist=4.433 T€, DIFF=0
Ampel: GRÜN=17, GELB=2, ROT=5, GRAU=4
```
