#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import logging
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(WORKSPACE / "scripts" / "budget"))

from budget_db import (  # noqa: E402
    BASE_URL,
    ORG_UNIT_ID,
    connect as budget_connect,
    init_db as budget_init_db,
    sync_btl_all,
    sync_devorder,
    trim,
)
from report_utils import note, report_path, section, table_md, write_report  # noqa: E402


LOGS_DIR = WORKSPACE / "userdata" / "tmp" / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

PLANNING_URL = f"{BASE_URL}/ek/api/PlanningException/UpdatePlanningExceptions"
NOTIFY_SCRIPT = WORKSPACE / "scripts" / "hooks" / "notify.ps1"

MONTH_FIELDS = {
    "jan": "percentInJan",
    "feb": "percentInFeb",
    "mar": "percentInMar",
    "apr": "percentInApr",
    "may": "percentInMay",
    "jun": "percentInJun",
    "jul": "percentInJul",
    "aug": "percentInAug",
    "sep": "percentInSep",
    "oct": "percentInOct",
    "nov": "percentInNov",
    "dec": "percentInDec",
}
MONTH_ORDER = list(MONTH_FIELDS)
MONTH_NUMBERS = {month: idx for idx, month in enumerate(MONTH_ORDER, start=1)}
NUM_TO_MONTH = {idx: month for month, idx in MONTH_NUMBERS.items()}
REFERENCE_PRESETS = {"btl_all_ek"}
MONTH_TOTAL_TARGET = 100.0
MONTH_TOTAL_TOLERANCE = 1e-6
LOCKED_MONTH_BLOCKED_MESSAGE = "Monat ist durch Buchungsrecht gesperrt; nur 0 ist erlaubt"

MONTH_ALIASES = {
    "jan": "jan",
    "january": "jan",
    "januar": "jan",
    "feb": "feb",
    "february": "feb",
    "februar": "feb",
    "mar": "mar",
    "march": "mar",
    "maerz": "mar",
    "märz": "mar",
    "apr": "apr",
    "april": "apr",
    "may": "may",
    "mai": "may",
    "jun": "jun",
    "june": "jun",
    "juni": "jun",
    "jul": "jul",
    "july": "jul",
    "juli": "jul",
    "aug": "aug",
    "august": "aug",
    "sep": "sep",
    "sept": "sep",
    "september": "sep",
    "oct": "oct",
    "okt": "oct",
    "october": "oct",
    "oktober": "oct",
    "nov": "nov",
    "november": "nov",
    "dec": "dec",
    "dez": "dec",
    "december": "dec",
    "dezember": "dec",
}


RUN_TS = datetime.now()
RUN_ID = uuid.uuid4().hex[:8]


def setup_logging() -> Path:
    log_path = LOGS_DIR / f"el_change_{RUN_TS:%Y%m%d_%H%M%S}_{RUN_ID}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler(sys.stderr)],
    )
    return log_path


LOG_PATH = setup_logging()


class ElChangeError(RuntimeError):
    pass


@dataclass
class RunResult:
    path: Path
    notify_message: str
    mode: str = "dryrun"
    readback: str = "n/a"
    changes: int = 0
    blocked: int = 0
    run_id: str = ""
    error: str = ""


@dataclass
class PlannedOperation:
    ea: str
    mode: str
    months: list[str]
    value: float
    reason: str
    require_open: bool = False


@dataclass
class EntryChange:
    ea: str
    description: str
    reason: str
    changed: dict[str, tuple[int | float, int | float]] = field(default_factory=dict)
    blocked: dict[str, str] = field(default_factory=dict)

    def has_effect(self) -> bool:
        return bool(self.changed or self.blocked)


@dataclass
class UserExecution:
    user_name: str
    operations: list[EntryChange]
    before_totals: dict[str, int | float]
    after_totals: dict[str, int | float]
    expected: dict[str, dict[str, int | float]]
    verification_ok: bool | None
    verification_errors: list[str] | None

    @property
    def changed_month_count(self) -> int:
        return sum(len(op.changed) for op in self.operations)


def current_now() -> datetime:
    return datetime.now()


