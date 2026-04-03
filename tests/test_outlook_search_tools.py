from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from outlook_search_tools import (
    EmailRef,
    _body_preview_lines,
    _cap_recipients,
    _normalize_subject,
    _score_candidate,
)


def test_cap_recipients_adds_hidden_marker_after_ten():
    values = [f"user{i}@example.com" for i in range(12)]
    actual = _cap_recipients(values)
    assert len(actual) == 11
    assert actual[:10] == values[:10]
    assert actual[-1] == "[....] 2"


def test_body_preview_lines_keeps_first_ten_nonempty_lines():
    body = "\n".join(["", "A", "B", "", "C", "D", "E", "F", "G", "H", "I", "J", "K"])
    lines, has_more = _body_preview_lines(body)
    assert lines == ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]
    assert has_more is True


def test_normalize_subject_removes_common_prefixes():
    assert _normalize_subject("AW: RE: WG: Budget Freigabe") == "Budget Freigabe"


def test_score_candidate_prefers_subject_participants_and_time():
    seed = EmailRef(
        entry_id="1",
        subject="Budget Freigabe Q3",
        sender="Alice <alice@example.com>",
        to_recipients=["Bob <bob@example.com>"],
        cc_recipients=["Carla <carla@example.com>"],
        received="2026-04-01T10:00:00+00:00",
        conversation_id="conv-1",
    )
    candidate = EmailRef(
        entry_id="2",
        subject="RE: Budget Freigabe Q3 Update",
        sender="Alice <alice@example.com>",
        to_recipients=["Bob <bob@example.com>"],
        cc_recipients=[],
        received="2026-03-28T10:00:00+00:00",
        conversation_id="conv-2",
    )

    score, reasons = _score_candidate(seed, candidate)

    assert score > 0
    assert "same participants" in reasons
    assert "same sender domain" in reasons
    assert any(reason.startswith("subject overlap:") for reason in reasons)
    assert "received within 7 days" in reasons
