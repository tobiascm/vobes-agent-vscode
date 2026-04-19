from __future__ import annotations

import csv
import logging
import sqlite3
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from budget_db import BTL_COLUMNS_SQL
from report_utils import report_path, section, table_md, write_report


WORKSPACE = Path(__file__).resolve().parents[2]
DB_PATH = WORKSPACE / "userdata" / "budget.db"
DEFAULT_RULES_CSV = WORKSPACE / "userdata" / "budget" / "planning" / "beauftragungsplanung_rules.csv"
STATUS_MAPPING_CSV = (
    WORKSPACE
    / ".agents"
    / "skills"
    / "skill-budget-target-ist-analyse"
    / "status_mapping.csv"
)
QUARTERS = ("Q1", "Q2", "Q3", "Q4")
QUARTER_ENDINGS = {"Q1": "03-31", "Q2": "06-30", "Q3": "09-30", "Q4": "12-31"}
CURRENT_QUARTER_TODO_STATUS = "02_Freigabe Kostenstelle"
VOITAS_RULECHECKER_COMPANY = "VOITAS ENGINEERING GMBH GEISENFELD"
VOITAS_RULECHECKER_GEWERK = "RuleChecker (4soft, ex Voitas)"
DEFAULT_RULE_ROWS = [
    ("stage2_source", "plan_stage2_results"),
    ("stage2_solver", "highs"),
    ("stage2_activation_penalty", "100"),
    ("stage2_quarter_activation_penalty", "50"),
    ("stage2_min_new_order_amount", "10000"),
    ("stage2_repeat_quarter_penalty", "200"),
    ("stage2_stop_penalty", "500"),
    ("stage2_existing_small_amount_penalty", "10000"),
    ("stage2_soft_target_penalty", "10"),
    ("stage2_active_ea_cap_per_quarter", "0"),
    ("stage2_hard_need_bonus", "50"),
    ("stage2_throughlauf_change_penalty", "2500"),
    ("stage2_special_rule_priority_penalty_step", "25"),
    ("stage2_time_limit_seconds", "120"),
    ("enforce_company_annual_target_consistency", "true"),
    ("btl_opt_refresh", "replace"),
]


class PlanningError(RuntimeError):
    pass


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_default_rules_csv(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["rule", "value"])
        writer.writerows(DEFAULT_RULE_ROWS)
    return path


