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
    def fake_to_markdown(input_path, output_path, *, no_llm_pdf=False, no_llm=False, all_sheets=False):
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

    def fake_to_markdown_partial(input_path, output_path, *, no_llm_pdf=False, no_llm=False, all_sheets=False):
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

    def fake_to_markdown(input_path, output_path, *, no_llm_pdf=False, no_llm=False, all_sheets=False):
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

    def fake_to_markdown(input_path, output_path, *, no_llm_pdf=False, no_llm=False, all_sheets=False):
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
