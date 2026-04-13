"""Shared fixtures for budget reporting tests."""
from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

WORKSPACE = Path(__file__).resolve().parents[1]
TEST_DB = Path(__file__).resolve().parent / "budget_test.db"


@pytest.fixture(scope="session")
def db_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Copy the test DB once per session so tests never mutate the original."""
    dest = tmp_path_factory.mktemp("budget") / "budget_test.db"
    shutil.copy2(TEST_DB, dest)
    return dest


@pytest.fixture()
def conn(db_path: Path) -> sqlite3.Connection:
    """Open a read-only connection with Row factory (per-test)."""
    c = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


@pytest.fixture(scope="session")
def budget_db():
    """Import budget_db module, adding scripts/budget to sys.path."""
    scripts_budget = str(WORKSPACE / "scripts" / "budget")
    if scripts_budget not in sys.path:
        sys.path.insert(0, scripts_budget)
    import budget_db as mod
    return mod


@pytest.fixture(scope="session")
def report_utils():
    """Import report_utils module."""
    scripts_budget = str(WORKSPACE / "scripts" / "budget")
    if scripts_budget not in sys.path:
        sys.path.insert(0, scripts_budget)
    import report_utils as mod
    return mod


@pytest.fixture(scope="session")
def report_bplus(budget_db, report_utils):
    """Import report_bplus module, ensuring its dependencies are on sys.path."""
    skill_dir = str(WORKSPACE / ".agents" / "skills" / "skill-budget-bplus-export")
    if skill_dir not in sys.path:
        sys.path.insert(0, skill_dir)
    import report_bplus as mod
    return mod


@pytest.fixture(scope="session")
def report_el(budget_db, report_utils):
    """Import report_el module."""
    skill_dir = str(WORKSPACE / ".agents" / "skills" / "skill-budget-eigenleistung-el")
    if skill_dir not in sys.path:
        sys.path.insert(0, skill_dir)
    import report_el as mod
    return mod


@pytest.fixture()
def btl_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """All BTL rows from the test DB, ordered like fetch_rows()."""
    return conn.execute(
        "SELECT concept, dev_order, ea, title, planned_value, company, status "
        "FROM btl ORDER BY planned_value DESC, concept"
    ).fetchall()


@pytest.fixture()
def mock_args():
    """Factory to create argparse-like namespace for report_bplus filters."""
    def _make(**kwargs):
        defaults = dict(firma=None, status=None, ea=None, projekt=None, oe=None, top=None, all_org_units=False)
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)
    return _make
