from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[3]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from outlook_search_tools import (  # type: ignore  # noqa: E402
    _coerce_text,
    _datetime_like_to_utc,
    _folder_path,
    _folder_store_id,
    _folder_name,
    _format_outlook_restrict_datetime,
    _lazy_outlook_context,
    _normalize_smtp_address,
    _safe_get,
    _try_internet_address,
)

OL_FOLDER_SENT_MAIL = 5
INBOX_NAMES = {"inbox", "posteingang"}
ARCHIVE_NAMES = {"archive", "archiv", "online archive", "onlinearchiv", "online-archiv"}
SENT_NAMES = {"sent items", "gesendete elemente"}
FOLDER_CHOICES = ("inbox", "archive", "sent")
SCAN_STATE_KEY = "last_successful_scan_utc"
STALE_AFTER = timedelta(days=1)

USERDATA_DIR = REPO_ROOT / "userdata" / "outlook"
DB_PATH = USERDATA_DIR / "address_cache.db"
LOGS_DIR = REPO_ROOT / "userdata" / "tmp" / "logs"


@dataclass(frozen=True)
class ScanFolder:
    folder: Any
    store_id: str
    store_name: str
    folder_path: str
    source_kind: str  # inbox | archive | sent
    filter_field: str  # ReceivedTime | SentOn


@dataclass
class AddressStat:
    email: str
    display_name: str
    inbound_count: int = 0
    outbound_count: int = 0
    sender_count: int = 0
    recipient_count: int = 0


class ScanError(RuntimeError):
    pass


def setup_logging(verbose: bool = False) -> logging.Logger:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("outlook_address_cache")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    log_path = LOGS_DIR / f"outlook_address_cache_{datetime.now():%Y%m%d_%H%M%S}.log"
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.debug("Logdatei: %s", log_path)
    return logger


def _normalize_text(value: str) -> str:
    return _coerce_text(value).strip().lower()


def _safe_iter_folders(folder: Any) -> Iterable[Any]:
    folders = _safe_get(folder, "Folders")
    count = int(_safe_get(folders, "Count", 0) or 0)
    for index in range(1, count + 1):
        try:
            yield folders.Item(index)
        except Exception:
            continue


def _iter_folder_tree(folder: Any) -> Iterable[Any]:
    yield folder
    for child in _safe_iter_folders(folder):
        yield from _iter_folder_tree(child)


def _store_display_name(store: Any) -> str:
    return _coerce_text(_safe_get(store, "DisplayName", "")).strip()


def _folder_identity(folder: Any) -> tuple[str, str]:
    return (_folder_store_id(folder), _folder_path(folder))


def _add_scan_folder(target: dict[tuple[str, str], ScanFolder], folder: Any, *, source_kind: str, filter_field: str) -> None:
    path = _folder_path(folder)
    if not path:
        return
    store = _safe_get(folder, "Store")
    store_id = _folder_store_id(folder)
    target[(store_id, path)] = ScanFolder(
        folder=folder,
        store_id=store_id,
        store_name=_store_display_name(store),
        folder_path=path,
        source_kind=source_kind,
        filter_field=filter_field,
    )


