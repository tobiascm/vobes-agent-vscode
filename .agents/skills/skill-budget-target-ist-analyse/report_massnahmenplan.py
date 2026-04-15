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
import sqlite3
import subprocess
import sys
from collections import defaultdict
from copy import copy
from dataclasses import dataclass, field
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
BUDGET_DB = os.path.join(REPO_ROOT, "scripts", "budget", "budget_db.py")
DB_PATH = os.path.join(REPO_ROOT, "userdata", "budget.db")
OUT_DIR = os.path.join(REPO_ROOT, "userdata", "budget")
VORGABEN_DIR = os.path.join(OUT_DIR, "vorgaben")
TARGET_CSV = os.path.join(VORGABEN_DIR, "target.csv")
STATUS_CSV = os.path.join(SCRIPT_DIR, "status_mapping.csv")
PRAEMISSEN_MD = os.path.join(VORGABEN_DIR, "praemissen.md")
TARGET_IMAGE = os.path.join(VORGABEN_DIR, "target.png")
SPECIAL_RULES_XLSX = os.path.join(REPO_ROOT, "userdata", "budget", "planning", "budget_sondervereinbarungen_ekek1.xlsx")
PLANNING_SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts", "budget")
if PLANNING_SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, PLANNING_SCRIPTS_DIR)

try:
    from beauftragungsplanung_core import (  # noqa: E402
        COMPANY_ALIAS_FALLBACKS,
        _detect_special_cadence,
        _extract_allowed_company_tokens,
        _extract_priority_tokens,
        _quarter_for_date,
        _resolve_company_tokens,
    )
except ImportError:  # pragma: no cover - fallback for missing planning core in local workspace
    COMPANY_ALIAS_FALLBACKS = {
        "4SOFT": "4SOFT GMBH MUENCHEN",
        "THIESEN": "THIESEN HARDWARE SOFTW. GMBH WARTENBERG",
        "FES": "FES GMBH ZWICKAU/00",
        "SUMITOMO": "SUMITOMO ELECTRIC BORDNETZE SE WOLFSBURG",
        "BERTRANDT": "BERTRANDT INGENIEURBUERO GMBH TAPPENBECK",
        "EDAG": "EDAG ENGINEERING GMBH WOLFSBURG",
        "VOLKSWAGEN": "VOLKSWAGEN GROUP SERVICES GMBH WOLFSBURG",
    }

    def _detect_special_cadence(display_name: str, remark: str, notes: str) -> str:
        blob = " ".join(part for part in [display_name, remark, notes] if part).lower()
        if "nur el" in blob or "keine fl" in blob:
            return "fl_forbidden"
        if "pro halbjahr" in blob:
            return "semiannual_tranche_exact"
        if "pro quartal" in blob:
            return "quarterly_tranche_exact"
        if "quartalsweise" in blob:
            return "quarterly_split_annual"
        return "annual_exact"

    def _extract_allowed_company_tokens(notes: str) -> list[str]:
        def _clean(value: str) -> str:
            return re.sub(r"\s+in genau dieser priorität\.?$", "", value.strip(), flags=re.IGNORECASE)
        match = re.search(r"nur für\s+([^\n.!]+)", notes, re.IGNORECASE)
        if match:
            return [_clean(token) for token in re.split(r"[,/]| und ", match.group(1)) if _clean(token)]
        match = re.search(r"folgende firmen .*?buchen:\s*([^\n.!]+)", notes, re.IGNORECASE)
        if match:
            return [_clean(token) for token in re.split(r",| und ", match.group(1)) if _clean(token)]
        return []

    def _extract_priority_tokens(notes: str) -> list[str]:
        match = re.search(r"folgende firmen .*?buchen:\s*([^\n.!]+)", notes, re.IGNORECASE)
        if not match:
            return []
        return [re.sub(r"\s+in genau dieser priorität\.?$", "", token.strip(), flags=re.IGNORECASE) for token in re.split(r",| und ", match.group(1)) if re.sub(r"\s+in genau dieser priorität\.?$", "", token.strip(), flags=re.IGNORECASE)]

    def _resolve_company_tokens(tokens: list[str], known_companies: list[str]) -> tuple[list[str], list[str]]:
        resolved: list[str] = []
        unresolved: list[str] = []
        for token in tokens:
            upper = token.upper()
            chosen = None
            if upper in COMPANY_ALIAS_FALLBACKS:
                fallback = COMPANY_ALIAS_FALLBACKS[upper]
                if fallback in known_companies:
                    chosen = fallback
            if chosen is None:
                for company in known_companies:
                    if upper in company.upper():
                        chosen = company
                        break
            if chosen is None:
                unresolved.append(token)
                continue
            if chosen not in resolved:
                resolved.append(chosen)
        return resolved, unresolved

    def _quarter_for_date(target_date: str | None, *, title: str = "", bm_text: str = "") -> str | None:
        text = str(target_date or "").strip()
        match = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
        if not match:
            return None
        month = int(match.group(2))
        if month <= 3:
            return "Q1"
        if month <= 6:
            return "Q2"
        if month <= 9:
            return "Q3"
        return "Q4"

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


