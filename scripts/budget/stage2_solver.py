"""Stage-2 MIP-Solver fuer Beauftragungsplanung via HiGHS."""
from __future__ import annotations

import logging
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import highspy

from beauftragungsplanung_core import (
    PlanningError,
    QUARTERS,
    raw_status_from_note,
    status_label_for_raw_status,
)


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SolverConfig:
    activation_penalty: float = 100.0
    quarter_activation_penalty: float = 50.0
    min_new_order_amount: int = 10000
    repeat_quarter_penalty: float = 200.0
    stop_penalty: float = 500.0
    large_order_penalty: float = 700.0
    large_order_threshold: int = 40000
    existing_small_amount_penalty: float = 10000.0  # reserved, currently unused
    soft_target_penalty: float = 100.0
    soft_target_overshoot_penalty: float = 10.0
    active_ea_cap_per_quarter: int = 0
    hard_need_bonus: float = 50.0
    throughlauf_change_penalty: float = 2500.0
    special_rule_priority_penalty_step: float = 25.0
    special_rule_annual_penalty: float = 500.0
    global_quarter_undershoot_penalty: float = 500.0
    global_quarter_overshoot_penalty: float = 5.0
    enforce_annual_consistency: bool = True
    time_limit_seconds: float = 120.0


@dataclass(slots=True)
class SolverSummary:
    status: str
    objective_value: float
    runtime_seconds: float
    hard_constraints: int
    soft_constraints: int
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Stage2Solution:
    run_id: str
    rows: list[dict[str, Any]]
    summary: SolverSummary


def _as_float(rules: dict[str, str], key: str, default: float) -> float:
    value = rules.get(key, str(default)).strip()
    try:
        return float(value.replace(",", "."))
    except (ValueError, TypeError):
        raise PlanningError(f"Solver-Parameter '{key}' hat ungueltigen Wert: '{value}' (Zahl erwartet)")


def _as_int(rules: dict[str, str], key: str, default: int) -> int:
    return int(round(_as_float(rules, key, float(default))))


def _as_bool(rules: dict[str, str], key: str, default: bool) -> bool:
    value = rules.get(key, "true" if default else "false").strip().lower()
    return value in {"1", "true", "yes", "ja", "y"}


def load_solver_config(rules: dict[str, str]) -> SolverConfig:
    solver_name = rules.get("stage2_solver", "highs").strip().lower()
    if solver_name != "highs":
        raise PlanningError(f"Nur stage2_solver=highs wird unterstuetzt, nicht {solver_name!r}.")
    return SolverConfig(
        activation_penalty=_as_float(rules, "stage2_activation_penalty", 100.0),
        quarter_activation_penalty=_as_float(rules, "stage2_quarter_activation_penalty", 50.0),
        min_new_order_amount=_as_int(rules, "stage2_min_new_order_amount", 10000),
        repeat_quarter_penalty=_as_float(rules, "stage2_repeat_quarter_penalty", 200.0),
        stop_penalty=_as_float(rules, "stage2_stop_penalty", 500.0),
        large_order_penalty=_as_float(rules, "stage2_large_order_penalty", 700.0),
        large_order_threshold=_as_int(rules, "stage2_large_order_threshold", 40000),
        existing_small_amount_penalty=_as_float(rules, "stage2_existing_small_amount_penalty", 10000.0),
        soft_target_penalty=_as_float(rules, "stage2_soft_target_penalty", 100.0),
        active_ea_cap_per_quarter=_as_int(rules, "stage2_active_ea_cap_per_quarter", 0),
        hard_need_bonus=_as_float(rules, "stage2_hard_need_bonus", 50.0),
        throughlauf_change_penalty=_as_float(rules, "stage2_throughlauf_change_penalty", 2500.0),
        special_rule_priority_penalty_step=_as_float(rules, "stage2_special_rule_priority_penalty_step", 25.0),
        special_rule_annual_penalty=_as_float(rules, "stage2_special_rule_annual_penalty", 500.0),
        global_quarter_undershoot_penalty=_as_float(rules, "stage2_global_quarter_undershoot_penalty", 500.0),
        global_quarter_overshoot_penalty=_as_float(rules, "stage2_global_quarter_overshoot_penalty", 5.0),
        soft_target_overshoot_penalty=_as_float(rules, "stage2_soft_target_overshoot_penalty", 10.0),
        enforce_annual_consistency=_as_bool(rules, "enforce_company_annual_target_consistency", True),
        time_limit_seconds=_as_float(rules, "stage2_time_limit_seconds", 120.0),
    )


