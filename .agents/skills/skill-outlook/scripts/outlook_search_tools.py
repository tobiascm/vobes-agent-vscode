from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

EXPLORER_SEARCH_SCOPES = {
    "current_folder": 0,
    "all_folders": 1,
    "all_outlook_items": 2,
    "subfolders": 3,
    "current_store": 4,
}

OL_FOLDER_DELETED_ITEMS = 3
OL_FOLDER_OUTBOX = 4
OL_FOLDER_SENT_MAIL = 5
OL_FOLDER_INBOX = 6
OL_FOLDER_CALENDAR = 9
OL_FOLDER_NOTES = 12
OL_FOLDER_TASKS = 13
OL_FOLDER_DRAFTS = 16

DEFAULT_BACKGROUND_FOLDER_IDS = (
    OL_FOLDER_INBOX,
    OL_FOLDER_SENT_MAIL,
    OL_FOLDER_DRAFTS,
    OL_FOLDER_DELETED_ITEMS,
    OL_FOLDER_OUTBOX,
    OL_FOLDER_CALENDAR,
    OL_FOLDER_TASKS,
    OL_FOLDER_NOTES,
)

SUBJECT_DASL = "urn:schemas:httpmail:subject"
BODY_DASL = "urn:schemas:httpmail:textdescription"
ADVANCED_SEARCH_TIMEOUT_SECONDS = 120.0
PR_SMTP_ADDRESS_DASL = "http://schemas.microsoft.com/mapi/proptag/0x39FE001E"
SMTP_ADDRESS_RE = re.compile(r"^[^@\s<>\"']+@[^@\s<>\"']+$")


@dataclass
class EmailRef:
    entry_id: str
    store_id: str = ""
    subject: str = ""
    sender: str = ""
    sender_name: str = ""
    to_recipients: list[str] = field(default_factory=list)
    cc_recipients: list[str] = field(default_factory=list)
    received: str | None = None
    conversation_id: str = ""
    has_attachments: bool = False
    body_preview_lines: list[str] = field(default_factory=list)
    body_has_more: bool = False


@dataclass
class SearchQuery:
    raw_query: str = ""
    keywords: list[str] = field(default_factory=list)
    sender_filters: list[str] = field(default_factory=list)
    recipient_filters: list[str] = field(default_factory=list)
    subject_must: list[str] = field(default_factory=list)
    exclude_terms: list[str] = field(default_factory=list)
    search_days: int = 90
    max_results: int = 25


class OutlookEvents:
    def __init__(self) -> None:
        self.completed: dict[str, Any] = {}
        self.stopped: set[str] = set()

    def OnAdvancedSearchComplete(self, search: Any) -> None:
        tag = _coerce_text(_safe_get(search, "Tag", ""))
        if tag:
            self.completed[tag] = search

    def OnAdvancedSearchStopped(self, search: Any) -> None:
        tag = _coerce_text(_safe_get(search, "Tag", ""))
        if tag:
            self.stopped.add(tag)


_COM_CONTEXT: tuple[Any, Any, OutlookEvents] | None = None


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\r\n", "\n").replace("\r", "\n")


def _normalize_text(value: str) -> str:
    return _coerce_text(value).strip().lower()


def _compact_keywords(values: list[str] | None) -> list[str]:
    compact: list[str] = []
    for value in values or []:
        text = _normalize_text(value)
        if text and text not in compact:
            compact.append(text)
    return compact


def _cap_recipients(values: list[str], limit: int = 10) -> list[str]:
    values = [value for value in values if value]
    if len(values) <= limit:
        return values
    hidden = len(values) - limit
    return values[:limit] + [f"[....] {hidden}"]


def _body_preview_lines(body: str, limit: int = 10) -> tuple[list[str], bool]:
    raw_lines = _coerce_text(body).split("\n")
    lines = [line.rstrip() for line in raw_lines if line.strip()]
    has_more = len(lines) > limit
    return lines[:limit], has_more


def _parse_received_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _safe_get(item: Any, name: str, default: Any = None) -> Any:
    try:
        value = getattr(item, name)
    except Exception:
        return default
    return default if value is None else value


def _com_to_local(value: Any) -> Any:
    try:
        return datetime(
            int(value.year),
            int(value.month),
            int(value.day),
            int(value.hour),
            int(value.minute),
            int(value.second),
        )
    except Exception:
        pass
    return value


def _lazy_outlook_context() -> tuple[Any, Any, OutlookEvents]:
    global _COM_CONTEXT
    if _COM_CONTEXT is not None:
        return _COM_CONTEXT
    try:
        import pythoncom  # type: ignore
        import win32com.client  # type: ignore
    except ImportError as exc:
        raise RuntimeError("Outlook COM is only available on Windows with pywin32 installed.") from exc
    pythoncom.CoInitialize()
    app = win32com.client.gencache.EnsureDispatch("Outlook.Application")
    events = win32com.client.WithEvents(app, OutlookEvents)
    namespace = app.GetNamespace("MAPI")
    _COM_CONTEXT = (app, namespace, events)
    return _COM_CONTEXT


