"""M365 Graph API — Scope & Capability Probe.

Diagnose-Script: Zeigt Token-Scopes, testet Graph-Endpunkte und
prueft Mail-/Chat-/Channel-Suchfaehigkeit.

Usage:
    python .agents/skills/skill-m365-graph-scope-probe/scripts/m365_graph_scope_probe.py check-token
    python .agents/skills/skill-m365-graph-scope-probe/scripts/m365_graph_scope_probe.py check-token --token TOKEN
    python .agents/skills/skill-m365-graph-scope-probe/scripts/m365_graph_scope_probe.py probe
    python .agents/skills/skill-m365-graph-scope-probe/scripts/m365_graph_scope_probe.py search-mail "Suchbegriff"
    python .agents/skills/skill-m365-graph-scope-probe/scripts/m365_graph_scope_probe.py search-chat "Suchbegriff"
    python .agents/skills/skill-m365-graph-scope-probe/scripts/m365_graph_scope_probe.py summary

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

SCRIPT_PATH = Path(__file__).resolve()
SCRIPT_COMMAND = ".agents/skills/skill-m365-graph-scope-probe/scripts/m365_graph_scope_probe.py"


def _find_repo_root(start: Path) -> Path:
    """Findet den Repo-Root ueber robuste Marker statt fixer Parent-Tiefe."""
    for candidate in (start, *start.parents):
        if (candidate / ".agents").is_dir() and (candidate / "userdata").is_dir():
            return candidate
    raise RuntimeError(
        f"Repo-Root konnte ab {start} nicht ermittelt werden. "
        "Erwartet wurden die Verzeichnisse '.agents' und 'userdata'."
    )


PROJECT_ROOT = _find_repo_root(SCRIPT_PATH.parent)
CACHE_FILE = PROJECT_ROOT / "userdata" / "tmp" / ".graph_token_cache.json"
CACHE_FILE_TEAMS = PROJECT_ROOT / "userdata" / "tmp" / ".graph_token_cache_teams.json"
MIN_TOKEN_LIFETIME = 120
GRAPH = "https://graph.microsoft.com"

# Scopes die wir explizit pruefen wollen
WATCHED_SCOPES = [
    "Mail.ReadBasic",
    "Mail.Read",
    "Chat.ReadBasic",
    "Chat.Read",
    "ChannelMessage.Read.All",
    "Channel.ReadBasic.All",
    "Team.ReadBasic.All",
    "Sites.Read.All",
    "Sites.ReadWrite.All",
    "People.Read",
    "People.Read.All",
]


# ---------------------------------------------------------------------------
# Token helpers (gleicher Cache wie copilot_file_search.py / m365_file_reader.py)
# ---------------------------------------------------------------------------

def _load_cached_token(source: str = "copilot") -> str | None:
    path = CACHE_FILE_TEAMS if source == "teams" else CACHE_FILE
    if not path.exists():
        return None
    try:
        with open(path) as f:
            raw = f.read()
        # browser_evaluate filename speichert als doppelt-quoteten String
        if raw.startswith('"'):
            raw = json.loads(raw)
        cache = json.loads(raw)
        if cache.get("exp", 0) > time.time() + MIN_TOKEN_LIFETIME:
            return cache["token"]
    except (json.JSONDecodeError, KeyError, OSError, ValueError):
        pass
    return None


def _decode_jwt_payload(token: str) -> dict:
    """Dekodiert JWT-Payload lokal (keine Signaturpruefung)."""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Kein gueltiges JWT-Format (erwartet 3 Teile)")
    payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
    return json.loads(base64.urlsafe_b64decode(payload_b64))


def _get_token(explicit: str | None = None, source: str = "copilot") -> str:
    """Token aus --token Argument oder Cache laden. Exit 2 wenn keiner da."""
    if explicit:
        return explicit
    token = _load_cached_token(source)
    if not token:
        print("TOKEN_EXPIRED", file=sys.stderr)
        hint = "Teams-Seite" if source == "teams" else "Playwright NAA"
        print(f"Kein gueltiger Token vorhanden. Bitte via {hint} holen.", file=sys.stderr)
        sys.exit(2)
    return token


def _mask_token(token: str) -> str:
    """Token maskiert anzeigen: erste 12 + letzte 8 Zeichen."""
    if len(token) <= 24:
        return "***"
    return token[:12] + "..." + token[-8:]


def _ts_readable(ts: int | float | None) -> str:
    """Unix-Timestamp als lesbares Datum."""
    if ts is None:
        return "n/a"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


# ---------------------------------------------------------------------------
# Graph API call helper
# ---------------------------------------------------------------------------

def _graph_call(method: str, url: str, token: str, json_body: dict | None = None,
                timeout: int = 15) -> tuple[int, dict | str]:
    """Fuehrt Graph-API-Call aus. Gibt (status, data_or_text) zurueck."""
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
    """Extrahiert Fehlermeldung aus Graph-Response."""
    if isinstance(data, dict):
        err = data.get("error", {})
        if isinstance(err, dict):
            return err.get("message", str(err))[:200]
        return str(err)[:200]
    return str(data)[:200]


# ---------------------------------------------------------------------------
# CMD: check-token
# ---------------------------------------------------------------------------

def cmd_check_token(token: str) -> dict:
    """Dekodiert JWT und zeigt Claims + Scope-Analyse."""
    payload = _decode_jwt_payload(token)

    print(f"=== Graph Token Analyse ===\n")
    print(f"Token:    {_mask_token(token)}")
    print(f"Laenge:   {len(token)} Zeichen\n")

    # Wichtige Claims
    claims = {
        "aud": payload.get("aud"),
        "appid": payload.get("appid") or payload.get("azp"),
        "tid": payload.get("tid"),
        "upn": payload.get("upn") or payload.get("preferred_username") or payload.get("unique_name"),
        "iat": _ts_readable(payload.get("iat")),
        "nbf": _ts_readable(payload.get("nbf")),
        "exp": _ts_readable(payload.get("exp")),
    }
    exp_ts = payload.get("exp", 0)
    remaining = int(exp_ts - time.time())
    if remaining > 0:
        claims["verbleibend"] = f"{remaining // 60}m {remaining % 60}s"
    else:
        claims["verbleibend"] = "ABGELAUFEN"

    for k, v in claims.items():
        print(f"  {k:20s} {v}")

    # Scopes
    scp_str = payload.get("scp", "")
    scopes = sorted(scp_str.split()) if scp_str else []
    roles = payload.get("roles", [])

    print(f"\n=== Scopes ({len(scopes)}) ===\n")
    for s in scopes:
        print(f"  {s}")

    if roles:
        print(f"\n=== Roles ({len(roles)}) ===\n")
        for r in roles:
            print(f"  {r}")

    # Watched scopes check
    scope_set = {s.lower() for s in scopes}
    print(f"\n=== Scope-Pruefung (relevante Scopes) ===\n")
    print(f"  {'Scope':<30s} {'Status'}")
    print(f"  {'-'*30} {'-'*10}")
    for ws in WATCHED_SCOPES:
        present = ws.lower() in scope_set
        marker = "PRESENT" if present else "MISSING"
        symbol = "+" if present else "-"
        print(f"  {ws:<30s} [{symbol}] {marker}")

    return {"payload": payload, "scopes": scopes, "scope_set": scope_set, "remaining": remaining}


# ---------------------------------------------------------------------------
# CMD: probe
# ---------------------------------------------------------------------------

def cmd_probe(token: str) -> list[dict]:
    """Fuehrt eine Serie von Graph-API-Tests aus."""
    results: list[dict] = []

    def _test(name: str, method: str, url: str, scope: str,
              json_body: dict | None = None) -> dict:
        status, data = _graph_call(method, url, token, json_body)
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
            "url": url.replace(GRAPH, ""),
            "scope": scope,
            "status": status,
            "verdict": verdict,
            "error": _error_msg(data) if status >= 400 or status == 0 else "",
            "data": data if isinstance(data, dict) else {},
        }
        results.append(result)
        return result

    print("=== Graph API Probe ===\n")
    print(f"  {'#':<3} {'Test':<35} {'Status':<6} {'Ergebnis':<25} {'Scope'}")
    print(f"  {'─'*3} {'─'*35} {'─'*6} {'─'*25} {'─'*30}")

    def _row(idx: int, r: dict) -> None:
        print(f"  {idx:<3} {r['name']:<35} {r['status']:<6} {r['verdict']:<25} {r['scope']}")
        if r["error"]:
            print(f"      → {r['error']}")

    # a) /v1.0/me
    r = _test("Identity (me)", "GET", f"{GRAPH}/v1.0/me", "User.Read")
    _row(1, r)

    # b) Mail messages
    r = _test("Mail messages", "GET",
              f"{GRAPH}/v1.0/me/messages?$top=3&$select=id,subject,receivedDateTime,from",
              "Mail.ReadBasic / Mail.Read")
    _row(2, r)

    # c) Chats list
    r = _test("Chats list", "GET", f"{GRAPH}/beta/me/chats?$top=5", "Chat.ReadBasic")
    _row(3, r)

    # d) Chat messages (wenn Chats vorhanden)
    chat_id = None
    if r["status"] == 200 and isinstance(r["data"], dict):
        chats = r["data"].get("value", [])
        if chats:
            chat_id = chats[0].get("id")
    if chat_id:
        r = _test("Chat messages (1st chat)", "GET",
                  f"{GRAPH}/v1.0/chats/{chat_id}/messages?$top=3", "Chat.Read")
        _row(4, r)
    else:
        print(f"  4   {'Chat messages (1st chat)':<35} {'—':<6} {'SKIP (kein Chat)':<25} Chat.Read")

    # e) Joined teams (joinedTeams unterstuetzt kein $top)
    r = _test("Joined teams", "GET", f"{GRAPH}/v1.0/me/joinedTeams",
              "Team.ReadBasic.All")
    _row(5, r)

    # f) Team channels
    team_id = None
    if r["status"] == 200 and isinstance(r["data"], dict):
        teams = r["data"].get("value", [])
        if teams:
            team_id = teams[0].get("id")
    channel_id = None
    if team_id:
        r = _test(f"Channels (1st team)", "GET",
                  f"{GRAPH}/v1.0/teams/{team_id}/channels",
                  "Channel.ReadBasic.All")
        _row(6, r)
        if r["status"] == 200 and isinstance(r["data"], dict):
            channels = r["data"].get("value", [])
            if channels:
                channel_id = channels[0].get("id")
    else:
        print(f"  6   {'Channels (1st team)':<35} {'—':<6} {'SKIP (kein Team)':<25} Channel.ReadBasic.All")

    # g) Channel messages
    if team_id and channel_id:
        r = _test("Channel messages", "GET",
                  f"{GRAPH}/v1.0/teams/{team_id}/channels/{channel_id}/messages?$top=3",
                  "ChannelMessage.Read.All")
        _row(7, r)
    else:
        print(f"  7   {'Channel messages':<35} {'—':<6} {'SKIP (kein Channel)':<25} ChannelMessage.Read.All")

    # h) Search: message (Mail)
    search_body = {
        "requests": [{"entityTypes": ["message"], "query": {"queryString": "test"},
                       "from": 0, "size": 3}]
    }
    r = _test("Search: message (Mail)", "POST",
              f"{GRAPH}/v1.0/search/query", "Mail.Read", search_body)
    _row(8, r)

    # i) Search: chatMessage
    search_body_chat = {
        "requests": [{"entityTypes": ["chatMessage"], "query": {"queryString": "test"},
                       "from": 0, "size": 3}]
    }
    r = _test("Search: chatMessage", "POST",
              f"{GRAPH}/v1.0/search/query", "Chat.Read", search_body_chat)
    _row(9, r)

    # j) Search: message + chatMessage
    search_body_both = {
        "requests": [{"entityTypes": ["message", "chatMessage"],
                       "query": {"queryString": "test"}, "from": 0, "size": 3}]
    }
    r = _test("Search: message+chatMessage", "POST",
              f"{GRAPH}/v1.0/search/query", "Mail.Read + Chat.Read", search_body_both)
    _row(10, r)

    print()
    return results


# ---------------------------------------------------------------------------
# CMD: search-mail
# ---------------------------------------------------------------------------

def cmd_search_mail(token: str, query: str) -> None:
    """Testet Microsoft Search fuer Outlook-Mails."""
    print(f"=== Mail-Suche: \"{query}\" ===\n")
    body = {
        "requests": [{
            "entityTypes": ["message"],
            "query": {"queryString": query},
            "from": 0,
            "size": 10,
        }]
    }
    status, data = _graph_call("POST", f"{GRAPH}/v1.0/search/query", token, body)

    if status == 403:
        print(f"FAIL: 403 Forbidden")
        print(f"  → Vermutlich fehlender Scope: Mail.Read")
        print(f"  → Fehlermeldung: {_error_msg(data)}")
        sys.exit(1)
    if status == 401:
        print(f"FAIL: 401 Unauthorized — Token ungueltig/abgelaufen")
        sys.exit(2)
    if status != 200:
        print(f"FAIL: HTTP {status}")
        print(f"  → {_error_msg(data)}")
        sys.exit(1)

    # Treffer extrahieren
    hits = []
    if isinstance(data, dict):
        for resp in data.get("value", []):
            for hit_container in resp.get("hitsContainers", []):
                for hit in hit_container.get("hits", []):
                    res = hit.get("resource", {})
                    hits.append(res)

    print(f"Treffer: {len(hits)}\n")
    if not hits:
        print("Keine Ergebnisse.")
        return

    for i, res in enumerate(hits[:10], 1):
        subject = res.get("subject", "?")
        sender = res.get("from", {}).get("emailAddress", {}).get("name", "?")
        received = res.get("receivedDateTime", "?")
        web_link = res.get("webLink", "")
        print(f"  {i}. {subject}")
        print(f"     Von: {sender}  |  Datum: {received}")
        if web_link:
            print(f"     Link: {web_link}")
        print()


# ---------------------------------------------------------------------------
# CMD: search-chat
# ---------------------------------------------------------------------------

def cmd_search_chat(token: str, query: str) -> None:
    """Testet Microsoft Search fuer Teams-Chatnachrichten."""
    print(f"=== Chat-Suche: \"{query}\" ===\n")
    body = {
        "requests": [{
            "entityTypes": ["chatMessage"],
            "query": {"queryString": query},
            "from": 0,
            "size": 10,
        }]
    }
    status, data = _graph_call("POST", f"{GRAPH}/v1.0/search/query", token, body)

    if status == 403:
        print(f"FAIL: 403 Forbidden")
        print(f"  → Vermutlich fehlender Scope: Chat.Read")
        print(f"  → Fehlermeldung: {_error_msg(data)}")
        sys.exit(1)
    if status == 401:
        print(f"FAIL: 401 Unauthorized — Token ungueltig/abgelaufen")
        sys.exit(2)
    if status != 200:
        print(f"FAIL: HTTP {status}")
        print(f"  → {_error_msg(data)}")
        sys.exit(1)

    hits = []
    if isinstance(data, dict):
        for resp in data.get("value", []):
            for hit_container in resp.get("hitsContainers", []):
                for hit in hit_container.get("hits", []):
                    res = hit.get("resource", {})
                    hits.append(res)

    print(f"Treffer: {len(hits)}\n")
    if not hits:
        print("Keine Ergebnisse.")
        return

    for i, res in enumerate(hits[:10], 1):
        summary = res.get("summary", "")
        sender = res.get("from", {}).get("emailAddress", {}).get("name", "?")
        created = res.get("createdDateTime", "?")
        chat_id = res.get("chatId", "")
        print(f"  {i}. {summary[:120]}")
        print(f"     Von: {sender}  |  Datum: {created}")
        if chat_id:
            print(f"     Chat-ID: {chat_id}")
        print()


# ---------------------------------------------------------------------------
# CMD: summary
# ---------------------------------------------------------------------------

def cmd_summary(token: str) -> None:
    """Kombinierte Zusammenfassung: Token + Probe + Empfehlung."""
    print("=" * 60)
    print("  M365 Graph API — Gesamtauswertung")
    print("=" * 60)
    print()

    # 1. Token-Analyse
    info = cmd_check_token(token)
    scope_set = info["scope_set"]
    remaining = info["remaining"]

    print()

    # 2. Probe
    results = cmd_probe(token)

    # 3. Matrix
    def _has_scope(*names: str) -> bool:
        return any(n.lower() in scope_set for n in names)

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
        ("Mail-Basiszugriff (messages)", _test_passed("Mail messages")),
        ("Mail-Suche (Search API)", _test_passed("Search: message (Mail)")),
        ("Chats listen", _test_passed("Chats list")),
        ("Chat-Nachrichten lesen", _test_passed("Chat messages (1st chat)")),
        ("Chat-Suche (Search API)", _test_passed("Search: chatMessage")),
        ("Teams listen", _test_passed("Joined teams")),
        ("Kanalnachrichten lesen", _test_passed("Channel messages")),
    ]

    print("=== Ergebnis-Matrix ===\n")
    print(f"  {'Faehigkeit':<35} {'Ergebnis'}")
    print(f"  {'─'*35} {'─'*25}")
    for label, value in matrix:
        print(f"  {label:<35} {value}")

    # Fehlende Scopes
    missing = [s for s in WATCHED_SCOPES if s.lower() not in scope_set]
    if missing:
        print(f"\n=== Wahrscheinlich fehlende Scopes ===\n")
        for s in missing:
            print(f"  - {s}")

    print(f"\n=== Vorhandene relevante Scopes ===\n")
    present = [s for s in WATCHED_SCOPES if s.lower() in scope_set]
    for s in present:
        print(f"  + {s}")

    print()


# ---------------------------------------------------------------------------
# CMD: cache-teams-token
# ---------------------------------------------------------------------------

def _cmd_cache_teams_token() -> None:
    """Normalisiert und validiert den Teams-Token aus der Cache-Datei."""
    if not CACHE_FILE_TEAMS.exists():
        print("Keine Teams-Token-Datei vorhanden.", file=sys.stderr)
        print(f"Erwartet: {CACHE_FILE_TEAMS}", file=sys.stderr)
        sys.exit(2)

    raw = CACHE_FILE_TEAMS.read_text("utf-8")
    # browser_evaluate filename speichert als doppelt-quoteten String
    if raw.startswith('"'):
        raw = json.loads(raw)
    data = json.loads(raw)
    token = data.get("token", "")
    exp = data.get("exp", 0)

    if not token:
        print("Token-Datei enthaelt keinen Token.", file=sys.stderr)
        sys.exit(1)

    # Validieren gegen Graph API
    status, resp = _graph_call("GET", f"{GRAPH}/v1.0/me", token)
    if status == 401:
        print("FAIL: Token serverseitig ungueltig (401 — Signatur korrumpiert?).", file=sys.stderr)
        sys.exit(2)
    if status != 200:
        print(f"WARNING: Validierung ergab HTTP {status}", file=sys.stderr)

    # In kanonisches Format schreiben
    CACHE_FILE_TEAMS.write_text(json.dumps({"token": token, "exp": exp}), "utf-8")
    remaining = int(exp - time.time())
    print(f"Teams-Token validiert und normalisiert.")
    print(f"  Datei:    {CACHE_FILE_TEAMS}")
    print(f"  Gueltig:  {remaining // 60}m {remaining % 60}s")
    print(f"  Laenge:   {len(token)} Zeichen")
    print(f"\nNutze --source teams fuer alle Befehle:")
    print(f"  python {SCRIPT_COMMAND} --source teams check-token")
    print(f"  python {SCRIPT_COMMAND} --source teams probe")
    print(f"  python {SCRIPT_COMMAND} --source teams search-mail \"Suchbegriff\"")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="M365 Graph API — Scope & Capability Probe",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--token", help="Expliziter Bearer-Token (statt Cache)")
    parser.add_argument("--source", choices=["copilot", "teams"], default="copilot",
                        help="Token-Quelle: copilot (M365 Chat) oder teams (Teams Web)")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check-token", help="JWT dekodieren und Scopes anzeigen")
    sub.add_parser("probe", help="Graph-Endpunkte systematisch testen")

    p_smail = sub.add_parser("search-mail", help="Outlook-Mail-Suche testen")
    p_smail.add_argument("query", help="Suchbegriff")

    p_schat = sub.add_parser("search-chat", help="Teams-Chat-Suche testen")
    p_schat.add_argument("query", help="Suchbegriff")

    sub.add_parser("summary", help="Gesamtauswertung (Token + Probe + Matrix)")
    sub.add_parser("cache-teams-token",
                   help="Teams-Token aus Cache-Datei normalisieren und validieren")

    args = parser.parse_args()

    if args.command == "cache-teams-token":
        _cmd_cache_teams_token()
        return

    token = _get_token(args.token, args.source)

    if args.command == "check-token":
        cmd_check_token(token)
    elif args.command == "probe":
        cmd_probe(token)
    elif args.command == "search-mail":
        cmd_search_mail(token, args.query)
    elif args.command == "search-chat":
        cmd_search_chat(token, args.query)
    elif args.command == "summary":
        cmd_summary(token)


if __name__ == "__main__":
    main()
