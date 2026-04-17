#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import copy
import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(WORKSPACE / "scripts" / "budget"))

from budget_db import BASE_URL, ORG_UNIT_ID, trim  # noqa: E402
from report_utils import note, report_path, section, table_md, write_report  # noqa: E402


LOGS_DIR = WORKSPACE / "userdata" / "tmp" / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

PLANNING_URL = f"{BASE_URL}/ek/api/PlanningException/UpdatePlanningExceptions"
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


def setup_logging() -> Path:
    log_path = LOGS_DIR / f"el_change_{datetime.now():%Y%m%d_%H%M%S}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler(sys.stderr)],
    )
    return log_path


LOG_PATH = setup_logging()


class ElChangeError(RuntimeError):
    pass


def _normalize(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def _coerce_percentage(value: float) -> int | float:
    if value < 0 or value > 100:
        raise ElChangeError("Prozentwert muss zwischen 0 und 100 liegen.")
    return int(value) if float(value).is_integer() else value


def _powershell_json(method: str, url: str, payload: object | None = None, timeout: int = 180):
    cmd_parts = [
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8",
        f"$method = '{method.upper()}'",
        f"$url = '{url}'",
        f"$timeout = {int(timeout)}",
        "$params = @{ Uri = $url; Method = $method; UseDefaultCredentials = $true; TimeoutSec = $timeout }",
    ]
    if payload is not None:
        payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        payload_b64 = base64.b64encode(payload_json.encode("utf-8")).decode("ascii")
        cmd_parts.extend(
            [
                f"$json = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{payload_b64}'))",
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
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", cmd],
        capture_output=True,
        text=True,
    )
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


def render_delta(before: dict[str, int | float], after: dict[str, int | float], months: list[str]) -> str:
    rows = [[month.upper(), before[month], after[month]] for month in MONTH_ORDER if month in months or before[month] != after[month]]
    return table_md(rows, ["Monat", "Alt", "Neu"])


def write_change_report(
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
    output: str | None,
) -> Path:
    path = report_path("el_change", label=f"{command}_{trim(mitarbeiter.get('userFullName'))}_{trim(entry.get('number'))}", output=output)
    role_rows = [[trim(item.get("roleName")), trim(item.get("orgUnit"))] for item in roles]
    sections = [
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
        section("Monatswerte", render_delta(before, after, months)),
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


def run(args: argparse.Namespace) -> Path:
    roles = fetch_roles()
    if not isinstance(roles, list):
        roles = []
    employee_hours = fetch_employee_hours(args.year, args.org_unit_id)
    user = resolve_user(employee_hours, args.mitarbeiter)
    user_id = user.get("idxUser")
    if not user_id:
        raise ElChangeError(f"idxUser fehlt fuer Mitarbeiter: {trim(user.get('userFullName'))}")

    planning = fetch_planning(int(user_id), args.year, args.org_unit_id)
    entry_index, _entry = resolve_entry(planning, args.ea)
    payload = copy.deepcopy(planning)
    target = payload["planningExceptions"][entry_index]

    months = MONTH_ORDER.copy() if args.command == "reset-ea" else parse_months(args.months, all_months=args.all_months)
    value = 0 if args.command == "reset-ea" else _coerce_percentage(args.value)
    before, after = apply_month_changes(target, months, value)

    verification_ok = None
    verification_errors: list[str] | None = None
    if args.apply and before != after:
        logging.info("Sende UpdatePlanningExceptions fuer %s / %s", trim(user.get("userFullName")), trim(target.get("number")))
        post_planning_update(payload)
        refreshed = fetch_planning(int(user_id), args.year, args.org_unit_id)
        _, refreshed_entry = resolve_entry(refreshed, trim(target.get("number")))
        expected = {month: after[month] for month in months}
        verification_ok, verification_errors = verify_months(refreshed_entry, expected)
        if not verification_ok:
            raise ElChangeError("Readback-Verifikation fehlgeschlagen: " + "; ".join(verification_errors or []))
    elif args.apply:
        logging.info("Kein Write noetig, da keine Aenderung entstanden ist.")

    return write_change_report(
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
        output=args.output,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="EL-Aenderungen fuer BPLUS-NG mit dry-run als Default.")
    parser.add_argument("--year", type=int, default=datetime.now().year)
    parser.add_argument("--org-unit-id", type=int, default=ORG_UNIT_ID)
    parser.add_argument("--apply", action="store_true", help="Fuehrt den Write wirklich aus. Ohne --apply bleibt es ein dry-run.")
    parser.add_argument("--output", help="Optionaler Pfad fuer den Markdown-Bericht.")

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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        path = run(args)
    except ElChangeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
