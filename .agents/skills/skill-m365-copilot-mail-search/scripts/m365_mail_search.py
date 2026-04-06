"""M365 Mail/Event Search via Graph Search API.

Durchsucht Outlook-Mails ueber /v1.0/search/query mit entityTypes=[message].
Mit --events werden stattdessen Outlook-Kalendereintraege ueber entityTypes=[event] gesucht.
Mail-Suche benoetigt Mail.Read, Event-Suche benoetigt Calendars.Read.

Usage:
    python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py search "Suchbegriff"
    python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py search "Suchbegriff" --events
    python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py search "Suchbegriff" --size 25
    python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py search "Suchbegriff" --date-order
    python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py search "Suchbegriff" --only-summary
    python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py search "Suchbegriff" --token TOKEN
    python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py read MESSAGE_ID
    python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py read MESSAGE_ID --save-attachments
    python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py read MESSAGE_ID --save-attachments --convert
    python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py read MESSAGE_ID --include-thread
    python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py check-token

Token-Caching:
    Nutzt ausschliesslich den separaten Resolver
    .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search_token.py.
    Nur Tokens mit Mail.Read Scope funktionieren.
    Token-Laufzeit: ca. 1 Stunde.
    Bei fehlendem/abgelaufenem Token versucht das Script jetzt selbst,
    ueber .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search_token.py einen frischen Teams-Token
    zu beschaffen, bevor Exit-Code 2 zurueckgegeben wird.

Exit-Codes:
    0  Ergebnisse gefunden
    1  Fehler
    2  Token abgelaufen oder kein gueltiger Token mit Mail.Read
"""

from __future__ import annotations

import base64
import hashlib
import os
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import re

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[4]
REPO_SCRIPTS_DIR = REPO_ROOT / "scripts"

