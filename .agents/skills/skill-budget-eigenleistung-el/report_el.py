#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(WORKSPACE / "scripts"))

from report_utils import note, report_path, section, sync_info, table_md, warning, write_report  # noqa: E402

DB_PATH = WORKSPACE / "userdata" / "budget.db"
BUDGET_DB = WORKSPACE / "scripts" / "budget_db.py"
LOGS_DIR = WORKSPACE / "userdata" / "tmp" / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)


def setup_logging() -> Path:
    log_path = LOGS_DIR / f"report_el_{datetime.now():%Y%m%d_%H%M%S}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler(sys.stderr)],
    )
    return log_path


LOG_PATH = setup_logging()


def sync(table: str, year: int, force: bool = False) -> bool:
    cmd = [sys.executable, str(BUDGET_DB), "sync", table, "--year", str(year)]
    if force:
        cmd.append("--force")
    r = subprocess.run(cmd, capture_output=True)
    ok = r.returncode == 0
    if ok:
        logging.info("sync %s erfolgreich", table)
    else:
        stderr = r.stderr.decode("utf-8", errors="replace").strip()
        stdout = r.stdout.decode("utf-8", errors="replace").strip()
        logging.warning("sync %s fehlgeschlagen: %s", table, stderr or stdout)
    return ok


def avg_expr(alias: str = "") -> str:
    p = f"{alias}." if alias else ""
    return (
        f"({p}pct_jan+{p}pct_feb+{p}pct_mar+{p}pct_apr+{p}pct_may+{p}pct_jun+"
        f"{p}pct_jul+{p}pct_aug+{p}pct_sep+{p}pct_oct+{p}pct_nov+{p}pct_dec)/12.0"
    )


def sync_warning(conn: sqlite3.Connection, table: str, failed: bool) -> str | None:
    if not failed:
        return None
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT synced_at FROM _sync_meta WHERE table_name = ?", (table,)).fetchone()
    if row:
        return f"Sync fuer `{table}` fehlgeschlagen. Bericht nutzt vorhandene DB-Daten vom {row['synced_at']}."
    return f"Sync fuer `{table}` fehlgeschlagen."


def section_ma_planung(conn: sqlite3.Connection, mitarbeiter: str) -> str:
    sql = f"""
        SELECT user_name, ea_number, ea_title, project_family, ROUND({avg_expr()}, 1) AS avg_pct, booking_locks,
               ROUND(year_work_hours, 1) AS year_work_hours, ROUND(hourly_rate, 2) AS hourly_rate
        FROM el_planning
        WHERE LOWER(user_name) LIKE ?
        ORDER BY user_name, ea_number
    """
    rows = conn.execute(sql, (f"%{mitarbeiter.lower()}%",)).fetchall()
    if not rows:
        return section("MA-Planung", note("Kein passender Mitarbeiter gefunden."))
    table = [[r["user_name"], r["ea_number"], r["ea_title"], r["project_family"], f"{r['avg_pct']:.1f}%", r["booking_locks"], r["year_work_hours"], r["hourly_rate"]] for r in rows]
    return section("MA-Planung", table_md(table, ["Mitarbeiter", "EA-Nummer", "EA-Titel", "Projektfamilie", "Avg %", "Sperrungen", "Jahresstunden", "Stundensatz"]))


def section_buchungssperren(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        """
        SELECT user_name, ea_number, ea_title, project_family, booking_locks
        FROM el_planning
        WHERE booking_locks IS NOT NULL AND booking_locks != ''
        ORDER BY user_name, ea_number
        """
    ).fetchall()
    table = [[r["user_name"], r["ea_number"], r["ea_title"], r["project_family"], r["booking_locks"]] for r in rows]
    return section("Buchungssperren", table_md(table, ["Mitarbeiter", "EA-Nummer", "EA-Titel", "Projektfamilie", "Gesperrte Monate"]))


def section_jahressicht(conn: sqlite3.Connection) -> str:
    sql = f"""
        SELECT ea_number, MAX(ea_title) AS ea_title, MAX(project_family) AS project_family,
               ROUND(SUM(({avg_expr()} / 100.0) * year_work_hours * hourly_rate)) AS el_eur
        FROM el_planning
        GROUP BY ea_number
        ORDER BY el_eur DESC, ea_number
    """
    rows = conn.execute(sql).fetchall()
    table = [[r["ea_number"], r["ea_title"], r["project_family"], int(r["el_eur"] or 0)] for r in rows]
    return section("Jahressicht Eigenleistung", table_md(table, ["EA-Nummer", "EA-Titel", "Projektfamilie", "EL (EUR)"]))


