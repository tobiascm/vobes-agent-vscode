import base64
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

WORKSPACE = Path(__file__).resolve().parents[1]

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[1]
        / ".agents"
        / "skills"
        / "skill-m365-copilot-mail-search"
        / "scripts"
    ),
)

import m365_mail_search as mod  # noqa: E402


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text
        self.headers = {"content-type": "application/json"}

    def json(self) -> dict:
        return self._payload


def test_cmd_search_writes_attachment_links_to_md_and_names_to_stdout(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "SEARCH_OUTPUT_DIR", tmp_path / "tmp")
    monkeypatch.setattr(mod, "_resolve_token", lambda _token=None: "token")
    monkeypatch.setattr(mod.time, "strftime", lambda _fmt: "20260404_120000")

    def fake_post(url, headers=None, json=None, timeout=None):
        assert url == mod.SEARCH_URL
        return FakeResponse(
            200,
            {
                "value": [
                    {
                        "hitsContainers": [
                            {
                                "total": 1,
                                "hits": [
                                    {
                                        "hitId": "msg-1",
                                        "summary": "irrelevant",
                                        "resource": {
                                            "subject": "Budget Freigabe",
                                            "receivedDateTime": "2026-04-04T08:00:00Z",
                                            "hasAttachments": True,
                                            "importance": "normal",
                                            "replyTo": [],
                                            "from": {"emailAddress": {"name": "Alice"}},
                                            "webLink": "https://outlook.office.com/mail/read/msg-1",
                                        },
                                    }
                                ],
                            }
                        ]
                    }
                ]
            },
        )

    def fake_get(url, headers=None, params=None, timeout=None):
        if url.endswith("/msg-1") and params == {"$select": "body,ccRecipients,parentFolderId"}:
            return FakeResponse(
                200,
                {
                    "body": {
                        "contentType": "html",
                        "content": "\n".join(
                            [
                                "Hallo zusammen,",
                                '<a href="https://contoso.sharepoint.com/sites/team/Kapazitaetsanalyse.xlsx">Kapazitätsanalyse_minimaler_Kompetenzerhalt_EKE.xlsx</a>',
                                "-----Ursprünglicher Termin-----",
                                "Von: Alice Example <alice@example.com>",
                            ]
                        ),
                    },
                    "ccRecipients": [
                        {"emailAddress": {"name": "Tobias Mueller", "address": "tobias@example.com"}}
                    ],
                },
            )
        if url.endswith("/attachments"):
            return FakeResponse(
                200,
                {
                    "value": [
                        {
                            "@odata.type": "#microsoft.graph.fileAttachment",
                            "id": "att-1",
                            "name": "angebot.pdf",
                            "isInline": False,
                        },
                        {
                            "@odata.type": "#microsoft.graph.fileAttachment",
                            "id": "att-2",
                            "name": "screenshot.png",
                            "isInline": True,
                        },
                        {
                            "@odata.type": "#microsoft.graph.referenceAttachment",
                            "id": "att-3",
                            "name": "Projektplan.docx",
                            "sourceUrl": "https://contoso.sharepoint.com/sites/team/Projektplan.docx",
                        },
                        {
                            "@odata.type": "#microsoft.graph.itemAttachment",
                            "id": "att-4",
                            "name": "embedded-message",
                        },
                    ]
                },
            )
        raise AssertionError(f"Unexpected GET {url}")

    monkeypatch.setattr(mod.requests, "post", fake_post)
    monkeypatch.setattr(mod.requests, "get", fake_get)

    mod.cmd_search("Budget", only_summary=False)

    stdout = capsys.readouterr().out
    assert "- hasAttachments:" not in stdout
    assert "- importance: normal" not in stdout
    assert "- attachments:" in stdout
    assert "  - angebot.pdf" in stdout
    assert "  - screenshot.png" in stdout
    assert "  - Projektplan.docx" in stdout
    assert "  - Kapazitätsanalyse_minimaler_Kompetenzerhalt_EKE.xlsx" in stdout
    assert "- cc: Tobias Mueller" in stdout
    assert "<alice@example.com>" not in stdout
    assert "Hallo zusammen," in stdout
    assert "-----Ursprünglicher Termin-----" not in stdout
    assert "Von: Alice Example" not in stdout
    assert "embedded-message" not in stdout

    output_file = tmp_path / "tmp" / "20260404_120000_mail_search_budget.md"
    content = output_file.read_text(encoding="utf-8")
    assert "- attachments:" in content
    assert "[angebot.pdf](https://graph.microsoft.com/v1.0/me/messages/msg-1/attachments/att-1/$value)" in content
    assert "[screenshot.png](https://graph.microsoft.com/v1.0/me/messages/msg-1/attachments/att-2/$value)" in content
    assert "[Projektplan.docx](https://contoso.sharepoint.com/sites/team/Projektplan.docx)" in content
    assert "[Kapazitätsanalyse_minimaler_Kompetenzerhalt_EKE.xlsx](https://contoso.sharepoint.com/sites/team/Kapazitaetsanalyse.xlsx)" in content
    assert "- cc: Tobias Mueller" in content
    assert "embedded-message" not in content


def test_cmd_search_omits_stdout_attachment_hint_when_no_linkable_attachments(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "SEARCH_OUTPUT_DIR", tmp_path / "tmp")
    monkeypatch.setattr(mod, "_resolve_token", lambda _token=None: "token")
    monkeypatch.setattr(mod.time, "strftime", lambda _fmt: "20260404_120001")

    def fake_post(url, headers=None, json=None, timeout=None):
        return FakeResponse(
            200,
            {
                "value": [
                    {
                        "hitsContainers": [
                            {
                                "total": 1,
                                "hits": [
                                    {
                                        "hitId": "msg-2",
                                        "summary": "irrelevant",
                                        "resource": {
                                            "subject": "Ohne Link",
                                            "receivedDateTime": "2026-04-04T09:00:00Z",
                                            "hasAttachments": True,
                                            "importance": "high",
                                            "replyTo": [],
                                            "from": {"emailAddress": {"name": "Bob"}},
                                            "webLink": "https://outlook.office.com/mail/read/msg-2",
                                        },
                                    }
                                ],
                            }
                        ]
                    }
                ]
            },
        )

    def fake_get(url, headers=None, params=None, timeout=None):
        if url.endswith("/msg-2") and params == {"$select": "body,ccRecipients,parentFolderId"}:
            return FakeResponse(
                200,
                {
                    "body": {"contentType": "text", "content": "Kurzinfo"},
                    "ccRecipients": [],
                },
            )
        if url.endswith("/attachments"):
            return FakeResponse(
                200,
                {
                    "value": [
                        {
                            "@odata.type": "#microsoft.graph.itemAttachment",
                            "id": "att-9",
                            "name": "embedded-message",
                        }
                    ]
                },
            )
        raise AssertionError(f"Unexpected GET {url}")

    monkeypatch.setattr(mod.requests, "post", fake_post)
    monkeypatch.setattr(mod.requests, "get", fake_get)

    mod.cmd_search("NoLink", only_summary=True)

    stdout = capsys.readouterr().out
    assert "- hasAttachments:" not in stdout
    assert "- importance: high" in stdout
    assert "- attachments:" not in stdout

    output_file = tmp_path / "tmp" / "20260404_120001_mail_search_nolink.md"
    content = output_file.read_text(encoding="utf-8")
    assert "- importance: high" in content
    assert "- attachments:" not in content