for path in (SCRIPT_DIR, REPO_SCRIPTS_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from m365_mail_search_token import TokenAcquisitionError, fetch_graph_token
from m365_mail_search_token import (
    _decode_jwt_payload as _decode_mail_jwt_payload,
    _has_required_scope,
    _load_cached_token as _load_mail_cached_token,
)

# Windows UTF-8
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

SEARCH_URL = "https://graph.microsoft.com/v1.0/search/query"
DEFAULT_PAGE_SIZE = 10
SEARCH_OUTPUT_DIR = REPO_ROOT / "tmp"
BODY_PREVIEW_LINES = 10
NOISE_TERMS = ("INTERNAL",)
MAIL_SCOPE_OPTIONS = (("Mail.Read",), ("Mail.ReadWrite",))
EVENT_SCOPE_OPTIONS = (("Calendars.Read",), ("Calendars.ReadWrite",))
EVENT_FIELDS = ["subject", "start", "iCalUId", "hasAttachments", "webLink"]


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def _has_mail_scope(token: str) -> bool:
    """Prueft ob der Token Mail.Read oder Mail.ReadWrite Scope hat."""
    return _has_required_scope(token, ("Mail.Read",)) or _has_required_scope(token, ("Mail.ReadWrite",))


def _has_any_required_scope(token: str, scope_options: tuple[tuple[str, ...], ...]) -> bool:
    """Prueft, ob ein Token mindestens eine erlaubte Scope-Kombination erfuellt."""
    return any(_has_required_scope(token, required_scopes) for required_scopes in scope_options)


def _resolve_token(
    explicit_token: str | None = None,
    scope_options: tuple[tuple[str, ...], ...] = MAIL_SCOPE_OPTIONS,
    scope_error_code: str = "NO_MAIL_SCOPE",
    scope_error_message: str = "Der uebergebene Token hat keinen Mail.Read Scope.",
) -> str:
    """Liefert einen gueltigen Graph-Token fuer die benoetigten Scopes.

    Reihenfolge:
    1. explizit uebergebener Token
    2. vorhandener Cache
    3. Teams-Resolver: LocalStorage/Refresh-Token/Teams-Reopen
    """
    if explicit_token:
        if not _has_any_required_scope(explicit_token, scope_options):
            print(scope_error_code, file=sys.stderr)
            print(scope_error_message, file=sys.stderr)
            sys.exit(2)
        return explicit_token

    for required_scopes in scope_options:
        cached = _load_mail_cached_token(required_scopes)
        if cached:
            token, _exp = cached
            return token

    last_exc: TokenAcquisitionError | None = None
    for required_scopes in scope_options:
        try:
            token, _exp, _source = fetch_graph_token(required_scopes=required_scopes)
            return token
        except TokenAcquisitionError as exc:
            last_exc = exc

    if last_exc is not None:
        print(last_exc.code, file=sys.stderr)
        print(str(last_exc), file=sys.stderr)
        sys.exit(2)

    print(scope_error_code, file=sys.stderr)
    print(scope_error_message, file=sys.stderr)
    sys.exit(2)


# ---------------------------------------------------------------------------
# CMD: check-token
# ---------------------------------------------------------------------------

def cmd_check_token() -> None:
    """Prueft ob ein gueltiger Token mit Mail.Read im Cache liegt."""
    cached = _load_mail_cached_token(("Mail.Read",))
    if cached:
        token, exp = cached
        payload = _decode_mail_jwt_payload(token)
        remaining = int(exp - time.time())
        scopes = payload.get("scp", "").split()
        mail_scopes = [s for s in scopes if s.lower().startswith("mail.")]
        print(f"VALID (expires in {remaining // 60}m {remaining % 60}s)")
        print(f"Mail-Scopes: {', '.join(mail_scopes)}")
    else:
        print("EXPIRED_OR_MISSING", file=sys.stderr)
        sys.exit(2)


# ---------------------------------------------------------------------------
# Search result formatting
# ---------------------------------------------------------------------------

def _truncate_text(text: str, limit: int) -> str:
    """Kuerzt Text fuer kompakte Markdown-Ausgabe."""
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _clean_search_snippet(text: str, limit: int = 160) -> str:
    """Bereinigt Search-Snippets aus Graph und macht sie kompakt lesbar."""
    if not text:
        return "-"
    cleaned = text.replace("<c0>", "").replace("</c0>", "")
    cleaned = cleaned.replace("<ddd/>", "...")
    cleaned = cleaned.replace("\r", " ").replace("\n", " ")
    cleaned = _strip_noise_terms(cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    if not cleaned:
        return "-"
    return _truncate_text(cleaned, limit)


def _format_email_contact(contact: dict | None) -> str:
    """Formatiert ein emailAddress-Objekt robust."""
    if not isinstance(contact, dict):
        return "-"
    name = (contact.get("name") or "").strip()
    address = (contact.get("address") or "").strip()
    if name and address:
        return f"{name} <{address}>"
    return name or address or "-"


def _format_display_name(contact: dict | None) -> str:
    """Gibt nur den Anzeigenamen zurueck, ohne Mailadresse."""
    if not isinstance(contact, dict):
        return "-"
    name = (contact.get("name") or "").strip()
    return name or "-"


def _format_display_name_or_address(contact: dict | None) -> str:
    """Gibt bevorzugt den Anzeigenamen, sonst die Mailadresse zurueck."""
    if not isinstance(contact, dict):
        return "-"
    name = (contact.get("name") or "").strip()
    address = (contact.get("address") or "").strip()
    return name or address or "-"


def _format_email_recipient_list(entries: list | None) -> str:
    """Formatiert replyTo/sender/from-Listen fuer kompakte Ausgabe."""
    if not entries:
        return "-"
    formatted = []
    for entry in entries:
        email_address = (entry or {}).get("emailAddress", {})
        rendered = _format_email_contact(email_address)
        if rendered != "-":
            formatted.append(rendered)
    return "; ".join(formatted) if formatted else "-"


def _format_display_name_list(entries: list | None) -> str:
    """Formatiert Empfaengerlisten nur mit Anzeigenamen."""
    if not entries:
        return "-"
    formatted = []
    for entry in entries:
        rendered = _format_display_name((entry or {}).get("emailAddress", {}))
        if rendered != "-":
            formatted.append(rendered)
    return "; ".join(formatted) if formatted else "-"


def _strip_html_tags(text: str) -> str:
    """Entfernt HTML-Tags in kurzen Inline-Fragmenten."""
    cleaned = re.sub(r"<[^>]+>", "", text)
    cleaned = (
        cleaned.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
    )
    return cleaned.strip()


def _strip_noise_terms(text: str) -> str:
    """Entfernt bekannte Rauschworte komplett aus Texten."""
    cleaned = text
    for term in NOISE_TERMS:
        cleaned = re.sub(rf"\b{re.escape(term)}\b", "", cleaned, flags=re.IGNORECASE)
    return cleaned


def _strip_email_addresses(text: str) -> str:
    """Entfernt Mailadressen aus Vorschauzeilen, behaelt Anzeigenamen aber bei."""
    cleaned = re.sub(r"\s*<[^<>\s]+@[^<>\s]+>\s*", "", text)
    cleaned = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()


def _slugify_filename(text: str, limit: int = 80) -> str:
    """Erzeugt einen robusten ASCII-Dateinamen aus der Suchanfrage."""
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "_", ascii_text).strip("_").lower()
    if not slug:
        slug = "mail_search"
    return slug[:limit].rstrip("_") or "mail_search"


_INVALID_WIN_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _sanitize_att_name(name: str) -> str:
    """Windows-safe Dateiname fuer Anhaenge."""
    safe = os.path.basename(name or "").strip()
    safe = _INVALID_WIN_CHARS.sub("_", safe).strip(" .")
    return safe or "attachment"


def _unique_att_path(directory: Path, name: str) -> Path:
    """Eindeutiger Pfad: name (2).ext, name (3).ext bei Kollision."""
    safe = _sanitize_att_name(name)
    stem, ext = os.path.splitext(safe)
    candidate = directory / safe
    idx = 2
    while candidate.exists():
        candidate = directory / f"{stem} ({idx}){ext}"
        idx += 1
    return candidate


def _fmt_sender(name: str, address: str) -> str:
    """Formatiert Absender als 'Name <email>' oder nur email."""
    name, address = (name or "").strip(), (address or "").strip()
    if name and address and name != address:
        return f"{name} <{address}>"
    return name or address or "-"


def _fmt_recipients(items: list[str], max_items: int = 10) -> str:
    """Semikolon-getrennte Empfaengerliste, max N + [...]."""
    items = [i.strip() for i in items if i and i.strip()]
    if not items:
        return "-"
    if len(items) > max_items:
        items = items[:max_items] + ["[...]"]
    return "; ".join(items)


def _make_email_folder_name(received_iso: str, sender_address: str, subject: str, msg_id: str) -> str:
    """Ordnername im outlook-agent Stil: YYYYmmdd_HHMM_sender_subject_hash8."""
    ts = received_iso[:16].replace("-", "").replace("T", "_").replace(":", "")
    sender_slug = _slugify_filename(sender_address.split("@")[0], limit=40) if sender_address else "unknown"
    subject_slug = _slugify_filename(subject, limit=40)
    id_hash = hashlib.sha256(msg_id.encode()).hexdigest()[:8]
    return f"{ts}_{sender_slug}_{subject_slug}_{id_hash}"


def _encode_graph_id_for_path(value: str) -> str:
    """Escaped Graph-IDs fuer die Verwendung als einzelnes URL-Pfadsegment."""
    return quote(value, safe="")


def _build_search_output_path(query: str, search_type: str = "mail") -> Path:
    """Baut den Pfad fuer die gespeicherte Suchausgabe in tmp/."""
    SEARCH_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    slug = _slugify_filename(query)
    return SEARCH_OUTPUT_DIR / f"{timestamp}_{search_type}_search_{slug}.md"


def _get_first_nonempty_lines(text: str, max_lines: int = BODY_PREVIEW_LINES) -> list[str]:
    """Extrahiert die ersten nichtleeren Zeilen aus einem Text."""
    cleaned_lines = []
    for raw_line in text.splitlines():
        line = _strip_noise_terms(raw_line)
        line = _strip_email_addresses(line)
        line = re.sub(r"\s{2,}", " ", line.strip())
        if not line:
            continue
        if line.lower().startswith("von:") or line.startswith("-----Ursprünglicher Termin"):
            break
        cleaned_lines.append(line)
        if len(cleaned_lines) >= max_lines:
            break
    return cleaned_lines


def _fetch_message_search_context(message_id: str, token: str, max_lines: int = BODY_PREVIEW_LINES) -> dict[str, str]:
    """Laedt Mail-Kontext fuer Search-Treffer: Preview, CC, Body-Rohdaten und Ordner-ID."""
    if not message_id or message_id == "-":
        return {
            "body_preview": "(Body konnte nicht geladen werden)",
            "cc": "-",
            "body_raw": "",
            "body_type": "text",
            "folder_id": "",
        }

    encoded_message_id = _encode_graph_id_for_path(message_id)
    url = f"https://graph.microsoft.com/v1.0/me/messages/{encoded_message_id}"
    params = {"$select": "body,ccRecipients,parentFolderId"}

    try:
        r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, params=params, timeout=15)
    except requests.RequestException:
        return {
            "body_preview": "(Body konnte nicht geladen werden)",
            "cc": "-",
            "body_raw": "",
            "body_type": "text",
            "folder_id": "",
        }

    if r.status_code != 200:
        return {
            "body_preview": "(Body konnte nicht geladen werden)",
            "cc": "-",
            "body_raw": "",
            "body_type": "text",
            "folder_id": "",
        }

    msg = r.json()
    body_raw = msg.get("body", {}).get("content", "")
    body_type = msg.get("body", {}).get("contentType", "text")
    cc_value = _format_display_name_list(msg.get("ccRecipients"))
    if body_type == "html":
        body_text = _html_to_text(body_raw)
    else:
        body_text = body_raw.strip()

    lines = _get_first_nonempty_lines(body_text, max_lines)
    if not lines:
        body_preview = "(Kein Body-Inhalt verfuegbar)"
    else:
        body_preview = "\n".join(lines)
    return {
        "body_preview": body_preview,
        "cc": cc_value,
        "body_raw": body_raw,
        "body_type": body_type,
        "folder_id": msg.get("parentFolderId", ""),
    }


