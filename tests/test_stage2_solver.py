from __future__ import annotations

import sqlite3
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts" / "budget"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import beauftragungsplanung_core as core  # noqa: E402
import stage2_solver as solver  # noqa: E402


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    core.init_planning_schema(conn)
    return conn


def _config(*, cap: int = 0) -> solver.SolverConfig:
    return solver.SolverConfig(active_ea_cap_per_quarter=cap, min_new_order_amount=0)


def _insert_stage1(conn: sqlite3.Connection, rows: list[tuple[str, int, int]]) -> None:
    conn.executemany(
        """
        INSERT INTO plan_stage1_results (run_id, year, ea_number, target_value, reference_score, is_hard, note)
        VALUES ('stage1', 2026, ?, ?, 1.0, ?, NULL)
        """,
        rows,
    )


def _rows_by_key(conn: sqlite3.Connection) -> dict[tuple[str, str, str], int]:
    rows = conn.execute(
        "SELECT company, quarter, ea_number, amount FROM plan_stage2_results"
    ).fetchall()
    return {
        (row["company"], row["quarter"], row["ea_number"]): row["amount"]
        for row in rows
    }


def test_minimal_case_hits_targets_exactly():
    conn = _conn()
    conn.execute(
        """
        INSERT INTO plan_company_targets (year, company, quarter, target_value, annual_target, step_value)
        VALUES
            (2026, 'Firma A', 'Q1', 100, 200, 50),
            (2026, 'Firma A', 'Q2', 100, 200, 50)
        """
    )
    _insert_stage1(conn, [("EA1", 100, 0), ("EA2", 100, 0)])
    conn.commit()

    result = solver.solve_stage2(conn, year=2026, config=_config(), planning_start_quarter=1)

    totals = conn.execute(
        """
        SELECT quarter, SUM(amount) AS total
        FROM plan_stage2_results
        GROUP BY quarter
        ORDER BY quarter
        """
    ).fetchall()
    assert result.summary.status == "optimal"
    assert [(row["quarter"], row["total"]) for row in totals] == [("Q1", 100), ("Q2", 100)]


def test_step_values_are_respected():
    conn = _conn()
    conn.execute(
        """
        INSERT INTO plan_company_targets (year, company, quarter, target_value, annual_target, step_value)
        VALUES
            (2026, 'Firma A', 'Q1', 150, 300, 50),
            (2026, 'Firma A', 'Q2', 150, 300, 50)
        """
    )
    _insert_stage1(conn, [("EA1", 150, 0), ("EA2", 150, 0)])
    conn.commit()

    solver.solve_stage2(conn, year=2026, config=_config(), planning_start_quarter=1)

    amounts = [row["amount"] for row in conn.execute("SELECT amount FROM plan_stage2_results")]
    assert amounts
    assert all(amount % 50 == 0 for amount in amounts)


def test_fixed_orders_are_preserved():
    conn = _conn()
    conn.execute(
        """
        INSERT INTO plan_company_targets (year, company, quarter, target_value, annual_target, step_value)
        VALUES (2026, 'Firma A', 'Q1', 100, 100, 50)
        """
    )
    _insert_stage1(conn, [("EA1", 50, 0), ("EA2", 50, 0)])
    conn.execute(
        """
        INSERT INTO plan_existing_orders (year, company, quarter, ea_number, amount, is_fixed, can_stop, note)
        VALUES (2026, 'Firma A', 'Q1', 'EA1', 50, 1, 0, 'fixed')
        """
    )
    conn.commit()

    solver.solve_stage2(conn, year=2026, config=_config(), planning_start_quarter=1)

    rows = _rows_by_key(conn)
    assert rows[("Firma A", "Q1", "EA1")] == 50


def test_frozen_quarters_keep_existing_values():
    conn = _conn()
    conn.execute(
        """
        INSERT INTO plan_company_targets (year, company, quarter, target_value, annual_target, step_value)
        VALUES
            (2026, 'Firma A', 'Q1', 100, 200, 50),
            (2026, 'Firma A', 'Q2', 100, 200, 50)
        """
    )
    _insert_stage1(conn, [("EA1", 100, 0), ("EA2", 100, 0)])
    conn.executemany(
        """
        INSERT INTO plan_existing_orders (year, company, quarter, ea_number, amount, is_fixed, can_stop, note)
        VALUES (2026, 'Firma A', ?, ?, ?, 0, 1, NULL)
        """,
        [("Q1", "EA1", 50), ("Q1", "EA2", 50)],
    )
    conn.commit()

    solver.solve_stage2(conn, year=2026, config=_config(), planning_start_quarter=2)

    rows = _rows_by_key(conn)
    assert rows[("Firma A", "Q1", "EA1")] == 50
    assert rows[("Firma A", "Q1", "EA2")] == 50


