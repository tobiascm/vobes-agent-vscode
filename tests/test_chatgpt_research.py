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


@pytest.mark.parametrize(
    "sentinel",
    [
        "---fertig---",
        "---fertig",
        "--- fertig",
        "--- FERTIG",
    ],
)
def test_completion_sentinel_accepts_exact_and_short_forms(sentinel: str):
    assert mod._has_completion_sentinel(f"Antwort\n{sentinel}")
    assert mod._strip_completion_sentinel(f"Antwort\n{sentinel}") == "Antwort"


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
    assert captured.out == ""
    assert captured.err == ""


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


def test_save_and_load_followup_url_roundtrip(tmp_path: Path):
    state_path = tmp_path / "followup.json"
    out_path = tmp_path / "antwort.md"

    mod._save_followup_state("https://chatgpt.com/c/test-chat", out_path, state_path)

    assert mod._load_followup_url(state_path) == "https://chatgpt.com/c/test-chat"


def test_load_followup_url_rejects_missing_or_root_url(tmp_path: Path):
    state_path = tmp_path / "followup.json"

    with pytest.raises(RuntimeError, match="Kein wiederverwendbarer letzter Chat gespeichert"):
        mod._load_followup_url(state_path)

    state_path.write_text(json.dumps({"last_chat_url": "https://chatgpt.com/"}), encoding="utf-8")

    with pytest.raises(RuntimeError, match="Kein wiederverwendbarer letzter Chat gespeichert"):
        mod._load_followup_url(state_path)


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


def test_poll_for_completed_message_prints_wait_message_to_stdout(monkeypatch, capsys):
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
    times = iter([0.0, 61.0, 61.0, 62.0, 62.0, 62.0, 62.0])
    last_time = {"value": 62.0}
    last_state = {
        "value": json.dumps(
            {
                "assistantCount": 1,
                "lastAssistantLength": 5,
                "lastAssistantPreview": "Erste Zwischenantwort",
                "isGenerating": False,
            }
        )
    }

    def fake_time():
        try:
            last_time["value"] = next(times)
        except StopIteration:
            pass
        return last_time["value"]

    def fake_tool_text(*args, **kwargs):
        try:
            last_state["value"] = next(states)
        except StopIteration:
            pass
        return last_state["value"]

    monkeypatch.setattr(mod, "_tool_text_with_retry", fake_tool_text)
    monkeypatch.setattr(mod, "_call_tool_with_retry", lambda *args, **kwargs: None)
    monkeypatch.setattr(mod.time, "time", fake_time)

    state = mod._poll_for_completed_message(
        client=None,  # type: ignore[arg-type]
        baseline_count=0,
        thinking=False,
        timeout_seconds=180,
        poll_interval_seconds=3,
        completion_stable_seconds=0,
        completion_min_chars=0,
        no_generation_grace_seconds=0,
    )

    captured = capsys.readouterr()
    assert captured.out.strip() == mod.RUN_WAIT_MESSAGE
    assert captured.err == ""
    assert state["assistantCount"] == 1


def test_wait_for_prompt_readiness_retries_until_textbox(monkeypatch):
    states = iter(
        [
            json.dumps({"hasTextbox": False, "url": "https://chatgpt.com/c/test", "title": "Chat"}),
            json.dumps({"hasTextbox": False, "url": "https://chatgpt.com/c/test", "title": "Chat"}),
            json.dumps({"hasTextbox": True, "url": "https://chatgpt.com/c/test", "title": "Chat"}),
        ]
    )
    waits: list[tuple[str, dict[str, int]]] = []

    monkeypatch.setattr(mod, "_tool_text_with_retry", lambda *args, **kwargs: next(states))
    monkeypatch.setattr(
        mod,
        "_call_tool_with_retry",
        lambda client, name, arguments: waits.append((name, arguments)),
    )

    state = mod._wait_for_prompt_readiness(
        client=None,  # type: ignore[arg-type]
        initial_state={"hasTextbox": False, "url": "https://chatgpt.com/c/test", "title": "Chat"},
        timeout_seconds=5,
        poll_interval_seconds=1,
        context="Test",
    )

    assert state["hasTextbox"] is True
    assert waits == [
        ("browser_wait_for", {"time": 1}),
        ("browser_wait_for", {"time": 1}),
    ]