def _resolve_folder_name(folder_id: str, token: str, cache: dict[str, str]) -> str:
    """Laedt den displayName eines Mail-Ordners via /me/mailFolders/{id}. Cached."""
    if not folder_id:
        return "-"
    if folder_id in cache:
        return cache[folder_id]
    encoded = _encode_graph_id_for_path(folder_id)
    url = f"https://graph.microsoft.com/v1.0/me/mailFolders/{encoded}"
    try:
        r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=10)
        if r.status_code == 200:
            name = r.json().get("displayName", folder_id)
            cache[folder_id] = name
            return name
    except requests.RequestException:
        pass
    cache[folder_id] = folder_id
    return folder_id


def _escape_markdown_link_label(text: str) -> str:
    """Escaped nur die Zeichen, die Markdown-Linklabels stoeren."""
    return text.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def _attachment_name(att: dict) -> str:
    """Liefert einen robusten Anzeigenamen fuer Attachments."""
    name = (att.get("name") or "").strip()
    if name:
        return name
    content_id = (att.get("contentId") or "").strip()
    if content_id:
        return content_id
    return "attachment"


def _attachment_type(att: dict) -> str:
    """Normalisiert den Graph-Typ fuer Entscheidungen im Search-Output."""
    raw = (att.get("@odata.type") or "").strip()
    if raw.endswith("fileAttachment"):
        return "fileAttachment"
    if raw.endswith("referenceAttachment"):
        return "referenceAttachment"
    if raw.endswith("itemAttachment"):
        return "itemAttachment"
    return raw or "attachment"


def _extract_attachment_link_entries(message_id: str, attachments: list[dict]) -> list[dict[str, str]]:
    """Erzeugt verlinkbare Attachment-Eintraege fuer .md und STDOUT."""
    return _extract_attachment_link_entries_for_resource("message", message_id, attachments)


def _extract_attachment_link_entries_for_resource(resource_type: str, resource_id: str, attachments: list[dict]) -> list[dict[str, str]]:
    """Erzeugt verlinkbare Attachment-Eintraege fuer Message- oder Event-Ressourcen."""
    encoded_resource_id = _encode_graph_id_for_path(resource_id)
    entries: list[dict[str, str]] = []
    for att in attachments:
        att_type = _attachment_type(att)
        name = _attachment_name(att)
        url = ""
        if att_type == "fileAttachment":
            att_id = (att.get("id") or "").strip()
            if att_id:
                url = f"https://graph.microsoft.com/v1.0/me/{resource_type}s/{encoded_resource_id}/attachments/{att_id}/$value"
        elif att_type == "referenceAttachment":
            url = (att.get("sourceUrl") or "").strip()
        if not url:
            continue
        entries.append({"name": name, "url": url})
    return entries


def _extract_cloud_links_from_body(body_raw: str, body_type: str) -> list[dict[str, str]]:
    """Extrahiert SharePoint-/OneDrive-Dateilinks aus Mail-HTML als Fallback."""
    if body_type.lower() != "html" or not body_raw:
        return []

    entries: list[dict[str, str]] = []
    pattern = re.compile(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', flags=re.IGNORECASE | re.DOTALL)
    for href, raw_label in pattern.findall(body_raw):
        url = href.strip()
        if not url:
            continue
        url_lower = url.lower()
        if not (
            "sharepoint.com" in url_lower
            or "1drv.ms" in url_lower
            or "onedrive.live.com" in url_lower
        ):
            continue
        label = _strip_html_tags(raw_label)
        label = _strip_email_addresses(label)
        label = re.sub(r"\s{2,}", " ", label).strip()
        if not label or "." not in label:
            continue
        entries.append({"name": label, "url": url})
    return entries


def _merge_attachment_entries(*groups: list[dict[str, str]]) -> list[dict[str, str]]:
    """Fasst Attachment-Eintraege zusammen und vermeidet Duplikate."""
    merged: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for group in groups:
        for entry in group:
            key = (entry["name"], entry["url"])
            if key in seen:
                continue
            seen.add(key)
            merged.append(entry)
    return merged


def _fetch_attachment_link_entries(message_id: str, token: str) -> tuple[list[dict[str, str]], str | None]:
    """Laedt nur Attachment-Metadaten und baut daraus verlinkbare Eintraege."""
    if not message_id or message_id == "-":
        return [], None

    encoded_message_id = _encode_graph_id_for_path(message_id)
    url = f"https://graph.microsoft.com/v1.0/me/messages/{encoded_message_id}/attachments"
    attachments: list[dict] = []
    while url:
        try:
            r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=15)
        except requests.RequestException:
            return [], "Konnten nicht geladen werden"

        if r.status_code != 200:
            return [], "Konnten nicht geladen werden"

        data = r.json()
        attachments.extend(data.get("value", []) or [])
        url = (data.get("@odata.nextLink") or "").strip() or None

    return _extract_attachment_link_entries(message_id, attachments), None


def _fetch_event_attachment_link_entries(event_id: str, token: str) -> tuple[list[dict[str, str]], str | None]:
    """Laedt Event-Attachments und baut daraus verlinkbare Eintraege."""
    if not event_id or event_id == "-":
        return [], None

    encoded_event_id = _encode_graph_id_for_path(event_id)
    url = f"https://graph.microsoft.com/v1.0/me/events/{encoded_event_id}/attachments"
    attachments: list[dict] = []
    while url:
        try:
            r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=15)
        except requests.RequestException:
            return [], "Konnten nicht geladen werden"

        if r.status_code != 200:
            return [], "Konnten nicht geladen werden"

        data = r.json()
        attachments.extend(data.get("value", []) or [])
        url = (data.get("@odata.nextLink") or "").strip() or None

    return _extract_attachment_link_entries_for_resource("event", event_id, attachments), None


# ---------------------------------------------------------------------------
# CMD: search
# ---------------------------------------------------------------------------