def test_infeasible_constraints_raise():
    conn = _conn()
    conn.execute(
        """
        INSERT INTO plan_company_targets (year, company, quarter, target_value, annual_target, step_value)
        VALUES (2026, 'Firma A', 'Q1', 100, 100, 50)
        """
    )
    _insert_stage1(conn, [("EA1", 100, 0)])
    conn.execute(
        """
        INSERT INTO plan_existing_orders (year, company, quarter, ea_number, amount, is_fixed, can_stop, note)
        VALUES (2026, 'Firma A', 'Q1', 'EA1', 150, 1, 0, 'too much')
        """
    )
    conn.commit()

    with pytest.raises(core.PlanningError):
        solver.solve_stage2(conn, year=2026, config=_config(), planning_start_quarter=1)


def test_hard_group_rules_are_enforced():
    conn = _conn()
    conn.execute(
        """
        INSERT INTO plan_company_targets (year, company, quarter, target_value, annual_target, step_value)
        VALUES
            (2026, 'Firma A', 'Q1', 100, 200, 50),
            (2026, 'Firma A', 'Q2', 100, 200, 50)
        """
    )
    _insert_stage1(conn, [("EA1", 100, 0), ("EA2", 100, 0)])
    conn.execute(
        "INSERT INTO plan_group_rules (year, group_code, target_value, is_hard, note) VALUES (2026, 'G1', 200, 1, NULL)"
    )
    conn.execute(
        "INSERT INTO plan_group_members (year, group_code, ea_number, fixed_target_value, min_value, max_value, is_hard, note) VALUES (2026, 'G1', 'EA1', NULL, NULL, NULL, 1, NULL)"
    )
    conn.commit()

    solver.solve_stage2(conn, year=2026, config=_config(), planning_start_quarter=1)

    total = conn.execute(
        "SELECT SUM(amount) AS total FROM plan_stage2_results WHERE ea_number = 'EA1'"
    ).fetchone()["total"]
    assert total == 200


def test_active_ea_cap_per_quarter_is_enforced():
    conn = _conn()
    conn.execute(
        """
        INSERT INTO plan_company_targets (year, company, quarter, target_value, annual_target, step_value)
        VALUES
            (2026, 'Firma A', 'Q1', 100, 200, 50),
            (2026, 'Firma A', 'Q2', 100, 200, 50)
        """
    )
    _insert_stage1(conn, [("EA1", 100, 0), ("EA2", 100, 0), ("EA3", 100, 0)])
    conn.commit()

    solver.solve_stage2(conn, year=2026, config=_config(cap=1), planning_start_quarter=1)

    rows = conn.execute(
        """
        SELECT quarter, COUNT(*) AS active
        FROM plan_stage2_results
        WHERE amount > 0
        GROUP BY quarter
        """
    ).fetchall()
    assert rows
    assert all(row["active"] <= 1 for row in rows)


def test_throughlauf_rows_are_kept_before_switching_to_other_eas():
    conn = _conn()
    conn.execute(
        """
        INSERT INTO plan_company_targets (year, company, quarter, target_value, annual_target, step_value)
        VALUES (2026, 'Firma A', 'Q1', 50, 50, 50)
        """
    )
    _insert_stage1(conn, [("EA1", 50, 0), ("EA2", 50, 0)])
    conn.execute(
        """
        INSERT INTO plan_existing_orders (year, company, quarter, ea_number, amount, is_fixed, can_stop, note)
        VALUES (2026, 'Firma A', 'Q1', 'EA1', 50, 0, 1, 'auto:06_In Bearbeitung BM-Team')
        """
    )
    conn.commit()

    solver.solve_stage2(conn, year=2026, config=_config(), planning_start_quarter=1)

    rows = _rows_by_key(conn)
    assert rows == {("Firma A", "Q1", "EA1"): 50}