def _get_item_by_id(entry_id: str, store_id: str = "") -> Any:
    _, namespace, _ = _lazy_outlook_context()
    if store_id:
        return namespace.GetItemFromID(entry_id, store_id)
    return namespace.GetItemFromID(entry_id)


def _normalize_smtp_address(value: Any) -> str:
    text = _coerce_text(value).strip().strip("<>").strip()
    if not text:
        return ""
    if text.lower().startswith("smtp:"):
        text = text[5:].strip()
    if not text or text.lower().startswith("/o="):
        return ""
    if not SMTP_ADDRESS_RE.fullmatch(text):
        return ""
    return text


def _property_smtp_address(value: Any) -> str:
    accessor = _safe_get(value, "PropertyAccessor")
    if accessor is None:
        return ""
    try:
        return _normalize_smtp_address(accessor.GetProperty(PR_SMTP_ADDRESS_DASL))
    except Exception:
        return ""


def _exchange_primary_smtp(address_entry: Any) -> str:
    for getter_name in ("GetExchangeUser", "GetExchangeDistributionList"):
        try:
            exchange_target = getattr(address_entry, getter_name)()
        except Exception:
            continue
        address = _normalize_smtp_address(_safe_get(exchange_target, "PrimarySmtpAddress", ""))
        if address:
            return address
    return ""


def _try_internet_address(recipient: Any) -> str:
    address_entry = _safe_get(recipient, "AddressEntry")
    if address_entry is not None:
        address = _exchange_primary_smtp(address_entry)
        if address:
            return address
        address = _property_smtp_address(address_entry)
        if address:
            return address
        address = _normalize_smtp_address(_safe_get(address_entry, "Address", ""))
        if address:
            return address
    address = _property_smtp_address(recipient)
    if address:
        return address
    try:
        address = _normalize_smtp_address(recipient.Address)
        if address:
            return address
    except Exception:
        pass
    return ""


def _recipient_display(recipient: Any) -> str:
    name = _coerce_text(_safe_get(recipient, "Name", "")).strip()
    address = _try_internet_address(recipient).strip()
    if address and name and address.lower() != name.lower():
        return f"{name} <{address}>"
    return address or name


def _extract_recipients(item: Any) -> tuple[list[str], list[str]]:
    to_values: list[str] = []
    cc_values: list[str] = []
    recipients = _safe_get(item, "Recipients")
    if recipients is None:
        return to_values, cc_values

    count = int(_safe_get(recipients, "Count", 0) or 0)
    for index in range(1, count + 1):
        try:
            recipient = recipients.Item(index)
        except Exception:
            continue
        value = _recipient_display(recipient)
        recipient_type = int(_safe_get(recipient, "Type", 0) or 0)
        if recipient_type == 2:
            cc_values.append(value)
        elif recipient_type == 1:
            to_values.append(value)
    return to_values, cc_values


def _datetime_like_to_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if hasattr(value, "astimezone") and getattr(value, "tzinfo", None) is not None:
        try:
            return value.astimezone(timezone.utc).replace(microsecond=0)
        except Exception:
            pass
    try:
        return datetime(
            int(value.year),
            int(value.month),
            int(value.day),
            int(value.hour),
            int(value.minute),
            int(value.second),
            tzinfo=timezone.utc,
        )
    except Exception:
        return None


def _datetime_like_to_iso(value: Any) -> str | None:
    dt = _datetime_like_to_utc(value)
    return dt.isoformat() if dt is not None else None


def _format_outlook_restrict_datetime(dt: datetime) -> str:
    local_dt = dt.astimezone().replace(tzinfo=None)
    return local_dt.strftime("%m/%d/%Y %I:%M %p")


def _best_item_iso_time(item: Any) -> str | None:
    for attr in ("ReceivedTime", "Start", "DueDate", "CreationTime", "LastModificationTime"):
        value = _datetime_like_to_iso(_safe_get(item, attr))
        if value:
            return value
    return None


def _folder_name(folder: Any) -> str:
    return _coerce_text(_safe_get(folder, "Name", "")).strip()


def _folder_path(folder: Any) -> str:
    return _coerce_text(_safe_get(folder, "FolderPath", "")).strip()


def _folder_store_id(folder: Any) -> str:
    value = _safe_get(folder, "StoreID", "")
    if value:
        return _coerce_text(value)
    store = _safe_get(folder, "Store")
    if store is not None:
        return _coerce_text(_safe_get(store, "StoreID", ""))
    return ""


def _mail_to_ref(item: Any) -> EmailRef:
    to_values, cc_values = _extract_recipients(item)
    body_preview, body_has_more = _body_preview_lines(_coerce_text(_safe_get(item, "Body", "")))
    parent = _safe_get(item, "Parent")
    return EmailRef(
        entry_id=_coerce_text(_safe_get(item, "EntryID", "")),
        store_id=_folder_store_id(parent),
        subject=_coerce_text(_safe_get(item, "Subject", "")),
        sender=_coerce_text(_safe_get(item, "SenderEmailAddress", "")),
        sender_name=_coerce_text(_safe_get(item, "SenderName", "")),
        to_recipients=_cap_recipients(to_values),
        cc_recipients=_cap_recipients(cc_values),
        received=_best_item_iso_time(item),
        conversation_id=_coerce_text(_safe_get(item, "ConversationID", "")),
        has_attachments=bool(
            _safe_get(item, "Attachments", None) and _safe_get(_safe_get(item, "Attachments"), "Count", 0)
        ),
        body_preview_lines=body_preview,
        body_has_more=body_has_more,
    )