def _normalize(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def _coerce_percentage(value: float) -> int | float:
    if value < 0 or value > 100:
        raise ElChangeError("Prozentwert muss zwischen 0 und 100 liegen.")
    return int(value) if float(value).is_integer() else value


def _is_zero_percentage(value: int | float) -> bool:
    return abs(float(value)) <= MONTH_TOTAL_TOLERANCE


def _powershell_json(method: str, url: str, payload: object | None = None, timeout: int = 180):
    temp_paths: list[Path] = []
    cmd_parts = [
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8",
        f"$method = '{method.upper()}'",
        f"$url = '{url}'",
        f"$timeout = {int(timeout)}",
        "$params = @{ Uri = $url; Method = $method; UseDefaultCredentials = $true; TimeoutSec = $timeout }",
    ]
    if payload is not None:
        payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
            handle.write(payload_json)
            payload_path = Path(handle.name)
        temp_paths.append(payload_path)
        cmd_parts.extend(
            [
                f"$json = Get-Content -LiteralPath '{payload_path}' -Raw -Encoding UTF8",
                "$params['ContentType'] = 'application/json; charset=utf-8'",
                "$params['Body'] = $json",
            ]
        )
    cmd_parts.extend(
        [
            "$resp = Invoke-RestMethod @params",
            "if ($null -eq $resp) { '' } else { $resp | ConvertTo-Json -Depth 25 -Compress }",
        ]
    )
    cmd = "; ".join(cmd_parts)
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True,
            text=True,
        )
    finally:
        for path in temp_paths:
            path.unlink(missing_ok=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise ElChangeError(detail or f"PowerShell request failed: {method} {url}")
    stdout = result.stdout.strip()
    if not stdout:
        return None
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return stdout


def fetch_employee_hours(year: int, org_unit_id: int = ORG_UNIT_ID):
    return _powershell_json("GET", f"{BASE_URL}/ek/api/EmployeeHours?orgUnitId={org_unit_id}&year={year}")


def fetch_roles():
    return _powershell_json("GET", f"{BASE_URL}/ek/api/Role/GetCurrentUserRoles") or []


def fetch_planning(user_id: int, year: int, org_unit_id: int = ORG_UNIT_ID):
    return _powershell_json(
        "GET",
        f"{BASE_URL}/ek/api/PlanningException/GetPlanningExceptionsForUser?userId={user_id}&year={year}&orgUnitId={org_unit_id}",
        timeout=180,
    )


def post_planning_update(payload: dict):
    return _powershell_json("POST", PLANNING_URL, payload=payload, timeout=180)


def parse_months(months_raw: str | None, *, all_months: bool = False) -> list[str]:
    if all_months:
        return MONTH_ORDER.copy()
    if not months_raw:
        raise ElChangeError("--months oder --all-months ist erforderlich.")
    parsed: list[str] = []
    for token in months_raw.split(","):
        normalized = MONTH_ALIASES.get(_normalize(token))
        if not normalized:
            raise ElChangeError(f"Unbekannter Monat: {token.strip()}")
        if normalized not in parsed:
            parsed.append(normalized)
    if not parsed:
        raise ElChangeError("Keine gueltigen Monate angegeben.")
    return parsed


def parse_month(month_raw: str | None) -> str | None:
    if month_raw is None:
        return None
    normalized = MONTH_ALIASES.get(_normalize(month_raw))
    if not normalized:
        raise ElChangeError(f"Unbekannter Monat: {month_raw}")
    return normalized


def parse_adjustment_specs(items: list[str] | None, *, sign: int) -> list[tuple[str, int]]:
    parsed: list[tuple[str, int]] = []
    for item in items or []:
        if "=" not in item:
            raise ElChangeError(f"Ungültiges EA-Delta: {item}. Erwartet EA=Wert")
        ea, raw_value = item.split("=", 1)
        ea = trim(ea)
        if not ea:
            raise ElChangeError(f"EA fehlt in Delta-Spezifikation: {item}")
        try:
            value = int(float(raw_value.strip()))
        except ValueError as exc:
            raise ElChangeError(f"Ungültiger Delta-Wert in {item}") from exc
        if value < 0:
            raise ElChangeError(f"Delta-Wert muss positiv angegeben werden: {item}")
        parsed.append((ea, sign * value))
    return parsed


def month_values(entry: dict) -> dict[str, int | float]:
    return {month: entry.get(field, 0) for month, field in MONTH_FIELDS.items()}


def apply_month_changes(entry: dict, months: list[str], value: int | float) -> tuple[dict, dict]:
    before = month_values(entry)
    for month in months:
        entry[MONTH_FIELDS[month]] = value
    after = month_values(entry)
    return before, after


def verify_months(entry: dict, expected: dict[str, int | float]) -> tuple[bool, list[str]]:
    mismatches = []
    actual = month_values(entry)
    for month, expected_value in expected.items():
        if actual.get(month) != expected_value:
            mismatches.append(f"{month}: expected {expected_value}, got {actual.get(month)}")
    return (not mismatches), mismatches


def collect_users(employee_hours: dict) -> list[dict]:
    users: list[dict] = []
    if not isinstance(employee_hours, dict):
        return users
    for bucket, entries in employee_hours.items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict):
                item = dict(entry)
                item["_bucket"] = bucket
                users.append(item)
    return users


def resolve_user(employee_hours: dict, query: str) -> dict:
    users = collect_users(employee_hours)
    if not users:
        raise ElChangeError("Keine Mitarbeiterdaten verfuegbar.")
    normalized_query = _normalize(query)
    exact = [u for u in users if _normalize(u.get("userFullName")) == normalized_query]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise ElChangeError(f"Mitarbeiter nicht eindeutig: {query}")
    partial = [u for u in users if normalized_query in _normalize(u.get("userFullName"))]
    if len(partial) == 1:
        return partial[0]
    if not partial:
        raise ElChangeError(f"Kein Mitarbeiter gefunden: {query}")
    names = ", ".join(trim(u.get("userFullName")) for u in partial[:8])
    raise ElChangeError(f"Mitarbeiter nicht eindeutig: {query}. Treffer: {names}")


def resolve_entry(planning: dict, ea_query: str) -> tuple[int, dict]:
    entries = planning.get("planningExceptions") or []
    normalized_query = _normalize(ea_query)
    exact_number = [item for item in entries if _normalize(item.get("number")) == normalized_query]
    if len(exact_number) == 1:
        entry = exact_number[0]
        return entries.index(entry), entry
    if len(exact_number) > 1:
        raise ElChangeError(f"EA nicht eindeutig: {ea_query}")
    partial = [
        item
        for item in entries
        if normalized_query in _normalize(item.get("description"))
        or normalized_query in _normalize(item.get("devOrderDescription"))
    ]
    if len(partial) == 1:
        entry = partial[0]
        return entries.index(entry), entry
    if not partial:
        raise ElChangeError(f"Kein EA gefunden: {ea_query}")
    labels = ", ".join(trim(item.get("number")) for item in partial[:8])
    raise ElChangeError(f"EA nicht eindeutig: {ea_query}. Treffer: {labels}")


