from __future__ import annotations

import importlib.util
from pathlib import Path

from openpyxl import load_workbook


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / ".agents"
    / "skills"
    / "skill-budget-target-ist-analyse"
    / "report_massnahmenplan.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("report_massnahmenplan", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample_report(mod):
    return mod.ReportDocument(
        title="Testreport",
        meta_lines=["**Stand BPLUS-NG:** 2026-04-09T12:00:00 | **Erstellt:** 09.04.2026"],
        sections=[
            mod.TableSection(
                title="Gesamtübersicht",
                headers=["", "Wert"],
                rows=[
                    mod.TableRow(["Ist (BPLUS)", "100 T€"]),
                    mod.TableRow(["Summe", "100 T€"], style="summary"),
                ],
                align_right={1},
                separator_before=False,
            ),
            mod.TextSection(
                title="Korrektur Überplanung",
                lines=["**Aktion-Spalte** manuell befüllen"],
                sheet_name="Korrektur",
            ),
            mod.TableSection(
                title="Lieferant A — Jahres-Korrektur: 50 T€ zu reduzieren",
                headers=["Konzept", "EA", "BM-Titel", "Wert", "Status", "Aktion"],
                rows=[mod.TableRow(["K1", "EA1", "BM 1", "50 T€", "01 Erstellung", ""])],
                align_right={3},
                level=3,
                separator_before=False,
                sheet_name="Korrektur",
                body_row_height=15,
            ),
            mod.TextSection(
                title="Hinweise",
                lines=["### Zwischenüberschrift", "- Erster Punkt", "", "**Wichtig**"],
            ),
        ],
        max_columns=11,
    )


def test_render_markdown_formats_summary_and_sections():
    mod = load_module()
    report = sample_report(mod)

    content = mod.render_markdown(report)

    assert "# Testreport" in content
    assert "## Gesamtübersicht" in content
    assert "| **Summe** | **100 T€** |" in content
    assert "## Hinweise" in content
    assert "**Wichtig**" in content


def test_exclude_from_budget_filters_storniert():
    mod = load_module()

    assert mod._exclude_from_budget("storniert") is False
    assert mod._exclude_from_budget("bestellt") is False
    assert mod._exclude_from_budget("im Durchlauf") is False


def test_hide_from_firm_overview_filters_voitas():
    mod = load_module()

    assert mod._hide_from_firm_overview("Voitas GmbH") is True
    assert mod._hide_from_firm_overview("4Soft GmbH") is False


def test_thiesen_manual_soll_includes_both_thiesen_areas():
    mod = load_module()

    result = mod._thiesen_manual_soll(
        "Thiesen GmbH",
        {
            "Bordnetz Support, RollOut (Thiesen)": 288,
            "Spez. und Test VOBES2025 (Thiesen)": 263,
        },
        {
            "Bordnetz Support, RollOut (Thiesen)": 1,
            "Spez. und Test VOBES2025 (Thiesen)": 1,
        },
        2,
    )

    assert result == (551000, 275500)


def test_write_xlsx_report_writes_titles_and_summary_style(tmp_path):
    mod = load_module()
    report = sample_report(mod)
    output = tmp_path / "report.xlsx"

    mod.write_xlsx_report(report, str(output))

    workbook = load_workbook(output)
    overview = workbook["Übersicht"]
    correction = workbook["Korrektur"]

    positions = {}
    for row in overview.iter_rows():
        for cell in row:
            if cell.value in {"Gesamtübersicht", "Summe", "Hinweise", "Wichtig", "Zwischenüberschrift"}:
                positions[cell.value] = cell.coordinate

    correction_values = {
        cell.value
        for row in correction.iter_rows()
        for cell in row
        if cell.value is not None
    }

    assert workbook.sheetnames == ["Übersicht", "Korrektur"]
    assert overview["A1"].value == "Testreport"
    assert overview.row_dimensions[1].height and overview.row_dimensions[1].height >= 30
    assert overview["A1"].fill.fill_type is None
    assert correction.row_dimensions[1].height and correction.row_dimensions[1].height >= 24
    assert overview.column_dimensions["A"].width == 44
    assert correction.column_dimensions["A"].width <= 20
    assert correction.column_dimensions["C"].width == 48
    assert correction.row_dimensions[5].height == 15
    assert positions["Gesamtübersicht"] == "A3"
    assert positions["Summe"] == "A6"
    assert overview[positions["Summe"]].font.bold is True
    assert overview["B5"].value == 100
    assert 'T€' in overview["B5"].number_format
    assert positions["Hinweise"] == "A8"
    assert positions["Zwischenüberschrift"] == "A9"
    assert overview["A9"].font.bold is True
    assert positions["Wichtig"] == "A12"
    assert correction["A1"].value == "Korrektur Überplanung"
    assert "Korrektur Überplanung" in correction_values
    assert "Lieferant A — Jahres-Korrektur: 50 T€ zu reduzieren" in correction_values


