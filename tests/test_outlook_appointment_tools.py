from pathlib import Path
import sys
from datetime import datetime


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".agents" / "skills" / "skill-outlook-termin" / "scripts"))

from outlook_appointment_tools import (  # noqa: E402
    DRAFT_PREFIX,
    _apply_standard_start,
    _default_end,
    _effective_subject,
    _resolve_send_mode,
    _strip_draft_prefix,
)


def test_apply_standard_start_shifts_full_and_half_hour_by_five_minutes():
    assert _apply_standard_start(datetime(2026, 4, 17, 12, 0)) == datetime(2026, 4, 17, 12, 5)
    assert _apply_standard_start(datetime(2026, 4, 17, 12, 30)) == datetime(2026, 4, 17, 12, 35)


def test_apply_standard_start_keeps_exact_custom_minutes():
    assert _apply_standard_start(datetime(2026, 4, 17, 12, 17)) == datetime(2026, 4, 17, 12, 17)


def test_default_end_uses_55_or_25_minutes():
    start = datetime(2026, 4, 17, 12, 5)
    assert _default_end(start, short_clarification=False) == datetime(2026, 4, 17, 13, 0)
    assert _default_end(start, short_clarification=True) == datetime(2026, 4, 17, 12, 30)


def test_effective_subject_applies_and_removes_draft_prefix():
    assert _effective_subject("Austausch", draft=True) == f"{DRAFT_PREFIX}Austausch"
    assert _effective_subject("Entwurf: Austausch", draft=False) == "Austausch"
    assert _strip_draft_prefix("Entwurf: Austausch") == "Austausch"


def test_resolve_send_mode_prefers_explicit_confirmation_bypass():
    assert _resolve_send_mode("", False) == "review"
    assert _resolve_send_mode("draft", False) == "draft"
    assert _resolve_send_mode("review", True) == "send"
