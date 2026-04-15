import json
from pathlib import Path
import sys

import pytest

WORKSPACE = Path(__file__).resolve().parents[1]

sys.path.insert(
    0,
    str(
        WORKSPACE
        / ".agents"
        / "skills"
        / "skill-m365-mail-agent"
        / "scripts"
    ),
)

import analyze_case as mod  # noqa: E402


def test_mail_agent_default_prompt_requires_orga_skill_for_ekek1_context():
    prompt = (
        WORKSPACE
        / ".agents"
        / "skills"
        / "skill-m365-mail-agent"
        / "agents"
        / "openai.yaml"
    ).read_text(encoding="utf-8")
    assert "$skill-orga-ekek1" in prompt
    assert "erste Referenzquelle" in prompt


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text
        self.headers = {"content-type": "application/json"}

    def json(self) -> dict:
        return self._payload


@pytest.fixture
def fake_case_environment(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "CASE_BASE_DIR", tmp_path / "userdata" / "outlook")
    monkeypatch.setattr(mod.ms, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod.ms, "_resolve_token", lambda _token=None, debug=False: "token")

    def fake_collect_rendered_event_hits(query, token, desired_results):
        if query == "budget-calendar-fails":
            raise SystemExit(2)
        return (
            1,
            [
                {
                    "subject": "Abstimmung Budget",
                    "hit": {"hitId": "event-1"},
                    "search_ctx": {
                        "event_id": "event-1",
                        "start_date": "2026-04-09T10:00:00Z",
                        "from": "Alice Example",
                        "reply_to": "Bob; Carol",
                        "body_preview": "Abstimmung zum Sachstand",
                        "web_link": "https://outlook.office.com/calendar/item/event-1",
                        "is_series": False,
                    },
                }
            ],
        )

    monkeypatch.setattr(mod.ms, "_collect_rendered_event_hits", fake_collect_rendered_event_hits)

    def fake_process_message_output(
        msg,
        *,
        message_id,
        token,
        att_dir,
        body_raw,
        body_type,
        attachments,
        save_attachments=False,
        convert=False,
        convert_to_markdown=False,
        no_llm_pdf=False,
        no_llm=False,
        no_inline_llm=False,
        debug=False,
    ):
        return {
            "header_lines": [f"Von: {msg['from']['emailAddress']['name']}", f"Betreff: {msg['subject']}"],
            "att_lines": ["Anhaenge: -"],
            "inline_lines": [],
            "sp_link_lines": [],
            "body_text": mod._format_message_preview(msg, prefer_unique_body=True),
            "saved_att_names": [],
            "md_converted_names": [],
            "converted": [],
        }

    monkeypatch.setattr(mod.ms, "_process_message_output", fake_process_message_output)

    def fake_get(url, headers=None, params=None, timeout=None):
        if "/me/messages/msg-seed" in url:
            return FakeResponse(
                200,
                {
                    "id": "msg-seed",
                    "subject": "AW: Budget Abstimmung MQB Classic",
                    "from": {"emailAddress": {"name": "Alice Example", "address": "alice@example.com"}},
                    "toRecipients": [{"emailAddress": {"name": "Tobias Mueller", "address": "tobias@example.com"}}],
                    "ccRecipients": [{"emailAddress": {"name": "Bob Example", "address": "bob@example.com"}}],
                    "receivedDateTime": "2026-04-07T11:38:00Z",
                    "body": {"contentType": "text", "content": "Bitte pruefen wir die Umbuchung bis 09.04.2026."},
                    "uniqueBody": {"contentType": "text", "content": "Bitte pruefen wir die Umbuchung bis 09.04.2026."},
                    "hasAttachments": False,
                    "importance": "normal",
                    "conversationId": "conv-1",
                    "webLink": "https://outlook.office.com/mail/read/msg-seed",
                    "parentFolderId": "folder-inbox",
                },
            )
        if "/me/messages/msg-alt" in url:
            return FakeResponse(
                200,
                {
                    "id": "msg-alt",
                    "subject": "AW: Budget Abstimmung MQB Classic Alternative",
                    "from": {"emailAddress": {"name": "Alice Example", "address": "alice@example.com"}},
                    "toRecipients": [{"emailAddress": {"name": "Tobias Mueller", "address": "tobias@example.com"}}],
                    "ccRecipients": [],
                    "receivedDateTime": "2026-04-08T09:15:00Z",
                    "body": {"contentType": "text", "content": "Bitte rueckmelden, welche Mail gemeint war."},
                    "uniqueBody": {"contentType": "text", "content": "Bitte rueckmelden, welche Mail gemeint war."},
                    "hasAttachments": False,
                    "importance": "normal",
                    "conversationId": "conv-1",
                    "webLink": "https://outlook.office.com/mail/read/msg-alt",
                    "parentFolderId": "folder-inbox",
                },
            )
        if "/me/messages/msg-related-1" in url:
            return FakeResponse(
                200,
                {
                    "id": "msg-related-1",
                    "subject": "Budget Abstimmung MQB Folgepunkt",
                    "from": {"emailAddress": {"name": "Alice Example", "address": "alice@example.com"}},
                    "toRecipients": [{"emailAddress": {"name": "Tobias Mueller", "address": "tobias@example.com"}}],
                    "ccRecipients": [],
                    "receivedDateTime": "2026-04-01T08:00:00Z",
                    "body": {"contentType": "text", "content": "Bitte veranlassen wir auch die Rueckmeldung an Skoda."},
                    "uniqueBody": {"contentType": "text", "content": "Bitte veranlassen wir auch die Rueckmeldung an Skoda."},
                    "hasAttachments": False,
                    "importance": "normal",
                    "conversationId": "conv-2",
                    "webLink": "https://outlook.office.com/mail/read/msg-related-1",
                    "parentFolderId": "folder-archive",
                },
            )
        if url.endswith("/me/messages"):
            return FakeResponse(
                200,
                {
                    "value": [
                        {
                            "id": "msg-old",
                            "subject": "Budget Abstimmung MQB Classic",
                            "from": {"emailAddress": {"name": "Alice Example", "address": "alice@example.com"}},
                            "toRecipients": [{"emailAddress": {"name": "Tobias Mueller", "address": "tobias@example.com"}}],
                            "ccRecipients": [],
                            "receivedDateTime": "2026-04-05T09:00:00Z",
                            "body": {"contentType": "text", "content": "Wir muessen die Umbuchung vorbereiten."},
                            "uniqueBody": {"contentType": "text", "content": "Wir muessen die Umbuchung vorbereiten."},
                            "hasAttachments": False,
                            "importance": "normal",
                            "conversationId": "conv-1",
                            "webLink": "https://outlook.office.com/mail/read/msg-old",
                            "parentFolderId": "folder-inbox",
                        },
                        {
                            "id": "msg-seed",
                            "subject": "AW: Budget Abstimmung MQB Classic",
                            "from": {"emailAddress": {"name": "Alice Example", "address": "alice@example.com"}},
                            "toRecipients": [{"emailAddress": {"name": "Tobias Mueller", "address": "tobias@example.com"}}],
                            "ccRecipients": [{"emailAddress": {"name": "Bob Example", "address": "bob@example.com"}}],
                            "receivedDateTime": "2026-04-07T11:38:00Z",
                            "body": {"contentType": "text", "content": "Bitte pruefen wir die Umbuchung bis 09.04.2026."},
                            "uniqueBody": {"contentType": "text", "content": "Bitte pruefen wir die Umbuchung bis 09.04.2026."},
                            "hasAttachments": False,
                            "importance": "normal",
                            "conversationId": "conv-1",
                            "webLink": "https://outlook.office.com/mail/read/msg-seed",
                            "parentFolderId": "folder-inbox",
                        },
                    ]
                },
            )
        if "/mailFolders/folder-inbox" in url:
            return FakeResponse(200, {"displayName": "Inbox"})
        if "/mailFolders/folder-archive" in url:
            return FakeResponse(200, {"displayName": "Archive"})
        raise AssertionError(f"Unexpected GET {url} params={params}")

    def fake_post(url, headers=None, json=None, timeout=None):
        query = json["requests"][0]["query"]["queryString"]
        assert json["requests"][0]["entityTypes"] == ["message"]
        if query == "Seed query":
            hits = [
                {"hitId": "msg-seed", "resource": {"subject": "AW: Budget Abstimmung MQB Classic"}},
                {"hitId": "msg-alt", "resource": {"subject": "AW: Budget Abstimmung MQB Classic Alternative"}},
            ]
        else:
            hits = [
                {
                    "hitId": "msg-related-1",
                    "resource": {
                        "subject": "Budget Abstimmung MQB Folgepunkt",
                        "receivedDateTime": "2026-04-01T08:00:00Z",
                        "from": {"emailAddress": {"name": "Alice Example"}},
                        "replyTo": [],
                        "hasAttachments": False,
                        "importance": "normal",
                        "webLink": "https://outlook.office.com/mail/read/msg-related-1",
                    },
                    "summary": "Bitte veranlassen wir auch die Rueckmeldung an Skoda.",
                }
            ]
        return FakeResponse(200, {"value": [{"hitsContainers": [{"total": len(hits), "hits": hits}]}]})

    monkeypatch.setattr(mod.requests, "get", fake_get)
    monkeypatch.setattr(mod.requests, "post", fake_post)
    monkeypatch.setattr(mod.ms.requests, "get", fake_get)
    monkeypatch.setattr(mod.ms.requests, "post", fake_post)
    return tmp_path


