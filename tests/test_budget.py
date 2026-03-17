"""Budget reporting system tests -- minimal tests, maximum coverage, zero calculation errors."""
from __future__ import annotations

import sqlite3

import pytest


# ---------------------------------------------------------------
# 1. Pure number parsing & formatting (paths 1, 2, 3)
# ---------------------------------------------------------------

class TestNumberParsing:

    @pytest.mark.parametrize("input_val, expected", [
        (None, 0),
        ("", 0),
        (0, 0),
        (37980, 37980),
        ("37980", 37980),
        ("37980,49", 37980),
        ("37980,50", 37980),        # banker's rounding (.50 -> even)
        ("37981,50", 37982),        # banker's rounding (.50 -> even)
        ("37980,51", 37981),
        (159.08, 159),
        ("159,08", 159),
        ("abc", 0),
        ("37.980,00", 0),           # German thousands sep -> ValueError -> 0
    ])
    def test_as_int(self, budget_db, input_val, expected):
        assert budget_db.as_int(input_val) == expected

    @pytest.mark.parametrize("input_val, expected", [
        (None, 0.0),
        ("", 0.0),
        ("159,08", 159.08),
        ("0,5", 0.5),
        (2.5, 2.5),
        ("abc", 0.0),
    ])
    def test_as_float(self, budget_db, input_val, expected):
        assert budget_db.as_float(input_val) == pytest.approx(expected)

    @pytest.mark.parametrize("input_val, expected", [
        (38000, "38.000"),
        (0, "0"),
        (999, "999"),
        (1000000, "1.000.000"),
        (1478544, "1.478.544"),
        (4276436, "4.276.436"),
    ])
    def test_euro(self, report_bplus, input_val, expected):
        assert report_bplus.euro(input_val) == expected


# ---------------------------------------------------------------
# 2. String helpers
# ---------------------------------------------------------------

class TestStringHelpers:

    @pytest.mark.parametrize("input_val, expected", [
        (None, ""),
        ("", ""),
        ("  hello  ", "hello"),
        (42, "42"),
    ])
    def test_trim(self, budget_db, input_val, expected):
        assert budget_db.trim(input_val) == expected

    @pytest.mark.parametrize("input_val, expected", [
        (None, ""),
        ("", ""),
        ("2026-03-17T13:49:21", "2026-03-17"),
        ("2026-03-17", "2026-03-17"),
    ])
    def test_iso_date(self, budget_db, input_val, expected):
        assert budget_db.iso_date(input_val) == expected

    @pytest.mark.parametrize("input_val, expected", [
        (None, "report"),
        ("", "report"),
        ("Hello World!", "hello_world"),
        ("a" * 100, "a" * 48),
    ])
    def test_slug(self, report_utils, input_val, expected):
        assert report_utils.slug(input_val) == expected


# ---------------------------------------------------------------
# 3. SQL validation & extraction (path 10)
# ---------------------------------------------------------------

class TestSQLValidation:

    def test_validate_select_allows_select(self, budget_db):
        budget_db.validate_select("SELECT * FROM btl")

    def test_validate_select_allows_cte(self, budget_db):
        budget_db.validate_select("WITH cte AS (SELECT 1) SELECT * FROM cte")

    @pytest.mark.parametrize("bad_sql", [
        "INSERT INTO btl VALUES (1)",
        "DELETE FROM btl",
        "DROP TABLE btl",
        "UPDATE btl SET status='x'",
        "ALTER TABLE btl ADD col TEXT",
        "CREATE TABLE hack (x TEXT)",
        "ATTACH DATABASE 'x' AS x",
        "PRAGMA table_info(btl)",
    ])
    def test_validate_select_rejects_mutations(self, budget_db, bad_sql):
        with pytest.raises(ValueError):
            budget_db.validate_select(bad_sql)

    @pytest.mark.parametrize("sql, expected", [
        ("SELECT * FROM btl", ["btl"]),
        ("SELECT * FROM btl JOIN devorder ON 1=1", ["btl", "devorder"]),
        ("SELECT * FROM el_planning e LEFT JOIN btl b ON 1=1", ["el_planning", "btl"]),
        ("SELECT * FROM unknown_table", []),
    ])
    def test_extract_tables(self, budget_db, sql, expected):
        assert budget_db._extract_tables(sql) == expected


# ---------------------------------------------------------------
# 4. BTL report sections (paths 4, 5, 6, 7)
# ---------------------------------------------------------------