def section_gesamt(conn: sqlite3.Connection) -> str:
    sql = f"""
        SELECT e.ea_number, MAX(e.ea_title) AS ea_title, MAX(e.project_family) AS project_family,
               ROUND(SUM(({avg_expr('e')} / 100.0) * e.year_work_hours * e.hourly_rate)) AS el_eur,
               COALESCE(b.fremd_eur, 0) AS fremd_eur
        FROM el_planning e
        LEFT JOIN (
            SELECT dev_order, SUM(planned_value) AS fremd_eur
            FROM btl
            GROUP BY dev_order
        ) b ON e.ea_number = b.dev_order
        GROUP BY e.ea_number, b.fremd_eur
        ORDER BY el_eur DESC, e.ea_number
    """
    rows = conn.execute(sql).fetchall()
    table = []
    total_el = 0
    total_fremd = 0
    for r in rows:
        el = int(r["el_eur"] or 0)
        fr = int(r["fremd_eur"] or 0)
        total = el + fr
        share = (100.0 * el / total) if total else 0.0
        total_el += el
        total_fremd += fr
        table.append([r["ea_number"], r["ea_title"], r["project_family"], el, fr, total, f"{share:.1f}%"])
    mermaid = "\n".join([
        "```mermaid",
        "pie showData",
        "    title EL vs. Fremdleistung (gesamt)",
        f'    "EL" : {total_el}',
        f'    "Fremdleistung" : {total_fremd}',
        "```",
    ])
    return section("EL vs. Fremdleistung", table_md(table, ["EA-Nummer", "EA-Titel", "Projektfamilie", "EL (EUR)", "Fremd (EUR)", "Summe", "EL-Anteil"]) + "\n" + mermaid + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="EL-Report auf budget.db")
    parser.add_argument("--usecase", choices=["ma-planung", "buchungssperren", "jahressicht", "gesamt-uebersicht"], default="ma-planung")
    parser.add_argument("--mitarbeiter")
    parser.add_argument("--jahr", type=int, default=datetime.now().year)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()

    if args.usecase == "ma-planung" and not args.mitarbeiter:
        print("--mitarbeiter ist fuer ma-planung erforderlich", file=sys.stderr)
        return 1

    el_ok = sync("el_planning", args.jahr, force=args.force)
    btl_ok = True
    if args.usecase == "gesamt-uebersicht":
        btl_ok = sync("btl", args.jahr, force=args.force)

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        if not conn.execute("SELECT 1 FROM el_planning LIMIT 1").fetchone():
            print("Keine EL-Daten verfuegbar.", file=sys.stderr)
            return 1
        if args.usecase == "gesamt-uebersicht" and not conn.execute("SELECT 1 FROM btl LIMIT 1").fetchone():
            print("Keine BTL-Daten fuer gesamt-uebersicht verfuegbar.", file=sys.stderr)
            return 1

        label = args.mitarbeiter if args.usecase == "ma-planung" else args.usecase
        path = report_path("el", label=label, output=args.output)
        sections = [note(f"Logdatei: {LOG_PATH}")]
        warn_el = sync_warning(conn, "el_planning", not el_ok)
        warn_btl = sync_warning(conn, "btl", args.usecase == "gesamt-uebersicht" and not btl_ok)
        if warn_el:
            sections.append(warning(warn_el))
        if warn_btl:
            sections.append(warning(warn_btl))

        if args.usecase == "ma-planung":
            sections.append(section_ma_planung(conn, args.mitarbeiter))
        elif args.usecase == "buchungssperren":
            sections.append(section_buchungssperren(conn))
        elif args.usecase == "jahressicht":
            sections.append(section_jahressicht(conn))
        else:
            sections.append(section_gesamt(conn))

        meta = [sync_info(DB_PATH, "el_planning")]
        if args.usecase == "gesamt-uebersicht":
            meta.append(sync_info(DB_PATH, "btl"))
        write_report(path, f"Eigenleistungs-Report: {args.usecase}", sections, meta_lines=meta)
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