def test_analyze_case_prepares_case_without_analysis(fake_case_environment):
    case_dir = mod.analyze_case(
        "msg-seed",
        debug=True,
        related_queries=["skoda rueckmeldung"],
        calendar_queries=["budget kalender"],
        retrieval_trace=[{"phase": "related_mail", "query": "skoda rueckmeldung", "evaluation": "weiter relevant"}],
    )
    assert case_dir.is_dir()
    data = (case_dir / "case.json").read_text(encoding="utf-8")
    assert '"analysis_status": "prepared"' in data
    assert '"seed_resolution"' in data
    assert '"selection_mode": "message_id"' in data
    assert '"retrieval_trace"' in data
    assert (case_dir / "logs" / "agent_trace.json").is_file()


def test_analyze_case_finalizes_with_agent_payload(fake_case_environment):
    analysis_payload = {
        "tlmdr": "Budget Abstimmung MQB Classic - Rueckmeldung vorbereiten",
        "analysis_md": "Finale Bewertung: Die Anfrage ist plausibel, muss aber gegen fachliche Systemverantwortung und vorhandene Dokumentation gegengeprueft werden.",
        "core_topic": "Budget Abstimmung MQB Classic",
        "history": "Thread und eine verwandte Mail wurden agentisch bewertet.",
        "key_points": ["Seed-Mail und Thread gelesen", "Verwandte Mail bestaetigt Rueckmeldung an Skoda"],
        "deadlines": ["09.04.2026"],
        "relevant_aspects": ["Skoda-Rueckmeldung ist explizit benoetigt"],
        "open_points": ["Freigabe fuer die finale Rueckmeldung fehlt"],
        "decision": {
            "criteria": [
                {"name": "Risiko", "is_dynamic": False},
                {"name": "Aufwand Anwender", "is_dynamic": False},
                {"name": "Aufwand Softwareänderungen", "is_dynamic": False},
            ],
            "options": [
                {
                    "title": "Option A",
                    "description": "Rueckmeldung mit Vorbehalt senden",
                    "ratings": {
                        "Risiko": {"score": 4, "rationale": "Gering, wenn Freigabe genannt wird."},
                        "Aufwand Anwender": {"score": 2, "rationale": "Nur geringe Zusatzarbeit fuer den Anwender."},
                        "Aufwand Softwareänderungen": {"score": 5, "rationale": "Keine Softwareaenderung erforderlich."},
                    },
                }
            ],
            "recommendation": {"option_title": "Option A", "rationale": "Schnellste belastbare Rueckmeldung."},
        },
        "actions": [
            {
                "action_type": "reply",
                "title": "Antwort an Alice",
                "body": "Hallo Alice,\n\nich bereite die Rueckmeldung an Skoda vor.\n",
            },
            {
                "action_type": "todo",
                "title": "Freigabe einholen",
                "body": "Todo-Vorschlag 1\n\nAufgabe: Freigabe fuer Rueckmeldung einholen\n",
            },
            {
                "action_type": "calendar",
                "title": "Kurzabstimmung Budget",
                "body": "Kalender-Draft 1\n\nTitel: Kurzabstimmung Budget\n",
            },
        ],
        "agent_decisions": ["Related Mail msg-related-1 als belastbaren Kontext eingestuft."],
    }
    case_dir = mod.analyze_case(
        "msg-seed",
        debug=True,
        related_queries=["skoda rueckmeldung"],
        calendar_queries=["budget kalender"],
        retrieval_trace=[{"phase": "calendar", "query": "budget kalender", "evaluation": "Event als relevant markiert"}],
        analysis_payload=analysis_payload,
    )
    assert (case_dir / "00_analyse.md").is_file()
    assert (case_dir / "10_email_1.md").is_file()
    assert (case_dir / "20_todo_1.md").is_file()
    assert (case_dir / "30_calendar_1.md").is_file()
    case_json = (case_dir / "case.json").read_text(encoding="utf-8")
    assert '"analysis_status": "completed"' in case_json
    assert '"agent_decisions"' in case_json
    assert '"summary"' not in case_json
    assert '"core_topic": "Budget Abstimmung MQB Classic"' in case_json
    analysis = (case_dir / "00_analyse.md").read_text(encoding="utf-8")
    assert "TL;DR: Budget Abstimmung MQB Classic - Rueckmeldung vorbereiten" in analysis
    assert "Finale Bewertung: Die Anfrage ist plausibel" in analysis
    assert "# Retrieval-Verlauf" not in analysis
    assert "# Agent-Entscheidungen" not in analysis
    assert "# Zusammenfassung und Entscheidung" not in analysis
    assert "Aufwand Anwender" in analysis
    assert "Aufwand Softwareänderungen" in analysis
    reply = (case_dir / "10_email_1.md").read_text(encoding="utf-8")
    assert "ich bereite die Rueckmeldung an Skoda vor" in reply