def load_batch_users(args: argparse.Namespace) -> list[str]:
    users = list(args.mitarbeiter or [])
    if args.mitarbeiter_file:
        path = Path(args.mitarbeiter_file)
        if not path.exists():
            raise ElChangeError(f"Mitarbeiter-Datei nicht gefunden: {path}")
        for line in path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if text and not text.startswith("#"):
                users.append(text)
    if not users:
        raise ElChangeError("Mindestens ein --mitarbeiter oder --mitarbeiter-file ist erforderlich.")
    deduped: list[str] = []
    seen = set()
    for user in users:
        key = _normalize(user)
        if key and key not in seen:
            deduped.append(user)
            seen.add(key)
    return deduped


def compute_default_start_month(year: int) -> str:
    now = current_now()
    if year < now.year:
        raise ElChangeError("Vergangene Jahre sind nicht aenderbar.")
    if year > now.year:
        return "jan"
    return NUM_TO_MONTH[now.month]


def compute_month_window(
    *,
    year: int,
    from_month: str | None,
    to_month: str | None,
) -> list[str]:
    start = parse_month(from_month) or compute_default_start_month(year)
    end = parse_month(to_month) or "dec"
    start_num = MONTH_NUMBERS[start]
    end_num = MONTH_NUMBERS[end]
    if start_num > end_num:
        raise ElChangeError("--from-month darf nicht hinter --to-month liegen.")
    return [month for month in MONTH_ORDER if start_num <= MONTH_NUMBERS[month] <= end_num]


def filter_editable_months(
    months: list[str],
    *,
    year: int,
) -> tuple[list[str], dict[str, str]]:
    editable = set(compute_month_window(year=year, from_month=None, to_month=None))
    allowed = [month for month in months if month in editable]
    blocked = {month: "Vergangener Monat ausserhalb des aenderbaren Fensters" for month in months if month not in editable}
    return allowed, blocked


def entry_lock_months(entry: dict) -> set[int]:
    raw = entry.get("bookingRightsExceptionsMonths") or []
    return {int(item) for item in raw if str(item).strip()}


def get_month_total(planning: dict, month: str) -> float:
    return float(sum(float(entry.get(MONTH_FIELDS[month], 0) or 0) for entry in planning.get("planningExceptions") or []))


def monthly_totals(planning: dict) -> dict[str, int | float]:
    return {month: get_month_total(planning, month) for month in MONTH_ORDER}


def _format_number(value: int | float) -> str:
    numeric = float(value)
    rounded = round(numeric)
    if abs(numeric - rounded) <= MONTH_TOTAL_TOLERANCE:
        return str(int(rounded))
    return f"{numeric:.4f}".rstrip("0").rstrip(".")


def find_invalid_month_totals(planning: dict, months: list[str]) -> dict[str, float]:
    invalid: dict[str, float] = {}
    for month in months:
        total = get_month_total(planning, month)
        if abs(total - MONTH_TOTAL_TARGET) > MONTH_TOTAL_TOLERANCE:
            invalid[month] = total
    return invalid


def invalid_month_total_lines(planning: dict, months: list[str]) -> list[str]:
    invalid = find_invalid_month_totals(planning, months)
    return [f"{month.upper()}={_format_number(total)}" for month, total in sorted(invalid.items(), key=lambda item: MONTH_NUMBERS[item[0]])]


def ensure_month_totals(planning: dict, months: list[str], *, context: str) -> None:
    lines = invalid_month_total_lines(planning, months)
    if lines:
        raise ElChangeError(f"{context}: Monatssumme muss fuer alle betroffenen Monate 100 sein. Abweichungen: {', '.join(lines)}")


def compute_annual_shares(planning: dict) -> dict[str, float]:
    totals: dict[str, float] = {}
    grand_total = 0.0
    for entry in planning.get("planningExceptions") or []:
        ea = trim(entry.get("number"))
        month_sum = float(sum(float(entry.get(field, 0) or 0) for field in MONTH_FIELDS.values()))
        totals[ea] = month_sum
        grand_total += month_sum
    if grand_total == 0:
        return {ea: 0.0 for ea in totals}
    return {ea: 100.0 * value / grand_total for ea, value in totals.items()}


def load_reference_shares(
    year: int,
    *,
    preset: str,
    org_like: str | None = None,
    include_status_tokens: list[str] | None = None,
    exclude_status_tokens: list[str] | None = None,
) -> dict[str, float]:
    if preset not in REFERENCE_PRESETS:
        raise ElChangeError(f"Unbekanntes Referenz-Preset: {preset}")
    with budget_connect() as conn:
        budget_init_db(conn)
        sync_btl_all(conn, year, force=True)
        default_org = "EK%"
        org_filter = org_like or default_org
        sql = [
            "WITH ref AS (",
            "  SELECT dev_order AS ea_number, SUM(planned_value) AS fl_value",
            "  FROM btl_all",
            "  WHERE org_unit LIKE ?",
            "    AND COALESCE(planned_value, 0) > 0",
            "    AND TRIM(COALESCE(dev_order, '')) <> ''",
            "    AND status NOT LIKE '97_%'",
            "    AND status NOT LIKE '98_%'",
            "    AND LOWER(status) NOT LIKE '%abgelehnt%'",
        ]
        params: list[object] = [org_filter]
        include_tokens = [token.strip().lower() for token in (include_status_tokens or []) if token.strip()]
        exclude_tokens = [token.strip().lower() for token in (exclude_status_tokens or []) if token.strip()]
        if include_tokens:
            sql.append("    AND (" + " OR ".join("LOWER(status) LIKE ?" for _ in include_tokens) + ")")
            params.extend(f"%{token}%" for token in include_tokens)
        for token in exclude_tokens:
            sql.append("    AND LOWER(status) NOT LIKE ?")
            params.append(f"%{token}%")
        sql.extend(
            [
                "  GROUP BY dev_order",
                "), total AS (",
                "  SELECT SUM(fl_value) AS total_fl FROM ref",
                ")",
                "SELECT ea_number, CASE WHEN total_fl IS NULL OR total_fl = 0 THEN 0 ELSE 100.0 * fl_value / total_fl END AS ref_share_pct",
                "FROM ref CROSS JOIN total",
            ]
        )
        rows = conn.execute("\n".join(sql), params).fetchall()
    return {trim(row["ea_number"]): float(row["ref_share_pct"] or 0.0) for row in rows}