def load_targets() -> tuple[
    dict[str, int],
    dict[str, int],
    list[str],
    dict[str, int],
    dict[str, dict[str, int | str]],
    dict[str, Any] | None,
]:
    """Liest target.csv inkl. optionaler Quartalsaufteilung."""
    ref_2025: dict[str, int] = {}
    target_2026: dict[str, int] = {}
    start_q: dict[str, int] = {}
    area_order: list[str] = []
    company_target_overrides: dict[str, dict[str, int | str]] = {}
    quarter_split: dict[str, Any] | None = None
    with open(TARGET_CSV, encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=";")
        headers: list[str] = []
        mode: str | None = None
        for raw_row in reader:
            row = [cell.strip() for cell in raw_row]
            if not any(row):
                continue
            first = row[0]
            if first == "Aufgabenbereich":
                headers = row
                mode = "areas"
                continue
            if first == "Jahr/Quartal":
                headers = row
                mode = "quarters"
                continue
            if not headers or mode is None:
                continue

            record = {
                headers[idx]: row[idx].strip() if idx < len(row) else ""
                for idx in range(len(headers))
            }
            if mode == "areas":
                area = record["Aufgabenbereich"].strip()
                ref_2025[area] = int(record["2025"].strip())
                target_2026[area] = int(record["Target_2026"].strip())
                start_q[area] = int(record.get("Start_Q", "1").strip() or "1")
                area_order.append(area)
                for col_name, raw_value in record.items():
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
                continue

            if mode == "quarters" and first == "Summe":
                year_header = next((header for header in headers if re.fullmatch(r"\d{4}", header)), None)
                annual_te = _parse_te_value(record.get(year_header or ""))
                quarter_values = {quarter: _parse_te_value(record.get(quarter, "")) for quarter in QUARTERS}
                if year_header is None or annual_te is None or any(value is None for value in quarter_values.values()):
                    raise ValueError(f"Ungültige Quartalsaufteilung in {TARGET_CSV}.")
                quarter_sum_te = sum(float(quarter_values[quarter]) for quarter in QUARTERS)
                if abs(float(annual_te) - quarter_sum_te) > 1e-6:
                    raise ValueError(
                        f"Quartalsaufteilung in {TARGET_CSV} ist inkonsistent: Jahr {annual_te} T€ != Summe Quartale {quarter_sum_te} T€."
                    )
                quarter_split = {
                    "year": int(year_header),
                    "annual_te": float(annual_te),
                    "quarters_te": {quarter: float(quarter_values[quarter]) for quarter in QUARTERS},
                }
    return ref_2025, target_2026, area_order, start_q, company_target_overrides, quarter_split

# ── Prämissen laden ───────────────────────────────────────────────────

def load_praemissen() -> str:
    """Liest praemissen.md als String."""
    with open(PRAEMISSEN_MD, encoding="utf-8") as f:
        return f.read().strip()


MONTH_COLUMNS = (
    "pct_jan",
    "pct_feb",
    "pct_mar",
    "pct_apr",
    "pct_may",
    "pct_jun",
    "pct_jul",
    "pct_aug",
    "pct_sep",
    "pct_oct",
    "pct_nov",
    "pct_dec",
)
QUARTERS = ("Q1", "Q2", "Q3", "Q4")
SPECIAL_STATUS_HEADERS = {"EL DIFF", "IO/nIO"}


def _normalize_ea_key(value: Any) -> str:
    digits = re.sub(r"[^0-9]", "", str(value or ""))
    if not digits:
        return ""
    return digits.lstrip("0") or "0"


def _parse_number_text(text: str) -> float | None:
    cleaned = text.strip()
    if not cleaned:
        return None
    if re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+(?:,\d+)?", cleaned):
        return float(cleaned.replace(".", "").replace(",", "."))
    if re.fullmatch(r"-?\d+(?:,\d+)?", cleaned):
        return float(cleaned.replace(",", "."))
    if re.fullmatch(r"-?\d+\.\d+", cleaned):
        return float(cleaned)
    return None


def _parse_te_value(raw: Any) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip()
    if not text or text in {"-", "–"}:
        return None
    text = text.replace("T€", "").replace("€", "").replace(" ", "")
    if text.startswith("="):
        parts = [part for part in text[1:].split("+") if part]
        if parts:
            values = [_parse_te_value(part) for part in parts]
            if any(value is None for value in values):
                return None
            return sum(value for value in values if value is not None)
    return _parse_number_text(text)


def _parse_hour_value(raw: Any) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if not text or text in {"-", "–"}:
        return None
    text = text.removesuffix("h").replace(" ", "")
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", text):
        return float(text.replace(".", ""))
    return _parse_number_text(text)


def _parse_el_target(raw: Any) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text or text in {"-", "–"}:
        return {"mode": "none", "value": None, "display": "-"}
    if text.lower().endswith("h"):
        hours = _parse_hour_value(text)
        if hours is None:
            return {"mode": "manual", "value": None, "display": text}
        return {"mode": "hours", "value": hours, "display": text}
    te_value = _parse_te_value(raw)
    if te_value is None:
        return {"mode": "manual", "value": None, "display": text}
    if te_value >= 1000 and "€" not in text.upper():
        return {"mode": "manual", "value": None, "display": text}
    return {"mode": "te", "value": te_value, "display": text}


