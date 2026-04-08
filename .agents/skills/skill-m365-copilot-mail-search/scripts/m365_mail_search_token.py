"""Mail-search token resolver based on Teams Web MSAL data.

Ziel:
- Teams-/Graph-Token komplett in Python aufloesen
- zuerst gueltigen Access-Token nutzen
- sonst vorhandenen Refresh-Token verwenden
- sonst Teams in Edge oeffnen und auf aktualisierte MSAL-Eintraege warten

Usage:
    python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search_token.py fetch
    python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search_token.py fetch --force
    python .agents/skills/skill-m365-copilot-mail-search/scripts/m365_mail_search_token.py check-token
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[4]
REPO_SCRIPTS_DIR = REPO_ROOT / "scripts"
for path in (SCRIPT_DIR, REPO_SCRIPTS_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from m365_copilot_graph_token import (
    McpError,
    McpStdioClient,
    McpToolError,
    TokenResolverError as BridgeTokenResolverError,
    _call_tool_with_retry,
    _close_matching_browser_tab,
    _ensure_required_tools,
    _load_playwright_server_config,
)

# Windows UTF-8
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

CACHE_FILE_TEAMS = REPO_ROOT / "userdata" / "tmp" / ".graph_token_cache_teams.json"
CLIENT_ID = "5e3ce6c0-2b1f-4285-8d4b-75ee78787346"
TEAMS_URL = "https://teams.microsoft.com/v2/"
GRAPH_ME_URL = "https://graph.microsoft.com/v1.0/me"
MIN_TOKEN_LIFETIME = 120
PLAYWRIGHT_WAIT_SECONDS = 5
EDGE_PATH_CANDIDATES = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
]


class TokenAcquisitionError(RuntimeError):
    """Fehler mit maschinenlesbarem Code fuer CLI und aufrufende Scripts."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class TokenRecord:
    credential_type: str
    secret: str
    target: str
    expires_on: int | None
    home_account_id: str
    file_path: Path


