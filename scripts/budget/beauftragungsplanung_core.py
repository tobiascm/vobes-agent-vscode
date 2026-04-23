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
DEFAULT_CONFIG_XLSX = WORKSPACE / "userdata" / "budget" / "planning" / "beauftragungsplanung_config.xlsx"
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
COMPANY_AREA_MAP: dict[str, list[str]] = {
    "4SOFT GMBH MUENCHEN": [
        "Vorentwicklung (4soft)",
        "RuleChecker (4soft, ex Voitas)",
        "SW-Entwicklung VOBES2025 (4soft)",
    ],
    "VOLKSWAGEN GROUP SERVICES GMBH WOLFSBURG": ["CATIA-Bibl. (GroupServices)"],
    "FES GMBH ZWICKAU/00": ["Projektbüro / Prüfbüro (FES, B&W)"],
    "THIESEN HARDWARE SOFTW. GMBH WARTENBERG": [
        "Bordnetz Support, RollOut (Thiesen)",
        "Spez. und Test VOBES2025 (Thiesen)",
    ],
    "SUMITOMO ELECTRIC BORDNETZE SE WOLFSBURG": ["Pilot und Anwendertest VOBES2025 (SEBN)"],
}
SYSTEMS_AREA = "Systemschaltpläne und Bibl. (EDAG, Bertrandt)"
EDAG_COMPANY = "EDAG ENGINEERING GMBH WOLFSBURG"
BERTRANDT_COMPANY = "BERTRANDT INGENIEURBUERO GMBH TAPPENBECK"


class PlanningError(RuntimeError):
    pass


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


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


def _migrate_drop_gewerk_tables(conn: sqlite3.Connection) -> None:
    """Löscht alte Planungstabellen mit gewerk-Spalte, damit sie neu angelegt werden."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(plan_company_targets)").fetchall()}
    if "gewerk" not in cols:
        return
    conn.executescript(
        """
        DROP TABLE IF EXISTS plan_company_targets;
        DROP TABLE IF EXISTS plan_existing_orders;
        DROP TABLE IF EXISTS plan_reference_orders;
        DROP TABLE IF EXISTS plan_ea_metadata;
        DROP TABLE IF EXISTS plan_stage1_results;
        DROP TABLE IF EXISTS plan_stage2_results;
        """
    )
    conn.commit()


def init_planning_schema(conn: sqlite3.Connection) -> None:
    _migrate_drop_gewerk_tables(conn)
    conn.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS plan_company_targets (
            year INTEGER NOT NULL,
            company TEXT NOT NULL,
            quarter TEXT NOT NULL,
            target_value INTEGER NOT NULL,
            annual_target INTEGER,
            quarter_cap INTEGER,
            step_value INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (year, company, quarter)
        );

        CREATE TABLE IF NOT EXISTS plan_existing_orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            year INTEGER NOT NULL,
            company TEXT NOT NULL,
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
            project_group TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            note TEXT,
            PRIMARY KEY (year, ea_number)
        );

        CREATE TABLE IF NOT EXISTS plan_stage1_results (
            run_id TEXT NOT NULL,
            year INTEGER NOT NULL,
            ea_number TEXT NOT NULL,
            target_value INTEGER NOT NULL,
            reference_score REAL NOT NULL DEFAULT 0,
            is_hard INTEGER NOT NULL DEFAULT 0,
            note TEXT,
            PRIMARY KEY (run_id, year, ea_number)
        );

        CREATE TABLE IF NOT EXISTS plan_stage2_results (
            result_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            year INTEGER NOT NULL,
            company TEXT NOT NULL,
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
        WHERE year = ? AND company = '4SOFT GMBH MUENCHEN'
        ORDER BY quarter
        LIMIT 1
        """,
        (year,),
    ).fetchone()
    step = max(1, int(row["step_value"] if row is not None else 1))
    conn.executemany(
        """
        INSERT INTO plan_company_targets (year, company, quarter, target_value, annual_target, quarter_cap, step_value)
        VALUES (?, ?, ?, 0, 0, NULL, ?)
        ON CONFLICT(year, company, quarter) DO UPDATE SET
            target_value = excluded.target_value,
            annual_target = excluded.annual_target,
            quarter_cap = excluded.quarter_cap,
            step_value = excluded.step_value
        """,
        [(year, VOITAS_RULECHECKER_COMPANY, quarter, step) for quarter in QUARTERS],
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
    current_q = _current_quarter(now)
    q_num = int(quarter[1]) if len(quarter) == 2 and quarter[0] == "Q" else 0
    if year == now.year and q_num <= current_q:
        return CURRENT_QUARTER_TODO_STATUS
    return "01_In Erstellung"



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
        SELECT year, company, quarter, ea_number, amount, note, run_id
        FROM plan_stage2_results
        WHERE year = ?
          AND run_id = ?
          {amount_filter}
        ORDER BY company, quarter, ea_number
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
               first_signature, second_signature, target_date, invoices, dev_order_active
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
    dev_order_active: int | None = None,
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
        dev_order_active,
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
    quarter: str,
    timestamp: str,
) -> tuple[Any, ...]:
    if sample_row is not None:
        return (
            concept,
            str(sample_row["ea"] or ea_number),
            str(sample_row["title"] or ea_number),
            status,
            planned_value,
            str(sample_row["org_unit"] or "EKEK/1"),
            str(sample_row["company"] or company),
            str(sample_row["creator"] or "Beauftragungsplanung"),
            sample_row["bm_number"],
            sample_row["az_number"],
            sample_row["projektfamilie"],
            str(sample_row["dev_order"] or ea_number),
            str(sample_row["bm_text"] or ""),
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
            sample_row["dev_order_active"],
        )
    return _build_btl_insert_row(
        concept=concept,
        ea_number=ea_number,
        title=ea_number,
        status=status,
        planned_value=planned_value,
        company=company,
        bm_text="",
        target_date=_quarter_target_date(year, quarter),
        timestamp=timestamp,
        dev_order_active=None,
    )