def load_special_rule_rows(path: str, known_companies: list[str]) -> list[dict[str, Any]]:
    if not os.path.isfile(path):
        return []

    workbook = load_workbook(path, data_only=True)
    ws = workbook.active
    required = {"Thema", "EA", "EL", "FL", "Bemerkung", "Hinweise für autom. Auslegung"}
    header_row = None
    header_map: dict[str, int] = {}

    for row_idx in range(1, ws.max_row + 1):
        values = {
            str(ws.cell(row_idx, col_idx).value).strip(): col_idx
            for col_idx in range(1, ws.max_column + 1)
            if ws.cell(row_idx, col_idx).value is not None
        }
        if required.issubset(values):
            header_row = row_idx
            header_map = values
            break

    if header_row is None:
        return []

    rules: list[dict[str, Any]] = []
    for row_idx in range(header_row + 1, ws.max_row + 1):
        topic = str(ws.cell(row_idx, header_map["Thema"]).value or "").strip()
        if not topic:
            continue
        raw_ea = ws.cell(row_idx, header_map["EA"]).value
        raw_ea_text = str(raw_ea or "").strip()
        ea_keys = [
            key
            for key in (_normalize_ea_key(part) for part in re.split(r"[\n,;]+", raw_ea_text))
            if key
        ]
        remark = str(ws.cell(row_idx, header_map["Bemerkung"]).value or "").strip()
        notes = str(ws.cell(row_idx, header_map["Hinweise für autom. Auslegung"]).value or "").strip()
        cadence_type = _detect_special_cadence(topic, remark, notes)
        allowed_companies, _ = _resolve_company_tokens(_extract_allowed_company_tokens(notes), known_companies)
        priority_companies, _ = _resolve_company_tokens(_extract_priority_tokens(notes), known_companies)
        rules.append(
            {
                "topic": topic,
                "ea_display": ", ".join(
                    part.strip() for part in re.split(r"[\n,;]+", raw_ea_text) if part.strip()
                ) or raw_ea_text,
                "ea_keys": ea_keys,
                "fl_target_te": _parse_te_value(ws.cell(row_idx, header_map["FL"]).value),
                "el_target": _parse_el_target(ws.cell(row_idx, header_map["EL"]).value),
                "remark": remark,
                "notes": notes,
                "cadence_type": cadence_type,
                "allowed_companies": allowed_companies,
                "priority_companies": priority_companies,
            }
        )
    return rules


def _annual_target_for_cadence(base_target: float | None, cadence_type: str) -> float | None:
    if base_target is None:
        return None
    return base_target


def _period_target_for_cadence(base_target: float | None, cadence_type: str, num_q: int) -> float | None:
    annual_target = _annual_target_for_cadence(base_target, cadence_type)
    if annual_target is None:
        return None
    if cadence_type == "quarterly_tranche_exact":
        return base_target if base_target is not None and num_q >= 1 else 0.0
    if cadence_type == "semiannual_tranche_exact":
        if num_q < 2:
            return 0.0
        return base_target
    return annual_target * num_q / 4


def _values_match(actual: float, target: float, *, tolerance: float = 0.1) -> bool:
    return abs(actual - target) <= tolerance


def _status_text(value: bool | None) -> str:
    if value is None:
        return "-"
    return "OK" if value else "X"


def _io_text(value: bool | None) -> str:
    if value is None:
        return "-"
    return "IO" if value else "nIO"


def _diff_band_status(actual: float, target: float | None, *, warn_ratio: float = 0.10, ok_ratio: float = 0.01) -> str:
    if target is None:
        return "-"
    if abs(target) <= 0.1:
        return "OK" if abs(actual - target) <= 0.1 else "X"
    ratio = abs(actual - target) / abs(target)
    if ratio < ok_ratio:
        return "OK"
    if ratio <= warn_ratio:
        return "WARN"
    return "X"


_BAND_SEVERITY = {"-": 0, "OK": 1, "WARN": 2, "X": 3}


def _worst_band(*bands: str) -> str:
    applicable = [b for b in bands if b != "-"]
    if not applicable:
        return "-"
    return max(applicable, key=lambda b: _BAND_SEVERITY.get(b, 0))


def _band_to_io(band: str) -> str:
    if band == "-":
        return "-"
    return "IO" if band == "OK" else "nIO"


