from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
OUTLOOK_SEARCH_DIR = SCRIPT_DIR.parents[1] / "skill-outlook" / "scripts"
for _p in (str(SCRIPT_DIR), str(OUTLOOK_SEARCH_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from outlook_appointment_tools import _parse_local_datetime, _resolve_recipient  # noqa: E402
from outlook_search_tools import (  # noqa: E402
    _com_to_local,
    _coerce_text,
    _get_item_by_id,
    _lazy_outlook_context,
    _safe_get,
    _try_internet_address,
)

OL_FOLDER_CALENDAR = 9
OL_APPOINTMENT_ITEM = 1
OL_MEETING = 1
OL_NON_MEETING = 0

BUSY_FREE = 0
BUSY_TENTATIVE = 1
BUSY_BUSY = 2
BUSY_OOF = 3
BUSY_WORKING_ELSEWHERE = 4

OWN_RANK_SCORE = {
    1: 100,
    2: 80,
    3: 60,
    4: 40,
}

PARTICIPANT_SCORE = {
    "main_free": 50,
    "other_free": 10,
    "other_busy": 3,
}

SHORTER_SLOT_PENALTY = -50
EDGE_HOURS_PENALTY = -80
EDGE_HOUR_EARLY = (8, 30)   # before 08:30
EDGE_HOUR_LATE = (17, 0)    # at or after 17:00
EDGE_FRIDAY_LATE = (14, 0)  # Friday at or after 14:00
RUECKSPRACHE_MOVABLE_BONUS = 15

TEAM_FIRST_NAMES: dict[str, str] = {
    "armin": "armin.bachmann@volkswagen.de", "timo": "timo.bartels@volkswagen.de",
    "ralf": "ralf.gemmerich@volkswagen.de", "christian": "christian.junge@volkswagen.de",
    "andreas": "andreas.krause1@volkswagen.de", "afshin": "afshin.mehrsai@volkswagen.de",
    "heide": "heide.melchior@volkswagen.de", "donato": "donato.sciaraffia@volkswagen.de",
    "frank": "frank.syring@volkswagen.de", "fritz": "fritz.titzmann@volkswagen.de",
}

DEFAULT_SUBJECT = "Neuer Termin"


@dataclass
class Participant:
    name: str
    is_main: bool


@dataclass
class OwnSlotStatus:
    allowed: bool
    rank: int
    score: float
    reason: str


@dataclass
class ParticipantSlotStatus:
    allowed: bool
    status: str
    score: float
    needs_confirmation: bool = False


@dataclass
class RueckspracheMove:
    entry_id: str
    subject: str
    original_start: datetime
    original_end: datetime
    participant: str
    proposed_start: datetime
    proposed_end: datetime


@dataclass
class _CachedAppointment:
    """In-memory snapshot of an Outlook appointment for fast slot checks."""
    entry_id: str
    subject: str
    start: datetime
    end: datetime
    busy_status: int
    categories: str
    message_class: str
    all_day: bool
    _com_ref: Any = field(repr=False, default=None)


@dataclass
class SlotResult:
    start: datetime
    end: datetime
    score: float
    own_rank: int
    own_reason: str
    participant_state: str
    participant_details: list[str] = field(default_factory=list)
    needs_confirmation: bool = False
    is_shorter_alternative: bool = False
    ruecksprache_moves: list[RueckspracheMove] = field(default_factory=list)


def _normalize_text(value: str) -> str:
    return _coerce_text(value).strip().lower()


def _to_py_datetime(value: Any) -> datetime:
    # Outlook COM appointment times already expose the local wall-clock
    # components we want. The attached tzinfo can be misleading for
    # appointments and shifts values by +2h when passed through
    # astimezone() during CEST.
    value = _com_to_local(value)
    return datetime(
        int(value.year),
        int(value.month),
        int(value.day),
        int(value.hour),
        int(value.minute),
        int(value.second),
    )


def _calendar_folder() -> Any:
    _, namespace, _ = _lazy_outlook_context()
    return namespace.GetDefaultFolder(OL_FOLDER_CALENDAR)


def _format_outlook_filter_datetime(value: datetime) -> str:
    return value.strftime("%m/%d/%Y %I:%M %p")


def _subject_is_blocker(subject: str) -> bool:
    return "blocker" in _normalize_text(subject)


def _subject_is_ruecksprache(subject: str) -> bool:
    normalized = _normalize_text(subject)
    return "rücksprache" in normalized or "ruecksprache" in normalized


def _ruecksprache_team_participant(subject: str) -> str | None:
    n = _normalize_text(subject)
    for pfx in ("rücksprache ", "ruecksprache "):
        if n.startswith(pfx):
            return TEAM_FIRST_NAMES.get(n[len(pfx):].strip())
    return None


def _unique_participants(values: list[str], *, is_main: bool) -> list[Participant]:
    result: list[Participant] = []
    seen: set[str] = set()
    for value in values:
        text = _coerce_text(value).strip()
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(Participant(name=text, is_main=is_main))
    return result


def _combine_participants(main_values: list[str], other_values: list[str]) -> list[Participant]:
    main_participants = _unique_participants(main_values, is_main=True)
    other_seen = {participant.name.lower() for participant in main_participants}
    participants = list(main_participants)
    for participant in _unique_participants(other_values, is_main=False):
        if participant.name.lower() in other_seen:
            continue
        participants.append(participant)
    return participants


def _recipient_to_text(recipient: Any) -> str:
    address = _coerce_text(_try_internet_address(recipient)).strip()
    if address:
        return address
    return _coerce_text(_safe_get(recipient, "Name", "")).strip()


def _participants_from_appointment(item: Any) -> tuple[list[str], list[str]]:
    required: list[str] = []
    optional: list[str] = []
    recipients = _safe_get(item, "Recipients")
    count = int(_safe_get(recipients, "Count", 0) or 0)
    for index in range(1, count + 1):
        try:
            recipient = recipients.Item(index)
        except Exception:
            continue
        value = _recipient_to_text(recipient)
        if not value:
            continue
        recipient_type = int(_safe_get(recipient, "Type", 0) or 0)
        if recipient_type == 2:
            optional.append(value)
        else:
            required.append(value)
    return required, optional


def _appointment_summary(item: Any) -> dict[str, Any]:
    required, optional = _participants_from_appointment(item)
    start = _to_py_datetime(_safe_get(item, "Start"))
    end = _to_py_datetime(_safe_get(item, "End"))
    return {
        "entry_id": _coerce_text(_safe_get(item, "EntryID", "")),
        "store_id": _coerce_text(_safe_get(_safe_get(item, "Parent"), "StoreID", "")),
        "subject": _coerce_text(_safe_get(item, "Subject", "")),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "duration_minutes": int((end - start).total_seconds() // 60),
        "required_participants": required,
        "optional_participants": optional,
    }


def _load_reschedule_context(
    entry_id: str,
    store_id: str,
    explicit_main: list[str],
    explicit_other: list[str],
    subject_override: str,
    duration_override: int,
) -> dict[str, Any]:
    item = _get_item_by_id(entry_id, store_id)
    summary = _appointment_summary(item)
    main_values = explicit_main or summary["required_participants"]
    other_values = explicit_other or summary["optional_participants"]
    return {
        "source": summary,
        "subject": _coerce_text(subject_override).strip() or summary["subject"] or DEFAULT_SUBJECT,
        "duration_minutes": duration_override or summary["duration_minutes"],
        "main_participants": main_values,
        "other_participants": other_values,
        "ignore_entry_ids": {entry_id},
    }


def _is_candidate_time(
    start: datetime,
    end: datetime,
    *,
    weekdays_only: bool,
    working_hour_start: int,
    working_hour_end: int,
) -> bool:
    if weekdays_only and start.weekday() >= 5:
        return False
    if start.date() != end.date():
        return False
    start_minutes = start.hour * 60 + start.minute
    end_minutes = end.hour * 60 + end.minute
    if start_minutes < working_hour_start * 60:
        return False
    if end_minutes > working_hour_end * 60:
        return False
    return True


def iter_overlapping_appointments(
    calendar_folder: Any,
    start: datetime,
    end: datetime,
    ignore_entry_ids: set[str] | None = None,
) -> Iterable[Any]:
    ignored = {value for value in (ignore_entry_ids or set()) if value}
    items = calendar_folder.Items
    items.Sort("[Start]")
    items.IncludeRecurrences = True
    try:
        start_text = _format_outlook_filter_datetime(start)
        end_text = _format_outlook_filter_datetime(end)
        items = items.Restrict(f"[Start] < '{end_text}' AND [End] > '{start_text}'")
    except Exception:
        pass
    for item in items:
        try:
            if not str(_safe_get(item, "MessageClass", "")).startswith("IPM.Appointment"):
                continue
            entry_id = _coerce_text(_safe_get(item, "EntryID", ""))
            if entry_id and entry_id in ignored:
                continue
            item_start = _to_py_datetime(_safe_get(item, "Start"))
            item_end = _to_py_datetime(_safe_get(item, "End"))
            if item_end <= start:
                continue
            if item_start >= end:
                break
            yield item
        except Exception:
            continue


def get_own_appointment_rank(appt: Any) -> tuple[int, str]:
    subject = _coerce_text(_safe_get(appt, "Subject", ""))
    categories = _coerce_text(_safe_get(appt, "Categories", ""))
    raw_busy = _safe_get(appt, "BusyStatus", None)
    busy_status = int(raw_busy) if raw_busy is not None else BUSY_BUSY

    if busy_status in (BUSY_FREE, BUSY_TENTATIVE, BUSY_WORKING_ELSEWHERE):
        return 1, f"Frei/Tentative: {subject}"
    if busy_status not in (BUSY_BUSY, BUSY_OOF):
        return 1, f"Frei/Tentative (Status ignoriert): {subject}"
    if not categories.strip():
        return 2, f"Keine Kategorie: {subject}"
    if _subject_is_blocker(subject):
        return 3, f"Blocker: {subject}"
    if _subject_is_ruecksprache(subject):
        return 4, f"Rücksprache: {subject}"
    return 99, f"Nicht verschiebbar: {subject}"


def get_own_slot_status(
    calendar_folder: Any,
    start: datetime,
    end: datetime,
    *,
    ignore_entry_ids: set[str] | None = None,
) -> tuple[OwnSlotStatus, list[Any]]:
    appointments = list(iter_overlapping_appointments(calendar_folder, start, end, ignore_entry_ids))
    if not appointments:
        return OwnSlotStatus(True, 1, OWN_RANK_SCORE[1], "Kein Konflikt"), []

    ranks: list[int] = []
    reasons: list[str] = []
    for appt in appointments:
        rank, reason = get_own_appointment_rank(appt)
        ranks.append(rank)
        reasons.append(reason)
    if 99 in ranks:
        return OwnSlotStatus(False, 99, -1000, " | ".join(reasons)), appointments
    worst_rank = max(ranks)
    return OwnSlotStatus(True, worst_rank, OWN_RANK_SCORE[worst_rank], " | ".join(reasons)), appointments


# -- Prefetch helpers for batch slot searches (avoids repeated COM queries) ----

def _prefetch_appointments(
    calendar_folder: Any,
    range_start: datetime,
    range_end: datetime,
    ignore_entry_ids: set[str] | None = None,
) -> list[_CachedAppointment]:
    """Load all appointments in [range_start, range_end) once into memory.

    Categories and EntryID are expensive COM properties (~25s overhead for 79
    items).  We defer Categories: only read it when BusyStatus is Busy/OOF,
    because Free/Tentative items always get Rank 1 regardless of categories.
    EntryID is only needed for ignore-filtering and Rücksprache moves.
    """
    ignored = {v for v in (ignore_entry_ids or set()) if v}
    need_eid_filter = bool(ignored)
    items = calendar_folder.Items
    items.Sort("[Start]")
    items.IncludeRecurrences = True
    try:
        start_text = _format_outlook_filter_datetime(range_start)
        end_text = _format_outlook_filter_datetime(range_end)
        items = items.Restrict(f"[Start] < '{end_text}' AND [End] > '{start_text}'")
    except Exception:
        pass
    result: list[_CachedAppointment] = []
    item = items.GetFirst()
    while item is not None:
        try:
            item_start = _to_py_datetime(item.Start)
            item_end = _to_py_datetime(item.End)
            if item_end <= range_start:
                item = items.GetNext()
                continue
            if item_start >= range_end:
                break
            subject = str(item.Subject or "")
            raw_busy = item.BusyStatus
            busy_status = int(raw_busy) if raw_busy is not None else BUSY_BUSY
            # Expensive properties — only read when needed
            eid = ""
            if need_eid_filter:
                eid = str(item.EntryID or "")
                if eid in ignored:
                    item = items.GetNext()
                    continue
            categories = ""
            if busy_status in (BUSY_BUSY, BUSY_OOF):
                categories = str(item.Categories or "")
            result.append(_CachedAppointment(
                entry_id=eid,
                subject=subject,
                start=item_start,
                end=item_end,
                busy_status=busy_status,
                categories=categories,
                message_class="IPM.Appointment",
                all_day=item_end - item_start >= timedelta(hours=23),
                _com_ref=item,
            ))
        except Exception:
            pass
        item = items.GetNext()
    return result


def _rank_cached(appt: _CachedAppointment) -> tuple[int, str]:
    """Same logic as get_own_appointment_rank but for cached data."""
    if appt.busy_status in (BUSY_FREE, BUSY_TENTATIVE, BUSY_WORKING_ELSEWHERE):
        return 1, f"Frei/Tentative: {appt.subject}"
    if appt.busy_status not in (BUSY_BUSY, BUSY_OOF):
        return 1, f"Frei/Tentative (Status ignoriert): {appt.subject}"
    if not appt.categories.strip():
        return 2, f"Keine Kategorie: {appt.subject}"
    if _subject_is_blocker(appt.subject):
        return 3, f"Blocker: {appt.subject}"
    if _subject_is_ruecksprache(appt.subject):
        return 4, f"Rücksprache: {appt.subject}"
    return 99, f"Nicht verschiebbar: {appt.subject}"


def _get_own_slot_status_cached(
    cached: list[_CachedAppointment],
    slot_start: datetime,
    slot_end: datetime,
) -> tuple[OwnSlotStatus, list[_CachedAppointment]]:
    """Fast in-memory variant of get_own_slot_status."""
    overlapping = [a for a in cached if a.start < slot_end and a.end > slot_start]
    if not overlapping:
        return OwnSlotStatus(True, 1, OWN_RANK_SCORE[1], "Kein Konflikt"), []
    ranks: list[int] = []
    reasons: list[str] = []
    for appt in overlapping:
        rank, reason = _rank_cached(appt)
        ranks.append(rank)
        reasons.append(reason)
    if 99 in ranks:
        return OwnSlotStatus(False, 99, -1000, " | ".join(reasons)), overlapping
    worst_rank = max(ranks)
    return OwnSlotStatus(True, worst_rank, OWN_RANK_SCORE[worst_rank], " | ".join(reasons)), overlapping


def _resolved_target(name_or_mail: str) -> str:
    resolved = _resolve_recipient(name_or_mail)
    if not resolved.resolved:
        raise RuntimeError(f"Empfänger nicht auflösbar: {name_or_mail}")
    return resolved.target or resolved.address or resolved.name or name_or_mail


def _get_freebusy_string(name_or_mail: str, base_date: datetime, slot_minutes: int) -> str:
    _, namespace, _ = _lazy_outlook_context()
    target = _resolved_target(name_or_mail)
    recipient = namespace.CreateRecipient(target)
    recipient.Resolve()
    if not recipient.Resolved:
        raise RuntimeError(f"Empfänger nicht auflösbar: {name_or_mail}")
    return _coerce_text(recipient.AddressEntry.GetFreeBusy(base_date, slot_minutes, True))


def get_participant_slot_status(
    freebusy_string: str,
    offset: int,
    duration_slots: int,
    *,
    is_main: bool,
) -> ParticipantSlotStatus:
    if offset < 0 or offset + duration_slots > len(freebusy_string):
        return ParticipantSlotStatus(False, "OutOfRange", -1000)

    segment = freebusy_string[offset:offset + duration_slots]
    if "3" in segment:
        return ParticipantSlotStatus(False, "OOF", -1000)
    if is_main and "2" in segment:
        return ParticipantSlotStatus(False, "BusyMain", -1000)
    if "2" in segment:
        return ParticipantSlotStatus(True, "Busy", PARTICIPANT_SCORE["other_busy"], needs_confirmation=True)
    score_key = "main_free" if is_main else "other_free"
    return ParticipantSlotStatus(True, "FreeOrTentative", PARTICIPANT_SCORE[score_key], needs_confirmation=False)


def _participant_status(
    freebusy_string: str | None,
    offset: int,
    duration_slots: int,
    *,
    is_main: bool,
) -> ParticipantSlotStatus:
    if freebusy_string is None:
        if is_main:
            return ParticipantSlotStatus(False, "FreeBusyUnavailable", -1000)
        return ParticipantSlotStatus(True, "FreeBusyUnavailable", 0, needs_confirmation=True)
    return get_participant_slot_status(
        freebusy_string,
        offset,
        duration_slots,
        is_main=is_main,
    )


def _try_ruecksprache_move(
    appt: Any,
    slot_start: datetime,
    slot_end: datetime,
    calendar_folder: Any,
    slot_minutes: int,
    working_hour_start: int,
    working_hour_end: int,
    ignore_entry_ids: set[str] | None,
    rs_cache: dict[str, RueckspracheMove | None],
    _prefetch_cache: list[_CachedAppointment] | None = None,
    _freebusy_cache: dict[str, str] | None = None,
) -> RueckspracheMove | None:
    # Support both COM objects and _CachedAppointment
    if isinstance(appt, _CachedAppointment):
        rank, _ = _rank_cached(appt)
        if rank != 4:
            return None
        subject = appt.subject
        participant = _ruecksprache_team_participant(subject)
        if not participant:
            return None
        eid = appt.entry_id
        rs_start = appt.start
        rs_end = appt.end
    else:
        rank, _ = get_own_appointment_rank(appt)
        if rank != 4:
            return None
        subject = _coerce_text(_safe_get(appt, "Subject", ""))
        participant = _ruecksprache_team_participant(subject)
        if not participant:
            return None
        eid = _coerce_text(_safe_get(appt, "EntryID", ""))
        rs_start = _to_py_datetime(_safe_get(appt, "Start"))
        rs_end = _to_py_datetime(_safe_get(appt, "End"))
    rs_dur = int((rs_end - rs_start).total_seconds() // 60)

    def _make_move(p_start: datetime, p_end: datetime) -> RueckspracheMove:
        return RueckspracheMove(eid, subject, rs_start, rs_end, participant, p_start, p_end)

    # Variante 1: Kürzen am Platz (nur wenn länger als slot_minutes)
    if rs_dur > slot_minutes:
        short_end = rs_start + timedelta(minutes=slot_minutes)
        if short_end <= slot_start:
            return _make_move(rs_start, short_end)
        short_start = rs_end - timedelta(minutes=slot_minutes)
        if short_start >= slot_end:
            return _make_move(short_start, rs_end)

    # Variante 2: Verschieben (rekursiv, gecacht pro entry_id)
    cache_key = eid or f"{subject}|{rs_start.isoformat()}"
    if cache_key not in rs_cache:
        # Aufrunden auf nächstes Vielfaches von slot_minutes
        search_dur = ((rs_dur + slot_minutes - 1) // slot_minutes) * slot_minutes
        week_mon = (rs_start - timedelta(days=rs_start.weekday())).replace(
            hour=working_hour_start, minute=0, second=0, microsecond=0)
        week_fri = (week_mon + timedelta(days=4)).replace(hour=working_hour_end)
        alt = find_best_slots(
            search_start=week_mon, search_end=week_fri,
            duration_minutes=search_dur, slot_minutes=slot_minutes, top_n=1,
            main_participants=[participant], other_participants=[],
            ignore_entry_ids={eid} | (ignore_entry_ids or set()),
            weekdays_only=True, working_hour_start=working_hour_start,
            working_hour_end=working_hour_end, include_shorter_slots=True,
            check_ruecksprache_moves=False,
            _prefetch_cache=_prefetch_cache,
            _freebusy_cache=_freebusy_cache,
        )
        rs_cache[cache_key] = _make_move(alt[0].start, alt[0].end) if alt else None
    return rs_cache[cache_key]


def find_best_slots(
    *,
    search_start: datetime,
    search_end: datetime,
    duration_minutes: int,
    slot_minutes: int,
    top_n: int,
    main_participants: list[str],
    other_participants: list[str],
    ignore_entry_ids: set[str] | None = None,
    weekdays_only: bool,
    working_hour_start: int,
    working_hour_end: int,
    include_shorter_slots: bool = True,
    check_ruecksprache_moves: bool = True,
    _prefetch_cache: list[_CachedAppointment] | None = None,
    _freebusy_cache: dict[str, str] | None = None,
) -> list[SlotResult]:
    if duration_minutes <= 0:
        raise ValueError("duration_minutes muss > 0 sein.")
    if slot_minutes <= 0:
        raise ValueError("slot_minutes muss > 0 sein.")
    if duration_minutes % slot_minutes != 0:
        raise ValueError("duration_minutes muss ein Vielfaches von slot_minutes sein.")

    base_date = search_start.replace(hour=0, minute=0, second=0, microsecond=0)
    # Outlook COM GetFreeBusy returns a string that starts 1 day before
    # the given base_date (empirically verified). Offset calculations must
    # use this anchor so that FreeBusy positions map to the correct times.
    freebusy_anchor = base_date - timedelta(days=1)
    if search_end > freebusy_anchor + timedelta(days=29):
        raise ValueError("GetFreeBusy deckt nur 30 Tage ab. Suchfenster ist zu groß.")

    # Shared FreeBusy cache across recursive calls
    if _freebusy_cache is None:
        _freebusy_cache = {}

    duration_slots = duration_minutes // slot_minutes
    calendar_folder = _calendar_folder()
    participants = _combine_participants(main_participants, other_participants)
    for participant in participants:
        if participant.name not in _freebusy_cache:
            try:
                _freebusy_cache[participant.name] = _get_freebusy_string(
                    participant.name, base_date, slot_minutes)
            except Exception:
                _freebusy_cache[participant.name] = None
    freebusy_map = {p.name: _freebusy_cache[p.name] for p in participants}

    # Prefetch all own appointments (reuse cache from parent call if available)
    if _prefetch_cache is not None:
        cached_appts = _prefetch_cache
    else:
        cached_appts = _prefetch_appointments(calendar_folder, search_start, search_end, ignore_entry_ids)

    rs_cache: dict[str, RueckspracheMove | None] = {}
    results: list[SlotResult] = []
    slot_start = search_start
    while slot_start + timedelta(minutes=duration_minutes) <= search_end:
        slot_end = slot_start + timedelta(minutes=duration_minutes)
        if not _is_candidate_time(
            slot_start,
            slot_end,
            weekdays_only=weekdays_only,
            working_hour_start=working_hour_start,
            working_hour_end=working_hour_end,
        ):
            slot_start += timedelta(minutes=slot_minutes)
            continue

        own_status, own_appts = _get_own_slot_status_cached(
            cached_appts,
            slot_start,
            slot_end,
        )
        if not own_status.allowed:
            slot_start += timedelta(minutes=slot_minutes)
            continue

        offset = int((slot_start - freebusy_anchor).total_seconds() // 60 // slot_minutes)
        score = float(own_status.score)
        # Penalty for edge hours (before 08:30, at/after 17:00, or Friday at/after 14:00)
        start_hm = (slot_start.hour, slot_start.minute)
        is_friday = slot_start.weekday() == 4
        if start_hm < EDGE_HOUR_EARLY or start_hm >= EDGE_HOUR_LATE or (is_friday and start_hm >= EDGE_FRIDAY_LATE):
            score += EDGE_HOURS_PENALTY
        allowed = True
        needs_confirmation = False
        participant_details: list[str] = []
        rs_moves: list[RueckspracheMove] = []

        if check_ruecksprache_moves and own_status.rank == 4:
            for appt in own_appts:
                move = _try_ruecksprache_move(
                    appt, slot_start, slot_end, calendar_folder, slot_minutes,
                    working_hour_start, working_hour_end, ignore_entry_ids, rs_cache,
                    _prefetch_cache=cached_appts, _freebusy_cache=_freebusy_cache)
                if move:
                    rs_moves.append(move)
            score += RUECKSPRACHE_MOVABLE_BONUS * len(rs_moves)
            if rs_moves:
                needs_confirmation = True

        for participant in participants:
            status = _participant_status(
                freebusy_map[participant.name],
                offset,
                duration_slots,
                is_main=participant.is_main,
            )
            if not status.allowed:
                participant_details.append(f"{participant.name}: {status.status}")
                allowed = False
                break
            score += status.score
            needs_confirmation = needs_confirmation or status.needs_confirmation
            suffix = " (Rückfrage nötig)" if status.needs_confirmation else ""
            participant_details.append(f"{participant.name}: {status.status}{suffix}")

        if allowed:
            results.append(
                SlotResult(
                    start=slot_start,
                    end=slot_end,
                    score=round(score, 2),
                    own_rank=own_status.rank,
                    own_reason=own_status.reason,
                    participant_state=" | ".join(participant_details) if participant_details else "Keine Teilnehmerprüfung",
                    participant_details=participant_details,
                    needs_confirmation=needs_confirmation,
                    ruecksprache_moves=rs_moves,
                )
            )

        slot_start += timedelta(minutes=slot_minutes)

    # -- Fallback: kürzere Slots (slot_minutes Dauer) mit Penalty-Score ------
    shorter_duration = slot_minutes
    if include_shorter_slots and duration_minutes > shorter_duration and len(results) < top_n:
        shorter_duration_slots = 1  # exactly one slot_minutes block
        seen_starts = {r.start for r in results}
        slot_start = search_start
        while slot_start + timedelta(minutes=shorter_duration) <= search_end:
            slot_end = slot_start + timedelta(minutes=shorter_duration)
            if slot_start in seen_starts:
                slot_start += timedelta(minutes=slot_minutes)
                continue
            if not _is_candidate_time(
                slot_start,
                slot_end,
                weekdays_only=weekdays_only,
                working_hour_start=working_hour_start,
                working_hour_end=working_hour_end,
            ):
                slot_start += timedelta(minutes=slot_minutes)
                continue

            own_status, own_appts = _get_own_slot_status_cached(
                cached_appts,
                slot_start,
                slot_end,
            )
            if not own_status.allowed:
                slot_start += timedelta(minutes=slot_minutes)
                continue

            offset = int((slot_start - freebusy_anchor).total_seconds() // 60 // slot_minutes)
            score = float(own_status.score) + SHORTER_SLOT_PENALTY
            # Penalty for edge hours (before 08:30, at/after 17:00, or Friday at/after 14:00)
            start_hm = (slot_start.hour, slot_start.minute)
            is_friday = slot_start.weekday() == 4
            if start_hm < EDGE_HOUR_EARLY or start_hm >= EDGE_HOUR_LATE or (is_friday and start_hm >= EDGE_FRIDAY_LATE):
                score += EDGE_HOURS_PENALTY
            allowed = True
            needs_confirmation = False
            participant_details_short: list[str] = []
            rs_moves_short: list[RueckspracheMove] = []

            if check_ruecksprache_moves and own_status.rank == 4:
                for appt in own_appts:
                    move = _try_ruecksprache_move(
                        appt, slot_start, slot_end, calendar_folder, slot_minutes,
                        working_hour_start, working_hour_end, ignore_entry_ids, rs_cache,
                        _prefetch_cache=cached_appts, _freebusy_cache=_freebusy_cache)
                    if move:
                        rs_moves_short.append(move)
                score += RUECKSPRACHE_MOVABLE_BONUS * len(rs_moves_short)
                if rs_moves_short:
                    needs_confirmation = True

            for participant in participants:
                status = _participant_status(
                    freebusy_map[participant.name],
                    offset,
                    shorter_duration_slots,
                    is_main=participant.is_main,
                )
                if not status.allowed:
                    participant_details_short.append(f"{participant.name}: {status.status}")
                    allowed = False
                    break
                score += status.score
                needs_confirmation = needs_confirmation or status.needs_confirmation
                suffix = " (Rückfrage nötig)" if status.needs_confirmation else ""
                participant_details_short.append(f"{participant.name}: {status.status}{suffix}")

            if allowed:
                results.append(
                    SlotResult(
                        start=slot_start,
                        end=slot_end,
                        score=round(score, 2),
                        own_rank=own_status.rank,
                        own_reason=own_status.reason,
                        participant_state=" | ".join(participant_details_short) if participant_details_short else "Keine Teilnehmerprüfung",
                        participant_details=participant_details_short,
                        needs_confirmation=needs_confirmation,
                        is_shorter_alternative=True,
                        ruecksprache_moves=rs_moves_short,
                    )
                )

            slot_start += timedelta(minutes=slot_minutes)

    results.sort(key=lambda item: (-item.score, item.needs_confirmation, item.own_rank, item.start))
    return results[:top_n]


def _slot_payload(slot: SlotResult) -> dict[str, Any]:
    payload = asdict(slot)
    payload["start"] = slot.start.isoformat()
    payload["end"] = slot.end.isoformat()
    for move in payload.get("ruecksprache_moves", []):
        for key in ("original_start", "original_end", "proposed_start", "proposed_end"):
            move[key] = move[key].isoformat()
    return payload


def open_best_slot_as_meeting(slot: SlotResult, *, subject: str, participants: list[Participant]) -> None:
    app, _, _ = _lazy_outlook_context()
    appt = app.CreateItem(OL_APPOINTMENT_ITEM)
    appt.Start = slot.start
    appt.End = slot.end
    appt.Subject = subject or DEFAULT_SUBJECT
    appt.MeetingStatus = OL_MEETING if participants else OL_NON_MEETING
    for participant in participants:
        appt.Recipients.Add(participant.name)
    appt.Recipients.ResolveAll()
    appt.Display()


def _print_results(results: list[SlotResult]) -> None:
    if not results:
        print("Keine passenden Slots gefunden.")
        return
    print()
    print("Beste Slots:")
    print("-" * 120)
    for index, slot in enumerate(results, start=1):
        shorter_tag = " [KÜRZER]" if slot.is_shorter_alternative else ""
        print(
            f"{index:2d}. {slot.start:%d.%m.%Y %H:%M} - {slot.end:%H:%M} | "
            f"Score={slot.score:6.1f} | OwnRank={slot.own_rank} | "
            f"Rückfrage={'ja' if slot.needs_confirmation else 'nein'}{shorter_tag}"
        )
        print(f"    Eigener Kalender : {slot.own_reason}")
        print(f"    Teilnehmer       : {slot.participant_state}")
        for move in slot.ruecksprache_moves:
            print(f"    \u21bb {move.subject}  {move.original_start:%d.%m. %H:%M}-{move.original_end:%H:%M}"
                  f" \u2192 {move.proposed_start:%d.%m. %H:%M}-{move.proposed_end:%H:%M}")
        print("-" * 120)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Finde passende Outlook-Termin-Slots auf Basis von Classic Outlook COM.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_search_arguments(command: argparse.ArgumentParser) -> None:
        command.add_argument("--search-start", required=True, help="ISO-Datetime fuer den Suchstart.")
        command.add_argument("--search-end", required=True, help="ISO-Datetime fuer das Suchende.")
        command.add_argument("--slot-minutes", type=int, default=30)
        command.add_argument("--top-n", type=int, default=10)
        command.add_argument("--working-hour-start", type=int, default=8)
        command.add_argument("--working-hour-end", type=int, default=18)
        command.add_argument("--include-weekends", action="store_true")
        command.add_argument("--open-best-slot", action="store_true")
        command.add_argument("--json", action="store_true")

    find_parser = subparsers.add_parser("find", help="Finde Slots fuer einen neuen Termin.")
    add_search_arguments(find_parser)
    find_parser.add_argument("--duration-min", type=int, default=60)
    find_parser.add_argument("--subject", default=DEFAULT_SUBJECT)
    find_parser.add_argument("--main", action="append", default=[])
    find_parser.add_argument("--other", action="append", default=[])
    find_parser.add_argument("--no-shorter-slots", dest="include_shorter_slots", action="store_false", default=True,
                             help="Keine kuerzeren Alternativ-Slots anzeigen.")

    reschedule_parser = subparsers.add_parser("reschedule", help="Finde Slots fuer einen bestehenden Termin.")
    add_search_arguments(reschedule_parser)
    reschedule_parser.add_argument("--source-entry-id", required=True)
    reschedule_parser.add_argument("--store-id", default="")
    reschedule_parser.add_argument("--duration-min", type=int, default=0)
    reschedule_parser.add_argument("--subject", default="")
    reschedule_parser.add_argument("--main", action="append", default=[])
    reschedule_parser.add_argument("--other", action="append", default=[])
    reschedule_parser.add_argument("--no-shorter-slots", dest="include_shorter_slots", action="store_false", default=True,
                                   help="Keine kuerzeren Alternativ-Slots anzeigen.")
    return parser


def _run_find(args: argparse.Namespace) -> dict[str, Any]:
    search_start = _parse_local_datetime(args.search_start)
    search_end = _parse_local_datetime(args.search_end)
    participants = _combine_participants(args.main, args.other)
    results = find_best_slots(
        search_start=search_start,
        search_end=search_end,
        duration_minutes=args.duration_min,
        slot_minutes=args.slot_minutes,
        top_n=args.top_n,
        main_participants=args.main,
        other_participants=args.other,
        ignore_entry_ids=set(),
        weekdays_only=not args.include_weekends,
        working_hour_start=args.working_hour_start,
        working_hour_end=args.working_hour_end,
        include_shorter_slots=args.include_shorter_slots,
    )
    if args.open_best_slot and results:
        open_best_slot_as_meeting(results[0], subject=args.subject, participants=participants)
    return {
        "status": "ok",
        "action": "find",
        "subject": args.subject,
        "criteria": {
            "search_start": search_start.isoformat(),
            "search_end": search_end.isoformat(),
            "duration_minutes": args.duration_min,
            "slot_minutes": args.slot_minutes,
            "top_n": args.top_n,
            "weekdays_only": not args.include_weekends,
            "working_hour_start": args.working_hour_start,
            "working_hour_end": args.working_hour_end,
            "main_participants": args.main,
            "other_participants": args.other,
        },
        "best_slot_opened": bool(args.open_best_slot and results),
        "slots": [_slot_payload(slot) for slot in results],
    }


def _run_reschedule(args: argparse.Namespace) -> dict[str, Any]:
    context = _load_reschedule_context(
        args.source_entry_id,
        args.store_id,
        args.main,
        args.other,
        args.subject,
        args.duration_min,
    )
    search_start = _parse_local_datetime(args.search_start)
    search_end = _parse_local_datetime(args.search_end)
    participants = _combine_participants(context["main_participants"], context["other_participants"])
    results = find_best_slots(
        search_start=search_start,
        search_end=search_end,
        duration_minutes=context["duration_minutes"],
        slot_minutes=args.slot_minutes,
        top_n=args.top_n,
        main_participants=context["main_participants"],
        other_participants=context["other_participants"],
        ignore_entry_ids=context["ignore_entry_ids"],
        weekdays_only=not args.include_weekends,
        working_hour_start=args.working_hour_start,
        working_hour_end=args.working_hour_end,
        include_shorter_slots=args.include_shorter_slots,
    )
    if args.open_best_slot and results:
        open_best_slot_as_meeting(results[0], subject=context["subject"], participants=participants)
    return {
        "status": "ok",
        "action": "reschedule",
        "subject": context["subject"],
        "source_appointment": context["source"],
        "criteria": {
            "search_start": search_start.isoformat(),
            "search_end": search_end.isoformat(),
            "duration_minutes": context["duration_minutes"],
            "slot_minutes": args.slot_minutes,
            "top_n": args.top_n,
            "weekdays_only": not args.include_weekends,
            "working_hour_start": args.working_hour_start,
            "working_hour_end": args.working_hour_end,
            "main_participants": context["main_participants"],
            "other_participants": context["other_participants"],
        },
        "best_slot_opened": bool(args.open_best_slot and results),
        "slots": [_slot_payload(slot) for slot in results],
    }


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "find":
        payload = _run_find(args)
    else:
        payload = _run_reschedule(args)

    if args.json:
        json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        if payload.get("action") == "reschedule":
            source = payload["source_appointment"]
            print(
                "Quelle:",
                f"{source['subject']} | {source['start']} - {source['end']} | Dauer={source['duration_minutes']} Min",
            )
        def _deserialize_slot(slot: dict) -> SlotResult:
            moves = [RueckspracheMove(**{
                **m,
                "original_start": datetime.fromisoformat(m["original_start"]),
                "original_end": datetime.fromisoformat(m["original_end"]),
                "proposed_start": datetime.fromisoformat(m["proposed_start"]),
                "proposed_end": datetime.fromisoformat(m["proposed_end"]),
            }) for m in slot.get("ruecksprache_moves", [])]
            return SlotResult(**{
                **slot,
                "start": datetime.fromisoformat(slot["start"]),
                "end": datetime.fromisoformat(slot["end"]),
                "ruecksprache_moves": moves,
            })
        _print_results([_deserialize_slot(slot) for slot in payload["slots"]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
