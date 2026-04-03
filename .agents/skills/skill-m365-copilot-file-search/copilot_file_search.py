"""M365 Copilot Search via Graph Beta API.

Usage:
    python .agents/skills/skill-m365-copilot-file-search/copilot_file_search.py search "Suchbegriff"
    python .agents/skills/skill-m365-copilot-file-search/copilot_file_search.py search "Suchbegriff" --force
    python .agents/skills/skill-m365-copilot-file-search/copilot_file_search.py search "Suchbegriff" --token TOKEN
    python .agents/skills/skill-m365-copilot-file-search/copilot_file_search.py cache-token TOKEN [EXP_TIMESTAMP]
    python .agents/skills/skill-m365-copilot-file-search/copilot_file_search.py check-token

Behavior:
    - search: Ensures a valid Graph token automatically via m365_copilot_graph_token.py.
    - search --force: Ignores the cache and fetches a fresh token via MCP/NAA first.
    - cache-token: Debug helper for manual cache writes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import unquote

import requests

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")


def _discover_project_root(start_dir: Path) -> Path:
    for candidate in (start_dir, *start_dir.parents):
        if (candidate / ".vscode" / "mcp.json").exists():
            return candidate
    raise RuntimeError(
        f"Workspace-Root mit .vscode/mcp.json konnte ab {start_dir} nicht gefunden werden."
    )


PROJECT_ROOT = _discover_project_root(Path(__file__).resolve().parent)
CACHE_FILE = PROJECT_ROOT / "userdata" / "tmp" / ".graph_token_cache.json"
RESOLVER_SCRIPT = PROJECT_ROOT / "scripts" / "m365_copilot_graph_token.py"
SEARCH_URL = "https://graph.microsoft.com/beta/copilot/search"
MIN_TOKEN_LIFETIME = 120


def _decode_jwt_exp(token: str) -> int:
    import base64

    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid JWT format")
    payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
    payload = json.loads(base64.urlsafe_b64decode(payload_b64))
    return int(payload["exp"])


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


def _save_token(token: str, exp: int, source: str = "manual-debug") -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(
        json.dumps({"token": token, "exp": exp, "source": source}, ensure_ascii=False),
        encoding="utf-8",
    )


def _delete_cache() -> None:
    try:
        CACHE_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def _run_resolver(force: bool = False) -> None:
    args = [sys.executable, str(RESOLVER_SCRIPT), "ensure"]
    if force:
        args.append("--force")

    result = subprocess.run(
        args,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode == 0:
        return

    if result.stdout.strip():
        print(result.stdout.strip(), file=sys.stderr)
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    sys.exit(result.returncode)


def cmd_check_token() -> None:
    token = _load_cached_token()
    if token:
        raw = CACHE_FILE.read_text("utf-8")
        if raw.startswith('"'):
            raw = json.loads(raw)
        exp = json.loads(raw)["exp"]
        remaining = int(exp - time.time())
        print(f"VALID (expires in {remaining // 60}m {remaining % 60}s)")
    else:
        print("EXPIRED_OR_MISSING")
        sys.exit(2)


def cmd_cache_token(token: str, exp: str | None = None) -> None:
    if exp is None:
        exp_ts = _decode_jwt_exp(token)
    else:
        exp_ts = int(exp)
    try:
        response = requests.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if response.status_code == 401:
            print("TOKEN_EXPIRED", file=sys.stderr)
            print("Token ist serverseitig ungueltig (401). Bitte neuen Token holen.", file=sys.stderr)
            sys.exit(2)
        if response.status_code != 200:
            print(f"ERROR: Token-Validierung ergab HTTP {response.status_code}", file=sys.stderr)
            sys.exit(1)
    except requests.RequestException as exc:
        print(f"ERROR: Token-Validierung fehlgeschlagen: {exc}", file=sys.stderr)
        sys.exit(1)

    _save_token(token, exp_ts)
    remaining = int(exp_ts - time.time())
    print(f"Token cached (expires in {remaining // 60}m {remaining % 60}s)")


def _execute_search_request(token: str, query: str) -> requests.Response:
    try:
        return requests.post(
            SEARCH_URL,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"query": query},
            timeout=20,
        )
    except requests.RequestException as exc:
        print(f"ERROR: Request failed: {exc}", file=sys.stderr)
        sys.exit(1)


def cmd_search(query: str, token: str | None = None, force: bool = False) -> None:
    exp_to_cache: int | None = None
    if token:
        try:
            exp_to_cache = _decode_jwt_exp(token)
        except ValueError:
            exp_to_cache = None
    else:
        _run_resolver(force=force)
        token = _load_cached_token()
        if not token:
            print("TOKEN_EXPIRED", file=sys.stderr)
            print("Kein gueltiger Token vorhanden. Resolver hat keinen Cache geschrieben.", file=sys.stderr)
            sys.exit(2)

    response = _execute_search_request(token, query)
    if response.status_code == 401:
        _delete_cache()
        print("TOKEN_EXPIRED", file=sys.stderr)
        print("Copilot Search hat den Token abgelehnt. Cache wurde geloescht.", file=sys.stderr)
        sys.exit(2)
    if response.status_code != 200:
        data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        msg = data.get("error", {}).get("message", response.text[:200])
        print(f"ERROR {response.status_code}: {msg}", file=sys.stderr)
        sys.exit(1)

    if exp_to_cache is not None:
        _save_token(token, exp_to_cache)

    data = response.json()
    hits = data.get("searchHits", [])

    print(f"### Copilot Search: \"{query}\"\n")
    print(f"**{len(hits)} Treffer**\n")
    if not hits:
        print("Keine Ergebnisse gefunden.")
        return

    print("| # | Typ | Dokument | Vorschau |")
    print("|---|-----|----------|----------|")
    for index, hit in enumerate(hits, 1):
        url = hit.get("webUrl", "")
        res_type = hit.get("resourceType", "?")
        preview = (hit.get("preview") or "").replace("<c0>", "**").replace("</c0>", "**")
        name = unquote(url.split("/")[-1]) if url else "?"
        if len(name) > 80:
            name = name[:77] + "..."
        if len(preview) > 120:
            preview = preview[:117] + "..."
        print(f"| {index} | {res_type} | [{name}]({url}) | {preview} |")
    print()


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    if command == "search":
        if len(sys.argv) < 3:
            print('Usage: python .agents/skills/skill-m365-copilot-file-search/copilot_file_search.py search "Suchbegriff" [--force] [--token TOKEN]')
            sys.exit(1)
        query = sys.argv[2]
        token = None
        force = "--force" in sys.argv
        if "--token" in sys.argv:
            idx = sys.argv.index("--token")
            if idx + 1 < len(sys.argv):
                token = sys.argv[idx + 1]
        cmd_search(query, token=token, force=force)
        return

    if command == "cache-token":
        if len(sys.argv) < 3:
            print("Usage: python .agents/skills/skill-m365-copilot-file-search/copilot_file_search.py cache-token TOKEN [EXP_TIMESTAMP]")
            sys.exit(1)
        token = sys.argv[2]
        exp = sys.argv[3] if len(sys.argv) > 3 else None
        cmd_cache_token(token, exp)
        return

    if command == "check-token":
        cmd_check_token()
        return

    print(f"Unknown command: {command}")
    print(__doc__)
    sys.exit(1)


if __name__ == "__main__":
    main()