def _evaluate_hint_status(hint: str, ctx: dict) -> str:
    h = hint.lower()

    # Rule 1: "EL und FL müssen exakt passen!"
    if "el und fl müssen exakt passen" in h or "el und fl müssen exakt passen" in h.replace("ü", "ue"):
        return _band_to_io(ctx["year_band"])

    # Rule 2: "FL muss exakt passen!" (without "el und fl")
    if "fl muss exakt passen" in h or "fl muss exakt passen" in h.replace("ü", "ue"):
        return _band_to_io(ctx["year_band"])

    # Rule 3: "EL und FL dürfen nur Quartalsweise beauftragen..."
    if "quartalsweise" in h and "beauftrag" in h:
        worst = _worst_band(ctx["quarter_band"], ctx["el_period_band"])
        return _band_to_io(worst)

    # Rule 4a: "Werte für 1. HJ müssen auch wirklich im 1.HJ beauftragt werden"
    # Entire annual budget must be ordered in Q1-2 → compare period actual vs annual target
    if "1. hj" in h and "beauftragt" in h:
        band = _diff_band_status(ctx["fl_period_te"], ctx.get("fl_target_annual"))
        return _band_to_io(band)

    # Rule 4b: "EL und FL müssen hier pro Halbjahr beauftragt werden"
    if "halbjahr" in h and "beauftragt" in h:
        return _band_to_io(ctx["quarter_band"])

    # Rule 5: "EL kann niedriger sein, darf aber auf keinen Fall höher sein."
    if "kann niedriger" in h:
        el_target = ctx.get("el_annual_target")
        el_actual = ctx.get("el_actual_annual", 0.0)
        if el_target is None or el_target == 0:
            return "-"
        if el_actual <= el_target:
            return "IO"
        ratio = (el_actual - el_target) / abs(el_target)
        if ratio <= 0.01:
            return "IO"
        if ratio <= 0.10:
            return "WARN"
        return "nIO"

    # Rule 6: "Folgende Firmen können auf ... buchen: ... in genau dieser Priorität."
    if "folgende firmen" in h and ("priorität" in h or "priorit" in h):
        checks = [ctx.get("allowed_company_ok"), ctx.get("priority_order_ok")]
        applicable = [c for c in checks if c is not None]
        if not applicable:
            return "-"
        return "IO" if all(applicable) else "nIO"

    # Rule 7: "Nur für ..."
    if h.startswith("nur für ") or h.startswith("nur f\u00fcr ") or h.startswith("nur fuer "):
        val = ctx.get("allowed_company_ok")
        return _io_text(val)

    # Rule 8: "Achtung: 4soft kann nur auf PMT und Digi-budget gebucht werden!"
    if "4soft kann nur" in h:
        val = ctx.get("four_soft_ok")
        return _io_text(val)

    # Rule 9: "Hier nur FL buchen."
    if "hier nur fl buchen" in h:
        el_actual = ctx.get("el_actual_annual", 0.0)
        return "IO" if abs(el_actual) <= 0.1 else "nIO"

    # Rule 10: "Nur EL. Keine FL."
    if "nur el" in h and "keine fl" in h:
        fl_actual = ctx.get("fl_actual_sum", 0.0)
        return "IO" if abs(fl_actual) <= 0.1 else "nIO"

    # Rule 11: "FL kann am Stück beauftragt werden..." (explicit exemption)
    if "am stück beauftragt" in h or "am stueck beauftragt" in h or "am st\u00fcck" in h:
        return "IO"

    # Rule 3b: "pro Quartal beauftragt werden" / "pro por Quartal" (typo variant)
    if ("pro quartal" in h or "pro por quartal" in h) and "beauftragt" in h:
        worst = _worst_band(ctx["quarter_band"], ctx["el_period_band"])
        return _band_to_io(worst)

    # Fallback: unmatched hint
    return "-"


def _special_rule_matches_budget_row(rule: dict[str, Any], row: dict[str, Any]) -> bool:
    topic = str(rule.get("topic", "")).upper()
    if "DIGI-BUDGET" in topic:
        title = str(row.get("title", "")).upper()
        bm_text = str(row.get("bm_text", "")).upper()
        return "VW-EK" in title and "DIGITALISIERUNG" in bm_text
    return True


def _load_el_aggregates(year: int, num_q: int) -> dict[str, dict[str, float]]:
    period_columns = MONTH_COLUMNS[: num_q * 3]
    year_expr = " + ".join(f"COALESCE({column}, 0)" for column in MONTH_COLUMNS)
    period_expr = " + ".join(f"COALESCE({column}, 0)" for column in period_columns) or "0"
    sql = f"""
        SELECT
            ea_number,
            ROUND(SUM((({year_expr}) / 1200.0) * year_work_hours), 2) AS year_hours,
            ROUND(SUM((({period_expr}) / 1200.0) * year_work_hours), 2) AS period_hours,
            ROUND(SUM((({year_expr}) / 1200.0) * year_work_hours * hourly_rate) / 1000.0, 2) AS year_te,
            ROUND(SUM((({period_expr}) / 1200.0) * year_work_hours * hourly_rate) / 1000.0, 2) AS period_te
        FROM el_planning
        GROUP BY ea_number
    """
    try:
        rows = run_sql(sql, year)
    except BaseException:
        return {}
    aggregates: dict[str, dict[str, float]] = {}
    for row in rows:
        key = _normalize_ea_key(row.get("ea_number"))
        if not key:
            continue
        aggregates[key] = {
            "year_hours": float(row.get("year_hours") or 0),
            "period_hours": float(row.get("period_hours") or 0),
            "year_te": float(row.get("year_te") or 0),
            "period_te": float(row.get("period_te") or 0),
        }
    return aggregates


