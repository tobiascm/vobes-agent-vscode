"""Tests for JSON sanitization and repair in analyze_case.py."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

WORKSPACE = Path(__file__).resolve().parents[1]
SKILL_SCRIPTS = WORKSPACE / ".agents" / "skills" / "skill-m365-mail-agent" / "scripts"

if str(SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS))


# ---------------------------------------------------------------------------
# Import targets — we patch network-dependent imports so we can import
# analyze_case even without Graph tokens.
# ---------------------------------------------------------------------------

# analyze_case imports m365_mail_search at module level which may fail without
# the mail-search scripts on sys.path.  We add the expected path.
_MAIL_SEARCH_SCRIPTS = WORKSPACE / ".agents" / "skills" / "skill-m365-copilot-mail-search" / "scripts"
if str(_MAIL_SEARCH_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_MAIL_SEARCH_SCRIPTS))

from analyze_case import (  # noqa: E402
    CaseError,
    _read_json_file,
    _sanitize_json_text,
    _try_json_repair,
)


# ---------------------------------------------------------------------------
# _sanitize_json_text  (only for *broken* JSON with mismatched smart quotes)
# ---------------------------------------------------------------------------

class TestSanitizeJsonText:
    """Unit tests for _sanitize_json_text()."""

    def test_plain_ascii_unchanged(self):
        text = '{"key": "value", "num": 42}'
        assert _sanitize_json_text(text) == text

    def test_fixes_broken_german_smart_quote(self):
        """„Gesperrt" where closing " is U+0022 — the text continues after it."""
        broken = '{"p": "Status \u201eGesperrt" ist aktiv"}'
        with pytest.raises(json.JSONDecodeError):
            json.loads(broken)
        sanitized = _sanitize_json_text(broken)
        parsed = json.loads(sanitized)
        assert "\u201e" in parsed["p"]
        assert "Gesperrt" in parsed["p"]
        assert "\u201d" in parsed["p"]
        assert "ist aktiv" in parsed["p"]

    def test_fixes_multiple_smart_quote_pairs(self):
        """Multiple „..." pairs in one JSON string value."""
        broken = '{"h": "Projekte \u201eDefault\", Status \u201ein Entwicklung\"/"}'
        with pytest.raises(json.JSONDecodeError):
            json.loads(broken)
        sanitized = _sanitize_json_text(broken)
        parsed = json.loads(sanitized)
        assert "\u201eDefault\u201d" in parsed["h"]
        assert "\u201ein Entwicklung\u201d" in parsed["h"]

    def test_fixes_smart_quote_followed_by_comma_in_text(self):
        """„Default", Status — comma is text content, not JSON structure."""
        broken = '{"v": "Bordnetzprojekte \u201eDefault\", Status \u201eGesperrt\" BTV"}'
        with pytest.raises(json.JSONDecodeError):
            json.loads(broken)
        sanitized = _sanitize_json_text(broken)
        parsed = json.loads(sanitized)
        assert "Default" in parsed["v"]
        assert "Gesperrt" in parsed["v"]
        assert "BTV" in parsed["v"]

    def test_fixes_smart_quote_before_period_and_json_closer(self):
        """„VCTC"." — smart closer, then period, then actual JSON closer."""
        broken = '{"t": "Bordnetzprojekte \u201eVCTC\"."}'
        with pytest.raises(json.JSONDecodeError):
            json.loads(broken)
        sanitized = _sanitize_json_text(broken)
        parsed = json.loads(sanitized)
        assert "\u201eVCTC\u201d" in parsed["t"]
        assert parsed["t"].endswith(".")

    def test_left_double_quote_opener(self):
        """\u201c as opener (English style) with mismatched U+0022 closer."""
        broken = '{"e": "says \u201chello\" and more"}'
        with pytest.raises(json.JSONDecodeError):
            json.loads(broken)
        sanitized = _sanitize_json_text(broken)
        parsed = json.loads(sanitized)
        assert "\u201c" in parsed["e"]
        assert "hello" in parsed["e"]
        assert "and more" in parsed["e"]

    def test_guillemet_opener(self):
        """\u00ab as opener (French style) with mismatched U+0022 closer."""
        broken = '{"f": "dit \u00abbonjour\" encore"}'
        with pytest.raises(json.JSONDecodeError):
            json.loads(broken)
        sanitized = _sanitize_json_text(broken)
        parsed = json.loads(sanitized)
        assert "\u00ab" in parsed["f"]
        assert "bonjour" in parsed["f"]