def _execute_search_request(
    token: str,
    query: str,
    entity_type: str,
    size: int,
    *,
    start_at: int = 0,
    top_results: bool = False,
    fields: list[str] | None = None,
    scope_error_code: str,
) -> dict:
    """Fuehrt einen Search-Request fuer einen Entity-Typ aus."""
    request: dict[str, object] = {
        "entityTypes": [entity_type],
        "query": {"queryString": query},
        "from": max(0, int(start_at)),
        "size": min(size, 25),
    }
    if entity_type == "message":
        request["enableTopResults"] = top_results
    if fields:
        request["fields"] = fields

    body = {"requests": [request]}

    try:
        response = requests.post(
            SEARCH_URL,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=body,
            timeout=20,
        )
    except requests.RequestException as exc:
        print(f"ERROR: Request failed: {exc}", file=sys.stderr)
        sys.exit(1)

    if response.status_code == 401:
        print("TOKEN_EXPIRED", file=sys.stderr)
        sys.exit(2)

    if response.status_code == 403:
        data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        msg = data.get("error", {}).get("message", "")
        print(scope_error_code, file=sys.stderr)
        print(f"403 Forbidden: {msg[:200]}", file=sys.stderr)
        sys.exit(2)

    if response.status_code != 200:
        data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        msg = data.get("error", {}).get("message", response.text[:200])
        print(f"ERROR {response.status_code}: {msg}", file=sys.stderr)
        sys.exit(1)

    return response.json()


def _extract_hits_from_search_response(data: dict) -> tuple[int, list[dict]]:
    """Extrahiert Gesamtzahl und Treffer aus dem Search-Response.

    Die Graph Search API kann denselben Treffer mehrfach liefern (bekanntes API-Verhalten).
    Deduplication erfolgt nach hitId, damit jede Nachricht nur einmal erscheint.
    """
    total = 0
    hits: list[dict] = []
    seen_hit_ids: set[str] = set()
    for val in data.get("value", []):
        for container in val.get("hitsContainers", []):
            total = container.get("total", 0)
            for hit in container.get("hits") or []:
                hit_id = hit.get("hitId", "")
                if hit_id and hit_id in seen_hit_ids:
                    continue
                if hit_id:
                    seen_hit_ids.add(hit_id)
                hits.append(hit)
    return total, hits


def _format_event_datetime(value: object) -> str:
    """Formatiert event.start/event.end robust fuer kompakte Ausgabe."""
    if not isinstance(value, dict):
        return "-"
    date_time = str(value.get("dateTime") or "").strip()
    timezone = str(value.get("timeZone") or "").strip()
    if date_time:
        try:
            normalized = date_time.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            date_time = parsed.isoformat(timespec="seconds").replace("+00:00", "Z")
        except ValueError:
            pass
    if date_time and timezone:
        return f"{date_time} ({timezone})"
    return date_time or timezone or "-"


def _format_event_location(value: object) -> str:
    """Formatiert die Event-Location robust."""
    if not isinstance(value, dict):
        return "-"
    display_name = str(value.get("displayName") or "").strip()
    return display_name or "-"


def _format_attendee_list(entries: list | None, max_entries: int = 10) -> str:
    """Formatiert Teilnehmerlisten und kuerzt lange Listen mit Gesamtzahl ab."""
    if not entries:
        return "-"
    formatted = []
    for entry in entries:
        rendered = _format_display_name_or_address((entry or {}).get("emailAddress", {}))
        if rendered != "-":
            formatted.append(rendered)
    if not formatted:
        return "-"
    if len(formatted) <= max_entries:
        return "; ".join(formatted)
    shortened = formatted[:max_entries] + [f"[...] ({len(formatted)})"]
    return "; ".join(shortened)


def _empty_event_search_context(received: str = "-") -> dict[str, str | bool]:
    """Liefert den leeren Fallback fuer Event-Suchergebnisse."""
    return {
        "body_preview": "(Body konnte nicht geladen werden)",
        "body_raw": "",
        "body_type": "text",
        "from": "-",
        "reply_to": "-",
        "start_date": received,
        "web_link": "-",
        "has_attachments": False,
        "event_id": "",
        "series_master_id": "",
        "event_type": "",
        "is_series": False,
    }


def _event_series_now() -> datetime:
    """Liefert den Referenzzeitpunkt fuer die Auswahl der naechsten Serieninstanz."""
    return datetime.now(timezone.utc)


def _calendar_view_window_for_event_start(start_value: object) -> tuple[str, str] | None:
    """Berechnet ein Tagesfenster fuer calendarView auf Basis von event.start."""
    if not isinstance(start_value, dict):
        return None
    date_time_raw = str(start_value.get("dateTime") or "").strip()
    if not date_time_raw:
        return None
    try:
        normalized = date_time_raw.replace("Z", "+00:00")
        start_dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if start_dt.tzinfo is None:
        timezone_name = str(start_value.get("timeZone") or "").strip()
        try:
            tzinfo = ZoneInfo(timezone_name) if timezone_name else timezone.utc
        except ZoneInfoNotFoundError:
            tzinfo = timezone.utc
        start_dt = start_dt.replace(tzinfo=tzinfo)
    day_start = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    return day_start.isoformat().replace("+00:00", "Z"), day_end.isoformat().replace("+00:00", "Z")


def _fetch_event_via_calendar_view(search_resource: dict, token: str) -> dict | None:
    """Loest ein Search-Event ueber calendarView in das echte Eventobjekt auf."""
    ical_uid = str(search_resource.get("iCalUId") or "").strip()
    window = _calendar_view_window_for_event_start(search_resource.get("start"))
    if not ical_uid or window is None:
        return None

    start_window, end_window = window
    params = {
        "startDateTime": start_window,
        "endDateTime": end_window,
        "$select": "id,body,attendees,organizer,start,webLink,hasAttachments,iCalUId,subject,type,seriesMasterId",
        "$top": "200",
    }
    try:
        r = requests.get(
            "https://graph.microsoft.com/v1.0/me/calendarView",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=20,
        )
    except requests.RequestException:
        return None

    if r.status_code != 200:
        return None

    items = r.json().get("value", []) or []
    exact_matches = [item for item in items if str(item.get("iCalUId") or "").strip() == ical_uid]
    if not exact_matches:
        return None

    search_subject = str(search_resource.get("subject") or "").strip()
    search_start = _format_event_datetime(search_resource.get("start"))
    for item in exact_matches:
        if search_subject and str(item.get("subject") or "").strip() != search_subject:
            continue
        if search_start != "-" and _format_event_datetime(item.get("start")) != search_start:
            continue
        return item

    return exact_matches[0]


def _fetch_event_direct(event_id: str, token: str) -> dict | None:
    """Versucht ein Event direkt ueber /me/events/{id} zu laden."""
    if not event_id or event_id == "-":
        return None
    encoded_event_id = _encode_graph_id_for_path(event_id)
    url = f"https://graph.microsoft.com/v1.0/me/events/{encoded_event_id}"
    params = {"$select": "id,body,attendees,organizer,start,webLink,hasAttachments,type,seriesMasterId"}

    try:
        r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, params=params, timeout=15)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    return r.json()