def _read_rules_csv(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        fieldnames = [str(name or "").strip() for name in reader.fieldnames or []]
        if fieldnames != ["rule", "value"]:
            raise PlanningError(
                f"Ungueltiges Rules-Format in {path}. Erwartet wird exakt 'rule;value'."
            )
        rules = {
            str(row["rule"]).strip(): str(row["value"] or "").strip()
            for row in reader
            if str(row.get("rule") or "").strip()
        }
    if not rules:
        raise PlanningError(f"Keine Regeln in {path} gefunden.")
    return rules


@lru_cache(maxsize=1)
def load_status_labels() -> dict[str, str]:
    mapping: dict[str, str] = {}
    with STATUS_MAPPING_CSV.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        for row in reader:
            status = str(row.get("Status") or "").strip()
            label = str(row.get("Benennung") or "").strip()
            if status:
                mapping[status] = label
    return mapping


def raw_status_from_note(note: str | None) -> str:
    text = str(note or "").strip()
    if text.startswith("auto:"):
        return text[5:].strip()
    return text


def status_label_for_raw_status(raw_status: str | None) -> str:
    status = str(raw_status or "").strip()
    if not status:
        return ""
    mapped = load_status_labels().get(status)
    if mapped:
        return mapped
    lowered = status.lower()
    if "bestellt" in lowered or "genehmigt" in lowered:
        return "bestellt"
    if "storni" in lowered:
        return "storniert"
    if "abgelehnt" in lowered:
        return "abgelehnt"
    if status.startswith("01_"):
        return "Konzept"
    if status.startswith("07_") or status.startswith("06_") or status.startswith("02_"):
        return "im Durchlauf"
    return ""


def status_label_from_note(note: str | None) -> str:
    return status_label_for_raw_status(raw_status_from_note(note))


def init_planning_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS plan_company_targets (
            year INTEGER NOT NULL,
            company TEXT NOT NULL,
            gewerk TEXT NOT NULL DEFAULT '',
            quarter TEXT NOT NULL,
            target_value INTEGER NOT NULL,
            annual_target INTEGER,
            quarter_cap INTEGER,
            step_value INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (year, company, gewerk, quarter)
        );

        CREATE TABLE IF NOT EXISTS plan_existing_orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            year INTEGER NOT NULL,
            company TEXT NOT NULL,
            gewerk TEXT NOT NULL DEFAULT '',
            quarter TEXT NOT NULL,
            ea_number TEXT NOT NULL,
            amount INTEGER NOT NULL,
            is_fixed INTEGER NOT NULL DEFAULT 0,
            can_stop INTEGER NOT NULL DEFAULT 1,
            note TEXT
        );

        CREATE TABLE IF NOT EXISTS plan_reference_orders (
            reference_id INTEGER PRIMARY KEY AUTOINCREMENT,
            year INTEGER NOT NULL,
            ea_number TEXT NOT NULL,
            reference_value INTEGER,
            reference_count INTEGER,
            source_company TEXT,
            gewerk TEXT,
            note TEXT
        );

        CREATE TABLE IF NOT EXISTS plan_group_rules (
            year INTEGER NOT NULL,
            group_code TEXT NOT NULL,
            target_value INTEGER,
            is_hard INTEGER NOT NULL DEFAULT 0,
            note TEXT,
            PRIMARY KEY (year, group_code)
        );

        CREATE TABLE IF NOT EXISTS plan_group_members (
            year INTEGER NOT NULL,
            group_code TEXT NOT NULL,
            ea_number TEXT NOT NULL,
            fixed_target_value INTEGER,
            min_value INTEGER,
            max_value INTEGER,
            is_hard INTEGER NOT NULL DEFAULT 0,
            note TEXT,
            PRIMARY KEY (year, group_code, ea_number)
        );

        CREATE TABLE IF NOT EXISTS plan_ea_metadata (
            year INTEGER NOT NULL,
            ea_number TEXT NOT NULL,
            gewerk TEXT,
            project_group TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            note TEXT,
            PRIMARY KEY (year, ea_number)
        );

        CREATE TABLE IF NOT EXISTS plan_stage1_results (
            run_id TEXT NOT NULL,
            year INTEGER NOT NULL,
            gewerk TEXT NOT NULL DEFAULT '',
            ea_number TEXT NOT NULL,
            target_value INTEGER NOT NULL,
            reference_score REAL NOT NULL DEFAULT 0,
            is_hard INTEGER NOT NULL DEFAULT 0,
            note TEXT,
            PRIMARY KEY (run_id, year, gewerk, ea_number)
        );

        CREATE TABLE IF NOT EXISTS plan_stage2_results (
            result_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            year INTEGER NOT NULL,
            company TEXT NOT NULL,
            gewerk TEXT NOT NULL DEFAULT '',
            quarter TEXT NOT NULL,
            ea_number TEXT NOT NULL,
            amount INTEGER NOT NULL,
            source TEXT NOT NULL DEFAULT 'highs',
            is_locked INTEGER NOT NULL DEFAULT 0,
            note TEXT
        );

        CREATE TABLE IF NOT EXISTS plan_run_log (
            run_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            year INTEGER NOT NULL,
            solver TEXT NOT NULL,
            rules_csv TEXT,
            status TEXT NOT NULL,
            message TEXT
        );

        CREATE TABLE IF NOT EXISTS btl_opt (
{BTL_COLUMNS_SQL}
        );
        """
    )
    conn.commit()


def _current_quarter(now: datetime | None = None) -> int:
    month = (now or datetime.now()).month
    return ((month - 1) // 3) + 1


def _ensure_special_company_targets(conn: sqlite3.Connection, year: int) -> None:
    try:
        has_voitas_rows = conn.execute(
            """
            SELECT 1
            FROM btl
            WHERE substr(COALESCE(target_date, ''), 1, 4) = ?
              AND company = ?
              AND COALESCE(planned_value, 0) > 0
            LIMIT 1
            """,
            (str(year), VOITAS_RULECHECKER_COMPANY),
        ).fetchone()
    except sqlite3.OperationalError:
        has_voitas_rows = None
    if has_voitas_rows is None:
        return

    row = conn.execute(
        """
        SELECT step_value
        FROM plan_company_targets
        WHERE year = ?
          AND company = '4SOFT GMBH MUENCHEN'
          AND gewerk = ?
        ORDER BY quarter
        LIMIT 1
        """,
        (year, VOITAS_RULECHECKER_GEWERK),
    ).fetchone()
    step = max(1, int(row["step_value"] if row is not None else 1))
    conn.executemany(
        """
        INSERT INTO plan_company_targets (
            year, company, gewerk, quarter, target_value, annual_target, quarter_cap, step_value
        )
        VALUES (?, ?, ?, ?, 0, 0, NULL, ?)
        ON CONFLICT(year, company, gewerk, quarter) DO UPDATE SET
            target_value = excluded.target_value,
            annual_target = excluded.annual_target,
            quarter_cap = excluded.quarter_cap,
            step_value = excluded.step_value
        """,
        [
            (year, VOITAS_RULECHECKER_COMPANY, VOITAS_RULECHECKER_GEWERK, quarter, step)
            for quarter in QUARTERS
        ],
    )
    conn.commit()


def _quarter_target_date(year: int, quarter: str) -> str:
    if quarter not in QUARTER_ENDINGS:
        raise PlanningError(f"Unbekanntes Quartal in plan_stage2_results: {quarter}")
    return f"{year}-{QUARTER_ENDINGS[quarter]}"


def _quarter_for_date(target_date: str | None) -> str | None:
    text = str(target_date or "").strip()
    if len(text) < 7:
        return None
    try:
        month = int(text[5:7])
    except ValueError:
        return None
    if month <= 3:
        return "Q1"
    if month <= 6:
        return "Q2"
    if month <= 9:
        return "Q3"
    return "Q4"


def _status_for_new_planned_row(year: int, quarter: str) -> str:
    now = datetime.now()
    if year == now.year and quarter == f"Q{_current_quarter(now)}":
        return CURRENT_QUARTER_TODO_STATUS
    return "01_In Erstellung"


def _btl_title(company: str, gewerk: str, ea_number: str) -> str:
    upper_company = company.upper()
    upper_gewerk = gewerk.upper()
    if "4SOFT" in upper_company and "RULECHECKER" in upper_gewerk:
        return f"RuleChecker {ea_number}"
    if "4SOFT" in upper_company and "SW-ENTWICKLUNG" in upper_gewerk:
        return f"TE-PMT {ea_number}"
    return f"{gewerk} {ea_number}".strip()


def _btl_company(company: str, gewerk: str) -> str:
    upper_company = company.upper()
    upper_gewerk = gewerk.upper()
    if "4SOFT" in upper_company and "RULECHECKER" in upper_gewerk:
        return "VOITAS"
    return company


def _btl_bm_text(company: str, gewerk: str) -> str:
    upper_company = company.upper()
    upper_gewerk = gewerk.upper()
    if "THIESEN" in upper_company:
        if "SPEZ." in upper_gewerk or "SPEZIF" in upper_gewerk:
            return "Gewerk #2"
        if "BORDNETZ SUPPORT" in upper_gewerk or "ROLLOUT" in upper_gewerk:
            return "Gewerk #1,#2,#3,#5"
    return gewerk


def _latest_run_id(conn: sqlite3.Connection, table: str, year: int) -> str | None:
    row = conn.execute(
        f"""
        SELECT run_id
        FROM {table}
        WHERE year = ?
        ORDER BY run_id DESC
        LIMIT 1
        """,
        (year,),
    ).fetchone()
    return None if row is None else str(row["run_id"])


def _load_stage2_rows(conn: sqlite3.Connection, year: int, *, include_zero: bool = False) -> list[sqlite3.Row]:
    run_id = _latest_run_id(conn, "plan_stage2_results", year)
    if run_id is None:
        raise PlanningError(
            f"Keine finalen Stage-2-Ergebnisse fuer {year} in plan_stage2_results gefunden."
        )
    amount_filter = "" if include_zero else "AND amount <> 0"
    rows = conn.execute(
        f"""
        SELECT year, company, gewerk, quarter, ea_number, amount, note, run_id
        FROM plan_stage2_results
        WHERE year = ?
          AND run_id = ?
          {amount_filter}
        ORDER BY company, gewerk, quarter, ea_number
        """,
        (year, run_id),
    ).fetchall()
    if not rows:
        raise PlanningError(
            f"Keine finalen Stage-2-Ergebnisse fuer {year} in plan_stage2_results gefunden."
        )
    return rows


def _load_btl_year_rows(conn: sqlite3.Connection, year: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT concept, ea, title, status, planned_value,
               org_unit, company, creator, bm_number, az_number,
               projektfamilie, dev_order, bm_text, last_updated,
               category, cost_type, quantity, unit, supplier_number,
               first_signature, second_signature, target_date, invoices
        FROM btl
        WHERE substr(COALESCE(target_date, ''), 1, 4) = ?
        ORDER BY company, target_date, dev_order, title
        """,
        (str(year),),
    ).fetchall()


