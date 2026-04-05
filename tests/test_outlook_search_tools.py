from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".agents" / "skills" / "skill-outlook" / "scripts"))

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
