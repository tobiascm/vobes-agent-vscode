from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
OUTLOOK_SEARCH_DIR = SCRIPT_DIR.parents[1] / "skill-outlook" / "scripts"
if str(OUTLOOK_SEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(OUTLOOK_SEARCH_DIR))

from outlook_search_tools import (  # noqa: E402
    _coerce_text,
    _get_item_by_id,
    _lazy_outlook_context,
    _safe_get,
    _try_internet_address,
)

OL_APPOINTMENT_ITEM = 1
OL_FOLDER_CALENDAR = 9
OL_MEETING = 1
OL_NON_MEETING = 0
OL_MEETING_CANCELED = 5
OL_REQUIRED = 1
OL_OPTIONAL = 2
DRAFT_PREFIX = "Entwurf: "
SEND_MODE_REVIEW = "review"


@dataclass
class RecipientResult:
    requested: str
    resolved: bool
    kind: str
    target: str = ""
    name: str = ""
    address: str = ""
    candidates: list[dict[str, str]] = field(default_factory=list)


def _parse_local_datetime(value: str) -> datetime:
    text = _coerce_text(value).strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt.replace(second=0, microsecond=0)


def _apply_standard_start(dt: datetime) -> datetime:
    if dt.minute in (0, 30):
        return dt + timedelta(minutes=5)
    return dt


def _default_end(start: datetime, short_clarification: bool) -> datetime:
    return start + timedelta(minutes=25 if short_clarification else 55)


def _strip_draft_prefix(subject: str) -> str:
    text = _coerce_text(subject).strip()
    if text.lower().startswith(DRAFT_PREFIX.lower()):
        return text[len(DRAFT_PREFIX) :].strip()
    return text


def _effective_subject(subject: str, draft: bool) -> str:
    base = _strip_draft_prefix(subject)
    return f"{DRAFT_PREFIX}{base}" if draft and base else base


def _candidate_payload(name: str, address: str) -> dict[str, str]:
    return {"name": _coerce_text(name).strip(), "address": _coerce_text(address).strip()}


def _primary_smtp(entry: Any) -> str:
    try:
        if _coerce_text(_safe_get(entry, "Type", "")) == "EX":
            ex_user = entry.GetExchangeUser()
            if ex_user and ex_user.PrimarySmtpAddress:
                return str(ex_user.PrimarySmtpAddress)
    except Exception:
        pass
    return _coerce_text(_safe_get(entry, "Address", ""))


def _candidate_target(candidate: dict[str, str]) -> str:
    return candidate["address"] or candidate["name"]


def _search_gal_candidates(token: str, limit: int = 5) -> list[dict[str, str]]:
    _, namespace, _ = _lazy_outlook_context()
    terms = [part for part in re.split(r"\W+", token.lower()) if part]
    if not terms:
        return []
    candidates: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    address_lists = _safe_get(namespace, "AddressLists")
    count = int(_safe_get(address_lists, "Count", 0) or 0)
    for index in range(1, count + 1):
        address_list = address_lists.Item(index)
        list_name = _coerce_text(_safe_get(address_list, "Name", "")).lower()
        if "globale adressliste" not in list_name and "global address list" not in list_name:
            continue
        entries = _safe_get(address_list, "AddressEntries")
        entry_count = int(_safe_get(entries, "Count", 0) or 0)
        for entry_index in range(1, entry_count + 1):
            entry = entries.Item(entry_index)
            name = _coerce_text(_safe_get(entry, "Name", ""))
            address = _primary_smtp(entry)
            haystack = f"{name}\n{address}".lower()
            if not all(term in haystack for term in terms):
                continue
            key = (name.lower(), address.lower())
            if key in seen:
                continue
            seen.add(key)
            candidates.append(_candidate_payload(name, address))
            if len(candidates) >= limit:
                return candidates
    return candidates


def _resolve_recipient(token: str) -> RecipientResult:
    _, namespace, _ = _lazy_outlook_context()
    recipient = namespace.CreateRecipient(token)
    if recipient.Resolve():
        address_entry = recipient.AddressEntry
        name = _coerce_text(_safe_get(recipient, "Name", ""))
        address = _try_internet_address(recipient)
        target = address or name
        return RecipientResult(token, True, "direct", target=target, name=name, address=address)
    candidates = _search_gal_candidates(token)
    if len(candidates) == 1:
        candidate = candidates[0]
        return RecipientResult(
            token,
            True,
            "gal-search",
            target=_candidate_target(candidate),
            name=candidate["name"],
            address=candidate["address"],
        )
    return RecipientResult(token, False, "ambiguous" if candidates else "missing", candidates=candidates)