def build_special_rule_section(
    *,
    year: int,
    num_q: int,
    q_label: str,
    rows: list[dict],
    status_map: dict[str, str],
) -> Any:
    ea_budget_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    known_companies: set[str] = set()
    for row in rows:
        ea_key = _normalize_ea_key(row.get("dev_order") or row.get("ea_number") or row.get("ea"))
        if not ea_key:
            continue
        pv = int(float(row.get("planned_value", "0") or 0))
        company = row.get("company", "")
        title = row.get("title", "")
        bm_text = row.get("bm_text", "")
        status_label = status_map.get(row.get("status", ""), "")
        reporting_company = _reporting_company(classify_bm(company, title, bm_text), company)
        ea_budget_rows[ea_key].append(
            {
                "planned_value": pv,
                "reporting_company": reporting_company,
                "status_label": status_label,
                "title": title,
                "bm_text": bm_text,
            }
        )
        known_companies.add(reporting_company)

    special_rules = load_special_rule_rows(SPECIAL_RULES_XLSX, sorted(known_companies))
    if not special_rules:
        return None

    el_aggregates = _load_el_aggregates(year, num_q)
    pmt_or_digi_eas = {
        ea_key
        for rule in special_rules
        if "PMT" in rule["topic"].upper() or "DIGI-BUDGET" in rule["topic"].upper()
        for ea_key in rule["ea_keys"]
    }
    rows_out: list[TableRow] = []

    for rule in special_rules:
        totals = {
            "count": 0,
            "sum_te": 0.0,
            "bestellt_te": 0.0,
            "durchlauf_te": 0.0,
            "konzept_te": 0.0,
            "storniert_te": 0.0,
            "period_te": 0.0,
            "el_year_hours": 0.0,
            "el_period_hours": 0.0,
            "el_year_te": 0.0,
            "el_period_te": 0.0,
        }
        company_totals: dict[str, int] = defaultdict(int)
        for ea_key in rule["ea_keys"]:
            for budget_row in ea_budget_rows.get(ea_key, []):
                if not _special_rule_matches_budget_row(rule, budget_row):
                    continue
                pv = int(budget_row["planned_value"])
                totals["count"] += 1
                totals["sum_te"] += pv / 1000
                company_totals[str(budget_row["reporting_company"])] += pv
                status_label = str(budget_row["status_label"])
                if status_label == "bestellt":
                    totals["bestellt_te"] += pv / 1000
                elif status_label == "im Durchlauf":
                    totals["durchlauf_te"] += pv / 1000
                elif status_label == "Konzept":
                    totals["konzept_te"] += pv / 1000
                elif status_label == "storniert":
                    totals["storniert_te"] += pv / 1000
            el_row = el_aggregates.get(ea_key)
            if el_row:
                totals["el_year_hours"] += el_row["year_hours"]
                totals["el_period_hours"] += el_row["period_hours"]
                totals["el_year_te"] += el_row["year_te"]
                totals["el_period_te"] += el_row["period_te"]
        totals["period_te"] = totals["bestellt_te"] + totals["durchlauf_te"]

        fl_target_annual = _annual_target_for_cadence(rule["fl_target_te"], rule["cadence_type"])
        fl_target_period = _period_target_for_cadence(rule["fl_target_te"], rule["cadence_type"], num_q)
        year_band = _diff_band_status(totals["sum_te"], fl_target_annual)
        quarter_band = _diff_band_status(totals["period_te"], fl_target_period)
        year_ok = None if fl_target_annual is None else year_band == "OK"
        quarter_ok = None if fl_target_period is None else quarter_band == "OK"

        el_diff_display = "-"
        el_diff_band = "-"
        el_period_band = "-"
        el_annual_target: float | None = None
        el_actual_annual: float = 0.0
        el_mode = rule["el_target"]["mode"]
        if el_mode in {"hours", "te"}:
            el_actual_annual = totals["el_year_hours"] if el_mode == "hours" else totals["el_year_te"]
            actual_period = totals["el_period_hours"] if el_mode == "hours" else totals["el_period_te"]
            el_base_target = rule["el_target"]["value"]
            if el_base_target is not None:
                el_annual_target = _annual_target_for_cadence(el_base_target, rule["cadence_type"])
                el_period_target = _period_target_for_cadence(el_base_target, rule["cadence_type"], num_q)
                if el_annual_target is not None:
                    if el_mode == "hours":
                        el_diff_display = delta_hours_fmt(el_actual_annual - el_annual_target)
                    else:
                        el_diff_display = delta_fmt(el_actual_annual - el_annual_target)
                if el_annual_target is not None:
                    el_diff_band = _diff_band_status(el_actual_annual, el_annual_target)
                el_period_band = _diff_band_status(actual_period, el_period_target)

        active_companies = {
            company
            for company, value in company_totals.items()
            if abs(value) > 0
        }
        allowed_company_ok: bool | None = None
        if rule["allowed_companies"]:
            allowed_company_ok = active_companies.issubset(set(rule["allowed_companies"]))
        priority_order_ok: bool | None = None
        if rule["priority_companies"]:
            rank_map = {company: idx for idx, company in enumerate(rule["priority_companies"], start=1)}
            active_ranks = sorted(rank_map[company] for company in active_companies if company in rank_map)
            priority_order_ok = active_ranks == list(range(1, len(active_ranks) + 1))
        four_soft_ok: bool | None = None
        four_soft = COMPANY_ALIAS_FALLBACKS["4SOFT"]
        if four_soft in active_companies:
            four_soft_ok = set(rule["ea_keys"]).issubset(pmt_or_digi_eas)

        ctx = {
            "year_band": year_band,
            "quarter_band": quarter_band,
            "el_diff_band": el_diff_band,
            "el_period_band": el_period_band,
            "el_annual_target": el_annual_target,
            "el_actual_annual": el_actual_annual,
            "el_mode": el_mode,
            "allowed_company_ok": allowed_company_ok,
            "priority_order_ok": priority_order_ok,
            "four_soft_ok": four_soft_ok,
            "fl_actual_sum": totals["sum_te"],
            "fl_target_annual": fl_target_annual,
            "fl_period_te": totals["period_te"],
        }

        base_values = [
            rule["topic"],
            rule["ea_display"] or "-",
            fmt(fl_target_annual) if fl_target_annual is not None else "-",
            fmt(totals["sum_te"]),
            delta_fmt(totals["sum_te"] - fl_target_annual) if fl_target_annual is not None else "-",
            fmt(fl_target_period) if fl_target_period is not None else "-",
            fmt(totals["bestellt_te"]),
            fmt(totals["durchlauf_te"]),
            fmt(totals["konzept_te"]),
            el_diff_display,
            delta_fmt(totals["period_te"] - fl_target_period) if fl_target_period is not None else "-",
            rule["remark"],
        ]

        hints = [h.strip() for h in rule["notes"].split("\n") if h.strip()]
        if not hints:
            rows_out.append(
                TableRow(
                    base_values + ["-", "-"],
                    cell_statuses={
                        "DIFF Ges.": year_band,
                        f"DIFF {q_label}": quarter_band,
                        "EL DIFF": el_diff_band,
                        "IO/nIO": "-",
                    },
                )
            )
        else:
            for hint_idx, hint_text in enumerate(hints):
                hint_status = _evaluate_hint_status(hint_text, ctx)
                if hint_idx == 0:
                    rows_out.append(
                        TableRow(
                            base_values + [hint_text, hint_status],
                            cell_statuses={
                                "DIFF Ges.": year_band,
                                f"DIFF {q_label}": quarter_band,
                                "EL DIFF": el_diff_band,
                                "IO/nIO": hint_status,
                            },
                        )
                    )
                else:
                    rows_out.append(
                        TableRow(
                            [""] * 12 + [hint_text, hint_status],
                            cell_statuses={"IO/nIO": hint_status},
                        )
                    )

    return TableSection(
        title="Sondervereinbarungen",
        headers=[
            "Thema",
            "EA",
            "Soll",
            "Ist",
            "DIFF Ges.",
            f"Soll {q_label}",
            "bestellt",
            "im Durchlauf",
            "01 Erstellung",
            "EL DIFF",
            f"DIFF {q_label}",
            "Bemerkung",
            "Hinweise",
            "IO/nIO",
        ],
        rows=rows_out,
        align_right={1, 2, 3, 4, 5, 6, 7, 8, 10},
        body_row_height=15,
    )


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
    except Exception as exc:  # PDF ist Zusatzartefakt; Markdown/XLSX bleiben gültig.
        print(f"WARNUNG: PDF-Export fehlgeschlagen: {exc}", file=sys.stderr)
        return None