def test_analysis_omits_open_points_section_when_none_exist(fake_case_environment):
    analysis_payload = {
        "tlmdr": "Keine offenen Punkte im Fall",
        "analysis_md": "Finale Bewertung: Der Fall ist fachlich ausreichend geklaert.",
        "core_topic": "Budget Abstimmung MQB Classic",
        "key_points": ["Sachverhalt ist geklaert"],
        "deadlines": [],
        "relevant_aspects": ["Keine weitere Eskalation erforderlich"],
        "open_points": [],
        "decision": {"criteria": [], "options": [], "recommendation": {"option_title": "-", "rationale": "-"}} ,
        "actions": [],
    }
    case_dir = mod.analyze_case("msg-seed", debug=True, analysis_payload=analysis_payload)
    analysis = (case_dir / "00_analyse.md").read_text(encoding="utf-8")
    assert "# Offene Punkte" not in analysis
    assert "Keine offenen Punkte benannt" not in analysis


def test_query_resolution_warns_on_ambiguous_seed(fake_case_environment):
    case_dir = mod.analyze_case(query="Seed query", selection_index=1, debug=True)
    data = (case_dir / "case.json").read_text(encoding="utf-8")
    assert '"selection_mode": "query"' in data
    assert '"user_prompt": "Seed query"' in data
    assert '"warnings"' in data
    assert "plausible Seed-Mails" in data