def _resolve_many(required: list[str], optional: list[str]) -> tuple[list[RecipientResult], list[RecipientResult]]:
    required_results = [_resolve_recipient(value) for value in required]
    optional_results = [_resolve_recipient(value) for value in optional]
    return required_results, optional_results


def _add_recipients(item: Any, recipient_results: list[RecipientResult], recipient_type: int) -> None:
    for result in recipient_results:
        recipient = item.Recipients.Add(result.target)
        recipient.Type = recipient_type


def _recipient_payload(results: list[RecipientResult]) -> list[dict[str, Any]]:
    return [asdict(result) for result in results]


def _format_datetime(value: Any) -> str:
    try:
        return datetime(
            int(value.year),
            int(value.month),
            int(value.day),
            int(value.hour),
            int(value.minute),
            int(value.second),
        ).isoformat()
    except Exception:
        return ""


def _appointment_payload(item: Any) -> dict[str, Any]:
    required_results = []
    optional_results = []
    recipients = _safe_get(item, "Recipients")
    count = int(_safe_get(recipients, "Count", 0) or 0)
    for index in range(1, count + 1):
        recipient = recipients.Item(index)
        payload = {
            "name": _coerce_text(_safe_get(recipient, "Name", "")),
            "address": _try_internet_address(recipient),
            "type": int(_safe_get(recipient, "Type", 0) or 0),
        }
        if payload["type"] == OL_OPTIONAL:
            optional_results.append(payload)
        else:
            required_results.append(payload)
    return {
        "entry_id": _coerce_text(_safe_get(item, "EntryID", "")),
        "subject": _coerce_text(_safe_get(item, "Subject", "")),
        "start": _format_datetime(_safe_get(item, "Start")),
        "end": _format_datetime(_safe_get(item, "End")),
        "location": _coerce_text(_safe_get(item, "Location", "")),
        "body": _coerce_text(_safe_get(item, "Body", "")),
        "is_online_meeting": bool(_safe_get(item, "IsOnlineMeeting", False)),
        "online_meeting_provider": int(_safe_get(item, "OnlineMeetingProvider", 0) or 0),
        "meeting_status": int(_safe_get(item, "MeetingStatus", 0) or 0),
        "required_recipients": required_results,
        "optional_recipients": optional_results,
    }


def _display_item(item: Any) -> dict[str, bool]:
    item.Display(False)
    inspector = item.GetInspector()
    inspector.Activate()
    return {"window_opened": True, "window_activated": True}


def _resolve_send_mode(send_mode: str, send_without_confirmation: bool) -> str:
    return "send" if send_without_confirmation else (send_mode or SEND_MODE_REVIEW)


def _finalize_item(item: Any, *, send_mode: str, has_attendees: bool, save_when_draft: bool = True) -> dict[str, Any]:
    warnings: list[str] = []
    ui_state = {"window_opened": False, "window_activated": False}
    if send_mode == "send":
        item.Subject = _effective_subject(_coerce_text(_safe_get(item, "Subject", "")), draft=False)
        item.Save()
        if has_attendees:
            item.Send()
        else:
            warnings.append("No attendees resolved; item was saved in calendar only.")
    elif send_mode == "draft":
        if save_when_draft:
            item.Save()
    else:
        ui_state = _display_item(item)
    return {"warnings": warnings, **ui_state}


def _calendar_items() -> Any:
    _, namespace, _ = _lazy_outlook_context()
    folder = namespace.GetDefaultFolder(OL_FOLDER_CALENDAR)
    items = folder.Items
    items.Sort("[Start]")
    items.IncludeRecurrences = False
    return items


