from pathlib import Path
import sqlite3
import sys
from datetime import UTC, datetime, timedelta

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".agents" / "skills" / "skill-outlook" / "scripts"))

import outlook_address_cache as address_cache  # noqa: E402
from outlook_search_tools import (  # noqa: E402
    EmailRef,
    EXPLORER_SEARCH_SCOPES,
    OL_FOLDER_CALENDAR,
    OL_FOLDER_INBOX,
    OL_FOLDER_NOTES,
    OL_FOLDER_SENT_MAIL,
    OL_FOLDER_TASKS,
    SearchQuery,
    SUBJECT_DASL,
    _body_preview_lines,
    _build_advanced_filter,
    _build_store_scope_paths,
    _build_ui_query,
    _cap_recipients,
    _mail_item_debug_payload,
    _matches_filter_terms,
    _try_internet_address,
    main,
    search_emails,
)


def test_cap_recipients_adds_hidden_marker_after_ten():
    values = [f"user{i}@example.com" for i in range(12)]
    actual = _cap_recipients(values)
    assert len(actual) == 11
    assert actual[:10] == values[:10]
    assert actual[-1] == "[....] 2"


def test_body_preview_lines_keeps_first_ten_nonempty_lines():
    body = "\n".join(["", "A", "B", "", "C", "D", "E", "F", "G", "H", "I", "J", "K"])
    lines, has_more = _body_preview_lines(body)
    assert lines == ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]
    assert has_more is True


def test_mail_item_debug_payload_includes_parent_and_roundtrip_details():
    class FakeStore:
        DisplayName = "Mailbox"
        StoreID = "store-1"
        FilePath = "C:\\mailbox.ost"
        ExchangeStoreType = 3
        IsCachedExchange = True
        IsInstantSearchEnabled = True
        IsOpen = True

    class FakeFolder:
        Name = "Inbox"
        FolderPath = "\\\\Mailbox\\Inbox"
        StoreID = "store-1"
        Store = FakeStore()

    class FakeItem:
        EntryID = "entry-1"
        Subject = "Workshop-Nachbereitung"
        SenderEmailAddress = "martin@example.com"
        SenderName = "Martin"
        ConversationID = "conv-1"
        MessageClass = "IPM.Note"
        Parent = FakeFolder()
        ReceivedTime = type("DT", (), {"year": 2024, "month": 3, "day": 15, "hour": 15, "minute": 52, "second": 53})()

    payload = _mail_item_debug_payload(FakeItem(), roundtrip_item=FakeItem())

    assert payload["entry_id"] == "entry-1"
    assert payload["parent"]["folder_path"] == "\\\\Mailbox\\Inbox"
    assert payload["parent"]["store"]["store_id"] == "store-1"
    assert payload["get_item_from_id"]["ok"] is True
    assert payload["get_item_from_id"]["folder_path"] == "\\\\Mailbox\\Inbox"


def test_explorer_search_scopes_expose_expected_values():
    assert EXPLORER_SEARCH_SCOPES == {
        "current_folder": 0,
        "all_folders": 1,
        "all_outlook_items": 2,
        "subfolders": 3,
        "current_store": 4,
    }


def test_build_ui_query_maps_legacy_flags():
    query = SearchQuery(
        keywords=["budget q3"],
        sender_filters=["alice"],
        recipient_filters=["bob"],
        subject_must=["freigabe"],
    )
    actual = _build_ui_query(query)
    assert actual == 'subject:freigabe from:alice to:bob "budget q3"'


def test_build_advanced_filter_prefers_indexed_operators():
    query = SearchQuery(raw_query="Workshop-Nachbereitung", subject_must=["Vortrag"])
    actual = _build_advanced_filter(query, indexed=True)
    assert "ci_phrasematch" in actual
    assert SUBJECT_DASL in actual
    assert "Workshop" in actual
    assert "Nachbereitung" in actual


def test_build_advanced_filter_falls_back_to_like():
    query = SearchQuery(raw_query="Workshop-Nachbereitung")
    actual = _build_advanced_filter(query, indexed=False)
    assert " like " in actual
    assert "ci_phrasematch" not in actual


