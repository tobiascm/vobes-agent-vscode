"""Outlook REST API Token — Extraction & Probe.

Holt den Outlook-Token ueber Playwright (Request-Interception bei Page-Reload)
und testet Outlook REST API Endpunkte.

Der Token hat audience=https://outlook.office.com und ist NICHT fuer
die Graph API (graph.microsoft.com) geeignet.

Usage:
    python scripts/outlook_token.py fetch
    python scripts/outlook_token.py fetch --headless
    python scripts/outlook_token.py check-token
    python scripts/outlook_token.py probe
    python scripts/outlook_token.py summary
    python scripts/outlook_token.py check-token --token TOKEN

Token-Caching:
    Speichert unter userdata/tmp/.outlook_token_cache.json
    Token-Laufzeit: ca. 1 Stunde (Outlook Web App).
    Bei abgelaufenem Token: erneut 'fetch' aufrufen.

Exit-Codes:
    0  Erfolgreich
    1  Fehler
    2  Token abgelaufen oder nicht vorhanden
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# Windows UTF-8
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

CACHE_FILE = Path(__file__).resolve().parent.parent / "userdata" / "tmp" / ".outlook_token_cache.json"
MIN_TOKEN_LIFETIME = 120  # Sekunden
OUTLOOK_BASE = "https://outlook.office.com"
OUTLOOK_API = f"{OUTLOOK_BASE}/api/v2.0"
OUTLOOK_URL = "https://outlook.office.com/mail/"

# Scopes die wir explizit pruefen wollen
WATCHED_SCOPES = [
    "Mail.Read",
    "Mail.ReadWrite",
    "Mail.Send",
    "Calendars.ReadWrite",
    "Contacts.ReadWrite",
    "Chat.Read",
    "Chat.ReadWrite.All",
    "ChannelMessage.Read.All",
    "Team.ReadBasic.All",
    "Files.ReadWrite.All",
    "People.Read",
    "People.ReadWrite",
    "Tasks.ReadWrite",
    "SubstrateSearch-Internal.ReadWrite",
    "Directory.Read.Global",
    "User.ReadBasic.All",
]


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

def _decode_jwt_payload(token: str) -> dict:
    """Dekodiert JWT-Payload lokal (keine Signaturpruefung)."""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Kein gueltiges JWT-Format (erwartet 3 Teile)")
    payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
    return json.loads(base64.urlsafe_b64decode(payload_b64))


def _ts_readable(ts: int | float | None) -> str:
    if ts is None:
        return "n/a"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _mask_token(token: str) -> str:
    if len(token) <= 24:
        return "***"
    return token[:12] + "..." + token[-8:]


# ---------------------------------------------------------------------------
# Token cache
# ---------------------------------------------------------------------------

def _load_cached_token() -> str | None:
    if not CACHE_FILE.exists():
        return None
    try:
        raw = CACHE_FILE.read_text("utf-8")
        if raw.startswith('"'):
            raw = json.loads(raw)
        cache = json.loads(raw)
        if cache.get("exp", 0) > time.time() + MIN_TOKEN_LIFETIME:
            return cache["token"]
    except (json.JSONDecodeError, KeyError, OSError, ValueError):
        pass
    return None


def _save_token(token: str, exp: int | float) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(
        json.dumps({"token": token, "exp": exp, "source": "outlook-web"}),
        "utf-8",
    )


def _get_token(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    token = _load_cached_token()
    if not token:
        print("TOKEN_EXPIRED", file=sys.stderr)
        print("Kein gueltiger Outlook-Token vorhanden.", file=sys.stderr)
        print("Bitte 'python scripts/outlook_token.py fetch' ausfuehren.", file=sys.stderr)
        sys.exit(2)
    return token


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def _api_call(method: str, url: str, token: str, json_body: dict | None = None,
              timeout: int = 15) -> tuple[int, dict | str]:
    headers = {"Authorization": f"Bearer {token}"}
    if json_body is not None:
        headers["Content-Type"] = "application/json"
    try:
        r = requests.request(method, url, headers=headers, json=json_body, timeout=timeout)
    except requests.RequestException as e:
        return 0, f"Request failed: {e}"
    if r.headers.get("content-type", "").startswith("application/json"):
        return r.status_code, r.json()
    return r.status_code, r.text[:500]


def _error_msg(data: dict | str) -> str:
    if isinstance(data, dict):
        err = data.get("error", {})
        if isinstance(err, dict):
            return err.get("message", str(err))[:200]
        return str(err)[:200]
    return str(data)[:200]


# ---------------------------------------------------------------------------
# CMD: fetch  (Playwright-basiert)
# ---------------------------------------------------------------------------

def cmd_fetch(headless: bool = False, cdp_port: int = 9222) -> None:
    """Holt den Outlook-Token per Playwright CDP/Request-Interception.

    Sucht zuerst einen laufenden Chrome mit CDP auf dem angegebenen Port.
    Falls kein CDP verfuegbar: startet einen neuen Browser (braucht SSO).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Fehler: playwright nicht installiert.", file=sys.stderr)
        print("  pip install playwright && playwright install chromium", file=sys.stderr)
        sys.exit(1)

    print("=== Outlook Token Fetch ===\n")

    import socket

    cdp_url = None

    def _port_open(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            return s.connect_ex(("127.0.0.1", port)) == 0

    if _port_open(cdp_port):
        cdp_url = f"http://127.0.0.1:{cdp_port}"
        print(f"  Chrome CDP gefunden auf Port {cdp_port}")
    else:
        print(f"  Kein Chrome mit CDP auf Port {cdp_port} gefunden.")
        print(f"  Starte neuen Browser (headless={headless})...")
        print(f"  HINWEIS: Ein neuer Browser hat keine SSO-Session.")
        print(f"           Falls Login fehlschlaegt, Chrome mit CDP starten:")
        print(f'           chrome.exe --remote-debugging-port={cdp_port}')
        print()

    captured_token = None
    captured_exp = 0

    with sync_playwright() as pw:
        own_browser = False
        if cdp_url:
            browser = pw.chromium.connect_over_cdp(cdp_url)
            contexts = browser.contexts
            if not contexts:
                print("  Kein Browser-Kontext verfuegbar.", file=sys.stderr)
                sys.exit(1)
            context = contexts[0]
            # Suche existierenden Outlook-Tab
            page = None
            for p in context.pages:
                if "outlook" in p.url.lower():
                    page = p
                    print(f"  Bestehender Outlook-Tab gefunden: {p.url[:80]}")
                    break
            if not page:
                page = context.new_page()
                print(f"  Kein Outlook-Tab gefunden, oeffne neuen Tab...")
        else:
            browser = pw.chromium.launch(headless=headless)
            context = browser.new_context()
            page = context.new_page()
            own_browser = True

        def _on_request(request):
            nonlocal captured_token, captured_exp
            if captured_token:
                return
            auth = request.headers.get("authorization", "")
            if auth.startswith("Bearer "):
                token = auth[7:]
                try:
                    payload = _decode_jwt_payload(token)
                    aud = payload.get("aud", "")
                    if "outlook" in aud.lower():
                        captured_token = token
                        captured_exp = payload.get("exp", 0)
                except ValueError:
                    # Nicht jeder Bearer-Token ist ein JWT, das ist hier erwartbar.
                    pass
                except Exception as exc:
                    print(f"DEBUG: Token konnte nicht dekodiert werden: {exc}", file=sys.stderr)

        page.on("request", _on_request)

        # Wenn die Seite schon Outlook zeigt, reicht ein Reload
        if "outlook" in page.url.lower():
            print(f"  Reload der bestehenden Outlook-Seite...")
            page.reload(wait_until="networkidle", timeout=30000)
        else:
            print(f"  Navigiere zu {OUTLOOK_URL} ...")
            page.goto(OUTLOOK_URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)

        if not captured_token:
            print("  Kein Token beim ersten Laden. Reload...")
            page.reload(wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(3000)

        if own_browser:
            page.close()
            browser.close()

    if not captured_token:
        print("\nFEHLER: Kein Outlook-Token abgefangen.", file=sys.stderr)
        print("  Moegliche Ursachen:", file=sys.stderr)
        print("  - Nicht eingeloggt (SSO/Kerberos fehlt)", file=sys.stderr)
        print("  - Chrome laeuft nicht mit --remote-debugging-port", file=sys.stderr)
        print("  - Seite hat keine Requests ausgeloest", file=sys.stderr)
        print(f"\n  Alternativer Weg: Token manuell per Playwright MCP holen", file=sys.stderr)
        print(f"  und dann:  python scripts/outlook_token.py check-token --token TOKEN", file=sys.stderr)
        sys.exit(1)

    _save_token(captured_token, captured_exp)

    remaining = int(captured_exp - time.time())
    print(f"\n  Token erfolgreich extrahiert und gespeichert!")
    print(f"  Datei:    {CACHE_FILE}")
    print(f"  Laenge:   {len(captured_token)} Zeichen")
    print(f"  Gueltig:  {remaining // 60}m {remaining % 60}s")
    print(f"\nNutze jetzt:")
    print(f"  python scripts/outlook_token.py check-token")
    print(f"  python scripts/outlook_token.py probe")
    print()
    print(f"HINWEIS: Outlook-Tokens sind nonce-gebunden.")
    print(f"  'probe' (Python requests) schlaegt fehl (401 Signature invalid).")


# ---------------------------------------------------------------------------
# CMD: check-token
# ---------------------------------------------------------------------------

def cmd_check_token(token: str) -> dict:
    payload = _decode_jwt_payload(token)

    print("=== Outlook Token Analyse ===\n")
    print(f"Token:    {_mask_token(token)}")
    print(f"Laenge:   {len(token)} Zeichen\n")

    claims = {
        "aud": payload.get("aud"),
        "app_displayname": payload.get("app_displayname"),
        "appid": payload.get("appid") or payload.get("azp"),
        "tid": payload.get("tid"),
        "upn": payload.get("upn") or payload.get("preferred_username") or payload.get("unique_name"),
        "iat": _ts_readable(payload.get("iat")),
        "exp": _ts_readable(payload.get("exp")),
    }
    exp_ts = payload.get("exp", 0)
    remaining = int(exp_ts - time.time())
    claims["verbleibend"] = f"{remaining // 60}m {remaining % 60}s" if remaining > 0 else "ABGELAUFEN"

    for k, v in claims.items():
        print(f"  {k:20s} {v}")

    scp_str = payload.get("scp", "")
    scopes = sorted(scp_str.split()) if scp_str else []
    scope_set = {s.lower() for s in scopes}

    print(f"\n=== Scopes ({len(scopes)}) ===\n")
    for s in scopes:
        print(f"  {s}")

    print(f"\n=== Scope-Pruefung (relevante Scopes) ===\n")
    print(f"  {'Scope':<40s} {'Status'}")
    print(f"  {'-'*40} {'-'*10}")
    for ws in WATCHED_SCOPES:
        present = ws.lower() in scope_set
        marker = "PRESENT" if present else "MISSING"
        symbol = "+" if present else "-"
        print(f"  {ws:<40s} [{symbol}] {marker}")

    return {"payload": payload, "scopes": scopes, "scope_set": scope_set, "remaining": remaining}


# ---------------------------------------------------------------------------
# CMD: probe
# ---------------------------------------------------------------------------

def cmd_probe(token: str) -> list[dict]:
    results: list[dict] = []

    def _test(name: str, method: str, url: str, scope: str,
              json_body: dict | None = None) -> dict:
        status, data = _api_call(method, url, token, json_body)
        if status == 0:
            verdict = "FAIL"
        elif 200 <= status < 300:
            verdict = "PASS"
        elif status == 403:
            verdict = "FAIL (403 Forbidden)"
        elif status == 401:
            verdict = "FAIL (401 Unauthorized)"
        else:
            verdict = f"FAIL ({status})"
        result = {
            "name": name,
            "method": method,
            "url": url.replace(OUTLOOK_BASE, ""),
            "scope": scope,
            "status": status,
            "verdict": verdict,
            "error": _error_msg(data) if status >= 400 or status == 0 else "",
        }
        results.append(result)
        return result

    print("=== Outlook REST API Probe ===\n")
    print(f"  {'#':<3} {'Test':<40} {'Status':<6} {'Ergebnis':<25} {'Scope'}")
    print(f"  {'─'*3} {'─'*40} {'─'*6} {'─'*25} {'─'*35}")

    def _row(idx: int, r: dict) -> None:
        print(f"  {idx:<3} {r['name']:<40} {r['status']:<6} {r['verdict']:<25} {r['scope']}")
        if r["error"]:
            print(f"      → {r['error']}")

    # 1. Identity
    r = _test("Identity (/me)", "GET",
              f"{OUTLOOK_API}/me", "User.ReadBasic")
    _row(1, r)

    # 2. Mail messages
    r = _test("Mail messages", "GET",
              f"{OUTLOOK_API}/me/messages?$top=3&$select=Id,Subject,ReceivedDateTime,From",
              "Mail.Read / Mail.ReadWrite")
    _row(2, r)

    # 3. Mail folders
    r = _test("Mail folders", "GET",
              f"{OUTLOOK_API}/me/mailfolders?$top=5",
              "Mail.Read / Mail.ReadWrite")
    _row(3, r)

    # 4. Calendars
    r = _test("Calendars", "GET",
              f"{OUTLOOK_API}/me/calendars",
              "Calendars.ReadWrite")
    _row(4, r)

    # 5. Calendar Events (naechste 3)
    r = _test("Calendar events", "GET",
              f"{OUTLOOK_API}/me/events?$top=3&$select=Subject,Start,End",
              "Calendars.ReadWrite")
    _row(5, r)

    # 6. Contacts
    r = _test("Contacts", "GET",
              f"{OUTLOOK_API}/me/contacts?$top=3&$select=DisplayName,EmailAddresses",
              "Contacts.ReadWrite")
    _row(6, r)

    # 7. Contact folders
    r = _test("Contact folders", "GET",
              f"{OUTLOOK_API}/me/contactfolders",
              "Contacts.ReadWrite")
    _row(7, r)

    # 8. Tasks
    r = _test("Task folders", "GET",
              f"{OUTLOOK_API}/me/taskfolders",
              "Tasks.ReadWrite")
    _row(8, r)

    # 9. People
    r = _test("People", "GET",
              f"{OUTLOOK_API}/me/people?$top=3",
              "People.Read")
    _row(9, r)

    # 10. Graph API (Gegenprobe — sollte fehlschlagen)
    r = _test("Graph /me (Gegenprobe)", "GET",
              "https://graph.microsoft.com/v1.0/me", "User.Read (Graph)")
    _row(10, r)

    print()
    return results


# ---------------------------------------------------------------------------
# CMD: summary
# ---------------------------------------------------------------------------

def cmd_summary(token: str) -> None:
    print("=" * 60)
    print("  Outlook REST API — Gesamtauswertung")
    print("=" * 60)
    print()

    info = cmd_check_token(token)
    scope_set = info["scope_set"]
    remaining = info["remaining"]
    print()

    results = cmd_probe(token)

    def _test_passed(name: str) -> str:
        for r in results:
            if r["name"] == name:
                if r["status"] == 200:
                    return "ja"
                return f"nein ({r['status']})"
        return "nicht getestet"

    matrix = [
        ("Token gueltig", "ja" if remaining > 0 else "NEIN"),
        ("Token Restlaufzeit", f"{remaining // 60}m {remaining % 60}s" if remaining > 0 else "ABGELAUFEN"),
        ("Identitaet (/me)", _test_passed("Identity (/me)")),
        ("Mails lesen", _test_passed("Mail messages")),
        ("Mail-Ordner", _test_passed("Mail folders")),
        ("Kalender", _test_passed("Calendars")),
        ("Kalender-Events", _test_passed("Calendar events")),
        ("Kontakte", _test_passed("Contacts")),
        ("Kontakt-Ordner", _test_passed("Contact folders")),
        ("Aufgaben-Ordner", _test_passed("Task folders")),
        ("Personen", _test_passed("People")),
        ("Graph API (Gegenprobe)", _test_passed("Graph /me (Gegenprobe)")),
    ]

    print("=== Ergebnis-Matrix ===\n")
    print(f"  {'Faehigkeit':<35} {'Ergebnis'}")
    print(f"  {'─'*35} {'─'*25}")
    for label, value in matrix:
        print(f"  {label:<35} {value}")

    missing = [s for s in WATCHED_SCOPES if s.lower() not in scope_set]
    if missing:
        print(f"\n=== Fehlende Scopes (aus Watch-Liste) ===\n")
        for s in missing:
            print(f"  - {s}")

    present = [s for s in WATCHED_SCOPES if s.lower() in scope_set]
    if present:
        print(f"\n=== Vorhandene relevante Scopes ===\n")
        for s in present:
            print(f"  + {s}")

    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Outlook REST API Token — Extraction & Probe",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--token", help="Expliziter Bearer-Token (statt Cache)")

    sub = parser.add_subparsers(dest="command", required=True)

    p_fetch = sub.add_parser("fetch", help="Token per Playwright aus Outlook Web extrahieren")
    p_fetch.add_argument("--headless", action="store_true",
                         help="Browser headless starten (nur ohne CDP)")

    sub.add_parser("check-token", help="Token dekodieren und Scopes anzeigen")
    sub.add_parser("probe", help="Outlook REST API Endpunkte testen")
    sub.add_parser("summary", help="Gesamtauswertung (Token + Probe + Matrix)")

    args = parser.parse_args()

    if args.command == "fetch":
        cmd_fetch(headless=args.headless)
        return

    token = _get_token(getattr(args, "token", None))

    if args.command == "check-token":
        cmd_check_token(token)
    elif args.command == "probe":
        cmd_probe(token)
    elif args.command == "summary":
        cmd_summary(token)


if __name__ == "__main__":
    main()