def create_appointment(
    *,
    subject: str,
    start: str,
    end: str = "",
    duration_min: int = 0,
    short_clarification: bool = False,
    required: list[str] | None = None,
    optional: list[str] | None = None,
    body: str = "",
    location: str = "",
    teams: bool = True,
    send_mode: str = SEND_MODE_REVIEW,
    send_without_confirmation: bool = False,
) -> dict[str, Any]:
    app, _, _ = _lazy_outlook_context()
    required_results, optional_results = _resolve_many(required or [], optional or [])
    unresolved = [result for result in required_results + optional_results if not result.resolved]
    if unresolved:
        return {
            "status": "needs_input",
            "action": "create",
            "unresolved_recipients": _recipient_payload(unresolved),
            "resolved_recipients": _recipient_payload([result for result in required_results + optional_results if result.resolved]),
        }

    start_dt = _apply_standard_start(_parse_local_datetime(start))
    if end:
        end_dt = _parse_local_datetime(end)
    elif duration_min:
        end_dt = start_dt + timedelta(minutes=duration_min)
    else:
        end_dt = _default_end(start_dt, short_clarification)

    item = app.CreateItem(OL_APPOINTMENT_ITEM)
    has_attendees = bool(required_results or optional_results)
    item.MeetingStatus = OL_MEETING if has_attendees else OL_NON_MEETING
    item.Subject = _effective_subject(subject, draft=send_mode == "draft")
    item.Start = start_dt
    item.End = end_dt
    item.Location = _coerce_text(location).strip()
    item.Body = _coerce_text(body)
    if teams:
        item.IsOnlineMeeting = True
    _add_recipients(item, required_results, OL_REQUIRED)
    _add_recipients(item, optional_results, OL_OPTIONAL)
    final_send_mode = _resolve_send_mode(send_mode, send_without_confirmation)
    final_state = _finalize_item(item, send_mode=final_send_mode, has_attendees=has_attendees)

    return {
        "status": "ok",
        "action": "create",
        "send_mode": final_send_mode,
        "draft_subject_applied": final_send_mode != "send",
        "effective_subject": item.Subject,
        "resolved_recipients": _recipient_payload(required_results + optional_results),
        "unresolved_recipients": [],
        "warnings": final_state["warnings"],
        "window_opened": final_state["window_opened"],
        "window_activated": final_state["window_activated"],
        "appointment": _appointment_payload(item),
    }


def send_appointment(entry_id: str, store_id: str = "") -> dict[str, Any]:
    item = _get_item_by_id(entry_id, store_id)
    item.Subject = _effective_subject(_coerce_text(_safe_get(item, "Subject", "")), draft=False)
    item.Save()
    has_attendees = bool(_coerce_text(_safe_get(item, "RequiredAttendees", "")).strip() or _coerce_text(_safe_get(item, "OptionalAttendees", "")).strip())
    warnings: list[str] = []
    if has_attendees:
        item.Send()
    else:
        warnings.append("No attendees on appointment; item was saved but not sent.")
    return {"status": "ok", "action": "send", "warnings": warnings, "appointment": _appointment_payload(item)}


def update_appointment(
    entry_id: str,
    store_id: str = "",
    *,
    subject: str = "",
    start: str = "",
    end: str = "",
    duration_min: int = 0,
    short_clarification: bool = False,
    body: str | None = None,
    location: str | None = None,
    teams: bool | None = None,
    send_mode: str = "",
    send_without_confirmation: bool = False,
) -> dict[str, Any]:
    item = _get_item_by_id(entry_id, store_id)
    if subject:
        keep_draft = _coerce_text(_safe_get(item, "Subject", "")).lower().startswith(DRAFT_PREFIX.lower()) and send_mode != "send"
        item.Subject = _effective_subject(subject, draft=keep_draft)
    if start:
        start_dt = _apply_standard_start(_parse_local_datetime(start))
        item.Start = start_dt
        if end:
            item.End = _parse_local_datetime(end)
        elif duration_min:
            item.End = start_dt + timedelta(minutes=duration_min)
        elif not _coerce_text(end):
            item.End = _default_end(start_dt, short_clarification)
    elif end:
        item.End = _parse_local_datetime(end)
    if body is not None:
        item.Body = _coerce_text(body)
    if location is not None:
        item.Location = _coerce_text(location).strip()
    if teams is not None:
        item.IsOnlineMeeting = teams
    final_send_mode = _resolve_send_mode(send_mode, send_without_confirmation)
    final_state = _finalize_item(item, send_mode=final_send_mode, has_attendees=True, save_when_draft=False)
    return {
        "status": "ok",
        "action": "update",
        "send_mode": final_send_mode,
        "warnings": final_state["warnings"],
        "window_opened": final_state["window_opened"],
        "window_activated": final_state["window_activated"],
        "appointment": _appointment_payload(item),
    }


