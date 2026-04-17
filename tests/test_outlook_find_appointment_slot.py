from pathlib import Path
import sys
from datetime import datetime, timedelta


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".agents" / "skills" / "skill-outlook-termin" / "scripts"))

from outlook_find_appointment_slot import (  # noqa: E402
    BUSY_BUSY,
    BUSY_FREE,
    BUSY_WORKING_ELSEWHERE,
    OwnSlotStatus,
    RUECKSPRACHE_MOVABLE_BONUS,
    _build_parser,
    _load_reschedule_context,
    _ruecksprache_team_participant,
    find_best_slots,
    get_own_appointment_rank,
    get_own_slot_status,
    get_participant_slot_status,
)


class FakeAppointment:
    def __init__(self, *, subject: str, categories: str = "", busy_status: int = BUSY_BUSY) -> None:
        self.Subject = subject
        self.Categories = categories
        self.BusyStatus = busy_status


class FakeRecipient:
    def __init__(self, *, name: str, address: str, recipient_type: int) -> None:
        self.Name = name
        self.Address = address
        self.Type = recipient_type


class FakeRecipients:
    def __init__(self, values: list[FakeRecipient]) -> None:
        self._values = values
        self.Count = len(values)

    def Item(self, index: int) -> FakeRecipient:
        return self._values[index - 1]


class FakeItem:
    def __init__(self) -> None:
        self.EntryID = "ABC-123"
        self.Parent = type("Parent", (), {"StoreID": "STORE-1"})()
        self.Subject = "Bestehender Termin"
        self.Start = datetime(2026, 4, 17, 9, 0)
        self.End = datetime(2026, 4, 17, 10, 0)
        self.Recipients = FakeRecipients(
            [
                FakeRecipient(name="Hauptperson", address="haupt@example.com", recipient_type=1),
                FakeRecipient(name="Optional", address="optional@example.com", recipient_type=2),
            ]
        )


def test_get_own_appointment_rank_treats_working_elsewhere_and_unknown_as_free():
    rank_we, reason_we = get_own_appointment_rank(FakeAppointment(subject="Extern", categories="Rot", busy_status=BUSY_WORKING_ELSEWHERE))
    rank_unknown, reason_unknown = get_own_appointment_rank(FakeAppointment(subject="Sonderstatus", categories="Rot", busy_status=7))

    assert rank_we == 1
    assert "Frei/Tentative" in reason_we
    assert rank_unknown == 1
    assert "ignoriert" in reason_unknown


def test_get_own_appointment_rank_respects_priority_order_for_category_blocker_and_ruecksprache():
    no_category_rank, _ = get_own_appointment_rank(FakeAppointment(subject="Termin", categories="", busy_status=BUSY_BUSY))
    blocker_rank, _ = get_own_appointment_rank(FakeAppointment(subject="Blocker Architektur", categories="Rot", busy_status=BUSY_BUSY))
    ruecksprache_rank, ruecksprache_reason = get_own_appointment_rank(FakeAppointment(subject="Rücksprache Team", categories="Gelb", busy_status=BUSY_BUSY))

    assert no_category_rank == 2
    assert blocker_rank == 3
    assert ruecksprache_rank == 4
    assert "Rücksprache" in ruecksprache_reason


def test_get_own_slot_status_uses_worst_allowed_rank_and_blocks_on_hard_conflict(monkeypatch):
    appointments = [
        FakeAppointment(subject="Ohne Kategorie", categories="", busy_status=BUSY_BUSY),
        FakeAppointment(subject="Blocker Strategie", categories="Blau", busy_status=BUSY_BUSY),
    ]
    monkeypatch.setattr(
        "outlook_find_appointment_slot.iter_overlapping_appointments",
        lambda *args, **kwargs: iter(appointments),
    )

    allowed, appts = get_own_slot_status(object(), datetime(2026, 4, 17, 9, 0), datetime(2026, 4, 17, 10, 0))
    assert allowed.allowed is True
    assert allowed.rank == 3
    assert len(appts) == 2

    blocked_items = appointments + [FakeAppointment(subject="Fixtermin", categories="Rot", busy_status=BUSY_FREE + 2)]
    monkeypatch.setattr(
        "outlook_find_appointment_slot.iter_overlapping_appointments",
        lambda *args, **kwargs: iter(blocked_items),
    )
    blocked, _ = get_own_slot_status(object(), datetime(2026, 4, 17, 9, 0), datetime(2026, 4, 17, 10, 0))
    assert blocked.allowed is False
    assert blocked.rank == 99