def _materialize_btl_opt(conn: sqlite3.Connection, year: int) -> list[sqlite3.Row]:
    rows = _load_stage2_rows(conn, year)
    stage2_rows_all = _load_stage2_rows(conn, year, include_zero=True)
    existing_rows = conn.execute(
        """
        SELECT company, quarter, ea_number, amount, note
        FROM plan_existing_orders
        WHERE year = ?
        ORDER BY company, quarter, ea_number, note
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
    _passthrough_exclude = {"storniert", "abgelehnt"}
    for source_row in source_rows:
        bare_key = (
            str(source_row["company"]),
            _quarter_for_date(source_row["target_date"]) or "",
            str(source_row["dev_order"] or source_row["ea"] or "").strip(),
        )
        if bare_key in planned_bare_keys:
            continue
        if status_label_for_raw_status(str(source_row["status"] or "")) in _passthrough_exclude:
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

    status_amounts: dict[tuple[str, str, str], dict[tuple[str, str], int]] = {}
    for existing_row in existing_rows:
        key = (
            str(existing_row["company"]),
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
        company = str(row["company"])
        quarter = str(row["quarter"]).upper()
        ea_number = str(row["ea_number"])
        key = (company, quarter, ea_number)
        bare_key = key

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
                f"Optimierung verletzt bestellt-Bestand fuer {company} / {quarter} / {ea_number}: {amount} < {ordered_total}."
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
                    ea_number=ea_number,
                    company=company,
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
                    ea_number=ea_number,
                    company=company,
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
                first_signature, second_signature, target_date, invoices, dev_order_active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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


def _bootstrap_company_targets(
    conn: sqlite3.Connection, year: int, company_targets: list[dict[str, Any]],
) -> None:
    """Befüllt/aktualisiert plan_company_targets aus Excel-Config."""
    if not company_targets:
        return
    insert_rows = []
    for ct in company_targets:
        company = ct["company"]
        annual = int(ct["annual_te"]) * 1000
        step = int(ct.get("step", 1))
        ratios = {q: float(ct.get(q, 0.25)) for q in QUARTERS}
        qvals = {q: int(round(annual * ratios[q])) for q in QUARTERS}
        qvals[QUARTERS[-1]] += annual - sum(qvals.values())
        for q in QUARTERS:
            insert_rows.append((year, company, q, qvals[q], annual, None, step))
    conn.executemany(
        """
        INSERT INTO plan_company_targets
            (year, company, quarter, target_value, annual_target, quarter_cap, step_value)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(year, company, quarter)
        DO UPDATE SET target_value=excluded.target_value,
                      annual_target=excluded.annual_target,
                      step_value=excluded.step_value
        """,
        insert_rows,
    )
    conn.commit()


def _bootstrap_existing_orders_from_btl(conn: sqlite3.Connection, year: int) -> None:
    """Befüllt plan_existing_orders aus BTL wenn leer: live-Statuses."""
    has = conn.execute(
        "SELECT 1 FROM plan_existing_orders WHERE year=? LIMIT 1", (year,)
    ).fetchone()
    if has:
        return
    try:
        source = conn.execute(
            """
            SELECT company, status, planned_value, target_date, dev_order, ea
            FROM btl
            WHERE substr(COALESCE(target_date, ''), 1, 4) = ?
            """,
            (str(year),),
        ).fetchall()
    except sqlite3.OperationalError:
        return
    known = {
        str(row["company"])
        for row in conn.execute(
            "SELECT DISTINCT company FROM plan_company_targets WHERE year=?", (year,)
        ).fetchall()
    }
    rows = []
    for row in source:
        company = str(row["company"])
        if company not in known:
            continue
        quarter = _quarter_for_date(row["target_date"])
        if not quarter:
            continue
        ea = str(row["dev_order"] or row["ea"] or "").strip()
        if not ea:
            continue
        raw = str(row["status"] or "").strip()
        if status_label_for_raw_status(raw) not in {"bestellt", "im Durchlauf", "Konzept"}:
            continue
        amount = int(row["planned_value"] or 0)
        if amount <= 0:
            continue
        can_stop = 0 if status_label_for_raw_status(raw) in {"bestellt", "im Durchlauf"} else 1
        rows.append((year, company, quarter, ea, amount, 0, can_stop, f"auto:{raw}"))
    if rows:
        conn.executemany(
            """
            INSERT INTO plan_existing_orders
                (year, company, quarter, ea_number, amount, is_fixed, can_stop, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()


def _bootstrap_stage1_from_btl(conn: sqlite3.Connection, year: int) -> None:
    """Befüllt plan_stage1_results aus BTL wenn leer: EA-Jahressumme als weiche Ziele."""
    has = conn.execute("SELECT 1 FROM plan_stage1_results WHERE year = ? LIMIT 1", (year,)).fetchone()
    if has:
        return
    try:
        rows = conn.execute(
            """
            SELECT dev_order, SUM(planned_value) AS total
            FROM btl
            WHERE substr(COALESCE(target_date, ''), 1, 4) = ?
              AND COALESCE(dev_order, '') <> ''
              AND COALESCE(planned_value, 0) > 0
            GROUP BY dev_order
            HAVING total > 0
            """,
            (str(year),),
        ).fetchall()
    except sqlite3.OperationalError:
        return
    if not rows:
        return
    run_id = f"auto_{year}"
    conn.executemany(
        """
        INSERT OR IGNORE INTO plan_stage1_results (run_id, year, ea_number, target_value, reference_score, is_hard)
        VALUES (?, ?, ?, ?, 0.0, 0)
        """,
        [(run_id, year, str(row["dev_order"]), int(row["total"])) for row in rows],
    )
    conn.commit()


def execute_planning(
    *,
    year: int,
    config_xlsx: str,
    output: str | None = None,
    logger: logging.Logger | None = None,
    planning_start_quarter: int | None = None,
    sondervorgaben_mode: str = "catchup",
) -> tuple[dict[str, Any], str]:
    from planning_config_io import read_config, transform_sondervorgaben
    from stage2_solver import load_solver_config, solve_stage2

    cfg = read_config(Path(config_xlsx))
    config = load_solver_config(cfg.rules)
    start_quarter = planning_start_quarter or _current_quarter()

    with connect() as conn:
        init_planning_schema(conn)
        _bootstrap_company_targets(conn, year, cfg.company_targets)
        _ensure_special_company_targets(conn, year)
        _bootstrap_stage1_from_btl(conn, year)
        _bootstrap_existing_orders_from_btl(conn, year)
        known_companies = sorted(
            str(r["company"])
            for r in conn.execute(
                "SELECT DISTINCT company FROM plan_company_targets WHERE year=?", (year,)
            ).fetchall()
        )
        special_rules = transform_sondervorgaben(cfg.sondervorgaben, known_companies, start_quarter)
        solution = solve_stage2(
            conn,
            year=year,
            config=config,
            planning_start_quarter=start_quarter,
            sondervorgaben_mode=sondervorgaben_mode,
            special_rules=special_rules,
        )
        conn.execute(
            "UPDATE plan_run_log SET rules_csv = ? WHERE run_id = ?",
            (str(config_xlsx), solution.run_id),
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
        "config_xlsx": str(config_xlsx),
    }
    return result, str(report)