def _latest_stage1_run_id(conn: sqlite3.Connection, year: int) -> str | None:
    row = conn.execute(
        """
        SELECT run_id
        FROM plan_stage1_results
        WHERE year = ?
        ORDER BY run_id DESC
        LIMIT 1
        """,
        (year,),
    ).fetchone()
    return None if row is None else str(row["run_id"])


def _quarter_index(quarter: str) -> int:
    return QUARTERS.index(str(quarter).upper()) + 1


def _normalize_ea_number(value: Any) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits.lstrip("0") or "0" if digits else ""





def _load_hard_company_annual_targets(target_rows: list[sqlite3.Row]) -> dict[str, int]:
    totals: dict[str, int] = defaultdict(int)
    for row in target_rows:
        totals[str(row["company"])] += int(row["target_value"])
    return dict(totals)


def _latest_stage1_rows(conn: sqlite3.Connection, year: int) -> list[sqlite3.Row]:
    run_id = _latest_stage1_run_id(conn, year)
    if run_id is None:
        raise PlanningError(f"Keine Stage-1-Ergebnisse fuer {year} gefunden.")
    rows = conn.execute(
        """
        SELECT run_id, year, ea_number, target_value, is_hard, note
        FROM plan_stage1_results
        WHERE year = ?
          AND run_id = ?
        ORDER BY ea_number
        """,
        (year, run_id),
    ).fetchall()
    if not rows:
        raise PlanningError(f"Keine Stage-1-Ergebnisse fuer {year} gefunden.")
    return rows


def _scale_to_total(base_values: dict[str, int], target_total: int) -> dict[str, int]:
    if not base_values:
        return {}
    base_total = sum(base_values.values())
    if base_total <= 0:
        first = next(iter(base_values))
        return {quarter: target_total if quarter == first else 0 for quarter in base_values}
    scaled = {
        quarter: int(round(target_total * value / base_total))
        for quarter, value in base_values.items()
    }
    correction = target_total - sum(scaled.values())
    if correction:
        last = next(reversed(tuple(base_values)))
        scaled[last] += correction
    return scaled


def _effective_targets(
    target_rows: list[sqlite3.Row],
    existing_amounts: dict[tuple[str, str, str], int],
    planning_start_quarter: int,
    sondervorgaben_mode: str,
    warnings: list[str],
    enforce_annual_consistency: bool,
) -> tuple[dict[tuple[str, str], int], dict[str, int]]:
    by_company: dict[str, dict[str, sqlite3.Row]] = defaultdict(dict)
    for row in target_rows:
        by_company[str(row["company"])][str(row["quarter"]).upper()] = row

    effective: dict[tuple[str, str], int] = {}
    step_by_company: dict[str, int] = {}
    for company, quarter_rows in by_company.items():
        annual_values = {int(row["annual_target"]) for row in quarter_rows.values() if row["annual_target"] is not None}
        target_sum = sum(int(row["target_value"]) for row in quarter_rows.values())
        if enforce_annual_consistency and annual_values:
            if len(annual_values) != 1 or next(iter(annual_values)) != target_sum:
                raise PlanningError(
                    f"Inkonsistente Jahresziele fuer {company}: Quartalssumme {target_sum} passt nicht zu annual_target."
                )
        step_values = {max(1, int(row["step_value"] or 1)) for row in quarter_rows.values()}
        if len(step_values) != 1:
            raise PlanningError(f"Uneinheitliche step_value fuer {company}.")
        step_by_company[company] = next(iter(step_values))

        if planning_start_quarter <= 1:
            for quarter, row in quarter_rows.items():
                effective[(company, quarter)] = int(row["target_value"])
            continue

        frozen_actual: dict[str, int] = {}
        future_targets: dict[str, int] = {}
        for quarter, row in quarter_rows.items():
            quarter_actual = sum(
                amount
                for (comp, row_quarter, _ea), amount in existing_amounts.items()
                if comp == company and row_quarter == quarter
            )
            if _quarter_index(quarter) < planning_start_quarter:
                frozen_actual[quarter] = quarter_actual
                target_value = int(row["target_value"])
                if sondervorgaben_mode == "strict" and quarter_actual != target_value:
                    raise PlanningError(
                        f"Vergangenes Quartal {quarter} fuer {company} ist eingefroren ({quarter_actual}) und verletzt strict-Target {target_value}."
                    )
                if quarter_actual != target_value:
                    warnings.append(
                        f"Catchup: {company} {quarter} von {target_value} auf {quarter_actual} eingefroren."
                    )
            else:
                future_targets[quarter] = int(row["target_value"])

        remaining_total = target_sum - sum(frozen_actual.values())
        if remaining_total < 0:
            raise PlanningError(
                f"Eingefrorene Vergangenheitswerte fuer {company} ueberschreiten das Jahresziel."
            )
        # Treppenlogik: kumulative Targets — Über-/Unterplanung vergangener
        # Quartale verschiebt sich automatisch auf zukünftige.
        scaled_future: dict[str, int] = {}
        if future_targets:
            sorted_qs = sorted(future_targets, key=_quarter_index)
            cumulative_used = sum(frozen_actual.values())
            for quarter in sorted_qs[:-1]:
                cum_target = sum(
                    int(quarter_rows[q]["target_value"])
                    for q in quarter_rows
                    if _quarter_index(q) <= _quarter_index(quarter)
                )
                val = max(0, cum_target - cumulative_used)
                scaled_future[quarter] = val
                cumulative_used += val
            scaled_future[sorted_qs[-1]] = remaining_total - sum(scaled_future.values())
        for quarter, value in frozen_actual.items():
            effective[(company, quarter)] = value
        for quarter, value in scaled_future.items():
            cap = quarter_rows[quarter]["quarter_cap"]
            if cap is not None and value > int(cap):
                raise PlanningError(
                    f"Catchup verletzt quarter_cap fuer {company} {quarter}: {value} > {int(cap)}."
                )
            effective[(company, quarter)] = value
    return effective, step_by_company