# ---------------------------------------------------------------------------
# _read_json_file  (three-stage: raw → sanitized → json-repair)
# ---------------------------------------------------------------------------

class TestReadJsonFile:
    """Integration tests for _read_json_file."""

    def test_valid_json_reads_normally(self, tmp_path: Path):
        p = tmp_path / "good.json"
        p.write_text('{"hello": "world"}', encoding="utf-8")
        assert _read_json_file(p, label="test") == {"hello": "world"}

    def test_valid_json_with_smart_quotes_preserved(self, tmp_path: Path):
        """Valid JSON containing smart quotes passes through raw parsing."""
        p = tmp_path / "valid_smart.json"
        p.write_text('{"x": "Status \u201eGesperrt"}', encoding="utf-8")
        result = _read_json_file(p, label="test")
        # The value contains the literal „ (U+201E) — no closer needed for valid JSON
        assert "\u201e" in result["x"]
        assert result["x"] == "Status \u201eGesperrt"

    def test_broken_smart_quote_json_reads_after_sanitization(self, tmp_path: Path):
        p = tmp_path / "broken.json"
        p.write_text(
            '{"status": "Vorzugteilstatus \u201eGesperrt" ist aktiv"}',
            encoding="utf-8",
        )
        result = _read_json_file(p, label="test")
        assert "Gesperrt" in result["status"]
        assert "\u201e" in result["status"]
        assert "\u201d" in result["status"]

    def test_missing_file_raises_case_error(self, tmp_path: Path):
        with pytest.raises(CaseError, match="nicht gefunden"):
            _read_json_file(tmp_path / "missing.json", label="test")


# ---------------------------------------------------------------------------
# _try_json_repair
# ---------------------------------------------------------------------------

class TestTryJsonRepair:
    """Tests for the json-repair fallback path."""

    def test_repair_with_missing_module_raises(self):
        with mock.patch.dict("sys.modules", {"json_repair": None}):
            with pytest.raises(CaseError, match="json-repair ist nicht installiert"):
                _try_json_repair('{"broken": }', label="test")

    def test_repair_returns_dict_when_available(self):
        """If json-repair is installed, it should fix simple broken JSON."""
        try:
            import json_repair  # noqa: F401
        except ImportError:
            pytest.skip("json-repair not installed")
        result = _try_json_repair('{"key": "value",}', label="test")
        assert isinstance(result, dict)
        assert result["key"] == "value"


# ---------------------------------------------------------------------------
# Full-pipeline test with the real broken response
# ---------------------------------------------------------------------------

class TestRealWorldResponse:
    """Test with the actual raw_response.txt from the failed case, if available."""

    RESPONSE_PATH = (
        WORKSPACE
        / "userdata"
        / "outlook"
        / "20260416_1625_afshin.mehrsai_wg_vctc_teile_vorzugteilstatus_auf_gespe_faa78b6d"
        / "context"
        / "logs"
        / "raw_response.txt"
    )

    @pytest.mark.skipif(
        not RESPONSE_PATH.exists(),
        reason="raw_response.txt not available in workspace",
    )
    def test_extract_and_parse_real_json(self):
        """Extract the JSON code block from the real response and parse it."""
        import re

        content = self.RESPONSE_PATH.read_text(encoding="utf-8")
        m = re.search(r"```json\s*(\{.*)\}\s*```", content, re.DOTALL)
        assert m, "No ```json code block found in raw_response.txt"
        raw_json = m.group(1) + "}"

        # Confirm it's actually broken without sanitization
        with pytest.raises(json.JSONDecodeError):
            json.loads(raw_json)

        # Sanitize and parse
        sanitized = _sanitize_json_text(raw_json)
        parsed = json.loads(sanitized)

        # Verify key structure
        assert "summary" in parsed
        assert "decision" in parsed
        assert "actions" in parsed
        assert isinstance(parsed["actions"], list)
        assert len(parsed["actions"]) >= 1
        assert parsed["summary"]["core_topic"]