def test_get_participant_slot_status_treats_working_elsewhere_and_unknown_as_free():
    status = get_participant_slot_status("149", 0, 3, is_main=False)
    assert status.allowed is True
    assert status.status == "FreeOrTentative"
    assert status.needs_confirmation is False


def test_get_participant_slot_status_blocks_main_busy_and_oof_but_allows_other_busy():
    main_busy = get_participant_slot_status("012", 0, 3, is_main=True)
    other_busy = get_participant_slot_status("012", 0, 3, is_main=False)
    oof = get_participant_slot_status("103", 0, 3, is_main=False)

    assert main_busy.allowed is False
    assert main_busy.status == "BusyMain"
    assert other_busy.allowed is True
    assert other_busy.needs_confirmation is True
    assert oof.allowed is False
    assert oof.status == "OOF"


def test_load_reschedule_context_reuses_required_and_optional_attendees(monkeypatch):
    monkeypatch.setattr("outlook_find_appointment_slot._get_item_by_id", lambda entry_id, store_id="": FakeItem())

    context = _load_reschedule_context("ABC-123", "STORE-1", [], [], "", 0)

    assert context["subject"] == "Bestehender Termin"
    assert context["duration_minutes"] == 60
    assert context["main_participants"] == ["haupt@example.com"]
    assert context["other_participants"] == ["optional@example.com"]
    assert context["ignore_entry_ids"] == {"ABC-123"}


def test_parser_supports_find_and_reschedule_modes():
    parser = _build_parser()

    find_args = parser.parse_args(
        ["find", "--search-start", "2026-04-17T09:00:00", "--search-end", "2026-04-17T18:00:00"]
    )
    reschedule_args = parser.parse_args(
        [
            "reschedule",
            "--source-entry-id",
            "ABC",
            "--search-start",
            "2026-04-17T09:00:00",
            "--search-end",
            "2026-04-17T18:00:00",
        ]
    )

    assert find_args.command == "find"
    assert find_args.duration_min == 60
    assert reschedule_args.command == "reschedule"
    assert reschedule_args.source_entry_id == "ABC"