def test_live_btl_rows_are_augmented_as_existing_orders_for_single_scope_company():
    conn = _conn()
    conn.execute(f"CREATE TABLE btl ({core.BTL_COLUMNS_SQL})")
    conn.execute(
        """
        INSERT INTO plan_company_targets (year, company, quarter, target_value, annual_target, step_value)
        VALUES (2026, 'Firma A', 'Q1', 50, 50, 50)
        """
    )
    _insert_stage1(conn, [("EA1", 50, 0)])
    conn.execute(
        """
        INSERT INTO btl (
            concept, ea, title, status, planned_value, org_unit, company, creator, bm_number, az_number,
            projektfamilie, dev_order, bm_text, last_updated, category, cost_type, quantity, unit,
            supplier_number, first_signature, second_signature, target_date, invoices
        )
        VALUES (
            'C1', 'Live EA', 'Live EA', '06_In Bearbeitung BM-Team', 50, 'EKEK/1', 'Firma A', 'Test', NULL, NULL,
            NULL, 'EA_LIVE', 'GW', '2026-01-01', 'TEST', NULL, NULL, NULL,
            NULL, NULL, NULL, '2026-03-31', NULL
        )
        """
    )
    conn.commit()

    core._bootstrap_existing_orders_from_btl(conn, 2026)
    solver.solve_stage2(conn, year=2026, config=_config(), planning_start_quarter=1)

    rows = _rows_by_key(conn)
    assert rows == {("Firma A", "Q1", "EA_LIVE"): 50}


def test_special_rule_annual_targets_are_enforced():
    conn = _conn()
    conn.execute(
        """
        INSERT INTO plan_company_targets (year, company, quarter, target_value, annual_target, step_value)
        VALUES
            (2026, 'Firma A', 'Q1', 50, 100, 50),
            (2026, 'Firma A', 'Q2', 50, 100, 50)
        """
    )
    _insert_stage1(conn, [("EA1", 100, 0), ("EA2", 100, 0)])
    conn.commit()

    rules = [
        {
            "topic": "Testregel",
            "ea_keys": {"1"},
            "candidate_eas": {"EA1"},
            "allowed_companies": set(),
            "priority_companies": [],
            "target_amount": 100,
            "period_target_amount": None,
            "enforce_period_exact": False,
        }
    ]

    cfg = solver.SolverConfig(min_new_order_amount=0)
    solver.solve_stage2(conn, year=2026, config=cfg, planning_start_quarter=1, special_rules=rules)

    total = conn.execute(
        "SELECT SUM(amount) AS total FROM plan_stage2_results WHERE ea_number = 'EA1'"
    ).fetchone()["total"]
    assert total == 100


def test_allowed_special_rule_company_gets_extra_candidate():
    conn = _conn()
    conn.execute(
        """
        INSERT INTO plan_company_targets (year, company, quarter, target_value, annual_target, step_value)
        VALUES
            (2026, 'Firma A', 'Q1', 0, 0, 50),
            (2026, 'Firma B', 'Q1', 100, 100, 50)
        """
    )
    _insert_stage1(conn, [("EA1", 100, 0)])
    conn.commit()

    rules = [
        {
            "topic": "PMT",
            "ea_keys": {"1"},
            "candidate_eas": {"EA1"},
            "allowed_companies": {"Firma B"},
            "priority_companies": ["Firma A", "Firma B"],
            "target_amount": 100,
            "period_target_amount": 100,
            "enforce_period_exact": True,
        }
    ]

    solver.solve_stage2(conn, year=2026, config=_config(), planning_start_quarter=1, special_rules=rules)

    rows = _rows_by_key(conn)
    assert rows == {("Firma B", "Q1", "EA1"): 100}


def test_special_rule_can_create_canonical_ea_without_existing_variant():
    conn = _conn()
    conn.execute(
        """
        INSERT INTO plan_company_targets (year, company, quarter, target_value, annual_target, step_value)
        VALUES (2026, 'Firma B', 'Q1', 100, 100, 50)
        """
    )
    _insert_stage1(conn, [("EA1", 100, 0)])
    conn.commit()

    rules = [
        {
            "topic": "KUE",
            "ea_keys": {"93037"},
            "candidate_eas": {"0093037"},
            "allowed_companies": {"Firma B"},
            "priority_companies": ["Firma B"],
            "target_amount": 100,
            "period_target_amount": None,
            "enforce_period_exact": False,
        }
    ]

    cfg = solver.SolverConfig(min_new_order_amount=0)
    solver.solve_stage2(conn, year=2026, config=cfg, planning_start_quarter=1, special_rules=rules)

    rows = _rows_by_key(conn)
    assert rows == {("Firma B", "Q1", "0093037"): 100}