def load_devorder_map(year: int) -> dict[str, dict]:
    with budget_connect() as conn:
        budget_init_db(conn)
        sync_devorder(conn, year, force=True)
        rows = conn.execute(
            "SELECT ea_number, title, active, date_from, date_until, project_family, controller FROM devorder"
        ).fetchall()
    return {trim(row["ea_number"]): dict(row) for row in rows}


def is_open_devorder(devorder_row: dict | None, *, year: int) -> bool:
    if not devorder_row:
        return False
    if int(devorder_row.get("active") or 0) != 1:
        return False
    date_until = trim(devorder_row.get("date_until"))
    if not date_until:
        return True
    try:
        until = datetime.fromisoformat(date_until).date()
    except ValueError:
        return True
    return until >= current_now().date()


def notify_result(status: str, message: str, *, title: str = "EL Change", no_popup: bool = False) -> None:
    if not NOTIFY_SCRIPT.exists():
        logging.warning("notify.ps1 nicht gefunden: %s", NOTIFY_SCRIPT)
        return
    cmd = [
        "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(NOTIFY_SCRIPT),
        "-Status",
        status,
        "-Message",
        message,
        "-Title",
        title,
    ]
    if no_popup:
        cmd.append("-NoPopup")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logging.warning("notify.ps1 fehlgeschlagen: %s", (result.stderr or result.stdout).strip())


def build_operation_lists(args: argparse.Namespace, months: list[str]) -> tuple[list[PlannedOperation], bool]:
    operations: list[PlannedOperation] = []
    for ea in args.zero_ea or []:
        operations.append(PlannedOperation(ea=ea, mode="set", months=months, value=0, reason="zero-ea", require_open=False))
    for ea, delta in parse_adjustment_specs(args.increase_ea, sign=1):
        operations.append(PlannedOperation(ea=ea, mode="delta", months=months, value=delta, reason="increase-ea", require_open=True))
    for ea, delta in parse_adjustment_specs(args.decrease_ea, sign=-1):
        operations.append(PlannedOperation(ea=ea, mode="delta", months=months, value=delta, reason="decrease-ea", require_open=True))
    if args.rebalance is None:
        do_rebalance = bool(args.zero_ea)
    else:
        do_rebalance = bool(args.rebalance)
    return operations, do_rebalance


def _set_month(entry: dict, month: str, value: int | float) -> None:
    entry[MONTH_FIELDS[month]] = value


def _apply_operation_to_entry(
    entry: dict,
    operation: PlannedOperation,
    *,
    year: int,
    require_open_devorder: bool,
    devorder_row: dict | None,
) -> EntryChange:
    allowed_months, blocked_by_window = filter_editable_months(operation.months, year=year)
    result = EntryChange(
        ea=trim(entry.get("number")),
        description=trim(entry.get("description")),
        reason=operation.reason,
    )
    result.blocked.update(blocked_by_window)
    if operation.require_open and require_open_devorder and not is_open_devorder(devorder_row, year=year):
        for month in allowed_months:
            result.blocked[month] = "EA ist nicht offen/aktiv"
        return result
    locks = entry_lock_months(entry)
    for month in allowed_months:
        before = float(entry.get(MONTH_FIELDS[month], 0) or 0)
        if operation.mode == "set":
            after = _coerce_percentage(operation.value)
        elif operation.mode == "delta":
            after = _coerce_percentage(before + operation.value)
        else:
            raise ElChangeError(f"Unbekannter Operationsmodus: {operation.mode}")
        month_num = MONTH_NUMBERS[month]
        if month_num in locks and not _is_zero_percentage(after):
            result.blocked[month] = LOCKED_MONTH_BLOCKED_MESSAGE
            continue
        if before == after:
            continue
        _set_month(entry, month, after)
        result.changed[month] = (before, after)
    return result


def _build_entry_map(planning: dict) -> dict[str, dict]:
    return {trim(entry.get("number")): entry for entry in planning.get("planningExceptions") or []}


def _add_expected(expected: dict[str, dict[str, int | float]], change: EntryChange) -> None:
    if not change.changed:
        return
    per_ea = expected.setdefault(change.ea, {})
    for month, (_, after) in change.changed.items():
        per_ea[month] = after


def _candidate_sort_key(item: dict) -> tuple:
    return (item["gap_vs_ref"] > 0, item["gap_vs_ref"], item["ref_share"], -item["current_value"], item["ea"])