def _build_event_search_context_from_event(event: dict, fallback_start_date: str, fallback_event_id: str) -> dict[str, str | bool]:
    """Baut den Event-Kontext aus einem bereits geladenen Eventobjekt."""
    real_event_id = str(event.get("id") or "").strip() or fallback_event_id
    body_raw = event.get("body", {}).get("content", "")
    body_type = event.get("body", {}).get("contentType", "text")
    if body_type == "html":
        body_text = _html_to_text(body_raw)
    else:
        body_text = body_raw.strip()

    lines = _get_first_nonempty_lines(body_text, BODY_PREVIEW_LINES)
    if not lines:
        body_preview = "(Kein Body-Inhalt verfuegbar)"
    else:
        body_preview = "\n".join(lines)

    series_master_id = str(event.get("seriesMasterId") or "").strip()
    event_type = str(event.get("type") or "").strip()
    return {
        "body_preview": body_preview,
        "body_raw": body_raw,
        "body_type": body_type,
        "from": _format_display_name_or_address((event.get("organizer") or {}).get("emailAddress")),
        "reply_to": _format_attendee_list(event.get("attendees")),
        "start_date": _format_event_datetime(event.get("start")) or fallback_start_date,
        "web_link": (event.get("webLink") or "").strip() or "-",
        "has_attachments": bool(event.get("hasAttachments")),
        "event_id": real_event_id,
        "series_master_id": series_master_id,
        "event_type": event_type,
        "is_series": bool(series_master_id) or event_type in {"occurrence", "exception", "seriesMaster"},
    }


def _fetch_next_series_occurrence_event(series_master_id: str, token: str) -> dict | None:
    """Laedt die naechste Instanz einer Terminserie ab jetzt."""
    if not series_master_id:
        return None
    encoded_series_master_id = _encode_graph_id_for_path(series_master_id)
    start_dt = _event_series_now()
    end_dt = start_dt + timedelta(days=366)
    params = {
        "startDateTime": start_dt.isoformat().replace("+00:00", "Z"),
        "endDateTime": end_dt.isoformat().replace("+00:00", "Z"),
        "$select": "id,start,subject,type,seriesMasterId",
        "$top": "200",
    }
    try:
        r = requests.get(
            f"https://graph.microsoft.com/v1.0/me/events/{encoded_series_master_id}/instances",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=20,
        )
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    items = r.json().get("value", []) or []
    if not items:
        return None
    items.sort(key=lambda item: _parse_event_datetime_for_sort(_format_event_datetime(item.get("start"))))
    next_event_id = str(items[0].get("id") or "").strip()
    if not next_event_id:
        return None
    return _fetch_event_direct(next_event_id, token)


def _fetch_event_search_context(event_id: str, search_resource: dict, token: str, max_lines: int = BODY_PREVIEW_LINES) -> dict[str, str | bool]:
    """Laedt Event-Details fuer Search-Treffer: Organizer, Teilnehmer und Body-Vorschau."""
    fallback_received = _format_event_datetime((search_resource or {}).get("start"))
    if not event_id or event_id == "-":
        return _empty_event_search_context(fallback_received)

    event = _fetch_event_via_calendar_view(search_resource, token)
    if event is None:
        event = _fetch_event_direct(event_id, token)
    if event is None:
        return _empty_event_search_context(fallback_received)
    return _build_event_search_context_from_event(event, fallback_received, event_id)


def _parse_event_datetime_for_sort(value: str) -> datetime:
    """Parst das formatierte Event-Datum fuer Sortierung; Fallback auf max datetime."""
    if not value or value == "-":
        return datetime.max.replace(tzinfo=timezone.utc)
    raw = value.split(" (", 1)[0].replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return datetime.max.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _dedupe_series_event_hits(resolved_hits: list[dict], token: str) -> list[dict]:
    """Reduziert Terminserien auf genau einen Repräsentanten, den naechsten Termin."""
    groups: dict[str, list[dict]] = {}
    singles: list[dict] = []

    for item in resolved_hits:
        search_ctx = item["search_ctx"]
        series_master_id = str(search_ctx.get("series_master_id") or "").strip()
        event_type = str(search_ctx.get("event_type") or "").strip()
        event_id = str(search_ctx.get("event_id") or "").strip()
        if series_master_id:
            group_key = f"series:{series_master_id}"
        elif event_type in {"occurrence", "exception", "seriesMaster"}:
            group_key = f"series-fallback:{event_id}"
        else:
            singles.append(item)
            continue
        groups.setdefault(group_key, []).append(item)

    deduped: list[dict] = singles[:]
    for group_items in groups.values():
        group_items.sort(key=lambda entry: _parse_event_datetime_for_sort(str(entry["search_ctx"].get("start_date") or "-")))
        chosen = group_items[0]
        series_master_id = str(chosen["search_ctx"].get("series_master_id") or "").strip()
        next_event = _fetch_next_series_occurrence_event(series_master_id, token) if series_master_id else None
        if next_event is not None:
            chosen = {
                **chosen,
                "subject": _truncate_text((next_event.get("subject") or chosen["subject"]).strip() or "-", 160),
                "search_ctx": _build_event_search_context_from_event(
                    next_event,
                    str(chosen["search_ctx"].get("start_date") or "-"),
                    str(chosen["search_ctx"].get("event_id") or ""),
                ),
            }
        chosen["search_ctx"]["is_series"] = len(group_items) > 1 or bool(str(chosen["search_ctx"].get("series_master_id") or "").strip())
        deduped.append(chosen)

    deduped.sort(key=lambda entry: entry["rank"])
    return deduped


def _resolve_event_hits(hits: list[dict], token: str) -> list[dict]:
    """Loest rohe Event-Search-Hits in Event-Kontexte auf."""
    resolved_hits = []
    for rank, hit in enumerate(hits, 1):
        res = hit.get("resource", {})
        hit_id = hit.get("hitId", "-")
        resolved_hits.append(
            {
                "rank": rank,
                "hit": hit,
                "resource": res,
                "subject": _truncate_text((res.get("subject") or "-").strip() or "-", 160),
                "search_ctx": _fetch_event_search_context(hit_id, res, token),
            }
        )
    return resolved_hits


def _collect_rendered_event_hits(query: str, token: str, desired_results: int) -> tuple[int, list[dict]]:
    """Laedt weitere Event-Search-Seiten, bis genug eindeutige Treffer fuer die Anzeige vorliegen."""
    page_size = 25
    target_count = max(1, int(desired_results or 0))
    total = 0
    offset = 0
    raw_hits: list[dict] = []
    rendered_hits: list[dict] = []

    while True:
        data = _execute_search_request(
            token,
            query,
            "event",
            page_size,
            start_at=offset,
            fields=EVENT_FIELDS,
            scope_error_code="NO_CALENDAR_SCOPE",
        )
        page_total, page_hits = _extract_hits_from_search_response(data)
        total = max(total, page_total)
        if not page_hits:
            break

        raw_hits.extend(page_hits)
        rendered_hits = _dedupe_series_event_hits(_resolve_event_hits(raw_hits, token), token)
        if len(rendered_hits) >= target_count:
            break

        offset += len(page_hits)
        if offset >= page_total or len(page_hits) < page_size:
            break

    return total, rendered_hits[:target_count]