def test_search_related_mails_uses_agent_queries(fake_case_environment):
    prepared_case = mod.prepare_case("msg-seed", debug=True)
    related, runs, warnings = mod.search_related_mails(prepared_case, ["skoda rueckmeldung"])
    assert not warnings
    assert runs[0]["query"] == "skoda rueckmeldung"
    assert related[0].source_query == "skoda rueckmeldung"
    assert related[0].message_id == "msg-related-1"


def test_search_calendar_context_tolerates_exit(fake_case_environment):
    prepared_case = mod.prepare_case("msg-seed", debug=True)
    events, runs, warnings = mod.search_calendar_context(prepared_case, ["budget-calendar-fails"])
    assert events == []
    assert runs == []
    assert warnings


def test_resume_case_reuses_saved_artifacts_without_refresh(fake_case_environment, monkeypatch):
    case_dir = mod.analyze_case("msg-seed", debug=True)
    original_thread = (case_dir / "logs" / "thread_context.md").read_text(encoding="utf-8")

    def fail_fetch(*args, **kwargs):
        raise AssertionError("resume_case ohne refresh darf keine Seed-Mail neu laden")

    monkeypatch.setattr(mod, "_fetch_message", fail_fetch)
    resumed = mod.resume_case(case_dir.name, debug=True)
    assert resumed.case_id == case_dir.name
    assert resumed.seed_message_id == "msg-seed"
    assert (case_dir / "logs" / "thread_context.md").read_text(encoding="utf-8") == original_thread


