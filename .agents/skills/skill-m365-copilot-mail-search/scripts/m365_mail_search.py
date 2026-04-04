"""M365 Mail Search via Graph Search API.

Durchsucht Outlook-Mails ueber /v1.0/search/query mit entityTypes=[message].
Benoetigt einen Token mit Mail.Read Scope (z.B. Teams-Web-Token).

Usage:
    python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py search "Suchbegriff"
    python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py search "Suchbegriff" --size 25
    python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py search "Suchbegriff" --date-order
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
import os
import sys
import time
from pathlib import Path

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


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def _has_mail_scope(token: str) -> bool:
    """Prueft ob der Token Mail.Read oder Mail.ReadWrite Scope hat."""
    return _has_required_scope(token, ("Mail.Read",)) or _has_required_scope(token, ("Mail.ReadWrite",))


def _resolve_token(explicit_token: str | None = None) -> str:
    """Liefert einen gueltigen Mail.Read-Token.

    Reihenfolge:
    1. explizit uebergebener Token
    2. vorhandener Cache
    3. Teams-Resolver: LocalStorage/Refresh-Token/Teams-Reopen
    """
    if explicit_token:
        if not _has_mail_scope(explicit_token):
            print("NO_MAIL_SCOPE", file=sys.stderr)
            print("Der uebergebene Token hat keinen Mail.Read Scope.", file=sys.stderr)
            sys.exit(2)
        return explicit_token

    cached = _load_mail_cached_token(("Mail.Read",))
    if cached:
        token, _exp = cached
        return token

    try:
        token, _exp, _source = fetch_graph_token(required_scopes=("Mail.Read",))
        return token
    except TokenAcquisitionError as exc:
        print(exc.code, file=sys.stderr)
        print(str(exc), file=sys.stderr)
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
    cleaned = text.replace("<c0>", "**").replace("</c0>", "**")
    cleaned = cleaned.replace("<ddd/>", "...")
    cleaned = cleaned.replace("\r", " ").replace("\n", " ")
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


def _format_bool(value: object) -> str:
    """Gibt boolesche Werte explizit und fehlende Werte neutral aus."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return "-"


# ---------------------------------------------------------------------------
# CMD: search
# ---------------------------------------------------------------------------