def test_cmd_search_events_only_writes_event_output_and_uses_event_request(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "SEARCH_OUTPUT_DIR", tmp_path / "tmp")
    monkeypatch.setattr(
        mod,
        "_resolve_token",
        lambda _token=None, scope_options=mod.MAIL_SCOPE_OPTIONS, scope_error_code="NO_MAIL_SCOPE", scope_error_message="": "token",
    )
    monkeypatch.setattr(mod, "_event_series_now", lambda: mod.datetime(2026, 4, 5, 8, 0, tzinfo=mod.timezone.utc))
    monkeypatch.setattr(mod.time, "strftime", lambda _fmt: "20260404_120002")

    seen_requests = []

    def fake_post(url, headers=None, json=None, timeout=None):
        seen_requests.append(json)
        return FakeResponse(
            200,
            {
                "value": [
                    {
                        "hitsContainers": [
                            {
                                "total": 2,
                                "hits": [
                                    {
                                        "hitId": "evt-1/withslash==",
                                        "summary": "<c0>Workshop</c0> zur Nachbereitung",
                                        "resource": {
                                            "subject": "Projekt Workshop",
                                            "start": {"dateTime": "2026-04-12T09:00:00", "timeZone": "Europe/Berlin"},
                                            "iCalUId": "ical-123",
                                            "hasAttachments": True,
                                            "webLink": "https://outlook.office.com/calendar/item/evt-1",
                                        },
                                    }
                                    ,
                                    {
                                        "hitId": "evt-2/withslash==",
                                        "summary": "<c0>Workshop</c0> zur Nachbereitung",
                                        "resource": {
                                            "subject": "Projekt Workshop",
                                            "start": {"dateTime": "2026-04-05T09:00:00", "timeZone": "Europe/Berlin"},
                                            "iCalUId": "ical-456",
                                            "hasAttachments": True,
                                            "webLink": "https://outlook.office.com/calendar/item/evt-2",
                                        },
                                    },
                                ],
                            }
                        ]
                    }
                ]
            },
        )

    monkeypatch.setattr(mod.requests, "post", fake_post)

    def fake_get(url, headers=None, params=None, timeout=None):
        if url.endswith("/calendarView"):
            if params["startDateTime"] == "2026-04-12T00:00:00+02:00":
                return FakeResponse(
                    200,
                    {
                        "value": [
                            {
                                "id": "evt-1-real",
                                "iCalUId": "ical-123",
                                "body": {
                                    "contentType": "html",
                                    "content": "\n".join(
                                        [
                                            "Hallo Tobias,",
                                            "im Anhang die Aufbereitung der Workshop-Ergebnisse von Montag.",
                                            "Bei Fragen bitte melden.",
                                            '<a href="https://contoso.sharepoint.com/sites/team/WorkshopAgenda.docx">WorkshopAgenda.docx</a>',
                                        ]
                                    ),
                                },
                                "attendees": [
                                    {"emailAddress": {"name": f"Teilnehmer {i:02d}", "address": f"user{i}@example.com"}}
                                    for i in range(1, 26)
                                ],
                                "organizer": {"emailAddress": {"name": "Alice Example", "address": "alice@example.com"}},
                                "start": {"dateTime": "2026-04-12T09:00:00", "timeZone": "Europe/Berlin"},
                                "subject": "Projekt Workshop",
                                "webLink": "https://outlook.office.com/calendar/item/evt-1",
                                "hasAttachments": True,
                                "type": "occurrence",
                                "seriesMasterId": "series-1",
                            }
                        ]
                    },
                )
            if params["startDateTime"] == "2026-04-05T00:00:00+02:00":
                return FakeResponse(
                    200,
                    {
                        "value": [
                            {
                                "id": "evt-2-real",
                                "iCalUId": "ical-456",
                                "body": {
                                    "contentType": "html",
                                    "content": "\n".join(
                                        [
                                            "Hallo Tobias,",
                                            "im Anhang die Aufbereitung der Workshop-Ergebnisse von Montag.",
                                            "Bei Fragen bitte melden.",
                                            '<a href="https://contoso.sharepoint.com/sites/team/WorkshopAgenda.docx">WorkshopAgenda.docx</a>',
                                        ]
                                    ),
                                },
                                "attendees": [
                                    {"emailAddress": {"name": f"Teilnehmer {i:02d}", "address": f"user{i}@example.com"}}
                                    for i in range(1, 26)
                                ],
                                "organizer": {"emailAddress": {"name": "Alice Example", "address": "alice@example.com"}},
                                "start": {"dateTime": "2026-04-05T09:00:00", "timeZone": "Europe/Berlin"},
                                "subject": "Projekt Workshop",
                                "webLink": "https://outlook.office.com/calendar/item/evt-2",
                                "hasAttachments": True,
                                "type": "occurrence",
                                "seriesMasterId": "series-1",
                            }
                        ]
                    },
                )
            raise AssertionError(f"Unexpected calendarView params {params}")
        if url.endswith("/events/series-1/instances"):
            assert params["startDateTime"] == "2026-04-05T08:00:00Z"
            return FakeResponse(
                200,
                {
                    "value": [
                        {
                            "id": "evt-2-real",
                            "start": {"dateTime": "2026-04-05T09:00:00", "timeZone": "Europe/Berlin"},
                            "subject": "Projekt Workshop",
                            "type": "occurrence",
                            "seriesMasterId": "series-1",
                        },
                        {
                            "id": "evt-1-real",
                            "start": {"dateTime": "2026-04-12T09:00:00", "timeZone": "Europe/Berlin"},
                            "subject": "Projekt Workshop",
                            "type": "occurrence",
                            "seriesMasterId": "series-1",
                        },
                    ]
                },
            )
        if url.endswith("/events/evt-2-real") and params == {"$select": "id,body,attendees,organizer,start,webLink,hasAttachments,type,seriesMasterId"}:
            return FakeResponse(
                200,
                {
                    "id": "evt-2-real",
                    "body": {
                        "contentType": "html",
                        "content": "\n".join(
                            [
                                "Hallo Tobias,",
                                "im Anhang die Aufbereitung der Workshop-Ergebnisse von Montag.",
                                "Bei Fragen bitte melden.",
                                '<a href="https://contoso.sharepoint.com/sites/team/WorkshopAgenda.docx">WorkshopAgenda.docx</a>',
                            ]
                        ),
                    },
                    "attendees": [
                        {"emailAddress": {"name": f"Teilnehmer {i:02d}", "address": f"user{i}@example.com"}}
                        for i in range(1, 26)
                    ],
                    "organizer": {"emailAddress": {"name": "Alice Example", "address": "alice@example.com"}},
                    "start": {"dateTime": "2026-04-05T09:00:00", "timeZone": "Europe/Berlin"},
                    "subject": "Projekt Workshop",
                    "webLink": "https://outlook.office.com/calendar/item/evt-2",
                    "hasAttachments": True,
                    "type": "occurrence",
                    "seriesMasterId": "series-1",
                },
            )
        if url.endswith("/events/evt-2-real/attachments"):
            return FakeResponse(
                200,
                {
                    "value": [
                        {
                            "@odata.type": "#microsoft.graph.fileAttachment",
                            "id": "att-evt-1",
                            "name": "Workshop-Ergebnis.pptx",
                            "isInline": False,
                        },
                        {
                            "@odata.type": "#microsoft.graph.itemAttachment",
                            "id": "att-evt-2",
                            "name": "embedded-item",
                        },
                    ]
                },
            )
        raise AssertionError(f"Unexpected GET {url}")

    monkeypatch.setattr(mod.requests, "get", fake_get)

    mod.cmd_search("Workshop", events_only=True)

    stdout = capsys.readouterr().out
    assert '### Kalender-Suche: "Workshop"' in stdout
    assert "**2 Treffer** (zeige 1)" in stdout
    assert "- startDate: 2026-04-05T09:00:00 (Europe/Berlin)" in stdout
    assert "- from: Alice Example" in stdout
    assert "- replyTo: Teilnehmer 01; Teilnehmer 02; Teilnehmer 03; Teilnehmer 04; Teilnehmer 05; Teilnehmer 06; Teilnehmer 07; Teilnehmer 08; Teilnehmer 09; Teilnehmer 10; [...] (25)" in stdout
    assert "- subject: Projekt Workshop" in stdout
    assert "- note: Terminserie" in stdout
    assert "- attachments:" in stdout
    assert "  - Workshop-Ergebnis.pptx" in stdout
    assert "  - WorkshopAgenda.docx" in stdout
    assert "- bodyPreview:" in stdout
    assert "Hallo Tobias," in stdout
    assert "im Anhang die Aufbereitung der Workshop-Ergebnisse von Montag." in stdout
    assert stdout.count("#### Treffer") == 1
    assert "- end:" not in stdout
    assert "- summary:" not in stdout
    assert "- receivedDateTime:" not in stdout
    assert "Mail-Suche" not in stdout

    assert len(seen_requests) == 1
    request = seen_requests[0]["requests"][0]
    assert request["entityTypes"] == ["event"]
    assert request["fields"] == mod.EVENT_FIELDS
    assert "enableTopResults" not in request

    output_file = tmp_path / "tmp" / "20260404_120002_event_search_workshop.md"
    content = output_file.read_text(encoding="utf-8")
    assert '# Kalender-Suche: "Workshop"' in content
    assert "**2 Treffer** (zeige 1)" in content
    assert "- startDate: 2026-04-05T09:00:00 (Europe/Berlin)" in content
    assert "- from: Alice Example" in content
    assert "- replyTo: Teilnehmer 01; Teilnehmer 02; Teilnehmer 03; Teilnehmer 04; Teilnehmer 05; Teilnehmer 06; Teilnehmer 07; Teilnehmer 08; Teilnehmer 09; Teilnehmer 10; [...] (25)" in content
    assert "- note: Terminserie" in content
    assert "[Workshop-Ergebnis.pptx](https://graph.microsoft.com/v1.0/me/events/evt-2-real/attachments/att-evt-1/$value)" in content
    assert "[WorkshopAgenda.docx](https://contoso.sharepoint.com/sites/team/WorkshopAgenda.docx)" in content
    assert "- bodyPreview:" in content
    assert "- webLink: https://outlook.office.com/calendar/item/evt-2" in content
    assert "- end:" not in content
    assert "- summary:" not in content
    assert "- receivedDateTime:" not in content
    assert "Mail-Suche" not in content


def test_collect_rendered_event_hits_pages_until_enough_unique_results(monkeypatch):
    seen_offsets = []

    def fake_execute_search_request(token, query, entity_type, size, *, start_at=0, top_results=False, fields=None, scope_error_code):
        assert token == "token"
        assert query == "Workshop"
        assert entity_type == "event"
        assert size == 25
        assert fields == mod.EVENT_FIELDS
        assert scope_error_code == "NO_CALENDAR_SCOPE"
        seen_offsets.append(start_at)
        if start_at == 0:
            hits = [
                {"hitId": f"series-{i}", "resource": {"subject": "Serie", "start": {"dateTime": "2026-04-10T09:00:00", "timeZone": "Europe/Berlin"}}}
                for i in range(25)
            ]
            return {"value": [{"hitsContainers": [{"total": 30, "hits": hits}]}]}
        if start_at == 25:
            hits = [
                {"hitId": "series-25", "resource": {"subject": "Serie", "start": {"dateTime": "2026-04-17T09:00:00", "timeZone": "Europe/Berlin"}}},
                {"hitId": "single-1", "resource": {"subject": "Workshop Abschaltung LDorado", "start": {"dateTime": "2026-04-28T10:00:00", "timeZone": "Europe/Berlin"}}},
                {"hitId": "single-2", "resource": {"subject": "UA-Workshop", "start": {"dateTime": "2026-05-01T09:00:00", "timeZone": "Europe/Berlin"}}},
                {"hitId": "single-3", "resource": {"subject": "Workshop KI", "start": {"dateTime": "2026-05-03T09:00:00", "timeZone": "Europe/Berlin"}}},
                {"hitId": "single-4", "resource": {"subject": "Workshop PMT", "start": {"dateTime": "2026-05-04T09:00:00", "timeZone": "Europe/Berlin"}}},
            ]
            return {"value": [{"hitsContainers": [{"total": 30, "hits": hits}]}]}
        raise AssertionError(f"Unexpected start_at {start_at}")

    def fake_resolve_event_hits(hits, token):
        return [
            {
                "rank": idx,
                "hit": hit,
                "resource": hit["resource"],
                "subject": hit["resource"]["subject"],
                "search_ctx": {
                    "event_id": hit["hitId"],
                    "start_date": mod._format_event_datetime(hit["resource"]["start"]),
                    "series_master_id": "series-1" if str(hit["hitId"]).startswith("series-") else "",
                    "event_type": "occurrence" if str(hit["hitId"]).startswith("series-") else "singleInstance",
                },
            }
            for idx, hit in enumerate(hits, 1)
        ]

    def fake_dedupe_series_event_hits(resolved_hits, token):
        series_hit = next(item for item in resolved_hits if str(item["hit"]["hitId"]).startswith("series-"))
        unique = [series_hit]
        for item in resolved_hits:
            if not str(item["hit"]["hitId"]).startswith("series-"):
                unique.append(item)
        return unique

    monkeypatch.setattr(mod, "_execute_search_request", fake_execute_search_request)
    monkeypatch.setattr(mod, "_resolve_event_hits", fake_resolve_event_hits)
    monkeypatch.setattr(mod, "_dedupe_series_event_hits", fake_dedupe_series_event_hits)

    total, rendered_hits = mod._collect_rendered_event_hits("Workshop", "token", 2)

    assert total == 30
    assert seen_offsets == [0, 25]
    assert len(rendered_hits) == 2
    assert rendered_hits[0]["subject"] == "Serie"
    assert rendered_hits[1]["subject"] == "Workshop Abschaltung LDorado"