def _current_period_company_targets(
    effective_targets: dict[tuple[str, str], int],
    *,
    planning_start_quarter: int,
) -> dict[str, int]:
    targets: dict[str, int] = defaultdict(int)
    for (company, quarter), value in effective_targets.items():
        if _quarter_index(quarter) <= planning_start_quarter:
            targets[company] += int(value)
    return dict(targets)


def _current_period_company_actuals(
    existing_rows: list[sqlite3.Row | dict[str, Any]],
    target_rows: list[sqlite3.Row],
) -> dict[str, int]:
    step_by_company: dict[str, int] = {}
    for row in target_rows:
        step_by_company.setdefault(str(row["company"]), max(1, int(row["step_value"] or 1)))

    actuals: dict[str, int] = defaultdict(int)
    for row in existing_rows:
        company = str(row["company"])
        amount = int(row["amount"] or 0)
        if status_label_for_raw_status(raw_status_from_note(row["note"])) in {"bestellt", "im Durchlauf"}:
            actuals[company] += amount
    return {c: (v // step_by_company.get(c, 1)) * step_by_company.get(c, 1) for c, v in actuals.items()}


def _min_new_units(step: int, min_amount: int) -> int:
    return max(1, (max(0, min_amount) + step - 1) // step)


def _min_order_exempt_ea_norms(special_rules: list[dict[str, Any]]) -> set[str]:
    exempt: set[str] = set()
    for rule in special_rules:
        target_amount = int(rule.get("target_amount") or 0)
        period_target_amount = int(rule.get("period_target_amount") or 0)
        if target_amount <= 0 and period_target_amount <= 0:
            continue
        exempt.update(str(ea_norm) for ea_norm in rule.get("ea_keys", set()) if str(ea_norm))
    return exempt


def solve_stage2(
    conn: sqlite3.Connection,
    *,
    year: int,
    config: SolverConfig,
    planning_start_quarter: int = 1,
    sondervorgaben_mode: str = "catchup",
    run_id: str | None = None,
    special_rules: list[dict[str, Any]] | None = None,
    ea_blacklist_norms: set[str] | None = None,
) -> Stage2Solution:
    if planning_start_quarter not in {1, 2, 3, 4}:
        raise PlanningError(f"Ungueltiges planning_start_quarter: {planning_start_quarter}")
    if sondervorgaben_mode not in {"catchup", "strict"}:
        raise PlanningError(f"Ungueltiger sondervorgaben_mode: {sondervorgaben_mode}")

    target_rows = conn.execute(
        """
        SELECT year, company, quarter, target_value, annual_target, quarter_cap, step_value
        FROM plan_company_targets
        WHERE year = ?
        ORDER BY company, quarter
        """,
        (year,),
    ).fetchall()
    if not target_rows:
        raise PlanningError(f"Keine Firmenziele fuer {year} gefunden.")

    stage1_rows = _latest_stage1_rows(conn, year)
    existing_rows = conn.execute(
        """
        SELECT year, company, quarter, ea_number, amount, is_fixed, can_stop, note
        FROM plan_existing_orders
        WHERE year = ?
        ORDER BY company, quarter, ea_number
        """,
        (year,),
    ).fetchall()
    group_rules = conn.execute(
        "SELECT year, group_code, target_value, is_hard, note FROM plan_group_rules WHERE year = ?",
        (year,),
    ).fetchall()
    group_members = conn.execute(
        """
        SELECT year, group_code, ea_number, fixed_target_value, min_value, max_value, is_hard, note
        FROM plan_group_members
        WHERE year = ?
        ORDER BY group_code, ea_number
        """,
        (year,),
    ).fetchall()
    reference_rows = conn.execute(
        """
        SELECT ea_number
        FROM plan_reference_orders
        WHERE year = ?
        ORDER BY ea_number
        """,
        (year,),
    ).fetchall()
    known_companies = sorted({str(row["company"]) for row in target_rows} | {str(row["company"]) for row in existing_rows})
    if special_rules is None:
        special_rules = []
    if ea_blacklist_norms is None:
        ea_blacklist_norms = set()
    else:
        ea_blacklist_norms = {
            norm
            for norm in (_normalize_ea_number(v) for v in ea_blacklist_norms)
            if norm
        }
    min_order_exempt_ea_norms = _min_order_exempt_ea_norms(special_rules)
    hard_company_annual_targets = _load_hard_company_annual_targets(target_rows)

    warnings: list[str] = []
    existing_amounts: dict[tuple[str, str, str], int] = defaultdict(int)
    fixed_keys: set[tuple[str, str, str]] = set()
    non_stoppable_keys: set[tuple[str, str, str]] = set()
    ordered_units_by_key: dict[tuple[str, str, str], int] = defaultdict(int)
    live_units_by_key: dict[tuple[str, str, str], int] = defaultdict(int)
    for row in existing_rows:
        key = (str(row["company"]), str(row["quarter"]).upper(), str(row["ea_number"]))
        amount = int(row["amount"])
        existing_amounts[key] += amount
        status_label = status_label_for_raw_status(raw_status_from_note(row["note"]))
        if int(row["is_fixed"] or 0):
            fixed_keys.add(key)
        if not int(row["can_stop"] or 0):
            non_stoppable_keys.add(key)
        step_hint = next(
            (max(1, int(target_row["step_value"] or 1))
             for target_row in target_rows
             if str(target_row["company"]) == key[0]),
            1,
        )
        units = amount // step_hint if step_hint else amount
        if status_label == "bestellt":
            ordered_units_by_key[key] += units
            live_units_by_key[key] += units
        elif status_label == "im Durchlauf":
            live_units_by_key[key] += units

    effective_targets, step_by_company = _effective_targets(
        target_rows,
        existing_amounts,
        planning_start_quarter,
        sondervorgaben_mode,
        warnings,
        config.enforce_annual_consistency,
    )
    company_current_period_targets = _current_period_company_targets(
        effective_targets,
        planning_start_quarter=planning_start_quarter,
    )
    company_current_period_actuals = _current_period_company_actuals(existing_rows, target_rows)
    current_quarter_blocked_companies = {
        company
        for company, target_amount in company_current_period_targets.items()
        if company_current_period_actuals.get(company, 0) >= target_amount > 0
    }
    for company in sorted(current_quarter_blocked_companies):
        warnings.append(
            "Firmen-Periodensperre aktiv: "
            f"{company} aktuelles Periodenziel bereits erreicht ({company_current_period_actuals.get(company, 0)} >= {company_current_period_targets[company]})."
        )

    stage1_targets: dict[str, int] = {}
    hard_need_keys: set[str] = set()
    stage1_ea_set: set[str] = set()
    for row in stage1_rows:
        ea_number = str(row["ea_number"])
        if _normalize_ea_number(ea_number) in ea_blacklist_norms:
            continue
        stage1_targets[ea_number] = int(row["target_value"])
        stage1_ea_set.add(ea_number)
        if int(row["is_hard"] or 0):
            hard_need_keys.add(ea_number)

    existing_by_company: dict[str, set[str]] = defaultdict(set)
    for company, _quarter, ea_number in existing_amounts:
        existing_by_company[company].add(ea_number)

    group_member_eas = {str(row["ea_number"]) for row in group_members}
    reference_eas = {
        ea_number
        for ea_number in (str(row["ea_number"]).strip() for row in reference_rows)
        if ea_number and _normalize_ea_number(ea_number) not in ea_blacklist_norms
    }
    ea_variants_by_norm: dict[str, set[str]] = defaultdict(set)
    for row in stage1_rows:
        ea_variants_by_norm[_normalize_ea_number(row["ea_number"])].add(str(row["ea_number"]))
    for row in existing_rows:
        ea_variants_by_norm[_normalize_ea_number(row["ea_number"])].add(str(row["ea_number"]))
    for row in group_members:
        ea_variants_by_norm[_normalize_ea_number(row["ea_number"])].add(str(row["ea_number"]))
    for ea_number in reference_eas:
        ea_variants_by_norm[_normalize_ea_number(ea_number)].add(ea_number)

    extra_candidates_by_company: dict[str, set[str]] = defaultdict(set)
    priority_penalty_by_company_ea: dict[tuple[str, str], float] = {}
    for rule in special_rules:
        rule_variants: set[str] = set()
        for ea_norm in rule["ea_keys"]:
            rule_variants.update(ea_variants_by_norm.get(ea_norm, set()))
        if not rule_variants:
            rule_variants.update(rule.get("candidate_eas", set()))
        if not rule_variants:
            continue
        for company in rule["allowed_companies"]:
            extra_candidates_by_company[company].update(rule_variants)
        for rank, company in enumerate(rule["priority_companies"]):
            penalty = rank * config.special_rule_priority_penalty_step
            for ea_norm in rule["ea_keys"]:
                key = (company, ea_norm)
                current = priority_penalty_by_company_ea.get(key)
                if current is None or penalty < current:
                    priority_penalty_by_company_ea[key] = penalty

    candidates_by_company: dict[str, list[str]] = {}
    for company, _quarter in effective_targets:
        if company in candidates_by_company:
            continue
        free_candidates = stage1_ea_set | reference_eas
        candidates = (
            free_candidates
            | existing_by_company.get(company, set())
            | group_member_eas
            | extra_candidates_by_company.get(company, set())
        )
        if not candidates:
            raise PlanningError(f"Keine EA-Kandidaten fuer {company} gefunden.")
        candidates_by_company[company] = sorted(candidates)

    for (company, quarter, ea_number), amount in existing_amounts.items():
        step = step_by_company.get(company)
        if step is not None and amount % step:
            raise PlanningError(
                f"Bestehender Betrag {amount} fuer {company} / {quarter} / {ea_number} ist nicht durch step_value {step} teilbar."
            )

    model = highspy.Highs()
    model.setOptionValue("output_flag", False)
    model.setOptionValue("time_limit", config.time_limit_seconds)

    n_vars: dict[tuple[str, str, str], Any] = {}
    y_vars: dict[tuple[str, str, str], Any] = {}
    company_year_totals: dict[str, int] = defaultdict(int)
    for (company, _quarter), value in effective_targets.items():
        company_year_totals[company] += value

    hard_constraints = 0
    soft_constraints = 0
    combined_activation_penalty = config.activation_penalty + config.quarter_activation_penalty

    for (company, quarter), target_value in effective_targets.items():
        if target_value < 0:
            raise PlanningError(f"Negativer Quartalswert fuer {company} / {quarter}.")
        step = step_by_company[company]
        max_units = max(0, hard_company_annual_targets.get(company, 0) // step)
        min_new_units_val = _min_new_units(step, config.min_new_order_amount)
        for ea_number in candidates_by_company[company]:
            key = (company, quarter, ea_number)
            bonus = config.hard_need_bonus if ea_number in hard_need_keys else 0.0
            priority_penalty = priority_penalty_by_company_ea.get((company, _normalize_ea_number(ea_number)), 0.0)
            y_vars[key] = model.addBinary(
                obj=combined_activation_penalty + priority_penalty - bonus,
                name=f"y__{company}__{quarter}__{ea_number}",
            )
            n_vars[key] = model.addIntegral(
                lb=0,
                ub=max_units,
                obj=0.0,
                name=f"n__{company}__{quarter}__{ea_number}",
            )
            min_active_units = min_new_units_val
            existing_amount = existing_amounts.get(key, 0)
            if (
                _quarter_index(quarter) < planning_start_quarter
                or (key in fixed_keys and 0 < existing_amount < config.min_new_order_amount)
                or (key in non_stoppable_keys and 0 < existing_amount < config.min_new_order_amount)
                or (ordered_units_by_key.get(key, 0) > 0 and existing_amount < config.min_new_order_amount)
                or company_year_totals[company] < config.min_new_order_amount
            ):
                min_active_units = 1
            model.addConstr(n_vars[key] <= max_units * y_vars[key])
            model.addConstr(n_vars[key] >= min_active_units * y_vars[key])
            hard_constraints += 2

    company_annual_exprs: dict[str, Any] = defaultdict(model.expr)
    for (company, quarter), _target_value in effective_targets.items():
        expr = model.expr()
        step = step_by_company[company]
        for ea_number in candidates_by_company[company]:
            key = (company, quarter, ea_number)
            expr += step * n_vars[key]
            company_annual_exprs[company] += step * n_vars[key]
        pos = model.addVariable(
            lb=0.0, obj=config.soft_target_penalty,
            name=f"scope_soft_pos__{company}__{quarter}",
        )
        neg = model.addVariable(
            lb=0.0, obj=config.soft_target_overshoot_penalty,
            name=f"scope_soft_neg__{company}__{quarter}",
        )
        model.addConstr(expr + pos - neg == _target_value)
        soft_constraints += 1

    # ── Global quarterly soft constraints (cross-company) ─────────
    global_q_expr: dict[str, Any] = defaultdict(model.expr)
    global_q_target: dict[str, float] = defaultdict(float)
    for (company, quarter), tv in effective_targets.items():
        step = step_by_company[company]
        for ea_number in candidates_by_company[company]:
            global_q_expr[quarter] += step * n_vars[(company, quarter, ea_number)]
        global_q_target[quarter] += tv
    for quarter in sorted(global_q_expr):
        g_pos = model.addVariable(lb=0.0, obj=config.global_quarter_undershoot_penalty, name=f"global_q_pos__{quarter}")
        g_neg = model.addVariable(lb=0.0, obj=config.global_quarter_overshoot_penalty, name=f"global_q_neg__{quarter}")
        model.addConstr(global_q_expr[quarter] + g_pos - g_neg == global_q_target[quarter])
        soft_constraints += 1

    for company, target_amount in hard_company_annual_targets.items():
        expr = company_annual_exprs.get(company)
        if expr is None:
            continue
        model.addConstr(expr == target_amount)
        hard_constraints += 1

    for key, amount in existing_amounts.items():
        company, quarter, ea_number = key
        if (company, quarter) not in effective_targets:
            if key in fixed_keys or key in non_stoppable_keys or _quarter_index(quarter) < planning_start_quarter:
                raise PlanningError(
                    f"Pflichtauftrag ohne Quartalsziel: {company} / {quarter} / {ea_number}."
                )
            warnings.append(
                f"Ignoriere stopbaren Bestandsauftrag ohne Quartalsziel: {company} / {quarter} / {ea_number}."
            )
            continue
        step = step_by_company[company]
        units = amount // step
        n_var = n_vars[key]
        quarter_is_frozen = _quarter_index(quarter) < planning_start_quarter
        ordered_units = ordered_units_by_key.get(key, 0)
        live_units = live_units_by_key.get(key, 0)
        if quarter_is_frozen:
            if 0 < amount < config.min_new_order_amount:
                model.addConstr(n_var == 0)
            else:
                model.addConstr(n_var == units)
            hard_constraints += 1
            continue
        if ordered_units:
            model.addConstr(n_var >= ordered_units)
            hard_constraints += 1
        if key in fixed_keys or ordered_units == units:
            model.addConstr(n_var == units)
            hard_constraints += 1
        elif live_units > ordered_units:
            live_shortfall = model.addVariable(
                lb=0.0,
                obj=config.throughlauf_change_penalty * step,
                name=f"live_shortfall__{company}__{quarter}__{ea_number}",
            )
            model.addConstr(n_var + live_shortfall >= live_units)
            soft_constraints += 1
        elif amount > 0:
            stop_var = model.addBinary(
                obj=config.stop_penalty,
                name=f"stop__{company}__{quarter}__{ea_number}",
            )
            model.addConstr(y_vars[key] + stop_var >= 1)
            soft_constraints += 1

    if config.large_order_penalty > 0 and config.large_order_threshold > 0:
        for key, n_var in n_vars.items():
            company, quarter, ea_number = key
            if _normalize_ea_number(ea_number) in min_order_exempt_ea_norms:
                continue
            if key in fixed_keys or key in non_stoppable_keys:
                continue
            step = step_by_company[company]
            max_units = max(0, hard_company_annual_targets.get(company, 0) // step)
            threshold_units = max(1, config.large_order_threshold // step)
            if max_units <= threshold_units:
                continue
            large_var = model.addBinary(
                obj=config.large_order_penalty,
                name=f"large__{company}__{quarter}__{ea_number}",
            )
            model.addConstr(n_var <= threshold_units + (max_units - threshold_units) * large_var)
            soft_constraints += 1

    for (company, quarter), _target_value in effective_targets.items():
        if _quarter_index(quarter) != planning_start_quarter or company not in current_quarter_blocked_companies:
            continue
        step = step_by_company[company]
        for ea_number in candidates_by_company[company]:
            key = (company, quarter, ea_number)
            current_units = existing_amounts.get(key, 0) // step
            model.addConstr(n_vars[key] <= current_units)
            hard_constraints += 1

    for (company, quarter), _target_value in effective_targets.items():
        if _quarter_index(quarter) >= planning_start_quarter:
            continue
        for ea_number in candidates_by_company[company]:
            key = (company, quarter, ea_number)
            if key in existing_amounts:
                continue
            model.addConstr(n_vars[key] == 0)
            hard_constraints += 1

    for ea_number, target_value in stage1_targets.items():
        pos = model.addVariable(lb=0.0, obj=config.soft_target_penalty, name=f"soft_pos__{ea_number}")
        neg = model.addVariable(lb=0.0, obj=config.soft_target_penalty, name=f"soft_neg__{ea_number}")
        expr = model.expr()
        for (company, quarter), _target_value in effective_targets.items():
            key = (company, quarter, ea_number)
            if key in n_vars:
                expr += step_by_company[company] * n_vars[key]
        model.addConstr(expr + pos - neg == target_value)
        soft_constraints += 1

    repeat_scopes: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for key, y_var in y_vars.items():
        company, _quarter, ea_number = key
        repeat_scopes[(company, ea_number)].append(y_var)
    for (company, ea_number), quarter_vars in repeat_scopes.items():
        if len(quarter_vars) <= 1:
            continue
        repeat_var = model.addBinary(
            obj=config.repeat_quarter_penalty,
            name=f"repeat__{company}__{ea_number}",
        )
        model.addConstr(sum(quarter_vars) <= 1 + (len(quarter_vars) - 1) * repeat_var)
        soft_constraints += 1

    if config.active_ea_cap_per_quarter > 0:
        for (company, quarter), _target_value in effective_targets.items():
            expr = model.expr()
            for ea_number in candidates_by_company[company]:
                expr += y_vars[(company, quarter, ea_number)]
            model.addConstr(expr <= config.active_ea_cap_per_quarter)
            hard_constraints += 1

    for rule in special_rules:
        expr = model.expr()
        period_expr = model.expr()
        matched = 0
        period_matched = 0
        annual_capacity = 0
        period_capacity = 0
        ordered_floor = 0
        period_ordered_floor = 0
        counted_companies: set[str] = set()
        period_counted_companies: set[str] = set()
        for key, n_var in n_vars.items():
            company, quarter, ea_number = key
            if _normalize_ea_number(ea_number) not in rule["ea_keys"]:
                continue
            if rule["allowed_companies"] and company not in rule["allowed_companies"]:
                continue
            step_amount = step_by_company[company]
            expr += step_amount * n_var
            matched += 1
            ordered_floor += ordered_units_by_key.get(key, 0) * step_amount
            if company not in counted_companies:
                counted_companies.add(company)
                annual_capacity += hard_company_annual_targets.get(company, company_year_totals[company])
            if _quarter_index(quarter) <= planning_start_quarter:
                period_expr += step_amount * n_var
                period_matched += 1
                period_ordered_floor += ordered_units_by_key.get(key, 0) * step_amount
                if company not in period_counted_companies:
                    period_counted_companies.add(company)
                    period_capacity += sum(
                        value
                        for (comp, q), value in effective_targets.items()
                        if comp == company and _quarter_index(q) <= planning_start_quarter
                    )
        if matched == 0:
            warnings.append(f"Sondervorgabe ohne Solver-Kandidaten ignoriert: {rule['topic']}.")
            continue
        if rule["target_amount"] < ordered_floor:
            warnings.append(
                f"Sondervorgabe {rule['topic']} nicht hart erzwungen: Ziel {rule['target_amount']} < bestellt-Floor {ordered_floor}."
            )
            continue
        if rule["target_amount"] > annual_capacity:
            warnings.append(
                f"Sondervorgabe {rule['topic']} nicht hart erzwungen: Ziel {rule['target_amount']} > Solver-Kapazitaet {annual_capacity}."
            )
            continue
        sr_pos = model.addVariable(lb=0.0, obj=config.special_rule_annual_penalty, name=f"sr_annual_pos__{rule['topic']}")
        sr_neg = model.addVariable(lb=0.0, obj=config.special_rule_annual_penalty, name=f"sr_annual_neg__{rule['topic']}")
        model.addConstr(expr + sr_pos - sr_neg == rule["target_amount"])
        soft_constraints += 1
        if rule.get("enforce_period_exact") and rule.get("period_target_amount") is not None:
            period_target_amount = int(rule["period_target_amount"])
            if period_matched == 0:
                warnings.append(f"Sondervorgabe {rule['topic']} ohne Perioden-Kandidaten ignoriert.")
                continue
            if period_target_amount < period_ordered_floor:
                warnings.append(
                    f"Sondervorgabe {rule['topic']} Quartal nicht hart erzwungen: Ziel {period_target_amount} < bestellt-Floor {period_ordered_floor}."
                )
                continue
            if period_target_amount > period_capacity:
                warnings.append(
                    f"Sondervorgabe {rule['topic']} Quartal nicht hart erzwungen: Ziel {period_target_amount} > Solver-Kapazitaet {period_capacity}."
                )
                continue
            sp_pos = model.addVariable(lb=0.0, obj=config.special_rule_annual_penalty, name=f"sr_period_pos__{rule['topic']}")
            sp_neg = model.addVariable(lb=0.0, obj=config.special_rule_annual_penalty, name=f"sr_period_neg__{rule['topic']}")
            model.addConstr(period_expr + sp_pos - sp_neg == period_target_amount)
            soft_constraints += 1

    members_by_group: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in group_members:
        members_by_group[str(row["group_code"])].append(row)
    for rule in group_rules:
        if not int(rule["is_hard"] or 0) or rule["target_value"] is None:
            continue
        expr = model.expr()
        for member in members_by_group.get(str(rule["group_code"]), []):
            ea_number = str(member["ea_number"])
            for key, n_var in n_vars.items():
                company, quarter, key_ea = key
                if key_ea != ea_number:
                    continue
                expr += step_by_company[company] * n_var
        model.addConstr(expr == int(rule["target_value"]))
        hard_constraints += 1

    for member in group_members:
        ea_number = str(member["ea_number"])
        expr = model.expr()
        for key, n_var in n_vars.items():
            company, quarter, key_ea = key
            if key_ea != ea_number:
                continue
            expr += step_by_company[company] * n_var
        if int(member["is_hard"] or 0) and member["fixed_target_value"] is not None:
            model.addConstr(expr == int(member["fixed_target_value"]))
            hard_constraints += 1
        if member["min_value"] is not None:
            model.addConstr(expr >= int(member["min_value"]))
            hard_constraints += 1
        if member["max_value"] is not None:
            model.addConstr(expr <= int(member["max_value"]))
            hard_constraints += 1

    model.setMinimize()
    model.run()
    solution = model.getSolution()
    status_enum = model.getModelStatus()
    status_map = {
        highspy.HighsModelStatus.kOptimal: "optimal",
        highspy.HighsModelStatus.kTimeLimit: "time-limit",
        highspy.HighsModelStatus.kInfeasible: "infeasible",
        highspy.HighsModelStatus.kUnboundedOrInfeasible: "infeasible",
        highspy.HighsModelStatus.kUnbounded: "infeasible",
    }
    status = status_map.get(status_enum, model.modelStatusToString(status_enum).lower())

    if status == "infeasible":
        raise PlanningError(
            "Stage-2-Modell ist unloesbar. Pruefe Quartalsziele, feste Bestellungen, Frozen-Quarter-Werte und Gruppenregeln."
        )
    if not solution.value_valid:
        raise PlanningError(f"HiGHS lieferte keine verwertbare Loesung ({status}).")
    if status == "time-limit":
        warnings.append("HiGHS hat das Time-Limit erreicht; beste gefundene Loesung wird verwendet.")

    run_id = run_id or f"plan_{datetime.now():%Y%m%d_%H%M%S}"
    rows: list[dict[str, Any]] = []
    for key, n_var in n_vars.items():
        units = int(round(model.val(n_var)))
        company, quarter, ea_number = key
        amount = units * step_by_company[company]
        if amount <= 0 and key not in existing_amounts:
            continue
        is_locked = int(_quarter_index(quarter) < planning_start_quarter or key in fixed_keys or key in non_stoppable_keys)
        rows.append(
            {
                "run_id": run_id,
                "year": year,
                "company": company,
                "quarter": quarter,
                "ea_number": ea_number,
                "amount": amount,
                "source": "highs",
                "is_locked": is_locked,
                "note": None,
            }
        )

    conn.execute("DELETE FROM plan_stage2_results WHERE year = ?", (year,))
    if rows:
        conn.executemany(
            """
            INSERT INTO plan_stage2_results (
                run_id, year, company, quarter, ea_number, amount, source, is_locked, note
            )
            VALUES (:run_id, :year, :company, :quarter, :ea_number, :amount, :source, :is_locked, :note)
            """,
            rows,
        )
    objective_value = float(model.getObjectiveValue())
    conn.execute(
        """
        INSERT OR REPLACE INTO plan_run_log (run_id, created_at, year, solver, rules_csv, status, message)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            datetime.now().isoformat(timespec="seconds"),
            year,
            "highs",
            None,
            status,
            "; ".join(warnings) if warnings else None,
        ),
    )
    conn.commit()
    logger.info("Stage-2-Solver abgeschlossen: %s, objective=%.2f, rows=%s", status, objective_value, len(rows))
    return Stage2Solution(
        run_id=run_id,
        rows=rows,
        summary=SolverSummary(
            status=status,
            objective_value=objective_value,
            runtime_seconds=float(model.getRunTime()),
            hard_constraints=hard_constraints,
            soft_constraints=soft_constraints,
            warnings=warnings,
        ),
    )
