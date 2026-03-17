#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(WORKSPACE / "scripts" / "budget"))

from report_utils import note, report_path, section, sync_info, table_md, warning, write_report  # noqa: E402

DB_PATH = WORKSPACE / "userdata" / "budget.db"
BUDGET_DB = WORKSPACE / "scripts" / "budget" / "budget_db.py"


def sync_btl(year: int, force: bool = False) -> bool:
    """Return True on success, False on failure (old data may still be usable)."""
    cmd = [sys.executable, str(BUDGET_DB), "sync", "btl", "--year", str(year)]
    if force:
        cmd.append("--force")
    r = subprocess.run(cmd, capture_output=True)
    return r.returncode == 0


def euro(value: int) -> str:
    return f"{int(value):,}".replace(",", ".")


def where_clause(args):
    parts, params = [], []
    if args.firma:
        parts.append("LOWER(company) LIKE ?")
        params.append(f"%{args.firma.lower()}%")
    if args.status:
        parts.append("LOWER(status) LIKE ?")
        params.append(f"%{args.status.lower()}%")
    if args.ea:
        parts.append("(LOWER(dev_order) LIKE ? OR LOWER(ea) LIKE ?)")
        params.extend([f"%{args.ea.lower()}%", f"%{args.ea.lower()}%"])
    if args.projekt:
        parts.append("LOWER(projektfamilie) LIKE ?")
        params.append(f"%{args.projekt.lower()}%")
    if args.oe:
        parts.append("LOWER(org_unit) LIKE ?")
        params.append(f"%{args.oe.lower()}%")
    return (" WHERE " + " AND ".join(parts)) if parts else "", params


def fetch_rows(args):
    where_sql, params = where_clause(args)
    sql = f"""
        SELECT concept, dev_order, ea, title, planned_value, company, status
        FROM btl
        {where_sql}
        ORDER BY planned_value DESC, concept
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(sql, params).fetchall()


def section_items(rows):
    total = sum(int(r["planned_value"] or 0) for r in rows)
    body = [[r["concept"], r["dev_order"], r["ea"], r["title"], euro(int(r["planned_value"] or 0)), r["company"], r["status"]] for r in rows]
    body.append(["", "", "", "**Summe**", f"**{euro(total)}**", "", ""])
    return section("Einzelvorgaenge", table_md(body, ["Konzept", "EA-Nummer", "EA-Titel", "BM-Titel", "Wert", "Firma", "Status"]))


def section_status(rows):
    grouped = defaultdict(lambda: [0, 0])
    for r in rows:
        grouped[r["status"]][0] += 1
        grouped[r["status"]][1] += int(r["planned_value"] or 0)
    table = [[status, count, euro(total)] for status, (count, total) in sorted(grouped.items())]
    mermaid = ["```mermaid", "pie showData", "    title Status-Verteilung"]
    mermaid.extend([f'    "{status}" : {total}' for status, (_, total) in sorted(grouped.items())])
    mermaid.append("```")
    return section("Nach Status", table_md(table, ["Status", "Anzahl", "Wert"]) + "\n" + "\n".join(mermaid) + "\n")


def section_company(rows, top: int | None):
    grouped = defaultdict(lambda: [0, 0])
    for r in rows:
        company = (r["company"] or "").strip()
        grouped[company][0] += 1
        grouped[company][1] += int(r["planned_value"] or 0)
    ordered = sorted(grouped.items(), key=lambda item: (-item[1][1], item[0]))
    if top:
        ordered = ordered[:top]
    table = [[company, count, euro(total)] for company, (count, total) in ordered]
    return section("Nach Firma", table_md(table, ["Firma", "Anzahl", "Wert"]))


def section_ea(rows):
    grouped = defaultdict(lambda: [0, 0, ""])
    for r in rows:
        key = r["dev_order"] or "(ohne EA)"
        grouped[key][0] += 1
        grouped[key][1] += int(r["planned_value"] or 0)
        grouped[key][2] = r["ea"] or ""
    ordered = sorted(grouped.items(), key=lambda item: (-item[1][1], item[0]))
    table = [[ea_number, ea_title, count, euro(total)] for ea_number, (count, total, ea_title) in ordered]
    return section("Nach EA", table_md(table, ["EA-Nummer", "EA-Titel", "Anzahl", "Wert"]))


def main() -> int:
    parser = argparse.ArgumentParser(description="BPLUS-Report auf budget.db")
    parser.add_argument("--firma")
    parser.add_argument("--status")
    parser.add_argument("--ea")
    parser.add_argument("--projekt")
    parser.add_argument("--oe")
    parser.add_argument("--top", type=int)
    parser.add_argument("--year", type=int, default=datetime.now().year)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()

    sync_ok = sync_btl(args.year, force=args.force)
    rows = fetch_rows(args)
    label = args.firma or args.status or args.ea or args.projekt or args.oe or "gesamt"
    path = report_path("bplus", label=label, output=args.output)

    sections = []
    if not sync_ok:
        if rows:
            sections.append(warning("Sync fehlgeschlagen - Bericht nutzt vorhandene DB-Daten (siehe Datenstand)."))
        else:
            sections.append(warning("Sync fehlgeschlagen und keine vorhandenen Daten verfuegbar."))
    sections.append(note(f"Treffer: {len(rows)}"))
    if not rows:
        sections.append(note("Keine Treffer gefunden."))
    else:
        sections.extend([section_items(rows), section_status(rows)])
        if not args.firma:
            sections.append(section_company(rows, args.top))
        if len({r["dev_order"] for r in rows if r["dev_order"]}) > 1:
            sections.append(section_ea(rows))

    write_report(path, "BPLUS-NG Auswertung", sections, meta_lines=[sync_info(DB_PATH, "btl")])
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
