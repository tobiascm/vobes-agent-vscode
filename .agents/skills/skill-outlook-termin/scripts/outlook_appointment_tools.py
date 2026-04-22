from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
OUTLOOK_SEARCH_DIR = SCRIPT_DIR.parents[1] / "skill-outlook" / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(OUTLOOK_SEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(OUTLOOK_SEARCH_DIR))

from outlook_search_tools import (  # noqa: E402
    _com_to_local,
    _coerce_text,
    _get_item_by_id,
    _lazy_outlook_context,
    _normalize_smtp_address,
    _safe_get,
    _try_internet_address,
    inspect_selected_email,
    outlook_read_email,
    search_emails,
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
DEFAULT_APPOINTMENT_CATEGORY = "EKEK1"
DEFAULT_MAIL_SEARCH_DAYS = 365


@dataclass
class RecipientResult:
    requested: str
    resolved: bool
    kind: str
    target: str = ""
    name: str = ""
    email: str = ""
    oe: str = ""
    seen_count: int = 0
    candidates: list[dict[str, Any]] = field(default_factory=list)


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


def _extract_oe(name: str) -> str:
    text = _coerce_text(name).strip()
    match = re.search(r"\(([^()]+)\)\s*$", text)
    return _coerce_text(match.group(1)).strip() if match else ""


def _normalize_subject_text(value: str) -> str:
    return _coerce_text(value).strip().lower()


def _strip_reply_prefixes(subject: str) -> str:
    text = _coerce_text(subject).strip()
    while True:
        updated = re.sub(r"^(?:re|aw|wg|fw|fwd)\s*:\s*", "", text, flags=re.IGNORECASE)
        if updated == text:
            return text
        text = updated.strip()


def _mail_subject_matches(candidate_subject: str, requested_subject: str) -> bool:
    candidate = _normalize_subject_text(candidate_subject)
    requested = _normalize_subject_text(requested_subject)
    if not candidate or not requested:
        return False
    return candidate == requested or requested in candidate or candidate in requested


def _unique_texts(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _coerce_text(value).strip()
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _extract_email_address(value: str) -> str:
    text = _coerce_text(value).strip()
    if not text:
        return ""
    match = re.search(r"<([^>]+)>", text)
    if match:
        return _normalize_smtp_address(match.group(1))
    return _normalize_smtp_address(text)


def _own_mail_addresses() -> set[str]:
    _, namespace, _ = _lazy_outlook_context()
    stores = _safe_get(namespace, "Stores")
    count = int(_safe_get(stores, "Count", 0) or 0)
    addresses: set[str] = set()
    for index in range(1, count + 1):
        try:
            store = stores.Item(index)
        except Exception:
            continue
        address = _normalize_smtp_address(_safe_get(store, "DisplayName", ""))
        if address:
            addresses.add(address.lower())
    return addresses


def _mail_recipients(mail_payload: dict[str, Any]) -> tuple[list[str], list[str]]:
    own_addresses = _own_mail_addresses()
    to_values = [_extract_email_address(value) for value in mail_payload.get("to_recipients", [])]
    cc_values = [_extract_email_address(value) for value in mail_payload.get("cc_recipients", [])]
    to_clean = [value for value in to_values if value and value.lower() not in own_addresses]
    cc_clean = [
        value
        for value in cc_values
        if value and value.lower() not in own_addresses and value.lower() not in {item.lower() for item in to_clean}
    ]
    return _unique_texts(to_clean), _unique_texts(cc_clean)


def _mail_context_lines(body: str, limit: int = 4) -> list[str]:
    stop_markers = (
        "-----original appointment-----",
        "-----ursprünglicher termin-----",
        "-----urspruenglicher termin-----",
        "microsoft teams-besprechung",
        "microsoft teams meeting",
        "________________________________________________________________________________",
    )
    lines: list[str] = []
    for raw_line in _coerce_text(body).splitlines():
        line = raw_line.strip()
        normalized = line.lower()
        if not line:
            if lines:
                break
            continue
        if normalized == "internal":
            continue
        if any(marker in normalized for marker in stop_markers):
            break
        lines.append(line)
        if len(lines) >= limit:
            break
    return lines


def _mail_context_body(subject: str, mail_payload: dict[str, Any]) -> str:
    excerpt = _mail_context_lines(mail_payload.get("body", ""))
    intro = f'ich habe den Termin zur Abstimmung "{subject}" vorbereitet.'
    if excerpt:
        intro = f"{intro}\n\nKontext aus der letzten Mail:\n" + "\n".join(excerpt)
    return f"Hallo zusammen,\n\n{intro}\n\nViele Gruesse\nTobias"


def _load_mail_context(source_mail_subject: str) -> dict[str, Any]:
    requested_subject = _coerce_text(source_mail_subject).strip()
    if not requested_subject:
        raise ValueError("source_mail_subject darf nicht leer sein.")

    try:
        selection = inspect_selected_email()
        selected_item = selection.get("selected_item", {})
        if _mail_subject_matches(selected_item.get("subject", ""), requested_subject):
            return outlook_read_email(
                selected_item.get("entry_id", ""),
                selected_item.get("parent", {}).get("store_id", ""),
            )
    except Exception:
        pass

    payload = search_emails(
        subject_must=[requested_subject],
        search_days=DEFAULT_MAIL_SEARCH_DAYS,
        max_results=10,
    )
    matches = payload.get("matches", [])
    if not matches:
        raise RuntimeError(f"Keine Outlook-Mail mit passendem Betreff gefunden: {requested_subject}")

    best_match = matches[0]["email"]
    return outlook_read_email(best_match.get("entry_id", ""), best_match.get("store_id", ""))


def _candidate_payload(name: str, address: str, *, seen_count: int = 0) -> dict[str, Any]:
    cleaned_name = _coerce_text(name).strip()
    cleaned_address = _coerce_text(address).strip()
    return {
        "name": cleaned_name,
        "email": cleaned_address,
        "oe": _extract_oe(cleaned_name),
        "seen_count": max(int(seen_count or 0), 0),
    }


def _candidate_target(candidate: dict[str, Any]) -> str:
    return _coerce_text(candidate.get("email") or candidate.get("name")).strip()


def _sort_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        candidates,
        key=lambda item: (
            -int(item.get("seen_count", 0) or 0),
            _coerce_text(item.get("name", "")).lower(),
            _coerce_text(item.get("email", "")).lower(),
        ),
    )


def _address_cache_module() -> Any:
    return importlib.import_module("outlook_address_cache")


def _cache_recipient_candidates(
    token: str,
    *,
    refresh_state: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    try:
        payload = _address_cache_module().lookup_cached_addresses(
            token,
            limit=5,
            refresh_state=refresh_state,
        )
    except Exception:
        return []

    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for match in payload.get("matches", []):
        candidate = _candidate_payload(
            match.get("display_name", ""),
            match.get("email", ""),
            seen_count=int(match.get("seen_count", 0) or 0),
        )
        key = (candidate["name"].lower(), candidate["email"].lower())
        if key in seen:
            continue
        seen.add(key)
        candidates.append(candidate)
    return _sort_candidates(candidates)


def _search_gal_candidates(token: str, limit: int = 5) -> list[dict[str, Any]]:
    _, namespace, _ = _lazy_outlook_context()
    terms = [part for part in re.split(r"\W+", token.lower()) if part]
    if not terms:
        return []
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    address_lists = _safe_get(namespace, "AddressLists")
    count = int(_safe_get(address_lists, "Count", 0) or 0)
    for index in range(1, count + 1):
        address_list = address_lists.Item(index)
        list_name = _coerce_text(_safe_get(address_list, "Name", "")).lower()
        if "offline global address list" in list_name:
            continue
        if "globale adressliste" not in list_name and "global address list" not in list_name:
            continue
        entries = _safe_get(address_list, "AddressEntries")
        entry_count = int(_safe_get(entries, "Count", 0) or 0)
        for entry_index in range(1, entry_count + 1):
            entry = entries.Item(entry_index)
            name = _coerce_text(_safe_get(entry, "Name", ""))
            address = _try_internet_address(entry)
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
    return _sort_candidates(candidates)


def _resolve_recipient(token: str, refresh_state: dict[str, Any] | None = None) -> RecipientResult:
    cache_candidates = _sort_candidates(_cache_recipient_candidates(token, refresh_state=refresh_state))
    if len(cache_candidates) == 1:
        candidate = cache_candidates[0]
        return RecipientResult(
            token,
            True,
            "address-cache",
            target=_candidate_target(candidate),
            name=candidate["name"],
            email=_coerce_text(candidate.get("email", "")),
            oe=_coerce_text(candidate.get("oe", "")),
            seen_count=int(candidate.get("seen_count", 0) or 0),
        )
    if cache_candidates:
        return RecipientResult(token, False, "ambiguous-cache", candidates=cache_candidates)

    _, namespace, _ = _lazy_outlook_context()
    recipient = namespace.CreateRecipient(token)
    if recipient.Resolve():
        name = _coerce_text(_safe_get(recipient, "Name", ""))
        address = _try_internet_address(recipient)
        target = address or name
        return RecipientResult(
            token,
            True,
            "direct",
            target=target,
            name=name,
            email=address,
            oe=_extract_oe(name),
        )
    candidates = _sort_candidates(_search_gal_candidates(token))
    if len(candidates) == 1:
        candidate = candidates[0]
        return RecipientResult(
            token,
            True,
            "gal-search",
            target=_candidate_target(candidate),
            name=candidate["name"],
            email=_coerce_text(candidate.get("email", "")),
            oe=_coerce_text(candidate.get("oe", "")),
            seen_count=int(candidate.get("seen_count", 0) or 0),
        )
    return RecipientResult(
        token,
        False,
        "ambiguous" if candidates else "missing",
        email=address if 'address' in locals() else "",
        oe=_extract_oe(name) if 'name' in locals() else "",
        candidates=candidates,
    )


def _resolve_many(required: list[str], optional: list[str]) -> tuple[list[RecipientResult], list[RecipientResult]]:
    refresh_state: dict[str, Any] = {}
    required_results = [_resolve_recipient(value, refresh_state=refresh_state) for value in required]
    optional_results = [_resolve_recipient(value, refresh_state=refresh_state) for value in optional]
    return required_results, optional_results


def _add_recipients(item: Any, recipient_results: list[RecipientResult], recipient_type: int) -> None:
    for result in recipient_results:
        recipient = item.Recipients.Add(result.target)
        recipient.Type = recipient_type


def _recipient_result_payload(result: RecipientResult) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "requested": result.requested,
        "resolved": result.resolved,
        "kind": result.kind,
    }
    if result.resolved:
        payload["target"] = result.target
        payload["name"] = result.name
        payload["email"] = result.email
        payload["oe"] = result.oe
        payload["seen_count"] = result.seen_count
    if result.candidates:
        payload["candidates"] = result.candidates
    return payload


def _recipient_payload(results: list[RecipientResult]) -> list[dict[str, Any]]:
    return [_recipient_result_payload(result) for result in results]


def _current_outlook_timezone(app: Any, fallback_item: Any) -> Any:
    """Return current Outlook timezone object, fallback to item's timezone."""
    try:
        time_zones = _safe_get(app, "TimeZones")
        current = _safe_get(time_zones, "CurrentTimeZone")
        if current is not None:
            return current
    except Exception:
        pass
    return _safe_get(fallback_item, "StartTimeZone")


def _format_datetime(value: Any) -> str:
    try:
        value = _com_to_local(value)
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
    inspector = item.GetInspector
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


def _reapply_times_if_shifted(
    item: Any,
    intended_start: datetime,
    intended_end: datetime,
    local_start_tz: Any = None,
    local_end_tz: Any = None,
) -> None:
    """Safety net: re-apply Start/End if they drifted during Display/Save."""
    try:
        actual = _com_to_local(item.Start)
        actual_naive = datetime(
            int(actual.year), int(actual.month), int(actual.day),
            int(actual.hour), int(actual.minute),
        )
        if actual_naive == intended_start:
            return
        if local_start_tz is not None:
            item.StartTimeZone = local_start_tz
        if local_end_tz is not None:
            item.EndTimeZone = local_end_tz
        item.Start = intended_start
        item.End = intended_end
        item.Save()
    except Exception:
        pass


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
    normalize_start: bool = True,
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

    start_dt = _parse_local_datetime(start)
    if normalize_start:
        start_dt = _apply_standard_start(start_dt)
    if end:
        end_dt = _parse_local_datetime(end)
    elif duration_min:
        end_dt = start_dt + timedelta(minutes=duration_min)
    else:
        end_dt = _default_end(start_dt, short_clarification)

    assign_start_dt = start_dt
    assign_end_dt = end_dt
    try:
        # Outlook COM stores appointment times two hours too early unless
        # we compensate with the local UTC offset for the target datetime.
        start_offset = start_dt.astimezone().utcoffset() or timedelta(0)
        end_offset = end_dt.astimezone().utcoffset() or timedelta(0)
        assign_start_dt = start_dt + start_offset
        assign_end_dt = end_dt + end_offset
    except Exception:
        pass

    item = app.CreateItem(OL_APPOINTMENT_ITEM)
    has_attendees = bool(required_results or optional_results)
    item.MeetingStatus = OL_MEETING if has_attendees else OL_NON_MEETING
    item.Subject = _effective_subject(subject, draft=send_mode == "draft")
    item.Categories = DEFAULT_APPOINTMENT_CATEGORY
    # Freeze timezone to Outlook's current timezone. Without this, Teams
    # provisioning can keep GMT and shift the displayed local start/end.
    local_tz = _current_outlook_timezone(app, item)
    local_start_tz = local_tz
    local_end_tz = local_tz
    item.Location = _coerce_text(location).strip()
    item.Body = _coerce_text(body).replace("\\n", "\n")
    if teams:
        item.IsOnlineMeeting = True
    _add_recipients(item, required_results, OL_REQUIRED)
    _add_recipients(item, optional_results, OL_OPTIONAL)
    # Restore local timezone and set Start/End so the naive datetimes
    # are interpreted in the correct (local) timezone, not GMT.
    item.StartTimeZone = local_start_tz
    item.EndTimeZone = local_end_tz
    item.Start = assign_start_dt
    item.End = assign_end_dt
    final_send_mode = _resolve_send_mode(send_mode, send_without_confirmation)
    final_state = _finalize_item(item, send_mode=final_send_mode, has_attendees=has_attendees)
    _reapply_times_if_shifted(item, start_dt, end_dt, local_start_tz, local_end_tz)

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
    normalize_start: bool = True,
) -> dict[str, Any]:
    app, _, _ = _lazy_outlook_context()
    item = _get_item_by_id(entry_id, store_id)
    # Freeze timezone to Outlook's current timezone to avoid display drift.
    local_tz = _current_outlook_timezone(app, item)
    local_start_tz = local_tz
    local_end_tz = local_tz
    if subject:
        keep_draft = _coerce_text(_safe_get(item, "Subject", "")).lower().startswith(DRAFT_PREFIX.lower()) and send_mode != "send"
        item.Subject = _effective_subject(subject, draft=keep_draft)
    if body is not None:
        item.Body = _coerce_text(body).replace("\\n", "\n")
    if location is not None:
        item.Location = _coerce_text(location).strip()
    if teams is not None:
        item.IsOnlineMeeting = teams
    # Restore local timezone and set Start/End so naive datetimes
    # are interpreted in the correct (local) timezone, not GMT.
    intended_start: datetime | None = None
    intended_end: datetime | None = None
    if start:
        item.StartTimeZone = local_start_tz
        item.EndTimeZone = local_end_tz
        start_dt = _parse_local_datetime(start)
        if normalize_start:
            start_dt = _apply_standard_start(start_dt)
        intended_start = start_dt
        item.Start = start_dt
        if end:
            end_dt = _parse_local_datetime(end)
            intended_end = end_dt
            item.End = end_dt
        elif duration_min:
            end_dt = start_dt + timedelta(minutes=duration_min)
            intended_end = end_dt
            item.End = end_dt
        elif not _coerce_text(end):
            end_dt = _default_end(start_dt, short_clarification)
            intended_end = end_dt
            item.End = end_dt
    elif end:
        item.End = _parse_local_datetime(end)
    final_send_mode = _resolve_send_mode(send_mode, send_without_confirmation)
    final_state = _finalize_item(item, send_mode=final_send_mode, has_attendees=True, save_when_draft=False)
    if intended_start and intended_end:
        _reapply_times_if_shifted(item, intended_start, intended_end, local_start_tz, local_end_tz)
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
            start_local = _com_to_local(start_value)
            item_start = datetime(
                int(start_local.year),
                int(start_local.month),
                int(start_local.day),
                int(start_local.hour),
                int(start_local.minute),
                int(start_local.second),
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


def _slotfinder_module() -> Any:
    return importlib.import_module("outlook_find_appointment_slot")


def suggest_slots(
    *,
    search_start: str,
    search_end: str,
    duration_min: int = 60,
    slot_minutes: int = 30,
    top_n: int = 10,
    required: list[str] | None = None,
    optional: list[str] | None = None,
    subject: str = "",
    include_weekends: bool = False,
    working_hour_start: int = 8,
    working_hour_end: int = 18,
    open_best_slot: bool = False,
    prepare_best_slot_review: bool = False,
    source_entry_id: str = "",
    store_id: str = "",
    body: str = "",
    location: str = "",
    teams: bool = True,
    include_shorter_slots: bool = True,
    prepare_slot_index: int = 0,
    source_mail_subject: str = "",
) -> dict[str, Any]:
    slotfinder = _slotfinder_module()
    search_start_dt = _parse_local_datetime(search_start)
    search_end_dt = _parse_local_datetime(search_end)

    # Support comma-separated values in --required / --optional
    def _split_csv(items: list[str] | None) -> list[str]:
        result: list[str] = []
        for item in (items or []):
            result.extend(part.strip() for part in item.split(",") if part.strip())
        return result

    required = _split_csv(required)
    optional = _split_csv(optional)
    mail_payload = _load_mail_context(source_mail_subject) if source_mail_subject else None

    if source_entry_id:
        context = slotfinder._load_reschedule_context(
            source_entry_id,
            store_id,
            required or [],
            optional or [],
            subject,
            duration_min,
        )
        main_participants = context["main_participants"]
        other_participants = context["other_participants"]
        effective_subject = context["subject"]
        effective_duration = context["duration_minutes"]
        ignore_entry_ids = context["ignore_entry_ids"]
        action = "suggest-reschedule-slots"
        source_payload = context["source"]
    else:
        derived_required: list[str] = []
        derived_optional: list[str] = []
        if mail_payload is not None:
            derived_required, derived_optional = _mail_recipients(mail_payload)
        main_participants = required or derived_required
        remaining_from_mail = [
            value for value in derived_required + derived_optional
            if value.lower() not in {item.lower() for item in main_participants}
        ]
        other_participants = _unique_texts((optional or []) + remaining_from_mail)
        effective_subject = (
            _coerce_text(subject).strip()
            or (_strip_reply_prefixes(mail_payload.get("subject", "")) if mail_payload is not None else "")
            or slotfinder.DEFAULT_SUBJECT
        )
        effective_duration = duration_min
        ignore_entry_ids = set()
        action = "suggest-slots"
        source_payload = None

    participants = slotfinder._combine_participants(main_participants, other_participants)
    slots = slotfinder.find_best_slots(
        search_start=search_start_dt,
        search_end=search_end_dt,
        duration_minutes=effective_duration,
        slot_minutes=slot_minutes,
        top_n=top_n,
        main_participants=main_participants,
        other_participants=other_participants,
        ignore_entry_ids=ignore_entry_ids,
        weekdays_only=not include_weekends,
        working_hour_start=working_hour_start,
        working_hour_end=working_hour_end,
        include_shorter_slots=include_shorter_slots,
    )
    if open_best_slot and slots:
        slotfinder.open_best_slot_as_meeting(slots[0], subject=effective_subject, participants=participants)

    prepared_appointment = None
    selected_slot = None
    if prepare_slot_index:
        if prepare_slot_index < 1 or prepare_slot_index > len(slots):
            raise ValueError(f"prepare_slot_index muss zwischen 1 und {len(slots)} liegen.")
        selected_slot = slots[prepare_slot_index - 1]
    elif prepare_best_slot_review and slots:
        selected_slot = slots[0]
    effective_body = body or (_mail_context_body(effective_subject, mail_payload) if mail_payload is not None else "")
    if selected_slot is not None:
        duration_for_create = int((selected_slot.end - selected_slot.start).total_seconds() // 60)
        prepared_appointment = create_appointment(
            subject=effective_subject,
            start=selected_slot.start.isoformat(),
            duration_min=duration_for_create,
            required=main_participants,
            optional=other_participants,
            body=effective_body,
            location=location,
            teams=teams,
            send_mode=SEND_MODE_REVIEW,
            normalize_start=not bool(prepare_slot_index),
        )

    payload: dict[str, Any] = {
        "status": "ok",
        "action": action,
        "subject": effective_subject,
        "criteria": {
            "search_start": search_start_dt.isoformat(),
            "search_end": search_end_dt.isoformat(),
            "duration_minutes": effective_duration,
            "slot_minutes": slot_minutes,
            "top_n": top_n,
            "weekdays_only": not include_weekends,
            "working_hour_start": working_hour_start,
            "working_hour_end": working_hour_end,
            "main_participants": main_participants,
            "other_participants": other_participants,
        },
        "best_slot_opened": bool(open_best_slot and slots),
        "best_slot_review_prepared": bool((prepare_best_slot_review or prepare_slot_index) and prepared_appointment),
        "slots": [slotfinder._slot_payload(slot) for slot in slots],
        "prepared_appointment": prepared_appointment,
    }
    if source_payload is not None:
        payload["source_appointment"] = source_payload
    if mail_payload is not None:
        payload["source_mail"] = {
            "entry_id": mail_payload.get("entry_id", ""),
            "store_id": mail_payload.get("store_id", ""),
            "subject": mail_payload.get("subject", ""),
            "conversation_id": mail_payload.get("conversation_id", ""),
        }
    return payload


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
    create_parser.add_argument("--no-normalize-start", dest="normalize_start", action="store_false", default=True)

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
    update_parser.add_argument("--no-normalize-start", dest="normalize_start", action="store_false", default=True)

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

    slot_parser = subparsers.add_parser("suggest-slots", help="Finde passende Slots fuer neue oder bestehende Termine.")
    slot_parser.add_argument("--search-start", required=True)
    slot_parser.add_argument("--search-end", required=True)
    slot_parser.add_argument("--duration-min", type=int, default=60)
    slot_parser.add_argument("--slot-minutes", type=int, default=30)
    slot_parser.add_argument("--top-n", type=int, default=10)
    slot_parser.add_argument("--required", action="append", default=[])
    slot_parser.add_argument("--optional", action="append", default=[])
    slot_parser.add_argument("--subject", default="")
    slot_parser.add_argument("--include-weekends", action="store_true")
    slot_parser.add_argument("--working-hour-start", type=int, default=8)
    slot_parser.add_argument("--working-hour-end", type=int, default=18)
    slot_parser.add_argument("--open-best-slot", action="store_true")
    slot_parser.add_argument("--prepare-best-slot-review", action="store_true")
    slot_parser.add_argument("--prepare-slot-index", type=int, default=0)
    slot_parser.add_argument("--body", default="")
    slot_parser.add_argument("--location", default="")
    slot_parser.add_argument("--teams", dest="teams", action="store_true", default=True)
    slot_parser.add_argument("--no-teams", dest="teams", action="store_false")
    slot_parser.add_argument("--source-entry-id", default="")
    slot_parser.add_argument("--store-id", default="")
    slot_parser.add_argument("--source-mail-subject", default="")
    slot_parser.add_argument("--no-shorter-slots", dest="include_shorter_slots", action="store_false", default=True,
                             help="Keine kuerzeren Alternativ-Slots anzeigen.")

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
            normalize_start=args.normalize_start,
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
            normalize_start=args.normalize_start,
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
    elif args.command == "suggest-slots":
        payload = suggest_slots(
            search_start=args.search_start,
            search_end=args.search_end,
            duration_min=args.duration_min,
            slot_minutes=args.slot_minutes,
            top_n=args.top_n,
            required=args.required,
            optional=args.optional,
            subject=args.subject,
            include_weekends=args.include_weekends,
            working_hour_start=args.working_hour_start,
            working_hour_end=args.working_hour_end,
            open_best_slot=args.open_best_slot,
            prepare_best_slot_review=args.prepare_best_slot_review,
            prepare_slot_index=args.prepare_slot_index,
            source_entry_id=args.source_entry_id,
            store_id=args.store_id,
            source_mail_subject=args.source_mail_subject,
            body=args.body,
            location=args.location,
            teams=args.teams,
            include_shorter_slots=args.include_shorter_slots,
        )
    elif args.command == "resolve-recipient":
        refresh_state: dict[str, Any] = {}
        payload = {
            "status": "ok",
            "action": "resolve-recipient",
            "results": _recipient_payload([_resolve_recipient(value, refresh_state=refresh_state) for value in args.name]),
        }
    else:
        payload = diagnostics()
    json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
