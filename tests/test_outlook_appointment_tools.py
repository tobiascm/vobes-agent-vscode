from pathlib import Path
import sys
from datetime import datetime


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".agents" / "skills" / "skill-outlook-termin" / "scripts"))

from outlook_appointment_tools import (  # noqa: E402
    DRAFT_PREFIX,
    _apply_standard_start,
    _default_end,
    _effective_subject,
    _build_parser,
    _resolve_recipient,
    _resolve_send_mode,
    _strip_draft_prefix,
    suggest_slots,
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


def test_build_parser_supports_suggest_slots_command():
    parser = _build_parser()
    args = parser.parse_args(
        [
            "suggest-slots",
            "--search-start",
            "2026-04-17T09:00:00",
            "--search-end",
            "2026-04-17T18:00:00",
            "--prepare-best-slot-review",
        ]
    )

    assert args.command == "suggest-slots"
    assert args.duration_min == 60
    assert args.slot_minutes == 30
    assert args.prepare_best_slot_review is True


class _FakeSlotFinder:
    DEFAULT_SUBJECT = "Neuer Termin"

    def __init__(self) -> None:
        self.open_calls = []
        self.load_calls = []
        self.find_calls = []

    def _load_reschedule_context(self, *args):
        self.load_calls.append(args)
        return {
            "source": {"entry_id": "ABC"},
            "subject": "Aus Bestand",
            "duration_minutes": 45,
            "main_participants": ["haupt@example.com"],
            "other_participants": ["optional@example.com"],
            "ignore_entry_ids": {"ABC"},
        }

    def _combine_participants(self, main_values, other_values):
        return ["combined"]

    def find_best_slots(self, **kwargs):
        self.find_calls.append(kwargs)
        return [
            type(
                "Slot",
                (),
                {
                    "start": datetime(2026, 4, 17, 11, 0),
                    "end": datetime(2026, 4, 17, 11, 45),
                    "score": 153.0,
                    "own_rank": 1,
                    "own_reason": "Kein Konflikt",
                    "participant_state": "haupt@example.com: FreeOrTentative",
                    "participant_details": ["haupt@example.com: FreeOrTentative"],
                    "needs_confirmation": False,
                },
            )()
        ]

    def open_best_slot_as_meeting(self, slot, *, subject, participants):
        self.open_calls.append((slot, subject, participants))

    def _slot_payload(self, slot):
        return {
            "start": slot.start.isoformat(),
            "end": slot.end.isoformat(),
            "score": slot.score,
            "own_rank": slot.own_rank,
            "own_reason": slot.own_reason,
            "participant_state": slot.participant_state,
            "participant_details": slot.participant_details,
            "needs_confirmation": slot.needs_confirmation,
        }


def test_suggest_slots_delegates_to_slotfinder_for_new_and_existing_appointments(monkeypatch):
    fake = _FakeSlotFinder()
    monkeypatch.setattr("outlook_appointment_tools._slotfinder_module", lambda: fake)

    fresh = suggest_slots(
        search_start="2026-04-17T09:00:00",
        search_end="2026-04-17T18:00:00",
        required=["haupt@example.com"],
        optional=["optional@example.com"],
        subject="Abstimmung",
        open_best_slot=True,
    )
    reschedule = suggest_slots(
        search_start="2026-04-17T09:00:00",
        search_end="2026-04-17T18:00:00",
        source_entry_id="ABC",
        store_id="STORE",
    )

    assert fresh["action"] == "suggest-slots"
    assert fresh["subject"] == "Abstimmung"
    assert fresh["best_slot_opened"] is True
    assert reschedule["action"] == "suggest-reschedule-slots"
    assert reschedule["subject"] == "Aus Bestand"
    assert reschedule["source_appointment"] == {"entry_id": "ABC"}
    assert fake.load_calls == [("ABC", "STORE", [], [], "", 60)]
    assert len(fake.find_calls) == 2


def test_suggest_slots_can_prepare_best_slot_review_with_standardized_start_and_preserved_duration(monkeypatch):
    fake = _FakeSlotFinder()
    create_calls = []

    def fake_create_appointment(**kwargs):
        create_calls.append(kwargs)
        return {"status": "ok", "action": "create", "appointment": {"entry_id": "NEW"}}

    monkeypatch.setattr("outlook_appointment_tools._slotfinder_module", lambda: fake)
    monkeypatch.setattr("outlook_appointment_tools.create_appointment", fake_create_appointment)

    payload = suggest_slots(
        search_start="2026-04-17T09:00:00",
        search_end="2026-04-17T18:00:00",
        required=["haupt@example.com"],
        optional=["optional@example.com"],
        subject="Abstimmung",
        prepare_best_slot_review=True,
        body="Bitte prüfen",
        location="Teams",
        teams=False,
    )

    assert payload["best_slot_review_prepared"] is True
    assert payload["prepared_appointment"] == {"status": "ok", "action": "create", "appointment": {"entry_id": "NEW"}}
    assert create_calls == [
        {
            "subject": "Abstimmung",
            "start": "2026-04-17T11:00:00",
            "duration_min": 45,
            "required": ["haupt@example.com"],
            "optional": ["optional@example.com"],
            "body": "Bitte prüfen",
            "location": "Teams",
            "teams": False,
            "send_mode": "review",
        }
    ]


def test_resolve_recipient_prefers_address_cache_before_direct(monkeypatch):
    monkeypatch.setattr(
        "outlook_appointment_tools._cache_recipient_candidates",
        lambda token, refresh_state=None: [{"name": "Martin Mustermann", "address": "martin@example.com"}],
    )
    monkeypatch.setattr(
        "outlook_appointment_tools._lazy_outlook_context",
        lambda: (_ for _ in ()).throw(AssertionError("direct resolve must not run on cache hit")),
    )

    result = _resolve_recipient("Martin Mustermann", refresh_state={})

    assert result.resolved is True
    assert result.kind == "address-cache"
    assert result.address == "martin@example.com"


def test_resolve_recipient_falls_back_to_direct_then_gal_after_cache_miss(monkeypatch):
    monkeypatch.setattr("outlook_appointment_tools._cache_recipient_candidates", lambda token, refresh_state=None: [])
    monkeypatch.setattr("outlook_appointment_tools._search_gal_candidates", lambda token: [])

    class FakeRecipient:
        def Resolve(self):
            return True

        Name = "Martin Mustermann"
        AddressEntry = object()

    class FakeNamespace:
        def CreateRecipient(self, token):
            return FakeRecipient()

    monkeypatch.setattr("outlook_appointment_tools._lazy_outlook_context", lambda: (None, FakeNamespace(), None))
    monkeypatch.setattr("outlook_appointment_tools._try_internet_address", lambda recipient: "martin@example.com")

    result = _resolve_recipient("Martin Mustermann", refresh_state={})

    assert result.resolved is True
    assert result.kind == "direct"
    assert result.address == "martin@example.com"