def test_resume_case_refresh_refetches_seed(fake_case_environment, monkeypatch):
    case_dir = mod.analyze_case("msg-seed", debug=True)
    calls: list[str] = []
    original_prepare_case = mod.prepare_case

    def wrapped_prepare_case(message_id=None, *, query=None, selection_index=0, debug=True):
        calls.append(str(message_id))
        return original_prepare_case(message_id, query=query, selection_index=selection_index, debug=debug)

    monkeypatch.setattr(mod, "prepare_case", wrapped_prepare_case)
    resumed = mod.resume_case(case_dir.name, refresh=True, debug=True)
    assert resumed.case_id == case_dir.name
    assert calls == ["msg-seed"]


def test_analyze_case_resume_records_followup_turn_and_active_pointer(fake_case_environment):
    analysis_payload = {
        "tlmdr": "Budget Abstimmung MQB Classic - Rueckmeldung vorbereiten",
        "analysis_md": "Finale Bewertung: Belastbarkeit ist fuer die aktuelle Rueckmeldung noch nicht vollstaendig abgesichert.",
        "core_topic": "Budget Abstimmung MQB Classic",
        "key_points": ["Seed-Mail und Thread gelesen"],
        "deadlines": [],
        "relevant_aspects": ["Freigabebedarf weiterhin offen"],
        "open_points": ["Freigabe fuer die finale Rueckmeldung fehlt"],
        "decision": {"criteria": [], "options": [], "recommendation": {"option_title": "-", "rationale": "-"}} ,
        "actions": [],
    }
    case_dir = mod.analyze_case("msg-seed", debug=True, analysis_payload=analysis_payload)
    followup_payload = {
        "tlmdr": "Folgefrage eingeordnet",
        "analysis_md": "Folgeanalyse: Die bisherige Rueckmeldung muss kritisch gegen die vorhandene Evidenz abgeglichen werden.",
        "core_topic": "Budget Abstimmung MQB Classic",
        "key_points": ["Bestehender Case wiederverwendet"],
        "deadlines": [],
        "relevant_aspects": ["Keine neue Seed-Auswahl notwendig"],
        "open_points": ["Freigabe weiterhin offen"],
        "decision": {"criteria": [], "options": [], "recommendation": {"option_title": "-", "rationale": "-"}} ,
        "actions": [],
    }

    mod.analyze_case(
        case_id=case_dir.name,
        debug=True,
        analysis_payload=followup_payload,
        user_question="Wie belastbar ist die bisherige Aussage?",
    )

    case_json = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
    assert case_json["resume_source"] == "explicit_case_id"
    assert case_json["last_user_question"] == "Wie belastbar ist die bisherige Aussage?"
    assert len(case_json["followup_turns"]) == 1
    assert case_json["followup_turns"][0]["resume_source"] == "explicit_case_id"
    assert case_json["followup_turns"][0]["user_question"] == "Wie belastbar ist die bisherige Aussage?"

    active_case = json.loads((mod.CASE_BASE_DIR / "_session" / "active_case.json").read_text(encoding="utf-8"))
    assert active_case["case_id"] == case_dir.name
    assert active_case["session_status"] == "completed"