def _email_search_text(email: EmailRef) -> str:
    parts = [
        email.subject,
        email.sender,
        email.sender_name,
        " ".join(email.to_recipients),
        " ".join(email.cc_recipients),
        " ".join(email.body_preview_lines),
    ]
    return _normalize_text("\n".join(parts))


def _matches_sender_filter(email: EmailRef, sender_filters: list[str]) -> bool:
    if not sender_filters:
        return True
    sender_text = _normalize_text(f"{email.sender_name}\n{email.sender}")
    return any(token in sender_text for token in sender_filters)


def _matches_recipient_filter(email: EmailRef, recipient_filters: list[str]) -> bool:
    if not recipient_filters:
        return True
    recipient_text = _normalize_text("\n".join(email.to_recipients + email.cc_recipients))
    return any(token in recipient_text for token in recipient_filters)


def _matches_filter_terms(email: EmailRef, query: SearchQuery) -> tuple[bool, list[str]]:
    haystack = _email_search_text(email)
    subject_text = _normalize_text(email.subject)
    reasons: list[str] = []

    if query.keywords:
        hits = [term for term in query.keywords if term in haystack]
        if not hits:
            return False, []
        reasons.append("keyword hits: " + ", ".join(hits[:5]))

    if query.subject_must:
        missing = [term for term in query.subject_must if term not in subject_text]
        if missing:
            return False, []
        reasons.append("subject must-haves matched")

    if query.exclude_terms:
        blocked = [term for term in query.exclude_terms if term in haystack]
        if blocked:
            return False, []

    if not _matches_sender_filter(email, query.sender_filters):
        return False, []
    if query.sender_filters:
        reasons.append("sender filter matched")

    if not _matches_recipient_filter(email, query.recipient_filters):
        return False, []
    if query.recipient_filters:
        reasons.append("recipient filter matched")

    return True, reasons


def _quote_query_term(term: str) -> str:
    text = _coerce_text(term).strip().replace('"', "'")
    if not text:
        return ""
    return f'"{text}"' if any(char.isspace() or char in "-:/" for char in text) else text


def _build_ui_query(query: SearchQuery) -> str:
    parts: list[str] = []
    raw_query = _coerce_text(query.raw_query).strip()
    if raw_query:
        parts.append(raw_query)
    for term in query.subject_must:
        parts.append(f"subject:{_quote_query_term(term)}")
    for term in query.sender_filters:
        parts.append(f"from:{_quote_query_term(term)}")
    for term in query.recipient_filters:
        parts.append(f"to:{_quote_query_term(term)}")
    for term in query.keywords:
        parts.append(_quote_query_term(term))
    ui_query = " ".join(part for part in parts if part).strip()
    if not ui_query:
        raise ValueError("search requires --query or at least one positive filter such as --keyword or --subject-must")
    return ui_query


def _address_cache_module() -> Any:
    return importlib.import_module("outlook_address_cache")


def _expand_filter_values_via_cache(
    values: list[str],
    *,
    refresh_state: dict[str, Any] | None = None,
    limit: int = 5,
) -> tuple[list[str], list[dict[str, Any]], list[str]]:
    expanded = list(values)
    expanded_seen = {value for value in values if value}
    resolutions: list[dict[str, Any]] = []
    warnings: list[str] = []
    if not values:
        return expanded, resolutions, warnings

    try:
        cache_module = _address_cache_module()
    except Exception as exc:
        warnings.append(f"address cache unavailable: {exc!r}")
        return expanded, resolutions, warnings

    for value in values:
        try:
            payload = cache_module.lookup_cached_addresses(
                value,
                limit=limit,
                refresh_state=refresh_state,
            )
        except Exception as exc:
            warnings.append(f"address cache lookup failed for {value!r}: {exc!r}")
            continue

        matches = payload.get("matches", [])
        resolution = {
            "query": value,
            "match_count": len(matches),
            "refreshed": bool(payload.get("refreshed")),
            "refresh_reason": payload.get("refresh_reason"),
            "matches": [
                {
                    "email": match.get("email", ""),
                    "display_name": match.get("display_name", ""),
                }
                for match in matches
            ],
        }
        if payload.get("warnings"):
            resolution["warnings"] = list(payload["warnings"])
            warnings.extend(str(warning) for warning in payload["warnings"])
        resolutions.append(resolution)

        for match in matches:
            for token in (_normalize_text(match.get("email", "")), _normalize_text(match.get("display_name", ""))):
                if token and token not in expanded_seen:
                    expanded.append(token)
                    expanded_seen.add(token)

    return expanded, resolutions, warnings


def _sql_quote(value: str) -> str:
    return _coerce_text(value).replace("'", "''")


def _like_quote(value: str) -> str:
    return _sql_quote(value).replace("%", "[%]").replace("_", "[_]")


