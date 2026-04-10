from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[4]
MAIL_SEARCH_SCRIPTS = REPO_ROOT / ".agents" / "skills" / "skill-m365-copilot-mail-search" / "scripts"

if str(MAIL_SEARCH_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(MAIL_SEARCH_SCRIPTS))

import m365_mail_search as ms  # noqa: E402

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

CASE_BASE_DIR = REPO_ROOT / "userdata" / "outlook"
SESSION_STATE_DIRNAME = "_session"
DEFAULT_RELATED_LIMIT = 6
DEFAULT_EVENT_LIMIT = 5
DEFAULT_SEED_QUERY_RESULTS = 5
THREAD_PAGE_SIZE = 50
MESSAGE_SELECT = (
    "id,subject,from,toRecipients,ccRecipients,receivedDateTime,body,uniqueBody,"
    "hasAttachments,importance,conversationId,webLink,parentFolderId"
)


class CaseError(RuntimeError):
    pass


@dataclass
class MailCandidate:
    message_id: str
    subject: str
    sender: str
    received: str
    preview: str
    folder: str
    web_link: str
    conversation_id: str
    source_query: str | None = None


@dataclass
class SearchResolution:
    message_id: str
    selection_mode: str
    query: str | None = None
    warning: str | None = None
    candidates: list[dict[str, Any]] | None = None


@dataclass
class PreparedCase:
    case_id: str
    case_dir: Path
    token: str
    seed_message_id: str
    seed_message: dict[str, Any]
    thread_messages: list[dict[str, Any]]
    attachment_names: list[str]
    attachment_md_names: list[str]
    seed_resolution: SearchResolution
    warnings: list[str]
    user_prompt: str | None = None