def test_build_store_scope_paths_excludes_contacts():
    mapping = {
        OL_FOLDER_INBOX: "\\\\Mailbox\\Inbox",
        OL_FOLDER_SENT_MAIL: "\\\\Mailbox\\Sent Items",
        OL_FOLDER_CALENDAR: "\\\\Mailbox\\Calendar",
        OL_FOLDER_TASKS: "\\\\Mailbox\\Tasks",
        OL_FOLDER_NOTES: "\\\\Mailbox\\Notes",
    }

    class FakeFolder:
        def __init__(self, path, name=""):
            self.FolderPath = path
            self.Name = name

    class FakeStore:
        def __init__(self):
            self._root = type(
                "Root",
                (),
                {
                    "Folders": type(
                        "Folders",
                        (),
                        {
                            "Count": 2,
                            "Item": staticmethod(
                                lambda index: [
                                    FakeFolder("\\\\Mailbox\\Archiv", "Archiv"),
                                    FakeFolder("\\\\Mailbox\\Kontakte", "Kontakte"),
                                ][index - 1]
                            ),
                        },
                    )()
                },
            )()

        def GetDefaultFolder(self, folder_id):
            if folder_id not in mapping:
                raise RuntimeError("folder not available")
            return FakeFolder(mapping[folder_id], "")

        def GetRootFolder(self):
            return self._root

    paths = _build_store_scope_paths(FakeStore())
    assert paths[: len(mapping)] == list(mapping.values())
    assert "\\\\Mailbox\\Archiv" in paths
    assert all("Contacts" not in path and "Kontakte" not in path for path in paths)


def test_matches_filter_terms_applies_post_filters():
    email = EmailRef(
        entry_id="1",
        subject="Workshop-Nachbereitung",
        sender="martin@example.com",
        sender_name="Martin",
        to_recipients=["Tobias <tobias@example.com>"],
        body_preview_lines=["Hallo Tobias", "Workshop-Ergebnisse im Anhang"],
    )
    query = SearchQuery(
        keywords=["ergebnisse"],
        sender_filters=["martin"],
        recipient_filters=["tobias"],
        subject_must=["workshop-nachbereitung"],
        exclude_terms=["absage"],
    )
    matched, reasons = _matches_filter_terms(email, query)
    assert matched is True
    assert "subject must-haves matched" in reasons
    assert "sender filter matched" in reasons
    assert "recipient filter matched" in reasons


def test_search_emails_ui_path_uses_explorer_search_and_filters_results(monkeypatch):
    monkeypatch.setattr(
        "outlook_search_tools._explorer_search_refs",
        lambda *args, **kwargs: (
            [
                EmailRef(
                    entry_id="entry-1",
                    store_id="store-1",
                    subject="Workshop-Nachbereitung",
                    sender="martin@example.com",
                    sender_name="Martin",
                    received="2024-03-15T16:52:53+00:00",
                    body_preview_lines=["Workshop-Ergebnisse im Anhang"],
                ),
                EmailRef(
                    entry_id="entry-2",
                    store_id="store-1",
                    subject="Absage",
                    sender="other@example.com",
                    sender_name="Other",
                    received="2024-03-15T16:52:53+00:00",
                ),
            ],
            {
                "query": 'subject:"workshop-nachbereitung"',
                "scope": "all_folders",
                "wait_seconds": 5.0,
                "max_results": 10,
                "current_folder": "\\\\Mailbox\\Suchordner\\Alle E-Mail-Elemente",
                "selection_count": 2,
            },
            [],
        ),
    )

    payload = search_emails(subject_must=["Workshop-Nachbereitung"], search_days=1500, max_results=10, search_ui=True)

    assert len(payload["matches"]) == 1
    assert payload["matches"][0]["email"]["subject"] == "Workshop-Nachbereitung"
    assert "explorer search matched" in payload["matches"][0]["reasons"]
    assert payload["query"]["ui_query"] == 'subject:"workshop-nachbereitung"'
    assert "engine" not in payload


def test_search_emails_background_uses_advanced_search_refs_and_filters_results(monkeypatch):
    monkeypatch.setattr(
        "outlook_search_tools._advanced_search_refs",
        lambda *args, **kwargs: (
            [
                EmailRef(
                    entry_id="entry-1",
                    store_id="store-1",
                    subject="Workshop-Nachbereitung",
                    sender="martin@example.com",
                    sender_name="Martin",
                    received="2024-03-15T16:52:53+00:00",
                    body_preview_lines=["Workshop-Ergebnisse im Anhang"],
                ),
                EmailRef(
                    entry_id="entry-2",
                    store_id="store-2",
                    subject="Absage",
                    sender="other@example.com",
                    sender_name="Other",
                    received="2024-03-15T16:52:53+00:00",
                ),
            ],
            {
                "stores": [{"store_name": "Mailbox", "store_id": "store-1", "indexed": True, "scope_paths": ["\\\\Mailbox\\Inbox"]}],
            },
            [],
        ),
    )

    payload = search_emails(subject_must=["Workshop-Nachbereitung"], search_days=1500, max_results=10)

    assert payload["engine"] == "advanced_search"
    assert len(payload["matches"]) == 1
    assert payload["matches"][0]["email"]["subject"] == "Workshop-Nachbereitung"
    assert "advanced search matched" in payload["matches"][0]["reasons"]
    assert payload["stores"][0]["store_name"] == "Mailbox"