def test_event_detail_lookup_uses_calendar_view_and_returns_real_event_id(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "SEARCH_OUTPUT_DIR", tmp_path / "tmp")

    seen_urls = []
    seen_params = []
    event_id = "AAMk/evt=="
    resource = {
        "subject": "Projekt Workshop",
        "start": {"dateTime": "2026-04-05T09:00:00", "timeZone": "Europe/Berlin"},
        "iCalUId": "ical-123",
    }

    def fake_get(url, headers=None, params=None, timeout=None):
        seen_urls.append(url)
        seen_params.append(params)
        return FakeResponse(
            200,
            {
                "value": [
                    {
                        "id": "evt-1-real",
                        "iCalUId": "ical-123",
                        "body": {"contentType": "text", "content": "Kurzinfo"},
                        "attendees": [],
                        "organizer": {"emailAddress": {"name": "Alice Example", "address": "alice@example.com"}},
                        "start": {"dateTime": "2026-04-05T09:00:00", "timeZone": "Europe/Berlin"},
                        "subject": "Projekt Workshop",
                        "webLink": "https://outlook.office.com/calendar/item/evt-1",
                        "hasAttachments": False,
                        "type": "occurrence",
                        "seriesMasterId": "series-1",
                    }
                ]
            },
        )

    monkeypatch.setattr(mod.requests, "get", fake_get)

    ctx = mod._fetch_event_search_context(event_id, resource, "token")

    assert ctx["from"] == "Alice Example"
    assert ctx["event_id"] == "evt-1-real"
    assert ctx["series_master_id"] == "series-1"
    assert ctx["is_series"] is True
    assert seen_urls == ["https://graph.microsoft.com/v1.0/me/calendarView"]
    assert seen_params[0]["startDateTime"] == "2026-04-05T00:00:00+02:00"
    assert seen_params[0]["endDateTime"] == "2026-04-06T00:00:00+02:00"


def test_series_dedupe_prefers_next_instance_from_series_master(monkeypatch):
    monkeypatch.setattr(mod, "_event_series_now", lambda: mod.datetime(2026, 4, 5, 8, 0, tzinfo=mod.timezone.utc))

    calls = []

    def fake_get(url, headers=None, params=None, timeout=None):
        calls.append((url, params))
        if url.endswith("/events/series-1/instances"):
            return FakeResponse(
                200,
                {
                    "value": [
                        {
                            "id": "evt-next",
                            "start": {"dateTime": "2026-04-17T08:35:00.0000000", "timeZone": "UTC"},
                            "subject": "Workshop Easy-Migration-Selfservice",
                            "type": "occurrence",
                            "seriesMasterId": "series-1",
                        },
                        {
                            "id": "evt-later",
                            "start": {"dateTime": "2026-05-08T08:35:00.0000000", "timeZone": "UTC"},
                            "subject": "Workshop Easy-Migration-Selfservice",
                            "type": "occurrence",
                            "seriesMasterId": "series-1",
                        },
                    ]
                },
            )
        if url.endswith("/events/evt-next") and params == {"$select": "id,body,attendees,organizer,start,webLink,hasAttachments,type,seriesMasterId"}:
            return FakeResponse(
                200,
                {
                    "id": "evt-next",
                    "body": {"contentType": "text", "content": "Nächster Termin"},
                    "attendees": [],
                    "organizer": {"emailAddress": {"name": "Alice Example", "address": "alice@example.com"}},
                    "start": {"dateTime": "2026-04-17T08:35:00.0000000", "timeZone": "UTC"},
                    "subject": "Workshop Easy-Migration-Selfservice",
                    "webLink": "https://outlook.office.com/calendar/item/evt-next",
                    "hasAttachments": False,
                    "type": "occurrence",
                    "seriesMasterId": "series-1",
                },
            )
        raise AssertionError(f"Unexpected GET {url} {params}")

    monkeypatch.setattr(mod.requests, "get", fake_get)

    resolved_hits = [
        {
            "rank": 1,
            "subject": "Workshop Easy-Migration-Selfservice",
            "search_ctx": {
                "start_date": "2026-09-11T08:35:00 (UTC)",
                "series_master_id": "series-1",
                "event_type": "occurrence",
                "event_id": "evt-sep",
                "is_series": True,
                "body_preview": "alt",
                "body_raw": "",
                "body_type": "text",
                "from": "Alice Example",
                "reply_to": "-",
                "web_link": "-",
                "has_attachments": False,
            },
        },
        {
            "rank": 2,
            "subject": "Workshop Easy-Migration-Selfservice",
            "search_ctx": {
                "start_date": "2026-10-02T08:35:00 (UTC)",
                "series_master_id": "series-1",
                "event_type": "occurrence",
                "event_id": "evt-oct",
                "is_series": True,
                "body_preview": "alt",
                "body_raw": "",
                "body_type": "text",
                "from": "Alice Example",
                "reply_to": "-",
                "web_link": "-",
                "has_attachments": False,
            },
        },
    ]

    deduped = mod._dedupe_series_event_hits(resolved_hits, "token")

    assert len(deduped) == 1
    assert deduped[0]["search_ctx"]["event_id"] == "evt-next"
    assert deduped[0]["search_ctx"]["start_date"] == "2026-04-17T08:35:00 (UTC)"
    assert deduped[0]["search_ctx"]["is_series"] is True


def test_main_passes_events_flag_to_cmd_search(monkeypatch):
    seen = {}

    def fake_cmd_search(query, token=None, size=mod.DEFAULT_PAGE_SIZE, top_results=True, only_summary=False, events_only=False):
        seen["query"] = query
        seen["token"] = token
        seen["size"] = size
        seen["top_results"] = top_results
        seen["only_summary"] = only_summary
        seen["events_only"] = events_only

    monkeypatch.setattr(mod, "cmd_search", fake_cmd_search)
    monkeypatch.setattr(mod.sys, "argv", ["m365_mail_search.py", "search", "Workshop", "--events", "--size", "5"])

    mod.main()

    assert seen == {
        "query": "Workshop",
        "token": None,
        "size": 5,
        "top_results": True,
        "only_summary": False,
        "events_only": True,
    }


# ---------------------------------------------------------------------------
# CMD: read  --convert-to-markdown
# ---------------------------------------------------------------------------

def _make_read_msg_payload(msg_id="msg-1", has_attachments=True):
    """Helper: Fake-Payload fuer GET /v1.0/me/messages/{id}."""
    return {
        "id": msg_id,
        "subject": "Test-Mail mit Anhaengen",
        "from": {"emailAddress": {"name": "Alice", "address": "alice@example.com"}},
        "toRecipients": [{"emailAddress": {"name": "Bob", "address": "bob@example.com"}}],
        "ccRecipients": [],
        "receivedDateTime": "2026-04-07T10:00:00Z",
        "body": {"contentType": "text", "content": "Hallo, siehe Anhaenge."},
        "hasAttachments": has_attachments,
        "importance": "normal",
        "conversationId": "conv-1",
    }


def _make_att_payload():
    """Helper: Fake-Payload fuer GET .../attachments mit DOCX + PNG."""
    import base64

    return {
        "value": [
            {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "id": "att-docx",
                "name": "bericht.docx",
                "isInline": False,
                "contentBytes": base64.b64encode(b"fake-docx-content").decode(),
            },
            {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "id": "att-png",
                "name": "foto.png",
                "isInline": False,
                "contentBytes": base64.b64encode(b"fake-png-content").decode(),
            },
        ]
    }


def test_cmd_read_convert_to_markdown_success(tmp_path, monkeypatch, capsys):
    """--convert-to-markdown erzeugt .md-Dateien fuer jeden Anhang (Erfolgsfall)."""
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_resolve_token", lambda _token=None: "token")

    def fake_get(url, headers=None, params=None, timeout=None):
        if "/attachments" in url:
            return FakeResponse(200, _make_att_payload())
        if "/messages/" in url:
            return FakeResponse(200, _make_read_msg_payload())
        raise AssertionError(f"Unexpected GET {url}")

    monkeypatch.setattr(mod.requests, "get", fake_get)

    # Mock file_converter._to_markdown: schreibt einfach "# converted" in die Ausgabedatei
    def fake_to_markdown(input_path, output_path, *, no_llm_pdf=False, no_llm=False, all_sheets=False, debug=False):
        output_path.write_text(f"# {input_path.name}\n\nKonvertierter Inhalt.", encoding="utf-8")
        return 0

    import file_converter
    monkeypatch.setattr(file_converter, "_to_markdown", fake_to_markdown)

    mod.cmd_read("msg-1", save_attachments=False, convert_to_markdown=True)

    stdout = capsys.readouterr().out

    # Anhaenge wurden gespeichert (implizit durch convert_to_markdown)
    assert "bericht.docx" in stdout
    assert "foto.png" in stdout

    # Markdown-Konvertierung gemeldet
    assert "Markdown-Konvertierung OK: bericht.docx -> bericht.md" in stdout
    assert "Markdown-Konvertierung OK: foto.png -> foto.md" in stdout

    # Dateien existieren
    email_dirs = list((tmp_path / "tmp" / "emails").iterdir())
    assert len(email_dirs) == 1
    att_dir = email_dirs[0] / "attachments"
    assert (att_dir / "bericht.docx").is_file()
    assert (att_dir / "bericht.md").is_file()
    assert (att_dir / "foto.png").is_file()
    assert (att_dir / "foto.md").is_file()

    # Markdown-Inhalt korrekt
    md_content = (att_dir / "bericht.md").read_text(encoding="utf-8")
    assert "# bericht.docx" in md_content


