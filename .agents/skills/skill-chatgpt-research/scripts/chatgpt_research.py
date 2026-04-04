"""ChatGPT Research via Playwright MCP Bridge.

Bridge mode is mandatory. This script talks to the Playwright MCP server over
stdio/JSON-RPC, drives chatgpt.com through the browser extension session, and
stores the answer as Markdown.

Usage:
    python .agents/skills/skill-chatgpt-research/scripts/chatgpt_research.py doctor
    python .agents/skills/skill-chatgpt-research/scripts/chatgpt_research.py run --question "..." --thinking
    python .agents/skills/skill-chatgpt-research/scripts/chatgpt_research.py close
    python .agents/skills/skill-chatgpt-research/scripts/chatgpt_research.py convert INPUT_HTML --question "..."

Exit codes:
    0 = Erfolg
    1 = Allgemeiner Fehler
    2 = Bridge/MCP nicht verfuegbar oder unvollstaendig
    3 = ChatGPT nicht eingeloggt / Textbox nicht gefunden
    4 = Antwort-Timeout
    6 = HTML extrahiert, aber nicht sinnvoll konvertierbar
"""

from __future__ import annotations

import argparse
import contextlib
import html as html_mod
import json
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

# Windows UTF-8
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

EXIT_OK = 0
EXIT_GENERAL_ERROR = 1
EXIT_MCP_UNAVAILABLE = 2
EXIT_LOGIN_REQUIRED = 3
EXIT_RESPONSE_TIMEOUT = 4
EXIT_INVALID_HTML = 6

DEFAULT_CHAT_URL = "https://chatgpt.com/"
DEFAULT_TIMEOUT_SECONDS = 1800
DEFAULT_TIMEOUT_MINUTES = DEFAULT_TIMEOUT_SECONDS // 60
DEFAULT_POLL_INTERVAL_SECONDS = 3
CHATGPT_MIN_INTERVAL_SECONDS = 30
GATE_LOCK_PATH = PROJECT_ROOT / "userdata" / "tmp" / "chatgpt_rate_gate.lock"
GATE_STATE_PATH = PROJECT_ROOT / "userdata" / "tmp" / "chatgpt_rate_gate.json"
LOCK_ACQUIRE_TIMEOUT_SECONDS = 60.0
LOCK_POLL_INTERVAL_SECONDS = 0.1

REQUIRED_TOOLS = {
    "browser_navigate",
    "browser_wait_for",
    "browser_run_code",
    "browser_evaluate",
    "browser_close",
}

TRANSIENT_BRIDGE_ERROR_PATTERNS = (
    "Target page, context or browser has been closed",
    "No open pages available",
    "Cannot read properties of undefined (reading 'url')",
    "MCP-Verbindung beendet",
)

DOM_STATE_JS = r"""
() => {
  const textarea = document.querySelector('#prompt-textarea, textarea');
  const assistants = [...document.querySelectorAll('[data-message-author-role="assistant"]')];
  const lastAssistant = assistants.length ? assistants[assistants.length - 1] : null;
  const lastText = lastAssistant ? (lastAssistant.innerText || '').trim() : '';
  const buttons = [...document.querySelectorAll('button')];
  const buttonText = buttons
    .map((btn) => [btn.getAttribute('aria-label') || '', btn.innerText || ''].join(' ').trim())
    .join(' | ');
  const activeThinking = !!document.querySelector('button.__composer-pill-remove[aria-label*="Nachdenken"]')
    || buttons.some((btn) => (btn.innerText || '').includes('Entfernen') && (btn.innerText || '').includes('Nachdenken'));
  const stopHints = [
    'Generieren beenden',
    'Stop generating',
    'Stoppt die Antwort',
    'Antwort stoppen',
  ];
  const isGenerating = stopHints.some((hint) => buttonText.includes(hint));
  return JSON.stringify({
    url: location.href,
    title: document.title,
    hasTextbox: !!textarea,
    assistantCount: assistants.length,
    lastAssistantLength: lastText.length,
    lastAssistantPreview: lastText.slice(0, 200),
    thinkingActive: activeThinking,
    isGenerating,
  });
}
""".strip()

