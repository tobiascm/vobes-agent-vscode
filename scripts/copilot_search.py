"""M365 Copilot Search via Graph Beta API.

Usage:
    python copilot_search.py search "Suchbegriff"
    python copilot_search.py search "Suchbegriff" --token TOKEN
    python copilot_search.py cache-token TOKEN EXP_TIMESTAMP
    python copilot_search.py check-token

Token-Caching:
    Der Graph API Token wird lokal in .graph_token_cache.json gespeichert.
    Token-Laufzeit: ca. 65-70 Minuten.
    Bei abgelaufenem Token gibt 'search' Exit-Code 2 zurueck.
    Der Agent holt dann einen neuen Token via Playwright NAA und uebergibt ihn.
"""

import json
import os
import sys
import time
from pathlib import Path

import requests

CACHE_FILE = Path(__file__).resolve().parent.parent / "userdata" / "tmp" / ".graph_token_cache.json"
SEARCH_URL = "https://graph.microsoft.com/beta/copilot/microsoft.graph.search"
MIN_TOKEN_LIFETIME = 120  # Sekunden Restlaufzeit minimum


def _decode_jwt_exp(token: str) -> int:
    """Extrahiert exp-Timestamp aus JWT ohne externe Libs."""
    import base64

    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid JWT format")
    # Base64url decode
    payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
    payload = json.loads(base64.urlsafe_b64decode(payload_b64))
    return int(payload["exp"])


def _load_cached_token() -> str | None:
    """Laedt Token aus Cache wenn noch gueltig. Gibt None zurueck wenn abgelaufen."""
    if not CACHE_FILE.exists():
        return None
    try:
        with open(CACHE_FILE) as f:
            cache = json.load(f)
        if cache.get("exp", 0) > time.time() + MIN_TOKEN_LIFETIME:
            return cache["token"]
    except (json.JSONDecodeError, KeyError, OSError):
        pass
    return None


def _save_token(token: str, exp: int) -> None:
    """Speichert Token in Cache-Datei."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump({"token": token, "exp": exp}, f)


def cmd_check_token() -> None:
    """Prueft ob ein gueltiger Token im Cache liegt."""
    token = _load_cached_token()
    if token:
        with open(CACHE_FILE) as f:
            exp = json.load(f)["exp"]
        remaining = int(exp - time.time())
        print(f"VALID (expires in {remaining // 60}m {remaining % 60}s)")
    else:
        print("EXPIRED_OR_MISSING")
        sys.exit(2)


def cmd_cache_token(token: str, exp: str | None = None) -> None:
    """Speichert einen Token im Cache nach Validierung gegen Graph API."""
    if exp is None:
        exp_ts = _decode_jwt_exp(token)
    else:
        exp_ts = int(exp)
    # Validate token against Graph API before caching
    try:
        r = requests.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if r.status_code == 401:
            print("TOKEN_EXPIRED", file=sys.stderr)
            print("Token ist serverseitig ungueltig (401). Bitte neuen Token holen.", file=sys.stderr)
            sys.exit(2)
        if r.status_code != 200:
            print(f"WARNING: Token-Validierung ergab HTTP {r.status_code}", file=sys.stderr)
    except requests.RequestException as e:
        print(f"WARNING: Token-Validierung fehlgeschlagen: {e}", file=sys.stderr)
    _save_token(token, exp_ts)
    remaining = int(exp_ts - time.time())
    print(f"Token cached (expires in {remaining // 60}m {remaining % 60}s)")


def cmd_search(query: str, token: str | None = None) -> None:
    """Fuehrt Copilot Search aus. Gibt Exit-Code 2 bei abgelaufenem Token."""
    # Token bestimmen
    if token:
        # Direkt uebergeben → auch cachen
        try:
            exp = _decode_jwt_exp(token)
            _save_token(token, exp)
        except ValueError:
            pass
    else:
        token = _load_cached_token()
        if not token:
            print("TOKEN_EXPIRED", file=sys.stderr)
            print("Kein gueltiger Token vorhanden. Bitte Token via Playwright NAA holen.", file=sys.stderr)
            sys.exit(2)

    # Search ausfuehren
    try:
        r = requests.post(
            SEARCH_URL,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"query": query},
            timeout=20,
        )
    except requests.RequestException as e:
        print(f"ERROR: Request failed: {e}", file=sys.stderr)
        sys.exit(1)

    if r.status_code == 401:
        # Token ungueltig → Cache loeschen
        if CACHE_FILE.exists():
            CACHE_FILE.unlink()
        print("TOKEN_EXPIRED", file=sys.stderr)
        sys.exit(2)

    if r.status_code != 200:
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        msg = data.get("error", {}).get("message", r.text[:200])
        print(f"ERROR {r.status_code}: {msg}", file=sys.stderr)
        sys.exit(1)

    data = r.json()
    hits = data.get("searchHits", [])

    # Ergebnisse formatieren
    print(f"### Copilot Search: \"{query}\"\n")
    print(f"**{len(hits)} Treffer**\n")

    if not hits:
        print("Keine Ergebnisse gefunden.")
        return

    print("| # | Typ | Dokument | Vorschau |")
    print("|---|-----|----------|----------|")

    for i, hit in enumerate(hits, 1):
        url = hit.get("webUrl", "")
        res_type = hit.get("resourceType", "?")
        preview = (hit.get("preview") or "").replace("<c0>", "**").replace("</c0>", "**")

        # Dateiname aus URL extrahieren
        name = url.split("/")[-1].replace("%20", " ") if url else "?"
        # Auf 80 Zeichen kuerzen
        if len(name) > 80:
            name = name[:77] + "..."
        if len(preview) > 120:
            preview = preview[:117] + "..."

        print(f"| {i} | {res_type} | [{name}]({url}) | {preview} |")

    print()


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "search":
        if len(sys.argv) < 3:
            print("Usage: python copilot_search.py search \"Suchbegriff\" [--token TOKEN]")
            sys.exit(1)
        query = sys.argv[2]
        token = None
        if "--token" in sys.argv:
            idx = sys.argv.index("--token")
            if idx + 1 < len(sys.argv):
                token = sys.argv[idx + 1]
        cmd_search(query, token)

    elif cmd == "cache-token":
        if len(sys.argv) < 3:
            print("Usage: python copilot_search.py cache-token TOKEN [EXP_TIMESTAMP]")
            sys.exit(1)
        token = sys.argv[2]
        exp = sys.argv[3] if len(sys.argv) > 3 else None
        cmd_cache_token(token, exp)

    elif cmd == "check-token":
        cmd_check_token()

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