def _build_freebusy(day: datetime, busy_ranges: list[tuple[int, int]], slot_minutes: int = 30) -> str:
    """Build a FreeBusy string starting at day - 1 day (matching Outlook COM behavior).

    busy_ranges: list of (start_hour, end_hour) on the given day to mark as busy ('2').
    The string covers 29 days (1392 slots at 30-min) starting from day - 1 day midnight.
    """
    total_slots = 29 * 24 * 60 // slot_minutes
    chars = ["0"] * total_slots
    anchor = day - timedelta(days=1)
    for start_hour, end_hour in busy_ranges:
        busy_start = day.replace(hour=start_hour, minute=0)
        busy_end = day.replace(hour=end_hour, minute=0)
        start_idx = int((busy_start - anchor).total_seconds() // 60 // slot_minutes)
        end_idx = int((busy_end - anchor).total_seconds() // 60 // slot_minutes)
        for i in range(start_idx, end_idx):
            chars[i] = "2"
    return "".join(chars)


def test_find_best_slots_uses_correct_freebusy_offset(monkeypatch):
    """Regression: FreeBusy string starts 1 day before base_date.

    Simulates a participant busy 09:00-12:00 and 13:00-17:00 on 2026-04-20.
    Only 08:00-09:00, 12:00-13:00, and 17:00-18:00 should appear as free slots.
    """
    search_day = datetime(2026, 4, 20)
    search_start = search_day.replace(hour=8)
    search_end = search_day.replace(hour=18)

    freebusy = _build_freebusy(search_day, [(9, 12), (13, 17)])

    monkeypatch.setattr(
        "outlook_find_appointment_slot._calendar_folder",
        lambda: None,
    )
    monkeypatch.setattr("outlook_find_appointment_slot._prefetch_appointments", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        "outlook_find_appointment_slot._get_freebusy_string",
        lambda name, base_date, slot_minutes: freebusy,
    )

    results = find_best_slots(
        search_start=search_start,
        search_end=search_end,
        duration_minutes=30,
        slot_minutes=30,
        top_n=20,
        main_participants=["test@example.com"],
        other_participants=[],
        ignore_entry_ids=set(),
        weekdays_only=False,
        working_hour_start=8,
        working_hour_end=18,
    )

    slot_starts = {r.start for r in results}
    # Free windows: 08:00-09:00 (2 slots), 12:00-13:00 (2 slots), 17:00-18:00 (2 slots)
    expected_free = {
        datetime(2026, 4, 20, 8, 0),
        datetime(2026, 4, 20, 8, 30),
        datetime(2026, 4, 20, 12, 0),
        datetime(2026, 4, 20, 12, 30),
        datetime(2026, 4, 20, 17, 0),
        datetime(2026, 4, 20, 17, 30),
    }
    assert slot_starts == expected_free, f"Expected {expected_free}, got {slot_starts}"

    # Verify busy slots are NOT in results
    for r in results:
        assert r.start.hour not in range(9, 12), f"Slot {r.start} should be busy"
        assert r.start.hour not in range(13, 17), f"Slot {r.start} should be busy"


# -- Rücksprache-Verschiebung Tests ------------------------------------------


def test_ruecksprache_team_participant():
    assert _ruecksprache_team_participant("Rücksprache Andreas") == "andreas.krause1@volkswagen.de"
    assert _ruecksprache_team_participant("rücksprache armin") == "armin.bachmann@volkswagen.de"
    assert _ruecksprache_team_participant("Ruecksprache Fritz") == "fritz.titzmann@volkswagen.de"
    assert _ruecksprache_team_participant("Rücksprache Max") is None
    assert _ruecksprache_team_participant("Team Meeting") is None


def test_ruecksprache_shorten_removes_overlap(monkeypatch):
    """A 60-min Rücksprache can be shortened to 30 min to avoid overlap."""
    # Rücksprache Andreas 9:00-10:00 (60 min), candidate slot 9:30-10:00
    # Shorten from front: 9:00-9:30 → no overlap with 9:30 slot
    rs_appt = FakeAppointment(subject="Rücksprache Andreas", categories="Gelb", busy_status=BUSY_BUSY)
    rs_appt.EntryID = "RS-001"
    rs_appt.Start = datetime(2026, 4, 20, 9, 0)
    rs_appt.End = datetime(2026, 4, 20, 10, 0)

    search_day = datetime(2026, 4, 20)
    search_start = search_day.replace(hour=8)
    search_end = search_day.replace(hour=18)

    freebusy = _build_freebusy(search_day, [])  # participant always free

    monkeypatch.setattr("outlook_find_appointment_slot._calendar_folder", lambda: None)
    monkeypatch.setattr("outlook_find_appointment_slot._get_freebusy_string",
                        lambda name, base_date, slot_minutes: freebusy)
    monkeypatch.setattr("outlook_find_appointment_slot._prefetch_appointments", lambda *args, **kwargs: [rs_appt])

    def fake_own_status(_cached, slot_start, slot_end):
        if slot_start < datetime(2026, 4, 20, 10, 0) and slot_end > datetime(2026, 4, 20, 9, 0):
            return OwnSlotStatus(True, 4, 40, "Rücksprache: Rücksprache Andreas"), [rs_appt]
        return OwnSlotStatus(True, 1, 100, "Kein Konflikt"), []

    monkeypatch.setattr("outlook_find_appointment_slot._get_own_slot_status_cached", fake_own_status)

    results = find_best_slots(
        search_start=search_start, search_end=search_end,
        duration_minutes=30, slot_minutes=30, top_n=20,
        main_participants=["test@example.com"], other_participants=[],
        ignore_entry_ids=set(), weekdays_only=False,
        working_hour_start=8, working_hour_end=18,
    )

    # Slot at 9:30 overlaps with RS 9:00-10:00 → should have a shorten move
    slot_930 = next((r for r in results if r.start.hour == 9 and r.start.minute == 30), None)
    assert slot_930 is not None
    assert len(slot_930.ruecksprache_moves) == 1
    move = slot_930.ruecksprache_moves[0]
    # Shortened from front: 9:00-9:30 (keeps start, 30 min)
    assert move.proposed_start == datetime(2026, 4, 20, 9, 0)
    assert move.proposed_end == datetime(2026, 4, 20, 9, 30)
    assert move.proposed_end <= slot_930.start  # no more overlap


def test_find_best_slots_no_ruecksprache_moves_when_flag_false(monkeypatch):
    """check_ruecksprache_moves=False disables Rücksprache analysis."""
    rs_appt = FakeAppointment(subject="Rücksprache Andreas", categories="Gelb", busy_status=BUSY_BUSY)
    rs_appt.EntryID = "RS-002"
    rs_appt.Start = datetime(2026, 4, 20, 9, 0)
    rs_appt.End = datetime(2026, 4, 20, 10, 0)

    search_day = datetime(2026, 4, 20)
    freebusy = _build_freebusy(search_day, [])

    monkeypatch.setattr("outlook_find_appointment_slot._calendar_folder", lambda: None)
    monkeypatch.setattr("outlook_find_appointment_slot._get_freebusy_string",
                        lambda name, base_date, slot_minutes: freebusy)
    monkeypatch.setattr("outlook_find_appointment_slot._prefetch_appointments", lambda *args, **kwargs: [rs_appt])
    monkeypatch.setattr(
        "outlook_find_appointment_slot._get_own_slot_status_cached",
        lambda _cached, _start, _end: (OwnSlotStatus(True, 4, 40, "Rücksprache: Rücksprache Andreas"), [rs_appt]),
    )

    results = find_best_slots(
        search_start=search_day.replace(hour=9), search_end=search_day.replace(hour=11),
        duration_minutes=30, slot_minutes=30, top_n=5,
        main_participants=["test@example.com"], other_participants=[],
        ignore_entry_ids=set(), weekdays_only=False,
        working_hour_start=8, working_hour_end=18,
        check_ruecksprache_moves=False,
    )

    for r in results:
        assert r.ruecksprache_moves == []


def test_find_best_slots_keeps_optional_participant_when_freebusy_is_unavailable(monkeypatch):
    search_day = datetime(2026, 4, 20)
    freebusy = _build_freebusy(search_day, [])

    monkeypatch.setattr("outlook_find_appointment_slot._calendar_folder", lambda: None)
    monkeypatch.setattr("outlook_find_appointment_slot._prefetch_appointments", lambda *args, **kwargs: [])

    def fake_get_freebusy(name, base_date, slot_minutes):
        if name == "optional@example.com":
            raise RuntimeError("no freebusy")
        return freebusy

    monkeypatch.setattr("outlook_find_appointment_slot._get_freebusy_string", fake_get_freebusy)

    results = find_best_slots(
        search_start=search_day.replace(hour=9),
        search_end=search_day.replace(hour=10),
        duration_minutes=30,
        slot_minutes=30,
        top_n=5,
        main_participants=["main@example.com"],
        other_participants=["optional@example.com"],
        ignore_entry_ids=set(),
        weekdays_only=False,
        working_hour_start=8,
        working_hour_end=18,
    )

    assert results
    assert results[0].needs_confirmation is True
    assert "optional@example.com: FreeBusyUnavailable (Rückfrage nötig)" in results[0].participant_details