def test_cmd_read_convert_to_markdown_failure_writes_error_md(tmp_path, monkeypatch, capsys):
    """Bei fehlgeschlagener Konvertierung wird .md mit Fehlermeldung angelegt."""
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_resolve_token", lambda _token=None: "token")

    def fake_get(url, headers=None, params=None, timeout=None):
        if "/attachments" in url:
            return FakeResponse(200, _make_att_payload())
        if "/messages/" in url:
            return FakeResponse(200, _make_read_msg_payload())
        raise AssertionError(f"Unexpected GET {url}")

    monkeypatch.setattr(mod.requests, "get", fake_get)

    # Mock _to_markdown: erster Anhang OK, zweiter Fehler
    call_count = {"n": 0}

    def fake_to_markdown_partial(input_path, output_path, *, no_llm_pdf=False, no_llm=False, all_sheets=False, debug=False):
        call_count["n"] += 1
        if call_count["n"] == 1:
            output_path.write_text(f"# {input_path.name}\n\nOK.", encoding="utf-8")
            return 0
        # Zweiter Aufruf: Fehler (exit code 1, keine Datei erzeugt)
        return 1

    import file_converter
    monkeypatch.setattr(file_converter, "_to_markdown", fake_to_markdown_partial)

    mod.cmd_read("msg-1", convert_to_markdown=True)

    stdout = capsys.readouterr().out

    # Erster Anhang OK
    assert "Markdown-Konvertierung OK: bericht.docx -> bericht.md" in stdout

    # Zweiter Anhang Fehler auf stdout
    assert "ERROR: Konvertierung von foto.png fehlgeschlagen (exit code 1)" in stdout

    email_dirs = list((tmp_path / "tmp" / "emails").iterdir())
    att_dir = email_dirs[0] / "attachments"

    # Erfolg-MD hat konvertierten Inhalt
    assert (att_dir / "bericht.md").is_file()
    ok_md = (att_dir / "bericht.md").read_text(encoding="utf-8")
    assert "# bericht.docx" in ok_md

    # Fehler-MD existiert und enthaelt Fehlermeldung
    assert (att_dir / "foto.md").is_file()
    err_md = (att_dir / "foto.md").read_text(encoding="utf-8")
    assert "# foto.png" in err_md
    assert "Konvertierung fehlgeschlagen" in err_md
    assert "Exit-Code: 1" in err_md


def test_cmd_read_convert_to_markdown_passes_no_llm_pdf(tmp_path, monkeypatch, capsys):
    """--no-llm-pdf wird korrekt an _to_markdown durchgereicht."""
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_resolve_token", lambda _token=None: "token")

    def fake_get(url, headers=None, params=None, timeout=None):
        if "/attachments" in url:
            return FakeResponse(200, _make_att_payload())
        if "/messages/" in url:
            return FakeResponse(200, _make_read_msg_payload())
        raise AssertionError(f"Unexpected GET {url}")

    monkeypatch.setattr(mod.requests, "get", fake_get)

    seen_flags = []

    def fake_to_markdown(input_path, output_path, *, no_llm_pdf=False, no_llm=False, all_sheets=False, debug=False):
        seen_flags.append(no_llm_pdf)
        output_path.write_text("# ok", encoding="utf-8")
        return 0

    import file_converter
    monkeypatch.setattr(file_converter, "_to_markdown", fake_to_markdown)

    mod.cmd_read("msg-1", convert_to_markdown=True, no_llm_pdf=True)

    # Beide Aufrufe muessen no_llm_pdf=True erhalten haben
    assert len(seen_flags) == 2
    assert all(f is True for f in seen_flags)


# ---------------------------------------------------------------------------
# E2E: read --convert-to-markdown  (echte Graph-API, echte Konvertierung)
# ---------------------------------------------------------------------------

MAIL_SCRIPT = str(
    WORKSPACE
    / ".agents" / "skills" / "skill-m365-copilot-mail-search" / "scripts"
    / "m365_mail_search.py"
)
TEST_MSG_ID = (
    "AAMkADQxNDFkMThlLWViMGQtNGU2Mi04YWI3LTEwOWVkNmVmN2QzOQBG"
    "AAAAAAARqUXzjL2ESqXfYRm8jmgxBwA9a2QUdu57QZSNjZqqqu-zAAMk"
    "fo4yAAA9a2QUdu57QZSNjZqqqu-zAAYTy1TLAAA="
)
E2E_TIMEOUT = 600  # 10 min — LLM-Pipeline braucht Zeit

_EXPECTED_CONTENT = [
    ("TestPDF.pdf", "TestPDF"),
    ("TestPNG.png", "Bildinfo 456"),
    ("TestPPTX.pptx", "Bildinfo 123"),
    ("TestXLSX-lang.xlsx", "Test Excel"),
]


@pytest.mark.e2e
def test_cmd_read_convert_to_markdown_e2e():
    """E2E: Echte Mail per Graph API lesen, Anhaenge herunterladen, nach Markdown konvertieren.

    Benoetigt gueltigen Mail.Read Token (wird uebersprungen wenn nicht vorhanden).
    Test-Mail enthaelt TestPDF.pdf, TestPNG.png, TestPPTX.pptx, TestXLSX-lang.xlsx.
    """
    # Vorherige Artefakte loeschen, damit _unique_att_path keine (2)-Suffixe erzeugt
    known_out_dir = WORKSPACE / "tmp" / "emails" / "20260406_1331_tobias_carsten_mueller_test_email_e7fc84fd"
    if known_out_dir.exists():
        shutil.rmtree(known_out_dir)

    result = subprocess.run(
        [
            sys.executable, MAIL_SCRIPT,
            "read", TEST_MSG_ID,
            "--save-attachments", "--convert-to-markdown",
        ],
        capture_output=True,
        text=True,
        timeout=E2E_TIMEOUT,
    )

    if result.returncode == 2:
        pytest.skip(f"Kein gueltiger Token: {result.stderr.strip()}")

    assert result.returncode == 0, (
        f"read fehlgeschlagen (rc={result.returncode})\n"
        f"stdout: {result.stdout[:500]}\nstderr: {result.stderr[:500]}"
    )

    # Ausgabe-Ordner aus stdout parsen
    match = re.search(r"Gespeichert in:\s*(.+)", result.stdout)
    assert match, f"'Gespeichert in:' nicht in stdout:\n{result.stdout[:500]}"
    out_dir = WORKSPACE / match.group(1).strip()
    att_dir = out_dir / "attachments"

    assert att_dir.is_dir(), f"attachments/ nicht angelegt: {att_dir}"

    # Jeder Anhang: Original + Markdown pruefen (identisch zu test_file_converter_e2e.py)
    for filename, expected_text in _EXPECTED_CONTENT:
        stem = Path(filename).stem
        md_name = f"{stem}.md"

        # Original-Anhang gespeichert
        att_file = att_dir / filename
        assert att_file.is_file(), f"Anhang fehlt: {att_file}"
        assert att_file.stat().st_size > 0, f"Anhang leer: {att_file}"

        # Markdown-Datei erzeugt
        md_file = att_dir / md_name
        assert md_file.is_file(), f"Markdown fehlt: {md_file}"
        content = md_file.read_text(encoding="utf-8")
        assert len(content.strip()) > 0, f"Markdown leer: {md_file}"
        assert expected_text.lower() in content.lower(), (
            f"Erwarteter Text '{expected_text}' nicht in {md_name} gefunden.\n"
            f"Inhalt (erste 500 Zeichen): {content[:500]}"
        )

    # stdout muss Erfolg fuer alle 4 Anhaenge melden
    for filename, _ in _EXPECTED_CONTENT:
        stem = Path(filename).stem
        assert f"Markdown-Konvertierung OK: {filename} -> {stem}.md" in result.stdout, (
            f"Erfolgsmeldung fuer {filename} fehlt in stdout"
        )


# ---------------------------------------------------------------------------
# SharePoint/OneDrive-Link-Download in cmd_read
# ---------------------------------------------------------------------------

def _make_read_msg_payload_with_sp_links(msg_id="msg-1"):
    """Fake-Payload fuer Message mit SharePoint-Links im HTML-Body."""
    return {
        "id": msg_id,
        "subject": "Mail mit SharePoint-Links",
        "from": {"emailAddress": {"name": "Alice", "address": "alice@example.com"}},
        "toRecipients": [{"emailAddress": {"name": "Bob", "address": "bob@example.com"}}],
        "ccRecipients": [],
        "receivedDateTime": "2026-04-07T10:00:00Z",
        "body": {
            "contentType": "html",
            "content": (
                '<p>Siehe Anhang:</p>'
                '<a href="https://contoso.sharepoint.com/sites/team/Shared%20Documents/Report.xlsx?d=w123&amp;csf=1&amp;web=1">Report.xlsx</a>'
                '<a href="https://contoso.sharepoint.com/sites/team/Shared%20Documents/Spec.pdf?d=w456&amp;csf=1&amp;web=1">Spec.pdf</a>'
            ),
        },
        "hasAttachments": False,
        "importance": "normal",
        "conversationId": "conv-sp",
    }


