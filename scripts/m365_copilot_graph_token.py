"""M365 Copilot Graph token resolver via Playwright MCP + NAA.

Usage:
    python scripts/m365_copilot_graph_token.py ensure
    python scripts/m365_copilot_graph_token.py ensure --force
    python scripts/m365_copilot_graph_token.py check-token

Behavior:
    - ensure: Reuse a validated cached token when possible.
    - ensure --force: Ignore the cache and fetch a fresh token via NAA.
    - check-token: Only inspect the local cache.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
MCP_CONFIG = PROJECT_ROOT / ".vscode" / "mcp.json"
CACHE_FILE = PROJECT_ROOT / "userdata" / "tmp" / ".graph_token_cache.json"
M365_CHAT_URL = "https://m365.cloud.microsoft/chat"
GRAPH_ME_URL = "https://graph.microsoft.com/v1.0/me"
CLIENT_ID = "c0ab8ce9-e9a0-42e7-b064-33d422df41f1"
GRAPH_RESOURCE = "https://graph.microsoft.com"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"
MIN_TOKEN_LIFETIME = 120

REQUIRED_TOOLS = {
    "browser_navigate",
    "browser_wait_for",
    "browser_evaluate",
    "browser_close",
}

TRANSIENT_BRIDGE_ERROR_PATTERNS = (
    "Target page, context or browser has been closed",
    "No open pages available",
    "Cannot read properties of undefined",
    "MCP-Verbindung beendet",
)

GET_TOKEN_JS = f"""
async () => {{
  const nas = window.nestedAppAuthService;
  if (!nas) {{
    return JSON.stringify({{ error: 'NAA_NOT_READY', message: 'nestedAppAuthService ist nicht verfuegbar' }});
  }}

  const result = await nas.handleRequest({{
    method: 'GetToken',
    requestId: 'copilot-search-' + Date.now(),
    tokenParams: {{
      clientId: '{CLIENT_ID}',
      resource: '{GRAPH_RESOURCE}',
      scope: '{GRAPH_SCOPE}'
    }}
  }}, new URL(window.location.href));

  if (!result?.success || !result.token?.access_token) {{
    return JSON.stringify({{
      error: 'TOKEN_REQUEST_FAILED',
      message: 'GetToken lieferte keinen access_token',
      details: result?.error || null
    }});
  }}

  const token = result.token.access_token;
  const parts = token.split('.');
  if (parts.length !== 3) {{
    return JSON.stringify({{
      error: 'TOKEN_INVALID',
      message: 'Token ist kein gueltiges JWT'
    }});
  }}

  const payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')));
  return JSON.stringify({{
    success: true,
    token,
    exp: payload.exp,
    aud: payload.aud || null,
    scp: payload.scp || null,
    source: 'm365-copilot-naa'
  }});
}}
""".strip()


class TokenResolverError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class McpError(RuntimeError):
    """Base MCP error."""


class McpToolError(McpError):
    """Raised when a tool call fails."""


@dataclass
class PlaywrightServerConfig:
    command: str
    args: list[str]
    env: dict[str, str]
    cwd: Path


class McpStdioClient:
    """Minimal MCP stdio client for the Playwright bridge server."""

    def __init__(self, config: PlaywrightServerConfig):
        self.config = config
        self.proc: subprocess.Popen[bytes] | None = None
        self._request_id = 0
        self._stderr_lines: list[str] = []
        self._stderr_thread: threading.Thread | None = None

    def start(self) -> None:
        env = os.environ.copy()
        env.update(self.config.env)
        try:
            self.proc = subprocess.Popen(
                [self.config.command, *self.config.args],
                cwd=self.config.cwd,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as exc:
            raise McpError(
                f"Playwright MCP konnte nicht gestartet werden: {self.config.command}"
            ) from exc

        self._stderr_thread = threading.Thread(target=self._collect_stderr, daemon=True)
        self._stderr_thread.start()

        try:
            self.request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "m365-copilot-graph-token", "version": "1.0.0"},
                },
            )
            self.notify("notifications/initialized", {})
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        if not self.proc:
            return
        if self.proc.stdin:
            try:
                self.proc.stdin.close()
            except OSError:
                pass
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None

    def _collect_stderr(self) -> None:
        if not self.proc or not self.proc.stderr:
            return
        try:
            while True:
                line = self.proc.stderr.readline()
                if not line:
                    return
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    self._stderr_lines.append(text)
        except Exception:
            return

    def _send(self, payload: dict[str, Any]) -> None:
        if not self.proc or not self.proc.stdin:
            raise McpError("MCP-Prozess ist nicht gestartet.")
        body = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        self.proc.stdin.write(body)
        self.proc.stdin.flush()

    def _read_message(self) -> dict[str, Any]:
        if not self.proc or not self.proc.stdout:
            raise McpError("MCP-Prozess ist nicht gestartet.")
        body = self.proc.stdout.readline()
        if not body:
            stderr_tail = "\n".join(self._stderr_lines[-5:])
            raise McpError(f"MCP-Verbindung beendet.\n{stderr_tail}".strip())
        try:
            return json.loads(body.decode("utf-8").strip())
        except json.JSONDecodeError as exc:
            raise McpError(f"Ungueltige MCP-JSON-Antwort: {body[:200]!r}") from exc

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._request_id += 1
        request_id = self._request_id
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {},
        }
        self._send(payload)

        while True:
            message = self._read_message()
            if "method" in message and "id" in message and "result" not in message and "error" not in message:
                self._send(
                    {
                        "jsonrpc": "2.0",
                        "id": message["id"],
                        "error": {"code": -32601, "message": "Client method not supported"},
                    }
                )
                continue
            if "method" in message and "id" not in message:
                continue
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise McpError(str(message["error"]))
            return message.get("result", {})

    def list_tools(self) -> list[dict[str, Any]]:
        result = self.request("tools/list", {})
        tools = result.get("tools", [])
        if not isinstance(tools, list):
            raise McpError("Ungueltige tools/list Antwort.")
        return tools

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        result = self.request("tools/call", {"name": name, "arguments": arguments or {}})
        if result.get("isError"):
            raise McpToolError(_extract_text_content(result) or f"Tool-Fehler: {name}")
        return result


def _strip_json_comments(text: str) -> str:
    import re

    text = re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return text


def _load_jsonc(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TokenResolverError("MCP_CONFIG_MISSING", f"Konfigurationsdatei nicht lesbar: {path}") from exc
    try:
        return json.loads(_strip_json_comments(raw))
    except json.JSONDecodeError as exc:
        raise TokenResolverError(
            "MCP_CONFIG_INVALID",
            f"Ungueltige JSONC-Konfiguration in {path}: {exc}",
        ) from exc


def _resolve_workspace_tokens(value: str) -> str:
    return value.replace("${workspaceFolder}", str(PROJECT_ROOT))


def _unwrap_evaluate_output(raw: str) -> str:
    if raw.startswith('"'):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            pass
    return raw


def _extract_text_content(result: dict[str, Any]) -> str:
    content = result.get("content", [])
    lines: list[str] = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            lines.append(str(item.get("text", "")))
    return "\n".join(line for line in lines if line).strip()


def _extract_playwright_result_text(text: str) -> str:
    import re

    match = re.search(r"### Result\s*(.*?)\s*(?:\n### |\Z)", text, flags=re.DOTALL)
    if match:
        text = match.group(1).strip()
    return _unwrap_evaluate_output(text.strip())


def _load_playwright_server_config() -> PlaywrightServerConfig:
    if not MCP_CONFIG.exists():
        raise TokenResolverError("MCP_CONFIG_MISSING", f"Playwright MCP Konfiguration fehlt: {MCP_CONFIG}")

    config = _load_jsonc(MCP_CONFIG)
    servers = config.get("servers", {})
    playwright = servers.get("playwright")
    if not isinstance(playwright, dict):
        raise TokenResolverError("PLAYWRIGHT_SERVER_MISSING", "Server 'playwright' fehlt in .vscode/mcp.json")

    command = str(playwright.get("command", "")).strip()
    args = [str(_resolve_workspace_tokens(arg)) for arg in playwright.get("args", [])]
    env = {
        key: _resolve_workspace_tokens(str(value))
        for key, value in (playwright.get("env") or {}).items()
    }

    if not command:
        raise TokenResolverError("PLAYWRIGHT_SERVER_MISSING", "Playwright MCP command fehlt in .vscode/mcp.json")
    if sys.platform == "win32" and Path(command).suffix.lower() != ".cmd":
        command = shutil.which(f"{command}.cmd") or shutil.which(command) or command
    if "PLAYWRIGHT_MCP_EXTENSION_TOKEN" not in env and not os.environ.get("PLAYWRIGHT_MCP_EXTENSION_TOKEN"):
        raise TokenResolverError(
            "PLAYWRIGHT_TOKEN_MISSING",
            "PLAYWRIGHT_MCP_EXTENSION_TOKEN fehlt fuer den Bridge Mode.",
        )

    return PlaywrightServerConfig(command=command, args=args, env=env, cwd=PROJECT_ROOT)


def _ensure_required_tools(client: McpStdioClient) -> None:
    names = sorted(str(tool.get("name", "")) for tool in client.list_tools())
    missing = sorted(REQUIRED_TOOLS - set(names))
    if missing:
        raise TokenResolverError(
            "PLAYWRIGHT_TOOLS_MISSING",
            f"Playwright MCP unvollstaendig. Fehlende Tools: {', '.join(missing)}",
        )


def _parse_json_text(raw: str, context: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TokenResolverError(
            "TOKEN_REQUEST_FAILED",
            f"Ungueltige JSON-Antwort bei {context}: {raw[:400]}",
        ) from exc
    if not isinstance(data, dict):
        raise TokenResolverError(
            "TOKEN_REQUEST_FAILED",
            f"Unerwartete Antwort bei {context}: {type(data)!r}",
        )
    return data


def _call_tool_with_retry(
    client: McpStdioClient,
    name: str,
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        return client.call_tool(name, arguments)
    except McpToolError as exc:
        if any(pattern in str(exc) for pattern in TRANSIENT_BRIDGE_ERROR_PATTERNS):
            try:
                client.call_tool("browser_close", {})
            except Exception:
                pass
            return client.call_tool(name, arguments)
        raise


def _tool_text_with_retry(
    client: McpStdioClient,
    name: str,
    arguments: dict[str, Any] | None = None,
) -> str:
    text = _extract_text_content(_call_tool_with_retry(client, name, arguments))
    return _extract_playwright_result_text(text)


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid JWT format")
    payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
    return json.loads(base64.urlsafe_b64decode(payload_b64))


def _decode_jwt_exp(token: str) -> int:
    return int(_decode_jwt_payload(token)["exp"])


def _load_cache() -> dict[str, Any] | None:
    if not CACHE_FILE.exists():
        return None
    try:
        raw = CACHE_FILE.read_text("utf-8")
        if raw.startswith('"'):
            raw = json.loads(raw)
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _delete_cache() -> None:
    try:
        CACHE_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def _save_cache(token: str, exp: int, source: str) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(
        json.dumps({"token": token, "exp": exp, "source": source}, ensure_ascii=False),
        encoding="utf-8",
    )


def _validate_token(token: str) -> int | None:
    try:
        response = requests.get(
            GRAPH_ME_URL,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
    except requests.RequestException as exc:
        raise TokenResolverError(
            "TOKEN_VALIDATION_FAILED",
            f"Token-Validierung gegen /me fehlgeschlagen: {exc}",
        ) from exc

    if response.status_code == 200:
        return _decode_jwt_exp(token)
    if response.status_code == 401:
        return None

    body = response.text[:300]
    raise TokenResolverError(
        "TOKEN_INVALID",
        f"Token-Validierung ergab HTTP {response.status_code}: {body}",
    )


def _get_cached_token_if_valid() -> tuple[str, int, str] | None:
    cache = _load_cache()
    if not cache:
        return None
    token = str(cache.get("token", "")).strip()
    exp = int(cache.get("exp", 0) or 0)
    source = str(cache.get("source", "cache")).strip() or "cache"
    if not token or exp <= time.time() + MIN_TOKEN_LIFETIME:
        _delete_cache()
        return None

    validated_exp = _validate_token(token)
    if validated_exp is None or validated_exp <= time.time() + MIN_TOKEN_LIFETIME:
        _delete_cache()
        return None

    if validated_exp != exp:
        _save_cache(token, validated_exp, source)
        exp = validated_exp
    return token, exp, source


def _fetch_token_via_mcp() -> tuple[str, int, str]:
    config = _load_playwright_server_config()
    last_error: Exception | None = None

    for attempt in range(2):
        client = McpStdioClient(config)
        try:
            client.start()
            _ensure_required_tools(client)
            _call_tool_with_retry(client, "browser_navigate", {"url": M365_CHAT_URL})
            _call_tool_with_retry(client, "browser_wait_for", {"time": 3 if attempt == 0 else 5})
            raw = _tool_text_with_retry(client, "browser_evaluate", {"function": GET_TOKEN_JS})
            data = _parse_json_text(raw, "NAA token fetch")

            if data.get("error") == "NAA_NOT_READY":
                last_error = TokenResolverError("NAA_NOT_READY", str(data.get("message") or "NAA nicht bereit"))
                continue
            if data.get("error"):
                raise TokenResolverError(
                    str(data.get("error")),
                    str(data.get("message") or data.get("details") or "Token-Beschaffung fehlgeschlagen"),
                )

            token = str(data.get("token", "")).strip()
            if not token:
                raise TokenResolverError("TOKEN_REQUEST_FAILED", "NAA lieferte keinen access_token.")

            validated_exp = _validate_token(token)
            if validated_exp is None:
                raise TokenResolverError("TOKEN_INVALID", "NAA lieferte einen serverseitig ungueltigen Token.")

            source = str(data.get("source", "m365-copilot-naa")).strip() or "m365-copilot-naa"
            _save_cache(token, validated_exp, source)
            try:
                _call_tool_with_retry(client, "browser_close", {})
            except Exception:
                pass
            return token, validated_exp, source
        except (McpError, McpToolError, TokenResolverError, ValueError) as exc:
            last_error = exc
            if attempt == 0:
                continue
        finally:
            client.close()

    if isinstance(last_error, TokenResolverError):
        raise last_error
    if last_error is not None:
        raise TokenResolverError("TOKEN_REQUEST_FAILED", str(last_error))
    raise TokenResolverError("TOKEN_REQUEST_FAILED", "Unbekannter Fehler bei der Token-Beschaffung.")


def ensure_token(force: bool = False) -> tuple[str, int, str]:
    if force:
        _delete_cache()
    else:
        cached = _get_cached_token_if_valid()
        if cached is not None:
            return cached

    return _fetch_token_via_mcp()


def cmd_ensure(force: bool) -> None:
    token, exp, source = ensure_token(force=force)
    remaining = int(exp - time.time())
    print(f"VALID (expires in {remaining // 60}m {remaining % 60}s)")
    print(f"Source: {source}")
    print(f"Cache:  {CACHE_FILE}")
    print(f"Token length: {len(token)}")


def cmd_check_token() -> None:
    cache = _load_cache()
    if not cache:
        print("EXPIRED_OR_MISSING", file=sys.stderr)
        sys.exit(2)

    token = str(cache.get("token", "")).strip()
    exp = int(cache.get("exp", 0) or 0)
    if not token or exp <= time.time() + MIN_TOKEN_LIFETIME:
        print("EXPIRED_OR_MISSING", file=sys.stderr)
        sys.exit(2)

    remaining = int(exp - time.time())
    print(f"VALID (expires in {remaining // 60}m {remaining % 60}s)")
    print(f"Cache:  {CACHE_FILE}")


def main() -> None:
    parser = argparse.ArgumentParser(description="M365 Copilot Graph token resolver")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ensure = sub.add_parser("ensure", help="Graph-Token sicherstellen")
    p_ensure.add_argument("--force", action="store_true", help="Cache ignorieren und frischen Token holen")
    sub.add_parser("check-token", help="Cache-Status pruefen")

    args = parser.parse_args()

    try:
        if args.command == "ensure":
            cmd_ensure(getattr(args, "force", False))
        elif args.command == "check-token":
            cmd_check_token()
    except TokenResolverError as exc:
        print(exc.code, file=sys.stderr)
        print(str(exc), file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
