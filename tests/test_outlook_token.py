import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import outlook_token as mod  # noqa: E402


class _FakeSocket:
    def __init__(self, connect_result: int):
        self._connect_result = connect_result

    def settimeout(self, _timeout):
        return None

    def connect_ex(self, _addr):
        return self._connect_result

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeRequest:
    def __init__(self, token: str):
        self.headers = {"authorization": f"Bearer {token}"}


class _FakePage:
    def __init__(self, token: str | None = None, url: str = "about:blank"):
        self.token = token
        self.url = url
        self.closed = False
        self.goto_calls = 0
        self.reload_calls = 0
        self._handler = None

    def on(self, _event, handler):
        self._handler = handler

    def goto(self, url, **_kwargs):
        self.url = url
        self.goto_calls += 1
        if self.token and self._handler:
            self._handler(_FakeRequest(self.token))

    def reload(self, **_kwargs):
        self.reload_calls += 1
        if self.token and self._handler:
            self._handler(_FakeRequest(self.token))

    def wait_for_timeout(self, _timeout):
        return None

    def close(self):
        self.closed = True


class _FakeContext:
    def __init__(self, pages, new_page_obj):
        self.pages = pages
        self._new_page_obj = new_page_obj
        self.new_page_calls = 0

    def new_page(self):
        self.new_page_calls += 1
        return self._new_page_obj


class _FakeBrowser:
    def __init__(self, contexts=None, new_context_obj=None):
        self.contexts = contexts or []
        self._new_context_obj = new_context_obj
        self.closed = False

    def new_context(self):
        return self._new_context_obj

    def close(self):
        self.closed = True


class _FakeChromium:
    def __init__(self, connect_browser=None, launch_browser=None):
        self._connect_browser = connect_browser
        self._launch_browser = launch_browser

    def connect_over_cdp(self, _url):
        return self._connect_browser

    def launch(self, **_kwargs):
        return self._launch_browser


class _FakePlaywrightManager:
    def __init__(self, chromium):
        self.chromium = chromium

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _install_fake_playwright(monkeypatch, chromium):
    sync_api = types.ModuleType("playwright.sync_api")
    sync_api.sync_playwright = lambda: _FakePlaywrightManager(chromium)
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api)


def test_cmd_fetch_uses_temporary_tab_and_closes_it_for_cdp_success(monkeypatch):
    token = "outlook-token"
    exp = 1_800_000_000
    existing_page = _FakePage(url="https://outlook.office.com/mail/")
    temp_page = _FakePage(token=token)
    context = _FakeContext([existing_page], temp_page)
    browser = _FakeBrowser(contexts=[context])
    chromium = _FakeChromium(connect_browser=browser)
    saved_tokens: list[tuple[str, int]] = []

    _install_fake_playwright(monkeypatch, chromium)
    monkeypatch.setattr("socket.socket", lambda *args, **kwargs: _FakeSocket(0))
    monkeypatch.setattr(mod, "_decode_jwt_payload", lambda _token: {"aud": "https://outlook.office.com", "exp": exp})
    monkeypatch.setattr(mod, "_save_token", lambda saved_token, saved_exp: saved_tokens.append((saved_token, saved_exp)))

    mod.cmd_fetch()

    assert context.new_page_calls == 1
    assert temp_page.goto_calls == 1
    assert temp_page.closed is True
    assert existing_page.reload_calls == 0
    assert browser.closed is False
    assert saved_tokens == [(token, exp)]


def test_cmd_fetch_does_not_close_temporary_tab_after_failed_cdp_fetch(monkeypatch):
    temp_page = _FakePage(token=None)
    context = _FakeContext([], temp_page)
    browser = _FakeBrowser(contexts=[context])
    chromium = _FakeChromium(connect_browser=browser)

    _install_fake_playwright(monkeypatch, chromium)
    monkeypatch.setattr("socket.socket", lambda *args, **kwargs: _FakeSocket(0))

    with pytest.raises(SystemExit) as exc_info:
        mod.cmd_fetch()

    assert exc_info.value.code == 1
    assert context.new_page_calls == 1
    assert temp_page.closed is True
    assert browser.closed is False


def test_cmd_fetch_closes_page_and_browser_for_own_browser_success(monkeypatch):
    token = "outlook-token"
    exp = 1_800_000_000
    temp_page = _FakePage(token=token)
    context = _FakeContext([], temp_page)
    browser = _FakeBrowser(new_context_obj=context)
    chromium = _FakeChromium(launch_browser=browser)
    saved_tokens: list[tuple[str, int]] = []

    _install_fake_playwright(monkeypatch, chromium)
    monkeypatch.setattr("socket.socket", lambda *args, **kwargs: _FakeSocket(1))
    monkeypatch.setattr(mod, "_decode_jwt_payload", lambda _token: {"aud": "https://outlook.office.com", "exp": exp})
    monkeypatch.setattr(mod, "_save_token", lambda saved_token, saved_exp: saved_tokens.append((saved_token, saved_exp)))

    mod.cmd_fetch(headless=True)

    assert context.new_page_calls == 1
    assert temp_page.closed is True
    assert browser.closed is True
    assert saved_tokens == [(token, exp)]


def test_cmd_fetch_keeps_temporary_tab_open_in_debug_mode(monkeypatch):
    token = "outlook-token"
    exp = 1_800_000_000
    temp_page = _FakePage(token=token)
    context = _FakeContext([], temp_page)
    browser = _FakeBrowser(new_context_obj=context)
    chromium = _FakeChromium(launch_browser=browser)
    saved_tokens: list[tuple[str, int]] = []

    _install_fake_playwright(monkeypatch, chromium)
    monkeypatch.setattr("socket.socket", lambda *args, **kwargs: _FakeSocket(1))
    monkeypatch.setattr(mod, "_decode_jwt_payload", lambda _token: {"aud": "https://outlook.office.com", "exp": exp})
    monkeypatch.setattr(mod, "_save_token", lambda saved_token, saved_exp: saved_tokens.append((saved_token, saved_exp)))

    mod.cmd_fetch(headless=True, debug=True)

    assert temp_page.closed is False
    assert browser.closed is False
    assert saved_tokens == [(token, exp)]