def test_main_rejects_scope_without_search_ui():
    with pytest.raises(SystemExit) as exc:
        main(["search", "--subject-must", "Workshop-Nachbereitung", "--scope", "all_folders"])
    assert exc.value.code == 2


def test_search_emails_uses_cache_expansion_for_sender_filters(monkeypatch):
    monkeypatch.setattr(
        "outlook_search_tools._advanced_search_refs",
        lambda *args, **kwargs: (
            [
                EmailRef(
                    entry_id="entry-1",
                    store_id="store-1",
                    subject="Workshop",
                    sender="martin@example.com",
                    sender_name="Martin",
                    received="2024-03-15T16:52:53+00:00",
                )
            ],
            {"stores": []},
            [],
        ),
    )
    monkeypatch.setattr(
        "outlook_search_tools._expand_filter_values_via_cache",
        lambda values, **kwargs: (
            ["martin mustermann", "martin@example.com"] if values else [],
            [{"query": "martin mustermann", "match_count": 1, "matches": [{"email": "martin@example.com", "display_name": "Martin Mustermann"}]}],
            [],
        ),
    )

    payload = search_emails(sender_filters=["Martin Mustermann"], search_days=1500, max_results=10)

    assert len(payload["matches"]) == 1
    assert payload["matches"][0]["email"]["sender"] == "martin@example.com"
    assert payload["query"]["sender"] == ["martin mustermann"]
    assert payload["query"]["cache_resolution"]["sender"][0]["match_count"] == 1


def test_try_internet_address_ignores_exchange_legacy_dn_and_prefers_property_smtp():
    class FakeAccessor:
        @staticmethod
        def GetProperty(name):
            assert name == "http://schemas.microsoft.com/mapi/proptag/0x39FE001E"
            return "martin.mustermann@volkswagen.de"

    class FakeAddressEntry:
        PropertyAccessor = FakeAccessor()
        Address = "/o=ExchangeLabs/ou=Exchange Administrative Group/cn=Recipients/cn=legacy"

        @staticmethod
        def GetExchangeUser():
            raise RuntimeError("no exchange user")

        @staticmethod
        def GetExchangeDistributionList():
            raise RuntimeError("no exchange dl")

    class FakeRecipient:
        AddressEntry = FakeAddressEntry()
        Address = "/o=ExchangeLabs/ou=Exchange Administrative Group/cn=Recipients/cn=legacy"

    assert _try_internet_address(FakeRecipient()) == "martin.mustermann@volkswagen.de"


def test_address_cache_status_marks_entries_older_than_one_day_as_stale(tmp_path, monkeypatch):
    db_path = tmp_path / "address_cache.db"
    monkeypatch.setattr(address_cache, "DB_PATH", db_path)
    monkeypatch.setattr(address_cache, "USERDATA_DIR", tmp_path)

    with address_cache._connect() as conn:
        conn.execute(
            "INSERT INTO addresses(email, display_name, seen_count) VALUES(?, ?, ?)",
            ("martin@example.com", "Martin", 1),
        )
        address_cache._set_last_scan_utc(conn, (datetime.now(UTC) - timedelta(days=2)).replace(microsecond=0).isoformat())
        conn.commit()

    status = address_cache.get_cache_status()

    assert status["address_count"] == 1
    assert status["is_empty"] is False
    assert status["is_stale"] is True


def test_address_cache_lookup_refreshes_empty_cache_once_and_retries(tmp_path, monkeypatch):
    db_path = tmp_path / "address_cache.db"
    monkeypatch.setattr(address_cache, "DB_PATH", db_path)
    monkeypatch.setattr(address_cache, "USERDATA_DIR", tmp_path)

    refresh_calls = []

    def fake_refresh(*, refresh_state, reason, logger):
        refresh_calls.append(reason)
        with address_cache._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO addresses(
                    email, display_name, seen_count, inbound_count, outbound_count,
                    sender_count, recipient_count, first_seen_utc, last_seen_utc
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "martin@example.com",
                    "Martin Mustermann",
                    3,
                    1,
                    2,
                    1,
                    2,
                    "2026-04-14T08:00:00+00:00",
                    "2026-04-16T08:00:00+00:00",
                ),
            )
            address_cache._set_last_scan_utc(conn, "2026-04-16T08:00:00+00:00")
            conn.commit()
        refresh_state[f"{reason}_attempted"] = True
        return True

    monkeypatch.setattr(address_cache, "_maybe_refresh_cache", fake_refresh)

    payload = address_cache.lookup_cached_addresses("Martin Mustermann", refresh_state={})

    assert refresh_calls == ["empty-cache"]
    assert payload["refreshed"] is True
    assert payload["refresh_reason"] == "empty-cache"
    assert payload["matches"][0]["email"] == "martin@example.com"