def test_cmd_read_downloads_sharepoint_links(tmp_path, monkeypatch, capsys):
    """cmd_read mit --save-attachments laedt SP-Links aus dem Mail-Body herunter."""
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_resolve_token", lambda _token=None: "token")

    def fake_get(url, headers=None, params=None, timeout=None):
        if "/attachments" in url:
            return FakeResponse(200, {"value": []})
        if "/messages/" in url:
            return FakeResponse(200, _make_read_msg_payload_with_sp_links())
        raise AssertionError(f"Unexpected GET {url}")

    monkeypatch.setattr(mod.requests, "get", fake_get)

    # Mock _try_download_sp_file: simuliert erfolgreichen Download
    downloaded_urls: list[str] = []

    def fake_try_download(url: str, att_dir: Path):
        downloaded_urls.append(url)
        att_dir.mkdir(parents=True, exist_ok=True)
        from urllib.parse import unquote, urlparse
        filename = unquote(urlparse(url).path.split("/")[-1])
        dest = att_dir / filename
        dest.write_bytes(b"fake-sp-content")
        return dest, None

    monkeypatch.setattr(mod, "_try_download_sp_file", fake_try_download)

    mod.cmd_read("msg-1", save_attachments=True)

    stdout = capsys.readouterr().out

    # Beide SP-Links erkannt und heruntergeladen
    assert len(downloaded_urls) == 2
    assert any("Report.xlsx" in u for u in downloaded_urls)
    assert any("Spec.pdf" in u for u in downloaded_urls)
    # URLs muessen dekodiert sein (kein &amp;)
    for u in downloaded_urls:
        assert "&amp;" not in u, f"URL enthaelt noch HTML-Entities: {u}"

    # Konsolenausgabe enthaelt SP-Download-Meldungen
    assert "SharePoint/OneDrive-Link(s) erkannt" in stdout
    assert "SP-Download OK" in stdout

    # Dateien in email.md als Anhaenge gelistet
    email_dirs = list((tmp_path / "tmp" / "emails").iterdir())
    assert len(email_dirs) == 1
    email_md = (email_dirs[0] / "email.md").read_text(encoding="utf-8")
    assert "Report.xlsx" in email_md
    assert "Spec.pdf" in email_md

    # Dateien existieren im attachments-Ordner
    att_dir = email_dirs[0] / "attachments"
    assert (att_dir / "Report.xlsx").is_file()
    assert (att_dir / "Spec.pdf").is_file()


def test_cmd_read_no_sp_download_without_save_attachments(tmp_path, monkeypatch, capsys):
    """Ohne --save-attachments werden SP-Links nicht heruntergeladen."""
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_resolve_token", lambda _token=None: "token")

    def fake_get(url, headers=None, params=None, timeout=None):
        if "/attachments" in url:
            return FakeResponse(200, {"value": []})
        if "/messages/" in url:
            return FakeResponse(200, _make_read_msg_payload_with_sp_links())
        raise AssertionError(f"Unexpected GET {url}")

    monkeypatch.setattr(mod.requests, "get", fake_get)

    download_called = {"called": False}

    def fake_try_download(url, att_dir):
        download_called["called"] = True
        return None, "should not be called"

    monkeypatch.setattr(mod, "_try_download_sp_file", fake_try_download)

    mod.cmd_read("msg-1", save_attachments=False)

    assert not download_called["called"], "SP-Download sollte ohne --save-attachments nicht aufgerufen werden"

    # SP-Links muessen trotzdem in email.md und stdout stehen
    stdout = capsys.readouterr().out
    assert "SharePoint-Links:" in stdout
    assert "Report.xlsx" in stdout
    assert "Spec.pdf" in stdout

    email_dirs = list((tmp_path / "tmp" / "emails").iterdir())
    email_md = (email_dirs[0] / "email.md").read_text(encoding="utf-8")
    assert "SharePoint-Links:" in email_md
    assert "Report.xlsx" in email_md
    assert "Spec.pdf" in email_md


def test_cmd_read_sp_download_failure_is_non_blocking(tmp_path, monkeypatch, capsys):
    """Fehlgeschlagener SP-Download bricht cmd_read nicht ab."""
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_resolve_token", lambda _token=None: "token")

    def fake_get(url, headers=None, params=None, timeout=None):
        if "/attachments" in url:
            return FakeResponse(200, {"value": []})
        if "/messages/" in url:
            return FakeResponse(200, _make_read_msg_payload_with_sp_links())
        raise AssertionError(f"Unexpected GET {url}")

    monkeypatch.setattr(mod.requests, "get", fake_get)

    def fake_try_download_fail(url, att_dir):
        return None, "Token nicht verfuegbar"

    monkeypatch.setattr(mod, "_try_download_sp_file", fake_try_download_fail)

    # Soll nicht abstuerzen
    mod.cmd_read("msg-1", save_attachments=True)

    stderr = capsys.readouterr().err
    assert "SP-Download fehlgeschlagen" in stderr
    assert "Token nicht verfuegbar" in stderr

    # email.md trotzdem erstellt
    email_dirs = list((tmp_path / "tmp" / "emails").iterdir())
    assert len(email_dirs) == 1
    assert (email_dirs[0] / "email.md").is_file()


def test_cmd_read_sp_download_with_convert_to_markdown(tmp_path, monkeypatch, capsys):
    """SP-Downloads werden bei --convert-to-markdown nach Markdown konvertiert."""
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_resolve_token", lambda _token=None: "token")

    def fake_get(url, headers=None, params=None, timeout=None):
        if "/attachments" in url:
            return FakeResponse(200, {"value": []})
        if "/messages/" in url:
            return FakeResponse(200, _make_read_msg_payload_with_sp_links())
        raise AssertionError(f"Unexpected GET {url}")

    monkeypatch.setattr(mod.requests, "get", fake_get)

    def fake_try_download(url, att_dir):
        att_dir.mkdir(parents=True, exist_ok=True)
        from urllib.parse import unquote, urlparse
        filename = unquote(urlparse(url).path.split("/")[-1])
        dest = att_dir / filename
        dest.write_bytes(b"fake-content")
        return dest, None

    monkeypatch.setattr(mod, "_try_download_sp_file", fake_try_download)

    def fake_to_markdown(input_path, output_path, *, no_llm_pdf=False, no_llm=False, all_sheets=False, debug=False):
        output_path.write_text(f"# {input_path.name}\n\nKonvertiert.", encoding="utf-8")
        return 0

    import file_converter
    monkeypatch.setattr(file_converter, "_to_markdown", fake_to_markdown)

    mod.cmd_read("msg-1", convert_to_markdown=True)

    stdout = capsys.readouterr().out

    assert "SP-Download OK" in stdout
    assert "Markdown-Konvertierung OK: Report.xlsx -> Report.md" in stdout
    assert "Markdown-Konvertierung OK: Spec.pdf -> Spec.md" in stdout

    email_dirs = list((tmp_path / "tmp" / "emails").iterdir())
    att_dir = email_dirs[0] / "attachments"
    assert (att_dir / "Report.md").is_file()
    assert (att_dir / "Spec.md").is_file()


def test_extract_cloud_links_decodes_html_entities():
    """_extract_cloud_links_from_body dekodiert &amp; in URLs korrekt."""
    html = (
        '<a href="https://contoso.sharepoint.com/doc.xlsx?d=w1&amp;csf=1&amp;web=1">doc.xlsx</a>'
    )
    entries = mod._extract_cloud_links_from_body(html, "html")
    assert len(entries) == 1
    assert "&amp;" not in entries[0]["url"], "HTML-Entities muessen dekodiert sein"
    assert "&" in entries[0]["url"]
    assert entries[0]["url"] == "https://contoso.sharepoint.com/doc.xlsx?d=w1&csf=1&web=1"


def test_cmd_read_no_sp_links_in_body(tmp_path, monkeypatch, capsys):
    """Mail ohne SP-Links loest keinen SP-Download aus."""
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_resolve_token", lambda _token=None: "token")

    def fake_get(url, headers=None, params=None, timeout=None):
        if "/attachments" in url:
            return FakeResponse(200, _make_att_payload())
        if "/messages/" in url:
            return FakeResponse(200, _make_read_msg_payload())
        raise AssertionError(f"Unexpected GET {url}")

    monkeypatch.setattr(mod.requests, "get", fake_get)

    download_called = {"called": False}

    def fake_try_download(url, att_dir):
        download_called["called"] = True
        return None, "unexpected"

    monkeypatch.setattr(mod, "_try_download_sp_file", fake_try_download)

    mod.cmd_read("msg-1", save_attachments=True)

    assert not download_called["called"], "SP-Download soll nicht aufgerufen werden wenn keine SP-Links im Body"


# ---------------------------------------------------------------------------
# Inline-Bild LLM-Beschreibung
# ---------------------------------------------------------------------------

def _make_msg_with_inline_image(msg_id="msg-inline"):
    """Fake-Payload fuer Mail mit Inline-Bild im HTML-Body."""
    return {
        "id": msg_id,
        "subject": "Mail mit Screenshot",
        "from": {"emailAddress": {"name": "Alice", "address": "alice@example.com"}},
        "toRecipients": [{"emailAddress": {"name": "Bob", "address": "bob@example.com"}}],
        "ccRecipients": [],
        "receivedDateTime": "2026-04-07T10:00:00Z",
        "body": {
            "contentType": "html",
            "content": '<p>Hallo, hier der Screenshot:</p><img src="cid:img001" /><p>Ende.</p>',
        },
        "hasAttachments": True,
        "importance": "normal",
        "conversationId": "conv-inline",
    }


def _make_inline_att_payload():
    """Fake-Payload mit einem Inline-Bild-Attachment."""
    import base64
    return {
        "value": [
            {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "id": "att-inline-1",
                "name": "screenshot.png",
                "isInline": True,
                "contentId": "img001",
                "contentBytes": base64.b64encode(b"fake-png-bytes").decode(),
            },
        ]
    }