def _write_event_search_results(query: str, total: int, rendered_hits: list[dict], token: str) -> None:
    """Schreibt bereits aufgeloeste Event-Treffer auf STDOUT und in eine Markdown-Datei."""
    output_path = _build_search_output_path(query, "event")

    output_lines = [f'# Kalender-Suche: "{query}"', "", f"**{total} Treffer** (zeige {len(rendered_hits)})", ""]

    if not rendered_hits:
        output_lines.append("Keine Termine gefunden.")
        output_path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")
        rel_path = output_path.relative_to(REPO_ROOT)
        print(f'Kalender-Suche: "{query}"')
        print("Keine Termine gefunden.")
        print(f"Detaildatei gespeichert in: {rel_path}")
        return

    print(f'### Kalender-Suche: "{query}"\n')
    print(f"**{total} Treffer** (zeige {len(rendered_hits)})\n")

    for i, item in enumerate(rendered_hits, 1):
        subject = item["subject"]
        search_ctx = item["search_ctx"]
        hit_id = str((item.get("hit") or {}).get("hitId") or "-")
        body_preview = search_ctx["body_preview"]
        start_date = search_ctx["start_date"]
        from_value = search_ctx["from"]
        reply_to = search_ctx["reply_to"]
        real_event_id = search_ctx["event_id"]
        attachment_entries = []
        attachment_error = None
        if search_ctx["has_attachments"]:
            attachment_entries, attachment_error = _fetch_event_attachment_link_entries(real_event_id or hit_id, token)
        cloud_entries = _extract_cloud_links_from_body(search_ctx["body_raw"], search_ctx["body_type"])
        attachment_entries = _merge_attachment_entries(attachment_entries, cloud_entries)
        web_url = search_ctx["web_link"]

        output_lines.append(f"## Treffer {i}")
        output_lines.append(f"- startDate: {start_date}")
        output_lines.append(f"- from: {from_value}")
        output_lines.append(f"- replyTo: {reply_to}")
        output_lines.append(f"- subject: {subject}")
        if search_ctx["is_series"]:
            output_lines.append("- note: Terminserie")
        if attachment_entries:
            output_lines.append("- attachments:")
            for entry in attachment_entries:
                label = _escape_markdown_link_label(entry["name"])
                output_lines.append(f"  - [{label}]({entry['url']})")
        elif attachment_error:
            output_lines.append("- attachments:")
            output_lines.append("  - _(Konnten nicht geladen werden)_")
        output_lines.append("- bodyPreview:")
        for line in body_preview.splitlines():
            output_lines.append(f"  {line}")
        output_lines.append(f"- webLink: {web_url}")
        output_lines.append("")

        print(f"#### Treffer {i}")
        print(f"- startDate: {start_date}")
        print(f"- from: {from_value}")
        print(f"- replyTo: {reply_to}")
        print(f"- subject: {subject}")
        if search_ctx["is_series"]:
            print("- note: Terminserie")
        if attachment_entries:
            print("- attachments:")
            for entry in attachment_entries:
                print(f"  - {entry['name']}")
        print("- bodyPreview:")
        for line in body_preview.splitlines():
            print(f"  {line}")
        print()

    output_path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")
    rel_path = output_path.relative_to(REPO_ROOT)
    print(f"Detaildatei gespeichert in: {rel_path}")


def cmd_search(
    query: str,
    token: str | None = None,
    size: int = DEFAULT_PAGE_SIZE,
    top_results: bool = True,
    only_summary: bool = False,
    events_only: bool = False,
) -> None:
    """Fuehrt wahlweise Mail- oder Event-Suche aus."""
    if events_only:
        token = _resolve_token(
            token,
            scope_options=EVENT_SCOPE_OPTIONS,
            scope_error_code="NO_CALENDAR_SCOPE",
            scope_error_message="Der uebergebene Token hat keinen Calendars.Read Scope.",
        )
        total, rendered_hits = _collect_rendered_event_hits(query, token, size)
        _write_event_search_results(query, total, rendered_hits, token)
        return

    token = _resolve_token(token)
    data = _execute_search_request(
        token,
        query,
        "message",
        size,
        top_results=top_results,
        scope_error_code="NO_MAIL_SCOPE",
    )
    total, hits = _extract_hits_from_search_response(data)

    output_path = _build_search_output_path(query)
    output_lines = [f'# Mail-Suche: "{query}"', "", f"**{total} Treffer** (zeige {len(hits)})", ""]

    if not hits:
        output_lines.append("Keine Mails gefunden.")
        output_path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")
        rel_path = output_path.relative_to(REPO_ROOT)
        print(f'Mail-Suche: "{query}"')
        print("Keine Mails gefunden.")
        print(f"Detaildatei mit Links gespeichert in: {rel_path}")
        return

    print(f'### Mail-Suche: "{query}"\n')
    print(f"**{total} Treffer** (zeige {len(hits)})\n")

    folder_name_cache: dict[str, str] = {}
    for i, hit in enumerate(hits, 1):
        res = hit.get("resource", {})
        hit_id = hit.get("hitId", "-")
        subject = _truncate_text((res.get("subject") or "-").strip() or "-", 160)
        summary = _clean_search_snippet(hit.get("summary", ""), 180)
        search_ctx = _fetch_message_search_context(hit_id, token)
        folder_name = _resolve_folder_name(search_ctx.get("folder_id", ""), token, folder_name_cache)
        body_preview = search_ctx["body_preview"] if not only_summary else ""
        received = (res.get("receivedDateTime") or "").strip() or "-"
        attachment_entries = []
        attachment_error = None
        if res.get("hasAttachments"):
            attachment_entries, attachment_error = _fetch_attachment_link_entries(hit_id, token)
        cloud_entries = _extract_cloud_links_from_body(search_ctx["body_raw"], search_ctx["body_type"])
        attachment_entries = _merge_attachment_entries(attachment_entries, cloud_entries)
        importance = (res.get("importance") or "").strip() or "-"
        reply_to = _format_display_name_list(res.get("replyTo"))
        from_value = _format_display_name((res.get("from") or {}).get("emailAddress"))
        cc_value = search_ctx["cc"]
        web_url = (res.get("webLink") or "").strip()
        web_link_display = web_url or "-"

        output_lines.append(f"## Treffer {i}")
        output_lines.append(f"- receivedDateTime: {received}")
        output_lines.append(f"- folder: {folder_name}")
        output_lines.append(f"- from: {from_value}")
        output_lines.append(f"- replyTo: {reply_to}")
        if cc_value != "-":
            output_lines.append(f"- cc: {cc_value}")
        if importance.lower() != "normal":
            output_lines.append(f"- importance: {importance}")
        output_lines.append(f"- subject: {subject}")
        if attachment_entries:
            output_lines.append("- attachments:")
            for entry in attachment_entries:
                label = _escape_markdown_link_label(entry["name"])
                output_lines.append(f"  - [{label}]({entry['url']})")
        elif attachment_error:
            output_lines.append("- attachments:")
            output_lines.append("  - _(Konnten nicht geladen werden)_")
        if only_summary:
            output_lines.append(f"- summary: {summary}")
        else:
            output_lines.append("- bodyPreview:")
            for line in body_preview.splitlines():
                output_lines.append(f"  {line}")
        output_lines.append(f"- webLink: {web_link_display}")
        output_lines.append(f"- messageId: `{hit_id}`")
        output_lines.append("")

        print(f"#### Treffer {i}")
        print(f"- receivedDateTime: {received}")
        print(f"- folder: {folder_name}")
        print(f"- from: {from_value}")
        print(f"- replyTo: {reply_to}")
        if cc_value != "-":
            print(f"- cc: {cc_value}")
        if importance.lower() != "normal":
            print(f"- importance: {importance}")
        print(f"- subject: {subject}")
        if attachment_entries:
            print("- attachments:")
            for entry in attachment_entries:
                print(f"  - {entry['name']}")
        if only_summary:
            print(f"- summary: {summary}")
        else:
            print("- bodyPreview:")
            for line in body_preview.splitlines():
                print(f"  {line}")
        print(f"- messageId: {hit_id}")
        print()

    output_path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")
    rel_path = output_path.relative_to(REPO_ROOT)
    print(f"Detaildatei mit Links gespeichert in: {rel_path}")


