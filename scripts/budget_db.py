#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from report_utils import report_path, section, table_md, write_report


WORKSPACE = Path(__file__).resolve().parent.parent
DB_PATH = WORKSPACE / "userdata" / "budget.db"
BASE_URL = "https://bplus-ng-mig.r02.vwgroup.com"
ORG_UNIT = "EKEK/1"
ORG_UNIT_ID = 161

STATUS_MAP = {
    "WF_Created": "01_In Erstellung",
    "WF_In_process_BM_Team": "06_In Bearbeitung BM-Team",
    "WF_In_Planen_BM": "07_In Planen-BM",
    "WF_Rejected": "97_Abgelehnt",
    "WF_Canceled": "98_Storniert",
    "WF_Archived": "99_Archiviert",
}

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS btl (
        concept TEXT, ea TEXT, title TEXT, status TEXT, planned_value INTEGER,
        org_unit TEXT, company TEXT, creator TEXT, bm_number TEXT, az_number TEXT,
        projektfamilie TEXT, dev_order TEXT, bm_text TEXT, last_updated TEXT,
        category TEXT, cost_type TEXT, quantity TEXT, unit TEXT, supplier_number TEXT,
        first_signature TEXT, second_signature TEXT, target_date TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS devorder (
        ea_number TEXT PRIMARY KEY, title TEXT, active INTEGER,
        date_from TEXT, date_until TEXT, sop TEXT,
        project_family TEXT, controller TEXT, hierarchy TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS el_planning (
        user_name TEXT, ea_number TEXT, ea_title TEXT, project_family TEXT,
        pct_jan REAL, pct_feb REAL, pct_mar REAL, pct_apr REAL,
        pct_may REAL, pct_jun REAL, pct_jul REAL, pct_aug REAL,
        pct_sep REAL, pct_oct REAL, pct_nov REAL, pct_dec REAL,
        booking_locks TEXT, year_work_hours REAL, hourly_rate REAL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS stundensaetze (
        jahr INTEGER, kst TEXT, oe TEXT, stundensatz REAL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ua_leiter (
        oe TEXT, ebene TEXT, mail TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS _sync_meta (
        table_name TEXT PRIMARY KEY, synced_at TEXT, year INTEGER
    )
    """,
]


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    for stmt in SCHEMA:
        conn.execute(stmt)
    conn.commit()


def ps_json(url: str, timeout: int = 60):
    cmd = (
        f'[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; '
        f'Invoke-RestMethod -Uri "{url}" -UseDefaultCredentials '
        f'-TimeoutSec {timeout} | ConvertTo-Json -Depth 12 -Compress'
    )
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command", cmd],
        capture_output=True,
    )
    stdout = r.stdout.decode("utf-8", errors="replace")
    stderr = r.stderr.decode("utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(stderr.strip() or f"PowerShell-Fehler beim Abruf: {url}")
    if not stdout.strip():
        raise RuntimeError(f"Leere API-Antwort: {url}")
    payload = json.loads(stdout)
    # APIs may wrap results as {"value": [...], "Count": N}
    if isinstance(payload, dict) and "value" in payload:
        return payload["value"]
    return payload


def ps_text(url: str, timeout: int = 60) -> str:
    cmd = (
        f'[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; '
        f'(Invoke-WebRequest -Uri "{url}" -UseDefaultCredentials '
        f'-TimeoutSec {timeout} -UseBasicParsing).Content'
    )
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command", cmd],
        capture_output=True,
    )
    stdout = r.stdout.decode("utf-8", errors="replace")
    stderr = r.stderr.decode("utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(stderr.strip() or f"PowerShell-Fehler beim Abruf: {url}")
    return stdout


def trim(value) -> str:
    return str(value or "").strip()


def iso_date(value) -> str:
    text = trim(value)
    return text.split("T")[0] if text else ""


def as_int(value) -> int:
    try:
        return int(round(float(str(value or "0").replace(",", "."))))
    except ValueError:
        return 0


def as_float(value) -> float:
    try:
        return float(str(value or "0").replace(",", "."))
    except ValueError:
        return 0.0


def update_sync_meta(conn: sqlite3.Connection, table: str, year: int) -> None:
    conn.execute(
        """
        INSERT INTO _sync_meta(table_name, synced_at, year)
        VALUES (?, ?, ?)
        ON CONFLICT(table_name) DO UPDATE SET synced_at=excluded.synced_at, year=excluded.year
        """,
        (table, datetime.now().isoformat(timespec="seconds"), year),
    )


def get_sync_meta(conn: sqlite3.Connection, table: str) -> dict | None:
    row = conn.execute(
        "SELECT table_name, synced_at, year FROM _sync_meta WHERE table_name = ?",
        (table,),
    ).fetchone()
    return dict(row) if row else None


def is_fresh(conn: sqlite3.Connection, table: str, year: int, max_age_hours: int = 24) -> bool:
    meta = get_sync_meta(conn, table)
    if not meta or meta["year"] != year:
        return False
    synced_at = datetime.fromisoformat(meta["synced_at"])
    return datetime.now() - synced_at < timedelta(hours=max_age_hours)


def replace_table(conn: sqlite3.Connection, table: str, columns: list[str], rows: list[tuple], year: int) -> int:
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(f"DELETE FROM {table}")
    if rows:
        conn.executemany(
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
            rows,
        )
    update_sync_meta(conn, table, year)
    return len(rows)


def sync_btl(conn: sqlite3.Connection, year: int, force: bool = False) -> int:
    if not force and is_fresh(conn, "btl", year):
        return 0
    raw = ps_json(f"{BASE_URL}/ek/api/Btl/GetAll?year={year}")
    rows = []
    for item in raw if isinstance(raw, list) else [raw]:
        if trim(item.get("orgUnitName")) != ORG_UNIT:
            continue
        if trim(item.get("workFlowStatus")) == "WF_Archived":
            continue
        status = STATUS_MAP.get(trim(item.get("workFlowStatus")), trim(item.get("workFlowStatus")))
        detail = trim(item.get("status"))
        if detail and detail.lower() not in status.lower():
            status = f"{status}: {detail}"
        rows.append((
            trim(item.get("concept")),
            trim(item.get("eaTitel")),
            trim(item.get("title")),
            status,
            as_int(item.get("plannedValue")),
            trim(item.get("orgUnitName")),
            trim(item.get("company")),
            trim(item.get("creatorName")),
            trim(item.get("bmNumber")),
            trim(item.get("azNumber")),
            "" if trim(item.get("projektfamilie")).upper() == "KEINE" else trim(item.get("projektfamilie")),
            trim(item.get("devOrder")),
            trim(item.get("pbmText")).replace("\r", " ").replace("\n", " | "),
            iso_date(item.get("lastUpdated")),
            trim(item.get("category")),
            trim(item.get("costType")),
            trim(item.get("quantity")),
            trim(item.get("unity") or item.get("unit")),
            trim(item.get("supplierNumber")),
            trim(item.get("firstSignature")),
            trim(item.get("secondSignature")),
            iso_date(item.get("targetDate")),
        ))
    count = replace_table(
        conn,
        "btl",
        [
            "concept", "ea", "title", "status", "planned_value", "org_unit",
            "company", "creator", "bm_number", "az_number", "projektfamilie",
            "dev_order", "bm_text", "last_updated", "category", "cost_type",
            "quantity", "unit", "supplier_number", "first_signature",
            "second_signature", "target_date",
        ],
        rows,
        year,
    )
    conn.commit()
    return count


def sync_devorder(conn: sqlite3.Connection, year: int, force: bool = False) -> int:
    if not force and is_fresh(conn, "devorder", year):
        return 0
    raw = ps_json(f"{BASE_URL}/ek/api/DevOrder/GetAll?year={year}")
    rows = []
    for item in raw if isinstance(raw, list) else [raw]:
        if not item.get("active"):
            continue
        rows.append((
            trim(item.get("number")),
            trim(item.get("developmentOrderName")),
            1 if item.get("active") else 0,
            iso_date(item.get("dateFrom")),
            iso_date(item.get("dateUntil")),
            iso_date(item.get("sop")),
            trim(item.get("assignedProjectFamily")),
            trim(item.get("controller")),
            trim(item.get("hierarchy")),
        ))
    count = replace_table(
        conn,
        "devorder",
        ["ea_number", "title", "active", "date_from", "date_until", "sop", "project_family", "controller", "hierarchy"],
        rows,
        year,
    )
    conn.commit()
    return count


LEVEL_MAP = {2: "Bereich", 3: "Hauptabteilung", 4: "Abteilung", 5: "Unterabteilung"}


def _get_org_units(year: int) -> list:
    """OrgUnit/GetAll returns all org units with KST, level and leader mail."""
    return ps_json(f"{BASE_URL}/ek/api/OrgUnit/GetAll?year={year}")


def sync_el_planning(conn: sqlite3.Connection, year: int, force: bool = False) -> int:
    if not force and is_fresh(conn, "el_planning", year):
        return 0
    emp_data = ps_json(f"{BASE_URL}/ek/api/EmployeeHours?orgUnitId={ORG_UNIT_ID}&year={year}")
    all_users = []
    for bucket in ("current", "previous"):
        all_users.extend(emp_data.get(bucket, []) if isinstance(emp_data, dict) else [])
    rows = []
    for employee in all_users:
        uid = employee.get("idxUser")
        user_name = trim(employee.get("userFullName"))
        if not uid or not user_name:
            continue
        el = ps_json(
            f"{BASE_URL}/ek/api/PlanningException/GetPlanningExceptionsForUser"
            f"?userId={uid}&year={year}&orgUnitId={ORG_UNIT_ID}"
        )
        year_hours = as_float(el.get("yearWorkHours"))
        hourly_rate = as_float(el.get("hourlyRateFltValueMix"))
        for entry in el.get("planningExceptions", []):
            locks_months = entry.get("bookingRightsExceptionsMonths") or []
            locks = ", ".join(str(m) for m in locks_months) if locks_months else ""
            rows.append((
                user_name,
                trim(entry.get("number")),
                trim(entry.get("description")),
                trim(entry.get("projectFamily")),
                as_float(entry.get("percentInJan")),
                as_float(entry.get("percentInFeb")),
                as_float(entry.get("percentInMar")),
                as_float(entry.get("percentInApr")),
                as_float(entry.get("percentInMay")),
                as_float(entry.get("percentInJun")),
                as_float(entry.get("percentInJul")),
                as_float(entry.get("percentInAug")),
                as_float(entry.get("percentInSep")),
                as_float(entry.get("percentInOct")),
                as_float(entry.get("percentInNov")),
                as_float(entry.get("percentInDec")),
                trim(locks),
                year_hours,
                hourly_rate,
            ))
    count = replace_table(
        conn,
        "el_planning",
        [
            "user_name", "ea_number", "ea_title", "project_family",
            "pct_jan", "pct_feb", "pct_mar", "pct_apr", "pct_may", "pct_jun",
            "pct_jul", "pct_aug", "pct_sep", "pct_oct", "pct_nov", "pct_dec",
            "booking_locks", "year_work_hours", "hourly_rate",
        ],
        rows,
        year,
    )
    conn.commit()
    return count


def sync_stundensaetze(conn: sqlite3.Connection, year: int, force: bool = False) -> int:
    if not force and is_fresh(conn, "stundensaetze", year):
        return 0
    orgs = _get_org_units(year)
    rates_raw = ps_json(f"{BASE_URL}/ek/api/CostCenter/GetCostCenter2HourlyRates")
    # Build KST -> best rate (latest year)
    kst_rate: dict[int, tuple[int, float]] = {}
    for r in rates_raw if isinstance(rates_raw, list) else []:
        kst = r["intCostCenter"]
        yr = r["intYear"]
        rate = as_float(r.get("fltValueMix"))
        if kst not in kst_rate or yr > kst_rate[kst][0]:
            kst_rate[kst] = (yr, rate)
    rows = []
    for o in orgs if isinstance(orgs, list) else []:
        oe = trim(o.get("strOrgUnit"))
        kst = o.get("intCostCenter", 0)
        if not oe or not kst or kst not in kst_rate:
            continue
        rows.append((kst_rate[kst][0], str(kst), oe, kst_rate[kst][1]))
    count = replace_table(conn, "stundensaetze", ["jahr", "kst", "oe", "stundensatz"], rows, year)
    conn.commit()
    return count


def sync_ua_leiter(conn: sqlite3.Connection, year: int, force: bool = False) -> int:
    if not force and is_fresh(conn, "ua_leiter", year):
        return 0
    orgs = _get_org_units(year)
    rows = []
    for o in orgs if isinstance(orgs, list) else []:
        mail = trim(o.get("strUserMail"))
        if not mail:
            continue
        oe = trim(o.get("strOrgUnit"))
        level = o.get("intOrgUnitLevel", 0)
        ebene = LEVEL_MAP.get(level, f"Level_{level}")
        rows.append((oe, ebene, mail))
    count = replace_table(conn, "ua_leiter", ["oe", "ebene", "mail"], rows, year)
    conn.commit()
    return count


SYNC_FUNCS = {
    "btl": sync_btl,
    "devorder": sync_devorder,
    "el_planning": sync_el_planning,
    "stundensaetze": sync_stundensaetze,
    "ua_leiter": sync_ua_leiter,
}


def validate_select(sql: str) -> None:
    sql_clean = sql.strip().lower()
    if not (sql_clean.startswith("select ") or sql_clean.startswith("with ")):
        raise ValueError("Nur SELECT/CTE-SELECT ist erlaubt.")
    for banned in (" insert ", " update ", " delete ", " drop ", " alter ", " create ", " attach ", " pragma "):
        if banned in f" {sql_clean} ":
            raise ValueError(f"Verbotenes SQL erkannt:{banned.strip()}")


def run_select(sql: str, *, output: str | None = None, title: str = "Budget-Auswertung") -> Path:
    validate_select(sql)
    with connect() as conn:
        init_db(conn)
        rows = conn.execute(sql).fetchall()
    headers = list(rows[0].keys()) if rows else []
    data = [list(r) for r in rows]
    path = report_path("budget_query", output=output)
    body = [section("SQL", f"```sql\n{sql.strip()}\n```"), section("Ergebnis", table_md(data, headers))]
    write_report(path, title, body)
    return path


def parse_args():
    parser = argparse.ArgumentParser(description="BPLUS budget.db Sync/Query")
    sub = parser.add_subparsers(dest="command", required=True)

    sync = sub.add_parser("sync", help="Tabelle oder alle Tabellen synchronisieren")
    sync.add_argument("table", choices=[*SYNC_FUNCS.keys(), "all"])
    sync.add_argument("--year", type=int, default=datetime.now().year)
    sync.add_argument("--force", action="store_true")

    query = sub.add_parser("query", help="SELECT auf budget.db ausfuehren")
    query.add_argument("sql")
    query.add_argument("--output")
    query.add_argument("--title", default="Budget-Auswertung")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "query":
        path = run_select(args.sql, output=args.output, title=args.title)
        print(path)
        return 0

    with connect() as conn:
        init_db(conn)
        failures = []
        targets = list(SYNC_FUNCS.keys()) if args.table == "all" else [args.table]
        for name in targets:
            try:
                count = SYNC_FUNCS[name](conn, args.year, force=args.force)
                print(f"{name}: ok ({count} Zeilen)")
            except Exception as exc:
                conn.rollback()
                failures.append((name, str(exc)))
                print(f"{name}: FEHLER: {exc}", file=sys.stderr)
        if failures:
            print("", file=sys.stderr)
            print("sync fehlgeschlagen:", file=sys.stderr)
            for name, msg in failures:
                print(f" - {name}: {msg}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