def test_hard_company_targets_keep_explicit_edag_target(monkeypatch):
    def fake_spec_from_file_location(name, path):
        class FakeLoader:
            def exec_module(self, module):
                module.load_targets = lambda: (
                    {},
                    {"Systemschaltpläne und Bibl. (EDAG, Bertrandt)": 1649},
                    [],
                    1,
                    {"BERTRANDT": {"target_te": 905}},
                    {},
                )

        return types.SimpleNamespace(loader=FakeLoader())

    monkeypatch.setattr("importlib.util.spec_from_file_location", fake_spec_from_file_location)
    monkeypatch.setattr("importlib.util.module_from_spec", lambda spec: types.SimpleNamespace())

    targets = solver._load_hard_company_annual_targets(
        [
            {"company": "EDAG ENGINEERING GMBH WOLFSBURG", "target_value": 544000},
            {"company": "EDAG ENGINEERING GMBH WOLFSBURG", "target_value": 544000},
            {"company": "BERTRANDT INGENIEURBUERO GMBH TAPPENBECK", "target_value": 452500},
            {"company": "BERTRANDT INGENIEURBUERO GMBH TAPPENBECK", "target_value": 452500},
        ]
    )

    assert targets["EDAG ENGINEERING GMBH WOLFSBURG"] == 1088000
    assert targets["BERTRANDT INGENIEURBUERO GMBH TAPPENBECK"] == 905000


def test_pmt_period_target_is_enforced():
    conn = _conn()
    conn.execute(
        """
        INSERT INTO plan_company_targets (year, company, quarter, target_value, annual_target, step_value)
        VALUES
            (2026, 'Firma A', 'Q1', 0, 400, 100),
            (2026, 'Firma A', 'Q2', 300, 400, 100),
            (2026, 'Firma A', 'Q3', 50, 400, 100),
            (2026, 'Firma A', 'Q4', 50, 400, 100)
        """
    )
    _insert_stage1(conn, [("EA1", 400, 0)])
    conn.commit()

    rules = [
        {
            "topic": "PMT",
            "ea_keys": {"1"},
            "candidate_eas": {"EA1"},
            "allowed_companies": set(),
            "priority_companies": [],
            "target_amount": 400,
            "period_target_amount": 200,
            "enforce_period_exact": True,
        }
    ]

    solver.solve_stage2(conn, year=2026, config=_config(), planning_start_quarter=2, special_rules=rules)

    totals = conn.execute(
        """
        SELECT quarter, SUM(amount) AS total
        FROM plan_stage2_results
        GROUP BY quarter
        ORDER BY quarter
        """
    ).fetchall()
    quarter_totals = {row["quarter"]: row["total"] for row in totals}
    assert quarter_totals.get("Q1", 0) + quarter_totals.get("Q2", 0) == 200
    assert quarter_totals.get("Q1", 0) == 0
    assert quarter_totals.get("Q2", 0) == 200
    assert sum(quarter_totals.values()) == 400


def test_company_period_rule_blocks_new_current_quarter_volume_when_period_is_already_fulfilled():
    conn = _conn()
    conn.execute(
        """
        INSERT INTO plan_company_targets (year, company, quarter, target_value, annual_target, step_value)
        VALUES
            (2026, 'Firma A', 'Q1', 100, 200, 10),
            (2026, 'Firma A', 'Q2', 50, 200, 10),
            (2026, 'Firma A', 'Q3', 25, 200, 10),
            (2026, 'Firma A', 'Q4', 25, 200, 10)
        """
    )
    _insert_stage1(conn, [("EA1", 200, 0)])
    conn.executemany(
        """
        INSERT INTO plan_existing_orders (year, company, quarter, ea_number, amount, is_fixed, can_stop, note)
        VALUES (2026, 'Firma A', ?, 'EA1', ?, ?, ?, ?)
        """,
        [
            ("Q1", 100, 1, 0, "auto:07_In Planen-BM: Bestellt"),
            ("Q4", 60, 1, 0, "auto:07_In Planen-BM: Bestellt"),
        ],
    )
    conn.commit()

    solver.solve_stage2(conn, year=2026, config=_config(), planning_start_quarter=2)

    rows = _rows_by_key(conn)
    assert ("Firma A", "Q2", "EA1") not in rows
    assert rows[("Firma A", "Q1", "EA1")] == 100
    assert rows[("Firma A", "Q3", "EA1")] == 40
    assert rows[("Firma A", "Q4", "EA1")] == 60