def test_address_cache_parse_args_accepts_folder_filter():
    args = address_cache.parse_args(["--folder", "inbox", "--folder", "sent"])

    assert args.folder == ["inbox", "sent"]
    assert args.force_full is False


def test_address_cache_parse_args_accepts_max_messages():
    args = address_cache.parse_args(["--folder", "inbox", "--max-messages", "200"])

    assert args.folder == ["inbox"]
    assert args.max_messages == 200


def test_address_cache_execute_scan_stops_after_considered_limit(monkeypatch, tmp_path):
    db_path = tmp_path / "address_cache.db"
    monkeypatch.setattr(address_cache, "DB_PATH", db_path)
    monkeypatch.setattr(address_cache, "USERDATA_DIR", tmp_path)

    class FakeItems:
        Count = 3

        @staticmethod
        def Item(index):
            return [
                type("Item", (), {"MessageClass": "IPM.Note", "EntryID": "1", "Subject": "A"})(),
                type("Item", (), {"MessageClass": "IPM.Note", "EntryID": "2", "Subject": "B"})(),
                type("Item", (), {"MessageClass": "IPM.Note", "EntryID": "3", "Subject": "C"})(),
            ][index - 1]

    fake_folder = object()
    monkeypatch.setattr(
        address_cache,
        "_discover_scan_folders",
        lambda logger, folder_filters=None: [
            address_cache.ScanFolder(
                folder=fake_folder,
                store_id="store-1",
                store_name="Mailbox",
                folder_path="\\\\Mailbox\\Inbox",
                source_kind="inbox",
                filter_field="ReceivedTime",
            )
        ],
    )
    monkeypatch.setattr(address_cache, "_restrict_items", lambda folder, filter_field, last_scan_utc, logger: address_cache._iter_items(FakeItems()))
    monkeypatch.setattr(address_cache, "_message_datetime", lambda item, source_kind: datetime(2026, 4, 17, 8, 0, tzinfo=UTC))
    monkeypatch.setattr(address_cache, "_collect_message_addresses", lambda item, source_kind: [])

    with address_cache._connect() as conn:
        payload = address_cache.execute_scan(conn, force_full=False, logger=address_cache._cache_logger(), max_messages=2)

    assert payload["messages_considered"] == 2
    assert payload["messages_seen"] == 2
    assert payload["stopped_early"] is True


def test_address_cache_connect_purges_non_smtp_rows(tmp_path, monkeypatch):
    db_path = tmp_path / "address_cache.db"
    monkeypatch.setattr(address_cache, "DB_PATH", db_path)
    monkeypatch.setattr(address_cache, "USERDATA_DIR", tmp_path)

    conn = sqlite3.connect(db_path)
    address_cache._ensure_schema(conn)
    conn.execute(
        "INSERT INTO addresses(email, display_name, seen_count) VALUES(?, ?, ?)",
        ("/o=exchangelabs/ou=exchange administrative group/cn=recipients/cn=legacy", "Legacy", 1),
    )
    conn.execute(
        "INSERT INTO addresses(email, display_name, seen_count) VALUES(?, ?, ?)",
        ("martin@example.com", "Martin", 1),
    )
    conn.execute(
        """
        INSERT INTO address_observations(
            store_id, entry_id, email, role, display_name, source_kind, folder_path, message_time_utc
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("store-1", "entry-1", "/o=exchangelabs/ou=exchange administrative group/cn=recipients/cn=legacy", "sender", "Legacy", "inbox", "\\\\Mailbox\\Inbox", None),
    )
    conn.commit()
    conn.close()

    with address_cache._connect() as conn:
        rows = conn.execute("SELECT email FROM addresses ORDER BY email").fetchall()
        obs_rows = conn.execute("SELECT email FROM address_observations").fetchall()

    assert rows == [("martin@example.com",)]
    assert obs_rows == []