def _apply_rebalance(
    planning: dict,
    *,
    months: list[str],
    year: int,
    devorder_map: dict[str, dict],
    require_open_devorder: bool,
    reference_shares: dict[str, float],
    max_step_per_ea_per_month: int,
    fill_strategy: str,
    protected_eas_by_month: dict[str, set[str]],
) -> tuple[list[EntryChange], dict[str, dict[str, int | float]]]:
    base_shares = compute_annual_shares(planning)
    entry_map = _build_entry_map(planning)
    results: list[EntryChange] = []
    expected: dict[str, dict[str, int | float]] = {}
    for month in months:
        allowed, _ = filter_editable_months([month], year=year)
        if not allowed:
            continue
        current_total = get_month_total(planning, month)
        deficit = int(round(100.0 - current_total))
        if deficit <= 0:
            continue
        candidates = []
        for ea, entry in entry_map.items():
            current_value = float(entry.get(MONTH_FIELDS[month], 0) or 0)
            if current_value <= 0:
                continue
            if ea in protected_eas_by_month.get(month, set()):
                continue
            if MONTH_NUMBERS[month] in entry_lock_months(entry):
                continue
            if require_open_devorder and not is_open_devorder(devorder_map.get(ea), year=year):
                continue
            gap_vs_ref = reference_shares.get(ea, 0.0) - base_shares.get(ea, 0.0)
            if fill_strategy == "strict-underweight" and gap_vs_ref <= 0:
                continue
            candidates.append(
                {
                    "ea": ea,
                    "entry": entry,
                    "current_value": current_value,
                    "ref_share": reference_shares.get(ea, 0.0),
                    "user_share": base_shares.get(ea, 0.0),
                    "gap_vs_ref": gap_vs_ref,
                }
            )
        candidates.sort(key=_candidate_sort_key, reverse=True)
        if max_step_per_ea_per_month < 1:
            raise ElChangeError("--max-step-per-ea-per-month muss mindestens 1 sein.")
        remaining = deficit
        for candidate in candidates:
            if remaining <= 0:
                break
            entry = candidate["entry"]
            before = float(entry.get(MONTH_FIELDS[month], 0) or 0)
            step = min(max_step_per_ea_per_month, remaining)
            after = _coerce_percentage(before + step)
            _set_month(entry, month, after)
            change = EntryChange(
                ea=candidate["ea"],
                description=trim(entry.get("description")),
                reason=f"rebalance ({fill_strategy})",
                changed={month: (before, after)},
            )
            results.append(change)
            _add_expected(expected, change)
            remaining -= step
    return results, expected


def _verify_expected(
    refreshed: dict,
    expected: dict[str, dict[str, int | float]],
    *,
    months_to_validate: list[str] | None = None,
) -> tuple[bool, list[str]]:
    if not expected and not months_to_validate:
        return True, []
    refreshed_map = _build_entry_map(refreshed)
    mismatches: list[str] = []
    for ea, months in expected.items():
        entry = refreshed_map.get(ea)
        if not entry:
            mismatches.append(f"{ea}: im Readback nicht gefunden")
            continue
        ok, lines = verify_months(entry, months)
        if not ok:
            mismatches.extend(f"{ea} {line}" for line in lines)
    for line in invalid_month_total_lines(refreshed, months_to_validate or []):
        mismatches.append(f"Monatssumme nicht 100: {line}")
    return (not mismatches), mismatches


def _render_change_rows(change: EntryChange) -> list[list[object]]:
    rows: list[list[object]] = []
    for month in sorted(change.changed, key=lambda item: MONTH_NUMBERS[item]):
        before, after = change.changed[month]
        rows.append([change.ea, change.description, change.reason, month.upper(), before, after, "geaendert"])
    for month in sorted(change.blocked, key=lambda item: MONTH_NUMBERS[item]):
        rows.append([change.ea, change.description, change.reason, month.upper(), "-", "-", f"blockiert: {change.blocked[month]}"])
    return rows


def write_single_report(
    *,
    command: str,
    mitarbeiter: dict,
    entry: dict,
    months: list[str],
    before: dict[str, int | float],
    after: dict[str, int | float],
    apply: bool,
    roles: list[dict],
    verification_ok: bool | None,
    verification_errors: list[str] | None,
    blocked_months: dict[str, str],
    output: str | None,
) -> Path:
    mode_label = "apply" if apply else "dryrun"
    path = report_path(
        "el_change",
        label=f"{command}_{mode_label}_{trim(mitarbeiter.get('userFullName'))}_{trim(entry.get('number'))}",
        output=output,
    )
    role_rows = [[trim(item.get("roleName")), trim(item.get("orgUnit"))] for item in roles]
    delta_rows = []
    changed_count = 0
    for month in MONTH_ORDER:
        if month in months or before[month] != after[month] or month in blocked_months:
            status = blocked_months.get(month, "")
            delta_rows.append([month.upper(), before[month], after[month], status])
            if before[month] != after[month]:
                changed_count += 1
    blocked_count = len(blocked_months)
    readback = "n/a" if not apply else ("ok" if verification_ok else "failed")
    status_rows = [[
        "apply" if apply else "dry-run",
        readback,
        changed_count,
        blocked_count,
        f"{trim(mitarbeiter.get('userFullName'))} / {trim(entry.get('number'))}",
        RUN_ID,
        RUN_TS.strftime("%Y-%m-%d %H:%M:%S"),
    ]]
    sections = [
        section(
            "Status",
            table_md(status_rows, ["Modus", "Readback", "Aenderungen", "Blockiert", "Ziel", "run_id", "Erstellt"]),
        ),
        note(f"Logdatei: {LOG_PATH}"),
        section(
            "Kontext",
            table_md(
                [[
                    command,
                    "apply" if apply else "dry-run",
                    trim(mitarbeiter.get("userFullName")),
                    trim(mitarbeiter.get("_bucket")),
                    trim(entry.get("number")),
                    trim(entry.get("description")),
                ]],
                ["Befehl", "Modus", "Mitarbeiter", "Bucket", "EA", "Beschreibung"],
            ),
        ),
        section("Monatswerte", table_md(delta_rows, ["Monat", "Alt", "Neu", "Hinweis"])),
        section("Rollen", table_md(role_rows, ["Rolle", "OE"])),
        section("Technik", table_md([[PLANNING_URL]], ["Write-Endpoint"])),
    ]
    if apply:
        verify_body = "Readback erfolgreich." if verification_ok else "Readback fehlgeschlagen.\n\n" + "\n".join(f"- {line}" for line in (verification_errors or []))
        sections.append(section("Verifikation", verify_body))
    else:
        sections.append(section("Verifikation", "Kein Write ausgefuehrt (dry-run)."))
    write_report(path, f"EL-Aenderung: {command}", sections)
    return path