def cmd_search(query: str, token: str | None = None, size: int = DEFAULT_PAGE_SIZE, top_results: bool = True) -> None:
    """Fuehrt Mail-Suche aus. Exit-Code 2 bei fehlendem/abgelaufenem Token."""
    token = _resolve_token(token)

    # Search ausfuehren
    body = {
        "requests": [
            {
                "entityTypes": ["message"],
                "query": {"queryString": query},
                "from": 0,
                "size": min(size, 25),
                "enableTopResults": top_results,
            }
        ]
    }

    try:
        r = requests.post(
            SEARCH_URL,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=body,
            timeout=20,
        )
    except requests.RequestException as e:
        print(f"ERROR: Request failed: {e}", file=sys.stderr)
        sys.exit(1)

    if r.status_code == 401:
        # Token ungueltig
        print("TOKEN_EXPIRED", file=sys.stderr)
        sys.exit(2)

    if r.status_code == 403:
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        msg = data.get("error", {}).get("message", "")
        print("NO_MAIL_SCOPE", file=sys.stderr)
        print(f"403 Forbidden: {msg[:200]}", file=sys.stderr)
        sys.exit(2)

    if r.status_code != 200:
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        msg = data.get("error", {}).get("message", r.text[:200])
        print(f"ERROR {r.status_code}: {msg}", file=sys.stderr)
        sys.exit(1)

    data = r.json()

    # Ergebnisse extrahieren
    total = 0
    hits = []
    for val in data.get("value", []):
        for container in val.get("hitsContainers", []):
            total = container.get("total", 0)
            hits.extend(container.get("hits") or [])

    # Formatieren
    print(f'### Mail-Suche: "{query}"\n')
    print(f"**{total} Treffer** (zeige {len(hits)})\n")

    if not hits:
        print("Keine Mails gefunden.")
        return

    for i, hit in enumerate(hits, 1):
        res = hit.get("resource", {})
        hit_id = hit.get("hitId", "-")
        subject = _truncate_text((res.get("subject") or "-").strip() or "-", 160)
        summary = _clean_search_snippet(hit.get("summary", ""), 180)
        body_preview = _clean_search_snippet(res.get("bodyPreview", ""), 220)
        received = (res.get("receivedDateTime") or "").strip() or "-"
        has_attachments = _format_bool(res.get("hasAttachments"))
        importance = (res.get("importance") or "").strip() or "-"
        reply_to = _format_email_recipient_list(res.get("replyTo"))
        from_value = _format_email_contact((res.get("from") or {}).get("emailAddress"))
        web_url = (res.get("webLink") or "").strip()
        web_link_display = f"[Link oeffnen]({web_url})" if web_url else "-"

        print(f"#### Treffer {i}")
        print(f"- `hitId`: `{hit_id}`")
        print(f"- `subject`: {subject}")
        print(f"- `summary`: {summary}")
        print(f"- `bodyPreview`: {body_preview}")
        print(f"- `receivedDateTime`: {received}")
        print(f"- `hasAttachments`: {has_attachments}")
        print(f"- `importance`: {importance}")
        print(f"- `replyTo`: {reply_to}")
        print(f"- `from`: {from_value}")
        print(f"- `webLink`: {web_link_display}")
        print()

    print()


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

    url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}"
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

    # Header
    subject = msg.get("subject", "?")
    sender = msg.get("from", {}).get("emailAddress", {})
    from_str = f"{sender.get('name', '?')} <{sender.get('address', '?')}>"
    received = msg.get("receivedDateTime", "?")[:19].replace("T", " ")
    importance = msg.get("importance", "normal")
    has_attach = msg.get("hasAttachments", False)

    to_list = [f"{t['emailAddress']['name']} <{t['emailAddress']['address']}>" for t in msg.get("toRecipients", [])]
    cc_list = [f"{c['emailAddress']['name']} <{c['emailAddress']['address']}>" for c in msg.get("ccRecipients", [])]

    # Body (roh — wird erst nach Inline-Bild-Verarbeitung konvertiert)
    body_raw = msg.get("body", {}).get("content", "")
    body_type = msg.get("body", {}).get("contentType", "text")

    # Anhaenge laden (auch bei hasAttachments=false wenn cid: im Body)
    attachments = []
    has_cid = "cid:" in body_raw
    if has_attach or has_cid:
        att_url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/attachments"
        try:
            r_att = requests.get(att_url, headers={"Authorization": f"Bearer {token}"}, timeout=20)
            if r_att.status_code == 200:
                attachments = r_att.json().get("value", [])
        except requests.RequestException:
            pass

    # Inline-Bilder speichern und cid:-Referenzen im Body ersetzen
    att_dir = REPO_ROOT / "userdata" / "tmp"
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
        att_path = att_dir / att_name
        att_path.write_bytes(raw_bytes)
        inline_saved.append(str(att_path))
        if content_id and body_type == "html":
            body_raw = body_raw.replace(f"cid:{content_id}", str(att_path))

    # Body konvertieren (nach cid-Ersetzung, damit lokale Pfade erhalten bleiben)
    if body_type == "html":
        body_text = _html_to_text(body_raw)
    else:
        body_text = body_raw

    # Ausgabe Header
    print(f"### {subject}\n")
    print(f"**Von:** {from_str}")
    print(f"**Datum:** {received}")
    if importance != "normal":
        print(f"**Prioritaet:** {importance}")

    if attachments:
        non_inline = [a.get("name", "?") for a in attachments if not a.get("isInline")]
        inline_names = [a.get("name", "?") for a in attachments if a.get("isInline")]
        if non_inline:
            print(f"**Anhaenge ({len(non_inline)}):**")
            for name in non_inline:
                print(f"  - {name}")
        if inline_names:
            print(f"**Inline-Bilder ({len(inline_names)}):**")
            for name in inline_names:
                print(f"  - {name}")
    print(f"**An:** {'; '.join(to_list)}")
    if cc_list:
        print(f"**Cc:** {'; '.join(cc_list)}")
    print(f"\n---\n")
    print(body_text)

    # Anhaenge speichern und/oder konvertieren
    if (save_attachments or convert) and attachments:
        from file_parsers import convert_bytes as _convert_bytes

        att_dir = REPO_ROOT / "userdata" / "tmp"
        att_dir.mkdir(parents=True, exist_ok=True)
        saved = []
        converted = []
        for att in attachments:
            if att.get("isInline"):
                continue
            content_bytes = att.get("contentBytes", "")
            if not content_bytes:
                continue
            att_name = att.get("name", "attachment")
            raw_bytes = _decode_attachment_bytes(content_bytes, att_name)
            if raw_bytes is None:
                continue

            if save_attachments:
                att_path = att_dir / att_name
                att_path.write_bytes(raw_bytes)
                saved.append(str(att_path))

            if convert:
                try:
                    text = _convert_bytes(raw_bytes, att_name)
                    if text:
                        converted.append((att_name, text))
                except Exception as e:
                    converted.append((att_name, f"_(Konvertierung fehlgeschlagen: {e})_"))

        if saved:
            print(f"\n---\n")
            print(f"**{len(saved)} Anhang/Anhaenge gespeichert:**")
            for s in saved:
                print(f"  - {s}")

        if converted:
            for att_name, text in converted:
                print(f"\n---\n")
                print(f"## Anhang: {att_name}\n")
                print(text)

    # Thread nachladen
    if include_thread:
        conversation_id = msg.get("conversationId")
        if not conversation_id:
            print("\n---\n")
            print("_Kein conversationId vorhanden — Thread kann nicht geladen werden._")
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
            print("Usage: python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search.py search \"Suchbegriff\" [--size N] [--date-order] [--token TOKEN]")
            sys.exit(1)
        query = sys.argv[2]
        token = None
        size = DEFAULT_PAGE_SIZE
        top_results = "--date-order" not in sys.argv
        if "--token" in sys.argv:
            idx = sys.argv.index("--token")
            if idx + 1 < len(sys.argv):
                token = sys.argv[idx + 1]
        if "--size" in sys.argv:
            idx = sys.argv.index("--size")
            if idx + 1 < len(sys.argv):
                size = int(sys.argv[idx + 1])
        cmd_search(query, token, size, top_results)

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