def open_excel_file(xlsx_file: str) -> None:
    """Öffnet die erzeugte XLSX-Datei auf Windows in der Standardanwendung (Excel)."""
    if os.name != "nt":
        return
    try:
        os.startfile(xlsx_file)
    except OSError as exc:
        print(f"WARNUNG: Excel-Datei konnte nicht automatisch geöffnet werden: {exc}", file=sys.stderr)

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
    """Führt SQL nach budget_db.py-Sync direkt auf SQLite aus."""
    sql_oneline = " ".join(sql.split())
    cmd = [
        sys.executable, BUDGET_DB, "query", sql_oneline,
        "--no-file", "--sync", "--year", str(year),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    if result.returncode != 0:
        raise RuntimeError(f"budget_db.py query fehlgeschlagen:\n{result.stderr}")
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql_oneline).fetchall()
    return [dict(row) for row in rows]


def fmt(v: float | int) -> str:
    number = float(v)
    if number.is_integer():
        return f"{int(number):,}".replace(",", ".") + " T€"
    text = f"{number:,.1f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".") + " T€"


def delta_fmt(d: float | int) -> str:
    sign = "+" if d > 0 else ""
    return sign + fmt(d)


def fmt_hours(v: float | int) -> str:
    number = float(v)
    if number.is_integer():
        return f"{int(number):,}".replace(",", ".") + " h"
    text = f"{number:,.1f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".") + " h"


def delta_hours_fmt(d: float | int) -> str:
    sign = "+" if d > 0 else ""
    return sign + fmt_hours(d)


@dataclass
class TableRow:
    values: list[str]
    style: str = "body"
    cell_statuses: dict[str, str] = field(default_factory=dict)


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
    overview_quarter_block: dict[str, Any] | None = None


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


def _write_overview_quarter_block(ws, overview_quarter_block: dict[str, Any] | None) -> None:
    if not overview_quarter_block:
        return

    row_labels = ("IST 2025 (Referenz)", "Ist (BPLUS)", "Target", "Delta Ist vs. Target")
    row_map: dict[str, int] = {}
    for row_idx in range(1, ws.max_row + 1):
        label = _strip_markdown(str(ws.cell(row_idx, 1).value or ""))
        if label in row_labels:
            row_map[label] = row_idx
    if len(row_map) != len(row_labels):
        return

    header_row = row_map["IST 2025 (Referenz)"] - 1
    header_template = ws.cell(header_row, 2)
    ws.cell(header_row, 2).value = "Jahr"

    for col_idx, quarter in enumerate(overview_quarter_block.get("headers", QUARTERS), start=3):
        cell = ws.cell(header_row, col_idx)
        _copy_cell_display(header_template, cell, copy_value=False)
        cell.value = quarter
        ws.column_dimensions[get_column_letter(col_idx)].width = max(ws.column_dimensions[get_column_letter(col_idx)].width or 0, 12)

    delta_year_cell = ws.cell(row_map["Delta Ist vs. Target"], 2)
    if isinstance(delta_year_cell.value, (int, float)):
        _apply_signed_delta_style(delta_year_cell, delta_year_cell.value)

    for label in row_labels:
        template_cell = ws.cell(row_map[label], 2)
        for col_idx, value in enumerate(overview_quarter_block["rows"].get(label, []), start=3):
            cell = ws.cell(row_map[label], col_idx)
            _copy_cell_display(template_cell, cell, copy_value=False)
            cell.value = value
            cell.number_format = _te_number_format(value)
            if label == "Delta Ist vs. Target":
                _apply_signed_delta_style(cell, value)


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


def _column_width_to_pixels(width: float | None) -> int:
    width = 8.43 if width is None else width
    return int(width * 7 + 5)


def _row_height_to_pixels(height: float | None) -> int:
    height = 15 if height is None else height
    return int(height * 4 / 3)


