import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import m365_copilot_graph_token as mod  # noqa: E402


def test_parse_tab_list_extracts_indices_and_urls():
    text = (
        "- 0: (current) [M365](https://m365.cloud.microsoft/chat)\n"
        "- 1: [Google](https://www.google.com)\n"
        "- 2: [Alt](https://m365.cloud.microsoft/chat?x=1)\n"
    )

    assert mod._parse_tab_list(text) == [
        (0, "https://m365.cloud.microsoft/chat"),
        (1, "https://www.google.com"),
        (2, "https://m365.cloud.microsoft/chat?x=1"),
    ]


def test_close_matching_browser_tab_closes_matching_tabs_in_reverse_order():
    class DummyClient:
        def __init__(self):
            self.calls: list[tuple[str, dict]] = []

        def call_tool(self, name, args):
            self.calls.append((name, args))
            if name == "browser_tabs" and args.get("action") == "list":
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "- 0: [M365](https://m365.cloud.microsoft/chat)\n"
                                "- 1: [Google](https://google.com)\n"
                                "- 2: [M365 2](https://m365.cloud.microsoft/chat?x=1)"
                            ),
                        }
                    ]
                }
            return {}

    client = DummyClient()

    mod._close_matching_browser_tab(client, ("m365.cloud.microsoft/chat",))

    assert client.calls == [
        ("browser_tabs", {"action": "list"}),
        ("browser_tabs", {"action": "close", "index": 2}),
        ("browser_tabs", {"action": "close", "index": 0}),
    ]


def test_close_matching_browser_tab_falls_back_to_browser_close_when_tab_listing_fails(capsys):
    class DummyClient:
        def __init__(self):
            self.calls: list[tuple[str, dict]] = []

        def call_tool(self, name, args):
            self.calls.append((name, args))
            if name == "browser_tabs":
                raise RuntimeError("tool not available")
            return {}

    client = DummyClient()

    mod._close_matching_browser_tab(client, ("m365.cloud.microsoft/chat",))

    assert ("browser_close", {}) in client.calls
    assert "Tab-Liste nicht verfuegbar" in capsys.readouterr().err


def test_fetch_token_via_mcp_closes_tab_after_success(monkeypatch):
    exp = int(time.time()) + 1800
    close_calls: list[tuple[str, ...]] = []
    saved_cache: list[tuple[str, int, str]] = []

    class FakeClient:
        def __init__(self, _config):
            self.closed = False

        def start(self):
            return None

        def close(self):
            self.closed = True

    monkeypatch.setattr(mod, "McpStdioClient", FakeClient)
    monkeypatch.setattr(mod, "_load_playwright_server_config", lambda: object())
    monkeypatch.setattr(mod, "_ensure_required_tools", lambda _client: None)
    monkeypatch.setattr(mod, "_call_tool_with_retry", lambda _client, _name, _arguments=None: {})
    monkeypatch.setattr(
        mod,
        "_tool_text_with_retry",
        lambda _client, _name, _arguments=None: json.dumps({"token": "abc", "source": "m365-copilot-naa"}),
    )
    monkeypatch.setattr(mod, "_validate_token", lambda _token: exp)
    monkeypatch.setattr(mod, "_save_cache", lambda token, token_exp, source: saved_cache.append((token, token_exp, source)))
    monkeypatch.setattr(mod, "_close_matching_browser_tab", lambda _client, fragments: close_calls.append(fragments))

    result = mod._fetch_token_via_mcp()

    assert result == ("abc", exp, "m365-copilot-naa")
    assert saved_cache == [("abc", exp, "m365-copilot-naa")]
    assert close_calls == [("m365.cloud.microsoft/chat",)]


def test_fetch_token_via_mcp_does_not_close_tab_on_error(monkeypatch):
    close_calls: list[tuple[str, ...]] = []

    class FakeClient:
        def __init__(self, _config):
            pass

        def start(self):
            return None

        def close(self):
            return None

    monkeypatch.setattr(mod, "McpStdioClient", FakeClient)
    monkeypatch.setattr(mod, "_load_playwright_server_config", lambda: object())
    monkeypatch.setattr(mod, "_ensure_required_tools", lambda _client: None)
    monkeypatch.setattr(mod, "_call_tool_with_retry", lambda _client, _name, _arguments=None: {})
    monkeypatch.setattr(
        mod,
        "_tool_text_with_retry",
        lambda _client, _name, _arguments=None: json.dumps({"error": "TOKEN_REQUEST_FAILED", "message": "nope"}),
    )
    monkeypatch.setattr(mod, "_close_matching_browser_tab", lambda _client, fragments: close_calls.append(fragments))

    try:
        mod._fetch_token_via_mcp()
    except mod.TokenResolverError as exc:
        assert exc.code == "TOKEN_REQUEST_FAILED"
    else:
        raise AssertionError("TokenResolverError expected")

    assert close_calls == [
        ("m365.cloud.microsoft/chat",),
        ("m365.cloud.microsoft/chat",),
    ]


def test_fetch_token_via_mcp_leaves_tab_open_in_debug_mode(monkeypatch):
    exp = int(time.time()) + 1800
    close_calls: list[tuple[str, ...]] = []

    class FakeClient:
        def __init__(self, _config):
            pass

        def start(self):
            return None

        def close(self):
            return None

    monkeypatch.setattr(mod, "McpStdioClient", FakeClient)
    monkeypatch.setattr(mod, "_load_playwright_server_config", lambda: object())
    monkeypatch.setattr(mod, "_ensure_required_tools", lambda _client: None)
    monkeypatch.setattr(mod, "_call_tool_with_retry", lambda _client, _name, _arguments=None: {})
    monkeypatch.setattr(
        mod,
        "_tool_text_with_retry",
        lambda _client, _name, _arguments=None: json.dumps({"token": "abc", "source": "m365-copilot-naa"}),
    )
    monkeypatch.setattr(mod, "_validate_token", lambda _token: exp)
    monkeypatch.setattr(mod, "_save_cache", lambda *_args: None)
    monkeypatch.setattr(mod, "_close_matching_browser_tab", lambda _client, fragments: close_calls.append(fragments))

    result = mod._fetch_token_via_mcp(debug=True)

    assert result == ("abc", exp, "m365-copilot-naa")
    assert close_calls == []