def _search_tokens(term: str) -> list[str]:
    raw = _coerce_text(term).strip()
    tokens = [token for token in re.split(r"[^\w]+", raw) if token]
    if len(tokens) > 1:
        return tokens
    return [raw] if raw else []


def _build_text_token_clause(term: str, *, indexed: bool) -> str:
    if indexed:
        quoted = _sql_quote(term)
        return (
            f'("{SUBJECT_DASL}" ci_phrasematch \'{quoted}\' '
            f'OR "{BODY_DASL}" ci_phrasematch \'{quoted}\')'
        )
    quoted = _like_quote(term)
    return (
        f'("{SUBJECT_DASL}" like \'%{quoted}%\' '
        f'OR "{BODY_DASL}" like \'%{quoted}%\')'
    )


def _build_text_clause(term: str, *, indexed: bool) -> str:
    parts = [_build_text_token_clause(token, indexed=indexed) for token in _search_tokens(term)]
    return " AND ".join(f"({part})" for part in parts)


def _build_subject_token_clause(term: str, *, indexed: bool) -> str:
    if indexed:
        return f'"{SUBJECT_DASL}" ci_phrasematch \'{_sql_quote(term)}\''
    return f'"{SUBJECT_DASL}" like \'%{_like_quote(term)}%\''


def _build_subject_clause(term: str, *, indexed: bool) -> str:
    parts = [_build_subject_token_clause(token, indexed=indexed) for token in _search_tokens(term)]
    return " AND ".join(f"({part})" for part in parts)


def _build_advanced_filter(query: SearchQuery, *, indexed: bool) -> str:
    clauses: list[str] = []
    raw_query = _coerce_text(query.raw_query).strip()
    if raw_query:
        clauses.append(_build_text_clause(raw_query, indexed=indexed))
    for term in query.keywords:
        clauses.append(_build_text_clause(term, indexed=indexed))
    for term in query.subject_must:
        clauses.append(_build_subject_clause(term, indexed=indexed))
    if not clauses:
        return ""
    return " AND ".join(f"({clause})" for clause in clauses)


def _store_debug_payload(store: Any) -> dict[str, Any]:
    return {
        "display_name": _coerce_text(_safe_get(store, "DisplayName", "")),
        "store_id": _coerce_text(_safe_get(store, "StoreID", "")),
        "file_path": _coerce_text(_safe_get(store, "FilePath", "")),
        "exchange_store_type": _coerce_text(_safe_get(store, "ExchangeStoreType", "")),
        "is_cached_exchange": bool(_safe_get(store, "IsCachedExchange", False)),
        "is_instant_search_enabled": bool(_safe_get(store, "IsInstantSearchEnabled", False)),
        "is_open": bool(_safe_get(store, "IsOpen", False)),
    }


def _folder_debug_payload(folder: Any) -> dict[str, Any]:
    store = _safe_get(folder, "Store")
    return {
        "name": _folder_name(folder),
        "folder_path": _folder_path(folder),
        "store_id": _folder_store_id(folder),
        "store": _store_debug_payload(store) if store is not None else {},
    }


def _mail_item_debug_payload(item: Any, *, roundtrip_item: Any | None = None) -> dict[str, Any]:
    parent = _safe_get(item, "Parent")
    payload = {
        "entry_id": _coerce_text(_safe_get(item, "EntryID", "")),
        "subject": _coerce_text(_safe_get(item, "Subject", "")),
        "sender": _coerce_text(_safe_get(item, "SenderEmailAddress", "")),
        "sender_name": _coerce_text(_safe_get(item, "SenderName", "")),
        "received": _best_item_iso_time(item),
        "conversation_id": _coerce_text(_safe_get(item, "ConversationID", "")),
        "message_class": _coerce_text(_safe_get(item, "MessageClass", "")),
        "parent": _folder_debug_payload(parent) if parent is not None else {},
    }
    if roundtrip_item is not None:
        roundtrip_parent = _safe_get(roundtrip_item, "Parent")
        payload["get_item_from_id"] = {
            "ok": True,
            "subject": _coerce_text(_safe_get(roundtrip_item, "Subject", "")),
            "folder_path": _folder_path(roundtrip_parent),
            "store_id": _folder_store_id(roundtrip_parent),
        }
    return payload