# ---------------------------------------------------------------------------
# HTML to text
# ---------------------------------------------------------------------------

def _html_to_text(html: str) -> str:
    """Einfache HTML→Text-Konvertierung ohne externe Libs."""
    # <img> Tags zu Markdown-Bildlinks konvertieren bevor HTML gestrippt wird
    text = re.sub(r'<img[^>]+src=["\']([^"\']+)["\'][^>]*/?>', r'![Bild](\1)', html, flags=re.IGNORECASE)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</(p|div|tr|li|h[1-6])>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    # HTML-Entities
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
    text = text.replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"')
    # Mehrfache Leerzeilen zusammenfassen
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _decode_attachment_bytes(content_bytes: str, att_name: str) -> bytes | None:
    """Dekodiert Base64-Anhangsdaten robust und meldet korrupte Daten als Warning."""
    try:
        return base64.b64decode(content_bytes)
    except (ValueError, TypeError) as exc:
        print(
            f"WARNING: Attachment '{att_name}' hat ungueltige Base64-Daten: {exc}",
            file=sys.stderr,
        )
        return None


# ---------------------------------------------------------------------------
# CMD: read
# ---------------------------------------------------------------------------

def cmd_read(message_id: str, token: str | None = None, save_attachments: bool = False, convert: bool = False, include_thread: bool = False) -> None:
    """Laedt eine Mail vollstaendig per GET /v1.0/me/messages/{id}.

    Mit --include-thread wird die conversationId aus der Mail gelesen und
    alle Mails der Unterhaltung per GET /v1.0/me/messages?$filter=conversationId eq '...' nachgeladen.
    """
    token = _resolve_token(token)

    encoded_message_id = _encode_graph_id_for_path(message_id)
    url = f"https://graph.microsoft.com/v1.0/me/messages/{encoded_message_id}"
    select_fields = "subject,from,toRecipients,ccRecipients,receivedDateTime,body,hasAttachments,importance,conversationId"
    params = {"$select": select_fields}

    try:
        r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, params=params, timeout=15)
    except requests.RequestException as e:
        print(f"ERROR: Request failed: {e}", file=sys.stderr)
        sys.exit(1)

    if r.status_code == 401:
        print("TOKEN_EXPIRED", file=sys.stderr)
        sys.exit(2)

    if r.status_code == 404:
        print(f"ERROR: Message nicht gefunden (404). ID: {message_id[:40]}...", file=sys.stderr)
        sys.exit(1)

    if r.status_code != 200:
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        msg = data.get("error", {}).get("message", r.text[:200])
        print(f"ERROR {r.status_code}: {msg}", file=sys.stderr)
        sys.exit(1)

    msg = r.json()

    # Header-Daten
    subject = msg.get("subject", "?")
    sender = msg.get("from", {}).get("emailAddress", {})
    from_str = _fmt_sender(sender.get("name", ""), sender.get("address", ""))
    sender_address = sender.get("address", "")
    received = msg.get("receivedDateTime", "?")[:19].replace("T", " ")
    importance = msg.get("importance", "normal")
    has_attach = msg.get("hasAttachments", False)

    to_list = [_fmt_sender(t["emailAddress"].get("name", ""), t["emailAddress"].get("address", ""))
               for t in msg.get("toRecipients", [])]
    cc_list = [_fmt_sender(c["emailAddress"].get("name", ""), c["emailAddress"].get("address", ""))
               for c in msg.get("ccRecipients", [])]

    # Ausgabe-Ordner: tmp/emails/YYYYmmdd_HHMM_sender_subject_hash8/
    folder_name = _make_email_folder_name(
        msg.get("receivedDateTime", ""), sender_address, subject, message_id,
    )
    out_dir = REPO_ROOT / "tmp" / "emails" / folder_name
    att_dir = out_dir / "attachments"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Body (roh — wird erst nach Inline-Bild-Verarbeitung konvertiert)
    body_raw = msg.get("body", {}).get("content", "")
    body_type = msg.get("body", {}).get("contentType", "text")

    # Anhaenge laden (auch bei hasAttachments=false wenn cid: im Body)
    attachments = []
    has_cid = "cid:" in body_raw
    if has_attach or has_cid:
        att_url = f"https://graph.microsoft.com/v1.0/me/messages/{encoded_message_id}/attachments"
        try:
            r_att = requests.get(att_url, headers={"Authorization": f"Bearer {token}"}, timeout=20)
            if r_att.status_code == 200:
                attachments = r_att.json().get("value", [])
        except requests.RequestException:
            pass

    non_inline = [a for a in attachments if not a.get("isInline")]

    # Nicht-Inline-Anhaenge speichern (VOR email.md, damit Dateinamen verfuegbar)
    saved_att_names: list[str] = []
    converted: list[tuple[str, str]] = []
    if (save_attachments or convert) and non_inline:
        att_dir.mkdir(parents=True, exist_ok=True)
        for att in non_inline:
            content_bytes = att.get("contentBytes", "")
            if not content_bytes:
                continue
            att_name = att.get("name", "attachment")
            raw_bytes = _decode_attachment_bytes(content_bytes, att_name)
            if raw_bytes is None:
                continue
            if save_attachments:
                att_path = _unique_att_path(att_dir, att_name)
                att_path.write_bytes(raw_bytes)
                saved_att_names.append(att_path.name)
            if convert:
                from file_parsers import convert_bytes as _convert_bytes
                try:
                    text = _convert_bytes(raw_bytes, att_name)
                    if text:
                        converted.append((att_name, text))
                except Exception as e:
                    converted.append((att_name, f"_(Konvertierung fehlgeschlagen: {e})_"))

    # Inline-Bilder in attachments/ speichern und cid:-Referenzen im Body ersetzen
    att_dir.mkdir(parents=True, exist_ok=True)
    inline_saved = []
    for att in attachments:
        if not att.get("isInline"):
            continue
        content_bytes = att.get("contentBytes", "")
        if not content_bytes:
            continue
        att_name = att.get("name", "inline_image")
        content_id = att.get("contentId", "")
        raw_bytes = _decode_attachment_bytes(content_bytes, att_name)
        if raw_bytes is None:
            continue
        att_path = _unique_att_path(att_dir, att_name)
        att_path.write_bytes(raw_bytes)
        inline_saved.append(str(att_path))
        if content_id and body_type == "html":
            body_raw = body_raw.replace(f"cid:{content_id}", str(att_path))

    # Body konvertieren (nach cid-Ersetzung, damit lokale Pfade erhalten bleiben)
    if body_type == "html":
        body_text = _html_to_text(body_raw)
    else:
        body_text = body_raw

    # email.md aufbauen — outlook-agent Format (Plaintext-Header)
    inline_atts = [a for a in attachments if a.get("isInline")]

    if saved_att_names:
        att_lines = ["Anhaenge:"] + [f"- attachments/{n}" for n in saved_att_names]
    elif non_inline:
        att_lines = ["Anhaenge:"] + [f"- {a.get('name', '?')}" for a in non_inline]
    else:
        att_lines = ["Anhaenge: -"]

    if inline_atts:
        inline_lines = ["Inline-Bilder:"] + [f"- {a.get('name', '?')}" for a in inline_atts]
    else:
        inline_lines = []

    header_lines = [
        f"Von: {from_str}",
        f"Gesendet: {received}",
    ]
    if importance != "normal":
        header_lines.append(f"Prioritaet: {importance}")
    header_lines += [
        f"An: {_fmt_recipients(to_list)}",
        f"Cc: {_fmt_recipients(cc_list)}",
        f"Betreff: {subject}",
    ]

    md_lines = header_lines + att_lines + inline_lines + ["", body_text]

    email_md_path = out_dir / "email.md"
    email_md_path.write_text("\n".join(md_lines), encoding="utf-8")

    # Konsole: gleiches Format wie email.md
    for line in header_lines + att_lines + inline_lines:
        print(line)
    print()
    print(body_text)

    # Konsole: gespeicherte Anhaenge
    if saved_att_names:
        print(f"\n{len(saved_att_names)} Anhang/Anhaenge gespeichert in attachments/:")
        for name in saved_att_names:
            print(f"  - {name}")

    if converted:
        for att_name, text in converted:
            print(f"\nAnhang: {att_name}\n")
            print(text)

    rel_out = out_dir.relative_to(REPO_ROOT)
    print(f"\nGespeichert in: {rel_out}")

    # Thread nachladen
    if include_thread:
        conversation_id = msg.get("conversationId")
        if not conversation_id:
            print("\nKein conversationId vorhanden — Thread kann nicht geladen werden.")
            return

        thread_url = "https://graph.microsoft.com/v1.0/me/messages"
        thread_params = {
            "$filter": f"conversationId eq '{conversation_id}'",
            "$select": "id,subject,from,receivedDateTime,bodyPreview,hasAttachments",
            "$top": 50,
        }
        try:
            r_thread = requests.get(thread_url, headers={"Authorization": f"Bearer {token}"}, params=thread_params, timeout=20)
        except requests.RequestException as e:
            print(f"\nERROR: Thread-Abfrage fehlgeschlagen: {e}", file=sys.stderr)
            return

        if r_thread.status_code != 200:
            data_t = r_thread.json() if r_thread.headers.get("content-type", "").startswith("application/json") else {}
            err_msg = data_t.get("error", {}).get("message", r_thread.text[:200])
            print(f"\nERROR Thread {r_thread.status_code}: {err_msg}", file=sys.stderr)
            return

        thread_msgs = r_thread.json().get("value", [])
        # Sortiere chronologisch (aelteste zuerst)
        thread_msgs.sort(key=lambda m: m.get("receivedDateTime", ""))
        print(f"\n---\n")
        print(f"## Thread ({len(thread_msgs)} Nachrichten)\n")

        if not thread_msgs:
            print("_Keine weiteren Nachrichten im Thread._")
            return

        print("| # | Datum | Von | Betreff | Vorschau |")
        print("|---|-------|-----|---------|----------|")
        for i, tm in enumerate(thread_msgs, 1):
            tm_sender = tm.get("from", {}).get("emailAddress", {})
            tm_from = tm_sender.get("name", tm_sender.get("address", "?"))
            if len(tm_from) > 25:
                tm_from = tm_from[:22] + "..."
            tm_date = (tm.get("receivedDateTime", "")[:10]) or "?"
            tm_subj = tm.get("subject", "?")
            if len(tm_subj) > 50:
                tm_subj = tm_subj[:47] + "..."
            tm_preview = (tm.get("bodyPreview", "") or "")[:80].replace("\n", " ").replace("\r", "")
            tm_id = tm.get("id", "")
            marker = " **\u25c0**" if tm_id == message_id else ""
            print(f"| {i} | {tm_date} | {tm_from} | {tm_subj}{marker} | {tm_preview} |")

        print()
        print("_Einzelne Thread-Mail lesen: `read <MESSAGE_ID>` mit der ID aus der Tabelle._")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "search":
        if len(sys.argv) < 3:
            print("Usage: python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py search \"Suchbegriff\" [--events] [--size N] [--date-order] [--only-summary] [--token TOKEN]")
            sys.exit(1)
        query = sys.argv[2]
        token = None
        size = DEFAULT_PAGE_SIZE
        top_results = "--date-order" not in sys.argv
        only_summary = "--only-summary" in sys.argv
        events_only = "--events" in sys.argv
        if "--token" in sys.argv:
            idx = sys.argv.index("--token")
            if idx + 1 < len(sys.argv):
                token = sys.argv[idx + 1]
        if "--size" in sys.argv:
            idx = sys.argv.index("--size")
            if idx + 1 < len(sys.argv):
                size = int(sys.argv[idx + 1])
        cmd_search(query, token, size, top_results, only_summary, events_only)

    elif cmd == "read":
        if len(sys.argv) < 3:
            print("Usage: python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py read MESSAGE_ID [--save-attachments] [--convert] [--include-thread] [--token TOKEN]")
            sys.exit(1)
        message_id = sys.argv[2]
        token = None
        save_att = "--save-attachments" in sys.argv
        do_convert = "--convert" in sys.argv
        inc_thread = "--include-thread" in sys.argv
        if "--token" in sys.argv:
            idx = sys.argv.index("--token")
            if idx + 1 < len(sys.argv):
                token = sys.argv[idx + 1]
        cmd_read(message_id, token, save_att, do_convert, inc_thread)

    elif cmd == "check-token":
        cmd_check_token()

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