def test_cmd_read_inline_image_llm_description_default(tmp_path, monkeypatch, capsys):
    """Inline-Bilder werden standardmaessig per LLM beschrieben und im Body eingebettet."""
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_resolve_token", lambda _token=None: "token")

    def fake_get(url, headers=None, params=None, timeout=None):
        if "/attachments" in url:
            return FakeResponse(200, _make_inline_att_payload())
        if "/messages/" in url:
            return FakeResponse(200, _make_msg_with_inline_image())
        raise AssertionError(f"Unexpected GET {url}")

    monkeypatch.setattr(mod.requests, "get", fake_get)

    to_markdown_calls = []

    def fake_to_markdown(input_path, output_path, *, no_llm_pdf=False, no_llm=False, all_sheets=False, debug=False):
        to_markdown_calls.append(input_path.name)
        output_path.write_text("*Caption: Architekturdiagramm mit 3 Komponenten*\n\nDas Bild zeigt eine Systemarchitektur.", encoding="utf-8")
        return 0

    import file_converter
    monkeypatch.setattr(file_converter, "_to_markdown", fake_to_markdown)

    mod.cmd_read("msg-inline")

    stdout = capsys.readouterr().out

    # _to_markdown wurde fuer das Inline-Bild aufgerufen
    assert "screenshot.png" in to_markdown_calls

    # LLM-Beschreibung im Body eingebettet
    assert "Architekturdiagramm" in stdout
    assert "Systemarchitektur" in stdout

    # email.md enthaelt die Beschreibung
    email_dirs = list((tmp_path / "tmp" / "emails").iterdir())
    assert len(email_dirs) == 1
    email_md = (email_dirs[0] / "email.md").read_text(encoding="utf-8")
    assert "Architekturdiagramm" in email_md
    assert "Inline-Bilder (LLM-beschrieben):" in email_md
    assert "![Bild](" not in email_md  # Roher Bildlink ersetzt


def test_cmd_read_inline_image_no_inline_llm_opt_out(tmp_path, monkeypatch, capsys):
    """--no-inline-llm deaktiviert LLM-Beschreibung, nur ![Bild](pfad) bleibt."""
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_resolve_token", lambda _token=None: "token")

    def fake_get(url, headers=None, params=None, timeout=None):
        if "/attachments" in url:
            return FakeResponse(200, _make_inline_att_payload())
        if "/messages/" in url:
            return FakeResponse(200, _make_msg_with_inline_image())
        raise AssertionError(f"Unexpected GET {url}")

    monkeypatch.setattr(mod.requests, "get", fake_get)

    to_markdown_calls = []

    def fake_to_markdown(input_path, output_path, *, no_llm_pdf=False, no_llm=False, all_sheets=False, debug=False):
        to_markdown_calls.append(input_path.name)
        return 0

    import file_converter
    monkeypatch.setattr(file_converter, "_to_markdown", fake_to_markdown)

    mod.cmd_read("msg-inline", no_inline_llm=True)

    stdout = capsys.readouterr().out

    # _to_markdown wurde NICHT aufgerufen
    assert len(to_markdown_calls) == 0

    # Body enthaelt nur den rohen Bildlink
    assert "![Bild](" in stdout

    # email.md Header sagt "Inline-Bilder:" (nicht LLM-beschrieben)
    email_dirs = list((tmp_path / "tmp" / "emails").iterdir())
    email_md = (email_dirs[0] / "email.md").read_text(encoding="utf-8")
    assert "Inline-Bilder:" in email_md
    assert "LLM-beschrieben" not in email_md


def test_cmd_read_inline_image_llm_failure_non_blocking(tmp_path, monkeypatch, capsys):
    """Fehlgeschlagene LLM-Konvertierung bricht cmd_read nicht ab."""
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_resolve_token", lambda _token=None: "token")

    def fake_get(url, headers=None, params=None, timeout=None):
        if "/attachments" in url:
            return FakeResponse(200, _make_inline_att_payload())
        if "/messages/" in url:
            return FakeResponse(200, _make_msg_with_inline_image())
        raise AssertionError(f"Unexpected GET {url}")

    monkeypatch.setattr(mod.requests, "get", fake_get)

    def fake_to_markdown_crash(input_path, output_path, *, no_llm_pdf=False, no_llm=False, all_sheets=False, debug=False):
        raise RuntimeError("LLM nicht erreichbar")

    import file_converter
    monkeypatch.setattr(file_converter, "_to_markdown", fake_to_markdown_crash)

    # Soll nicht abstuerzen
    mod.cmd_read("msg-inline")

    out = capsys.readouterr()

    # Warning auf stderr
    assert "LLM-Beschreibung" in out.err
    assert "screenshot.png" in out.err

    # email.md trotzdem erstellt mit Fallback (roher Bildlink)
    email_dirs = list((tmp_path / "tmp" / "emails").iterdir())
    assert len(email_dirs) == 1
    email_md = (email_dirs[0] / "email.md").read_text(encoding="utf-8")
    assert "Inline-Bilder (LLM-beschrieben):" not in email_md
    assert "Inline-Bilder (Konvertierungsfehler):" in email_md
    assert "- screenshot.png (Konvertierungsfehler)" in email_md
    assert "![Bild](" in email_md


# ---------------------------------------------------------------------------
# _html_to_text table conversion
# ---------------------------------------------------------------------------

def test_html_to_text_converts_simple_table_to_markdown():
    html = (
        "<table>"
        "<tr><th>Jahr</th><th>AL</th><th>EL Euro</th></tr>"
        "<tr><td>26</td><td>EKEA</td><td>48.083,43 €</td></tr>"
        "<tr><td>26</td><td>EKEB</td><td>13.130,57 €</td></tr>"
        "</table>"
    )
    result = mod._html_to_text(html)

    # Erste Zeile: Header
    lines = [l for l in result.splitlines() if l.strip()]
    assert lines[0] == "| Jahr | AL | EL Euro |"
    # Zweite Zeile: Separator
    assert lines[1] == "| --- | --- | --- |"
    # Datenzeilen
    assert "| 26 | EKEA | 48.083,43 € |" in result
    assert "| 26 | EKEB | 13.130,57 € |" in result
    # Kein vertikales Spaltendump mehr
    assert "26\nEKEA" not in result


def test_html_to_text_table_with_nested_p_tags():
    html = (
        "<table>"
        "<tr><th><p>Spalte A</p></th><th><p>Spalte B</p></th></tr>"
        "<tr><td><p>Wert 1</p></td><td><p>100,00 €</p></td></tr>"
        "</table>"
    )
    result = mod._html_to_text(html)
    assert "| Spalte A | Spalte B |" in result
    assert "| Wert 1 | 100,00 € |" in result


def test_html_to_text_table_pipe_in_cell_is_escaped():
    html = "<table><tr><th>A</th><th>B</th></tr><tr><td>x|y</td><td>z</td></tr></table>"
    result = mod._html_to_text(html)
    assert r"x\|y" in result


def test_html_to_text_mixed_content_table_and_text():
    html = "<p>Vor der Tabelle</p><table><tr><td>Zelle</td></tr></table><p>Nach der Tabelle</p>"
    result = mod._html_to_text(html)
    assert "Vor der Tabelle" in result
    assert "| Zelle |" in result
    assert "Nach der Tabelle" in result


def test_process_inline_and_body_collapses_whitespace_only_lines_from_unique_body_html(tmp_path):
    html = (
        "<html><body><div>\r\n"
        "<div>\r\n"
        '<p style="margin:0;">Moin,</p>\r\n'
        '<p style="margin:0;">&nbsp;</p>\r\n'
        '<p style="margin:0;">heute gibt es ein Update.</p>\r\n'
        '<p style="margin:0;"><br></p>\r\n'
        '<p style="margin:0;">Gruss,</p>\r\n'
        "</div>\r\n"
        "</div></body></html>"
    )

    body_text, _, inline_saved, _, _ = mod._process_inline_and_body(
        html, "html", [], tmp_path / "attachments"
    )

    assert inline_saved == []
    assert body_text == "Moin,\n\nheute gibt es ein Update.\n\nGruss,"


def test_unique_att_path_reuses_identical_file_and_suffixes_different_content(tmp_path):
    att_dir = tmp_path / "attachments"
    att_dir.mkdir()

    existing = att_dir / "report.pdf"
    existing.write_bytes(b"same-bytes")

    same_path = mod._unique_att_path(att_dir, "report.pdf", b"same-bytes")
    other_path = mod._unique_att_path(att_dir, "report.pdf", b"other-bytes")

    assert same_path == existing
    assert other_path == att_dir / "report (2).pdf"


# ---------------------------------------------------------------------------
# cmd_read_thread tests
# ---------------------------------------------------------------------------

def _make_thread_msg(msg_id, subject, sender_name, sender_addr, received,
                     unique_body="", body="", has_attachments=False,
                     to=None, cc=None, importance="normal"):
    """Helper: baut ein Graph-API message dict fuer Thread-Tests."""
    m = {
        "id": msg_id,
        "subject": subject,
        "from": {"emailAddress": {"name": sender_name, "address": sender_addr}},
        "toRecipients": [{"emailAddress": {"name": n, "address": a}} for n, a in (to or [])],
        "ccRecipients": [{"emailAddress": {"name": n, "address": a}} for n, a in (cc or [])],
        "receivedDateTime": received,
        "uniqueBody": {"content": unique_body, "contentType": "text"},
        "body": {"content": body, "contentType": "text"},
        "hasAttachments": has_attachments,
        "importance": importance,
    }
    return m