def test_company_period_rule_prevents_increase_of_existing_current_quarter_volume():
    conn = _conn()
    conn.execute(
        """
        INSERT INTO plan_company_targets (year, company, quarter, target_value, annual_target, step_value)
        VALUES
            (2026, 'Firma A', 'Q1', 100, 200, 10),
            (2026, 'Firma A', 'Q2', 50, 200, 10),
            (2026, 'Firma A', 'Q3', 25, 200, 10),
            (2026, 'Firma A', 'Q4', 25, 200, 10)
        """
    )
    _insert_stage1(conn, [("EA1", 200, 0)])
    conn.executemany(
        """
        INSERT INTO plan_existing_orders (year, company, quarter, ea_number, amount, is_fixed, can_stop, note)
        VALUES (2026, 'Firma A', ?, 'EA1', ?, ?, ?, ?)
        """,
        [
            ("Q1", 100, 1, 0, "auto:07_In Planen-BM: Bestellt"),
            ("Q2", 20, 0, 1, "auto:06_In Bearbeitung BM-Team"),
            ("Q4", 60, 1, 0, "auto:07_In Planen-BM: Bestellt"),
        ],
    )
    conn.commit()

    solver.solve_stage2(conn, year=2026, config=_config(), planning_start_quarter=2)

    rows = _rows_by_key(conn)
    assert rows[("Firma A", "Q2", "EA1")] == 20
    assert rows[("Firma A", "Q3", "EA1")] == 20
    assert rows[("Firma A", "Q4", "EA1")] == 60


def test_new_orders_respect_minimum_amount():
    conn = _conn()
    conn.execute(
        """
        INSERT INTO plan_company_targets (year, company, quarter, target_value, annual_target, step_value)
        VALUES
            (2026, 'Firma A', 'Q1', 15000, 15000, 1)
        """
    )
    _insert_stage1(conn, [("EA1", 15000, 0)])
    conn.commit()

    solver.solve_stage2(
        conn,
        year=2026,
        config=solver.SolverConfig(min_new_order_amount=10000),
        planning_start_quarter=1,
    )

    rows = _rows_by_key(conn)
    assert rows == {("Firma A", "Q1", "EA1"): 15000}


def test_new_orders_below_minimum_are_not_created():
    conn = _conn()
    conn.execute(
        """
        INSERT INTO plan_company_targets (year, company, quarter, target_value, annual_target, step_value)
        VALUES
            (2026, 'Firma A', 'Q1', 5000, 5000, 1)
        """
    )
    _insert_stage1(conn, [("EA1", 5000, 0)])
    conn.commit()

    solver.solve_stage2(
        conn,
        year=2026,
        config=solver.SolverConfig(min_new_order_amount=10000),
        planning_start_quarter=1,
    )

    rows = _rows_by_key(conn)
    assert rows == {("Firma A", "Q1", "EA1"): 5000}


def test_special_rules_can_override_minimum_amount_for_required_residuals():
    conn = _conn()
    conn.execute(
        """
        INSERT INTO plan_company_targets (year, company, quarter, target_value, annual_target, step_value)
        VALUES (2026, 'Firma A', 'Q1', 5000, 5000, 1)
        """
    )
    _insert_stage1(conn, [("EA1", 5000, 0)])
    conn.commit()

    rules = [
        {
            "topic": "Sonderregel",
            "ea_keys": {"1"},
            "candidate_eas": {"EA1"},
            "allowed_companies": {"Firma A"},
            "priority_companies": ["Firma A"],
            "target_amount": 5000,
            "period_target_amount": None,
            "enforce_period_exact": False,
        }
    ]

    solver.solve_stage2(
        conn,
        year=2026,
        config=solver.SolverConfig(min_new_order_amount=10000),
        planning_start_quarter=1,
        special_rules=rules,
    )

    rows = _rows_by_key(conn)
    assert rows == {("Firma A", "Q1", "EA1"): 5000}