def test_wait_for_prompt_readiness_times_out_with_context(monkeypatch):
    monkeypatch.setattr(
        mod,
        "_tool_text_with_retry",
        lambda *args, **kwargs: json.dumps(
            {"hasTextbox": False, "url": "https://chatgpt.com/c/slow", "title": "Langes Chatfenster"}
        ),
    )
    monkeypatch.setattr(mod, "_call_tool_with_retry", lambda *args, **kwargs: None)

    times = iter([0.0, 10.0, 20.0, 31.0])
    monkeypatch.setattr(mod.time, "time", lambda: next(times))

    with pytest.raises(RuntimeError, match="ChatGPT-Textbox wurde nicht innerhalb von 30 Sekunden bereit"):
        mod._wait_for_prompt_readiness(
            client=None,  # type: ignore[arg-type]
            initial_state={"hasTextbox": False, "url": "https://chatgpt.com/c/slow", "title": "Langes Chatfenster"},
            timeout_seconds=30,
            poll_interval_seconds=1,
        )


def _make_dummy_client():
    """Create a dummy MCP client that records call_tool invocations."""

    class _DummyClient:
        def __init__(self):
            self.calls: list[tuple[str, dict]] = []

        def call_tool(self, name, args):
            self.calls.append((name, args))
            if name == "browser_tabs" and args.get("action") == "list":
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": "- 0: (current) [ChatGPT](https://chatgpt.com/c/abc)",
                        }
                    ]
                }
            return {}

        def close(self):
            pass

    return _DummyClient()


def test_cmd_run_success_prints_wait_message_and_final_ok(monkeypatch, tmp_path, capsys):
    output = tmp_path / "antwort.md"
    calls = []
    dummy_client = _make_dummy_client()

    monkeypatch.setattr(mod, "_load_playwright_server_config", lambda: object())
    monkeypatch.setattr(
        mod,
        "_start_client_and_fetch_state",
        lambda config, chat_url: (
            dummy_client,
            [],
            {"hasTextbox": True, "assistantCount": 0, "thinkingActive": True},
            0,
        ),
    )
    monkeypatch.setattr(mod, "_apply_global_prompt_gate", lambda: None)
    monkeypatch.setattr(
        mod,
        "_tool_text_with_retry",
        lambda *args, **kwargs: json.dumps({"assistantCount": 0}),
    )
    monkeypatch.setattr(mod, "_submit_prompt", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        mod,
        "_call_tool_with_retry",
        lambda client, name, arguments, allow_reset=True: calls.append((name, arguments)),
    )
    monkeypatch.setattr(
        mod,
        "_poll_for_completed_message",
        lambda *args, **kwargs: {"assistantCount": 1},
    )
    monkeypatch.setattr(mod, "_extract_last_assistant_html", lambda *args, **kwargs: output.with_suffix(".html"))
    monkeypatch.setattr(
        mod,
        "_write_markdown_from_html",
        lambda *args, **kwargs: (output, "abcd"),
    )

    mod.cmd_run(
        mod.RunOptions(
            question="Testfrage",
            output=output,
            thinking=True,
            quick=False,
            chat_url=mod.DEFAULT_CHAT_URL,
            timeout_seconds=180,
            poll_interval_seconds=3,
            completion_stable_seconds=15,
            completion_min_chars=200,
            no_generation_grace_seconds=90,
            follow_up=False,
        )
    )

    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        mod.RUN_OPENING_MESSAGE,
        mod.RUN_PROMPT_SENT_MESSAGE,
        mod.RUN_WAIT_MESSAGE,
        f"OK: {output} (4 Zeichen)",
    ]
    assert captured.err == ""
    assert ("browser_tabs", {"action": "list"}) in dummy_client.calls
    assert ("browser_tabs", {"action": "close", "index": 0}) in dummy_client.calls