def _build_btl_insert_row(
    *,
    concept: str,
    ea_number: str,
    title: str,
    status: str,
    planned_value: int,
    company: str,
    bm_text: str,
    target_date: str,
    timestamp: str,
) -> tuple[Any, ...]:
    return (
        concept,
        ea_number,
        title,
        status,
        planned_value,
        "EKEK/1",
        company,
        "Beauftragungsplanung",
        None,
        None,
        None,
        ea_number,
        bm_text,
        timestamp,
        "OPTIMIERUNG",
        None,
        None,
        None,
        None,
        None,
        None,
        target_date,
        None,
    )


def _build_btl_insert_row_from_sample(
    *,
    year: int,
    concept: str,
    status: str,
    planned_value: int,
    sample_row: sqlite3.Row | None,
    ea_number: str,
    company: str,
    gewerk: str,
    quarter: str,
    timestamp: str,
) -> tuple[Any, ...]:
    if sample_row is not None:
        return (
            concept,
            str(sample_row["ea"] or ea_number),
            str(sample_row["title"] or _btl_title(company, gewerk, ea_number)),
            status,
            planned_value,
            str(sample_row["org_unit"] or "EKEK/1"),
            str(sample_row["company"] or company),
            str(sample_row["creator"] or "Beauftragungsplanung"),
            sample_row["bm_number"],
            sample_row["az_number"],
            sample_row["projektfamilie"],
            str(sample_row["dev_order"] or ea_number),
            str(sample_row["bm_text"] or _btl_bm_text(company, gewerk)),
            timestamp,
            str(sample_row["category"] or "OPTIMIERUNG"),
            sample_row["cost_type"],
            sample_row["quantity"],
            sample_row["unit"],
            sample_row["supplier_number"],
            sample_row["first_signature"],
            sample_row["second_signature"],
            _quarter_target_date(year, quarter),
            sample_row["invoices"],
        )
    return _build_btl_insert_row(
        concept=concept,
        ea_number=ea_number,
        title=_btl_title(company, gewerk, ea_number),
        status=status,
        planned_value=planned_value,
        company=company,
        bm_text=_btl_bm_text(company, gewerk),
        target_date=_quarter_target_date(year, quarter),
        timestamp=timestamp,
    )


