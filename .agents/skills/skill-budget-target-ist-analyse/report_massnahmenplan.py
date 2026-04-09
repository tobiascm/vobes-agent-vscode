"""
Budget-Maßnahmenplan EKEK/1
Erzeugt Markdown mit Aufgabenbereich- und Firmen-Tabelle.
Maßnahmen-Spalte bleibt leer (Agent füllt nach User-Vorgabe).

Usage:
    python .agents/skills/skill-budget-massnahmenplan/report_massnahmenplan.py [--year YYYY]
"""

import argparse
import csv
import datetime
import os
import re
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
BUDGET_DB = os.path.join(REPO_ROOT, "scripts", "budget", "budget_db.py")
OUT_DIR = os.path.join(REPO_ROOT, "userdata", "budget")
TARGET_CSV = os.path.join(SCRIPT_DIR, "target.csv")
STATUS_CSV = os.path.join(SCRIPT_DIR, "status_mapping.csv")
PRAEMISSEN_MD = os.path.join(SCRIPT_DIR, "praemissen.md")

# ── CSV laden: 2025 + Target ──────────────────────────────────────────

def load_status_mapping() -> dict[str, str]:
    """Liest status_mapping.csv → {status: benennung}."""
    mapping: dict[str, str] = {}
    with open(STATUS_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            mapping[row["Status"]] = row["Benennung"]
    return mapping


def load_targets() -> tuple[dict[str, int], dict[str, int], list[str], dict[str, int]]:
    """Liest target.csv → (ref_2025, target_2026, area_order, start_q)."""
    ref_2025: dict[str, int] = {}
    target_2026: dict[str, int] = {}
    start_q: dict[str, int] = {}
    area_order: list[str] = []
    with open(TARGET_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            area = row["Aufgabenbereich"].strip()
            ref_2025[area] = int(row["2025"].strip())
            target_2026[area] = int(row["Target_2026"].strip())
            start_q[area] = int(row.get("Start_Q", "1").strip() or "1")
            area_order.append(area)
    return ref_2025, target_2026, area_order, start_q

# ── Prämissen laden ───────────────────────────────────────────────────

def load_praemissen() -> str:
    """Liest praemissen.md als String."""
    with open(PRAEMISSEN_MD, encoding="utf-8") as f:
        return f.read().strip()

# ── AUDI fest (aus Target-CSV abgeleitet) ─────────────────────────────
AUDI_KEY = "AUDI - Bibliotheksarbeiten (Audi)"

# ── Firma→Aufgabenbereich Mapping ─────────────────────────────────────

def _parse_gewerk_numbers(bm_text: str) -> set[int]:
    """Extrahiert alle Gewerk-Nummern (#1, #2, …) aus dem BM-Text."""
    numbers: set[int] = set()
    for m in re.finditer(r'Gewerk\s+#([\d,#\s]+)', bm_text, re.IGNORECASE):
        for n in re.findall(r'\d+', m.group(1)):
            numbers.add(int(n))
    return numbers


def classify_bm(company: str, title: str, bm_text: str = "") -> str:
    """Ordnet eine BM anhand Firma+Titel+BM-Text einem Aufgabenbereich zu."""
    c = company.upper()
    t = title.upper() if title else ""

    if "EDAG" in c or "BERTRANDT" in c:
        return "Systemschaltpläne und Bibl. (EDAG, Bertrandt)"
    if "GROUP SERVICES" in c or "T-SYSTEMS" in c:
        return "CATIA-Bibl. (GroupServices)"
    if "FES " in c or "FEV " in c:
        return "Projektbüro / Prüfbüro (FES, B&W)"
    if "MSG " in c:
        return "BordnetzGPT"
    if "PEC " in c:
        return "SYS-Flow (PEC)"
    if "SUMITOMO" in c or "SEBN" in c:
        return "Pilot und Anwendertest VOBES2025 (SEBN)"
    if "VOITAS" in c:
        return "RuleChecker (4soft, ex Voitas)"

    # 4SOFT: Split nach BM-Titel
    if "4SOFT" in c:
        if any(kw in t for kw in ["TE-PMT", "BORDNETZ", "KONZEPTENTW", "INTEGRATION"]):
            return "SW-Entwicklung VOBES2025 (4soft)"
        return "Vorentwicklung (4soft)"

    # THIESEN: Split nach Gewerk-Nummern im BM-Text
    #   nur Gewerk #2           → Spezifikation (Stückpreis-Abruf)
    #   mehrere Gewerke (#1,#2,#3,#5 + #4 FPs) → Bordnetz Support/RollOut
    if "THIESEN" in c:
        gewerke = _parse_gewerk_numbers(bm_text)
        if gewerke and gewerke != {2}:
            return "Bordnetz Support, RollOut (Thiesen)"
        return "Spez. und Test VOBES2025 (Thiesen)"

    # Fallback: KST/Werk/Sonstige → ignorieren (planned_value meist 0)
    return "_SONSTIGE"


def run_sql(sql: str, year: int) -> list[dict]:
    """Führt SQL über budget_db.py aus und parst die Markdown-Tabelle."""
    cmd = [
        sys.executable, BUDGET_DB, "query", sql,
        "--stdout", "--no-file", "--sync", "--year", str(year),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    if result.returncode != 0:
        print(f"FEHLER bei SQL:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)

    lines = result.stdout.strip().split("\n")
    # Find table header (starts with |)
    table_lines = [l for l in lines if l.startswith("|")]
    if len(table_lines) < 3:
        return []

    # Parse header
    headers = [h.strip() for h in table_lines[0].split("|")[1:-1]]
    rows = []
    for row_line in table_lines[2:]:  # skip separator
        vals = [v.strip() for v in row_line.split("|")[1:-1]]
        rows.append(dict(zip(headers, vals)))
    return rows


def fmt(v: int) -> str:
    return f"{v:,}".replace(",", ".") + " T€"


def delta_fmt(d: int) -> str:
    sign = "+" if d > 0 else ""
    return sign + fmt(d)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=datetime.date.today().year)
    args = parser.parse_args()
    year = args.year

    # ── CSV + Prämissen laden ──────────────────────────────────────────
    REF_2025, TARGET_2026, AREA_ORDER, START_Q = load_targets()
    praemissen_text = load_praemissen()
    AUDI_FIXED = TARGET_2026.get(AUDI_KEY, 0)

    # ── Quartal-Periode berechnen ──────────────────────────────────────
    # Ab 1 Monat nach Quartalsanfang → nächstes Quartal einbeziehen
    month = datetime.date.today().month
    if month >= 8:
        num_q = 4
    elif month >= 5:
        num_q = 3
    elif month >= 2:
        num_q = 2
    else:
        num_q = 1
    q_label = f"Q1-{num_q}" if num_q > 1 else "Q1"
    q_ratio = num_q / 4

    # ── BMs laden (inkl. Status) ───────────────────────────────────────
    sql = "SELECT concept, title, planned_value, company, status, bm_text FROM btl"
    rows = run_sql(sql, year)

    # ── Status-Mapping aus CSV laden ───────────────────────────────────
    status_map = load_status_mapping()

    # ── Sync-Zeitpunkt ermitteln ───────────────────────────────────────
    schema_cmd = [sys.executable, BUDGET_DB, "schema"]
    schema_out = subprocess.run(schema_cmd, capture_output=True, text=True, cwd=REPO_ROOT).stdout
    sync_match = re.search(r"btl\s+\|\s+\d+\s+\|\s+([\d\-T:]+)", schema_out)
    sync_time = sync_match.group(1) if sync_match else "unbekannt"

    # ── BMs klassifizieren ─────────────────────────────────────────────
    area_values: dict[str, int] = {a: 0 for a in AREA_ORDER}
    area_values["_SONSTIGE"] = 0
    firm_values: dict[str, dict] = {}  # firm → {sum, count, beauftragt}
    # Für Soll-Berechnung: Firma→Area→Ist-Anteil
    firm_area_ist: dict[str, dict[str, int]] = {}

    for row in rows:
        pv = int(float(row.get("planned_value", "0")))
        company = row.get("company", "")
        title = row.get("title", "")
        status = row.get("status", "")
        bm_text = row.get("bm_text", "")
        area = classify_bm(company, title, bm_text)
        area_values[area] = area_values.get(area, 0) + pv

        # Firmen-Aggregation
        if company not in firm_values:
            firm_values[company] = {"sum": 0, "count": 0, "bestellt": 0, "durchlauf": 0, "konzept": 0}
        firm_values[company]["sum"] += pv
        firm_values[company]["count"] += 1
        benennung = status_map.get(status, "")
        if benennung == "bestellt":
            firm_values[company]["bestellt"] += pv
        elif benennung == "im Durchlauf":
            firm_values[company]["durchlauf"] += pv
        elif benennung == "Konzept":
            firm_values[company]["konzept"] += pv

        # Firma→Area Zuordnung für Soll-Verteilung
        if area != "_SONSTIGE":
            if company not in firm_area_ist:
                firm_area_ist[company] = {}
            firm_area_ist[company][area] = firm_area_ist[company].get(area, 0) + pv

    # ── AUDI-Korrektur: von Systemschaltplänen abziehen ────────────────
    sysschalt_key = "Systemschaltpläne und Bibl. (EDAG, Bertrandt)"
    area_values[sysschalt_key] -= AUDI_FIXED * 1000
    area_values[AUDI_KEY] = AUDI_FIXED * 1000

    # ── In T€ umrechnen ───────────────────────────────────────────────
    area_te = {a: round(v / 1000) for a, v in area_values.items() if a != "_SONSTIGE"}

    # ── Soll pro Firma berechnen (proportional aus Area-Targets) ───────
    # Für jede Area: Firma-Anteil am Ist → gleicher Anteil am Target
    area_totals: dict[str, int] = {}
    for firm, areas in firm_area_ist.items():
        for area, val in areas.items():
            area_totals[area] = area_totals.get(area, 0) + val

    firm_soll: dict[str, int] = {}
    firm_soll_q: dict[str, int] = {}
    for firm, areas in firm_area_ist.items():
        soll = 0
        soll_q = 0
        for area, val in areas.items():
            total = area_totals.get(area, 1)
            target = TARGET_2026.get(area, 0) * 1000
            area_soll = round(target * val / total) if total > 0 else 0
            soll += area_soll
            # Area-spezifische Q-Ratio (Start_Q berücksichtigen)
            sq = START_Q.get(area, 1)
            if num_q < sq:
                a_q_ratio = 0.0
            else:
                a_q_ratio = (num_q - sq + 1) / (4 - sq + 1)
            soll_q += round(area_soll * a_q_ratio)
        firm_soll[firm] = soll
        firm_soll_q[firm] = soll_q

    # ── Markdown aufbauen ─────────────────────────────────────────────
    md = []
    md.append(f"# EKEK/1 Budget {year} — Target / Ist-Analyse")
    md.append("")
    md.append(f"**Stand BPLUS-NG:** {sync_time} | **Erstellt:** {datetime.date.today().strftime('%d.%m.%Y')}")
    md.append("")

    # ── Gesamtübersicht (oben) ────────────────────────────────────────
    # Summen vorberechnen
    sum_25 = sum_t = sum_i = 0
    for area in AREA_ORDER:
        sum_25 += REF_2025[area]
        sum_t += TARGET_2026[area]
        sum_i += area_te.get(area, 0)

    md.append("## Gesamtübersicht")
    md.append("")
    md.append("| | Wert |")
    md.append("|---|---:|")
    md.append(f"| IST 2025 (Referenz) | {fmt(sum_25)} |")
    md.append(f"| Ist (BPLUS) | {fmt(sum_i)} |")
    md.append(f"| Target | {fmt(sum_t)} |")
    md.append(f"| Delta Ist vs. Target | {delta_fmt(sum_i - sum_t)} |")
    md.append("")

    # ── Tabelle 1: Target - Ist - Vergleich ───────────────────────────
    md.append("---")
    md.append("")
    md.append("## Target - Ist - Vergleich")
    md.append("")
    md.append("| Aufgabenbereich | 2025 | Target | Ist | Delta | Maßnahmen |")
    md.append("|---|---:|---:|---:|---:|---|")

    s25 = s_t = s_i = 0
    for area in AREA_ORDER:
        if area == AUDI_KEY:
            continue  # Audi kommt separat
        v25 = REF_2025[area]
        vt = TARGET_2026[area]
        vi = area_te.get(area, 0)
        delta = vi - vt
        md.append(f"| {area} | {fmt(v25)} | {fmt(vt)} | {fmt(vi)} | {delta_fmt(delta)} | |")
        s25 += v25
        s_t += vt
        s_i += vi

    md.append(f"| **Summe** | **{fmt(s25)}** | **{fmt(s_t)}** | **{fmt(s_i)}** | **{delta_fmt(s_i - s_t)}** | |")

    # Audi
    v25_a = REF_2025[AUDI_KEY]
    vt_a = TARGET_2026[AUDI_KEY]
    vi_a = area_te.get(AUDI_KEY, 0)
    md.append(f"| {AUDI_KEY} | {fmt(v25_a)} | {fmt(vt_a)} | {fmt(vi_a)} | {delta_fmt(vi_a - vt_a)} | |")
    s25 += v25_a
    s_t += vt_a
    s_i += vi_a
    md.append(f"| **Summe inkl. Audi** | **{fmt(s25)}** | **{fmt(s_t)}** | **{fmt(s_i)}** | **{delta_fmt(s_i - s_t)}** | |")

    # ── Tabelle 2: Firmen ─────────────────────────────────────────────
    md.append("")
    md.append("---")
    md.append("")
    md.append("## Firmen-Übersicht")
    md.append("")
    md.append(f"| Firma | BMs | Soll | Ist | DIFF Ges. | Soll {q_label} | bestellt | im Durchlauf | 01 Erstellung | DIFF {q_label} | Maßnahmen |")
    md.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")

    firm_total = 0
    firm_total_soll = 0
    firm_total_bestellt = 0
    firm_total_durchlauf = 0
    firm_total_konzept = 0
    firm_count_total = 0
    csv_rows: list[list] = []  # für CSV-Export
    for firm, data in sorted(firm_values.items(), key=lambda x: -x[1]["sum"]):
        ist = round(data["sum"] / 1000)
        soll = round(firm_soll.get(firm, 0) / 1000)
        bestellt = round(data["bestellt"] / 1000)
        durchlauf = round(data["durchlauf"] / 1000)
        konzept = round(data["konzept"] / 1000)
        soll_q = round(firm_soll_q.get(firm, 0) / 1000)
        diff_planung = ist - soll
        diff_q = soll_q - (durchlauf + bestellt)
        c = data["count"]
        firm_short = firm.split()[0] if firm.strip() else firm
        md.append(f"| {firm_short} | {c} | {fmt(soll)} | {fmt(ist)} | {delta_fmt(diff_planung)} | {fmt(soll_q)} | {fmt(bestellt)} | {fmt(durchlauf)} | {fmt(konzept)} | {delta_fmt(diff_q)} | |")
        csv_rows.append([firm, c, soll, ist, diff_planung, soll_q, bestellt, durchlauf, konzept, diff_q, ""])
        firm_total += ist
        firm_total_soll += soll
        firm_total_bestellt += bestellt
        firm_total_durchlauf += durchlauf
        firm_total_konzept += konzept
        firm_count_total += c

    firm_total_soll_q = sum(round(firm_soll_q.get(f, 0) / 1000) for f in firm_values)
    firm_total_diff_q = firm_total_soll_q - (firm_total_durchlauf + firm_total_bestellt)
    firm_total_diff_planung = firm_total - firm_total_soll
    md.append(f"| **Gesamt** | **{firm_count_total}** | **{fmt(firm_total_soll)}** | **{fmt(firm_total)}** | **{delta_fmt(firm_total_diff_planung)}** | **{fmt(firm_total_soll_q)}** | **{fmt(firm_total_bestellt)}** | **{fmt(firm_total_durchlauf)}** | **{fmt(firm_total_konzept)}** | **{delta_fmt(firm_total_diff_q)}** | |")
    csv_rows.append(["Gesamt", firm_count_total, firm_total_soll, firm_total, firm_total_diff_planung, firm_total_soll_q, firm_total_bestellt, firm_total_durchlauf, firm_total_konzept, firm_total_diff_q, ""])

    # ── Prämissen (am Ende) ───────────────────────────────────────────
    md.append("")
    md.append("---")
    md.append("")
    md.append(praemissen_text)
    md.append(f"- 2026-Ist: BPLUS-NG Sync vom {sync_time}")

    # ── Datei schreiben ───────────────────────────────────────────────
    os.makedirs(OUT_DIR, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = os.path.join(OUT_DIR, f"{ts}_budget_massnahmenplan_ekek1.md")
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")

    # ── CSV schreiben (Firmen-Übersicht) ──────────────────────────────
    csv_file = os.path.join(OUT_DIR, f"{ts}_budget_massnahmenplan_ekek1.csv")
    csv_header = ["Firma", "BMs", "Soll", "Ist", "DIFF Ges.", f"Soll {q_label}", "bestellt", "im Durchlauf", "01 Erstellung", f"DIFF {q_label}", "Maßnahmen"]
    with open(csv_file, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(csv_header)
        writer.writerows(csv_rows)

    # Nur Pfad ausgeben (relative zum Repo)
    rel = os.path.relpath(out_file, REPO_ROOT)
    rel_csv = os.path.relpath(csv_file, REPO_ROOT)
    print(rel)
    print(rel_csv)


if __name__ == "__main__":
    main()
