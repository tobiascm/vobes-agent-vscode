from pathlib import Path
import json
import sys

import pytest

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[1]
        / ".agents"
        / "skills"
        / "skill-chatgpt-research"
        / "scripts"
    ),
)

import chatgpt_research as mod


def test_discover_project_root_finds_workspace_marker(tmp_path: Path):
    workspace = tmp_path / "repo"
    nested = workspace / ".agents" / "skills" / "skill-chatgpt-research" / "scripts"
    nested.mkdir(parents=True)
    mcp_config = workspace / ".vscode" / "mcp.json"
    mcp_config.parent.mkdir(parents=True)
    mcp_config.write_text("{}", encoding="utf-8")

    assert mod._discover_project_root(nested) == workspace


def test_extract_text_content_joins_text_items():
    payload = {
        "content": [
            {"type": "text", "text": "alpha"},
            {"type": "image", "image": "ignored"},
            {"type": "text", "text": "beta"},
        ]
    }

    assert mod._extract_text_content(payload) == "alpha\nbeta"


def test_load_jsonc_strips_comments(tmp_path: Path):
    config_file = tmp_path / "sample.jsonc"
    config_file.write_text(
        "// comment\n"
        "{\n"
        '  "servers": {\n'
        '    "playwright": {"command": "npx", "args": ["@playwright/mcp@latest"]}\n'
        "  }\n"
        "}\n",
        encoding="utf-8",
    )

    data = mod._load_jsonc(config_file)

    assert data["servers"]["playwright"]["command"] == "npx"