def _materialize_btl_opt(conn: sqlite3.Connection, year: int) -> list[sqlite3.Row]:
    rows = _load_stage2_rows(conn, year)
    stage2_rows_all = _load_stage2_rows(conn, year, include_zero=True)
    existing_rows = conn.execute(
        """
        SELECT company, gewerk, quarter, ea_number, amount, note
        FROM plan_existing_orders
        WHERE year = ?
        ORDER BY company, gewerk, quarter, ea_number, note
        """,
        (year,),
    ).fetchall()
    source_rows = _load_btl_year_rows(conn, year)
    conn.execute("DELETE FROM btl_opt")
    insert_rows: list[tuple[Any, ...]] = []
    timestamp = datetime.now().isoformat(timespec="seconds")
    index = 0
    planned_bare_keys = {
        (str(row["company"]), str(row["quarter"]).upper(), str(row["ea_number"]))
        for row in stage2_rows_all
    }
    for source_row in source_rows:
        bare_key = (
            str(source_row["company"]),
            _quarter_for_date(source_row["target_date"]) or "",
            str(source_row["dev_order"] or source_row["ea"] or "").strip(),
        )
        if bare_key in planned_bare_keys:
            continue
        insert_rows.append(tuple(source_row))

    source_by_bare_key: dict[tuple[str, str, str], sqlite3.Row] = {}
    source_by_bare_key_status: dict[tuple[str, str, str, str], sqlite3.Row] = {}
    for source_row in source_rows:
        bare_key = (
            str(source_row["company"]),
            _quarter_for_date(source_row["target_date"]) or "",
            str(source_row["dev_order"] or source_row["ea"] or "").strip(),
        )
        source_by_bare_key.setdefault(bare_key, source_row)
        source_by_bare_key_status.setdefault(bare_key + (str(source_row["status"]),), source_row)

    status_amounts: dict[tuple[str, str, str, str], dict[tuple[str, str], int]] = {}
    for existing_row in existing_rows:
        key = (
            str(existing_row["company"]),
            str(existing_row["gewerk"]),
            str(existing_row["quarter"]).upper(),
            str(existing_row["ea_number"]),
        )
        buckets = status_amounts.setdefault(key, {})
        raw_status = raw_status_from_note(existing_row["note"]) or "01_In Erstellung"
        label = status_label_for_raw_status(raw_status)
        bucket_key = (raw_status, label)
        buckets[bucket_key] = buckets.get(bucket_key, 0) + int(existing_row["amount"])

    label_priority = {"bestellt": 0, "im Durchlauf": 1, "Konzept": 2, "storniert": 3, "abgelehnt": 4}
    for row in rows:
        amount = int(row["amount"])
        if amount <= 0:
            continue
        key = (
            str(row["company"]),
            str(row["gewerk"]),
            str(row["quarter"]).upper(),
            str(row["ea_number"]),
        )
        company = _btl_company(key[0], key[1])
        quarter = key[2]
        bare_key = (key[0], quarter, key[3])

        bucket_rows = sorted(
            (
                (raw_status, label, bucket_amount)
                for (raw_status, label), bucket_amount in status_amounts.get(key, {}).items()
                if bucket_amount > 0
            ),
            key=lambda item: (label_priority.get(item[1], 9), item[0]),
        )
        ordered_total = sum(bucket_amount for _raw_status, label, bucket_amount in bucket_rows if label == "bestellt")
        if amount < ordered_total:
            raise PlanningError(
                f"Optimierung verletzt bestellt-Bestand fuer {key[0]} / {key[1]} / {key[2]} / {key[3]}: {amount} < {ordered_total}."
            )

        remaining = amount
        planned_status_amounts: list[tuple[str, int]] = []
        for raw_status, _label, bucket_amount in bucket_rows:
            keep_amount = bucket_amount if remaining >= bucket_amount else remaining
            if keep_amount <= 0:
                continue
            planned_status_amounts.append((raw_status, keep_amount))
            remaining -= keep_amount

        new_status = _status_for_new_planned_row(year, quarter)
        if remaining > 0:
            for status_index, (raw_status, keep_amount) in enumerate(planned_status_amounts):
                if raw_status != new_status:
                    continue
                planned_status_amounts[status_index] = (raw_status, keep_amount + remaining)
                remaining = 0
                break

        for raw_status, keep_amount in planned_status_amounts:
            index += 1
            sample_row = (
                source_by_bare_key_status.get(bare_key + (raw_status,))
                or source_by_bare_key.get(bare_key)
            )
            insert_rows.append(
                _build_btl_insert_row_from_sample(
                    year=year,
                    concept=f"OPT-{year}-{quarter}-{index:04d}",
                    status=raw_status,
                    planned_value=keep_amount,
                    sample_row=sample_row,
                    ea_number=key[3],
                    company=company,
                    gewerk=key[1],
                    quarter=quarter,
                    timestamp=timestamp,
                )
            )

        if remaining > 0:
            index += 1
            sample_row = source_by_bare_key.get(bare_key)
            insert_rows.append(
                _build_btl_insert_row_from_sample(
                    year=year,
                    concept=f"OPT-{year}-{quarter}-{index:04d}",
                    status=new_status,
                    planned_value=remaining,
                    sample_row=sample_row,
                    ea_number=key[3],
                    company=company,
                    gewerk=key[1],
                    quarter=quarter,
                    timestamp=timestamp,
                )
            )

    if insert_rows:
        conn.executemany(
            """
            INSERT INTO btl_opt (
                concept, ea, title, status, planned_value,
                org_unit, company, creator, bm_number, az_number,
                projektfamilie, dev_order, bm_text, last_updated,
                category, cost_type, quantity, unit, supplier_number,
                first_signature, second_signature, target_date, invoices
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            insert_rows,
        )
    conn.commit()
    return rows


def _write_planning_report(
    *,
    year: int,
    rows: list[sqlite3.Row],
    solver_summary: dict[str, Any],
    output: str | None,
    logger: logging.Logger | None,
) -> Path:
    per_company_quarter: dict[tuple[str, str], int] = {}
    for row in rows:
        key = (str(row["company"]), str(row["quarter"]))
        per_company_quarter[key] = per_company_quarter.get(key, 0) + int(row["amount"])

    summary_rows = [
        [company, quarter, f"{round(amount / 1000):,} T€".replace(",", ".")]
        for (company, quarter), amount in sorted(per_company_quarter.items())
    ]
    sections = [
        section(
            "Solver",
            table_md(
                [
                    ["Status", solver_summary["status"]],
                    ["Objective", f"{solver_summary['objective_value']:.2f}"],
                    ["Laufzeit", f"{solver_summary['runtime_seconds']:.3f} s"],
                    ["Harte Constraints", str(solver_summary["hard_constraints"])],
                    ["Weiche Constraints", str(solver_summary["soft_constraints"])],
                    ["Run-ID", solver_summary["run_id"]],
                ],
                headers=["Feld", "Wert"],
            ),
        ),
        section(
            "btl_opt Materialisierung",
            table_md(summary_rows, headers=["Firma", "Quartal", "Vorschlag"]),
        ),
    ]
    if solver_summary["warnings"]:
        sections.append(
            section(
                "Warnungen",
                "\n".join(f"- {message}" for message in solver_summary["warnings"]),
            )
        )
    sections.append(
        section(
            "Hinweis",
            "Die finale Optimierung wurde nach `btl_opt` geschrieben. "
            "`btl_opt` repraesentiert immer nur den letzten Vorschlag.",
        )
    )
    report = write_report(
        report_path("beauftragungsplanung", str(year), output=output),
        f"Beauftragungsplanung {year}",
        sections,
        meta_lines=[f"- Optimierte Zeilen in `btl_opt`: {len(rows)}"],
    )
    if logger:
        logger.info("Planungsbericht geschrieben: %s", report)
    return report


def execute_planning(
    *,
    year: int,
    rules_csv: str,
    output: str | None = None,
    logger: logging.Logger | None = None,
    planning_start_quarter: int | None = None,
    sondervorgaben_mode: str = "catchup",
) -> tuple[dict[str, Any], str]:
    rules_path = ensure_default_rules_csv(Path(rules_csv))
    rules = _read_rules_csv(rules_path)
    from stage2_solver import load_solver_config, solve_stage2

    config = load_solver_config(rules)
    start_quarter = planning_start_quarter or _current_quarter()

    with connect() as conn:
        init_planning_schema(conn)
        _ensure_special_company_targets(conn, year)
        solution = solve_stage2(
            conn,
            year=year,
            config=config,
            planning_start_quarter=start_quarter,
            sondervorgaben_mode=sondervorgaben_mode,
        )
        conn.execute(
            "UPDATE plan_run_log SET rules_csv = ? WHERE run_id = ?",
            (str(rules_path), solution.run_id),
        )
        rows = _materialize_btl_opt(conn, year)
        conn.commit()

    solver_summary = {
        "status": solution.summary.status,
        "objective_value": solution.summary.objective_value,
        "runtime_seconds": solution.summary.runtime_seconds,
        "hard_constraints": solution.summary.hard_constraints,
        "soft_constraints": solution.summary.soft_constraints,
        "warnings": solution.summary.warnings,
        "run_id": solution.run_id,
    }
    report = _write_planning_report(
        year=year,
        rows=rows,
        solver_summary=solver_summary,
        output=output,
        logger=logger,
    )
    result = {
        "year": year,
        "run_id": solution.run_id,
        "solver_status": solution.summary.status,
        "objective_value": solution.summary.objective_value,
        "btl_opt_rows": len(rows),
        "rules_csv": str(rules_path),
    }
    return result, str(report)