def inspect_selected_email() -> dict[str, Any]:
    app, namespace, _ = _lazy_outlook_context()
    item = None
    selection_source = ""

    try:
        explorer = app.ActiveExplorer()
    except Exception:
        explorer = None
    if explorer is not None:
        selection = _safe_get(explorer, "Selection")
        count = int(_safe_get(selection, "Count", 0) or 0)
        if count >= 1:
            try:
                item = selection.Item(1)
                selection_source = "active_explorer_selection"
            except Exception:
                item = None

    if item is None:
        try:
            inspector = app.ActiveInspector()
        except Exception:
            inspector = None
        if inspector is not None:
            item = _safe_get(inspector, "CurrentItem")
            if item is not None:
                selection_source = "active_inspector_current_item"

    if item is None:
        raise RuntimeError("No selected or open Outlook item found.")

    entry_id = _coerce_text(_safe_get(item, "EntryID", ""))
    parent = _safe_get(item, "Parent")
    store_id = _folder_store_id(parent)
    roundtrip_item = None
    roundtrip_error = ""
    if entry_id:
        try:
            roundtrip_item = _get_item_by_id(entry_id, store_id)
        except Exception as exc:
            roundtrip_error = repr(exc)

    stores_payload = []
    stores = _safe_get(namespace, "Stores")
    count = int(_safe_get(stores, "Count", 0) or 0)
    for index in range(1, count + 1):
        try:
            store = stores.Item(index)
        except Exception:
            continue
        stores_payload.append(_store_debug_payload(store))

    payload = {
        "mode": "inspect-selection",
        "selection_source": selection_source,
        "selected_item": _mail_item_debug_payload(item, roundtrip_item=roundtrip_item),
        "visible_stores": stores_payload,
        "warnings": [],
    }
    if roundtrip_error:
        payload["warnings"].append(f"GetItemFromID failed: {roundtrip_error}")
    return payload


def _explorer_search_refs(
    ui_query: str,
    *,
    scope: str = "all_folders",
    wait_seconds: float = 5.0,
    max_results: int = 25,
) -> tuple[list[EmailRef], dict[str, Any], list[str]]:
    app, _, _ = _lazy_outlook_context()
    try:
        explorer = app.ActiveExplorer()
    except Exception as exc:
        raise RuntimeError("No active Outlook explorer window found.") from exc
    if explorer is None:
        raise RuntimeError("No active Outlook explorer window found.")

    scope_key = _normalize_text(scope)
    if scope_key not in EXPLORER_SEARCH_SCOPES:
        raise ValueError(f"Unsupported explorer search scope: {scope}")

    warnings: list[str] = []
    try:
        explorer.ClearSearch()
        time.sleep(0.5)
    except Exception as exc:
        warnings.append(f"ClearSearch failed: {exc!r}")

    explorer.Search(ui_query, EXPLORER_SEARCH_SCOPES[scope_key])
    time.sleep(max(wait_seconds, 0.0))

    try:
        explorer.SelectAllItems()
    except Exception as exc:
        warnings.append(f"SelectAllItems failed: {exc!r}")

    selection = _safe_get(explorer, "Selection")
    selection_count = int(_safe_get(selection, "Count", 0) or 0)
    refs: list[EmailRef] = []
    for index in range(1, min(selection_count, max_results) + 1):
        try:
            item = selection.Item(index)
        except Exception as exc:
            warnings.append(f"Selection item {index} failed: {exc!r}")
            continue
        message_class = _coerce_text(_safe_get(item, "MessageClass", ""))
        if not message_class.startswith("IPM.Note"):
            continue
        refs.append(_mail_to_ref(item))

    meta = {
        "query": ui_query,
        "scope": scope_key,
        "wait_seconds": wait_seconds,
        "max_results": max_results,
        "current_folder": _folder_path(_safe_get(explorer, "CurrentFolder")),
        "selection_count": selection_count,
    }
    return refs, meta, warnings


def _has_instant_search(store: Any) -> bool:
    return bool(_safe_get(store, "IsInstantSearchEnabled", False))


def _get_default_folder_path(store: Any, folder_id: int) -> str | None:
    try:
        folder = store.GetDefaultFolder(folder_id)
    except Exception:
        return None
    path = _folder_path(folder)
    return path or None


def _build_store_scope_paths(store: Any) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()

    def add_path(path: str | None) -> None:
        if not path or not path.startswith("\\\\") or path in seen:
            return
        seen.add(path)
        paths.append(path)

    for folder_id in DEFAULT_BACKGROUND_FOLDER_IDS:
        add_path(_get_default_folder_path(store, folder_id))

    wanted_root_names = {
        "posteingang",
        "gesendete elemente",
        "entwürfe",
        "entwurfe",
        "gelöschte elemente",
        "geloschte elemente",
        "postausgang",
        "kalender",
        "aufgaben",
        "notizen",
        "archiv",
        "archive",
    }
    try:
        root = store.GetRootFolder()
        folders = root.Folders
        for index in range(1, int(_safe_get(folders, "Count", 0) or 0) + 1):
            folder = folders.Item(index)
            if _normalize_text(_folder_name(folder)) in wanted_root_names:
                add_path(_folder_path(folder))
    except Exception:
        pass
    return paths


def _scope_string(paths: list[str]) -> str:
    quoted_paths = []
    for path in paths:
        quoted_paths.append("'" + path.replace("'", "''") + "'")
    return ", ".join(quoted_paths)


def _advanced_search_tags_done(events: OutlookEvents, tags: set[str]) -> set[str]:
    return {tag for tag in tags if tag in events.completed or tag in events.stopped}


def _wait_for_advanced_searches(events: OutlookEvents, tags: set[str], timeout_seconds: float) -> set[str]:
    if not tags:
        return set()
    import pythoncom  # type: ignore

    deadline = time.time() + timeout_seconds
    while True:
        done = _advanced_search_tags_done(events, tags)
        if done == tags:
            return set()
        if time.time() >= deadline:
            return tags - done
        pythoncom.PumpWaitingMessages()
        time.sleep(0.05)


