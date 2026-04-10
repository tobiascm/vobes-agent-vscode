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
from copy import copy
from dataclasses import dataclass, field

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
BUDGET_DB = os.path.join(REPO_ROOT, "scripts", "budget", "budget_db.py")
OUT_DIR = os.path.join(REPO_ROOT, "userdata", "budget")
TARGET_CSV = os.path.join(SCRIPT_DIR, "target.csv")
STATUS_CSV = os.path.join(SCRIPT_DIR, "status_mapping.csv")
PRAEMISSEN_MD = os.path.join(SCRIPT_DIR, "praemissen.md")

PDF_CSS = """
body {
  font-family: Arial, sans-serif;
  font-size: 8pt;
  line-height: 1.25;
}
h1, h2, h3 { margin: 10pt 0 4pt; }
p, li { margin: 2pt 0; }
hr {
  border: 0;
  border-top: 1px solid #999;
  margin: 8pt 0;
}
table {
  width: auto;
  border-collapse: collapse;
  table-layout: auto;
  font-size: 6.5pt;
  margin: 0 0 6pt 0;
}
th, td {
  border: 0.4pt solid #999;
  padding: 1pt 6pt;
  vertical-align: top;
  white-space: nowrap;
}
"""

# ── CSV laden: 2025 + Target ──────────────────────────────────────────