def _embed_target_image(ws, image_path: str) -> None:
    if not os.path.isfile(image_path):
        return
    img = XLImage(image_path)
    start_col = 8   # H
    end_col = 12    # L
    start_row = 2
    end_row = 25
    target_width = sum(
        _column_width_to_pixels(ws.column_dimensions[get_column_letter(col_idx)].width)
        for col_idx in range(start_col, end_col + 1)
    )
    target_height = sum(
        _row_height_to_pixels(ws.row_dimensions[row_idx].height)
        for row_idx in range(start_row, end_row + 1)
    )
    img.width = target_width
    img.height = target_height
    ws.add_image(img, "H2")


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


def _parse_te_number(value: str) -> float | int | None:
    text = _strip_markdown(str(value))
    match = re.fullmatch(r"([+-]?)(\d{1,3}(?:\.\d{3})*|\d+)(?:,(\d+))?\s*T€", text)
    if not match:
        return None
    sign, digits, decimals = match.groups()
    normalized = digits.replace(".", "")
    number = float(f"{normalized}.{decimals}") if decimals else int(normalized)
    return -number if sign == "-" else number


def _te_number_format(value: float | int) -> str:
    return '#,##0.0 "T€";[Red]-#,##0.0 "T€"' if float(value) % 1 else '#,##0 "T€";[Red]-#,##0 "T€"'


def _round_te_display(value: float | int) -> int:
    return int(round(float(value)))


def _apply_signed_delta_style(cell, value: float | int) -> None:
    cell.number_format = '#,##0 "T€";-#,##0 "T€"'
    if value > 0:
        cell.font = copy(cell.font)
        cell.font = Font(
            name=cell.font.name,
            sz=cell.font.sz,
            b=cell.font.b,
            i=cell.font.i,
            underline=cell.font.underline,
            strike=cell.font.strike,
            color="FFFF0000",
        )
        cell.fill = PatternFill("solid", fgColor="FFFFC7CE")
    elif value < 0:
        cell.font = copy(cell.font)
        cell.font = Font(
            name=cell.font.name,
            sz=cell.font.sz,
            b=cell.font.b,
            i=cell.font.i,
            underline=cell.font.underline,
            strike=cell.font.strike,
            color="FF000000",
        )
        cell.fill = PatternFill("solid", fgColor="FFC6EFCE")


def _quarter_split_period_target_eur(quarter_split: dict[str, Any] | None, num_q: int) -> int | None:
    if not quarter_split:
        return None
    total_te = sum(float(quarter_split["quarters_te"][quarter]) for quarter in QUARTERS[:num_q])
    return round(total_te * 1000)