def test_followup_analysis_preserves_markdown_strikethrough_in_open_points(fake_case_environment):
    initial_payload = {
        "tlmdr": "Erste Analyse",
        "analysis_md": "Initiale Bewertung mit offenem Freigabepunkt.",
        "core_topic": "Budget Abstimmung MQB Classic",
        "key_points": ["Freigabe ist noch offen"],
        "deadlines": [],
        "relevant_aspects": [],
        "open_points": ["Freigabe durch Fachbereich fehlt"],
        "decision": {"criteria": [], "options": [], "recommendation": {"option_title": "-", "rationale": "-"}} ,
        "actions": [],
    }
    case_dir = mod.analyze_case("msg-seed", debug=True, analysis_payload=initial_payload)
    followup_payload = {
        "tlmdr": "Folgefrage eingeordnet",
        "analysis_md": "Folgeanalyse: Ein Punkt ist geklaert, ein anderer bleibt offen.",
        "core_topic": "Budget Abstimmung MQB Classic",
        "key_points": ["Ein offener Punkt wurde geklaert"],
        "deadlines": [],
        "relevant_aspects": [],
        "open_points": ["~~Freigabe durch Fachbereich fehlt~~", "Analyse: Belastbare Aussage zur Skoda-Rueckmeldung fehlt noch"],
        "decision": {"criteria": [], "options": [], "recommendation": {"option_title": "-", "rationale": "-"}} ,
        "actions": [],
    }
    mod.analyze_case(case_id=case_dir.name, debug=True, analysis_payload=followup_payload)
    analysis = (case_dir / "00_analyse.md").read_text(encoding="utf-8")
    assert "# Offene Punkte" in analysis
    assert "~~Freigabe durch Fachbereich fehlt~~" in analysis
    assert "Analyse: Belastbare Aussage zur Skoda-Rueckmeldung fehlt noch" in analysis


def test_analyze_case_resume_via_case_dir_sets_resume_source(fake_case_environment):
    case_dir = mod.analyze_case("msg-seed", debug=True)
    mod.analyze_case(case_dir=case_dir, debug=True, user_question="Bitte Fall fortsetzen")
    case_json = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
    assert case_json["resume_source"] == "explicit_case_dir"
    assert case_json["last_user_question"] == "Bitte Fall fortsetzen"
    assert case_json["followup_turns"][0]["resume_source"] == "explicit_case_dir"


def test_analyze_case_resume_via_case_json_sets_resume_source(fake_case_environment):
    case_dir = mod.analyze_case("msg-seed", debug=True)
    mod.analyze_case(case_json_path=case_dir / "case.json", debug=True, user_question="Bitte ueber case.json fortsetzen")
    case_json = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
    assert case_json["resume_source"] == "explicit_case_json"
    assert case_json["last_user_question"] == "Bitte ueber case.json fortsetzen"
    assert case_json["followup_turns"][0]["resume_source"] == "explicit_case_json"