def load_status_mapping() -> dict[str, str]:
    """Liest status_mapping.csv → {status: benennung}."""
    mapping: dict[str, str] = {}
    with open(STATUS_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            mapping[row["Status"]] = row["Benennung"]
    return mapping


def load_targets() -> tuple[dict[str, int], dict[str, int], list[str], dict[str, int], dict[str, dict[str, int | str]]]:
    """Liest target.csv → (ref_2025, target_2026, area_order, start_q, company_target_overrides)."""
    ref_2025: dict[str, int] = {}
    target_2026: dict[str, int] = {}
    start_q: dict[str, int] = {}
    area_order: list[str] = []
    company_target_overrides: dict[str, dict[str, int | str]] = {}
    with open(TARGET_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            area = row["Aufgabenbereich"].strip()
            ref_2025[area] = int(row["2025"].strip())
            target_2026[area] = int(row["Target_2026"].strip())
            start_q[area] = int(row.get("Start_Q", "1").strip() or "1")
            area_order.append(area)
            for col_name, raw_value in row.items():
                if col_name in {"Aufgabenbereich", "2025", "Target_2026", "Start_Q"}:
                    continue
                if not col_name or not col_name.endswith("_Target_2026"):
                    continue
                value = (raw_value or "").strip()
                if not value:
                    continue
                company_key = col_name.removesuffix("_Target_2026").upper()
                company_target_overrides[company_key] = {
                    "area": area,
                    "target_te": int(value),
                    "start_q": start_q[area],
                }
    return ref_2025, target_2026, area_order, start_q, company_target_overrides

# ── Prämissen laden ───────────────────────────────────────────────────

def load_praemissen() -> str:
    """Liest praemissen.md als String."""
    with open(PRAEMISSEN_MD, encoding="utf-8") as f:
        return f.read().strip()


def write_pdf_beside_markdown(md_file: str) -> str | None:
    """Best-effort Markdown->PDF Export im A4-Querformat."""
    pdf_file = os.path.splitext(md_file)[0] + ".pdf"
    try:
        from markdown_pdf import MarkdownPdf, Section
    except ImportError as exc:
        print(f"WARNUNG: PDF-Export übersprungen: markdown-pdf nicht installiert ({exc})", file=sys.stderr)
        return None

    try:
        with open(md_file, encoding="utf-8") as f:
            md_text = f.read()
        pdf = MarkdownPdf(toc_level=2, optimize=True)
        pdf.add_section(Section(md_text, paper_size="A4-L"), user_css=PDF_CSS)
        pdf.save(pdf_file)
        return pdf_file
    except Exception as exc:  # PDF ist Zusatzartefakt; Markdown/CSV bleiben gültig.
        print(f"WARNUNG: PDF-Export fehlgeschlagen: {exc}", file=sys.stderr)
        return None

# ── AUDI fest (aus Target-CSV abgeleitet) ─────────────────────────────
AUDI_KEY = "AUDI - Bibliotheksarbeiten (Audi)"
THIESEN_SUPPORT_KEY = "Bordnetz Support, RollOut (Thiesen)"
THIESEN_SPEC_KEY = "Spez. und Test VOBES2025 (Thiesen)"

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


@dataclass
class TableRow:
    values: list[str]
    style: str = "body"


@dataclass
class TextSection:
    title: str | None = None
    lines: list[str] = field(default_factory=list)
    level: int = 2
    separator_before: bool = True
    sheet_name: str = "Übersicht"


@dataclass
class TableSection:
    title: str
    headers: list[str]
    rows: list[TableRow]
    align_right: set[int] = field(default_factory=set)
    intro_lines: list[str] = field(default_factory=list)
    level: int = 2
    separator_before: bool = True
    sheet_name: str = "Übersicht"
    body_row_height: float | None = None


@dataclass
class ReportDocument:
    title: str
    meta_lines: list[str]
    sections: list[TextSection | TableSection]
    max_columns: int


def _cell_has_text(value) -> bool:
    return value is not None and str(value).strip() != ""


def _copy_cell_display(src, dst, *, copy_value: bool = True) -> None:
    if copy_value:
        dst.value = src.value
    dst.font = copy(src.font)
    dst.fill = copy(src.fill)
    dst.border = copy(src.border)
    dst.alignment = copy(src.alignment)
    dst.number_format = src.number_format
    dst.protection = copy(src.protection)
    dst.comment = copy(src.comment) if src.comment else None


def _find_previous_xlsx(out_dir: str, current_file: str) -> str | None:
    current_name = os.path.basename(current_file)
    candidates: list[str] = []
    for name in os.listdir(out_dir):
        if name.startswith("~$"):
            continue
        if name == current_name or not name.endswith("_budget_massnahmenplan_ekek1.xlsx"):
            continue
        path = os.path.join(out_dir, name)
        if os.path.isfile(path):
            candidates.append(path)
    candidates.sort(key=os.path.getmtime, reverse=True)
    return candidates[0] if candidates else None


def _find_table_header_row(ws, first_header: str) -> int | None:
    needle = _strip_markdown(first_header)
    for row_idx in range(1, ws.max_row + 1):
        if _strip_markdown(str(ws.cell(row_idx, 1).value or "")) == needle:
            return row_idx
    return None


def _collect_table_key_rows(ws, first_header: str) -> tuple[int | None, dict[str, int]]:
    header_row = _find_table_header_row(ws, first_header)
    if header_row is None:
        return None, {}

    rows: dict[str, int] = {}
    for row_idx in range(header_row + 1, ws.max_row + 1):
        first_value = _strip_markdown(str(ws.cell(row_idx, 1).value or ""))
        if not first_value:
            if rows:
                break
            continue
        if rows and first_value in {"Firma", "Konzept", "Korrektur Überplanung", "Prämissen", "Gesamtübersicht", "Target - Ist - Vergleich"}:
            break
        nonempty = sum(1 for col_idx in range(1, ws.max_column + 1) if _cell_has_text(ws.cell(row_idx, col_idx).value))
        if rows and nonempty == 1 and first_value not in {"Summe", "Summe inkl. Audi", "Gesamt"}:
            break
        rows[first_value] = row_idx
    return header_row, rows


def _parse_correction_section(first_value: str) -> tuple[str, str] | None:
    text = _strip_markdown(first_value)
    match = re.match(r"^(?P<firm>.+?)\s+—\s+(?P<section>Stornierte Vorgänge|Quartals-Korrektur|Jahres-Korrektur)", text)
    if not match:
        return None
    section = match.group("section")
    kind = {
        "Stornierte Vorgänge": "storno",
        "Quartals-Korrektur": "quartal",
        "Jahres-Korrektur": "jahr",
    }[section]
    return match.group("firm").strip(), kind


def _collect_correction_rows(ws) -> dict[tuple[str, str, str], int]:
    rows: dict[tuple[str, str, str], int] = {}
    current_section: tuple[str, str] | None = None
    for row_idx in range(1, ws.max_row + 1):
        first_value = _strip_markdown(str(ws.cell(row_idx, 1).value or ""))
        if not first_value:
            continue
        parsed = _parse_correction_section(first_value)
        if parsed is not None:
            current_section = parsed
            continue
        if first_value == "Konzept":
            continue
        if current_section is None or not re.fullmatch(r"\d+", first_value):
            continue
        rows[(current_section[0], current_section[1], first_value)] = row_idx
    return rows


def _copy_note_cell(source_ws, target_ws, source_row: int, source_col: int, target_row: int, target_col: int) -> None:
    source_cell = source_ws.cell(source_row, source_col)
    if not _cell_has_text(source_cell.value):
        return
    target_cell = target_ws.cell(target_row, target_col)
    _copy_cell_display(source_cell, target_cell, copy_value=True)
    source_height = source_ws.row_dimensions[source_row].height
    if source_height is not None:
        target_ws.row_dimensions[target_row].height = source_height


def _inherit_notes_from_workbook(workbook: Workbook, source_xlsx: str | None) -> None:
    if not source_xlsx or not os.path.isfile(source_xlsx):
        return

    source_wb = load_workbook(source_xlsx)
    source_overview = source_wb["Übersicht"] if "Übersicht" in source_wb.sheetnames else None
    target_overview = workbook["Übersicht"] if "Übersicht" in workbook.sheetnames else None
    if source_overview and target_overview:
        source_f_width = source_overview.column_dimensions["F"].width
        if source_f_width is not None:
            target_overview.column_dimensions["F"].width = source_f_width
        source_area_header, source_area_rows = _collect_table_key_rows(source_overview, "Aufgabenbereich")
        target_area_header, target_area_rows = _collect_table_key_rows(target_overview, "Aufgabenbereich")
        for key, target_row in target_area_rows.items():
            source_row = source_area_rows.get(key)
            if source_row is not None:
                _copy_note_cell(source_overview, target_overview, source_row, 6, target_row, 6)

        source_firm_header, source_firm_rows = _collect_table_key_rows(source_overview, "Firma")
        target_firm_header, target_firm_rows = _collect_table_key_rows(target_overview, "Firma")
        if target_firm_header is not None:
            target_header_cell = target_overview.cell(target_firm_header, 13)
            if source_firm_header is not None and _cell_has_text(source_overview.cell(source_firm_header, 13).value):
                _copy_cell_display(source_overview.cell(source_firm_header, 13), target_header_cell, copy_value=True)
            else:
                template_header = target_overview.cell(target_firm_header, 12)
                _copy_cell_display(template_header, target_header_cell, copy_value=False)
                target_header_cell.value = "Notizen"
            source_width = source_overview.column_dimensions["M"].width
            target_overview.column_dimensions["M"].width = source_width if source_width is not None else 65
        for key, target_row in target_firm_rows.items():
            source_row = source_firm_rows.get(key)
            if source_row is not None:
                _copy_note_cell(source_overview, target_overview, source_row, 13, target_row, 13)

    source_correction = source_wb["Korrektur"] if "Korrektur" in source_wb.sheetnames else None
    target_correction = workbook["Korrektur"] if "Korrektur" in workbook.sheetnames else None
    if source_correction and target_correction:
        source_f_width = source_correction.column_dimensions["F"].width
        if source_f_width is not None:
            target_correction.column_dimensions["F"].width = source_f_width
        source_rows = _collect_correction_rows(source_correction)
        target_rows = _collect_correction_rows(target_correction)
        for key, target_row in target_rows.items():
            source_row = source_rows.get(key)
            if source_row is not None:
                _copy_note_cell(source_correction, target_correction, source_row, 6, target_row, 6)


def _heading(level: int, title: str) -> str:
    return f"{'#' * level} {title}"


def _strip_markdown(line: str) -> str:
    text = line.strip()
    if text == "---":
        return ""
    text = re.sub(r"^#{1,6}\s*", "", text)
    text = text.replace("**", "").replace("`", "")
    if text.startswith("_") and text.endswith("_") and len(text) > 1:
        text = text[1:-1]
    return text


def _markdown_heading_level(line: str) -> int | None:
    match = re.match(r"^(#{1,6})\s+.+$", line.strip())
    return len(match.group(1)) if match else None


def _markdown_table_cell(value: str, style: str) -> str:
    if not value:
        return value
    if style == "summary":
        return f"**{value}**"
    if style == "note":
        return f"_{value}_"
    return value


def _parse_te_number(value: str) -> int | None:
    text = _strip_markdown(str(value))
    match = re.fullmatch(r"([+-]?)(\d{1,3}(?:\.\d{3})*|\d+)\s*T€", text)
    if not match:
        return None
    sign, digits = match.groups()
    number = int(digits.replace(".", ""))
    return -number if sign == "-" else number


def _bplus_vorgang_url(value: str) -> str | None:
    text = _strip_markdown(str(value))
    return f"https://bplus-ng-mig.r02.vwgroup.com/ek/view?id={text}" if re.fullmatch(r"\d+", text) else None


def _exclude_from_budget(benennung: str) -> bool:
    return False


def _hide_from_firm_overview(company: str) -> bool:
    return "VOITAS" in company.upper()


def _reporting_company(area: str, company: str) -> str:
    upper = company.upper()
    if area == "RuleChecker (4soft, ex Voitas)" and "VOITAS" in upper:
        return "4SOFT GMBH MUENCHEN"
    return company


def _thiesen_manual_soll(company: str, targets: dict[str, int], start_q: dict[str, int], num_q: int) -> tuple[int, int] | None:
    if "THIESEN" not in company.upper():
        return None

    areas = [THIESEN_SUPPORT_KEY, THIESEN_SPEC_KEY]
    soll = 0
    soll_q = 0
    for area in areas:
        target_te = targets.get(area, 0)
        area_soll = target_te * 1000
        soll += area_soll
        sq = start_q.get(area, 1)
        if num_q < sq:
            a_q_ratio = 0.0
        else:
            a_q_ratio = (num_q - sq + 1) / (4 - sq + 1)
        soll_q += round(area_soll * a_q_ratio)
    return soll, soll_q


def _manual_company_soll(
    company: str,
    company_target_overrides: dict[str, dict[str, int | str]],
    num_q: int,
) -> tuple[str, int, int] | None:
    upper = company.upper()
    for company_key, config in company_target_overrides.items():
        if company_key not in upper:
            continue
        target_te = int(config["target_te"])
        start_q = int(config["start_q"])
        soll = target_te * 1000
        if num_q < start_q:
            q_ratio = 0.0
        else:
            q_ratio = (num_q - start_q + 1) / (4 - start_q + 1)
        soll_q = round(soll * q_ratio)
        return str(config["area"]), soll, soll_q
    return None


def _render_table_markdown(section: TableSection) -> list[str]:
    lines = [f"| {' | '.join(section.headers)} |"]
    separator = [
        "---:" if idx in section.align_right else "---"
        for idx in range(len(section.headers))
    ]
    lines.append(f"|{'|'.join(separator)}|")
    for row in section.rows:
        values = [_markdown_table_cell(value, row.style) for value in row.values]
        if (
            section.sheet_name == "Korrektur"
            and row.style == "body"
            and section.headers
            and section.headers[0] == "Konzept"
            and values
        ):
            url = _bplus_vorgang_url(values[0])
            if url:
                values[0] = f"[{_strip_markdown(values[0])}]({url})"
        lines.append(f"| {' | '.join(values)} |")
    return lines


def render_markdown(report: ReportDocument) -> str:
    lines: list[str] = [f"# {report.title}", ""]
    lines.extend(report.meta_lines)

    for section in report.sections:
        lines.append("")
        if section.separator_before:
            lines.extend(["---", ""])
        if isinstance(section, TextSection):
            if section.title:
                lines.extend([_heading(section.level, section.title), ""])
            lines.extend(section.lines)
        else:
            lines.extend([_heading(section.level, section.title), ""])
            lines.extend(section.intro_lines)
            if section.intro_lines:
                lines.append("")
            lines.extend(_render_table_markdown(section))
    lines.append("")
    return "\n".join(lines)


def write_csv_report(report: ReportDocument, csv_file: str) -> None:
    with open(csv_file, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([report.title])
        for line in report.meta_lines:
            writer.writerow([_strip_markdown(line)])

        for section in report.sections:
            writer.writerow([])
            if isinstance(section, TextSection):
                if section.title:
                    writer.writerow([section.title])
                for line in section.lines:
                    clean = _strip_markdown(line)
                    writer.writerow([clean] if clean else [])
            else:
                writer.writerow([section.title])
                for line in section.intro_lines:
                    clean = _strip_markdown(line)
                    writer.writerow([clean] if clean else [])
                writer.writerow(section.headers)
                for row in section.rows:
                    writer.writerow([_strip_markdown(value) for value in row.values])


def write_xlsx_report(report: ReportDocument, xlsx_file: str, inherit_notes_from: str | None = None) -> str:
    workbook = Workbook()
    overview_ws = workbook.active
    overview_ws.title = "Übersicht"
    correction_ws = workbook.create_sheet("Korrektur")

    max_cols = max(1, report.max_columns)

    thin = Side(style="thin", color="BFBFBF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    section_fill = PatternFill("solid", fgColor="EAF2F8")
    header_fill = PatternFill("solid", fgColor="D9E2F3")
    summary_fill = PatternFill("solid", fgColor="F3F3F3")
    status_fill_bestellt = PatternFill("solid", fgColor="63BE7B")
    status_fill_storniert = PatternFill("solid", fgColor="D9D9D9")
    status_fill_abgelehnt = PatternFill("solid", fgColor="FFC7CE")
    status_fill_erstellung = PatternFill("solid", fgColor="8EA9DB")
    status_fill_durchlauf = PatternFill("solid", fgColor="FFC000")
    wrap = Alignment(vertical="top", wrap_text=True)
    left = Alignment(horizontal="left", vertical="top", wrap_text=True)
    right = Alignment(horizontal="right", vertical="top", wrap_text=True)

    def render_sheet(
        ws,
        sections: list[TextSection | TableSection],
        *,
        include_title: bool,
        include_meta: bool,
        empty_message: str | None = None,
        first_col_width: int = 32,
        first_col_min: int = 14,
        first_col_max: int = 42,
        fixed_widths: dict[int, float] | None = None,
    ) -> None:
        current_row = 1
        col_widths = [12] * (max_cols + 1)
        col_widths[1] = first_col_width

        def estimate_lines(text: str, chars_per_line: int) -> int:
            clean = _strip_markdown(text)
            if not clean:
                return 1
            total = 0
            for part in clean.splitlines() or [""]:
                total += max(1, (len(part) + max(chars_per_line - 1, 1) - 1) // max(chars_per_line, 1))
            return max(total, 1)

        def set_row_height(row_idx: int, *, texts: list[str], chars_per_line: list[int], min_height: float = 15.0, line_height: float = 15.0) -> None:
            estimated = max(
                estimate_lines(text, chars)
                for text, chars in zip(texts, chars_per_line, strict=False)
            )
            ws.row_dimensions[row_idx].height = max(min_height, estimated * line_height)

        def merge_row(
            text: str,
            *,
            font: Font,
            fill: PatternFill | None = None,
            min_height: float | None = None,
            line_height: float | None = None,
        ) -> None:
            nonlocal current_row
            row_idx = current_row
            ws.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=max_cols)
            cell = ws.cell(current_row, 1, _strip_markdown(text))
            cell.font = font
            cell.alignment = wrap
            if fill is not None:
                cell.fill = fill
            set_row_height(
                row_idx,
                texts=[text],
                chars_per_line=[120],
                min_height=min_height or max(font.sz + 8 if font.sz else 18, 18),
                line_height=line_height or max((font.sz or 11) + 3, 15),
            )
            current_row += 1

        def update_width(col_idx: int, value: str) -> None:
            text = _strip_markdown(str(value))
            if col_idx == 1:
                width = min(max(len(text) + 2, first_col_min), first_col_max)
            else:
                width = min(max(len(text) + 2, 10), 32)
            col_widths[col_idx] = max(col_widths[col_idx], width)

        def effective_chars_per_line(col_idx: int) -> int:
            width = fixed_widths.get(col_idx, col_widths[col_idx]) if fixed_widths else col_widths[col_idx]
            return max(10, int(width) - 2)

        def status_fill_for(value: str) -> PatternFill | None:
            text = _strip_markdown(str(value)).upper()
            if not text:
                return None
            if "BESTELLT" in text:
                return status_fill_bestellt
            if "STORNIERT" in text:
                return status_fill_storniert
            if "ABGELEHNT" in text:
                return status_fill_abgelehnt
            if "ERSTELLUNG" in text:
                return status_fill_erstellung
            if (
                "IM DURCHLAUF" in text
                or
                "PLANEN-BM" in text
                or "FREIGABE KOSTENSTELLE" in text
                or "BEARBEITUNG BM-TEAM" in text
                or "IN DEN EINKAUF ÜBERTRAGEN" in text
            ):
                return status_fill_durchlauf
            return None

        def header_fill_for(value: str) -> PatternFill | None:
            return status_fill_for(value)

        if include_title:
            merge_row(report.title, font=Font(size=16, bold=True), min_height=30, line_height=18)
        if include_meta:
            for line in report.meta_lines:
                merge_row(line, font=Font(size=10, italic=True), min_height=20, line_height=15)
        if empty_message and not sections:
            merge_row(empty_message, font=Font(size=10, italic=True), min_height=20, line_height=15)

        for section in sections:
            if section.separator_before and current_row > 1:
                current_row += 1

            if isinstance(section, TextSection):
                if section.title:
                    merge_row(
                        section.title,
                        font=Font(size=13 if section.level == 2 else 11, bold=True),
                        fill=section_fill,
                        min_height=26 if section.level == 2 else 24,
                        line_height=16,
                    )
                for line in section.lines:
                    clean = _strip_markdown(line)
                    if clean:
                        heading_level = _markdown_heading_level(line)
                        if heading_level is not None:
                            merge_row(
                                clean,
                                font=Font(size=13 if heading_level <= 2 else 11, bold=True),
                                min_height=24 if heading_level <= 2 else 22,
                                line_height=16,
                            )
                        else:
                            merge_row(clean, font=Font(size=10), min_height=18, line_height=15)
                    else:
                        current_row += 1
                continue

            merge_row(
                section.title,
                font=Font(size=13 if section.level == 2 else 11, bold=True),
                fill=section_fill,
                min_height=26 if section.level == 2 else 24,
                line_height=16,
            )
            for line in section.intro_lines:
                clean = _strip_markdown(line)
                if clean:
                    merge_row(clean, font=Font(size=10), min_height=18, line_height=15)
                else:
                    current_row += 1

            for col_idx, header in enumerate(section.headers, start=1):
                cell = ws.cell(current_row, col_idx, header)
                cell.font = Font(bold=True)
                custom_header_fill = header_fill_for(header) if ws.title == "Übersicht" else None
                cell.fill = custom_header_fill or header_fill
                cell.border = border
                cell.alignment = left
                update_width(col_idx, header)
            set_row_height(
                current_row,
                texts=section.headers,
                chars_per_line=[effective_chars_per_line(idx) for idx in range(1, len(section.headers) + 1)],
                min_height=20,
                line_height=15,
            )
            current_row += 1

            for row in section.rows:
                row_idx = current_row
                for col_idx, value in enumerate(row.values, start=1):
                    te_number = _parse_te_number(value)
                    cell_value = te_number if te_number is not None else _strip_markdown(value)
                    cell = ws.cell(current_row, col_idx, cell_value)
                    cell.border = border
                    cell.alignment = right if (col_idx - 1) in section.align_right else left
                    if ws.title == "Korrektur" and row.style == "body" and col_idx == 1:
                        url = _bplus_vorgang_url(str(value))
                        if url:
                            cell.hyperlink = url
                            cell.font = Font(color="0563C1", underline="single")
                    if te_number is not None:
                        cell.number_format = '#,##0 "T€";[Red]-#,##0 "T€"'
                    if row.style == "summary":
                        cell.font = Font(bold=True)
                        cell.fill = summary_fill
                    elif row.style == "note":
                        cell.font = Font(italic=True)
                    elif ws.title == "Korrektur" and col_idx == 5:
                        fill = status_fill_for(str(cell_value))
                        if fill is not None:
                            cell.fill = fill
                    update_width(col_idx, value)
                set_row_height(
                    row_idx,
                    texts=row.values,
                    chars_per_line=[effective_chars_per_line(idx) for idx in range(1, len(row.values) + 1)],
                    min_height=section.body_row_height if section.body_row_height is not None else (18 if row.style == "summary" else 15),
                    line_height=0 if section.body_row_height is not None else 15,
                )
                current_row += 1

        ws.sheet_view.showGridLines = False
        ws.page_setup.orientation = "landscape"
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0

        for col_idx in range(1, max_cols + 1):
            letter = get_column_letter(col_idx)
            ws.column_dimensions[letter].width = fixed_widths.get(col_idx, col_widths[col_idx]) if fixed_widths else col_widths[col_idx]

    overview_sections = [section for section in report.sections if section.sheet_name == "Übersicht"]
    correction_sections = [section for section in report.sections if section.sheet_name == "Korrektur"]

    render_sheet(
        overview_ws,
        overview_sections,
        include_title=True,
        include_meta=True,
        first_col_width=34,
        first_col_min=18,
        first_col_max=44,
        fixed_widths={1: 44, 12: 65},
    )
    render_sheet(
        correction_ws,
        correction_sections,
        include_title=False,
        include_meta=False,
        empty_message="Keine Korrekturabschnitte vorhanden.",
        first_col_width=16,
        first_col_min=10,
        first_col_max=20,
        fixed_widths={3: 48},
    )

    _, target_firm_rows = _collect_table_key_rows(overview_ws, "Firma")
    target_firm_header = _find_table_header_row(overview_ws, "Firma")
    if target_firm_header is not None:
        notes_header = overview_ws.cell(target_firm_header, 13)
        if not _cell_has_text(notes_header.value):
            template_header = overview_ws.cell(target_firm_header, 12)
            _copy_cell_display(template_header, notes_header, copy_value=False)
            notes_header.value = "Notizen"
        overview_ws.column_dimensions["M"].width = max(overview_ws.column_dimensions["M"].width or 0, 65)
        for row_idx in target_firm_rows.values():
            note_cell = overview_ws.cell(row_idx, 13)
            if not note_cell.has_style:
                template_cell = overview_ws.cell(row_idx, 12)
                _copy_cell_display(template_cell, note_cell, copy_value=False)
                note_cell.value = None
                note_cell.font = copy(template_cell.font)
                note_cell.fill = copy(template_cell.fill)
                note_cell.border = copy(template_cell.border)
                note_cell.alignment = copy(template_cell.alignment)

    _inherit_notes_from_workbook(workbook, inherit_notes_from)
    workbook.save(xlsx_file)
    return xlsx_file


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=datetime.date.today().year)
    parser.add_argument("--inherit-notes-from")
    args = parser.parse_args()
    year = args.year

    # ── CSV + Prämissen laden ──────────────────────────────────────────
    REF_2025, TARGET_2026, AREA_ORDER, START_Q, COMPANY_TARGET_OVERRIDES = load_targets()
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
    sql = "SELECT concept, ea, title, planned_value, company, status, bm_text FROM btl"
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
    firm_bms: dict[str, list[dict]] = {}  # firm → [{concept, ea, title, value, status_label}, ...]
    # Für Soll-Berechnung: Firma→Area→Ist-Anteil
    firm_area_ist: dict[str, dict[str, int]] = {}

    for row in rows:
        pv = int(float(row.get("planned_value", "0")))
        company = row.get("company", "")
        ea = row.get("ea", "")
        title = row.get("title", "")
        status = row.get("status", "")
        bm_text = row.get("bm_text", "")
        benennung = status_map.get(status, "")
        if _exclude_from_budget(benennung):
            continue
        area = classify_bm(company, title, bm_text)
        reporting_company = _reporting_company(area, company)
        area_values[area] = area_values.get(area, 0) + pv

        # Firmen-Aggregation
        if reporting_company not in firm_values:
            firm_values[reporting_company] = {"sum": 0, "count": 0, "bestellt": 0, "durchlauf": 0, "konzept": 0, "storniert": 0}
        firm_values[reporting_company]["sum"] += pv
        firm_values[reporting_company]["count"] += 1
        if benennung == "bestellt":
            firm_values[reporting_company]["bestellt"] += pv
        elif benennung == "im Durchlauf":
            firm_values[reporting_company]["durchlauf"] += pv
        elif benennung == "Konzept":
            firm_values[reporting_company]["konzept"] += pv
        elif benennung == "storniert":
            firm_values[reporting_company]["storniert"] += pv

        # BM-Einzeldaten für Korrektur-Abschnitt sammeln
        if benennung in ("Konzept", "im Durchlauf", "bestellt", "storniert"):
            if reporting_company not in firm_bms:
                firm_bms[reporting_company] = []
            firm_bms[reporting_company].append({
                "concept": row.get("concept", ""),
                "ea": ea,
                "title": title,
                "value": pv,
                "status_label": benennung,
                "status_raw": status,
                "source_company": company,
            })

        # Firma→Area Zuordnung für Soll-Verteilung
        if area != "_SONSTIGE":
            if reporting_company not in firm_area_ist:
                firm_area_ist[reporting_company] = {}
            firm_area_ist[reporting_company][area] = firm_area_ist[reporting_company].get(area, 0) + pv

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

    # AUDI-Target dem Systemschaltpläne-Target zuschlagen (AUDI-Ist steckt in EDAG-BMs)
    soll_targets: dict[str, int] = {a: v for a, v in TARGET_2026.items()}
    if AUDI_FIXED and AUDI_KEY in soll_targets:
        soll_targets[sysschalt_key] = soll_targets.get(sysschalt_key, 0) + AUDI_FIXED
        soll_targets.pop(AUDI_KEY, None)

    manual_company_soll: dict[str, tuple[str, int, int]] = {}
    override_target_by_area: dict[str, int] = {}
    area_totals_remaining: dict[str, int] = {}
    for firm, areas in firm_area_ist.items():
        manual_override = _manual_company_soll(firm, COMPANY_TARGET_OVERRIDES, num_q)
        if manual_override is not None:
            area_name, firm_soll_abs, firm_soll_q_abs = manual_override
            manual_company_soll[firm] = manual_override
            override_target_by_area[area_name] = override_target_by_area.get(area_name, 0) + firm_soll_abs
            continue
        for area, val in areas.items():
            area_totals_remaining[area] = area_totals_remaining.get(area, 0) + val

    firm_soll: dict[str, int] = {}
    firm_soll_q: dict[str, int] = {}
    for firm, areas in firm_area_ist.items():
        manual_override = manual_company_soll.get(firm)
        if manual_override is not None:
            _, firm_soll[firm], firm_soll_q[firm] = manual_override
            continue

        thiesen_override = _thiesen_manual_soll(firm, soll_targets, START_Q, num_q)
        if thiesen_override is not None:
            firm_soll[firm], firm_soll_q[firm] = thiesen_override
            continue

        soll = 0
        soll_q = 0
        for area, val in areas.items():
            total = area_totals_remaining.get(area, area_totals.get(area, 1))
            target = soll_targets.get(area, 0) * 1000 - override_target_by_area.get(area, 0)
            target = max(target, 0)
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

    report_title = f"EKEK/1 Budget {year} — Target / Ist-Analyse"
    meta_lines = [
        f"**Stand BPLUS-NG:** {sync_time} | **Erstellt:** {datetime.date.today().strftime('%d.%m.%Y')}"
    ]
    sections: list[TextSection | TableSection] = []

    # ── Gesamtübersicht (oben) ────────────────────────────────────────
    sum_25 = sum_t = sum_i = 0
    for area in AREA_ORDER:
        sum_25 += REF_2025[area]
        sum_t += TARGET_2026[area]
        sum_i += area_te.get(area, 0)

    sections.append(
        TableSection(
            title="Gesamtübersicht",
            headers=["", "Wert"],
            rows=[
                TableRow(["IST 2025 (Referenz)", fmt(sum_25)]),
                TableRow(["Ist (BPLUS)", fmt(sum_i)]),
                TableRow(["Target", fmt(sum_t)]),
                TableRow(["Delta Ist vs. Target", delta_fmt(sum_i - sum_t)]),
            ],
            align_right={1},
            separator_before=False,
        )
    )

    # ── Tabelle 1: Target - Ist - Vergleich ───────────────────────────
    area_rows: list[TableRow] = []
    s25 = s_t = s_i = 0
    for area in AREA_ORDER:
        if area == AUDI_KEY:
            continue
        v25 = REF_2025[area]
        vt = TARGET_2026[area]
        vi = area_te.get(area, 0)
        delta = vi - vt
        area_rows.append(TableRow([area, fmt(v25), fmt(vt), fmt(vi), delta_fmt(delta), ""]))
        s25 += v25
        s_t += vt
        s_i += vi

    area_rows.append(TableRow(["Summe", fmt(s25), fmt(s_t), fmt(s_i), delta_fmt(s_i - s_t), ""], style="summary"))

    v25_a = REF_2025[AUDI_KEY]
    vt_a = TARGET_2026[AUDI_KEY]
    vi_a = area_te.get(AUDI_KEY, 0)
    area_rows.append(TableRow([AUDI_KEY, fmt(v25_a), fmt(vt_a), fmt(vi_a), delta_fmt(vi_a - vt_a), ""]))
    s25 += v25_a
    s_t += vt_a
    s_i += vi_a
    area_rows.append(
        TableRow(
            ["Summe inkl. Audi", fmt(s25), fmt(s_t), fmt(s_i), delta_fmt(s_i - s_t), ""],
            style="summary",
        )
    )
    sections.append(
        TableSection(
            title="Target - Ist - Vergleich",
            headers=["Aufgabenbereich", "2025", "Target", "Ist", "Delta", "Maßnahmen"],
            rows=area_rows,
            align_right={1, 2, 3, 4},
            body_row_height=15,
        )
    )

    # ── Tabelle 2: Firmen ─────────────────────────────────────────────
    firm_rows: list[TableRow] = []
    firm_total = 0
    firm_total_soll = 0
    firm_total_bestellt = 0
    firm_total_durchlauf = 0
    firm_total_konzept = 0
    firm_total_storniert = 0
    firm_count_total = 0
    for firm, data in sorted(firm_values.items(), key=lambda x: -x[1]["sum"]):
        if _hide_from_firm_overview(firm):
            continue

        ist = round(data["sum"] / 1000)
        soll = round(firm_soll.get(firm, 0) / 1000)
        bestellt = round(data["bestellt"] / 1000)
        durchlauf = round(data["durchlauf"] / 1000)
        konzept = round(data["konzept"] / 1000)
        storniert = round(data["storniert"] / 1000)
        soll_q = round(firm_soll_q.get(firm, 0) / 1000)
        diff_planung = ist - soll
        diff_q = soll_q - (durchlauf + bestellt)
        firm_short = firm.split()[0] if firm.strip() else firm

        massnahmen_parts: list[str] = []
        if diff_q < 0:
            massnahmen_parts.append(f"Quartal überplant: {fmt(abs(diff_q))} zurückholen")
        elif diff_q > 0:
            massnahmen_parts.append(f"Quartalswert zu gering: {fmt(diff_q)} beauftragen")
        if diff_planung > 0:
            if storniert > 0:
                massnahmen_parts.append(f"Stornierte Positionen zuerst löschen: {fmt(min(diff_planung, storniert))}")
            massnahmen_parts.append(f"Jahr überplant: {fmt(diff_planung)} streichen")
        elif diff_planung < 0:
            massnahmen_parts.append(f"Jahreswert zu gering: {fmt(abs(diff_planung))} einplanen")
        massnahmen = "; ".join(massnahmen_parts)

        firm_rows.append(
            TableRow(
                [
                    firm_short,
                    str(data["count"]),
                    fmt(soll),
                    fmt(ist),
                    delta_fmt(diff_planung),
                    fmt(soll_q),
                    fmt(bestellt),
                    fmt(durchlauf),
                    fmt(konzept),
                    fmt(storniert),
                    delta_fmt(diff_q),
                    massnahmen,
                ]
            )
        )
        firm_total += ist
        firm_total_soll += soll
        firm_total_bestellt += bestellt
        firm_total_durchlauf += durchlauf
        firm_total_konzept += konzept
        firm_total_storniert += storniert
        firm_count_total += data["count"]

    firm_total_soll_q = sum(
        round(firm_soll_q.get(f, 0) / 1000)
        for f in firm_values
        if not _hide_from_firm_overview(f)
    )
    firm_total_diff_q = firm_total_soll_q - (firm_total_durchlauf + firm_total_bestellt)
    firm_total_diff_planung = firm_total - firm_total_soll
    firm_rows.append(
        TableRow(
            [
                "Gesamt",
                str(firm_count_total),
                fmt(firm_total_soll),
                fmt(firm_total),
                delta_fmt(firm_total_diff_planung),
                fmt(firm_total_soll_q),
                fmt(firm_total_bestellt),
                fmt(firm_total_durchlauf),
                fmt(firm_total_konzept),
                fmt(firm_total_storniert),
                delta_fmt(firm_total_diff_q),
                "",
            ],
            style="summary",
        )
    )
    sections.append(
        TableSection(
            title="Firmen-Übersicht",
            headers=[
                "Firma",
                "BMs",
                "Soll",
                "Ist",
                "DIFF Ges.",
                f"Soll {q_label}",
                "bestellt",
                "im Durchlauf",
                "01 Erstellung",
                "storniert",
                f"DIFF {q_label}",
                "Maßnahmen",
            ],
            rows=firm_rows,
            align_right={1, 2, 3, 4, 5, 6, 7, 8, 9, 10},
            body_row_height=15,
        )
    )

    # ── Tabelle 3: Korrektur Überplanung ──────────────────────────────
    korrektur_firmen: list[dict] = []
    for firm, data in sorted(firm_values.items(), key=lambda x: -x[1]["sum"]):
        ist = round(data["sum"] / 1000)
        soll = round(firm_soll.get(firm, 0) / 1000)
        bestellt_te = round(data["bestellt"] / 1000)
        durchlauf_te = round(data["durchlauf"] / 1000)
        soll_q_te = round(firm_soll_q.get(firm, 0) / 1000)
        diff_jahr = ist - soll
        diff_q = soll_q_te - (durchlauf_te + bestellt_te)
        if diff_jahr > 0 or diff_q < 0:
            korrektur_firmen.append({"firm": firm, "diff_jahr": diff_jahr, "diff_q": diff_q})

    if korrektur_firmen:
        sections.append(
            TextSection(
                title="Korrektur Überplanung",
                lines=[
                    "Überplante Lieferanten mit einzelnen Vorgängen zum Rückzug oder zur Reduzierung.",
                    "Stornierte Vorgänge werden pro Firma zuerst aufgeführt und in der **Aktion-Spalte** mit _löschen_ vorbelegt.",
                    "Alle übrigen Einträge in der **Aktion-Spalte** manuell befüllen (z.B. _zurückziehen_, _reduzieren auf X T€_, _verschieben Q3_).",
                ],
                sheet_name="Korrektur",
            )
        )

        korrektur_firmen.sort(key=lambda x: -(x["diff_jahr"] + abs(min(x["diff_q"], 0))))
        korrektur_headers = ["Konzept", "EA", "BM-Titel", "Wert", "Status", "Aktion"]

        for kf in korrektur_firmen:
            firm = kf["firm"]
            firm_short = firm.split()[0] if firm.strip() else firm
            bms = firm_bms.get(firm, [])
            diff_jahr = kf["diff_jahr"]
            diff_q = kf["diff_q"]
            storno_bms = sorted([b for b in bms if b["status_label"] == "storniert"], key=lambda x: -x["value"])

            if storno_bms:
                rows_storno: list[TableRow] = []
                sum_storno = 0
                for b in storno_bms:
                    v = round(b["value"] / 1000)
                    rows_storno.append(TableRow([b["concept"], b["ea"], b["title"], fmt(v), b["status_raw"], "löschen"]))
                    sum_storno += v
                rows_storno.append(TableRow(["", "", "Summe storniert", fmt(sum_storno), "", ""], style="summary"))

                sections.append(
                    TableSection(
                        title=f"{firm_short} — Stornierte Vorgänge: löschen",
                        headers=korrektur_headers,
                        rows=rows_storno,
                        align_right={3},
                        level=3,
                        separator_before=False,
                        sheet_name="Korrektur",
                        body_row_height=15,
                    )
                )

            if diff_q < 0:
                reduce_q = abs(diff_q)
                rows_q: list[TableRow] = []
                prio1 = sorted([b for b in bms if b["status_label"] == "im Durchlauf"], key=lambda x: -x["value"])
                sum_p1 = 0
                for b in prio1:
                    v = round(b["value"] / 1000)
                    rows_q.append(TableRow([b["concept"], b["ea"], b["title"], fmt(v), b["status_raw"], ""]))
                    sum_p1 += v
                if prio1:
                    rows_q.append(TableRow(["", "", "Summe im Durchlauf", fmt(sum_p1), "", ""], style="summary"))

                if sum_p1 < reduce_q:
                    prio2 = sorted([b for b in bms if b["status_label"] == "bestellt"], key=lambda x: -x["value"])
                    sum_p2 = 0
                    for b in prio2:
                        v = round(b["value"] / 1000)
                        rows_q.append(TableRow([b["concept"], b["ea"], b["title"], fmt(v), b["status_raw"], ""]))
                        sum_p2 += v
                    if prio2:
                        rows_q.append(TableRow(["", "", "Summe bestellt", fmt(sum_p2), "", ""], style="summary"))

                if not prio1 and not [b for b in bms if b["status_label"] == "bestellt"]:
                    rows_q.append(TableRow(["", "", "Keine rückziehbaren Vorgänge vorhanden", "", "", ""], style="note"))

                sections.append(
                    TableSection(
                        title=f"{firm_short} — Quartals-Korrektur ({q_label}): {fmt(reduce_q)} zu reduzieren",
                        headers=korrektur_headers,
                        rows=rows_q,
                        align_right={3},
                        level=3,
                        separator_before=False,
                        sheet_name="Korrektur",
                        body_row_height=15,
                    )
                )

            if diff_jahr > 0:
                rows_jahr: list[TableRow] = []
                prio1 = sorted([b for b in bms if b["status_label"] == "Konzept"], key=lambda x: -x["value"])
                sum_p1 = 0
                for b in prio1:
                    v = round(b["value"] / 1000)
                    rows_jahr.append(TableRow([b["concept"], b["ea"], b["title"], fmt(v), b["status_raw"], ""]))
                    sum_p1 += v
                if prio1:
                    rows_jahr.append(TableRow(["", "", "Summe 01 Erstellung", fmt(sum_p1), "", ""], style="summary"))

                if sum_p1 < diff_jahr:
                    prio2 = sorted([b for b in bms if b["status_label"] == "im Durchlauf"], key=lambda x: -x["value"])
                    sum_p2 = 0
                    for b in prio2:
                        v = round(b["value"] / 1000)
                        rows_jahr.append(TableRow([b["concept"], b["ea"], b["title"], fmt(v), b["status_raw"], ""]))
                        sum_p2 += v
                    if prio2:
                        rows_jahr.append(TableRow(["", "", "Summe im Durchlauf", fmt(sum_p2), "", ""], style="summary"))

                if not prio1 and not [b for b in bms if b["status_label"] == "im Durchlauf"]:
                    rows_jahr.append(TableRow(["", "", "Keine rückziehbaren Vorgänge vorhanden", "", "", ""], style="note"))

                sections.append(
                    TableSection(
                        title=f"{firm_short} — Jahres-Korrektur: {fmt(diff_jahr)} zu reduzieren",
                        headers=korrektur_headers,
                        rows=rows_jahr,
                        align_right={3},
                        level=3,
                        separator_before=False,
                        sheet_name="Korrektur",
                        body_row_height=15,
                    )
                )

    sections.append(
        TextSection(
            lines=praemissen_text.splitlines() + [f"- 2026-Ist: BPLUS-NG Sync vom {sync_time}"],
        )
    )

    max_columns = 1
    for section in sections:
        if isinstance(section, TableSection):
            max_columns = max(max_columns, len(section.headers), *(len(row.values) for row in section.rows or [TableRow([""])]))

    report = ReportDocument(
        title=report_title,
        meta_lines=meta_lines,
        sections=sections,
        max_columns=max_columns,
    )

    md_text = render_markdown(report)

    # ── Datei schreiben ───────────────────────────────────────────────
    os.makedirs(OUT_DIR, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = os.path.join(OUT_DIR, f"{ts}_budget_massnahmenplan_ekek1.md")
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(md_text + "\n")

    csv_file = os.path.join(OUT_DIR, f"{ts}_budget_massnahmenplan_ekek1.csv")
    write_csv_report(report, csv_file)

    xlsx_file = os.path.join(OUT_DIR, f"{ts}_budget_massnahmenplan_ekek1.xlsx")
    inherit_notes_from = args.inherit_notes_from or _find_previous_xlsx(OUT_DIR, xlsx_file)
    write_xlsx_report(report, xlsx_file, inherit_notes_from=inherit_notes_from)

    pdf_file = write_pdf_beside_markdown(out_file)

    rel = os.path.relpath(out_file, REPO_ROOT)
    rel_csv = os.path.relpath(csv_file, REPO_ROOT)
    rel_xlsx = os.path.relpath(xlsx_file, REPO_ROOT)
    print(rel)
    print(rel_csv)
    print(rel_xlsx)
    if pdf_file:
        rel_pdf = os.path.relpath(pdf_file, REPO_ROOT)
        print(rel_pdf)


if __name__ == "__main__":
    main()