LAST_ASSISTANT_HTML_JS = r"""
async () => {
  const articles = document.querySelectorAll('[data-message-author-role="assistant"]');
  if (!articles.length) return JSON.stringify({error:'No assistant message'});
  const last = articles[articles.length - 1];
  const content = last.querySelector('.markdown,.prose,[class*="markdown"],[class*="prose"]');
  return (content || last).innerHTML;
}
""".strip()


# ---------------------------------------------------------------------------
# HTML to Markdown Converter
# ---------------------------------------------------------------------------

_CODE_BLOCKS: list[tuple[str, str]] = []


def _protect_code_blocks(html: str) -> str:
    """Extract <pre><code> blocks and replace with placeholders."""
    _CODE_BLOCKS.clear()

    def _replace(m: re.Match) -> str:
        lang_attr = m.group(1) or ""
        lang_match = re.search(r'class="[^"]*language-(\w+)', lang_attr)
        lang = lang_match.group(1) if lang_match else ""
        code = m.group(2)
        idx = len(_CODE_BLOCKS)
        _CODE_BLOCKS.append((lang, code))
        return f"\n__CODE_BLOCK_{idx}__\n"

    return re.sub(
        r"<pre[^>]*>\s*<code([^>]*)>(.*?)</code>\s*</pre>",
        _replace,
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )


def _restore_code_blocks(text: str) -> str:
    """Restore code block placeholders as fenced Markdown blocks."""
    for idx, (lang, code) in enumerate(_CODE_BLOCKS):
        code_clean = html_mod.unescape(re.sub(r"<[^>]+>", "", code)).strip()
        fence = f"\n```{lang}\n{code_clean}\n```\n"
        text = text.replace(f"__CODE_BLOCK_{idx}__", fence)
    return text


def _convert_tables(html: str) -> str:
    """Convert <table> to Markdown tables."""

    def _table_replace(m: re.Match) -> str:
        table_html = m.group(0)
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.DOTALL | re.IGNORECASE)
        if not rows:
            return ""
        md_rows = []
        for i, row in enumerate(rows):
            cells = re.findall(
                r"<t[hd][^>]*>(.*?)</t[hd]>", row, re.DOTALL | re.IGNORECASE
            )
            cells_text = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
            md_rows.append("| " + " | ".join(cells_text) + " |")
            if i == 0:
                md_rows.append("|" + "|".join("---" for _ in cells_text) + "|")
        return "\n" + "\n".join(md_rows) + "\n"

    return re.sub(r"<table[^>]*>.*?</table>", _table_replace, html, flags=re.DOTALL | re.IGNORECASE)


def _convert_lists(html: str) -> str:
    """Convert <ul>/<ol> with <li> to Markdown lists."""

    def _list_replace(m: re.Match) -> str:
        tag = m.group(1).lower()
        content = m.group(2)
        items = re.findall(r"<li[^>]*>(.*?)</li>", content, re.DOTALL | re.IGNORECASE)
        lines = []
        for i, item in enumerate(items):
            item_text = re.sub(r"<[^>]+>", "", item).strip()
            item_text = re.sub(r"\n\s*", " ", item_text)
            prefix = f"{i + 1}. " if tag == "ol" else "- "
            lines.append(f"{prefix}{item_text}")
        return "\n" + "\n".join(lines) + "\n"

    # Process nested lists from inside out
    prev = ""
    result = html
    while prev != result:
        prev = result
        result = re.sub(
            r"<(ul|ol)[^>]*>(.*?)</\1>",
            _list_replace,
            result,
            flags=re.DOTALL | re.IGNORECASE,
        )
    return result