def test_cmd_run_permission_error_prints_markdown_target_on_stderr(monkeypatch, tmp_path, capsys):
    output = tmp_path / "antwort.md"

    monkeypatch.setattr(mod, "_load_playwright_server_config", lambda: object())
    monkeypatch.setattr(
        mod,
        "_start_client_and_fetch_state",
        lambda config, chat_url: (_ for _ in ()).throw(PermissionError("Textbox fehlt")),
    )

    with pytest.raises(SystemExit) as excinfo:
        mod.cmd_run(
            mod.RunOptions(
                question="Testfrage",
                output=output,
                thinking=True,
                quick=False,
                chat_url=mod.DEFAULT_CHAT_URL,
                timeout_seconds=180,
                poll_interval_seconds=3,
                completion_stable_seconds=15,
                completion_min_chars=200,
                no_generation_grace_seconds=90,
                follow_up=False,
            )
        )

    captured = capsys.readouterr()
    assert excinfo.value.code == mod.EXIT_LOGIN_REQUIRED
    assert captured.out.splitlines() == [mod.RUN_OPENING_MESSAGE]
    assert captured.err.strip() == f"Fehler: Textbox fehlt | Markdown-Ziel: {output}"


def test_cmd_run_follow_up_uses_saved_url(monkeypatch, tmp_path, capsys):
    output = tmp_path / "antwort.md"
    navigated_to: list[str] = []
    calls = []
    dummy_client = _make_dummy_client()

    monkeypatch.setattr(mod, "_load_followup_url", lambda: "https://chatgpt.com/c/existing-chat")
    monkeypatch.setattr(mod, "_load_playwright_server_config", lambda: object())
    monkeypatch.setattr(
        mod,
        "_start_client_and_fetch_state",
        lambda config, chat_url: (
            navigated_to.append(chat_url) or dummy_client,
            [],
            {"hasTextbox": True, "assistantCount": 2, "thinkingActive": True},
            0,
        ),
    )
    monkeypatch.setattr(mod, "_apply_global_prompt_gate", lambda: None)
    monkeypatch.setattr(
        mod,
        "_tool_text_with_retry",
        lambda *args, **kwargs: json.dumps({"assistantCount": 2}),
    )
    monkeypatch.setattr(mod, "_submit_prompt", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        mod,
        "_call_tool_with_retry",
        lambda client, name, arguments, allow_reset=True: calls.append((name, arguments)),
    )
    monkeypatch.setattr(
        mod,
        "_poll_for_completed_message",
        lambda *args, **kwargs: {"assistantCount": 3, "url": "https://chatgpt.com/c/existing-chat"},
    )
    monkeypatch.setattr(mod, "_extract_last_assistant_html", lambda *args, **kwargs: output.with_suffix(".html"))
    monkeypatch.setattr(mod, "_write_markdown_from_html", lambda *args, **kwargs: (output, "abcd"))
    saved: list[tuple[str, Path]] = []
    monkeypatch.setattr(mod, "_save_followup_state", lambda url, out_path: saved.append((url, out_path)))
    monkeypatch.setattr(
        mod,
        "_open_new_chat",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("new chat should not be opened")),
    )

    mod.cmd_run(
        mod.RunOptions(
            question="Folgefrage",
            output=output,
            thinking=True,
            quick=False,
            chat_url=mod.DEFAULT_CHAT_URL,
            timeout_seconds=180,
            poll_interval_seconds=3,
            completion_stable_seconds=15,
            completion_min_chars=200,
            no_generation_grace_seconds=90,
            follow_up=True,
        )
    )

    captured = capsys.readouterr()
    assert navigated_to == ["https://chatgpt.com/c/existing-chat"]
    assert saved == [("https://chatgpt.com/c/existing-chat", output)]
    assert captured.out.splitlines()[0] == mod.RUN_FOLLOWUP_OPENING_MESSAGE
    assert ("browser_tabs", {"action": "list"}) in dummy_client.calls
    assert ("browser_tabs", {"action": "close", "index": 0}) in dummy_client.calls


def test_main_run_defaults_to_thinking(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        mod.sys,
        "argv",
        [
            "chatgpt_research.py",
            "run",
            "--question",
            "Testfrage",
            "--output",
            str(tmp_path / "antwort.md"),
        ],
    )
    monkeypatch.setattr(mod, "cmd_run", lambda options: captured.setdefault("options", options))

    mod.main()

    options = captured["options"]
    assert isinstance(options, mod.RunOptions)
    assert options.thinking is True
    assert options.follow_up is False