def _discover_scan_folders(logger: logging.Logger, *, folder_filters: set[str] | None = None) -> list[ScanFolder]:
    _, namespace, _ = _lazy_outlook_context()
    stores = _safe_get(namespace, "Stores")
    store_count = int(_safe_get(stores, "Count", 0) or 0)
    scan_folders: dict[tuple[str, str], ScanFolder] = {}
    filters = set(folder_filters or ())

    for store_index in range(1, store_count + 1):
        try:
            store = stores.Item(store_index)
        except Exception as exc:
            logger.warning("Store %s konnte nicht gelesen werden: %r", store_index, exc)
            continue

        store_name = _store_display_name(store)
        logger.debug("Pruefe Store: %s", store_name)

        try:
            sent_folder = store.GetDefaultFolder(OL_FOLDER_SENT_MAIL)
        except Exception:
            sent_folder = None
        if sent_folder is not None and (not filters or "sent" in filters):
            for folder in _iter_folder_tree(sent_folder):
                _add_scan_folder(scan_folders, folder, source_kind="sent", filter_field="SentOn")

        try:
            root = store.GetRootFolder()
        except Exception as exc:
            logger.warning("RootFolder fuer Store %s nicht lesbar: %r", store_name, exc)
            continue

        for folder in _iter_folder_tree(root):
            name_norm = _normalize_text(_folder_name(folder))
            if name_norm in INBOX_NAMES and (not filters or "inbox" in filters):
                for subtree_folder in _iter_folder_tree(folder):
                    _add_scan_folder(scan_folders, subtree_folder, source_kind="inbox", filter_field="ReceivedTime")
            elif name_norm in ARCHIVE_NAMES and (not filters or "archive" in filters):
                for subtree_folder in _iter_folder_tree(folder):
                    _add_scan_folder(scan_folders, subtree_folder, source_kind="archive", filter_field="ReceivedTime")
            elif name_norm in SENT_NAMES and (not filters or "sent" in filters):
                for subtree_folder in _iter_folder_tree(folder):
                    _add_scan_folder(scan_folders, subtree_folder, source_kind="sent", filter_field="SentOn")

    ordered = sorted(scan_folders.values(), key=lambda item: (item.store_name.lower(), item.folder_path.lower()))
    logger.info("%s Scan-Ordner gefunden.", len(ordered))
    return ordered


def _iso_utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _parse_iso_utc(value: str | None) -> datetime | None:
    text = _coerce_text(value).strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _message_datetime(item: Any, source_kind: str) -> datetime | None:
    attr_order = ["SentOn"] if source_kind == "sent" else ["ReceivedTime", "CreationTime", "LastModificationTime"]
    for attr in attr_order:
        dt = _datetime_like_to_utc(_safe_get(item, attr))
        if dt is not None:
            return dt
    return None


def _item_is_mail(item: Any) -> bool:
    message_class = _coerce_text(_safe_get(item, "MessageClass", ""))
    return message_class.startswith("IPM.Note")


def _sender_address(item: Any) -> tuple[str, str]:
    sender_name = _coerce_text(_safe_get(item, "SenderName", "")).strip()

    sender = _safe_get(item, "Sender")
    if sender is not None:
        address = _try_internet_address(sender).strip()
        if address:
            return address.lower(), sender_name

    sender_email_address = _normalize_smtp_address(_safe_get(item, "SenderEmailAddress", ""))
    if sender_email_address:
        return sender_email_address.lower(), sender_name

    return "", sender_name


def _iter_recipients(item: Any) -> Iterable[tuple[str, str, int]]:
    recipients = _safe_get(item, "Recipients")
    count = int(_safe_get(recipients, "Count", 0) or 0)
    for index in range(1, count + 1):
        try:
            recipient = recipients.Item(index)
        except Exception:
            continue
        address = _try_internet_address(recipient).strip().lower()
        name = _coerce_text(_safe_get(recipient, "Name", "")).strip()
        recipient_type = int(_safe_get(recipient, "Type", 0) or 0)
        yield address, name, recipient_type


def _purge_non_smtp_cache_entries(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        DELETE FROM address_observations
         WHERE trim(email) = ''
            OR instr(email, '@') = 0
            OR lower(email) LIKE '/o=%'
        """
    )
    conn.execute(
        """
        DELETE FROM addresses
         WHERE trim(email) = ''
            OR instr(email, '@') = 0
            OR lower(email) LIKE '/o=%'
        """
    )


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA journal_mode=WAL;
        PRAGMA foreign_keys=ON;

        CREATE TABLE IF NOT EXISTS scan_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS scan_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            force_full INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            folders_scanned INTEGER NOT NULL DEFAULT 0,
            messages_seen INTEGER NOT NULL DEFAULT 0,
            addresses_upserted INTEGER NOT NULL DEFAULT 0,
            details_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS scanned_messages (
            store_id TEXT NOT NULL,
            entry_id TEXT NOT NULL,
            folder_path TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            message_time_utc TEXT,
            subject TEXT,
            last_seen_scan_utc TEXT NOT NULL,
            PRIMARY KEY (store_id, entry_id)
        );

        CREATE TABLE IF NOT EXISTS addresses (
            email TEXT PRIMARY KEY,
            display_name TEXT NOT NULL DEFAULT '',
            first_seen_utc TEXT,
            last_seen_utc TEXT,
            seen_count INTEGER NOT NULL DEFAULT 0,
            inbound_count INTEGER NOT NULL DEFAULT 0,
            outbound_count INTEGER NOT NULL DEFAULT 0,
            sender_count INTEGER NOT NULL DEFAULT 0,
            recipient_count INTEGER NOT NULL DEFAULT 0,
            last_source_kind TEXT NOT NULL DEFAULT '',
            last_folder_path TEXT NOT NULL DEFAULT '',
            last_store_id TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS address_observations (
            store_id TEXT NOT NULL,
            entry_id TEXT NOT NULL,
            email TEXT NOT NULL,
            role TEXT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            source_kind TEXT NOT NULL,
            folder_path TEXT NOT NULL,
            message_time_utc TEXT,
            PRIMARY KEY (store_id, entry_id, email, role)
        );

        CREATE INDEX IF NOT EXISTS idx_scanned_messages_time ON scanned_messages(message_time_utc);
        CREATE INDEX IF NOT EXISTS idx_observations_email ON address_observations(email);
        CREATE INDEX IF NOT EXISTS idx_observations_message ON address_observations(store_id, entry_id);
        """
    )


