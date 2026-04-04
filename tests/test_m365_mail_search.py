from pathlib import Path
import sys

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
        if url.endswith("/msg-1") and params == {"$select": "body,ccRecipients"}:
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
        if url.endswith("/msg-2") and params == {"$select": "body,ccRecipients"}:
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