def _row_value(row: Any, name: str, default: Any = None) -> Any:
    try:
        return row[name]
    except Exception:
        pass
    try:
        return row.Item(name)
    except Exception:
        pass
    try:
        return row(name)
    except Exception:
        pass
    try:
        return getattr(row, name)
    except Exception:
        return default


def _entry_ids_from_search(search: Any) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    entry_ids: list[str] = []

    try:
        table = search.GetTable()
        while not bool(_safe_get(table, "EndOfTable", True)):
            row = table.GetNextRow()
            entry_id = _coerce_text(_row_value(row, "EntryID", ""))
            if entry_id:
                entry_ids.append(entry_id)
        return entry_ids, warnings
    except Exception as exc:
        warnings.append(f"Search.GetTable failed, falling back to Search.Results: {exc!r}")

    results = _safe_get(search, "Results")
    count = int(_safe_get(results, "Count", 0) or 0)
    for index in range(1, count + 1):
        try:
            item = results.Item(index)
        except Exception as exc:
            warnings.append(f"Search.Results item {index} failed: {exc!r}")
            continue
        entry_id = _coerce_text(_safe_get(item, "EntryID", ""))
        if entry_id:
            entry_ids.append(entry_id)
    return entry_ids, warnings


def _advanced_search_refs(query: SearchQuery, *, timeout_seconds: float = ADVANCED_SEARCH_TIMEOUT_SECONDS) -> tuple[list[EmailRef], dict[str, Any], list[str]]:
    app, namespace, events = _lazy_outlook_context()
    stores = _safe_get(namespace, "Stores")
    store_count = int(_safe_get(stores, "Count", 0) or 0)

    launched: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []

    for index in range(1, store_count + 1):
        try:
            store = stores.Item(index)
        except Exception as exc:
            warnings.append(f"Store {index} could not be read: {exc!r}")
            continue

        paths = _build_store_scope_paths(store)
        if not paths:
            continue

        store_id = _coerce_text(_safe_get(store, "StoreID", ""))
        store_name = _coerce_text(_safe_get(store, "DisplayName", f"Store {index}"))
        scope = _scope_string(paths)
        indexed = _has_instant_search(store)
        filter_text = _build_advanced_filter(query, indexed=indexed)
        tag = f"codex-advanced-search::{index}::{int(time.time() * 1000)}"
        events.completed.pop(tag, None)
        events.stopped.discard(tag)

        search = None
        used_indexed = indexed
        try:
            search = app.AdvancedSearch(scope, filter_text, True, tag)
        except Exception as exc:
            if indexed and filter_text:
                try:
                    search = app.AdvancedSearch(scope, _build_advanced_filter(query, indexed=False), True, tag)
                    used_indexed = False
                    warnings.append(f"{store_name}: indexed AdvancedSearch failed, fell back to like-filter.")
                except Exception as fallback_exc:
                    warnings.append(f"{store_name}: AdvancedSearch launch failed: {fallback_exc!r}")
                    continue
            else:
                warnings.append(f"{store_name}: AdvancedSearch launch failed: {exc!r}")
                continue

        launched[tag] = {
            "search": search,
            "store_id": store_id,
            "store_name": store_name,
            "scope_paths": paths,
            "indexed": used_indexed,
        }

    if not launched:
        return [], {"stores": []}, warnings

    pending = _wait_for_advanced_searches(events, set(launched), timeout_seconds)
    for tag in sorted(pending):
        meta = launched[tag]
        warnings.append(f"{meta['store_name']}: AdvancedSearch timed out after {int(timeout_seconds)}s.")
        try:
            meta["search"].Stop()
        except Exception:
            pass

    refs: list[EmailRef] = []
    store_summaries: list[dict[str, Any]] = []
    for tag, meta in launched.items():
        store_summaries.append(
            {
                "store_name": meta["store_name"],
                "store_id": meta["store_id"],
                "indexed": meta["indexed"],
                "scope_paths": meta["scope_paths"],
            }
        )
        search = events.completed.get(tag)
        if search is None:
            continue

        entry_ids, row_warnings = _entry_ids_from_search(search)
        warnings.extend(f"{meta['store_name']}: {warning}" for warning in row_warnings)

        seen_entry_ids: set[str] = set()
        for entry_id in entry_ids:
            if not entry_id or entry_id in seen_entry_ids:
                continue
            seen_entry_ids.add(entry_id)
            try:
                item = _get_item_by_id(entry_id, meta["store_id"])
            except Exception as exc:
                warnings.append(f"{meta['store_name']}: GetItemFromID failed for one result: {exc!r}")
                continue
            refs.append(_mail_to_ref(item))

    meta = {
        "stores": store_summaries,
        "timeout_seconds": timeout_seconds,
    }
    return refs, meta, warnings[:50]


def _validate_search_query(query: SearchQuery) -> None:
    if any(
        (
            _coerce_text(query.raw_query).strip(),
            query.keywords,
            query.sender_filters,
            query.recipient_filters,
            query.subject_must,
            query.exclude_terms,
        )
    ):
        return
    raise ValueError("search requires at least one filter such as --query, --keyword, --sender or --subject-must")