def test_cmd_read_thread_reverse_chronological_with_unique_body(tmp_path, monkeypatch, capsys):
    """Thread-Mails werden neuste-zuerst ausgegeben, uniqueBody wird bevorzugt."""
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_resolve_token", lambda _token=None: "tok")

    msgs = [
        _make_thread_msg("m1", "Thema", "Alice", "alice@vw.de", "2026-04-05T10:00:00Z",
                         unique_body="Erste Nachricht komplett", body="Erste Nachricht komplett",
                         to=[("Bob", "bob@vw.de")]),
        _make_thread_msg("m2", "RE: Thema", "Bob", "bob@vw.de", "2026-04-06T11:00:00Z",
                         unique_body="Bobs Antwort nur neu", body="Bobs Antwort nur neu\n>Erste Nachricht komplett",
                         to=[("Alice", "alice@vw.de")]),
        _make_thread_msg("m3", "RE: Thema", "Alice", "alice@vw.de", "2026-04-07T09:00:00Z",
                         unique_body="Alices Rueckmeldung", body="Alices Rueckmeldung\n>Bobs Antwort\n>Erste Nachricht",
                         to=[("Bob", "bob@vw.de")]),
    ]

    call_count = [0]

    def fake_get(url, headers=None, params=None, timeout=None):
        call_count[0] += 1
        if call_count[0] == 1:
            # Seed-Mail
            return FakeResponse(200, {"conversationId": "conv-1", "subject": "Thema"})
        if call_count[0] == 2:
            # Thread-Abfrage
            return FakeResponse(200, {"value": msgs})
        return FakeResponse(200, {"value": []})

    monkeypatch.setattr(mod.requests, "get", fake_get)

    mod.cmd_read_thread("m1")

    out = capsys.readouterr().out
    # Thread-Header
    assert "Thread: Thema (3 Nachrichten)" in out
    # Anzeige: neueste zuerst, aber mit chronologischer Positionsnummer
    assert "=== Email [3/3] ===" in out
    assert "=== Email [2/3] ===" in out
    assert "=== Email [1/3] ===" in out
    pos_3 = out.index("=== Email [3/3] ===")
    pos_2 = out.index("=== Email [2/3] ===")
    pos_1 = out.index("=== Email [1/3] ===")
    assert pos_3 < pos_2 < pos_1
    # uniqueBody wird verwendet, nicht body mit Quotes
    assert "Alices Rueckmeldung" in out
    assert "Bobs Antwort nur neu" in out
    assert "Erste Nachricht komplett" in out
    # Keine Quotes aus body
    assert ">Erste Nachricht" not in out
    assert ">Bobs Antwort" not in out


def test_cmd_read_thread_falls_back_to_body(tmp_path, monkeypatch, capsys):
    """Wenn uniqueBody leer ist, wird body.content verwendet."""
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_resolve_token", lambda _token=None: "tok")

    msgs = [
        _make_thread_msg("m1", "Test", "Alice", "alice@vw.de", "2026-04-05T10:00:00Z",
                         unique_body="", body="Fallback-Body-Inhalt",
                         to=[("Bob", "bob@vw.de")]),
    ]

    call_count = [0]

    def fake_get(url, headers=None, params=None, timeout=None):
        call_count[0] += 1
        if call_count[0] == 1:
            return FakeResponse(200, {"conversationId": "conv-2", "subject": "Test"})
        if call_count[0] == 2:
            return FakeResponse(200, {"value": msgs})
        return FakeResponse(200, {"value": []})

    monkeypatch.setattr(mod.requests, "get", fake_get)

    mod.cmd_read_thread("m1")

    out = capsys.readouterr().out
    assert "Fallback-Body-Inhalt" in out


def test_cmd_read_thread_shows_attachments_per_mail(tmp_path, monkeypatch, capsys):
    """Anhaenge werden bei der jeweiligen Mail angezeigt, nicht zentral."""
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_resolve_token", lambda _token=None: "tok")

    msgs = [
        _make_thread_msg("m1", "Thema", "Alice", "alice@vw.de", "2026-04-05T10:00:00Z",
                         unique_body="Erste Mail", has_attachments=True,
                         to=[("Bob", "bob@vw.de")]),
        _make_thread_msg("m2", "RE: Thema", "Bob", "bob@vw.de", "2026-04-06T11:00:00Z",
                         unique_body="Antwort ohne Anhang", has_attachments=False,
                         to=[("Alice", "alice@vw.de")]),
    ]

    call_count = [0]

    def fake_get(url, headers=None, params=None, timeout=None):
        call_count[0] += 1
        if call_count[0] == 1:
            return FakeResponse(200, {"conversationId": "conv-3", "subject": "Thema"})
        if call_count[0] == 2:
            return FakeResponse(200, {"value": msgs})
        if "/attachments" in url:
            return FakeResponse(200, {"value": [
                {"id": "a1", "name": "Projektplan.pdf", "size": 12345,
                 "contentType": "application/pdf", "isInline": False},
                {"id": "a2", "name": "sig.png", "size": 100,
                 "contentType": "image/png", "isInline": True},
            ]})
        return FakeResponse(200, {"value": []})

    monkeypatch.setattr(mod.requests, "get", fake_get)

    mod.cmd_read_thread("m1")

    out = capsys.readouterr().out
    # Mail 2 (neueste, Bob) hat keine Anhaenge
    # Mail 1 (Alice) hat Projektplan.pdf; Inline-Bilder werden separat wie in read angezeigt
    assert "- Projektplan.pdf" in out
    assert "Inline-Bilder:" in out
    assert "- sig.png" in out
    # Bob's Mail zeigt "Anhaenge: -"
    # Zaehle wie oft "Anhaenge:" vorkommt (sollte 2x sein, einmal pro Mail)
    assert out.count("Anhaenge:") == 2


def test_cmd_read_thread_uses_lightweight_attachment_fetch_without_convert(tmp_path, monkeypatch, capsys):
    """Plain read_thread soll Attachments ohne contentBytes nachladen koennen."""
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_resolve_token", lambda _token=None: "tok")

    msgs = [
        _make_thread_msg(
            "m1", "Thema", "Alice", "alice@vw.de", "2026-04-05T10:00:00Z",
            unique_body="Erste Mail", has_attachments=True, to=[("Bob", "bob@vw.de")],
        ),
    ]

    attachment_params = []
    call_count = [0]

    def fake_get(url, headers=None, params=None, timeout=None):
        call_count[0] += 1
        if call_count[0] == 1:
            return FakeResponse(200, {"conversationId": "conv-light", "subject": "Thema"})
        if call_count[0] == 2:
            return FakeResponse(200, {"value": msgs})
        if "/attachments" in url:
            attachment_params.append(params)
            return FakeResponse(200, {"value": [
                {"id": "a1", "name": "Projektplan.pdf", "isInline": False},
                {"id": "a2", "name": "sig.png", "isInline": True, "contentId": "img1"},
            ]})
        return FakeResponse(200, {"value": []})

    monkeypatch.setattr(mod.requests, "get", fake_get)

    mod.cmd_read_thread("m1")

    out = capsys.readouterr().out
    assert "- Projektplan.pdf" in out
    assert attachment_params == [{"$select": "id,name,isInline,contentId,contentType,size"}]


def test_cmd_read_thread_html_tables_rendered_as_markdown(tmp_path, monkeypatch, capsys):
    """HTML-Tabellen im uniqueBody werden als Markdown-Tabellen gerendert."""
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_resolve_token", lambda _token=None: "tok")

    html_body = "<p>Ergebnis:</p><table><tr><th>Name</th><th>Wert</th></tr><tr><td>Alpha</td><td>100</td></tr></table>"
    msgs = [{
        "id": "m1", "subject": "Tabelle", "receivedDateTime": "2026-04-05T10:00:00Z",
        "from": {"emailAddress": {"name": "Alice", "address": "alice@vw.de"}},
        "toRecipients": [], "ccRecipients": [],
        "uniqueBody": {"content": html_body, "contentType": "html"},
        "body": {"content": html_body, "contentType": "html"},
        "hasAttachments": False, "importance": "normal",
    }]

    call_count = [0]

    def fake_get(url, headers=None, params=None, timeout=None):
        call_count[0] += 1
        if call_count[0] == 1:
            return FakeResponse(200, {"conversationId": "conv-t", "subject": "Tabelle"})
        if call_count[0] == 2:
            return FakeResponse(200, {"value": msgs})
        return FakeResponse(200, {"value": []})

    monkeypatch.setattr(mod.requests, "get", fake_get)

    mod.cmd_read_thread("m1")

    out = capsys.readouterr().out
    assert "| Name | Wert |" in out
    assert "| Alpha | 100 |" in out


def test_cmd_read_thread_writes_email_thread_md(tmp_path, monkeypatch, capsys):
    """read_thread schreibt analog zu read eine email_thread.md in tmp/threads."""
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_resolve_token", lambda _token=None: "tok")

    msgs = [
        _make_thread_msg(
            "m1", "Thema", "Alice", "alice@vw.de", "2026-04-05T10:00:00Z",
            unique_body="Erste Nachricht", body="Erste Nachricht",
            to=[("Bob", "bob@vw.de")],
        ),
        _make_thread_msg(
            "m2", "RE: Thema", "Bob", "bob@vw.de", "2026-04-06T11:00:00Z",
            unique_body="Zweite Nachricht", body="Zweite Nachricht",
            to=[("Alice", "alice@vw.de")],
        ),
    ]

    call_count = [0]

    def fake_get(url, headers=None, params=None, timeout=None):
        call_count[0] += 1
        if call_count[0] == 1:
            return FakeResponse(200, {"conversationId": "conv-md", "subject": "Thema"})
        if call_count[0] == 2:
            return FakeResponse(200, {"value": msgs})
        return FakeResponse(200, {"value": []})

    monkeypatch.setattr(mod.requests, "get", fake_get)

    mod.cmd_read_thread("m1")

    out = capsys.readouterr().out
    assert "Gespeichert in:" in out

    thread_files = list((tmp_path / "tmp" / "threads").glob("*/email_thread.md"))
    assert len(thread_files) == 1
    content = thread_files[0].read_text(encoding="utf-8")
    assert "=== Thread: Thema (2 Nachrichten) ===" in content
    assert "=== Email [2/2] ===" in content
    assert "=== Email [1/2] ===" in content
    assert "Zweite Nachricht" in content
    assert "Erste Nachricht" in content