def _log(message: str) -> None:
    print(message)


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_markdown(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


PDF_CSS = """
body { font-size: 9pt; font-family: Segoe UI, Arial, sans-serif; }
table { font-size: 8pt; width: auto; table-layout: auto; border-collapse: collapse; margin: 0 0 6pt 0; }
th, td { padding: 3px 5px; border: 1px solid #ccc; vertical-align: top; word-wrap: break-word; overflow-wrap: break-word; max-width: 220px; }
th { background-color: #f0f0f0; font-weight: bold; }
@page { size: A4; margin: 1.5cm 1.2cm; }
hr { display: none; border: none; height: 0; margin: 0; padding: 0; }
blockquote { font-size: 8pt; border-left: 3px solid #ccc; padding-left: 8px; margin-left: 0; color: #333; }
code { font-size: 7.5pt; }
pre { font-size: 7.5pt; }
"""


def _render_pdf(md_path: Path, pdf_path: Path) -> None:
    """Best-effort PDF from Markdown. Warns on stderr if markdown-pdf is missing."""
    try:
        from markdown_pdf import MarkdownPdf, Section  # type: ignore[import-untyped]
    except ImportError:
        print("WARN: markdown-pdf nicht installiert, PDF-Export uebersprungen.", file=sys.stderr)
        return
    try:
        md_text = md_path.read_text(encoding="utf-8")
        pdf = MarkdownPdf(toc_level=2)
        pdf.add_section(Section(md_text, toc=True), user_css=PDF_CSS)
        pdf.save(str(pdf_path))
        _log(f"PDF erzeugt: {pdf_path}")
    except Exception as exc:  # noqa: BLE001
        print(f"WARN: PDF-Export fehlgeschlagen: {exc}", file=sys.stderr)


def _session_state_dir() -> Path:
    return CASE_BASE_DIR / SESSION_STATE_DIRNAME


def _active_case_path() -> Path:
    return _session_state_dir() / "active_case.json"


def _read_json_file(path: Path, *, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CaseError(f"{label} nicht gefunden: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CaseError(f"{label} ist kein gueltiges JSON: {path}") from exc


def _optional_json_file(path: Path) -> Any | None:
    if not path.exists():
        return None
    return _read_json_file(path, label=path.name)


def _resolve_case_id_input(
    *,
    case_id: str | None = None,
    case_dir: str | Path | None = None,
    case_json_path: str | Path | None = None,
) -> str | None:
    inputs = [item for item in (case_id, case_dir, case_json_path) if item]
    if len(inputs) > 1:
        raise CaseError("Nur einer von case_id, case_dir oder case_json_path darf gesetzt sein.")
    if case_id:
        return case_id
    if case_dir:
        path = Path(case_dir).expanduser()
        if not path.is_dir():
            raise CaseError(f"Case-Verzeichnis nicht gefunden: {path}")
        if not (path / "case.json").is_file():
            raise CaseError(f"case.json fehlt im Case-Verzeichnis: {path}")
        return path.name
    if case_json_path:
        path = Path(case_json_path).expanduser()
        if not path.is_file():
            raise CaseError(f"case.json nicht gefunden: {path}")
        payload = _read_json_file(path, label="case.json")
        if not isinstance(payload, dict):
            raise CaseError(f"case.json hat einen ungueltigen Aufbau: {path}")
        resolved_case_id = str(payload.get("case_id") or path.parent.name or "").strip()
        if not resolved_case_id:
            raise CaseError(f"case_id konnte aus case.json nicht bestimmt werden: {path}")
        return resolved_case_id
    return None


def _normalize_subject(subject: str) -> str:
    prefixes = ("aw:", "wg:", "re:", "fw:", "fwd:")
    cleaned = subject or ""
    changed = True
    while changed:
        changed = False
        lower = cleaned.lower().lstrip()
        for prefix in prefixes:
            if lower.startswith(prefix):
                cleaned = cleaned.lstrip()[len(prefix):].lstrip()
                changed = True
                break
    return cleaned.strip()


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = item.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(item.strip())
    return result


def _graph_get(url: str, token: str, *, params: dict[str, str] | None = None, timeout: int = 20) -> dict[str, Any]:
    try:
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise CaseError(f"Graph GET fehlgeschlagen: {exc}") from exc
    if response.status_code == 401:
        raise CaseError("TOKEN_EXPIRED")
    if response.status_code != 200:
        data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        message = data.get("error", {}).get("message", response.text[:200])
        raise CaseError(f"Graph GET {response.status_code}: {message}")
    return response.json()


def _fetch_message(message_id: str, token: str) -> dict[str, Any]:
    encoded_message_id = ms._encode_graph_id_for_path(message_id)
    return _graph_get(
        f"https://graph.microsoft.com/v1.0/me/messages/{encoded_message_id}",
        token,
        params={"$select": MESSAGE_SELECT},
    )


def _fetch_thread_messages(conversation_id: str, token: str) -> list[dict[str, Any]]:
    if not conversation_id:
        return []
    url = "https://graph.microsoft.com/v1.0/me/messages"
    params: dict[str, str] | None = {
        "$filter": f"conversationId eq '{conversation_id}'",
        "$select": MESSAGE_SELECT,
        "$top": str(THREAD_PAGE_SIZE),
    }
    items: list[dict[str, Any]] = []
    while url:
        data = _graph_get(url, token, params=params)
        items.extend(data.get("value", []) or [])
        url = data.get("@odata.nextLink") or ""
        params = None
    items.sort(key=lambda item: item.get("receivedDateTime", ""))
    return items


def _format_message_preview(message: dict[str, Any], *, prefer_unique_body: bool = True, max_lines: int = 6) -> str:
    body_raw, body_type = ms._resolve_message_body(message, prefer_unique_body=prefer_unique_body)
    body_text = ms._html_to_text(body_raw) if body_type == "html" else body_raw
    lines = ms._get_first_nonempty_lines(body_text, max_lines)
    return "\n".join(lines) if lines else "(Kein Body-Inhalt verfuegbar)"


def _candidate_from_message(
    message: dict[str, Any],
    *,
    token: str,
    folder_cache: dict[str, str],
    source_query: str | None = None,
) -> MailCandidate:
    metadata = ms._extract_message_metadata(message)
    folder_name = ms._resolve_folder_name(message.get("parentFolderId", ""), token, folder_cache)
    return MailCandidate(
        message_id=message.get("id", ""),
        subject=message.get("subject", "-"),
        sender=metadata["from_str"],
        received=(message.get("receivedDateTime", "") or "").replace("T", " ")[:19],
        preview=_format_message_preview(message),
        folder=folder_name,
        web_link=message.get("webLink", ""),
        conversation_id=message.get("conversationId", ""),
        source_query=source_query,
    )


def _search_message_candidates(
    query: str,
    token: str,
    *,
    size: int = DEFAULT_SEED_QUERY_RESULTS,
) -> list[MailCandidate]:
    folder_cache: dict[str, str] = {}
    try:
        data = ms._execute_search_request(
            token,
            query,
            "message",
            size,
            top_results=True,
            scope_error_code="NO_MAIL_SCOPE",
        )
    except SystemExit as exc:
        raise CaseError(f"Mail-Suche fuer Query fehlgeschlagen: exit {exc.code}") from exc
    _total, hits = ms._extract_hits_from_search_response(data)
    candidates: list[MailCandidate] = []
    for hit in hits:
        message_id = hit.get("hitId", "")
        if not message_id:
            continue
        full_message = _fetch_message(message_id, token)
        candidates.append(_candidate_from_message(full_message, token=token, folder_cache=folder_cache, source_query=query))
        if len(candidates) >= size:
            break
    return candidates


def _resolve_seed_message(
    *,
    token: str,
    message_id: str | None = None,
    query: str | None = None,
    selection_index: int = 0,
) -> SearchResolution:
    if message_id:
        return SearchResolution(message_id=message_id, selection_mode="message_id", query=query)
    if not query:
        raise CaseError("Es wird entweder eine MESSAGE_ID oder --query benoetigt.")
    candidates = _search_message_candidates(query, token, size=DEFAULT_SEED_QUERY_RESULTS)
    if not candidates:
        raise CaseError(f'Keine Mail zur Query "{query}" gefunden.')
    if selection_index < 0 or selection_index >= len(candidates):
        raise CaseError(f"selection_index {selection_index} liegt ausserhalb von 0..{len(candidates) - 1}.")
    warning = None
    if len(candidates) > 1:
        warning = (
            f'Query "{query}" lieferte {len(candidates)} plausible Seed-Mails; '
            f"Index {selection_index} wurde automatisch gewaehlt."
        )
    return SearchResolution(
        message_id=candidates[selection_index].message_id,
        selection_mode="query",
        query=query,
        warning=warning,
        candidates=[asdict(candidate) for candidate in candidates],
    )


def _relocate_attachment_markdowns(case_dir: Path, md_names: list[str]) -> list[str]:
    att_dir = case_dir / "attachments"
    att_md_dir = _ensure_dir(case_dir / "attachments_md")
    final_names: list[str] = []
    for name in md_names:
        source = att_dir / name
        if not source.exists():
            continue
        target = att_md_dir / name
        if target.exists():
            target.unlink()
        source.replace(target)
        final_names.append(name)
    return final_names


def _render_message_artifacts(
    message: dict[str, Any],
    token: str,
    case_dir: Path,
    *,
    prefer_unique_body: bool,
    debug: bool,
) -> dict[str, Any]:
    body_raw, body_type = ms._resolve_message_body(message, prefer_unique_body=prefer_unique_body)
    attachments = ms._load_message_attachments(
        message["id"],
        body_raw,
        bool(message.get("hasAttachments")),
        token,
        include_content_bytes=True,
    )
    render_data = ms._process_message_output(
        message,
        message_id=message["id"],
        token=token,
        att_dir=_ensure_dir(case_dir / "attachments"),
        body_raw=body_raw,
        body_type=body_type,
        attachments=attachments,
        save_attachments=True,
        convert=False,
        convert_to_markdown=True,
        no_llm_pdf=False,
        no_llm=False,
        no_inline_llm=False,
        debug=debug,
    )
    render_data["md_converted_names"] = _relocate_attachment_markdowns(case_dir, render_data["md_converted_names"])
    return render_data


def _render_thread_markdown(
    case_dir: Path,
    thread_messages: list[dict[str, Any]],
    token: str,
    debug: bool,
) -> tuple[list[str], list[str]]:
    lines = ["# Thread-Kontext", ""]
    attachment_names: list[str] = []
    attachment_md_names: list[str] = []
    for idx, message in enumerate(thread_messages, 1):
        render_data = _render_message_artifacts(message, token, case_dir, prefer_unique_body=True, debug=debug)
        attachment_names.extend(render_data["saved_att_names"])
        attachment_md_names.extend(render_data["md_converted_names"])
        lines.extend(
            ms._build_message_block_lines(
                header_lines=render_data["header_lines"],
                att_lines=render_data["att_lines"],
                inline_lines=render_data["inline_lines"],
                sp_link_lines=render_data["sp_link_lines"],
                body_text=render_data["body_text"],
                section_heading=f"## Thread-Nachricht {idx}",
                trailing_blank=True,
            )
        )
    _write_markdown(case_dir / "logs" / "thread_context.md", lines)
    return _dedupe_keep_order(attachment_names), _dedupe_keep_order(attachment_md_names)


def _write_related_markdown(case_dir: Path, related_mails: list[MailCandidate]) -> None:
    lines = ["# Verwandte Mails", ""]
    if not related_mails:
        lines.append("Keine verwandten Mails gespeichert.")
    else:
        for index, mail in enumerate(related_mails, 1):
            lines.extend(
                [
                    f"## Treffer {index}",
                    f"- receivedDateTime: {mail.received}",
                    f"- folder: {mail.folder or '-'}",
                    f"- from: {mail.sender}",
                    f"- subject: {mail.subject}",
                    f"- source_query: {mail.source_query or '-'}",
                    f"- messageId: `{mail.message_id}`",
                    f"- webLink: {mail.web_link or '-'}",
                    "",
                    mail.preview,
                    "",
                ]
            )
    _write_markdown(case_dir / "logs" / "related_mails.md", lines)


def _write_calendar_markdown(case_dir: Path, events: list[dict[str, Any]]) -> None:
    lines = ["# Kalenderkontext", ""]
    if not events:
        lines.append("Keine relevanten Kalendereintraege gespeichert.")
    else:
        for index, event in enumerate(events, 1):
            lines.extend(
                [
                    f"## Treffer {index}",
                    f"- start: {event['start']}",
                    f"- organizer: {event['organizer']}",
                    f"- participants: {event['participants']}",
                    f"- subject: {event['subject']}",
                    f"- source_query: {event.get('source_query', '-')}",
                    f"- eventId: `{event['event_id']}`",
                    f"- webLink: {event['web_link'] or '-'}",
                    "",
                    event["preview"],
                    "",
                ]
            )
    _write_markdown(case_dir / "logs" / "calendar_context.md", lines)


def _write_context_logs(
    prepared_case: PreparedCase,
    related_mails: list[MailCandidate] | None = None,
    events: list[dict[str, Any]] | None = None,
) -> None:
    _write_json(prepared_case.case_dir / "logs" / "seed_resolution.json", asdict(prepared_case.seed_resolution))
    _write_json(prepared_case.case_dir / "logs" / "seed_message.json", prepared_case.seed_message)
    _write_json(prepared_case.case_dir / "logs" / "thread_messages.json", prepared_case.thread_messages)
    _write_json(prepared_case.case_dir / "logs" / "related_mails.json", [asdict(mail) for mail in related_mails or []])
    _write_json(prepared_case.case_dir / "logs" / "calendar_context.json", events or [])


def _write_related_json(case_dir: Path, related_mails: list[MailCandidate]) -> None:
    _write_json(case_dir / "logs" / "related_mails.json", [asdict(mail) for mail in related_mails])


def _write_calendar_json(case_dir: Path, events: list[dict[str, Any]]) -> None:
    _write_json(case_dir / "logs" / "calendar_context.json", events)


def _write_agent_trace(case_dir: Path, retrieval_trace: list[dict[str, Any]]) -> None:
    _write_json(case_dir / "logs" / "agent_trace.json", retrieval_trace)
    lines = ["# Agent Trace", ""]
    if not retrieval_trace:
        lines.append("Keine agentischen Suchrunden protokolliert.")
        _write_markdown(case_dir / "logs" / "agent_trace.md", lines)
        return
    for index, step in enumerate(retrieval_trace, 1):
        lines.extend(
            [
                f"## Runde {index}",
                f"- phase: {step.get('phase', '-')}",
                f"- goal: {step.get('goal', '-')}",
                f"- target_type: {step.get('target_type', '-')}",
                f"- query: {step.get('query', '-')}",
                f"- evaluation: {step.get('evaluation', '-')}",
                f"- next_step: {step.get('next_step', '-')}",
            ]
        )
        selected = step.get("selected_ids") or []
        if selected:
            lines.append(f"- selected_ids: {', '.join(str(item) for item in selected)}")
        notes = step.get("notes") or []
        if notes:
            lines.append("- notes:")
            lines.extend(f"  - {note}" for note in notes)
        lines.append("")
    _write_markdown(case_dir / "logs" / "agent_trace.md", lines)


def _load_existing_case_json(case_dir: Path) -> dict[str, Any]:
    payload = _read_json_file(case_dir / "case.json", label="case.json")
    if not isinstance(payload, dict):
        raise CaseError(f"case.json hat einen ungueltigen Aufbau: {case_dir / 'case.json'}")
    return payload


def _collect_attachment_names(case_dir: Path, dirname: str) -> list[str]:
    path = case_dir / dirname
    if not path.is_dir():
        return []
    return sorted(item.name for item in path.iterdir() if item.is_file())


def _mail_candidates_from_payload(items: list[dict[str, Any]]) -> list[MailCandidate]:
    candidates: list[MailCandidate] = []
    for item in items:
        try:
            candidates.append(
                MailCandidate(
                    message_id=str(item.get("message_id") or ""),
                    subject=str(item.get("subject") or "-"),
                    sender=str(item.get("sender") or "-"),
                    received=str(item.get("received") or "-"),
                    preview=str(item.get("preview") or ""),
                    folder=str(item.get("folder") or ""),
                    web_link=str(item.get("web_link") or ""),
                    conversation_id=str(item.get("conversation_id") or ""),
                    source_query=str(item.get("source_query")) if item.get("source_query") is not None else None,
                )
            )
        except AttributeError as exc:
            raise CaseError("related_emails in case.json ist ungueltig.") from exc
    return candidates


def _build_followup_turn(
    *,
    user_question: str | None,
    resume_source: str,
    refresh: bool,
    related_runs: list[dict[str, Any]],
    event_runs: list[dict[str, Any]],
) -> dict[str, Any]:
    new_queries = _dedupe_keep_order(
        [
            str(run.get("query") or "").strip()
            for run in [*related_runs, *event_runs]
            if str(run.get("query") or "").strip()
        ]
    )
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_question": user_question or "",
        "resume_source": resume_source,
        "refresh": refresh,
        "new_queries": new_queries,
        "notes": [],
    }


def _write_active_case_pointer(
    *,
    prepared_case: PreparedCase,
    analysis_status: str,
    user_question: str | None,
) -> None:
    payload = {
        "case_id": prepared_case.case_id,
        "case_dir": str(prepared_case.case_dir),
        "seed_message_id": prepared_case.seed_message_id,
        "last_active_at": datetime.now(timezone.utc).isoformat(),
        "last_user_question": user_question or prepared_case.user_prompt,
        "session_status": analysis_status,
    }
    _ensure_dir(_session_state_dir())
    _write_json(_active_case_path(), payload)


def prepare_case(
    message_id: str | None = None,
    *,
    query: str | None = None,
    selection_index: int = 0,
    debug: bool = True,
) -> PreparedCase:
    token = ms._resolve_token(None, debug=True if debug else False)
    resolution = _resolve_seed_message(token=token, message_id=message_id, query=query, selection_index=selection_index)
    seed_message = _fetch_message(resolution.message_id, token)
    metadata = ms._extract_message_metadata(seed_message)
    case_id = ms._make_email_folder_name(
        seed_message.get("receivedDateTime", ""),
        metadata["sender_address"],
        metadata["subject"],
        resolution.message_id,
    )
    case_dir = _ensure_dir(CASE_BASE_DIR / case_id)
    _ensure_dir(case_dir / "logs")
    _log(f"Case-Ordner: {case_dir}")
    thread_messages = _fetch_thread_messages(seed_message.get("conversationId", ""), token) or [seed_message]
    attachment_names, attachment_md_names = _render_thread_markdown(case_dir, thread_messages, token, debug)
    prepared_case = PreparedCase(
        case_id=case_id,
        case_dir=case_dir,
        token=token,
        seed_message_id=resolution.message_id,
        seed_message=seed_message,
        thread_messages=thread_messages,
        attachment_names=attachment_names,
        attachment_md_names=attachment_md_names,
        seed_resolution=resolution,
        warnings=[resolution.warning] if resolution.warning else [],
        user_prompt=query,
    )
    _write_context_logs(prepared_case)
    return prepared_case


def resume_case(case_id: str, *, refresh: bool = False, debug: bool = True) -> PreparedCase:
    case_dir = CASE_BASE_DIR / case_id
    if not case_dir.is_dir():
        raise CaseError(f"Case-Ordner nicht gefunden: {case_dir}")

    existing_case_json = _load_existing_case_json(case_dir)
    seed_message_id = str(existing_case_json.get("email_entry_id") or "")
    if not seed_message_id:
        raise CaseError(f"Case {case_id} enthaelt keine email_entry_id fuer die Wiederaufnahme.")

    if refresh:
        refreshed_case = prepare_case(seed_message_id, debug=debug)
        refreshed_case.user_prompt = existing_case_json.get("user_prompt") or refreshed_case.user_prompt
        return refreshed_case

    token = ms._resolve_token(None, debug=True if debug else False)
    try:
        seed_resolution_payload = _read_json_file(case_dir / "logs" / "seed_resolution.json", label="seed_resolution.json")
        seed_message = _read_json_file(case_dir / "logs" / "seed_message.json", label="seed_message.json")
        thread_messages = _read_json_file(case_dir / "logs" / "thread_messages.json", label="thread_messages.json")
    except CaseError:
        return prepare_case(seed_message_id, debug=debug)

    if not isinstance(seed_resolution_payload, dict):
        raise CaseError(f"seed_resolution.json hat einen ungueltigen Aufbau: {case_dir / 'logs' / 'seed_resolution.json'}")
    if not isinstance(seed_message, dict) or not isinstance(thread_messages, list):
        raise CaseError(f"Case {case_id} enthaelt ungueltige Seed-/Thread-Daten.")

    resolution = SearchResolution(
        message_id=str(seed_resolution_payload.get("message_id") or seed_message_id),
        selection_mode=str(seed_resolution_payload.get("selection_mode") or "message_id"),
        query=seed_resolution_payload.get("query"),
        warning=seed_resolution_payload.get("warning"),
        candidates=seed_resolution_payload.get("candidates"),
    )
    warnings = _dedupe_keep_order(list(existing_case_json.get("warnings") or []) + ([resolution.warning] if resolution.warning else []))
    prepared_case = PreparedCase(
        case_id=case_id,
        case_dir=case_dir,
        token=token,
        seed_message_id=resolution.message_id,
        seed_message=seed_message,
        thread_messages=thread_messages,
        attachment_names=_collect_attachment_names(case_dir, "attachments"),
        attachment_md_names=_collect_attachment_names(case_dir, "attachments_md"),
        seed_resolution=resolution,
        warnings=warnings,
        user_prompt=existing_case_json.get("user_prompt"),
    )
    _log(f"Case-Ordner wiederaufgenommen: {case_dir}")
    return prepared_case


def search_related_mails(
    prepared_case: PreparedCase,
    queries: list[str],
    *,
    limit: int = DEFAULT_RELATED_LIMIT,
) -> tuple[list[MailCandidate], list[dict[str, Any]], list[str]]:
    folder_cache: dict[str, str] = {}
    warnings: list[str] = []
    runs: list[dict[str, Any]] = []
    selected: dict[str, MailCandidate] = {}
    for query in _dedupe_keep_order(queries):
        _log(f"Verwandte Mails suchen: {query}")
        try:
            data = ms._execute_search_request(
                prepared_case.token,
                query,
                "message",
                25,
                top_results=True,
                scope_error_code="NO_MAIL_SCOPE",
            )
        except SystemExit as exc:
            warnings.append(f'Verwandte Mail-Suche fuer "{query}" fehlgeschlagen (exit {exc.code}).')
            continue
        total, hits = ms._extract_hits_from_search_response(data)
        run = {
            "phase": "related_mail",
            "goal": "Kontext ausserhalb des Threads nachladen",
            "target_type": "message",
            "query": query,
            "total": total,
            "selected_ids": [],
        }
        for hit in hits:
            message_id = hit.get("hitId", "")
            if not message_id or message_id == prepared_case.seed_message_id:
                continue
            full_message = _fetch_message(message_id, prepared_case.token)
            if full_message.get("conversationId") == prepared_case.seed_message.get("conversationId"):
                continue
            if message_id in selected:
                continue
            candidate = _candidate_from_message(
                full_message,
                token=prepared_case.token,
                folder_cache=folder_cache,
                source_query=query,
            )
            selected[message_id] = candidate
            run["selected_ids"].append(message_id)
            if len(selected) >= limit:
                break
        runs.append(run)
        if len(selected) >= limit:
            break
    result = list(selected.values())[:limit]
    return result, runs, warnings


def search_calendar_context(
    prepared_case: PreparedCase,
    queries: list[str],
    *,
    limit: int = DEFAULT_EVENT_LIMIT,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    runs: list[dict[str, Any]] = []
    events_by_id: dict[str, dict[str, Any]] = {}
    for query in _dedupe_keep_order(queries):
        _log(f"Kalenderkontext suchen: {query}")
        try:
            total, rendered_hits = ms._collect_rendered_event_hits(query, prepared_case.token, limit)
        except SystemExit as exc:
            warnings.append(f'Kalenderkontext fuer "{query}" nicht verfuegbar (exit {exc.code}).')
            continue
        run = {
            "phase": "calendar",
            "goal": "Kalenderkontext fuer den Mail-Fall sammeln",
            "target_type": "event",
            "query": query,
            "total": total,
            "selected_ids": [],
        }
        for item in rendered_hits:
            search_ctx = item["search_ctx"]
            event_id = str(search_ctx.get("event_id") or item.get("hit", {}).get("hitId") or "")
            if not event_id or event_id in events_by_id:
                continue
            run["selected_ids"].append(event_id)
            events_by_id[event_id] = {
                "event_id": event_id,
                "subject": item["subject"],
                "start": str(search_ctx.get("start_date") or "-"),
                "organizer": str(search_ctx.get("from") or "-"),
                "participants": str(search_ctx.get("reply_to") or "-"),
                "preview": str(search_ctx.get("body_preview") or "-"),
                "web_link": str(search_ctx.get("web_link") or "-"),
                "is_series": bool(search_ctx.get("is_series")),
                "source_query": query,
            }
            if len(events_by_id) >= limit:
                break
        runs.append(run)
        if len(events_by_id) >= limit:
            break
    result = sorted(events_by_id.values(), key=lambda item: item["start"])[:limit]
    return result, runs, warnings


def _default_sources(
    prepared_case: PreparedCase,
    related_mails: list[MailCandidate],
    events: list[dict[str, Any]],
) -> list[dict[str, str]]:
    metadata = ms._extract_message_metadata(prepared_case.seed_message)
    latest_preview = _format_message_preview(prepared_case.seed_message, prefer_unique_body=True)
    sources: list[dict[str, str]] = [
        {
            "type": "email",
            "label": f"E-Mail {metadata['subject']}",
            "reference": f"Seed-Mail, {metadata['received']}",
            "excerpt": latest_preview,
            "location_hint": metadata["received"],
            "retrieval_status": "ok",
        }
    ]
    for index, item in enumerate(prepared_case.thread_messages[:-1], 1):
        sources.append(
            {
                "type": "email",
                "label": f"Thread-Nachricht {index}",
                "reference": item.get("receivedDateTime", ""),
                "excerpt": _format_message_preview(item, prefer_unique_body=True),
                "location_hint": (item.get("receivedDateTime", "") or "").replace("T", " ")[:19],
                "retrieval_status": "ok",
            }
        )
    for mail in related_mails[:3]:
        sources.append(
            {
                "type": "related_email",
                "label": mail.subject,
                "reference": mail.message_id,
                "excerpt": mail.preview,
                "location_hint": mail.received,
                "retrieval_status": "ok",
            }
        )
    for event in events[:3]:
        sources.append(
            {
                "type": "calendar",
                "label": event["subject"],
                "reference": event["event_id"],
                "excerpt": event["preview"],
                "location_hint": event["start"],
                "retrieval_status": "ok",
            }
        )
    for name in (prepared_case.attachment_names + prepared_case.attachment_md_names)[:3]:
        sources.append(
            {
                "type": "attachment",
                "label": name,
                "reference": name,
                "excerpt": "Anhang aus Seed-Mail oder Thread gespeichert und fuer den Case verfuegbar gemacht.",
                "location_hint": f"attachments/{name}",
                "retrieval_status": "ok",
            }
        )
    return sources


def _default_summary(
    prepared_case: PreparedCase,
    related_mails: list[MailCandidate],
    events: list[dict[str, Any]],
    sources: list[dict[str, str]],
) -> dict[str, Any]:
    metadata = ms._extract_message_metadata(prepared_case.seed_message)
    latest_preview = _format_message_preview(prepared_case.seed_message, prefer_unique_body=True)
    participants = _dedupe_keep_order([metadata["from_str"]] + metadata["to_list"] + metadata["cc_list"])
    return {
        "core_topic": metadata["subject"],
        "occasion": metadata["subject"],
        "problem_statement": latest_preview,
        "expected_from_me": "Vom Agenten nach Retrieval-Verlauf zu bewerten.",
        "deadlines": [],
        "relevant_aspects": [],
        "participants": participants,
        "history": (
            f"Thread-Kontext mit {len(prepared_case.thread_messages)} Nachricht(en) ausgewertet; "
            f"{len(related_mails)} verwandte Mail(s) und {len(events)} Kalenderkontext-Treffer liegen als Evidenz vor."
        ),
        "open_points": [],
        "sources": sources,
    }


def _default_decision() -> dict[str, Any]:
    return {
        "criteria": [],
        "options": [],
        "recommendation": {
            "option_title": "Keine agentische Entscheidungsmatrix geliefert",
            "rationale": "Der Agent hat noch keine Entscheidungsmatrix in die Analyse-Payload geschrieben.",
        },
    }


def _action_file_name(action_type: str, index: int) -> str:
    if action_type == "reply":
        return f"10_email_{index}.md"
    if action_type == "todo":
        return f"20_todo_{index}.md"
    if action_type == "calendar":
        return f"30_calendar_{index}.md"
    return f"90_{action_type}_{index}.md"


def _extract_action_body(action: dict[str, Any]) -> str:
    if action.get("body"):
        return str(action["body"]).rstrip() + "\n"
    reply_draft = action.get("reply_draft") or {}
    todo = action.get("todo") or {}
    appointment = action.get("appointment") or {}
    for payload in (reply_draft, todo, appointment):
        body = payload.get("body")
        if body:
            return str(body).rstrip() + "\n"
    return ""


def _normalize_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counters: dict[str, int] = {}
    normalized: list[dict[str, Any]] = []
    for action in actions:
        action_type = str(action.get("action_type") or "note")
        counters[action_type] = counters.get(action_type, 0) + 1
        file_path = action.get("file_path") or _action_file_name(action_type, counters[action_type])
        body = _extract_action_body(action)
        normalized_action = {
            "action_id": action.get("action_id") or f"{action_type}_{counters[action_type]}",
            "action_type": action_type,
            "title": action.get("title") or file_path,
            "file_path": file_path,
            "status": action.get("status") or "proposed",
            "reply_draft": action.get("reply_draft"),
            "appointment": action.get("appointment"),
            "todo": action.get("todo"),
            "body": body.strip(),
        }
        if action_type == "reply" and normalized_action["reply_draft"] is None and body:
            normalized_action["reply_draft"] = {"label": action.get("title") or "Antwortdraft", "body": body.strip()}
        if action_type == "todo" and normalized_action["todo"] is None and body:
            normalized_action["todo"] = {"body": body.strip()}
        if action_type == "calendar" and normalized_action["appointment"] is None and body:
            normalized_action["appointment"] = {"body": body.strip()}
        normalized.append(normalized_action)
    return normalized


def _write_action_files(case_dir: Path, actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_actions = _normalize_actions(actions)
    for action in normalized_actions:
        body = _extract_action_body(action)
        if not body:
            continue
        (case_dir / action["file_path"]).write_text(body, encoding="utf-8")
    return normalized_actions


def _render_analysis_markdown(
    prepared_case: PreparedCase,
    *,
    analysis_payload: dict[str, Any],
    sources: list[dict[str, str]],
    actions: list[dict[str, Any]],
    warnings: list[str],
    retrieval_trace: list[dict[str, Any]],
    agent_decisions: list[Any],
) -> list[str]:
    summary = analysis_payload.get("summary") or {}
    decision = analysis_payload.get("decision") or _default_decision()
    core_topic = analysis_payload.get("core_topic") or summary.get("core_topic") or "-"
    open_points = analysis_payload.get("open_points") or summary.get("open_points") or []
    lines = [
        f"TL;DR: {analysis_payload.get('tlmdr') or 'Vom Agenten nachzureichen.'}",
        "",
    ]
    key_points = analysis_payload.get("key_points") or []
    if key_points:
        lines.extend(f"{index}. {point}" for index, point in enumerate(key_points, 1))
        lines.append("")
    final_analysis = analysis_payload.get("analysis_md") or analysis_payload.get("final_analysis")
    if final_analysis:
        lines.extend(["# Finale Analyse", "", str(final_analysis).strip(), ""])
    lines.append("Fristen:")
    deadlines = analysis_payload.get("deadlines") or []
    if deadlines:
        lines.extend(f"- {item}" for item in deadlines)
    else:
        lines.append("- Keine agentisch benannten Fristen.")
    lines.extend(["", "Relevante Aspekte:"])
    relevant_aspects = analysis_payload.get("relevant_aspects") or []
    if relevant_aspects:
        lines.extend(f"- {item}" for item in relevant_aspects)
    else:
        lines.append("- Keine zusaetzlichen agentischen Aspekte benannt.")
    if warnings:
        lines.extend(["", "Warnungen:"])
        lines.extend(f"- {item}" for item in warnings)
    lines.extend(["", "# Folgeaktionen"])
    if actions:
        lines.extend(f"- {action['title']} ({action['action_type']}) — proposed Datei: {action['file_path']}" for action in actions)
    else:
        lines.append("- Keine Draft-Dateien geschrieben.")
    lines.extend(
        [
            "",
            "# Evidenz",
            "",
            f"Vollstaendiger Rechercheverlauf: `logs/agent_trace.md` / `logs/agent_trace.json`.",
            "Untersuchte Mail-/Kalender-Kontexte: `logs/thread_context.md`, `logs/related_mails.md`, `logs/calendar_context.md`.",
            "",
            "# Offene Punkte",
            "",
        ]
    )
    if open_points:
        lines.extend(f"- {item}" for item in open_points)
    else:
        lines.append("- Keine offenen Punkte benannt.")
    lines.extend(["", "# Quellen"])
    for source in sources:
        lines.append(f"- [{source['type']}] {source['label']} ({source['location_hint']}): {source['excerpt']}")
    lines.extend(["", "# Entscheidungsmatrix", "", f"Kernthema: {core_topic}", "", "## Kriterien"])
    criteria = decision.get("criteria") or []
    if criteria:
        for criterion in criteria:
            suffix = " *(dynamisch)*" if criterion.get("is_dynamic") else ""
            lines.append(f"- {criterion.get('name', '-')}{suffix}")
    else:
        lines.append("- Keine Kriterien geliefert.")
    lines.extend(["", "## Optionen"])
    options = decision.get("options") or []
    if not options:
        lines.append("Keine agentischen Optionen dokumentiert.")
    else:
        for option in options:
            lines.extend(
                [
                    "",
                    f"#### {option.get('title', '-')}",
                    str(option.get("description", "-")),
                    "",
                    "| Kriterium | Score | Begruendung |",
                    "|-----------|-------|-------------|",
                ]
            )
            for criterion_name, rating in (option.get("ratings") or {}).items():
                lines.append(
                    f"| {criterion_name} | {rating.get('score', '-')}/5 | {rating.get('rationale', '-')} |"
                )
    recommendation = decision.get("recommendation") or {}
    lines.extend(
        [
            "",
            f"## Empfehlung: {recommendation.get('option_title', '-')}",
            str(recommendation.get("rationale", "-")),
            "",
        ]
    )
    return lines


def _build_case_json(
    prepared_case: PreparedCase,
    *,
    analysis_status: str,
    summary: dict[str, Any],
    decision: dict[str, Any],
    actions: list[dict[str, Any]],
    related_mails: list[MailCandidate],
    events: list[dict[str, Any]],
    related_runs: list[dict[str, Any]],
    event_runs: list[dict[str, Any]],
    warnings: list[str],
    retrieval_trace: list[dict[str, Any]],
    agent_decisions: list[Any],
    existing_case_json: dict[str, Any] | None = None,
    resume_source: str | None = None,
    last_user_question: str | None = None,
    followup_turns: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    metadata = ms._extract_message_metadata(prepared_case.seed_message)
    now = datetime.now(timezone.utc).isoformat()
    return {
        "case_id": prepared_case.case_id,
        "case_dir": str(prepared_case.case_dir),
        "email_entry_id": prepared_case.seed_message_id,
        "source_type": "email",
        "analysis_status": analysis_status,
        "case_status": "open",
        "error": None,
        "created_at": (existing_case_json or {}).get("created_at") or now,
        "completed_at": now,
        "forced_rerun": False,
        "archived_at": None,
        "archive_error": None,
        "archive_sync_pending_side": None,
        "supersedes_result_path": None,
        "received_at": prepared_case.seed_message.get("receivedDateTime", ""),
        "sender_slug": ms._slugify_filename(
            metadata["sender_address"].split("@")[0] if metadata["sender_address"] else metadata["from_str"],
            limit=40,
        ),
        "subject_slug": ms._slugify_filename(_normalize_subject(metadata["subject"]), limit=40),
        "folder_name": prepared_case.case_id,
        "tlmdr": summary.get("tlmdr") or summary.get("problem_statement") or "",
        "user_prompt": prepared_case.user_prompt,
        "last_active_at": now,
        "last_user_question": last_user_question if last_user_question is not None else (existing_case_json or {}).get("last_user_question"),
        "resume_source": resume_source if resume_source is not None else (existing_case_json or {}).get("resume_source"),
        "followup_turns": followup_turns if followup_turns is not None else list((existing_case_json or {}).get("followup_turns") or []),
        "assigned_clusters": [],
        "seed_resolution": asdict(prepared_case.seed_resolution),
        "retrieval_trace": retrieval_trace,
        "agent_decisions": agent_decisions,
        "related_search_runs": related_runs,
        "calendar_search_runs": event_runs,
        "related_emails": [asdict(mail) for mail in related_mails],
        "calendar_context": events,
        "warnings": warnings,
        "analysis_warnings": warnings,
        "core_topic": summary.get("core_topic"),
        "occasion": summary.get("occasion"),
        "problem_statement": summary.get("problem_statement"),
        "expected_from_me": summary.get("expected_from_me"),
        "deadlines": summary.get("deadlines") or [],
        "relevant_aspects": summary.get("relevant_aspects") or [],
        "participants": summary.get("participants") or [],
        "history": summary.get("history"),
        "open_points": summary.get("open_points") or [],
        "sources": summary.get("sources") or [],
        "decision": decision,
        "actions": actions,
    }


def write_prepared_case_state(
    prepared_case: PreparedCase,
    *,
    related_mails: list[MailCandidate] | None = None,
    events: list[dict[str, Any]] | None = None,
    related_runs: list[dict[str, Any]] | None = None,
    event_runs: list[dict[str, Any]] | None = None,
    retrieval_trace: list[dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
    resume_source: str | None = None,
    user_question: str | None = None,
    refresh: bool = False,
    existing_case_json: dict[str, Any] | None = None,
    persist_related_context: bool = True,
    persist_calendar_context: bool = True,
) -> Path:
    related_mails = related_mails or []
    events = events or []
    related_runs = related_runs or []
    event_runs = event_runs or []
    retrieval_trace = retrieval_trace or []
    merged_warnings = _dedupe_keep_order(prepared_case.warnings + (warnings or []))
    if persist_related_context:
        _write_related_markdown(prepared_case.case_dir, related_mails)
        _write_related_json(prepared_case.case_dir, related_mails)
    if persist_calendar_context:
        _write_calendar_markdown(prepared_case.case_dir, events)
        _write_calendar_json(prepared_case.case_dir, events)
    _write_agent_trace(prepared_case.case_dir, retrieval_trace)
    sources = _default_sources(prepared_case, related_mails, events)
    summary = _default_summary(prepared_case, related_mails, events, sources)
    followup_turns = list((existing_case_json or {}).get("followup_turns") or [])
    if resume_source:
        followup_turns.append(
            _build_followup_turn(
                user_question=user_question,
                resume_source=resume_source,
                refresh=refresh,
                related_runs=related_runs,
                event_runs=event_runs,
            )
        )
    case_json = _build_case_json(
        prepared_case,
        analysis_status="prepared",
        summary=summary,
        decision=_default_decision(),
        actions=[],
        related_mails=related_mails,
        events=events,
        related_runs=related_runs,
        event_runs=event_runs,
        warnings=merged_warnings,
        retrieval_trace=retrieval_trace,
        agent_decisions=[],
        existing_case_json=existing_case_json,
        resume_source=resume_source,
        last_user_question=user_question,
        followup_turns=followup_turns,
    )
    _write_json(prepared_case.case_dir / "case.json", case_json)
    _write_active_case_pointer(prepared_case=prepared_case, analysis_status="prepared", user_question=user_question)
    return prepared_case.case_dir


def finalize_case(
    prepared_case: PreparedCase,
    *,
    analysis_payload: dict[str, Any],
    related_mails: list[MailCandidate] | None = None,
    events: list[dict[str, Any]] | None = None,
    related_runs: list[dict[str, Any]] | None = None,
    event_runs: list[dict[str, Any]] | None = None,
    retrieval_trace: list[dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
    resume_source: str | None = None,
    user_question: str | None = None,
    refresh: bool = False,
    existing_case_json: dict[str, Any] | None = None,
    persist_related_context: bool = True,
    persist_calendar_context: bool = True,
) -> Path:
    related_mails = related_mails or []
    events = events or []
    related_runs = related_runs or []
    event_runs = event_runs or []
    existing_trace = list((existing_case_json or {}).get("retrieval_trace") or [])
    payload_trace = list(analysis_payload.get("retrieval_trace") or [])
    if retrieval_trace is not None:
        retrieval_trace = retrieval_trace
    elif payload_trace:
        retrieval_trace = [*existing_trace, *payload_trace]
    else:
        retrieval_trace = existing_trace
    agent_decisions = list((existing_case_json or {}).get("agent_decisions") or [])
    agent_decisions.extend(list(analysis_payload.get("agent_decisions") or []))
    merged_warnings = _dedupe_keep_order(
        prepared_case.warnings + (warnings or []) + list(analysis_payload.get("analysis_warnings") or [])
    )
    if persist_related_context:
        _write_related_markdown(prepared_case.case_dir, related_mails)
        _write_related_json(prepared_case.case_dir, related_mails)
    if persist_calendar_context:
        _write_calendar_markdown(prepared_case.case_dir, events)
        _write_calendar_json(prepared_case.case_dir, events)
    _write_agent_trace(prepared_case.case_dir, retrieval_trace)

    sources = (
        analysis_payload.get("sources")
        or analysis_payload.get("summary", {}).get("sources")
        or _default_sources(prepared_case, related_mails, events)
    )
    summary = _default_summary(prepared_case, related_mails, events, sources)
    summary.update(analysis_payload.get("summary") or {})
    summary["core_topic"] = analysis_payload.get("core_topic") or summary.get("core_topic")
    summary["occasion"] = analysis_payload.get("occasion") or summary.get("occasion")
    summary["problem_statement"] = analysis_payload.get("problem_statement") or summary.get("problem_statement")
    summary["expected_from_me"] = analysis_payload.get("expected_from_me") or summary.get("expected_from_me")
    summary["history"] = analysis_payload.get("history") or summary.get("history")
    summary["participants"] = analysis_payload.get("participants") or summary.get("participants") or []
    summary["sources"] = sources
    summary["open_points"] = analysis_payload.get("open_points") or summary.get("open_points") or []
    summary["deadlines"] = analysis_payload.get("deadlines") or summary.get("deadlines") or []
    summary["relevant_aspects"] = analysis_payload.get("relevant_aspects") or summary.get("relevant_aspects") or []
    summary["tlmdr"] = analysis_payload.get("tlmdr") or ""

    actions = _write_action_files(prepared_case.case_dir, list(analysis_payload.get("actions") or []))
    decision = analysis_payload.get("decision") or _default_decision()
    followup_turns = list((existing_case_json or {}).get("followup_turns") or [])
    if resume_source:
        followup_turns.append(
            _build_followup_turn(
                user_question=user_question,
                resume_source=resume_source,
                refresh=refresh,
                related_runs=related_runs,
                event_runs=event_runs,
            )
        )
    analysis_lines = _render_analysis_markdown(
        prepared_case,
        analysis_payload=analysis_payload,
        sources=sources,
        actions=actions,
        warnings=merged_warnings,
        retrieval_trace=retrieval_trace,
        agent_decisions=agent_decisions,
    )
    _write_markdown(prepared_case.case_dir / "00_analyse.md", analysis_lines)
    case_json = _build_case_json(
        prepared_case,
        analysis_status="completed",
        summary=summary,
        decision=decision,
        actions=actions,
        related_mails=related_mails,
        events=events,
        related_runs=related_runs,
        event_runs=event_runs,
        warnings=merged_warnings,
        retrieval_trace=retrieval_trace,
        agent_decisions=agent_decisions,
        existing_case_json=existing_case_json,
        resume_source=resume_source,
        last_user_question=user_question,
        followup_turns=followup_turns,
    )
    case_json["tlmdr"] = analysis_payload.get("tlmdr") or case_json["tlmdr"]
    _write_json(prepared_case.case_dir / "case.json", case_json)
    _write_active_case_pointer(prepared_case=prepared_case, analysis_status="completed", user_question=user_question)
    return prepared_case.case_dir


def analyze_case(
    message_id: str | None = None,
    *,
    case_id: str | None = None,
    case_dir: str | Path | None = None,
    case_json_path: str | Path | None = None,
    query: str | None = None,
    selection_index: int = 0,
    debug: bool = True,
    related_queries: list[str] | None = None,
    calendar_queries: list[str] | None = None,
    analysis_payload: dict[str, Any] | None = None,
    retrieval_trace: list[dict[str, Any]] | None = None,
    refresh: bool = False,
    resume_source: str | None = None,
    user_question: str | None = None,
    pdf: bool = False,
) -> Path:
    case_id = _resolve_case_id_input(case_id=case_id, case_dir=case_dir, case_json_path=case_json_path)
    if case_id:
        prepared_case = resume_case(case_id, refresh=refresh, debug=debug)
        existing_case_json = _load_existing_case_json(prepared_case.case_dir)
        if not resume_source:
            if case_json_path:
                resume_source = "explicit_case_json"
            elif case_dir:
                resume_source = "explicit_case_dir"
            else:
                resume_source = "explicit_case_id"
    else:
        prepared_case = prepare_case(message_id, query=query, selection_index=selection_index, debug=debug)
        existing_case_json = None
    existing_retrieval_trace = list((existing_case_json or {}).get("retrieval_trace") or [])
    if retrieval_trace is not None:
        retrieval_trace = [*existing_retrieval_trace, *retrieval_trace]
    elif analysis_payload is None:
        retrieval_trace = existing_retrieval_trace
    related_mails = _mail_candidates_from_payload(list((existing_case_json or {}).get("related_emails") or []))
    related_runs = list((existing_case_json or {}).get("related_search_runs") or [])
    related_warnings: list[str] = []
    if related_queries:
        new_related_mails, new_related_runs, related_warnings = search_related_mails(prepared_case, related_queries)
        merged_related = {mail.message_id: mail for mail in related_mails}
        for mail in new_related_mails:
            merged_related[mail.message_id] = mail
        related_mails = list(merged_related.values())
        related_runs.extend(new_related_runs)
    events = list((existing_case_json or {}).get("calendar_context") or [])
    event_runs = list((existing_case_json or {}).get("calendar_search_runs") or [])
    event_warnings: list[str] = []
    if calendar_queries:
        new_events, new_event_runs, event_warnings = search_calendar_context(prepared_case, calendar_queries)
        merged_events = {str(event.get("event_id") or ""): event for event in events if str(event.get("event_id") or "")}
        for event in new_events:
            merged_events[str(event.get("event_id") or "")] = event
        events = list(merged_events.values())
        event_runs.extend(new_event_runs)
    merged_warnings = _dedupe_keep_order(list((existing_case_json or {}).get("warnings") or []) + related_warnings + event_warnings)
    persist_related_context = bool(related_queries) or existing_case_json is None
    persist_calendar_context = bool(calendar_queries) or existing_case_json is None
    if analysis_payload is None:
        result_dir = write_prepared_case_state(
            prepared_case,
            related_mails=related_mails,
            events=events,
            related_runs=related_runs,
            event_runs=event_runs,
            retrieval_trace=retrieval_trace,
            warnings=merged_warnings,
            resume_source=resume_source,
            user_question=user_question,
            refresh=refresh,
            existing_case_json=existing_case_json,
            persist_related_context=persist_related_context,
            persist_calendar_context=persist_calendar_context,
        )
    else:
        result_dir = finalize_case(
            prepared_case,
            analysis_payload=analysis_payload,
            related_mails=related_mails,
            events=events,
            related_runs=related_runs,
            event_runs=event_runs,
            retrieval_trace=retrieval_trace,
            warnings=merged_warnings,
            resume_source=resume_source,
            user_question=user_question,
            refresh=refresh,
            existing_case_json=existing_case_json,
            persist_related_context=persist_related_context,
            persist_calendar_context=persist_calendar_context,
        )
    if pdf:
        md_path = result_dir / "00_analyse.md"
        if md_path.exists():
            _render_pdf(md_path, result_dir / "00_analyse.pdf")
        else:
            print(f"WARN: {md_path} existiert nicht, PDF-Export uebersprungen.", file=sys.stderr)
    return result_dir


def _load_json_payload(path: Path | None) -> Any | None:
    if path is None:
        return None
    return _read_json_file(path, label="JSON-Payload")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bereitet einen Mail-Case technisch vor oder finalisiert ihn mit agentischer Analyse."
    )
    parser.add_argument("message_id", nargs="?", help="Seed-Mail als MESSAGE_ID")
    parser.add_argument("--case-id", help="Bestehenden Case ueber case_id wiederaufnehmen")
    parser.add_argument("--case-dir", type=Path, help="Bestehenden Case ueber den Case-Ordner wiederaufnehmen")
    parser.add_argument("--case-json", type=Path, help="Bestehenden Case ueber den Pfad zur case.json wiederaufnehmen")
    parser.add_argument("--query", dest="query", help="Seed-Mail ueber Graph Search suchen")
    parser.add_argument("--selection-index", type=int, default=0, help="Index fuer automatische Seed-Auswahl")
    parser.add_argument("--related-query", action="append", default=[], help="Agentisch geplante Mail-Suchquery")
    parser.add_argument("--calendar-query", action="append", default=[], help="Agentisch geplante Kalender-Suchquery")
    parser.add_argument("--analysis-json", type=Path, help="Pfad zu agentisch erzeugter Analyse-Payload")
    parser.add_argument("--trace-json", type=Path, help="Optionaler Retrieval-Trace als JSON-Datei")
    parser.add_argument("--refresh", action="store_true", help="Case-Kontext fuer --case-id erneut aus Graph laden")
    parser.add_argument("--user-question", help="Letzte User-Frage fuer Follow-up-Historie speichern")
    parser.add_argument("--pdf", action="store_true", help="Optional: PDF aus 00_analyse.md erzeugen (benoetigt markdown-pdf)")
    parser.add_argument("--debug", action="store_true", help="Debug-Ausgabe aktivieren")
    args = parser.parse_args()

    resume_args = [item for item in (args.case_id, args.case_dir, args.case_json) if item]
    if resume_args and (args.message_id or args.query):
        parser.error("--case-id/--case-dir/--case-json koennen nicht mit MESSAGE_ID oder --query kombiniert werden.")
    if len(resume_args) > 1:
        parser.error("Nur einer von --case-id, --case-dir oder --case-json ist erlaubt.")
    if not resume_args and not args.message_id and not args.query:
        parser.error("Entweder --case-id, --case-dir, --case-json, MESSAGE_ID oder --query ist erforderlich.")
    if args.refresh and not resume_args:
        parser.error("--refresh ist nur zusammen mit --case-id, --case-dir oder --case-json erlaubt.")

    try:
        analysis_payload = _load_json_payload(args.analysis_json)
        retrieval_trace = _load_json_payload(args.trace_json)
        if retrieval_trace is not None and not isinstance(retrieval_trace, list):
            raise CaseError("Retrieval-Trace muss ein JSON-Array sein.")
        case_dir = analyze_case(
            args.message_id,
            case_id=args.case_id,
            case_dir=args.case_dir,
            case_json_path=args.case_json,
            query=args.query,
            selection_index=args.selection_index,
            debug=args.debug,
            related_queries=args.related_query,
            calendar_queries=args.calendar_query,
            analysis_payload=analysis_payload,
            retrieval_trace=retrieval_trace,
            refresh=args.refresh,
            user_question=args.user_question,
            pdf=args.pdf,
        )
    except CaseError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"OK: Case bereit -> {case_dir}")


if __name__ == "__main__":
    main()