def test_main_run_sets_follow_up(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        mod.sys,
        "argv",
        [
            "chatgpt_research.py",
            "run",
            "--question",
            "Folgefrage",
            "--follow-up",
            "--output",
            str(tmp_path / "antwort.md"),
        ],
    )
    monkeypatch.setattr(mod, "cmd_run", lambda options: captured.setdefault("options", options))

    mod.main()

    options = captured["options"]
    assert isinstance(options, mod.RunOptions)
    assert options.follow_up is True


def test_main_run_rejects_removed_thinking_flag(monkeypatch, capsys):
    monkeypatch.setattr(
        mod.sys,
        "argv",
        [
            "chatgpt_research.py",
            "run",
            "--question",
            "Testfrage",
            "--thinking",
        ],
    )

    with pytest.raises(SystemExit) as excinfo:
        mod.main()

    captured = capsys.readouterr()
    assert excinfo.value.code == 2
    assert "unrecognized arguments: --thinking" in captured.err


def test_main_run_rejects_removed_reuse_chat_flag(monkeypatch, capsys):
    monkeypatch.setattr(
        mod.sys,
        "argv",
        [
            "chatgpt_research.py",
            "run",
            "--question",
            "Folgefrage",
            "--reuse-chat",
        ],
    )

    with pytest.raises(SystemExit) as excinfo:
        mod.main()

    captured = capsys.readouterr()
    assert excinfo.value.code == 2
    assert "unrecognized arguments: --reuse-chat" in captured.err


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


# ---------------------------------------------------------------------------
# _parse_tab_list
# ---------------------------------------------------------------------------

def test_parse_tab_list_extracts_indices_and_urls():
    text = (
        "- 0: (current) [ChatGPT](https://chatgpt.com/c/abc)\n"
        "- 1: [Google](https://www.google.com)\n"
        "- 2: [Other Chat](https://chatgpt.com/c/xyz)\n"
    )
    result = mod._parse_tab_list(text)
    assert result == [
        (0, "https://chatgpt.com/c/abc"),
        (1, "https://www.google.com"),
        (2, "https://chatgpt.com/c/xyz"),
    ]


def test_parse_tab_list_returns_empty_for_garbage():
    assert mod._parse_tab_list("") == []
    assert mod._parse_tab_list("no tabs here") == []


# ---------------------------------------------------------------------------
# _close_chat_tab_safely
# ---------------------------------------------------------------------------

def test_close_chat_tab_safely_closes_chatgpt_tab_by_index(capsys):
    client = _make_dummy_client()
    mod._close_chat_tab_safely(client)

    assert ("browser_tabs", {"action": "list"}) in client.calls
    assert ("browser_tabs", {"action": "close", "index": 0}) in client.calls
    # No browser_close fallback needed
    assert not any(name == "browser_close" for name, _ in client.calls)
    assert capsys.readouterr().err == ""


def test_close_chat_tab_safely_falls_back_when_tabs_unavailable(capsys):
    class _NoTabsClient:
        def __init__(self):
            self.calls: list[tuple[str, dict]] = []

        def call_tool(self, name, args):
            self.calls.append((name, args))
            if name == "browser_tabs":
                raise RuntimeError("tool not available")
            return {}

    client = _NoTabsClient()
    mod._close_chat_tab_safely(client)

    assert ("browser_close", {}) in client.calls
    err = capsys.readouterr().err
    assert "Tab-Liste nicht verfuegbar" in err


def test_close_chat_tab_safely_falls_back_when_no_chatgpt_tab(capsys):
    class _OtherTabsClient:
        def __init__(self):
            self.calls: list[tuple[str, dict]] = []

        def call_tool(self, name, args):
            self.calls.append((name, args))
            if name == "browser_tabs" and args.get("action") == "list":
                return {
                    "content": [
                        {"type": "text", "text": "- 0: (current) [Google](https://google.com)"}
                    ]
                }
            return {}

    client = _OtherTabsClient()
    mod._close_chat_tab_safely(client)

    assert ("browser_close", {}) in client.calls
    assert capsys.readouterr().err == ""