def test_reporting_company_maps_voitas_rulechecker_to_4soft():
    mod = load_module()

    assert mod._reporting_company("RuleChecker (4soft, ex Voitas)", "VOITAS ENGINEERING GMBH") == "4SOFT GMBH MUENCHEN"
    assert mod._reporting_company("Vorentwicklung (4soft)", "4SOFT GMBH MUENCHEN") == "4SOFT GMBH MUENCHEN"


def test_load_targets_reads_company_target_overrides():
    mod = load_module()

    _, _, _, _, overrides = mod.load_targets()

    assert "BERTRANDT" in overrides
    assert overrides["BERTRANDT"]["area"] == "Systemschaltpläne und Bibl. (EDAG, Bertrandt)"
    assert overrides["BERTRANDT"]["target_te"] == 905


def test_write_xlsx_report_inherits_notes_and_column_widths(tmp_path):
    mod = load_module()
    report = mod.ReportDocument(
        title="Testreport",
        meta_lines=["Meta"],
        sections=[
            mod.TableSection(
                title="Target - Ist - Vergleich",
                headers=["Aufgabenbereich", "2025", "Target", "Ist", "Delta", "Maßnahmen"],
                rows=[mod.TableRow(["Area A", "1 T€", "2 T€", "3 T€", "+1 T€", ""])],
                align_right={1, 2, 3, 4},
                separator_before=False,
            ),
            mod.TableSection(
                title="Firmen-Übersicht",
                headers=["Firma", "BMs", "Soll", "Ist", "DIFF Ges.", "Soll Q1-2", "bestellt", "im Durchlauf", "01 Erstellung", "storniert", "DIFF Q1-2", "Maßnahmen"],
                rows=[mod.TableRow(["4SOFT", "2", "10 T€", "12 T€", "+2 T€", "5 T€", "2 T€", "1 T€", "3 T€", "0 T€", "-1 T€", "auto"])],
                align_right={1, 2, 3, 4, 5, 6, 7, 8, 9, 10},
            ),
            mod.TextSection(title="Korrektur Überplanung", lines=["Hinweis"], sheet_name="Korrektur"),
            mod.TableSection(
                title="4SOFT — Jahres-Korrektur: 2 T€ zu reduzieren",
                headers=["Konzept", "EA", "BM-Titel", "Wert", "Status", "Aktion"],
                rows=[mod.TableRow(["831058", "EA1", "Titel", "2 T€", "01_In Erstellung", ""])],
                align_right={3},
                level=3,
                separator_before=False,
                sheet_name="Korrektur",
                body_row_height=15,
            ),
        ],
        max_columns=13,
    )

    source = tmp_path / "source.xlsx"
    target = tmp_path / "target.xlsx"

    from openpyxl import Workbook
    from openpyxl.styles import Font, Border, Side, Alignment

    wb = Workbook()
    overview = wb.active
    overview.title = "Übersicht"
    correction = wb.create_sheet("Korrektur")
    overview["A1"] = "Aufgabenbereich"
    overview["F1"] = "Maßnahmen"
    overview["A2"] = "Area A"
    overview["F2"] = "Bereichsnotiz"
    overview["A4"] = "Firma"
    overview["M4"] = "Notizen"
    overview["A5"] = "4SOFT"
    overview["M5"] = "Firmennotiz"
    overview.column_dimensions["F"].width = 33
    overview.column_dimensions["M"].width = 77
    overview["M5"].font = Font(color="FFFF0000", bold=False)
    overview["M5"].alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
    overview["M5"].border = Border(left=Side(style="thin"), right=Side(style="thin"), top=Side(style="thin"), bottom=Side(style="thin"))
    correction["A1"] = "4SOFT — Jahres-Korrektur: 2 T€ zu reduzieren"
    correction["A2"] = "Konzept"
    correction["A3"] = "831058"
    correction["F3"] = "manuell"
    correction.column_dimensions["F"].width = 88
    wb.save(source)

    mod.write_xlsx_report(report, str(target), inherit_notes_from=str(source))

    out = load_workbook(target)
    out_overview = out["Übersicht"]
    out_correction = out["Korrektur"]

    area_row = next(row for row in range(1, out_overview.max_row + 1) if out_overview[f"A{row}"].value == "Area A")
    firm_header_row = next(row for row in range(1, out_overview.max_row + 1) if out_overview[f"A{row}"].value == "Firma")
    firm_row = next(row for row in range(firm_header_row + 1, out_overview.max_row + 1) if out_overview[f"A{row}"].value == "4SOFT")
    correction_row = next(row for row in range(1, out_correction.max_row + 1) if out_correction[f"A{row}"].value == "831058")

    assert out_overview.cell(area_row, 6).value == "Bereichsnotiz"
    assert out_overview.cell(firm_header_row, 13).value == "Notizen"
    assert out_overview.cell(firm_row, 13).value == "Firmennotiz"
    assert out_overview.cell(firm_row, 13).font.color.type == "rgb"
    assert out_overview.cell(firm_row, 13).font.color.rgb == "FFFF0000"
    assert out_overview.column_dimensions["F"].width == 33
    assert out_overview.column_dimensions["M"].width == 77
    assert out_correction.cell(correction_row, 6).value == "manuell"
    assert out_correction.column_dimensions["F"].width == 88
