import base64
import json
import sys
import time
from pathlib import Path

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[1]
        / ".agents"
        / "skills"
        / "skill-m365-copilot-mail-search"
        / "scripts"
    ),
)

import m365_mail_search_token as mod  # noqa: E402
from m365_mail_search_token import (  # noqa: E402
    TokenRecord,
    _best_graph_access_token,
    _candidate_from_cache_payload,
    _extract_balanced_json,
    _load_cached_payload,
)


def _jwt(exp: int, scopes: str, aud: str = "https://graph.microsoft.com") -> str:
    header = {"alg": "none", "typ": "JWT"}
    payload = {"exp": exp, "scp": scopes, "aud": aud}

    def _b64(data: dict) -> str:
        raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    return f"{_b64(header)}.{_b64(payload)}.sig"


def test_extract_balanced_json_from_binary_blob():
    blob = b"\x00\x01prefix" + b'{"homeAccountId":"abc","clientId":"cid","credentialType":"AccessToken","secret":"tok"}' + b"\x02suffix"
    start = blob.index(b'{"homeAccountId":"')
    raw = _extract_balanced_json(blob, start)
    assert raw is not None
    parsed = json.loads(raw.decode("utf-8"))
    assert parsed["homeAccountId"] == "abc"
    assert parsed["credentialType"] == "AccessToken"


def test_best_graph_access_token_prefers_valid_mail_scope():
    now = int(time.time())
    valid = TokenRecord(
        credential_type="AccessToken",
        secret=_jwt(now + 1800, "Mail.Read Mail.ReadWrite"),
        target="email openid profile https://graph.microsoft.com/Mail.Read",
        expires_on=now + 1800,
        home_account_id="home.tenant",
        file_path=Path("valid.ldb"),
    )
    expired = TokenRecord(
        credential_type="AccessToken",
        secret=_jwt(now - 30, "Mail.Read"),
        target="email openid profile https://graph.microsoft.com/Mail.Read",
        expires_on=now - 30,
        home_account_id="home.tenant",
        file_path=Path("expired.ldb"),
    )
    wrong_scope = TokenRecord(
        credential_type="AccessToken",
        secret=_jwt(now + 1800, "Calendars.Read"),
        target="email openid profile https://graph.microsoft.com/Calendars.Read",
        expires_on=now + 1800,
        home_account_id="home.tenant",
        file_path=Path("wrong.ldb"),
    )

    chosen = _best_graph_access_token([expired, wrong_scope, valid], ("Mail.Read",))
    assert chosen is not None
    token, _exp, source = chosen
    assert token == valid.secret
    assert source.endswith("valid.ldb")


def test_load_cached_payload_handles_wrapped_evaluate_output(tmp_path: Path, monkeypatch):
    cache_file = tmp_path / ".graph_token_cache_teams.json"
    cache_file.write_text(json.dumps(json.dumps({"token": "abc", "exp": 42, "source": "bridge"})), encoding="utf-8")
    monkeypatch.setattr(mod, "CACHE_FILE_TEAMS", cache_file)

    assert _load_cached_payload() == {"token": "abc", "exp": 42, "source": "bridge"}


def test_candidate_from_cache_payload_includes_source():
    now = int(time.time())
    candidate = _candidate_from_cache_payload(
        {"token": _jwt(now + 1800, "Mail.Read"), "exp": now + 1800, "source": "teams-bridge-cache-write"},
        ("Mail.Read",),
    )

    assert candidate is not None
    token, _exp, source = candidate
    assert token
    assert source == "teams-bridge-cache-write"


def test_resolve_via_playwright_bridge_restores_previous_cache_on_invalid_result(tmp_path: Path, monkeypatch):
    cache_file = tmp_path / ".graph_token_cache_teams.json"
    previous_raw = json.dumps({"token": "old", "exp": 1, "source": "previous"})
    cache_file.write_text(previous_raw, encoding="utf-8")
    monkeypatch.setattr(mod, "CACHE_FILE_TEAMS", cache_file)
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)

    class FakeClient:
        def __init__(self, _config):
            pass

        def start(self):
            return None

        def close(self):
            return None

    def fake_call(_client, name, arguments=None):
        if name == "browser_evaluate":
            cache_file.write_text(json.dumps(json.dumps({"error": "NO_GRAPH_TOKEN_FOUND"})), encoding="utf-8")
        return {"content": [{"type": "text", "text": "ok"}]}

    monkeypatch.setattr(mod, "McpStdioClient", FakeClient)
    monkeypatch.setattr(mod, "_load_playwright_server_config", lambda: object())
    monkeypatch.setattr(mod, "_ensure_required_tools", lambda _client: None)
    monkeypatch.setattr(mod, "_call_tool_with_retry", fake_call)
    monkeypatch.setattr(mod, "_validate_graph_token", lambda token: True)

    candidate = mod._resolve_via_playwright_bridge(("Mail.Read",), None, 0)

    assert candidate is None
    assert cache_file.read_text(encoding="utf-8") == previous_raw