def write_plan_report(
    *,
    summaries: list[UserExecution],
    apply: bool,
    roles: list[dict],
    output: str | None,
    reference_preset: str | None,
    month_window: list[str],
) -> Path:
    mode_label = "apply" if apply else "dryrun"
    path = report_path("el_change", label=f"plan_changes_{mode_label}", output=output)
    role_rows = [[trim(item.get("roleName")), trim(item.get("orgUnit"))] for item in roles] or [["-", "-"]]
    changes_total = sum(summary.changed_month_count for summary in summaries)
    blocked_total = sum(
        sum(len(op.blocked) for op in summary.operations) for summary in summaries
    )
    if not apply:
        readback = "n/a"
    elif all(summary.verification_ok for summary in summaries):
        readback = "ok"
    else:
        readback = "failed"
    status_rows = [[
        "apply" if apply else "dry-run",
        readback,
        changes_total,
        blocked_total,
        len(summaries),
        RUN_ID,
        RUN_TS.strftime("%Y-%m-%d %H:%M:%S"),
    ]]
    sections = [
        section(
            "Status",
            table_md(status_rows, ["Modus", "Readback", "Aenderungen", "Blockiert", "Mitarbeiter", "run_id", "Erstellt"]),
        ),
        note(f"Logdatei: {LOG_PATH}"),
        section(
            "Kontext",
            table_md(
                [[
                    "apply" if apply else "dry-run",
                    ",".join(month.upper() for month in month_window),
                    reference_preset or "-",
                    len(summaries),
                ]],
                ["Modus", "Monate", "Referenz", "Mitarbeiter"],
            ),
        ),
        section("Rollen", table_md(role_rows, ["Rolle", "OE"])),
    ]
    for summary in summaries:
        total_rows = [
            [month.upper(), summary.before_totals[month], summary.after_totals[month]]
            for month in MONTH_ORDER
            if month in summary.before_totals
        ]
        change_rows: list[list[object]] = []
        for item in summary.operations:
            change_rows.extend(_render_change_rows(item))
        if not change_rows:
            change_rows = [["-", "-", "-", "-", "-", "-", "Keine Änderungen"]]
        verify_body = "Readback erfolgreich." if apply and summary.verification_ok else (
            "Readback fehlgeschlagen.\n\n" + "\n".join(f"- {line}" for line in (summary.verification_errors or []))
            if apply
            else "Kein Write ausgefuehrt (dry-run)."
        )
        sections.append(
            section(
                f"Mitarbeiter: {summary.user_name}",
                table_md(total_rows, ["Monat", "Vorher Summe", "Nachher Summe"])
                + "\n"
                + table_md(change_rows, ["EA", "Beschreibung", "Grund", "Monat", "Alt", "Neu", "Status"])
                + "\n"
                + verify_body,
            )
        )
    write_report(path, "EL-Aenderung: plan-changes", sections)
    return path


def build_notify_message(args: argparse.Namespace, result: RunResult) -> str:
    return result.notify_message


def run_single_change(args: argparse.Namespace) -> RunResult:
    roles = fetch_roles()
    if not isinstance(roles, list):
        roles = []
    employee_hours = fetch_employee_hours(args.year, args.org_unit_id)
    user = resolve_user(employee_hours, args.mitarbeiter)
    user_id = user.get("idxUser")
    if not user_id:
        raise ElChangeError(f"idxUser fehlt fuer Mitarbeiter: {trim(user.get('userFullName'))}")

    planning = fetch_planning(int(user_id), args.year, args.org_unit_id)
    payload = copy.deepcopy(planning)
    entry_index, _ = resolve_entry(payload, args.ea)
    target = payload["planningExceptions"][entry_index]

    months = MONTH_ORDER.copy() if args.command == "reset-ea" else parse_months(args.months, all_months=args.all_months)
    value = 0 if args.command == "reset-ea" else _coerce_percentage(args.value)
    before = month_values(target)
    operation = PlannedOperation(
        ea=trim(target.get("number")),
        mode="set",
        months=months,
        value=value,
        reason=args.command,
        require_open=False,
    )
    change = _apply_operation_to_entry(
        target,
        operation,
        year=args.year,
        require_open_devorder=False,
        devorder_row=None,
    )
    blocked = dict(change.blocked)
    after = month_values(target)
    ensure_month_totals(
        payload,
        months,
        context=f"Zielplanung fuer {trim(user.get('userFullName'))} / {trim(target.get('number'))}",
    )

    verification_ok = None
    verification_errors: list[str] | None = None
    expected = {month: after[month] for month in months if before[month] != after[month]}
    if args.apply and expected:
        logging.info("Sende UpdatePlanningExceptions fuer %s / %s", trim(user.get("userFullName")), trim(target.get("number")))
        post_planning_update(payload)
        refreshed = fetch_planning(int(user_id), args.year, args.org_unit_id)
        _, refreshed_entry = resolve_entry(refreshed, trim(target.get("number")))
        verification_ok, verification_errors = verify_months(refreshed_entry, expected)
        verification_errors = list(verification_errors or [])
        verification_errors.extend(f"Monatssumme nicht 100: {line}" for line in invalid_month_total_lines(refreshed, months))
        verification_ok = not verification_errors
        if not verification_ok:
            raise ElChangeError("Readback-Verifikation fehlgeschlagen: " + "; ".join(verification_errors or []))
    elif args.apply:
        logging.info("Kein Write noetig, da keine Aenderung entstanden ist.")

    path = write_single_report(
        command=args.command,
        mitarbeiter=user,
        entry=target,
        months=months,
        before=before,
        after=after,
        apply=args.apply,
        roles=roles,
        verification_ok=verification_ok,
        verification_errors=verification_errors,
        blocked_months=blocked,
        output=args.output,
    )
    mode = "Apply" if args.apply else "Dry-run"
    changed_count = sum(1 for month in MONTH_ORDER if before[month] != after[month])
    readback = "n/a" if not args.apply else ("ok" if verification_ok else "failed")
    return RunResult(
        path=path,
        notify_message=f"{mode} erfolgreich fuer {trim(user.get('userFullName'))} / {trim(target.get('number'))}. Report: {path}",
        mode="apply" if args.apply else "dryrun",
        readback=readback,
        changes=changed_count,
        blocked=len(blocked),
        run_id=RUN_ID,
    )