def test_existing_konzept_rows_prefer_stop_over_small_residuals():
    conn = _conn()
    conn.execute(
        """
        INSERT INTO plan_company_targets (year, company, quarter, target_value, annual_target, step_value)
        VALUES (2026, 'Firma A', 'Q1', 0, 0, 1)
        """
    )
    _insert_stage1(conn, [("EA1", 0, 0)])
    conn.execute(
        """
        INSERT INTO plan_existing_orders (year, company, quarter, ea_number, amount, is_fixed, can_stop, note)
        VALUES (2026, 'Firma A', 'Q1', 'EA1', 37980, 0, 1, 'auto:01_In Erstellung')
        """
    )
    conn.commit()

    solver.solve_stage2(
        conn,
        year=2026,
        config=solver.SolverConfig(
            min_new_order_amount=10000,
        ),
        planning_start_quarter=1,
    )

    rows = _rows_by_key(conn)
    assert rows[("Firma A", "Q1", "EA1")] == 0


def test_existing_small_amount_stays_when_target_requires_it():
    conn = _conn()
    conn.execute(
        """
        INSERT INTO plan_company_targets (year, company, quarter, target_value, annual_target, step_value)
        VALUES (2026, 'Firma A', 'Q1', 5000, 5000, 1)
        """
    )
    _insert_stage1(conn, [("EA1", 5000, 0)])
    conn.execute(
        """
        INSERT INTO plan_existing_orders (year, company, quarter, ea_number, amount, is_fixed, can_stop, note)
        VALUES (2026, 'Firma A', 'Q1', 'EA1', 5000, 0, 1, 'auto:01_In Erstellung')
        """
    )
    conn.commit()

    solver.solve_stage2(
        conn,
        year=2026,
        config=solver.SolverConfig(
            min_new_order_amount=10000,
        ),
        planning_start_quarter=1,
    )

    rows = _rows_by_key(conn)
    assert rows[("Firma A", "Q1", "EA1")] == 5000


def test_non_pmt_period_target_is_enforced():
    """Period targets are enforced for ALL special rules with period_target, not just PMT."""
    conn = _conn()
    conn.execute(
        """
        INSERT INTO plan_company_targets (year, company, quarter, target_value, annual_target, step_value)
        VALUES
            (2026, 'Firma A', 'Q1', 0, 400, 100),
            (2026, 'Firma A', 'Q2', 300, 400, 100),
            (2026, 'Firma A', 'Q3', 50, 400, 100),
            (2026, 'Firma A', 'Q4', 50, 400, 100)
        """
    )
    _insert_stage1(conn, [("EA1", 400, 0)])
    conn.commit()

    rules = [
        {
            "topic": "Digi-budget",
            "ea_keys": {"1"},
            "candidate_eas": {"EA1"},
            "allowed_companies": set(),
            "priority_companies": [],
            "target_amount": 400,
            "period_target_amount": 200,
            "enforce_period_exact": True,
        }
    ]

    solver.solve_stage2(conn, year=2026, config=_config(), planning_start_quarter=2, special_rules=rules)

    totals = conn.execute(
        """
        SELECT quarter, SUM(amount) AS total
        FROM plan_stage2_results
        GROUP BY quarter
        ORDER BY quarter
        """
    ).fetchall()
    quarter_totals = {row["quarter"]: row["total"] for row in totals}
    assert quarter_totals.get("Q1", 0) + quarter_totals.get("Q2", 0) == 200
    assert sum(quarter_totals.values()) == 400


