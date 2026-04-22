#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import logging
import sys
from datetime import datetime
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(WORKSPACE / "scripts" / "budget"))

from beauftragungsplanung_core import (  # noqa: E402
    DEFAULT_CONFIG_XLSX,
    PlanningError,
    connect,
    execute_planning,
    init_planning_schema,
)
from planning_config_io import create_default_config  # noqa: E402

LOGS_DIR = WORKSPACE / "userdata" / "tmp" / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
TARGET_IST_SCRIPT = (
    WORKSPACE / ".agents" / "skills" / "skill-budget-target-ist-analyse" / "report_massnahmenplan.py"
)


def setup_logging() -> tuple[logging.Logger, Path]:
    log_path = LOGS_DIR / f"report_beauftragungsplanung_{datetime.now():%Y%m%d_%H%M%S}.log"
    logger = logging.getLogger("beauftragungsplanung")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(formatter)
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(formatter)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger, log_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Beauftragungsplanung auf budget.db")
    parser.add_argument("--jahr", type=int, default=datetime.now().year)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_XLSX))
    parser.add_argument("--output")
    parser.add_argument("--init", action="store_true", help="Planungsschema und Default-Config-Excel anlegen")
    parser.add_argument(
        "--volljahr",
        action="store_true",
        help="Planung fuer das gesamte Jahr erzwingen; vergangene Quartale nicht einfrieren (Debug/Test).",
    )
    parser.add_argument(
        "--sondervorgaben-mode",
        choices=["strict", "catchup"],
        default="catchup",
        help="Behandlung harter Sondervorgaben: strict = Quartals/Halbjahresregel strikt, catchup = Rest nach spaeter verschieben.",
    )
    return parser.parse_args()


def _load_target_ist_module():
    spec = importlib.util.spec_from_file_location("report_massnahmenplan", TARGET_IST_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Target-Ist-Analyse konnte nicht geladen werden: {TARGET_IST_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_target_ist_follow_up(year: int) -> dict[str, str]:
    module = _load_target_ist_module()
    return module.generate_report(year=year, source_table="btl_opt", open_excel=False)


def main() -> int:
    args = parse_args()
    logger, log_path = setup_logging()

    with connect() as conn:
        init_planning_schema(conn)

    config_path = Path(args.config)
    if not config_path.exists() or args.init:
        create_default_config(config_path)

    if args.init:
        print(f"Initialisiert. Config-Excel: {config_path}")
        return 0

    try:
        result, report = execute_planning(
            year=args.jahr,
            config_xlsx=str(config_path),
            output=args.output,
            logger=logger,
            planning_start_quarter=1 if args.volljahr else None,
            sondervorgaben_mode=args.sondervorgaben_mode,
        )
        follow_up = _run_target_ist_follow_up(args.jahr)
        logger.info("Planung erfolgreich. Bericht: %s", report)
        logger.info("btl_opt Zeilen: %s", result.get("btl_opt_rows"))
        logger.info("Target-Ist-Folgeanalyse (Markdown): %s", follow_up["markdown"])
        logger.info("Target-Ist-Folgeanalyse (XLSX): %s", follow_up["xlsx"])
        logger.info("Logdatei: %s", log_path)
        print(report)
        print(follow_up["markdown"])
        print(follow_up["xlsx"])
        return 0
    except PlanningError as exc:
        logger.exception("Planungsfehler")
        print(f"Planungsfehler: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover
        logger.exception("Unerwarteter Fehler")
        print(f"Unerwarteter Fehler: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