def cancel_appointment(entry_id: str, store_id: str = "", *, send_without_confirmation: bool = False) -> dict[str, Any]:
    item = _get_item_by_id(entry_id, store_id)
    has_attendees = bool(_coerce_text(_safe_get(item, "RequiredAttendees", "")).strip() or _coerce_text(_safe_get(item, "OptionalAttendees", "")).strip())
    if has_attendees:
        item.MeetingStatus = OL_MEETING_CANCELED
        final_state = _finalize_item(
            item,
            send_mode=_resolve_send_mode("", send_without_confirmation),
            has_attendees=True,
            save_when_draft=False,
        )
        return {
            "status": "ok",
            "action": "cancel",
            "mode": "meeting-cancel",
            "warnings": final_state["warnings"],
            "window_opened": final_state["window_opened"],
            "window_activated": final_state["window_activated"],
            "appointment": _appointment_payload(item),
        }
    item.Delete()
    return {"status": "ok", "action": "cancel", "mode": "delete-solo", "entry_id": entry_id}


def search_appointments(
    *,
    start_from: str = "",
    start_to: str = "",
    subject: str = "",
    participant: list[str] | None = None,
    max_results: int = 10,
) -> dict[str, Any]:
    start_from_dt = _parse_local_datetime(start_from) if start_from else None
    start_to_dt = _parse_local_datetime(start_to) if start_to else None
    participant_terms = [value.lower() for value in (participant or []) if _coerce_text(value).strip()]
    matches: list[dict[str, Any]] = []
    items = _calendar_items()
    count = int(_safe_get(items, "Count", 0) or 0)
    subject_term = _coerce_text(subject).strip().lower()
    for index in range(1, count + 1):
        item = items.Item(index)
        start_value = _safe_get(item, "Start")
        try:
            item_start = datetime(
                int(start_value.year),
                int(start_value.month),
                int(start_value.day),
                int(start_value.hour),
                int(start_value.minute),
                int(start_value.second),
            )
        except Exception:
            continue
        if start_from_dt and item_start < start_from_dt:
            continue
        if start_to_dt and item_start > start_to_dt:
            continue
        haystack = "\n".join(
            [
                _coerce_text(_safe_get(item, "Subject", "")),
                _coerce_text(_safe_get(item, "RequiredAttendees", "")),
                _coerce_text(_safe_get(item, "OptionalAttendees", "")),
            ]
        ).lower()
        if subject_term and subject_term not in haystack:
            continue
        if participant_terms and not all(term in haystack for term in participant_terms):
            continue
        matches.append(_appointment_payload(item))
        if len(matches) >= max_results:
            break
    return {"status": "ok", "action": "search", "matches": matches}