def test_treppenlogik_cumulative_catchup_reduces_overplanned_quarter():
    """When Q1 actual exceeds its target, Q2 effective target shrinks cumulatively."""
    conn = _conn()
    # Annual target 400, split 100/100/100/100. Q1 actual will be 150 (50 over).
    conn.execute(
        """
        INSERT INTO plan_company_targets (year, company, quarter, target_value, annual_target, step_value)
        VALUES
            (2026, 'Firma A', 'Q1', 100, 400, 50),
            (2026, 'Firma A', 'Q2', 100, 400, 50),
            (2026, 'Firma A', 'Q3', 100, 400, 50),
            (2026, 'Firma A', 'Q4', 100, 400, 50)
        """
    )
    _insert_stage1(conn, [("EA1", 400, 0)])
    # Q1 frozen with 150 (50 over target of 100)
    conn.execute(
        """
        INSERT INTO plan_existing_orders (year, company, quarter, ea_number, amount, is_fixed, can_stop, note)
        VALUES (2026, 'Firma A', 'Q1', 'EA1', 150, 1, 0, NULL)
        """
    )
    conn.commit()

    solver.solve_stage2(conn, year=2026, config=_config(), planning_start_quarter=2)

    totals = conn.execute(
        "SELECT quarter, SUM(amount) AS total FROM plan_stage2_results GROUP BY quarter ORDER BY quarter"
    ).fetchall()
    qt = {r["quarter"]: r["total"] for r in totals}
    # Q1 frozen at 150
    assert qt["Q1"] == 150
    # Cumulative Q1-Q2 target = 200, spent 150 → Q2 effective = 50 (not 83 from proportional)
    assert qt["Q2"] == 50
    # Total must still equal annual 400
    assert sum(qt.values()) == 400


def test_large_order_penalty_prefers_two_eas_over_one_double():
    """With large_order_penalty, solver prefers 2 EAs × 1 step over 1 EA × 2 steps."""
    conn = _conn()
    conn.execute(
        """
        INSERT INTO plan_company_targets (year, company, quarter, target_value, annual_target, step_value)
        VALUES (2026, 'Firma A', 'Q1', 100, 100, 50)
        """
    )
    _insert_stage1(conn, [("EA1", 100, 0), ("EA2", 100, 0)])
    conn.commit()

    solver.solve_stage2(
        conn,
        year=2026,
        config=solver.SolverConfig(
            large_order_penalty=700,
            large_order_threshold=50,
            activation_penalty=10,
            quarter_activation_penalty=0,
        ),
        planning_start_quarter=1,
    )

    rows = _rows_by_key(conn)
    allocated = {k: v for k, v in rows.items() if v > 0}
    assert len(allocated) == 2
    assert all(v == 50 for v in allocated.values())


def test_large_order_penalty_zero_allows_double_step():
    """Without large_order_penalty, solver consolidates into fewer positions."""
    conn = _conn()
    conn.execute(
        """
        INSERT INTO plan_company_targets (year, company, quarter, target_value, annual_target, step_value)
        VALUES (2026, 'Firma A', 'Q1', 100, 100, 50)
        """
    )
    _insert_stage1(conn, [("EA1", 100, 0), ("EA2", 100, 0)])
    conn.commit()

    solver.solve_stage2(
        conn,
        year=2026,
        config=solver.SolverConfig(
            large_order_penalty=0,
            activation_penalty=500,
            quarter_activation_penalty=0,
        ),
        planning_start_quarter=1,
    )

    rows = _rows_by_key(conn)
    allocated = {k: v for k, v in rows.items() if v > 0}
    assert len(allocated) == 1
    assert list(allocated.values())[0] == 100


def test_current_period_actuals_truncate_sum_not_per_row():
    """Step truncation must happen on the aggregate sum, not per individual row."""
    conn = _conn()
    # Two orders of 7500 each; step=10000 → sum=15000, truncated=10000
    existing = [
        {"company": "Firma A", "amount": 7500, "note": "auto:07_In Planen-BM: Bestellt"},
        {"company": "Firma A", "amount": 7500, "note": "auto:07_In Planen-BM: Bestellt"},
    ]
    targets = [{"company": "Firma A", "step_value": 10000}]
    result = solver._current_period_company_actuals(existing, targets)
    assert result["Firma A"] == 10000  # sum-then-truncate, not 0+0


def test_load_solver_config_reads_csv_values():
    """CSV rules override dataclass defaults."""
    rules = {
        "stage2_solver": "highs",
        "stage2_activation_penalty": "600",
        "stage2_quarter_activation_penalty": "300",
        "stage2_min_new_order_amount": "5000",
    }
    cfg = solver.load_solver_config(rules)
    assert cfg.activation_penalty == 600.0
    assert cfg.quarter_activation_penalty == 300.0
    assert cfg.min_new_order_amount == 5000