def _reset_full_scan(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM address_observations")
    conn.execute("DELETE FROM scanned_messages")
    conn.execute("DELETE FROM addresses")
    conn.execute("DELETE FROM scan_state WHERE key = ?", (SCAN_STATE_KEY,))


def _get_last_scan_utc(conn: sqlite3.Connection) -> datetime | None:
    row = conn.execute("SELECT value FROM scan_state WHERE key = ?", (SCAN_STATE_KEY,)).fetchone()
    return _parse_iso_utc(row[0] if row else None)


def _set_last_scan_utc(conn: sqlite3.Connection, value: str) -> None:
    conn.execute(
        "INSERT INTO scan_state(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (SCAN_STATE_KEY, value),
    )


def _start_run(conn: sqlite3.Connection, *, force_full: bool, started_at: str) -> int:
    cur = conn.execute(
        "INSERT INTO scan_runs(started_at, force_full, status) VALUES(?, ?, 'running')",
        (started_at, 1 if force_full else 0),
    )
    return int(cur.lastrowid)


def _finish_run(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    status: str,
    finished_at: str,
    folders_scanned: int,
    messages_seen: int,
    addresses_upserted: int,
    details: dict[str, Any],
) -> None:
    conn.execute(
        """
        UPDATE scan_runs
           SET finished_at = ?,
               status = ?,
               folders_scanned = ?,
               messages_seen = ?,
               addresses_upserted = ?,
               details_json = ?
         WHERE id = ?
        """,
        (
            finished_at,
            status,
            folders_scanned,
            messages_seen,
            addresses_upserted,
            json.dumps(details, ensure_ascii=False, sort_keys=True),
            run_id,
        ),
    )


def _restrict_items(folder: Any, filter_field: str, last_scan_utc: datetime | None, logger: logging.Logger) -> Iterable[Any]:
    items = _safe_get(folder, "Items")
    if items is None:
        return []

    try:
        items.Sort(f"[{filter_field}]", True)
    except Exception:
        pass

    if last_scan_utc is None:
        return _iter_items(items)

    outlook_ts = _format_outlook_restrict_datetime(last_scan_utc)
    restriction = f"[{filter_field}] >= '{outlook_ts}'"
    try:
        restricted = items.Restrict(restriction)
        return _iter_items(restricted)
    except Exception as exc:
        logger.warning("Restrict fehlgeschlagen fuer %s mit %s: %r", _folder_path(folder), restriction, exc)
        return _iter_items(items)


def _iter_items(items: Any) -> Iterable[Any]:
    count = int(_safe_get(items, "Count", 0) or 0)
    for index in range(1, count + 1):
        try:
            yield items.Item(index)
        except Exception:
            continue


def _upsert_message(conn: sqlite3.Connection, *, store_id: str, entry_id: str, folder_path: str, source_kind: str, message_time_utc: str | None, subject: str, scan_time_utc: str) -> bool:
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO scanned_messages(
            store_id, entry_id, folder_path, source_kind, message_time_utc, subject, last_seen_scan_utc
        ) VALUES(?, ?, ?, ?, ?, ?, ?)
        """,
        (store_id, entry_id, folder_path, source_kind, message_time_utc, subject, scan_time_utc),
    )
    inserted = cur.rowcount > 0
    if not inserted:
        conn.execute(
            """
            UPDATE scanned_messages
               SET folder_path = ?,
                   source_kind = ?,
                   message_time_utc = COALESCE(?, message_time_utc),
                   subject = COALESCE(?, subject),
                   last_seen_scan_utc = ?
             WHERE store_id = ? AND entry_id = ?
            """,
            (folder_path, source_kind, message_time_utc, subject, scan_time_utc, store_id, entry_id),
        )
    return inserted


def _observe_address(
    conn: sqlite3.Connection,
    *,
    store_id: str,
    entry_id: str,
    email: str,
    role: str,
    display_name: str,
    source_kind: str,
    folder_path: str,
    message_time_utc: str | None,
) -> bool:
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO address_observations(
            store_id, entry_id, email, role, display_name, source_kind, folder_path, message_time_utc
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (store_id, entry_id, email, role, display_name, source_kind, folder_path, message_time_utc),
    )
    return cur.rowcount > 0


def _upsert_address_summary(
    conn: sqlite3.Connection,
    *,
    stat: AddressStat,
    message_time_utc: str | None,
    source_kind: str,
    folder_path: str,
    store_id: str,
) -> None:
    conn.execute(
        """
        INSERT INTO addresses(
            email, display_name, first_seen_utc, last_seen_utc, seen_count,
            inbound_count, outbound_count, sender_count, recipient_count,
            last_source_kind, last_folder_path, last_store_id
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(email) DO UPDATE SET
            display_name = CASE
                WHEN excluded.display_name <> '' THEN excluded.display_name
                ELSE addresses.display_name
            END,
            first_seen_utc = CASE
                WHEN addresses.first_seen_utc IS NULL THEN excluded.first_seen_utc
                WHEN excluded.first_seen_utc IS NULL THEN addresses.first_seen_utc
                WHEN excluded.first_seen_utc < addresses.first_seen_utc THEN excluded.first_seen_utc
                ELSE addresses.first_seen_utc
            END,
            last_seen_utc = CASE
                WHEN addresses.last_seen_utc IS NULL THEN excluded.last_seen_utc
                WHEN excluded.last_seen_utc IS NULL THEN addresses.last_seen_utc
                WHEN excluded.last_seen_utc > addresses.last_seen_utc THEN excluded.last_seen_utc
                ELSE addresses.last_seen_utc
            END,
            seen_count = addresses.seen_count + excluded.seen_count,
            inbound_count = addresses.inbound_count + excluded.inbound_count,
            outbound_count = addresses.outbound_count + excluded.outbound_count,
            sender_count = addresses.sender_count + excluded.sender_count,
            recipient_count = addresses.recipient_count + excluded.recipient_count,
            last_source_kind = excluded.last_source_kind,
            last_folder_path = excluded.last_folder_path,
            last_store_id = excluded.last_store_id
        """,
        (
            stat.email,
            stat.display_name,
            message_time_utc,
            message_time_utc,
            stat.inbound_count + stat.outbound_count,
            stat.inbound_count,
            stat.outbound_count,
            stat.sender_count,
            stat.recipient_count,
            source_kind,
            folder_path,
            store_id,
        ),
    )


def _collect_message_addresses(item: Any, *, source_kind: str) -> list[tuple[str, str, str]]:
    collected: list[tuple[str, str, str]] = []

    sender_email, sender_name = _sender_address(item)
    if sender_email:
        collected.append((sender_email, sender_name, "sender"))

    for email, name, _recipient_type in _iter_recipients(item):
        if email:
            collected.append((email, name, "recipient"))

    # received mails without recipients should still yield sender; sent mails without recipients are rare but allowed
    # dedupe within the same message+role
    deduped: dict[tuple[str, str], tuple[str, str, str]] = {}
    for email, name, role in collected:
        key = (email, role)
        if key not in deduped or (name and not deduped[key][1]):
            deduped[key] = (email, name, role)
    return list(deduped.values())


def execute_scan(
    conn: sqlite3.Connection,
    *,
    force_full: bool,
    logger: logging.Logger,
    folder_filters: set[str] | None = None,
    max_messages: int = 0,
) -> dict[str, Any]:
    started_at = _iso_utc_now()
    last_scan_utc = None if force_full else _get_last_scan_utc(conn)
    if force_full:
        _reset_full_scan(conn)
        conn.commit()

    run_id = _start_run(conn, force_full=force_full, started_at=started_at)
    folders = _discover_scan_folders(logger, folder_filters=folder_filters)
    selected_folders = sorted(folder_filters or [])

    messages_seen = 0
    messages_considered = 0
    addresses_upserted = 0
    folder_summaries: list[dict[str, Any]] = []
    failures: list[str] = []
    stopped_early = False

    try:
        for scan_folder in folders:
            if max_messages > 0 and messages_considered >= max_messages:
                stopped_early = True
                break
            logger.info("Scanne %s [%s]", scan_folder.folder_path, scan_folder.source_kind)
            folder_summary = {
                "store_name": scan_folder.store_name,
                "store_id": scan_folder.store_id,
                "folder_path": scan_folder.folder_path,
                "source_kind": scan_folder.source_kind,
                "messages_seen": 0,
                "addresses_upserted": 0,
            }

            folder = scan_folder.folder
            if folder is None:
                failures.append(f"Ordner nicht gefunden: {scan_folder.folder_path}")
                folder_summaries.append(folder_summary)
                continue

            for item in _restrict_items(folder, scan_folder.filter_field, last_scan_utc, logger):
                if not _item_is_mail(item):
                    continue
                entry_id = _coerce_text(_safe_get(item, "EntryID", "")).strip()
                if not entry_id:
                    continue

                message_dt = _message_datetime(item, scan_folder.source_kind)
                if last_scan_utc is not None and message_dt is not None and message_dt < last_scan_utc:
                    continue

                if max_messages > 0 and messages_considered >= max_messages:
                    stopped_early = True
                    break
                messages_considered += 1

                subject = _coerce_text(_safe_get(item, "Subject", "")).strip()
                message_time_utc = message_dt.replace(microsecond=0).isoformat() if message_dt else None
                is_new_message = _upsert_message(
                    conn,
                    store_id=scan_folder.store_id,
                    entry_id=entry_id,
                    folder_path=scan_folder.folder_path,
                    source_kind=scan_folder.source_kind,
                    message_time_utc=message_time_utc,
                    subject=subject,
                    scan_time_utc=started_at,
                )

                if not is_new_message and not force_full:
                    continue

                messages_seen += 1
                folder_summary["messages_seen"] += 1

                for email, display_name, role in _collect_message_addresses(item, source_kind=scan_folder.source_kind):
                    inserted = _observe_address(
                        conn,
                        store_id=scan_folder.store_id,
                        entry_id=entry_id,
                        email=email,
                        role=role,
                        display_name=display_name,
                        source_kind=scan_folder.source_kind,
                        folder_path=scan_folder.folder_path,
                        message_time_utc=message_time_utc,
                    )
                    if not inserted:
                        continue

                    stat = AddressStat(email=email, display_name=display_name)
                    if scan_folder.source_kind == "sent":
                        stat.outbound_count = 1
                    else:
                        stat.inbound_count = 1
                    if role == "sender":
                        stat.sender_count = 1
                    else:
                        stat.recipient_count = 1

                    _upsert_address_summary(
                        conn,
                        stat=stat,
                        message_time_utc=message_time_utc,
                        source_kind=scan_folder.source_kind,
                        folder_path=scan_folder.folder_path,
                        store_id=scan_folder.store_id,
                    )
                    addresses_upserted += 1
                    folder_summary["addresses_upserted"] += 1

            folder_summaries.append(folder_summary)
            conn.commit()
            if stopped_early:
                break

        finished_at = _iso_utc_now()
        _set_last_scan_utc(conn, finished_at)
        details = {
            "db_path": str(DB_PATH),
            "last_scan_before": last_scan_utc.isoformat() if last_scan_utc else None,
            "last_scan_after": finished_at,
            "selected_folders": selected_folders,
            "max_messages": max_messages,
            "stopped_early": stopped_early,
            "messages_considered": messages_considered,
            "folders": folder_summaries,
            "failures": failures,
        }
        _finish_run(
            conn,
            run_id,
            status="ok",
            finished_at=finished_at,
            folders_scanned=len(folders),
            messages_seen=messages_seen,
            addresses_upserted=addresses_upserted,
            details=details,
        )
        conn.commit()
        return {
            "status": "ok",
            "db_path": str(DB_PATH),
            "force_full": force_full,
            "selected_folders": selected_folders,
            "max_messages": max_messages,
            "stopped_early": stopped_early,
            "messages_considered": messages_considered,
            "last_scan_before": last_scan_utc.isoformat() if last_scan_utc else None,
            "last_scan_after": finished_at,
            "folders_scanned": len(folders),
            "messages_seen": messages_seen,
            "addresses_upserted": addresses_upserted,
            "folders": folder_summaries,
            "failures": failures,
        }
    except Exception as exc:
        finished_at = _iso_utc_now()
        details = {
            "error": repr(exc),
            "db_path": str(DB_PATH),
            "last_scan_before": last_scan_utc.isoformat() if last_scan_utc else None,
            "selected_folders": selected_folders,
            "max_messages": max_messages,
            "stopped_early": stopped_early,
            "messages_considered": messages_considered,
            "folders": folder_summaries,
            "failures": failures,
        }
        _finish_run(
            conn,
            run_id,
            status="error",
            finished_at=finished_at,
            folders_scanned=len(folders),
            messages_seen=messages_seen,
            addresses_upserted=addresses_upserted,
            details=details,
        )
        conn.commit()
        raise


def _connect() -> sqlite3.Connection:
    USERDATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    _ensure_schema(conn)
    _purge_non_smtp_cache_entries(conn)
    conn.commit()
    return conn


def _cache_logger() -> logging.Logger:
    logger = logging.getLogger("outlook_address_cache")
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
    return logger


def _address_count(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) FROM addresses").fetchone()
    return int(row[0] if row else 0)


def _cache_status(conn: sqlite3.Connection, *, now_utc: datetime | None = None) -> dict[str, Any]:
    now_utc = now_utc or datetime.now(UTC)
    last_scan_utc = _get_last_scan_utc(conn)
    address_count = _address_count(conn)
    is_empty = address_count == 0 or last_scan_utc is None
    age_seconds: int | None = None
    is_stale = False
    if last_scan_utc is not None:
        age_seconds = max(int((now_utc - last_scan_utc).total_seconds()), 0)
        is_stale = now_utc - last_scan_utc > STALE_AFTER
    return {
        "db_path": str(DB_PATH),
        "address_count": address_count,
        "last_successful_scan_utc": last_scan_utc.isoformat() if last_scan_utc else None,
        "is_empty": is_empty,
        "is_stale": is_stale,
        "stale_after_seconds": int(STALE_AFTER.total_seconds()),
        "age_seconds": age_seconds,
    }


def get_cache_status(*, now_utc: datetime | None = None) -> dict[str, Any]:
    with _connect() as conn:
        return _cache_status(conn, now_utc=now_utc)


def _lookup_terms(query: str) -> list[str]:
    normalized = _normalize_text(query)
    if not normalized:
        return []
    terms: list[str] = [normalized]
    for part in re.split(r"[^\w@.+-]+", normalized):
        token = part.strip()
        if token and token not in terms:
            terms.append(token)
    return terms


def _lookup_candidates(conn: sqlite3.Connection, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
    terms = _lookup_terms(query)
    if not terms:
        return []

    where_parts: list[str] = []
    params: list[str] = []
    for term in terms:
        where_parts.append("(lower(email) LIKE ? OR lower(display_name) LIKE ?)")
        like = f"%{term}%"
        params.extend([like, like])

    rows = conn.execute(
        f"""
        SELECT email, display_name, seen_count, inbound_count, outbound_count,
               sender_count, recipient_count, first_seen_utc, last_seen_utc
          FROM addresses
         WHERE {" OR ".join(where_parts)}
         ORDER BY seen_count DESC, COALESCE(last_seen_utc, '') DESC
         LIMIT 50
        """,
        params,
    ).fetchall()

    normalized_query = _normalize_text(query)
    matches: list[dict[str, Any]] = []
    for row in rows:
        email = _coerce_text(row[0]).strip()
        display_name = _coerce_text(row[1]).strip()
        haystack = _normalize_text(f"{email}\n{display_name}")
        if not all(term in haystack for term in terms):
            continue

        score = 0
        email_norm = _normalize_text(email)
        name_norm = _normalize_text(display_name)
        if email_norm == normalized_query:
            score += 500
        if name_norm == normalized_query:
            score += 450
        if normalized_query and normalized_query in email_norm:
            score += 200
        if normalized_query and normalized_query in name_norm:
            score += 180
        score += min(int(row[2] or 0), 100)
        score += min(len(terms) * 15, 60)

        matches.append(
            {
                "email": email,
                "display_name": display_name,
                "seen_count": int(row[2] or 0),
                "inbound_count": int(row[3] or 0),
                "outbound_count": int(row[4] or 0),
                "sender_count": int(row[5] or 0),
                "recipient_count": int(row[6] or 0),
                "first_seen_utc": _coerce_text(row[7]).strip(),
                "last_seen_utc": _coerce_text(row[8]).strip(),
                "score": score,
            }
        )

    matches.sort(key=lambda item: (-int(item["score"]), -int(item["seen_count"]), item["email"].lower()))
    return matches[:limit]


def _maybe_refresh_cache(
    *,
    refresh_state: dict[str, Any] | None,
    reason: str,
    logger: logging.Logger,
) -> bool:
    state = refresh_state if refresh_state is not None else {}
    key = f"{reason}_attempted"
    if state.get(key):
        return False
    state[key] = True
    force_full = reason == "empty-cache"
    with _connect() as conn:
        execute_scan(conn, force_full=force_full, logger=logger)
    return True


def lookup_cached_addresses(
    query: str,
    *,
    limit: int = 5,
    refresh_state: dict[str, Any] | None = None,
    now_utc: datetime | None = None,
    logger: logging.Logger | None = None,
) -> dict[str, Any]:
    logger = logger or _cache_logger()
    warnings: list[str] = []

    with _connect() as conn:
        status_before = _cache_status(conn, now_utc=now_utc)
        matches = _lookup_candidates(conn, query, limit=limit)

    refreshed = False
    refresh_reason = ""
    if not matches:
        if status_before["is_empty"]:
            refresh_reason = "empty-cache"
        elif status_before["is_stale"]:
            refresh_reason = "stale-cache"

    if refresh_reason:
        try:
            refreshed = _maybe_refresh_cache(
                refresh_state=refresh_state,
                reason=refresh_reason,
                logger=logger,
            )
        except Exception as exc:
            warnings.append(f"{refresh_reason} refresh failed: {exc!r}")

    if refreshed:
        with _connect() as conn:
            status_after = _cache_status(conn, now_utc=now_utc)
            matches = _lookup_candidates(conn, query, limit=limit)
    else:
        status_after = status_before

    return {
        "query": _coerce_text(query).strip(),
        "matches": matches,
        "refreshed": refreshed,
        "refresh_reason": refresh_reason if refreshed else "",
        "cache_status_before": status_before,
        "cache_status_after": status_after,
        "warnings": warnings,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan Outlook inbox/archive/sent folders into a local SQLite address cache.")
    parser.add_argument("--force-full", action="store_true", help="Ignoriere den letzten Scanstand und baue den Cache komplett neu auf.")
    parser.add_argument("--verbose", action="store_true", help="Ausfuehrlich loggen.")
    parser.add_argument(
        "--folder",
        action="append",
        choices=FOLDER_CHOICES,
        default=[],
        help="Scanne nur die angegebene Quelle. Kann mehrfach angegeben werden: inbox, archive, sent.",
    )
    parser.add_argument(
        "--max-messages",
        type=int,
        default=0,
        help="Begrenze den Lauf global auf maximal N verarbeitete Nachrichten. 0 = unbegrenzt.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logger = setup_logging(verbose=args.verbose)

    with _connect() as conn:
        payload = execute_scan(
            conn,
            force_full=args.force_full,
            logger=logger,
            folder_filters=set(args.folder),
            max_messages=max(args.max_messages, 0),
        )

    json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