def test_load_playwright_server_config_reads_workspace_and_env(tmp_path: Path, monkeypatch):
    config_file = tmp_path / "mcp.json"
    config_file.write_text(
        "{\n"
        '  "servers": {\n'
        '    "playwright": {\n'
        '      "command": "npx",\n'
        '      "args": ["@playwright/mcp@latest", "--extension"],\n'
        '      "env": {"PLAYWRIGHT_MCP_EXTENSION_TOKEN": "token-123", "ROOT": "${workspaceFolder}"}\n'
        "    }\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "MCP_CONFIG", config_file)

    cfg = mod._load_playwright_server_config()

    assert cfg.command.lower().endswith("npx.cmd")
    assert cfg.args == ["@playwright/mcp@latest", "--extension"]
    assert cfg.env["PLAYWRIGHT_MCP_EXTENSION_TOKEN"] == "token-123"
    assert cfg.env["ROOT"] == str(mod.PROJECT_ROOT)


def test_write_markdown_from_html_handles_wrapped_evaluate_output(tmp_path: Path):
    html_file = tmp_path / "raw.html"
    html_file.write_text(
        json.dumps("<h2>Headline</h2><p>Hello</p><ul><li>One</li><li>Two</li></ul>"),
        encoding="utf-8",
    )
    output_file = tmp_path / "result.md"

    out_path, content = mod._write_markdown_from_html(
        html_file,
        question="Test question",
        output=output_file,
        thinking=True,
    )

    assert out_path == output_file
    assert "# Test question" in content
    assert "Quelle: ChatGPT (Laengeres Nachdenken)" in content
    assert "## Headline" in content
    assert "- One" in content
    assert "- Two" in content
    assert output_file.read_text(encoding="utf-8") == content


def test_extract_playwright_result_text_unwraps_markdown_report():
    raw = (
        "### Result\n"
        '"{\\"ok\\": true, \\"value\\": 3}"\n'
        "### Ran Playwright code\n"
        "```js\nconsole.log('x')\n```"
    )

    assert mod._extract_playwright_result_text(raw) == '{"ok": true, "value": 3}'


def test_load_gate_state_recovers_from_invalid_json(tmp_path: Path):
    state_path = tmp_path / "gate.json"
    state_path.write_text("{invalid", encoding="utf-8")

    state = mod._load_gate_state(state_path)

    assert state == {"next_allowed_at": 0.0}


def test_reserve_global_chatgpt_slot_initializes_empty_state(tmp_path: Path):
    lock_path = tmp_path / "gate.lock"
    state_path = tmp_path / "gate.json"

    reservation = mod._reserve_global_chatgpt_slot(
        now_ts=1000.0,
        interval_seconds=30.0,
        lock_path=lock_path,
        state_path=state_path,
    )

    assert reservation["wait_seconds"] == 0.0
    assert reservation["slot_at"] == 1000.0
    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved["next_allowed_at"] == 1030.0


def test_reserve_global_chatgpt_slot_serializes_subsequent_calls(tmp_path: Path):
    lock_path = tmp_path / "gate.lock"
    state_path = tmp_path / "gate.json"

    first = mod._reserve_global_chatgpt_slot(
        now_ts=1000.0,
        interval_seconds=30.0,
        lock_path=lock_path,
        state_path=state_path,
    )
    second = mod._reserve_global_chatgpt_slot(
        now_ts=1001.0,
        interval_seconds=30.0,
        lock_path=lock_path,
        state_path=state_path,
    )

    assert first["slot_at"] == 1000.0
    assert second["slot_at"] == 1030.0
    assert second["wait_seconds"] == 29.0
    assert second["queue_depth_hint"] == 1


def test_apply_global_prompt_gate_waits(monkeypatch, capsys):
    calls: list[float] = []

    monkeypatch.setattr(
        mod,
        "_reserve_global_chatgpt_slot",
        lambda: {
            "wait_seconds": 12.5,
            "slot_at_iso": "2026-04-03T12:00:30",
            "queue_depth_hint": 1,
        },
    )
    monkeypatch.setattr(mod.time, "sleep", lambda seconds: calls.append(seconds))

    mod._apply_global_prompt_gate()

    captured = capsys.readouterr()
    assert calls == [12.5]
    assert "Globales ChatGPT-Limit aktiv, warte 12.5s bis zum naechsten Slot" in captured.err


def test_apply_global_prompt_gate_skips_sleep_when_no_wait(monkeypatch):
    monkeypatch.setattr(
        mod,
        "_reserve_global_chatgpt_slot",
        lambda: {
            "wait_seconds": 0.0,
            "slot_at_iso": "2026-04-03T12:01:00",
            "queue_depth_hint": 0,
        },
    )
    monkeypatch.setattr(mod.time, "sleep", lambda seconds: (_ for _ in ()).throw(RuntimeError("sleep should not be called")))

    mod._apply_global_prompt_gate()

def test_html_output_path_uses_same_name_as_markdown(tmp_path: Path):
    md_path = tmp_path / "bericht.md"

    assert mod._html_output_path(md_path) == tmp_path / "bericht.html"


def test_success_meta_is_minimal(tmp_path: Path):
    raw_html = tmp_path / "bericht.html"
    out_md = tmp_path / "bericht.md"

    meta = mod._success_meta(raw_html, out_md, "abcd")

    assert meta == {
        "output_md": str(out_md),
        "output_chars": 4,
        "raw_html_out": str(raw_html),
    }


def test_error_meta_is_minimal(tmp_path: Path):
    raw_html = tmp_path / "bericht.html"

    meta = mod._error_meta(raw_html, "kaputt")

    assert meta == {
        "raw_html_out": str(raw_html),
        "error": "kaputt",
    }


def test_cmd_close_closes_current_tab(monkeypatch, capsys):
    calls = []

    monkeypatch.setattr(mod, "_load_playwright_server_config", lambda: object())
    monkeypatch.setattr(
        mod,
        "_start_client_and_fetch_state",
        lambda config, chat_url: (type("Dummy", (), {"close": lambda self: None})(), [], {"hasTextbox": True}, 0),
    )
    monkeypatch.setattr(
        mod,
        "_call_tool_with_retry",
        lambda client, name, arguments: calls.append((name, arguments)),
    )

    mod.cmd_close(mod.DEFAULT_CHAT_URL)

    captured = capsys.readouterr()
    assert calls == [("browser_close", {})]
    assert json.loads(captured.out) == {"closed": True}


def test_cmd_close_returns_login_error_when_no_textbox(monkeypatch, capsys):
    monkeypatch.setattr(mod, "_load_playwright_server_config", lambda: object())
    monkeypatch.setattr(
        mod,
        "_start_client_and_fetch_state",
        lambda config, chat_url: (type("Dummy", (), {"close": lambda self: None})(), [], {"hasTextbox": False}, 0),
    )

    with pytest.raises(SystemExit) as excinfo:
        mod.cmd_close(mod.DEFAULT_CHAT_URL)

    captured = capsys.readouterr()
    assert excinfo.value.code == mod.EXIT_LOGIN_REQUIRED
    assert json.loads(captured.out) == {
        "closed": False,
        "error": "ChatGPT ist nicht eingeloggt oder die Textbox fehlt.",
    }


def test_default_timeout_is_30_minutes():
    assert mod.DEFAULT_TIMEOUT_SECONDS == 1800


def test_poll_for_completed_message_prints_minute_status_with_preview(monkeypatch, capsys):
    states = iter(
        [
            json.dumps(
                {
                    "assistantCount": 1,
                    "lastAssistantLength": 5,
                    "lastAssistantPreview": "Erste Zwischenantwort",
                    "isGenerating": True,
                }
            ),
            json.dumps(
                {
                    "assistantCount": 1,
                    "lastAssistantLength": 5,
                    "lastAssistantPreview": "Erste Zwischenantwort",
                    "isGenerating": False,
                }
            ),
        ]
    )
    times = iter([0.0, 61.0, 61.0, 62.0, 62.0])

    monkeypatch.setattr(mod, "_tool_text_with_retry", lambda *args, **kwargs: next(states))
    monkeypatch.setattr(mod, "_call_tool_with_retry", lambda *args, **kwargs: None)
    monkeypatch.setattr(mod.time, "time", lambda: next(times))

    state = mod._poll_for_completed_message(
        client=None,  # type: ignore[arg-type]
        baseline_count=0,
        timeout_seconds=180,
        poll_interval_seconds=3,
    )

    captured = capsys.readouterr()
    assert "Status 01:01: ChatGPT antwortet noch | Preview: Erste Zwischenantwort" in captured.err
    assert state["assistantCount"] == 1


def test_is_transient_bridge_error_matches_known_bridge_failures():
    assert mod._is_transient_bridge_error(
        RuntimeError("Target page, context or browser has been closed")
    )
    assert mod._is_transient_bridge_error(RuntimeError("No open pages available"))
    assert mod._is_transient_bridge_error(
        RuntimeError("TypeError: Cannot read properties of undefined (reading 'url')")
    )
    assert not mod._is_transient_bridge_error(RuntimeError("Playwright MCP command fehlt"))


def test_parse_json_text_rejects_invalid_payload():
    with pytest.raises(RuntimeError, match="Ungueltige JSON-Antwort"):
        mod._parse_json_text("not-json", "unit-test")