def diagnostics() -> dict[str, Any]:
    app, namespace, _ = _lazy_outlook_context()
    item = app.CreateItem(OL_APPOINTMENT_ITEM)
    return {
        "status": "ok",
        "action": "diagnostics",
        "outlook_version": _coerce_text(_safe_get(app, "Version", "")),
        "default_online_meeting_enabled": bool(_safe_get(item, "DefaultOnlineMeetingEnabled", False)),
        "online_meeting_provider": int(_safe_get(item, "OnlineMeetingProvider", 0) or 0),
        "calendar_folder": _coerce_text(_safe_get(namespace.GetDefaultFolder(OL_FOLDER_CALENDAR), "FolderPath", "")),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Outlook appointment helper for review-first Teams meetings.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common_time_arguments(command: argparse.ArgumentParser, *, start_required: bool = False) -> None:
        command.add_argument("--start", default="", required=start_required, help="ISO-Datetime fuer den Start.")
        command.add_argument("--end", default="", help="ISO-Datetime fuer das Ende.")
        command.add_argument("--duration-min", type=int, default=0, help="Alternative Dauer in Minuten.")
        command.add_argument("--short-clarification", action="store_true", help="Nutze 25 Minuten statt 55 Minuten Standarddauer.")

    create_parser = subparsers.add_parser("create", help="Create an Outlook appointment or meeting.")
    create_parser.add_argument("--subject", required=True)
    add_common_time_arguments(create_parser, start_required=True)
    create_parser.add_argument("--required", action="append", default=[])
    create_parser.add_argument("--optional", action="append", default=[])
    create_parser.add_argument("--body", default="")
    create_parser.add_argument("--location", default="")
    create_parser.add_argument("--send-mode", choices=(SEND_MODE_REVIEW, "draft", "send"), default=SEND_MODE_REVIEW)
    create_parser.add_argument("--send-without-confirmation", action="store_true")
    create_parser.add_argument("--teams", dest="teams", action="store_true", default=True)
    create_parser.add_argument("--no-teams", dest="teams", action="store_false")

    send_parser = subparsers.add_parser("send", help="Send a prepared draft meeting.")
    send_parser.add_argument("--entry-id", required=True)
    send_parser.add_argument("--store-id", default="")

    update_parser = subparsers.add_parser("update", help="Update an existing appointment.")
    update_parser.add_argument("--entry-id", required=True)
    update_parser.add_argument("--store-id", default="")
    update_parser.add_argument("--subject", default="")
    add_common_time_arguments(update_parser)
    update_parser.add_argument("--body", default=None)
    update_parser.add_argument("--location", default=None)
    update_parser.add_argument("--send-mode", choices=(SEND_MODE_REVIEW, "draft", "send"), default="")
    update_parser.add_argument("--send-without-confirmation", action="store_true")
    update_parser.add_argument("--teams", dest="teams", action="store_true", default=None)
    update_parser.add_argument("--no-teams", dest="teams", action="store_false")

    cancel_parser = subparsers.add_parser("cancel", help="Cancel an existing appointment.")
    cancel_parser.add_argument("--entry-id", required=True)
    cancel_parser.add_argument("--store-id", default="")
    cancel_parser.add_argument("--send-without-confirmation", action="store_true")

    search_parser = subparsers.add_parser("search", help="Search appointments in the default calendar.")
    search_parser.add_argument("--start-from", default="")
    search_parser.add_argument("--start-to", default="")
    search_parser.add_argument("--subject", default="")
    search_parser.add_argument("--participant", action="append", default=[])
    search_parser.add_argument("--max-results", type=int, default=10)

    resolve_parser = subparsers.add_parser("resolve-recipient", help="Resolve one or more recipients.")
    resolve_parser.add_argument("--name", action="append", default=[], required=True)

    subparsers.add_parser("diagnostics", help="Run a lightweight Outlook COM diagnostics check.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "create":
        payload = create_appointment(
            subject=args.subject,
            start=args.start,
            end=args.end,
            duration_min=args.duration_min,
            short_clarification=args.short_clarification,
            required=args.required,
            optional=args.optional,
            body=args.body,
            location=args.location,
            teams=args.teams,
            send_mode=args.send_mode,
            send_without_confirmation=args.send_without_confirmation,
        )
    elif args.command == "send":
        payload = send_appointment(args.entry_id, args.store_id)
    elif args.command == "update":
        payload = update_appointment(
            args.entry_id,
            args.store_id,
            subject=args.subject,
            start=args.start,
            end=args.end,
            duration_min=args.duration_min,
            short_clarification=args.short_clarification,
            body=args.body,
            location=args.location,
            teams=args.teams,
            send_mode=args.send_mode,
            send_without_confirmation=args.send_without_confirmation,
        )
    elif args.command == "cancel":
        payload = cancel_appointment(args.entry_id, args.store_id, send_without_confirmation=args.send_without_confirmation)
    elif args.command == "search":
        payload = search_appointments(
            start_from=args.start_from,
            start_to=args.start_to,
            subject=args.subject,
            participant=args.participant,
            max_results=args.max_results,
        )
    elif args.command == "resolve-recipient":
        payload = {
            "status": "ok",
            "action": "resolve-recipient",
            "results": _recipient_payload([_resolve_recipient(value) for value in args.name]),
        }
    else:
        payload = diagnostics()
    json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