def search_emails(
    *,
    raw_query: str = "",
    keywords: list[str] | None = None,
    sender_filters: list[str] | None = None,
    recipient_filters: list[str] | None = None,
    subject_must: list[str] | None = None,
    exclude_terms: list[str] | None = None,
    search_days: int = 90,
    max_results: int = 25,
    search_ui: bool = False,
    scope: str = "all_folders",
    wait_seconds: float = 5.0,
) -> dict[str, Any]:
    query = SearchQuery(
        raw_query=_coerce_text(raw_query).strip(),
        keywords=_compact_keywords(keywords),
        sender_filters=_compact_keywords(sender_filters),
        recipient_filters=_compact_keywords(recipient_filters),
        subject_must=_compact_keywords(subject_must),
        exclude_terms=_compact_keywords(exclude_terms),
        search_days=search_days,
        max_results=max_results,
    )
    _validate_search_query(query)
    refresh_state: dict[str, Any] = {}
    expanded_sender_filters, sender_cache_resolution, sender_cache_warnings = _expand_filter_values_via_cache(
        query.sender_filters,
        refresh_state=refresh_state,
    )
    expanded_recipient_filters, recipient_cache_resolution, recipient_cache_warnings = _expand_filter_values_via_cache(
        query.recipient_filters,
        refresh_state=refresh_state,
    )
    match_query = SearchQuery(
        raw_query=query.raw_query,
        keywords=list(query.keywords),
        sender_filters=expanded_sender_filters,
        recipient_filters=expanded_recipient_filters,
        subject_must=list(query.subject_must),
        exclude_terms=list(query.exclude_terms),
        search_days=query.search_days,
        max_results=query.max_results,
    )
    cache_resolution = {
        "sender": sender_cache_resolution,
        "recipient": recipient_cache_resolution,
    }
    cache_warnings = sender_cache_warnings + recipient_cache_warnings

    if search_ui:
        ui_query = _build_ui_query(query)
        refs, meta, warnings = _explorer_search_refs(
            ui_query,
            scope=scope,
            wait_seconds=wait_seconds,
            max_results=max_results,
        )

        cutoff = datetime.now(timezone.utc) - timedelta(days=search_days)
        dedupe: set[tuple[str, str]] = set()
        matches: list[dict[str, Any]] = []
        for ref in refs:
            key = (ref.store_id, ref.entry_id)
            if key in dedupe:
                continue
            dedupe.add(key)
            received_dt = _parse_received_iso(ref.received)
            if received_dt and received_dt < cutoff:
                continue
            matched, reasons = _matches_filter_terms(ref, match_query)
            if not matched:
                continue
            matches.append(
                {
                    "reasons": reasons + ["explorer search matched"],
                    "email": asdict(ref),
                }
            )

        matches.sort(key=lambda match: match["email"].get("received") or "", reverse=True)
        return {
            "mode": "search",
            "query": {
                "raw_query": query.raw_query,
                "keywords": query.keywords,
                "sender": query.sender_filters,
                "recipient": query.recipient_filters,
                "subject_must": query.subject_must,
                "exclude_terms": query.exclude_terms,
                "search_days": search_days,
                "max_results": max_results,
                "scope": meta["scope"],
                "wait_seconds": meta["wait_seconds"],
                "ui_query": meta["query"],
                "cache_resolution": cache_resolution,
            },
            "current_folder": meta["current_folder"],
            "selection_count": meta["selection_count"],
            "matches": matches[:max_results],
            "warnings": (warnings + cache_warnings)[:10],
        }

    refs, meta, warnings = _advanced_search_refs(query)
    cutoff = datetime.now(timezone.utc) - timedelta(days=search_days)
    dedupe: set[tuple[str, str]] = set()
    matches: list[dict[str, Any]] = []
    for ref in refs:
        key = (ref.store_id, ref.entry_id)
        if key in dedupe:
            continue
        dedupe.add(key)
        received_dt = _parse_received_iso(ref.received)
        if received_dt and received_dt < cutoff:
            continue
        matched, reasons = _matches_filter_terms(ref, match_query)
        if not matched:
            continue
        matches.append(
            {
                "reasons": reasons + ["advanced search matched"],
                "email": asdict(ref),
            }
        )

    matches.sort(key=lambda match: match["email"].get("received") or "", reverse=True)
    return {
        "mode": "search",
        "engine": "advanced_search",
        "query": {
            "raw_query": query.raw_query,
            "keywords": query.keywords,
            "sender": query.sender_filters,
            "recipient": query.recipient_filters,
            "subject_must": query.subject_must,
            "exclude_terms": query.exclude_terms,
            "search_days": search_days,
            "max_results": max_results,
            "search_ui": False,
            "cache_resolution": cache_resolution,
        },
        "stores": meta["stores"],
        "matches": matches[:max_results],
        "warnings": (warnings + cache_warnings)[:20],
    }