def _html_to_markdown(html: str) -> str:
    """Convert ChatGPT response HTML to clean Markdown (no external deps)."""
    text = html

    # Pass 1: Protect code blocks
    text = _protect_code_blocks(text)

    # Pass 2: Block elements
    for level in range(6, 0, -1):
        prefix = "#" * level
        text = re.sub(
            rf"<h{level}[^>]*>(.*?)</h{level}>",
            rf"\n{prefix} \1\n",
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )

    # Blockquotes
    def _bq_replace(m: re.Match) -> str:
        inner = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        lines = inner.split("\n")
        return "\n" + "\n".join(f"> {line}" for line in lines) + "\n"

    text = re.sub(
        r"<blockquote[^>]*>(.*?)</blockquote>",
        _bq_replace,
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Tables
    text = _convert_tables(text)

    # Lists
    text = _convert_lists(text)

    # Paragraphs
    text = re.sub(r"<p[^>]*>(.*?)</p>", r"\1\n\n", text, flags=re.DOTALL | re.IGNORECASE)

    # Pass 3: Inline elements
    text = re.sub(r"<strong[^>]*>(.*?)</strong>", r"**\1**", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<b[^>]*>(.*?)</b>", r"**\1**", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<em[^>]*>(.*?)</em>", r"*\1*", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<i[^>]*>(.*?)</i>", r"*\1*", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<code[^>]*>(.*?)</code>", r"`\1`", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<a[^>]+href="([^"]*)"[^>]*>(.*?)</a>', r"[\2](\1)", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)

    # Pass 4: Strip remaining tags, decode entities
    text = re.sub(r"<[^>]+>", "", text)
    text = html_mod.unescape(text)

    # Pass 5: Restore code blocks, clean whitespace
    text = _restore_code_blocks(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(text: str, max_len: int = 50) -> str:
    """Generate a filesystem-safe slug from text."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "-", text.lower())
    text = text.strip("-")
    if len(text) > max_len:
        text = text[:max_len].rsplit("-", 1)[0]
    return text or "chatgpt-response"


def _strip_json_comments(text: str) -> str:
    text = re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return text


def _load_jsonc(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"Konfigurationsdatei nicht lesbar: {path}") from exc
    try:
        return json.loads(_strip_json_comments(raw))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Ungueltige JSONC-Konfiguration in {path}: {exc}") from exc


def _resolve_workspace_tokens(value: str) -> str:
    return value.replace("${workspaceFolder}", str(PROJECT_ROOT))


def _ensure_path(path_value: str | Path) -> Path:
    path = Path(path_value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _unwrap_evaluate_output(raw: str) -> str:
    """browser_evaluate filename saves as double-quoted JSON string."""
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
    """Unwrap Playwright MCP markdown reports to the actual tool result payload."""
    match = re.search(r"### Result\s*(.*?)\s*(?:\n### |\Z)", text, flags=re.DOTALL)
    if match:
        text = match.group(1).strip()
    return _unwrap_evaluate_output(text.strip())


def _read_html_from_file(path_value: str | Path) -> str:
    path = _ensure_path(path_value)
    if not path.exists():
        raise RuntimeError(f"HTML-Datei nicht gefunden: {path}")
    raw = path.read_text(encoding="utf-8").strip()
    html = _unwrap_evaluate_output(raw)
    if html.startswith("{"):
        try:
            data = json.loads(html)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict) and "error" in data:
            raise RuntimeError(str(data["error"]))
    if not html or len(html) < 20:
        raise RuntimeError("HTML-Datei ist leer oder zu kurz.")
    return html


def _build_markdown_document(question: str, html: str, thinking: bool) -> str:
    markdown = _html_to_markdown(html)
    if not markdown or len(markdown) < 20:
        raise RuntimeError("Konvertierte Markdown-Antwort ist leer oder zu kurz.")

    date_display = datetime.now().strftime("%Y-%m-%d")
    header = f"# {question}\n\n> Quelle: ChatGPT"
    if thinking:
        header += " (Laengeres Nachdenken)"
    header += f", abgerufen am {date_display}\n\n"
    return header + markdown


def _default_output_path(question: str) -> Path:
    slug = _slugify(question)
    date_str = datetime.now().strftime("%Y%m%d")
    return PROJECT_ROOT / "tmp" / f"{date_str}_chatgpt_{slug}.md"


def _html_output_path(markdown_path: str | Path) -> Path:
    return _ensure_path(markdown_path).with_suffix(".html")


def _write_markdown_from_html(
    input_file: str | Path,
    question: str,
    output: str | Path | None,
    thinking: bool,
) -> tuple[Path, str]:
    html = _read_html_from_file(input_file)
    content = _build_markdown_document(question, html, thinking)
    out_path = _ensure_path(output) if output else _default_output_path(question)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    return out_path, content


def _rel_for_display(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _success_meta(raw_html_out: Path, out_path: Path, content: str) -> dict[str, Any]:
    return {
        "output_md": _rel_for_display(out_path),
        "output_chars": len(content),
        "raw_html_out": _rel_for_display(raw_html_out),
    }


def _error_meta(raw_html_out: Path, error: str) -> dict[str, Any]:
    return {
        "raw_html_out": _rel_for_display(raw_html_out),
        "error": error,
    }


# ---------------------------------------------------------------------------
# Global prompt gate
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def _exclusive_file_lock(
    lock_path: Path,
    *,
    timeout_seconds: float = LOCK_ACQUIRE_TIMEOUT_SECONDS,
    poll_interval_seconds: float = LOCK_POLL_INTERVAL_SECONDS,
):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = lock_path.open("a+b")
    acquired = False
    deadline = time.time() + timeout_seconds

    try:
        while time.time() < deadline:
            try:
                fh.seek(0)
                if os.name == "nt":
                    import msvcrt

                    try:
                        fh.write(b"\0")
                        fh.flush()
                    except OSError:
                        pass
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except OSError:
                time.sleep(poll_interval_seconds)

        if not acquired:
            raise RuntimeError(f"Konnte globalen ChatGPT-Lock nicht rechtzeitig erhalten: {lock_path}")

        yield fh
    finally:
        try:
            if acquired:
                fh.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()


def _load_gate_state(state_path: Path = GATE_STATE_PATH) -> dict[str, Any]:
    if not state_path.exists():
        return {"next_allowed_at": 0.0}
    try:
        raw = state_path.read_text(encoding="utf-8").strip()
        if not raw:
            return {"next_allowed_at": 0.0}
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {"next_allowed_at": 0.0}

    next_allowed_at = data.get("next_allowed_at", 0.0)
    try:
        next_allowed = float(next_allowed_at)
    except (TypeError, ValueError):
        next_allowed = 0.0
    return {"next_allowed_at": max(0.0, next_allowed)}


def _save_gate_state(state: dict[str, Any], state_path: Path = GATE_STATE_PATH) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"next_allowed_at": float(state.get("next_allowed_at", 0.0))}
    state_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _reserve_global_chatgpt_slot(
    *,
    now_ts: float | None = None,
    interval_seconds: float = CHATGPT_MIN_INTERVAL_SECONDS,
    lock_path: Path = GATE_LOCK_PATH,
    state_path: Path = GATE_STATE_PATH,
) -> dict[str, Any]:
    now = float(time.time() if now_ts is None else now_ts)
    with _exclusive_file_lock(lock_path):
        state = _load_gate_state(state_path)
        next_allowed_at = max(now, float(state.get("next_allowed_at", 0.0)))
        slot_at = next_allowed_at
        new_next_allowed_at = slot_at + interval_seconds
        _save_gate_state({"next_allowed_at": new_next_allowed_at}, state_path)

    wait_seconds = max(0.0, slot_at - now)
    queue_depth_hint = int(math.ceil(wait_seconds / interval_seconds)) if wait_seconds > 0 else 0
    return {
        "reserved_at": now,
        "slot_at": slot_at,
        "next_allowed_at": new_next_allowed_at,
        "wait_seconds": wait_seconds,
        "queue_depth_hint": queue_depth_hint,
        "slot_at_iso": datetime.fromtimestamp(slot_at).isoformat(),
    }


def _apply_global_prompt_gate() -> None:
    reservation = _reserve_global_chatgpt_slot()
    wait_seconds = float(reservation["wait_seconds"])
    if wait_seconds > 0:
        print(
            f"Globales ChatGPT-Limit aktiv, warte {wait_seconds:.1f}s bis zum naechsten Slot",
            file=sys.stderr,
        )
        time.sleep(wait_seconds)


# ---------------------------------------------------------------------------
# MCP client
# ---------------------------------------------------------------------------

@dataclass
class PlaywrightServerConfig:
    command: str
    args: list[str]
    env: dict[str, str]
    cwd: Path


@dataclass
class RunOptions:
    question: str
    output: Path | None
    thinking: bool
    chat_url: str
    timeout_seconds: int
    poll_interval_seconds: int
    reuse_chat: bool


class McpError(RuntimeError):
    """Base MCP error."""


class McpToolError(McpError):
    """Raised when a tool call fails."""


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
                    "clientInfo": {"name": "chatgpt-research", "version": "1.0.0"},
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


def _load_playwright_server_config() -> PlaywrightServerConfig:
    if not MCP_CONFIG.exists():
        raise McpError(f"Playwright MCP Konfiguration fehlt: {MCP_CONFIG}")

    config = _load_jsonc(MCP_CONFIG)
    servers = config.get("servers", {})
    playwright = servers.get("playwright")
    if not isinstance(playwright, dict):
        raise McpError("Server 'playwright' fehlt in .vscode/mcp.json")

    command = str(playwright.get("command", "")).strip()
    args = [str(_resolve_workspace_tokens(arg)) for arg in playwright.get("args", [])]
    env = {
        key: _resolve_workspace_tokens(str(value))
        for key, value in (playwright.get("env") or {}).items()
    }

    if not command:
        raise McpError("Playwright MCP command fehlt in .vscode/mcp.json")
    if sys.platform == "win32" and Path(command).suffix.lower() != ".cmd":
        command = shutil.which(f"{command}.cmd") or shutil.which(command) or command
    if "PLAYWRIGHT_MCP_EXTENSION_TOKEN" not in env and not os.environ.get("PLAYWRIGHT_MCP_EXTENSION_TOKEN"):
        raise McpError("PLAYWRIGHT_MCP_EXTENSION_TOKEN fehlt fuer den Bridge Mode.")

    return PlaywrightServerConfig(command=command, args=args, env=env, cwd=PROJECT_ROOT)


def _parse_json_text(raw: str, context: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Ungueltige JSON-Antwort bei {context}: {raw[:400]}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"Unerwartete Antwort bei {context}: {type(data)!r}")
    return data


def _call_tool_with_retry(
    client: McpStdioClient,
    name: str,
    arguments: dict[str, Any] | None = None,
    *,
    allow_reset: bool = True,
) -> dict[str, Any]:
    try:
        return client.call_tool(name, arguments)
    except McpToolError as exc:
        if allow_reset and "Target page, context or browser has been closed" in str(exc):
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
    *,
    allow_reset: bool = True,
) -> str:
    text = _extract_text_content(
        _call_tool_with_retry(client, name, arguments, allow_reset=allow_reset)
    )
    return _extract_playwright_result_text(text)


def _is_transient_bridge_error(exc: Exception) -> bool:
    message = str(exc)
    return any(pattern in message for pattern in TRANSIENT_BRIDGE_ERROR_PATTERNS)


def _start_client_and_fetch_state(
    config: PlaywrightServerConfig,
    chat_url: str,
) -> tuple[McpStdioClient, list[str], dict[str, Any], int]:
    last_exc: Exception | None = None
    for attempt in range(2):
        client = McpStdioClient(config)
        try:
            client.start()
            tools = _ensure_required_tools(client)
            state = _navigate_and_check(client, chat_url)
            return client, tools, state, attempt
        except Exception as exc:
            client.close()
            last_exc = exc
            if attempt == 0 and _is_transient_bridge_error(exc):
                continue
            raise

    assert last_exc is not None
    raise last_exc


# ---------------------------------------------------------------------------
# Browser workflow
# ---------------------------------------------------------------------------

def _js_return(payload: str) -> str:
    return f"async (page) => {payload}"


def _navigate_and_check(client: McpStdioClient, chat_url: str) -> dict[str, Any]:
    _call_tool_with_retry(client, "browser_navigate", {"url": chat_url})
    _call_tool_with_retry(client, "browser_wait_for", {"time": 5})
    raw = _tool_text_with_retry(client, "browser_evaluate", {"function": DOM_STATE_JS})
    return _parse_json_text(raw, "DOM state")


def _ensure_required_tools(client: McpStdioClient) -> list[str]:
    names = sorted(str(tool.get("name", "")) for tool in client.list_tools())
    missing = sorted(REQUIRED_TOOLS - set(names))
    if missing:
        raise McpError(f"Playwright MCP unvollstaendig. Fehlende Tools: {', '.join(missing)}")
    return names


def _set_thinking_mode(client: McpStdioClient) -> bool:
    code = _js_return(
        r"""
{
  const trySelectors = async () => {
    const buttons = [
      page.locator('button.__composer-pill', { hasText: 'Längeres Nachdenken' }),
      page.getByRole('button', { name: /Längeres Nachdenken/i }),
      page.locator('button').filter({ hasText: 'Längeres Nachdenken' }),
    ];
    for (const button of buttons) {
      if (await button.count() > 0) {
        await button.first().click();
        return {clicked: true};
      }
    }
    return {clicked: false};
  };
  return JSON.stringify(await trySelectors());
}
"""
    )
    raw = _tool_text_with_retry(client, "browser_run_code", {"code": code})
    data = _parse_json_text(raw, "thinking toggle")
    _call_tool_with_retry(client, "browser_wait_for", {"time": 1})
    state = _parse_json_text(
        _tool_text_with_retry(client, "browser_evaluate", {"function": DOM_STATE_JS}),
        "DOM state after thinking toggle",
    )
    return bool(data.get("clicked")) and bool(state.get("thinkingActive"))


def _open_new_chat(client: McpStdioClient, chat_url: str) -> None:
    _call_tool_with_retry(client, "browser_navigate", {"url": chat_url})
    _call_tool_with_retry(client, "browser_wait_for", {"time": 2})


def _submit_prompt(client: McpStdioClient, prompt: str) -> None:
    code = _js_return(
        "{"
        f"const prompt = {json.dumps(prompt)};"
        r"""
  const textarea = page.locator('#prompt-textarea, textarea').last();
  if (await textarea.count() === 0) {
    return JSON.stringify({error: 'TEXTBOX_NOT_FOUND'});
  }
  await textarea.click();
  await textarea.fill(prompt);
  await textarea.press('Enter');
  return JSON.stringify({submitted: true});
}
"""
    )
    raw = _tool_text_with_retry(client, "browser_run_code", {"code": code})
    data = _parse_json_text(raw, "prompt submit")
    if data.get("error") == "TEXTBOX_NOT_FOUND":
        raise RuntimeError("ChatGPT-Textbox wurde nicht gefunden.")


def _poll_for_completed_message(
    client: McpStdioClient,
    *,
    baseline_count: int,
    timeout_seconds: int,
    poll_interval_seconds: int,
) -> dict[str, Any]:
    started_at = time.time()
    deadline = started_at + timeout_seconds
    previous_length = -1
    stable_rounds = 0
    next_status_at = started_at + 60

    while time.time() < deadline:
        raw = _tool_text_with_retry(client, "browser_evaluate", {"function": DOM_STATE_JS})
        state = _parse_json_text(raw, "poll DOM state")

        assistant_count = int(state.get("assistantCount", 0))
        last_len = int(state.get("lastAssistantLength", 0))
        is_generating = bool(state.get("isGenerating"))
        now_ts = time.time()

        if now_ts >= next_status_at:
            elapsed_seconds = int(now_ts - started_at)
            elapsed_mm = elapsed_seconds // 60
            elapsed_ss = elapsed_seconds % 60
            preview = str(state.get("lastAssistantPreview", "")).replace("\n", " ").strip()
            preview = re.sub(r"\s+", " ", preview)
            if assistant_count <= baseline_count:
                message = f"Status {elapsed_mm:02d}:{elapsed_ss:02d}: noch keine Assistant-Antwort sichtbar"
            else:
                message = f"Status {elapsed_mm:02d}:{elapsed_ss:02d}: ChatGPT antwortet noch"
                if preview:
                    tail_preview = preview[-140:]
                    if len(preview) > len(tail_preview):
                        tail_preview = f"...{tail_preview}"
                    message += f" | Preview: {tail_preview}"
            print(message, file=sys.stderr)
            next_status_at += 60

        if assistant_count > baseline_count:
            if last_len == previous_length and last_len > 0:
                stable_rounds += 1
            else:
                stable_rounds = 0
                previous_length = last_len

            if not is_generating and stable_rounds >= 1:
                return state

        _call_tool_with_retry(client, "browser_wait_for", {"time": poll_interval_seconds})

    raise TimeoutError(
        f"ChatGPT-Antwort wurde nicht innerhalb von {timeout_seconds} Sekunden fertig."
    )


def _extract_last_assistant_html(client: McpStdioClient, raw_html_out: Path) -> Path:
    raw_html_out.parent.mkdir(parents=True, exist_ok=True)
    _call_tool_with_retry(
        client,
        "browser_evaluate",
        {
            "function": LAST_ASSISTANT_HTML_JS,
            "filename": str(raw_html_out),
        },
    )
    return raw_html_out
# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_convert(input_file: str, question: str, output: str | None, thinking: bool) -> None:
    """Read HTML file from evaluate(), convert to Markdown, save."""
    try:
        out_path, content = _write_markdown_from_html(input_file, question, output, thinking)
    except Exception as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        sys.exit(EXIT_INVALID_HTML)

    print(f"OK: {_rel_for_display(out_path)} ({len(content)} Zeichen)")


def cmd_doctor(chat_url: str) -> None:
    config = _load_playwright_server_config()
    client: McpStdioClient | None = None
    try:
        client, tools, state, restart_count = _start_client_and_fetch_state(config, chat_url)
    except McpError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        sys.exit(EXIT_MCP_UNAVAILABLE)
    except Exception as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        sys.exit(EXIT_GENERAL_ERROR)
    finally:
        if client:
            client.close()

    report = {
        "bridge_mode": True,
        "config": {"command": config.command, "args": config.args},
        "required_tools_ok": True,
        "tool_count": len(tools),
        "startup_restart_count": restart_count,
        "page": {
            "url": state.get("url"),
            "title": state.get("title"),
            "has_textbox": state.get("hasTextbox"),
            "thinking_active": state.get("thinkingActive"),
        },
        "login_ok": bool(state.get("hasTextbox")),
    }
    print(_json_dumps(report))
    if not state.get("hasTextbox"):
        sys.exit(EXIT_LOGIN_REQUIRED)


def cmd_close(chat_url: str) -> None:
    config = _load_playwright_server_config()
    client: McpStdioClient | None = None
    try:
        client, _, state, _ = _start_client_and_fetch_state(config, chat_url)
        if not state.get("hasTextbox"):
            raise PermissionError("ChatGPT ist nicht eingeloggt oder die Textbox fehlt.")
        _call_tool_with_retry(client, "browser_close", {})
        print(_json_dumps({"closed": True}))
    except PermissionError as exc:
        print(_json_dumps({"closed": False, "error": str(exc)}))
        sys.exit(EXIT_LOGIN_REQUIRED)
    except McpError as exc:
        print(_json_dumps({"closed": False, "error": str(exc)}))
        sys.exit(EXIT_MCP_UNAVAILABLE)
    except Exception as exc:
        print(_json_dumps({"closed": False, "error": str(exc)}))
        sys.exit(EXIT_GENERAL_ERROR)
    finally:
        if client:
            client.close()


def cmd_run(options: RunOptions) -> None:
    output = _ensure_path(options.output) if options.output else _default_output_path(options.question)
    raw_html_out = _html_output_path(output)
    raw_html_out.parent.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)

    config = _load_playwright_server_config()
    client: McpStdioClient | None = None

    try:
        client, _, state, _ = _start_client_and_fetch_state(
            config,
            options.chat_url,
        )
        if not state.get("hasTextbox"):
            raise PermissionError("ChatGPT ist nicht eingeloggt oder die Textbox fehlt.")

        if not options.reuse_chat and int(state.get("assistantCount", 0)) > 0:
            _open_new_chat(client, options.chat_url)
            state = _parse_json_text(
                _tool_text_with_retry(client, "browser_evaluate", {"function": DOM_STATE_JS}),
                "DOM state after new chat",
            )
            if not state.get("hasTextbox"):
                raise PermissionError("Neue Chat-Seite geladen, aber keine Textbox gefunden.")

        if options.thinking and not state.get("thinkingActive"):
            if not _set_thinking_mode(client):
                raise RuntimeError("Längeres Nachdenken konnte nicht aktiviert werden.")
            state = _parse_json_text(
                _tool_text_with_retry(client, "browser_evaluate", {"function": DOM_STATE_JS}),
                "DOM state after thinking mode",
            )

        _apply_global_prompt_gate()
        state = _parse_json_text(
            _tool_text_with_retry(client, "browser_evaluate", {"function": DOM_STATE_JS}),
            "DOM state before first prompt",
        )
        baseline = int(state.get("assistantCount", 0))
        _submit_prompt(client, options.question)
        _call_tool_with_retry(client, "browser_wait_for", {"time": 2})
        print(
            "ChatGPT-Research kann bis zu "
            f"{options.timeout_seconds // 60} Minuten dauern; "
            "der Agent wartet bis zum konfigurierten Timeout.",
            file=sys.stderr,
        )

        _poll_for_completed_message(
            client,
            baseline_count=baseline,
            timeout_seconds=options.timeout_seconds,
            poll_interval_seconds=options.poll_interval_seconds,
        )

        _extract_last_assistant_html(client, raw_html_out)
        out_path, content = _write_markdown_from_html(
            raw_html_out,
            options.question,
            output,
            options.thinking,
        )

        print(_json_dumps(_success_meta(raw_html_out, out_path, content)))
    except PermissionError as exc:
        print(_json_dumps(_error_meta(raw_html_out, str(exc))))
        sys.exit(EXIT_LOGIN_REQUIRED)
    except TimeoutError as exc:
        print(_json_dumps(_error_meta(raw_html_out, str(exc))))
        sys.exit(EXIT_RESPONSE_TIMEOUT)
    except McpError as exc:
        print(_json_dumps(_error_meta(raw_html_out, str(exc))))
        sys.exit(EXIT_MCP_UNAVAILABLE)
    except RuntimeError as exc:
        print(_json_dumps(_error_meta(raw_html_out, str(exc))))
        sys.exit(EXIT_INVALID_HTML)
    except Exception as exc:
        print(_json_dumps(_error_meta(raw_html_out, str(exc))))
        sys.exit(EXIT_GENERAL_ERROR)
    finally:
        if client:
            client.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="ChatGPT Research via Playwright MCP Bridge",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    conv = subparsers.add_parser("convert", help="HTML-Datei zu Markdown konvertieren")
    conv.add_argument("input_file", help="Pfad zur HTML-Datei (aus evaluate filename)")
    conv.add_argument("--question", "-q", required=True, help="Die urspruengliche Frage")
    conv.add_argument(
        "--output",
        "-o",
        default=None,
        help="Ausgabepfad (Default: tmp/YYYYMMDD_chatgpt_SLUG.md)",
    )
    conv.add_argument(
        "--thinking",
        action="store_true",
        help="Markierung 'Laengeres Nachdenken' im Header",
    )

    doctor = subparsers.add_parser("doctor", help="Bridge/MCP/Login pruefen")
    doctor.add_argument("--chat-url", default=DEFAULT_CHAT_URL, help="ChatGPT URL")
    close = subparsers.add_parser("close", help="Aktuellen ChatGPT-Tab schliessen")
    close.add_argument("--chat-url", default=DEFAULT_CHAT_URL, help="ChatGPT URL")

    run = subparsers.add_parser("run", help="Bridge-basierten ChatGPT-Workflow ausfuehren")
    run.add_argument("--question", "-q", required=True, help="Die urspruengliche Frage")
    run.add_argument(
        "--output",
        "-o",
        default=None,
        help="Ausgabepfad (Default: tmp/YYYYMMDD_chatgpt_SLUG.md)",
    )
    run.add_argument(
        "--thinking",
        action="store_true",
        help="Versucht 'Laengeres Nachdenken' zu aktivieren",
    )
    run.add_argument("--chat-url", default=DEFAULT_CHAT_URL, help="ChatGPT URL")
    run.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=(
            "Maximale Wartezeit pro Antwort "
            f"(Default: {DEFAULT_TIMEOUT_SECONDS} Sekunden = {DEFAULT_TIMEOUT_MINUTES} Minuten)"
        ),
    )
    run.add_argument(
        "--poll-interval-seconds",
        type=int,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
        help="Polling-Intervall fuer DOM-Status",
    )
    run.add_argument(
        "--reuse-chat",
        action="store_true",
        help="Bestehenden Chat weiterverwenden statt auf die Startseite zu gehen",
    )

    args = parser.parse_args()

    if args.command == "convert":
        cmd_convert(args.input_file, args.question, args.output, args.thinking)
    elif args.command == "doctor":
        cmd_doctor(args.chat_url)
    elif args.command == "close":
        cmd_close(args.chat_url)
    elif args.command == "run":
        cmd_run(
            RunOptions(
                question=args.question,
                output=Path(args.output) if args.output else None,
                thinking=args.thinking,
                chat_url=args.chat_url,
                timeout_seconds=args.timeout_seconds,
                poll_interval_seconds=args.poll_interval_seconds,
                reuse_chat=args.reuse_chat,
            )
        )


if __name__ == "__main__":
    main()