def _scale_distribution_to_target(values: dict[str, int], target_total: int | None) -> dict[str, int]:
    if target_total is None:
        return dict(values)
    positive = {key: value for key, value in values.items() if value > 0}
    if target_total <= 0 or not positive:
        return {key: 0 for key in values}

    current_total = sum(positive.values())
    scaled = {key: 0 for key in values}
    remainders: list[tuple[float, str]] = []
    assigned = 0
    for key, value in positive.items():
        raw_value = value * target_total / current_total
        base_value = int(raw_value)
        scaled[key] = base_value
        assigned += base_value
        remainders.append((raw_value - base_value, key))

    remainders.sort(reverse=True)
    for _, key in remainders[: max(target_total - assigned, 0)]:
        scaled[key] += 1
    return scaled


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
    status_fill_ok = PatternFill("solid", fgColor="FFC6EFCE")
    status_fill_warn = PatternFill("solid", fgColor="FFFFEB9C")
    status_fill_x = PatternFill("solid", fgColor="FFFFC7CE")
    status_fill_na = PatternFill("solid", fgColor="FFD9D9D9")
    wrap = Alignment(vertical="top", wrap_text=True)
    left = Alignment(horizontal="left", vertical="top", wrap_text=True)
    right = Alignment(horizontal="right", vertical="top", wrap_text=True)
    center = Alignment(horizontal="center", vertical="top", wrap_text=True)

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

        def special_status_fill(value: str) -> PatternFill | None:
            text = _strip_markdown(str(value)).upper()
            if text in {"OK", "IO"}:
                return status_fill_ok
            if text == "WARN":
                return status_fill_warn
            if text in {"X", "NIO"}:
                return status_fill_x
            if text == "-":
                return status_fill_na
            return None

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
                cell.alignment = center if header in SPECIAL_STATUS_HEADERS else left
                update_width(col_idx, header)
            set_row_height(
                current_row,
                texts=section.headers,
                chars_per_line=[effective_chars_per_line(idx) for idx in range(1, len(section.headers) + 1)],
                min_height=20,
                line_height=15,
            )
            current_row += 1

            is_sonder = section.title == "Sondervereinbarungen"

            for ridx, row in enumerate(section.rows):
                row_idx = current_row
                if is_sonder:
                    is_first_of_block = not (row.values and row.values[0] == "")
                    next_is_cont = (
                        ridx + 1 < len(section.rows)
                        and section.rows[ridx + 1].values
                        and section.rows[ridx + 1].values[0] == ""
                    )
                    row_border = Border(
                        left=thin,
                        right=thin,
                        top=thin if is_first_of_block else None,
                        bottom=thin if not next_is_cont else None,
                    )
                else:
                    row_border = border

                for col_idx, value in enumerate(row.values, start=1):
                    te_number = _parse_te_number(value)
                    cell_value = te_number if te_number is not None else _strip_markdown(value)
                    cell = ws.cell(current_row, col_idx, cell_value)
                    cell.border = row_border
                    header = section.headers[col_idx - 1] if col_idx - 1 < len(section.headers) else ""
                    cell_status = row.cell_statuses.get(header)
                    if header in SPECIAL_STATUS_HEADERS:
                        cell.alignment = center
                    else:
                        cell.alignment = right if (col_idx - 1) in section.align_right else left
                    if ws.title == "Korrektur" and row.style == "body" and col_idx == 1:
                        url = _bplus_vorgang_url(str(value))
                        if url:
                            cell.hyperlink = url
                            cell.font = Font(color="0563C1", underline="single")
                    if te_number is not None:
                        cell.number_format = _te_number_format(te_number)
                    if row.style == "summary":
                        cell.font = Font(bold=True)
                        cell.fill = summary_fill
                    elif row.style == "note":
                        cell.font = Font(italic=True)
                    elif cell_status is not None:
                        fill = special_status_fill(cell_status)
                        if fill is not None:
                            cell.fill = fill
                    elif header in SPECIAL_STATUS_HEADERS:
                        fill = special_status_fill(str(cell_value))
                        if fill is not None:
                            cell.fill = fill
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
    _embed_target_image(overview_ws, TARGET_IMAGE)

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
    _write_overview_quarter_block(overview_ws, report.overview_quarter_block)
    workbook.save(xlsx_file)
    return xlsx_file


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=datetime.date.today().year)
    parser.add_argument("--pdf", action="store_true", help="Erzeugt zusaetzlich eine PDF-Datei neben Markdown und XLSX.")
    parser.add_argument("--inherit-notes-from")
    args = parser.parse_args()
    year = args.year

    # ── Vorgaben + Prämissen laden ─────────────────────────────────────
    REF_2025, TARGET_2026, AREA_ORDER, START_Q, COMPANY_TARGET_OVERRIDES, QUARTER_SPLIT = load_targets()
    praemissen_text = load_praemissen()
    AUDI_FIXED = TARGET_2026.get(AUDI_KEY, 0)
    quarter_split = QUARTER_SPLIT if QUARTER_SPLIT and int(QUARTER_SPLIT.get("year", 0)) == year else None

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

    # ── BMs laden (inkl. Status) ───────────────────────────────────────
    sql = "SELECT concept, dev_order, ea, title, planned_value, company, status, bm_text, target_date FROM btl"
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
    actual_quarter_eur = {quarter: 0 for quarter in QUARTERS}

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
        quarter = _quarter_for_date(row.get("target_date"), title=title, bm_text=bm_text)
        if quarter in actual_quarter_eur:
            actual_quarter_eur[quarter] += pv
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
    firm_soll_q = _scale_distribution_to_target(firm_soll_q, _quarter_split_period_target_eur(quarter_split, num_q))

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
    overview_quarter_block = None
    if quarter_split:
        target_quarter_te = {quarter: float(quarter_split["quarters_te"][quarter]) for quarter in QUARTERS}
        annual_target_te = float(quarter_split["annual_te"])
        ref_quarter_te = {
            quarter: (sum_25 * target_quarter_te[quarter] / annual_target_te) if annual_target_te else 0.0
            for quarter in QUARTERS
        }
        actual_quarter_te = {quarter: actual_quarter_eur[quarter] / 1000 for quarter in QUARTERS}
        delta_quarter_te = {
            quarter: actual_quarter_te[quarter] - target_quarter_te[quarter]
            for quarter in QUARTERS
        }
        overview_quarter_block = {
            "headers": list(QUARTERS),
            "rows": {
                "IST 2025 (Referenz)": [_round_te_display(ref_quarter_te[quarter]) for quarter in QUARTERS],
                "Ist (BPLUS)": [_round_te_display(actual_quarter_te[quarter]) for quarter in QUARTERS],
                "Target": [_round_te_display(target_quarter_te[quarter]) for quarter in QUARTERS],
                "Delta Ist vs. Target": [_round_te_display(delta_quarter_te[quarter]) for quarter in QUARTERS],
            },
        }

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

    special_section = build_special_rule_section(
        year=year,
        num_q=num_q,
        q_label=q_label,
        rows=rows,
        status_map=status_map,
    )
    if special_section is not None:
        sections.append(special_section)

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
        overview_quarter_block=overview_quarter_block,
    )

    md_text = render_markdown(report)

    # ── Datei schreiben ───────────────────────────────────────────────
    os.makedirs(OUT_DIR, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = os.path.join(OUT_DIR, f"{ts}_budget_massnahmenplan_ekek1.md")
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(md_text + "\n")

    xlsx_file = os.path.join(OUT_DIR, f"{ts}_budget_massnahmenplan_ekek1.xlsx")
    inherit_notes_from = args.inherit_notes_from or _find_previous_xlsx(OUT_DIR, xlsx_file)
    write_xlsx_report(report, xlsx_file, inherit_notes_from=inherit_notes_from)

    pdf_file = write_pdf_beside_markdown(out_file) if args.pdf else None

    rel = os.path.relpath(out_file, REPO_ROOT)
    rel_xlsx = os.path.relpath(xlsx_file, REPO_ROOT)
    print(rel)
    print(rel_xlsx)
    if pdf_file:
        rel_pdf = os.path.relpath(pdf_file, REPO_ROOT)
        print(rel_pdf)

    open_excel_file(xlsx_file)


if __name__ == "__main__":
    main()