class TestBTLReport:

    def test_section_items_total(self, report_bplus, btl_rows):
        """SUM of all planned_values = 4.276.436."""
        md = report_bplus.section_items(btl_rows)
        assert "**4.276.436**" in md

    def test_section_status_grouping(self, report_bplus, btl_rows):
        """GROUP BY status with count + sum."""
        md = report_bplus.section_status(btl_rows)
        assert "01_In Erstellung" in md
        assert "1.478.544" in md
        assert "97_Abgelehnt" in md
        assert "98_Storniert" in md
        assert "pie showData" in md

    def test_section_company_sorted_desc(self, report_bplus, btl_rows):
        """GROUP BY company, sorted by value DESC."""
        md = report_bplus.section_company(btl_rows, top=None)
        assert "1.083.758" in md
        assert "995.770" in md
        edag_pos = md.index("EDAG")
        bertrandt_pos = md.index("BERTRANDT")
        assert edag_pos < bertrandt_pos

    def test_section_company_top_n(self, report_bplus, btl_rows):
        """top=3 limits to 3 companies."""
        md = report_bplus.section_company(btl_rows, top=3)
        assert "EDAG" in md
        assert "4SOFT" in md
        assert "THIESEN" not in md

    def test_section_ea_grouping(self, report_bplus, btl_rows):
        """GROUP BY dev_order with count + sum."""
        md = report_bplus.section_ea(btl_rows)
        assert "521.097" in md
        assert "390.37" in md  # tabulate strips trailing zero from "390.370"


# ---------------------------------------------------------------
# 5. EL report sections (paths 8, 9)
# ---------------------------------------------------------------

class TestELReport:

    def test_section_jahressicht_known_ea(self, report_el, conn):
        """EL EUR for EA 0043932 = 966809."""
        md = report_el.section_jahressicht(conn)
        assert "0043932" in md
        assert "966809" in md

    def test_section_gesamt_join(self, report_el, conn):
        """EL vs Fremd JOIN: EA 0043932 share = 65.0%."""
        md = report_el.section_gesamt(conn)
        assert "0043932" in md
        assert "65.0%" in md
        assert "pie showData" in md
        assert '"EL"' in md
        assert '"Fremdleistung"' in md

    def test_avg_expr_generates_valid_sql(self, report_el, conn):
        """avg_expr() produces executable SQL."""
        expr = report_el.avg_expr("e")
        sql = f"SELECT {expr} AS avg_pct FROM el_planning e LIMIT 1"
        row = conn.execute(sql).fetchone()
        assert row["avg_pct"] is not None

    def test_section_ma_planung_syring(self, report_el, conn):
        """MA-Planung for Syring: avg 100%, rate 159.08."""
        md = report_el.section_ma_planung(conn, "Syring")
        assert "Syring" in md
        assert "0043932" in md
        assert "100.0%" in md
        assert "159.08" in md


# ---------------------------------------------------------------
# 6. run_select end-to-end (path 11)
# ---------------------------------------------------------------

class TestRunSelect:

    def test_run_select_produces_report(self, budget_db, db_path, tmp_path, monkeypatch):
        """run_select executes SQL, writes markdown, returns Path."""
        def fake_connect():
            c = sqlite3.connect(str(db_path))
            c.row_factory = sqlite3.Row
            return c

        monkeypatch.setattr(budget_db, "connect", fake_connect)

        output = tmp_path / "test_query.md"
        result = budget_db.run_select(
            "SELECT status, COUNT(*) as cnt, SUM(planned_value) as total FROM btl GROUP BY status",
            output=str(output),
            title="Test Query",
        )
        assert result == output
        assert output.exists()
        content = output.read_text(encoding="utf-8")
        assert "# Test Query" in content
        assert "## SQL" in content
        assert "## Ergebnis" in content
        assert "7 Zeilen" in content


# ---------------------------------------------------------------
# 7. report_utils formatting
# ---------------------------------------------------------------

class TestReportUtils:

    def test_table_md_empty(self, report_utils):
        result = report_utils.table_md([], ["A", "B"])
        assert "Keine Ergebnisse" in result

    def test_table_md_with_data(self, report_utils):
        result = report_utils.table_md([[1, "x"], [2, "y"]], ["Num", "Val"])
        assert "Num" in result
        assert "---" in result
        assert "1" in result

    def test_section_format(self, report_utils):
        result = report_utils.section("Title", "Body text")
        assert result == "## Title\n\nBody text\n"

    def test_write_report(self, report_utils, tmp_path):
        path = tmp_path / "test.md"
        report_utils.write_report(path, "My Report", ["## S1\n\nContent\n"])
        content = path.read_text(encoding="utf-8")
        assert "# My Report" in content
        assert "## S1" in content
        assert "Erstellt:" in content