def run_plan_changes(args: argparse.Namespace) -> RunResult:
    roles = fetch_roles()
    if not isinstance(roles, list):
        roles = []
    users = load_batch_users(args)
    employee_hours = fetch_employee_hours(args.year, args.org_unit_id)
    month_window = compute_month_window(
        year=args.year,
        from_month=args.from_month,
        to_month=args.to_month,
    )
    manual_operations, do_rebalance = build_operation_lists(args, month_window)
    reference_shares = {}
    devorder_map = {}
    if do_rebalance:
        reference_shares = load_reference_shares(
            args.year,
            preset=args.reference_preset,
            org_like=args.reference_org_like,
            include_status_tokens=args.reference_include_status,
            exclude_status_tokens=args.reference_exclude_status,
        )
        devorder_map = load_devorder_map(args.year)
    elif args.require_open_devorder:
        devorder_map = load_devorder_map(args.year)

    summaries: list[UserExecution] = []
    for user_query in users:
        user = resolve_user(employee_hours, user_query)
        user_id = user.get("idxUser")
        if not user_id:
            raise ElChangeError(f"idxUser fehlt fuer Mitarbeiter: {trim(user.get('userFullName'))}")
        planning = fetch_planning(int(user_id), args.year, args.org_unit_id)
        payload = copy.deepcopy(planning)
        before_totals = monthly_totals(planning)
        entry_map = _build_entry_map(payload)
        operations: list[EntryChange] = []
        expected: dict[str, dict[str, int | float]] = {}
        protected_eas_by_month: dict[str, set[str]] = {}
        for operation in manual_operations:
            ea = trim(operation.ea)
            entry = entry_map.get(ea)
            if not entry:
                if operation.reason == "zero-ea":
                    blocked = {month: "EA nicht im bestehenden Plan gefunden" for month in operation.months}
                    operations.append(
                        EntryChange(
                            ea=ea,
                            description=ea,
                            reason=operation.reason,
                            blocked=blocked,
                        )
                    )
                    continue
                raise ElChangeError(f"EA nicht im bestehenden Plan gefunden: {operation.ea} bei {trim(user.get('userFullName'))}")
            change = _apply_operation_to_entry(
                entry,
                operation,
                year=args.year,
                require_open_devorder=args.require_open_devorder,
                devorder_row=devorder_map.get(ea),
            )
            if change.has_effect():
                operations.append(change)
                _add_expected(expected, change)
                if operation.reason == "zero-ea":
                    for month in change.changed:
                        protected_eas_by_month.setdefault(month, set()).add(ea)
        if do_rebalance:
            rebalance_changes, rebalance_expected = _apply_rebalance(
                payload,
                months=month_window,
                year=args.year,
                devorder_map=devorder_map,
                require_open_devorder=args.require_open_devorder,
                reference_shares=reference_shares,
                max_step_per_ea_per_month=args.max_step_per_ea_per_month,
                fill_strategy=args.fill_strategy,
                protected_eas_by_month=protected_eas_by_month,
            )
            operations.extend(rebalance_changes)
            for ea, months in rebalance_expected.items():
                expected.setdefault(ea, {}).update(months)
        ensure_month_totals(
            payload,
            month_window,
            context=f"Zielplanung fuer {trim(user.get('userFullName'))}",
        )
        verification_ok = None
        verification_errors: list[str] | None = None
        if args.apply and expected:
            logging.info("Sende UpdatePlanningExceptions fuer %s (%s Aenderungsmonate)", trim(user.get("userFullName")), sum(len(v) for v in expected.values()))
            post_planning_update(payload)
            refreshed = fetch_planning(int(user_id), args.year, args.org_unit_id)
            verification_ok, verification_errors = _verify_expected(
                refreshed,
                expected,
                months_to_validate=month_window,
            )
            if not verification_ok:
                raise ElChangeError(
                    f"Readback-Verifikation fehlgeschlagen fuer {trim(user.get('userFullName'))}: " + "; ".join(verification_errors or [])
                )
        elif args.apply:
            logging.info("Kein Write noetig fuer %s", trim(user.get("userFullName")))
        summaries.append(
            UserExecution(
                user_name=trim(user.get("userFullName")),
                operations=operations,
                before_totals=before_totals,
                after_totals=monthly_totals(payload),
                expected=expected,
                verification_ok=verification_ok,
                verification_errors=verification_errors,
            )
        )

    path = write_plan_report(
        summaries=summaries,
        apply=args.apply,
        roles=roles,
        output=args.output,
        reference_preset=args.reference_preset if do_rebalance else None,
        month_window=month_window,
    )
    changed_months = sum(summary.changed_month_count for summary in summaries)
    blocked_months_count = sum(
        sum(len(op.blocked) for op in summary.operations) for summary in summaries
    )
    mode = "Apply" if args.apply else "Dry-run"
    if not args.apply:
        readback = "n/a"
    elif all(summary.verification_ok for summary in summaries):
        readback = "ok"
    else:
        readback = "failed"
    return RunResult(
        path=path,
        notify_message=f"{mode} erfolgreich fuer {len(summaries)} Mitarbeiter, {changed_months} Aenderungsmonate. Report: {path}",
        mode="apply" if args.apply else "dryrun",
        readback=readback,
        changes=changed_months,
        blocked=blocked_months_count,
        run_id=RUN_ID,
    )