def _decode_jwt_payload(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid JWT format")
    payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
    return json.loads(base64.urlsafe_b64decode(payload_b64))


def _has_required_scope(token: str, required_scopes: tuple[str, ...]) -> bool:
    try:
        payload = _decode_jwt_payload(token)
    except ValueError:
        return False
    scope_set = {scope.lower() for scope in payload.get("scp", "").split()}
    return all(scope.lower() in scope_set for scope in required_scopes)


def _token_exp(token: str) -> int:
    return int(_decode_jwt_payload(token)["exp"])


def _load_cached_payload() -> dict[str, Any] | None:
    if not CACHE_FILE_TEAMS.exists():
        return None
    try:
        raw = CACHE_FILE_TEAMS.read_text("utf-8")
        if raw.startswith('"'):
            raw = json.loads(raw)
        data = json.loads(raw)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _candidate_from_cache_payload(
    data: dict[str, Any] | None,
    required_scopes: tuple[str, ...],
) -> tuple[str, int, str] | None:
    if not data:
        return None
    token = str(data.get("token", "")).strip()
    source = str(data.get("source", "teams-cache")).strip() or "teams-cache"
    try:
        exp = int(data["exp"])
    except (KeyError, TypeError, ValueError):
        return None
    if not token:
        return None
    if exp <= time.time() + MIN_TOKEN_LIFETIME:
        return None
    if not _has_required_scope(token, required_scopes):
        return None
    return token, exp, source


def _load_cached_token(required_scopes: tuple[str, ...]) -> tuple[str, int] | None:
    candidate = _candidate_from_cache_payload(_load_cached_payload(), required_scopes)
    if candidate is None:
        return None
    token, exp, _source = candidate
    return token, exp


def _ensure_cache_dir() -> None:
    CACHE_FILE_TEAMS.parent.mkdir(parents=True, exist_ok=True)


def _save_cached_token(token: str, exp: int, source: str) -> None:
    _ensure_cache_dir()
    CACHE_FILE_TEAMS.write_text(
        json.dumps({"token": token, "exp": exp, "source": source}),
        encoding="utf-8",
    )


def _restore_cached_file(raw: str | None) -> None:
    if raw is None:
        try:
            CACHE_FILE_TEAMS.unlink(missing_ok=True)
        except OSError:
            pass
        return
    _ensure_cache_dir()
    CACHE_FILE_TEAMS.write_text(raw, encoding="utf-8")


def _validate_graph_token(token: str) -> bool:
    try:
        response = requests.get(
            GRAPH_ME_URL,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
    except requests.RequestException as exc:
        raise TokenAcquisitionError(
            "TOKEN_VALIDATION_FAILED",
            f"Token-Validierung gegen /me fehlgeschlagen: {exc}",
        ) from exc
    return response.status_code != 401


def _bridge_cache_filename() -> str:
    return str(CACHE_FILE_TEAMS.relative_to(REPO_ROOT)).replace("\\", "/")


def _bridge_extract_token_js(required_scopes: tuple[str, ...]) -> str:
    required = json.dumps([scope.lower() for scope in required_scopes], ensure_ascii=False)
    return f"""
async () => {{
  const requiredScopes = {required};
  const tokenKeysRaw = localStorage.getItem('msal.token.keys.{CLIENT_ID}');
  if (!tokenKeysRaw) {{
    return JSON.stringify({{
      error: 'NO_MSAL_TOKEN_KEYS',
      message: 'Keine MSAL-Token-Keys fuer den Teams Web Client gefunden.'
    }});
  }}

  let keys;
  try {{
    keys = JSON.parse(tokenKeysRaw);
  }} catch (_err) {{
    return JSON.stringify({{
      error: 'INVALID_MSAL_TOKEN_KEYS',
      message: 'MSAL-Token-Keys konnten nicht geparst werden.'
    }});
  }}

  let best = null;
  for (const atKey of (keys.accessToken || [])) {{
    const atRaw = localStorage.getItem(atKey);
    if (!atRaw) continue;

    let atData;
    try {{
      atData = JSON.parse(atRaw);
    }} catch (_err) {{
      continue;
    }}
    if (!atData.target || !String(atData.target).toLowerCase().includes('graph.microsoft.com')) {{
      continue;
    }}

    const token = String(atData.secret || '');
    const parts = token.split('.');
    if (parts.length !== 3) continue;

    let payload;
    try {{
      payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')));
    }} catch (_err) {{
      continue;
    }}

    const scopeSet = new Set(
      String(payload.scp || '')
        .toLowerCase()
        .split(/\\s+/)
        .filter(Boolean)
    );
    if (!requiredScopes.every(scope => scopeSet.has(scope))) {{
      continue;
    }}

    const exp = Number(payload.exp || 0);
    if (!Number.isFinite(exp)) {{
      continue;
    }}

    if (!best || exp > best.exp) {{
      best = {{
        token,
        exp,
        source: 'teams-bridge-cache-write',
        target: atData.target || null,
      }};
    }}
  }}

  if (!best) {{
    return JSON.stringify({{
      error: 'NO_GRAPH_TOKEN_FOUND',
      message: 'Kein Graph-Token mit den benoetigten Scopes im Teams-localStorage gefunden.'
    }});
  }}

  return JSON.stringify(best);
}}
""".strip()


def _resolve_via_playwright_bridge(
    required_scopes: tuple[str, ...],
    baseline_token: str | None,
    baseline_exp: int,
    require_fresher_than_baseline: bool = False,
    debug: bool = False,
) -> tuple[str, int, str] | None:
    previous_raw = None
    if CACHE_FILE_TEAMS.exists():
        try:
            previous_raw = CACHE_FILE_TEAMS.read_text("utf-8")
        except OSError:
            previous_raw = None

    success = False
    client: McpStdioClient | None = None
    try:
        _ensure_cache_dir()
        client = McpStdioClient(_load_playwright_server_config())
        client.start()
        _ensure_required_tools(client)
        _call_tool_with_retry(client, "browser_navigate", {"url": TEAMS_URL})
        _call_tool_with_retry(client, "browser_wait_for", {"time": PLAYWRIGHT_WAIT_SECONDS})
        _call_tool_with_retry(
            client,
            "browser_evaluate",
            {
                "function": _bridge_extract_token_js(required_scopes),
                "filename": _bridge_cache_filename(),
            },
        )

        data = _load_cached_payload()
        candidate = _candidate_from_cache_payload(data, required_scopes)
        if candidate is None:
            return None
        token, exp, source = candidate
        if require_fresher_than_baseline and not _is_fresher_token(candidate, baseline_token, baseline_exp):
            return None
        if not _validate_graph_token(token):
            return None
        _save_cached_token(token, exp, source)
        success = True
        return token, exp, source
    except (BridgeTokenResolverError, McpError, McpToolError, OSError, ValueError):
        return None
    finally:
        if client is not None:
            if not debug:
                _close_matching_browser_tab(client, ("teams.microsoft.com/v2/",))
            client.close()
        if not success:
            _restore_cached_file(previous_raw)


def _edge_user_data_dir() -> Path:
    local_app_data = Path(os.environ["LOCALAPPDATA"])
    return local_app_data / "Microsoft" / "Edge" / "User Data"


def _teams_leveldb_dir() -> Path:
    return _edge_user_data_dir() / "Default" / "Local Storage" / "leveldb"


def _candidate_leveldb_files() -> list[Path]:
    leveldb_dir = _teams_leveldb_dir()
    if not leveldb_dir.exists():
        return []
    files = []
    for path in leveldb_dir.iterdir():
        if path.suffix.lower() not in {".ldb", ".log"}:
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.stat().st_mtime, reverse=True)


def _extract_balanced_json(blob: bytes, start_index: int) -> bytes | None:
    depth = 0
    in_string = False
    escaped = False
    for index in range(start_index, len(blob)):
        value = blob[index]
        if in_string:
            if escaped:
                escaped = False
            elif value == 0x5C:
                escaped = True
            elif value == 0x22:
                in_string = False
            continue
        if value == 0x22:
            in_string = True
        elif value == 0x7B:
            depth += 1
        elif value == 0x7D:
            depth -= 1
            if depth == 0:
                return blob[start_index:index + 1]
    return None


def _iter_local_storage_objects() -> list[dict]:
    needle = b'{"homeAccountId":"'
    results: list[dict] = []
    seen: set[str] = set()
    for path in _candidate_leveldb_files():
        try:
            blob = path.read_bytes()
        except OSError:
            continue
        start = 0
        while True:
            index = blob.find(needle, start)
            if index < 0:
                break
            raw_json = _extract_balanced_json(blob, index)
            start = index + len(needle)
            if not raw_json:
                continue
            try:
                obj = json.loads(raw_json.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            marker = "|".join(
                [
                    obj.get("credentialType", ""),
                    obj.get("clientId", ""),
                    obj.get("target", "") or "",
                    obj.get("expiresOn", "") or "",
                    obj.get("secret", "")[:64],
                ]
            )
            if marker in seen:
                continue
            seen.add(marker)
            obj["_file_path"] = str(path)
            results.append(obj)
    return results


def _collect_token_records() -> list[TokenRecord]:
    records: list[TokenRecord] = []
    for obj in _iter_local_storage_objects():
        if obj.get("clientId") != CLIENT_ID:
            continue
        credential_type = obj.get("credentialType", "")
        if credential_type not in {"AccessToken", "RefreshToken"}:
            continue
        secret = obj.get("secret", "")
        if not secret:
            continue
        expires_on = None
        expires_raw = obj.get("expiresOn")
        if expires_raw:
            try:
                expires_on = int(expires_raw)
            except (TypeError, ValueError):
                expires_on = None
        records.append(
            TokenRecord(
                credential_type=credential_type,
                secret=secret,
                target=obj.get("target") or "",
                expires_on=expires_on,
                home_account_id=obj.get("homeAccountId") or "",
                file_path=Path(obj["_file_path"]),
            )
        )
    return records


def _tenant_id(records: list[TokenRecord]) -> str:
    for record in records:
        if "." in record.home_account_id:
            parts = record.home_account_id.split(".", 1)
            if len(parts) == 2 and parts[1]:
                return parts[1]
    raise TokenAcquisitionError(
        "NO_TENANT_ID",
        "Tenant-ID konnte aus dem Teams-Token-Cache nicht ermittelt werden.",
    )


def _best_graph_access_token(records: list[TokenRecord], required_scopes: tuple[str, ...]) -> tuple[str, int, str] | None:
    best: tuple[str, int, str] | None = None
    for record in records:
        if record.credential_type != "AccessToken":
            continue
        if "graph.microsoft.com" not in record.target.lower():
            continue
        try:
            exp = _token_exp(record.secret)
        except ValueError:
            continue
        if exp <= time.time() + MIN_TOKEN_LIFETIME:
            continue
        if not _has_required_scope(record.secret, required_scopes):
            continue
        source = f"teams-localstorage:{record.file_path.name}"
        if best is None or exp > best[1]:
            best = (record.secret, exp, source)
    return best


def _is_fresher_token(
    candidate: tuple[str, int, str] | None,
    baseline_token: str | None,
    baseline_exp: int,
) -> bool:
    if candidate is None:
        return False
    token, exp, _source = candidate
    if token != baseline_token:
        return True
    return exp > baseline_exp


def _best_refresh_token(records: list[TokenRecord]) -> TokenRecord | None:
    candidates: list[TokenRecord] = []
    now_ts = time.time()
    for record in records:
        if record.credential_type != "RefreshToken":
            continue
        if record.expires_on is not None and record.expires_on <= now_ts + MIN_TOKEN_LIFETIME:
            continue
        candidates.append(record)
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.expires_on or 0)


def _graph_scope_candidates(records: list[TokenRecord]) -> list[str]:
    scopes: list[str] = []
    seen: set[str] = set()
    for record in records:
        if record.credential_type != "AccessToken":
            continue
        if "graph.microsoft.com" not in record.target.lower():
            continue
        scope = record.target.strip()
        if not scope or scope in seen:
            continue
        seen.add(scope)
        scopes.append(scope)
    minimal = "https://graph.microsoft.com/Mail.Read offline_access openid profile"
    if minimal not in seen:
        scopes.append(minimal)
    return scopes


def _refresh_access_token(
    refresh_record: TokenRecord,
    tenant_id: str,
    requested_scope: str,
    required_scopes: tuple[str, ...],
) -> tuple[str, int, str] | None:
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    body = {
        "client_id": CLIENT_ID,
        "grant_type": "refresh_token",
        "refresh_token": refresh_record.secret,
        "scope": requested_scope,
    }
    try:
        response = requests.post(token_url, data=body, timeout=20)
    except requests.RequestException as exc:
        raise TokenAcquisitionError("TOKEN_REQUEST_FAILED", f"Token-Refresh fehlgeschlagen: {exc}") from exc

    payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    if response.status_code != 200:
        error = payload.get("error", "unknown_error")
        description = (payload.get("error_description") or "")[:400]
        if error == "invalid_grant":
            return None
        raise TokenAcquisitionError("TOKEN_REQUEST_FAILED", f"Token-Refresh fehlgeschlagen: {error} {description}".strip())

    access_token = payload.get("access_token", "")
    if not access_token:
        raise TokenAcquisitionError("TOKEN_REQUEST_FAILED", "Token-Refresh lieferte keinen access_token.")
    if not _has_required_scope(access_token, required_scopes):
        return None
    exp = _token_exp(access_token)
    return access_token, exp, "teams-refresh-token"


def _edge_executable() -> Path | None:
    for path in EDGE_PATH_CANDIDATES:
        if path.exists():
            return path
    return None


def _open_teams_in_edge() -> subprocess.Popen[Any]:
    edge_path = _edge_executable()
    if edge_path is None:
        raise TokenAcquisitionError(
            "EDGE_NOT_FOUND",
            "Microsoft Edge wurde nicht gefunden. Teams kann nicht automatisch geoeffnet werden.",
        )
    try:
        return subprocess.Popen(
            [str(edge_path), "--new-window", "--profile-directory=Default", TEAMS_URL],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise TokenAcquisitionError("EDGE_START_FAILED", f"Teams konnte in Edge nicht gestartet werden: {exc}") from exc


def _close_started_teams_window(process: subprocess.Popen[Any] | None) -> None:
    """Schliesst das von diesem Script gestartete Edge-Fenster best effort."""
    if process is None:
        return
    try:
        if process.poll() is not None:
            return
        process.terminate()
        process.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        try:
            if process.poll() is None:
                process.kill()
        except OSError:
            pass


def fetch_graph_token(
    required_scopes: tuple[str, ...] = ("Mail.Read",),
    open_teams_if_needed: bool = True,
    wait_seconds: int = 25,
    poll_interval: int = 3,
    force_refresh: bool = False,
    debug: bool = False,
) -> tuple[str, int, str]:
    _ensure_cache_dir()
    cached = _load_cached_token(required_scopes)
    if cached is not None and not force_refresh:
        token, exp = cached
        return token, exp, "teams-cache"

    baseline_token: str | None = None
    baseline_exp = 0
    if cached is not None:
        baseline_token, baseline_exp = cached

    def _resolve_from_local_state(require_fresher_than_baseline: bool = False) -> tuple[str, int, str] | None:
        records = _collect_token_records()
        direct = _best_graph_access_token(records, required_scopes)
        if direct is not None and (
            not require_fresher_than_baseline or _is_fresher_token(direct, baseline_token, baseline_exp)
        ):
            return direct

        refresh_record = _best_refresh_token(records)
        if refresh_record is None:
            return None

        tenant_id = _tenant_id(records)
        for requested_scope in _graph_scope_candidates(records):
            refreshed = _refresh_access_token(refresh_record, tenant_id, requested_scope, required_scopes)
            if refreshed is not None and (
                not require_fresher_than_baseline or _is_fresher_token(refreshed, baseline_token, baseline_exp)
            ):
                return refreshed
        return None

    require_fresher = force_refresh and baseline_token is not None

    resolved = _resolve_via_playwright_bridge(
        required_scopes,
        baseline_token,
        baseline_exp,
        require_fresher_than_baseline=require_fresher,
        debug=debug,
    )
    if resolved is not None:
        token, exp, source = resolved
        _save_cached_token(token, exp, source)
        return token, exp, source

    resolved = _resolve_from_local_state(require_fresher_than_baseline=require_fresher)
    if resolved is not None:
        token, exp, source = resolved
        _save_cached_token(token, exp, source)
        return token, exp, source

    if not open_teams_if_needed:
        raise TokenAcquisitionError(
            "TOKEN_EXPIRED",
            "Kein gueltiger Teams-Graph-Token gefunden. Teams bitte neu oeffnen oder anmelden.",
        )

    started_process: subprocess.Popen[Any] | None = _open_teams_in_edge()
    try:
        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            time.sleep(poll_interval)
            resolved = _resolve_from_local_state(require_fresher_than_baseline=force_refresh)
            if resolved is None:
                continue
            token, exp, source = resolved
            _save_cached_token(token, exp, source)
            return token, exp, f"{source}+teams-reopen"
    finally:
        if not debug:
            _close_started_teams_window(started_process)

    if force_refresh:
        raise TokenAcquisitionError(
            "TOKEN_EXPIRED",
            "Kein neuer Teams-Graph-Token gefunden. Teams wurde neu geoeffnet, aber gegenueber dem Ausgangszustand wurde kein frischer Mail.Read-Token erzeugt. Bitte Teams einmal aktiv neu laden oder neu anmelden und das Script erneut starten.",
        )

    raise TokenAcquisitionError(
        "TOKEN_EXPIRED",
        "Kein gueltiger Teams-Graph-Token gefunden. Teams wurde geoeffnet, aber Access-/Refresh-Token wurden nicht aktualisiert. Bitte Teams einmal neu anmelden oder die Seite neu laden und das Script erneut starten.",
    )


def cmd_fetch(wait_seconds: int, force_refresh: bool = False, debug: bool = False) -> None:
    token, exp, source = fetch_graph_token(wait_seconds=wait_seconds, force_refresh=force_refresh, debug=debug)
    remaining = int(exp - time.time())
    print(f"VALID (expires in {remaining // 60}m {remaining % 60}s)")
    print(f"Source: {source}")
    print(f"Cache:  {CACHE_FILE_TEAMS}")
    print(f"Scopes: Mail.Read")
    print(f"Token length: {len(token)}")


def cmd_check_token() -> None:
    cached = _load_cached_token(("Mail.Read",))
    if cached is None:
        print("EXPIRED_OR_MISSING", file=sys.stderr)
        sys.exit(2)
    token, exp = cached
    payload = _decode_jwt_payload(token)
    remaining = int(exp - time.time())
    print(f"VALID (expires in {remaining // 60}m {remaining % 60}s)")
    print(f"Audience: {payload.get('aud')}")
    print(f"Scopes: {payload.get('scp', '')}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Mail-search token resolver")
    parser.add_argument("--wait-seconds", type=int, default=25, help="Wartezeit nach Edge-Start")
    sub = parser.add_subparsers(dest="command", required=True)
    p_fetch = sub.add_parser("fetch", help="Access-Token fuer Graph/Mail.Read sicherstellen")
    p_fetch.add_argument("--force", action="store_true", help="Cache ignorieren und Teams-Reopen fuer einen frischen Token erzwingen")
    p_fetch.add_argument("--debug", action="store_true", help="Browser-Fenster/Tabs nach dem Lauf offen lassen")
    sub.add_parser("check-token", help="Vorhandenen gecachten Token pruefen")
    args = parser.parse_args()

    try:
        if args.command == "fetch":
            cmd_fetch(args.wait_seconds, getattr(args, "force", False), getattr(args, "debug", False))
        elif args.command == "check-token":
            cmd_check_token()
    except TokenAcquisitionError as exc:
        print(exc.code, file=sys.stderr)
        print(str(exc), file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