def test_cmd_read_thread_convert_outputs_attachment_text_per_email(tmp_path, monkeypatch, capsys):
    """--convert gibt konvertierte Attachment-Inhalte pro Mail aus."""
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_resolve_token", lambda _token=None: "tok")

    msgs = [
        _make_thread_msg(
            "m1", "Thema", "Alice", "alice@vw.de", "2026-04-05T10:00:00Z",
            unique_body="Erste Nachricht", body="Erste Nachricht", has_attachments=True,
            to=[("Bob", "bob@vw.de")],
        ),
    ]

    call_count = [0]

    def fake_get(url, headers=None, params=None, timeout=None):
        call_count[0] += 1
        if call_count[0] == 1:
            return FakeResponse(200, {"conversationId": "conv-convert", "subject": "Thema"})
        if call_count[0] == 2:
            return FakeResponse(200, {"value": msgs})
        if "/attachments" in url:
            return FakeResponse(200, _make_att_payload())
        return FakeResponse(200, {"value": []})

    monkeypatch.setattr(mod.requests, "get", fake_get)

    import file_parsers

    def fake_convert_bytes(raw_bytes, att_name):
        return f"Konvertierter Inhalt fuer {att_name}"

    monkeypatch.setattr(file_parsers, "convert_bytes", fake_convert_bytes)

    mod.cmd_read_thread("m1", convert=True)

    out = capsys.readouterr().out
    assert "Anhang: bericht.docx" in out
    assert "Konvertierter Inhalt fuer bericht.docx" in out
    assert "Anhang: foto.png" in out
    assert "Konvertierter Inhalt fuer foto.png" in out


def test_cmd_read_thread_reuses_identical_forwarded_attachments(tmp_path, monkeypatch, capsys):
    """Identische Anhaenge in mehreren Thread-Mails werden nicht als (2) dupliziert."""
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_resolve_token", lambda _token=None: "tok")

    msgs = [
        _make_thread_msg(
            "m1", "Thema", "Alice", "alice@vw.de", "2026-04-05T10:00:00Z",
            unique_body="Erste Nachricht", body="Erste Nachricht", has_attachments=True,
            to=[("Bob", "bob@vw.de")],
        ),
        _make_thread_msg(
            "m2", "RE: Thema", "Bob", "bob@vw.de", "2026-04-06T11:00:00Z",
            unique_body="Weitergeleitet", body="Weitergeleitet", has_attachments=True,
            to=[("Alice", "alice@vw.de")],
        ),
    ]

    shared_attachment = {
        "value": [
            {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "id": "att-docx",
                "name": "bericht.docx",
                "isInline": False,
                "contentBytes": base64.b64encode(b"identical-content").decode(),
            }
        ]
    }

    call_count = [0]

    def fake_get(url, headers=None, params=None, timeout=None):
        call_count[0] += 1
        if call_count[0] == 1:
            return FakeResponse(200, {"conversationId": "conv-dedup", "subject": "Thema"})
        if call_count[0] == 2:
            return FakeResponse(200, {"value": msgs})
        if "/attachments" in url:
            return FakeResponse(200, shared_attachment)
        return FakeResponse(200, {"value": []})

    monkeypatch.setattr(mod.requests, "get", fake_get)

    mod.cmd_read_thread("m1", save_attachments=True)

    out = capsys.readouterr().out
    assert "bericht (2).docx" not in out

    thread_dirs = list((tmp_path / "tmp" / "threads").iterdir())
    assert len(thread_dirs) == 1
    files = sorted(p.name for p in (thread_dirs[0] / "attachments").iterdir())
    assert files == ["bericht.docx"]


def test_cmd_read_thread_convert_to_markdown_implicit_save_and_flags(tmp_path, monkeypatch, capsys):
    """--convert-to-markdown impliziert save_attachments und reicht Flags durch."""
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_resolve_token", lambda _token=None: "tok")

    msgs = [
        _make_thread_msg(
            "m1", "Thema", "Alice", "alice@vw.de", "2026-04-05T10:00:00Z",
            unique_body="Erste Nachricht", body="Erste Nachricht", has_attachments=True,
            to=[("Bob", "bob@vw.de")],
        ),
    ]

    call_count = [0]

    def fake_get(url, headers=None, params=None, timeout=None):
        call_count[0] += 1
        if call_count[0] == 1:
            return FakeResponse(200, {"conversationId": "conv-md-flags", "subject": "Thema"})
        if call_count[0] == 2:
            return FakeResponse(200, {"value": msgs})
        if "/attachments" in url:
            return FakeResponse(200, _make_att_payload())
        return FakeResponse(200, {"value": []})

    monkeypatch.setattr(mod.requests, "get", fake_get)

    seen_flags = []

    import file_converter

    def fake_to_markdown(input_path, output_path, *, no_llm_pdf=False, no_llm=False, all_sheets=False, debug=False):
        seen_flags.append((input_path.name, no_llm_pdf, no_llm))
        output_path.write_text(f"# {input_path.name}\n\nKonvertiert.", encoding="utf-8")
        return 0

    monkeypatch.setattr(file_converter, "_to_markdown", fake_to_markdown)

    mod.cmd_read_thread("m1", convert_to_markdown=True, no_llm_pdf=True, no_llm=True)

    out = capsys.readouterr().out
    assert "Markdown-Konvertierung OK: bericht.docx -> bericht.md" in out
    assert "Markdown-Konvertierung OK: foto.png -> foto.md" in out
    assert "Anhaenge gespeichert in:" in out
    assert len(seen_flags) == 2
    assert all(no_llm_pdf is True and no_llm is True for _, no_llm_pdf, no_llm in seen_flags)

    thread_dirs = list((tmp_path / "tmp" / "threads").iterdir())
    assert len(thread_dirs) == 1
    att_dir = thread_dirs[0] / "attachments"
    assert (att_dir / "bericht.docx").is_file()
    assert (att_dir / "bericht.md").is_file()
    assert (att_dir / "foto.png").is_file()
    assert (att_dir / "foto.md").is_file()


def test_cmd_read_thread_no_inline_llm_opt_out(tmp_path, monkeypatch, capsys):
    """--no-inline-llm deaktiviert die Inline-Bildbeschreibung auch im Thread."""
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_resolve_token", lambda _token=None: "tok")

    html_body = '<p>Hallo, hier der Screenshot:</p><img src="cid:img001" /><p>Ende.</p>'
    msgs = [{
        "id": "m1",
        "subject": "Thread mit Screenshot",
        "from": {"emailAddress": {"name": "Alice", "address": "alice@vw.de"}},
        "toRecipients": [],
        "ccRecipients": [],
        "receivedDateTime": "2026-04-05T10:00:00Z",
        "uniqueBody": {"content": html_body, "contentType": "html"},
        "body": {"content": html_body, "contentType": "html"},
        "hasAttachments": True,
        "importance": "normal",
    }]

    call_count = [0]

    def fake_get(url, headers=None, params=None, timeout=None):
        call_count[0] += 1
        if call_count[0] == 1:
            return FakeResponse(200, {"conversationId": "conv-inline-thread", "subject": "Thread mit Screenshot"})
        if call_count[0] == 2:
            return FakeResponse(200, {"value": msgs})
        if "/attachments" in url:
            return FakeResponse(200, _make_inline_att_payload())
        return FakeResponse(200, {"value": []})

    monkeypatch.setattr(mod.requests, "get", fake_get)

    import file_converter

    calls = []

    def fake_to_markdown(input_path, output_path, *, no_llm_pdf=False, no_llm=False, all_sheets=False, debug=False):
        calls.append(input_path.name)
        return 0

    monkeypatch.setattr(file_converter, "_to_markdown", fake_to_markdown)

    mod.cmd_read_thread("m1", no_inline_llm=True)

    out = capsys.readouterr().out
    assert calls == []
    assert "![Bild](" in out
    assert "LLM-beschrieben" not in out

    thread_files = list((tmp_path / "tmp" / "threads").glob("*/email_thread.md"))
    assert len(thread_files) == 1
    content = thread_files[0].read_text(encoding="utf-8")
    assert "Inline-Bilder:" in content
    assert "LLM-beschrieben" not in content


def test_cmd_read_thread_inline_image_llm_failure_marks_conversion_error(tmp_path, monkeypatch, capsys):
    """Inline-Bildfehler im Thread werden sichtbar als Konvertierungsfehler ausgewiesen."""
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_resolve_token", lambda _token=None: "tok")

    html_body = '<p>Hallo, hier der Screenshot:</p><img src="cid:img001" /><p>Ende.</p>'
    msgs = [{
        "id": "m1",
        "subject": "Thread mit Screenshot",
        "from": {"emailAddress": {"name": "Alice", "address": "alice@vw.de"}},
        "toRecipients": [],
        "ccRecipients": [],
        "receivedDateTime": "2026-04-05T10:00:00Z",
        "uniqueBody": {"content": html_body, "contentType": "html"},
        "body": {"content": html_body, "contentType": "html"},
        "hasAttachments": True,
        "importance": "normal",
    }]

    call_count = [0]

    def fake_get(url, headers=None, params=None, timeout=None):
        call_count[0] += 1
        if call_count[0] == 1:
            return FakeResponse(200, {"conversationId": "conv-inline-fail", "subject": "Thread mit Screenshot"})
        if call_count[0] == 2:
            return FakeResponse(200, {"value": msgs})
        if "/attachments" in url:
            return FakeResponse(200, _make_inline_att_payload())
        return FakeResponse(200, {"value": []})

    monkeypatch.setattr(mod.requests, "get", fake_get)

    import file_converter

    def fake_to_markdown_crash(input_path, output_path, *, no_llm_pdf=False, no_llm=False, all_sheets=False, debug=False):
        raise RuntimeError("LLM nicht erreichbar")

    monkeypatch.setattr(file_converter, "_to_markdown", fake_to_markdown_crash)

    mod.cmd_read_thread("m1")

    out = capsys.readouterr()
    assert "LLM-Beschreibung" in out.err
    assert "Inline-Bilder (LLM-beschrieben):" not in out.out
    assert "Inline-Bilder (Konvertierungsfehler):" in out.out
    assert "- screenshot.png (Konvertierungsfehler)" in out.out

    thread_files = list((tmp_path / "tmp" / "threads").glob("*/email_thread.md"))
    assert len(thread_files) == 1
    content = thread_files[0].read_text(encoding="utf-8")
    assert "Inline-Bilder (LLM-beschrieben):" not in content
    assert "Inline-Bilder (Konvertierungsfehler):" in content
    assert "- screenshot.png (Konvertierungsfehler)" in content