def run(args: argparse.Namespace) -> RunResult:
    if args.command in {"set-months", "reset-ea"}:
        return run_single_change(args)
    if args.command == "plan-changes":
        return run_plan_changes(args)
    raise ElChangeError(f"Unbekannter Befehl: {args.command}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="EL-Aenderungen fuer BPLUS-NG mit dry-run als Default.")
    parser.add_argument("--year", type=int, default=current_now().year)
    parser.add_argument("--org-unit-id", type=int, default=ORG_UNIT_ID)
    parser.add_argument("--apply", action="store_true", help="Fuehrt den Write wirklich aus. Ohne --apply bleibt es ein dry-run.")
    parser.add_argument("--output", help="Optionaler Pfad fuer den Markdown-Bericht.")
    parser.add_argument(
        "--notify-no-popup",
        action="store_true",
        help="Ruft notify.ps1 ohne Popup auf (vor allem fuer Tests/Automation).",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    set_months = sub.add_parser("set-months", help="Setzt ausgewaehlte Monate einer bestehenden EA-Zeile auf einen Wert.")
    set_months.add_argument("--mitarbeiter", required=True)
    set_months.add_argument("--ea", required=True)
    set_months.add_argument("--months", help="Kommagetrennte Monate, z. B. apr,may,jun")
    set_months.add_argument("--value", type=float, required=True)
    set_months.add_argument("--all-months", action="store_true", help="Optional: ignoriert --months und setzt alle Monate.")

    reset_ea = sub.add_parser("reset-ea", help="Setzt alle Monate einer bestehenden EA-Zeile auf 0.")
    reset_ea.add_argument("--mitarbeiter", required=True)
    reset_ea.add_argument("--ea", required=True)

    plan_changes = sub.add_parser("plan-changes", help="Plant kombinierte EL-Aenderungen fuer einen oder mehrere Mitarbeiter.")
    plan_changes.add_argument("--mitarbeiter", action="append", help="Mitarbeitername; mehrfach erlaubt.")
    plan_changes.add_argument("--mitarbeiter-file", help="Datei mit einem Mitarbeiter pro Zeile.")
    plan_changes.add_argument("--from-month", help="Startmonat des Aenderungsfensters. Default: aktueller Monat bzw. Jan fuer Zukunftsjahre.")
    plan_changes.add_argument("--to-month", help="Endmonat des Aenderungsfensters. Default: dec.")
    plan_changes.add_argument("--zero-ea", action="append", default=[], help="EA, die im Aenderungsfenster auf 0 gesetzt werden soll.")
    plan_changes.add_argument("--increase-ea", action="append", default=[], help="EA=Wert, z. B. 0043898=1")
    plan_changes.add_argument("--decrease-ea", action="append", default=[], help="EA=Wert, z. B. 0000163=1")
    plan_changes.add_argument(
        "--rebalance",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Restdifferenz pro Monat anhand der Referenz auf offene EAs verteilen. Default: automatisch an bei --zero-ea, sonst aus.",
    )
    plan_changes.add_argument("--reference-preset", default="btl_all_ek", choices=sorted(REFERENCE_PRESETS))
    plan_changes.add_argument("--reference-org-like", help="Optionaler Override fuer den Org-Filter der Referenz, z. B. EKEK%%.")
    plan_changes.add_argument("--reference-include-status", action="append", default=[], help="Status-Substring, das in der Referenz enthalten sein muss. Mehrfach erlaubt.")
    plan_changes.add_argument("--reference-exclude-status", action="append", default=[], help="Status-Substring, das aus der Referenz ausgeschlossen wird. Mehrfach erlaubt.")
    plan_changes.add_argument("--max-step-per-ea-per-month", type=int, default=1)
    plan_changes.add_argument("--fill-strategy", choices=["fallback-active", "strict-underweight"], default="fallback-active")
    plan_changes.add_argument("--require-open-devorder", action=argparse.BooleanOptionalAction, default=True)

    return parser


def build_status_line(result: RunResult, path: Path | str) -> str:
    fields = [
        "STATUS",
        f"MODE={result.mode}",
        f"READBACK={result.readback}",
        f"CHANGES={result.changes}",
        f"BLOCKED={result.blocked}",
        f"RUN_ID={result.run_id}",
        f"PATH={path}",
    ]
    if result.error:
        fields.append(f"ERROR={result.error}")
    return "\t".join(fields)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = run(args)
    except ElChangeError as exc:
        notify_result("failed", str(exc), title="EL Change", no_popup=args.notify_no_popup)
        error_result = RunResult(
            path=Path("-"),
            notify_message=str(exc),
            mode="apply" if getattr(args, "apply", False) else "dryrun",
            readback="failed",
            run_id=RUN_ID,
            error=str(exc).replace("\t", " ").replace("\n", " "),
        )
        print(build_status_line(error_result, "-"), file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1
    notify_result("done", build_notify_message(args, result), title="EL Change", no_popup=args.notify_no_popup)
    print(build_status_line(result, result.path))
    print(result.path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