def outlook_read_email(entry_id: str, store_id: str = "", *, include_body: bool = True) -> dict[str, Any]:
    item = _get_item_by_id(entry_id, store_id)
    to_values, cc_values = _extract_recipients(item)
    body = _coerce_text(_safe_get(item, "Body", ""))
    preview_lines, body_has_more = _body_preview_lines(body)
    payload = {
        "entry_id": _coerce_text(_safe_get(item, "EntryID", "")),
        "store_id": store_id,
        "subject": _coerce_text(_safe_get(item, "Subject", "")),
        "sender": _coerce_text(_safe_get(item, "SenderEmailAddress", "")),
        "sender_name": _coerce_text(_safe_get(item, "SenderName", "")),
        "to_recipients": to_values,
        "cc_recipients": cc_values,
        "received": _best_item_iso_time(item),
        "conversation_id": _coerce_text(_safe_get(item, "ConversationID", "")),
        "has_attachments": bool(
            _safe_get(item, "Attachments", None) and _safe_get(_safe_get(item, "Attachments"), "Count", 0)
        ),
        "body_preview_lines": preview_lines,
        "body_has_more": body_has_more,
    }
    if include_body:
        payload["body"] = body
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Classic Outlook search and diagnostics.",
        epilog=(
            "Subcommand help:\n"
            "  python .\\scripts\\outlook_search_tools.py search --help\n"
            "  python .\\scripts\\outlook_search_tools.py read-email --help\n"
            "  python .\\scripts\\outlook_search_tools.py inspect-selection --help"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search", help="Search Outlook in background or via the visible Explorer UI.")
    search_parser.add_argument(
        "--query",
        default="",
        help="Freitext fuer den Standardpfad. Mit --search-ui wird der Wert unveraendert an Explorer.Search uebergeben.",
    )
    search_parser.add_argument(
        "--keyword",
        action="append",
        default=[],
        help="Zusatzbegriff. Kann mehrfach angegeben werden.",
    )
    search_parser.add_argument(
        "--sender",
        action="append",
        default=[],
        help="Absenderfilter. Wirkt im Standardpfad als Nachfilter, im UI-Pfad als from:<wert>.",
    )
    search_parser.add_argument(
        "--recipient",
        action="append",
        default=[],
        help="Empfaengerfilter. Wirkt im Standardpfad als Nachfilter, im UI-Pfad als to:<wert>.",
    )
    search_parser.add_argument(
        "--subject-must",
        action="append",
        default=[],
        help="Betreffbegriff, der enthalten sein muss. Kann mehrfach angegeben werden.",
    )
    search_parser.add_argument(
        "--exclude-term",
        action="append",
        default=[],
        help="Begriff, der Treffer nach dem Suchlauf lokal ausschliesst. Kann mehrfach angegeben werden.",
    )
    search_parser.add_argument(
        "--search-days",
        type=int,
        default=90,
        help="Nur Treffer der letzten N Tage behalten. Filter wirkt nach dem Suchlauf.",
    )
    search_parser.add_argument(
        "--max-results",
        type=int,
        default=25,
        help="Maximale Anzahl ausgegebener Treffer.",
    )
    search_parser.add_argument(
        "--search-ui",
        action="store_true",
        help="Nutze exakt den bisherigen Explorer/UI-Suchpfad. Ohne diese Option wird die stille Hintergrundsuche via AdvancedSearch verwendet.",
    )
    search_parser.add_argument(
        "--scope",
        choices=sorted(EXPLORER_SEARCH_SCOPES.keys()),
        default=None,
        help="Explorer.Search-Scope. Nur zusammen mit --search-ui erlaubt.",
    )
    search_parser.add_argument(
        "--wait-seconds",
        type=float,
        default=None,
        help="Wartezeit nach Explorer.Search, bevor die aktuelle Auswahl ausgelesen wird. Nur mit --search-ui erlaubt.",
    )

    read_parser = subparsers.add_parser("read-email", help="Read one email, optionally with full body.")
    read_parser.add_argument("--entry-id", required=True, help="Outlook EntryID der Mail.")
    read_parser.add_argument("--store-id", default="", help="Optionale Outlook StoreID der Mail.")
    read_parser.add_argument("--no-body", action="store_true", help="Body nicht mit ausgeben.")

    subparsers.add_parser(
        "inspect-selection",
        help="Inspect the currently selected or open Outlook item, including EntryID/StoreID/folder path.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "search":
        if not args.search_ui:
            if args.scope is not None:
                parser.error("--scope requires --search-ui")
            if args.wait_seconds is not None:
                parser.error("--wait-seconds requires --search-ui")
        payload = search_emails(
            raw_query=args.query,
            keywords=args.keyword,
            sender_filters=args.sender,
            recipient_filters=args.recipient,
            subject_must=args.subject_must,
            exclude_terms=args.exclude_term,
            search_days=args.search_days,
            max_results=args.max_results,
            search_ui=args.search_ui,
            scope=args.scope or "all_folders",
            wait_seconds=args.wait_seconds if args.wait_seconds is not None else 5.0,
        )
    elif args.command == "inspect-selection":
        payload = inspect_selected_email()
    else:
        payload = outlook_read_email(
            args.entry_id,
            args.store_id,
            include_body=not args.no_body,
        )

    json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
