from __future__ import annotations

from argparse import Namespace
from datetime import datetime
from pathlib import Path

import pytest


def _employee_hours():
    return {
        "current": [
            {"idxUser": 1053, "userFullName": "Mueller, Tobias Carsten"},
            {"idxUser": 1056, "userFullName": "Bachmann, Armin"},
        ],
        "previous": [],
        "future": [],
    }


def _planning_payload():
    return {
        "userId": 1053,
        "orgUnitId": 161,
        "year": 2026,
        "yearWorkHours": 1500,
        "hourlyRateFltValueMix": 159.08,
        "inactiveMonths": [],
        "planningExceptions": [
            {
                "idxWorkPlanning": None,
                "userId": 1053,
                "plannedPositionId": None,
                "developementOrderId": 326,
                "organizationalUnitId": 161,
                "year": 2026,
                "projectFamily": "SON",
                "number": "0048207",
                "description": "0048207 - Digitale Arbeitsorganisation",
                "devOrderDescription": "Digitale Arbeitsorganisation",
                "percentInJan": 0,
                "percentInFeb": 0,
                "percentInMar": 0,
                "percentInApr": 100,
                "percentInMay": 100,
                "percentInJun": 100,
                "percentInJul": 30,
                "percentInAug": 0,
                "percentInSep": 0,
                "percentInOct": 0,
                "percentInNov": 0,
                "percentInDec": 0,
                "bookingRightsExceptionsMonths": None,
            },
            {
                "idxWorkPlanning": None,
                "userId": 1053,
                "plannedPositionId": None,
                "developementOrderId": 999,
                "organizationalUnitId": 161,
                "year": 2026,
                "projectFamily": "MEB",
                "number": "0038004",
                "description": "0038004 - SB MEB 31",
                "devOrderDescription": "SB MEB 31",
                "percentInJan": 1,
                "percentInFeb": 1,
                "percentInMar": 2,
                "percentInApr": 2,
                "percentInMay": 2,
                "percentInJun": 3,
                "percentInJul": 3,
                "percentInAug": 3,
                "percentInSep": 3,
                "percentInOct": 3,
                "percentInNov": 3,
                "percentInDec": 3,
                "bookingRightsExceptionsMonths": None,
            },
        ],
    }


def _planning_payload_single_change():
    return {
        "userId": 1053,
        "orgUnitId": 161,
        "year": 2026,
        "yearWorkHours": 1500,
        "hourlyRateFltValueMix": 159.08,
        "inactiveMonths": [],
        "planningExceptions": [
            {
                "idxWorkPlanning": None,
                "userId": 1053,
                "plannedPositionId": None,
                "developementOrderId": 326,
                "organizationalUnitId": 161,
                "year": 2026,
                "projectFamily": "SON",
                "number": "0048207",
                "description": "0048207 - Digitale Arbeitsorganisation",
                "devOrderDescription": "Digitale Arbeitsorganisation",
                "percentInJan": 0,
                "percentInFeb": 0,
                "percentInMar": 0,
                "percentInApr": 98,
                "percentInMay": 98,
                "percentInJun": 0,
                "percentInJul": 0,
                "percentInAug": 0,
                "percentInSep": 0,
                "percentInOct": 0,
                "percentInNov": 0,
                "percentInDec": 0,
                "bookingRightsExceptionsMonths": None,
            },
            {
                "idxWorkPlanning": None,
                "userId": 1053,
                "plannedPositionId": None,
                "developementOrderId": 999,
                "organizationalUnitId": 161,
                "year": 2026,
                "projectFamily": "MEB",
                "number": "0038004",
                "description": "0038004 - SB MEB 31",
                "devOrderDescription": "SB MEB 31",
                "percentInJan": 0,
                "percentInFeb": 0,
                "percentInMar": 0,
                "percentInApr": 1,
                "percentInMay": 1,
                "percentInJun": 0,
                "percentInJul": 0,
                "percentInAug": 0,
                "percentInSep": 0,
                "percentInOct": 0,
                "percentInNov": 0,
                "percentInDec": 0,
                "bookingRightsExceptionsMonths": None,
            },
        ],
    }


def _planning_payload_locked_single_change(total_other_apr=99, total_other_may=99):
    return {
        "userId": 1053,
        "orgUnitId": 161,
        "year": 2026,
        "yearWorkHours": 1500,
        "hourlyRateFltValueMix": 159.08,
        "inactiveMonths": [],
        "planningExceptions": [
            {
                "idxWorkPlanning": None,
                "userId": 1053,
                "plannedPositionId": None,
                "developementOrderId": 326,
                "organizationalUnitId": 161,
                "year": 2026,
                "projectFamily": "SON",
                "number": "0048207",
                "description": "0048207 - Digitale Arbeitsorganisation",
                "devOrderDescription": "Digitale Arbeitsorganisation",
                "percentInJan": 0,
                "percentInFeb": 0,
                "percentInMar": 0,
                "percentInApr": 1,
                "percentInMay": 1,
                "percentInJun": 0,
                "percentInJul": 0,
                "percentInAug": 0,
                "percentInSep": 0,
                "percentInOct": 0,
                "percentInNov": 0,
                "percentInDec": 0,
                "bookingRightsExceptionsMonths": [4, 5],
            },
            {
                "idxWorkPlanning": None,
                "userId": 1053,
                "plannedPositionId": None,
                "developementOrderId": 999,
                "organizationalUnitId": 161,
                "year": 2026,
                "projectFamily": "MEB",
                "number": "0038004",
                "description": "0038004 - SB MEB 31",
                "devOrderDescription": "SB MEB 31",
                "percentInJan": 0,
                "percentInFeb": 0,
                "percentInMar": 0,
                "percentInApr": total_other_apr,
                "percentInMay": total_other_may,
                "percentInJun": 0,
                "percentInJul": 0,
                "percentInAug": 0,
                "percentInSep": 0,
                "percentInOct": 0,
                "percentInNov": 0,
                "percentInDec": 0,
                "bookingRightsExceptionsMonths": None,
            },
        ],
    }


def _planning_payload_plan_changes():
    def _entry(number, description, apr, may, jun, jul, aug, sep, oct_, nov, dec, locks=None):
        return {
            "idxWorkPlanning": None,
            "userId": 1053,
            "plannedPositionId": None,
            "developementOrderId": 1000,
            "organizationalUnitId": 161,
            "year": 2026,
            "projectFamily": "MEB",
            "number": number,
            "description": f"{number} - {description}",
            "devOrderDescription": description,
            "percentInJan": 0,
            "percentInFeb": 0,
            "percentInMar": 0,
            "percentInApr": apr,
            "percentInMay": may,
            "percentInJun": jun,
            "percentInJul": jul,
            "percentInAug": aug,
            "percentInSep": sep,
            "percentInOct": oct_,
            "percentInNov": nov,
            "percentInDec": dec,
            "bookingRightsExceptionsMonths": locks,
        }

    return {
        "userId": 1053,
        "orgUnitId": 161,
        "year": 2026,
        "yearWorkHours": 1500,
        "hourlyRateFltValueMix": 159.08,
        "inactiveMonths": [],
        "planningExceptions": [
            _entry("0000170", "SSP31C", 5, 5, 5, 5, 5, 5, 5, 5, 5),
            _entry("0043898", "IDS.8", 3, 3, 3, 3, 3, 3, 3, 3, 3),
            _entry("0000163", "SDV1.0", 3, 3, 3, 3, 3, 3, 3, 3, 3),
            _entry("0027121", "ID.1 Hut", 1, 1, 2, 2, 2, 2, 2, 2, 2),
            _entry("0036565", "SB VW3xx Hut", 1, 1, 1, 1, 1, 1, 1, 1, 2),
            _entry("0038018", "ID.Roc EU", 1, 1, 1, 1, 1, 1, 1, 1, 2),
            _entry("0000237", "Gesperrte EA", 1, 1, 1, 1, 1, 1, 1, 1, 1, locks=[4, 5, 6, 7, 8, 9, 10, 11, 12]),
            _entry("0099999", "Rest EA", 85, 85, 84, 84, 84, 84, 84, 84, 82),
        ],
    }


def _planning_payload_large_gap():
    def _entry(number, description, apr):
        return {
            "idxWorkPlanning": None,
            "userId": 1053,
            "plannedPositionId": None,
            "developementOrderId": 1000,
            "organizationalUnitId": 161,
            "year": 2026,
            "projectFamily": "MEB",
            "number": number,
            "description": f"{number} - {description}",
            "devOrderDescription": description,
            "percentInJan": 0,
            "percentInFeb": 0,
            "percentInMar": 0,
            "percentInApr": apr,
            "percentInMay": 0,
            "percentInJun": 0,
            "percentInJul": 0,
            "percentInAug": 0,
            "percentInSep": 0,
            "percentInOct": 0,
            "percentInNov": 0,
            "percentInDec": 0,
            "bookingRightsExceptionsMonths": None,
        }

    return {
        "userId": 1053,
        "orgUnitId": 161,
        "year": 2026,
        "yearWorkHours": 1500,
        "hourlyRateFltValueMix": 159.08,
        "inactiveMonths": [],
        "planningExceptions": [
            _entry("0000170", "Zero EA", 3),
            _entry("0099999", "Rebalance EA", 97),
        ],
    }


def test_parse_months_accepts_german_and_english(el_change):
    assert el_change.parse_months("apr,mai,july") == ["apr", "may", "jul"]


def test_parse_months_all_months(el_change):
    assert el_change.parse_months(None, all_months=True) == el_change.MONTH_ORDER


def test_build_operation_lists_enables_rebalance_by_default_for_zero_ea(el_change):
    args = Namespace(
        zero_ea=["0000170", "0000237"],
        increase_ea=[],
        decrease_ea=[],
        rebalance=None,
    )

    operations, do_rebalance = el_change.build_operation_lists(args, ["apr", "may"])
    assert [op.ea for op in operations] == ["0000170", "0000237"]
    assert do_rebalance is True


def test_build_operation_lists_respects_explicit_no_rebalance(el_change):
    args = Namespace(
        zero_ea=["0000170"],
        increase_ea=[],
        decrease_ea=[],
        rebalance=False,
    )

    operations, do_rebalance = el_change.build_operation_lists(args, ["apr"])
    assert [op.ea for op in operations] == ["0000170"]
    assert do_rebalance is False


def test_resolve_user_prefers_exact(el_change):
    user = el_change.resolve_user(_employee_hours(), "Mueller, Tobias Carsten")
    assert user["idxUser"] == 1053


def test_resolve_entry_by_number(el_change):
    index, entry = el_change.resolve_entry(_planning_payload(), "0048207")
    assert index == 0
    assert entry["description"] == "0048207 - Digitale Arbeitsorganisation"


def test_apply_month_changes_updates_only_selected_months(el_change):
    entry = _planning_payload()["planningExceptions"][0]
    before, after = el_change.apply_month_changes(entry, ["apr", "may", "jun", "jul"], 0)
    assert before["apr"] == 100
    assert after["apr"] == 0
    assert after["may"] == 0
    assert after["jun"] == 0
    assert after["jul"] == 0
    assert after["aug"] == 0


def test_filter_editable_months_blocks_past_months_by_default(monkeypatch, el_change):
    monkeypatch.setattr(el_change, "current_now", lambda: datetime(2026, 4, 17, 12, 0, 0))
    allowed, blocked = el_change.filter_editable_months(["jan", "apr", "may"], year=2026)
    assert allowed == ["apr", "may"]
    assert blocked == {"jan": "Vergangener Monat ausserhalb des aenderbaren Fensters"}


def test_run_dry_run_writes_report_without_post(monkeypatch, el_change, tmp_path):
    monkeypatch.setattr(el_change, "current_now", lambda: datetime(2026, 4, 17, 12, 0, 0))
    monkeypatch.setattr(el_change, "fetch_roles", lambda: [{"roleName": "UA-Leiter", "orgUnit": "EKEK/1"}])
    monkeypatch.setattr(el_change, "fetch_employee_hours", lambda year, org_unit_id: _employee_hours())
    monkeypatch.setattr(el_change, "fetch_planning", lambda user_id, year, org_unit_id: _planning_payload_single_change())

    def _forbidden_post(payload):
        raise AssertionError("post_planning_update must not be called in dry-run")

    monkeypatch.setattr(el_change, "post_planning_update", _forbidden_post)

    args = Namespace(
        command="set-months",
        mitarbeiter="Mueller, Tobias Carsten",
        ea="0048207",
        months="apr,may",
        all_months=False,
        value=99.0,
        year=2026,
        org_unit_id=161,
        apply=False,
        output=str(tmp_path / "dry-run.md"),
        notify_no_popup=True,
    )

    result = el_change.run(args)
    text = result.path.read_text(encoding="utf-8")
    assert "dry-run" in text
    assert "0048207" in text
    assert "Kein Write ausgefuehrt" in text


def test_run_apply_posts_and_verifies(monkeypatch, el_change, tmp_path):
    monkeypatch.setattr(el_change, "current_now", lambda: datetime(2026, 4, 17, 12, 0, 0))
    posted = {}
    refreshed = _planning_payload_single_change()
    refreshed["planningExceptions"][0]["percentInApr"] = 99
    refreshed["planningExceptions"][0]["percentInMay"] = 99
    planning_calls = iter([_planning_payload_single_change(), refreshed])

    monkeypatch.setattr(el_change, "fetch_roles", lambda: [{"roleName": "UA-Leiter", "orgUnit": "EKEK/1"}])
    monkeypatch.setattr(el_change, "fetch_employee_hours", lambda year, org_unit_id: _employee_hours())
    monkeypatch.setattr(el_change, "fetch_planning", lambda user_id, year, org_unit_id: next(planning_calls))

    def _capture_post(payload):
        posted["payload"] = payload
        return {"ok": True}

    monkeypatch.setattr(el_change, "post_planning_update", _capture_post)

    args = Namespace(
        command="set-months",
        mitarbeiter="Mueller, Tobias Carsten",
        ea="0048207",
        months="apr,may",
        all_months=False,
        value=99.0,
        year=2026,
        org_unit_id=161,
        apply=True,
        output=str(tmp_path / "apply.md"),
        notify_no_popup=True,
    )

    result = el_change.run(args)
    payload_entry = posted["payload"]["planningExceptions"][0]
    assert payload_entry["percentInApr"] == 99
    assert payload_entry["percentInMay"] == 99

    text = result.path.read_text(encoding="utf-8")
    assert "apply" in text
    assert "Readback erfolgreich." in text


def test_reset_ea_aborts_if_month_totals_would_not_be_100(monkeypatch, el_change, tmp_path):
    monkeypatch.setattr(el_change, "current_now", lambda: datetime(2026, 4, 17, 12, 0, 0))
    monkeypatch.setattr(el_change, "fetch_roles", lambda: [{"roleName": "UA-Leiter", "orgUnit": "EKEK/1"}])
    monkeypatch.setattr(el_change, "fetch_employee_hours", lambda year, org_unit_id: _employee_hours())
    monkeypatch.setattr(el_change, "fetch_planning", lambda user_id, year, org_unit_id: _planning_payload_single_change())

    def _forbidden_post(payload):
        raise AssertionError("post_planning_update must not be called when month totals are invalid")

    monkeypatch.setattr(el_change, "post_planning_update", _forbidden_post)

    args = Namespace(
        command="reset-ea",
        mitarbeiter="Mueller, Tobias Carsten",
        ea="0048207",
        months=None,
        all_months=False,
        value=None,
        year=2026,
        org_unit_id=161,
        apply=False,
        output=str(tmp_path / "reset_invalid.md"),
        notify_no_popup=True,
    )

    with pytest.raises(el_change.ElChangeError, match="Monatssumme muss fuer alle betroffenen Monate 100 sein"):
        el_change.run(args)


def test_run_apply_fails_if_readback_month_totals_are_not_100(monkeypatch, el_change, tmp_path):
    monkeypatch.setattr(el_change, "current_now", lambda: datetime(2026, 4, 17, 12, 0, 0))
    posted = {}
    refreshed = _planning_payload_single_change()
    refreshed["planningExceptions"][0]["percentInApr"] = 99
    refreshed["planningExceptions"][0]["percentInMay"] = 99
    refreshed["planningExceptions"][1]["percentInApr"] = 0
    refreshed["planningExceptions"][1]["percentInMay"] = 0
    planning_calls = iter([_planning_payload_single_change(), refreshed])

    monkeypatch.setattr(el_change, "fetch_roles", lambda: [{"roleName": "UA-Leiter", "orgUnit": "EKEK/1"}])
    monkeypatch.setattr(el_change, "fetch_employee_hours", lambda year, org_unit_id: _employee_hours())
    monkeypatch.setattr(el_change, "fetch_planning", lambda user_id, year, org_unit_id: next(planning_calls))

    def _capture_post(payload):
        posted["payload"] = payload
        return {"ok": True}

    monkeypatch.setattr(el_change, "post_planning_update", _capture_post)

    args = Namespace(
        command="set-months",
        mitarbeiter="Mueller, Tobias Carsten",
        ea="0048207",
        months="apr,may",
        all_months=False,
        value=99.0,
        year=2026,
        org_unit_id=161,
        apply=True,
        output=str(tmp_path / "apply_readback_invalid.md"),
        notify_no_popup=True,
    )

    with pytest.raises(el_change.ElChangeError, match="Readback-Verifikation fehlgeschlagen"):
        el_change.run(args)
    assert posted["payload"]["planningExceptions"][0]["percentInApr"] == 99


def test_plan_changes_zero_ea_can_zero_locked_months_and_rebalance(monkeypatch, el_change, tmp_path):
    monkeypatch.setattr(el_change, "current_now", lambda: datetime(2026, 4, 17, 12, 0, 0))
    monkeypatch.setattr(el_change, "fetch_roles", lambda: [{"roleName": "UA-Leiter", "orgUnit": "EKEK/1"}])
    monkeypatch.setattr(el_change, "fetch_employee_hours", lambda year, org_unit_id: _employee_hours())
    monkeypatch.setattr(el_change, "fetch_planning", lambda user_id, year, org_unit_id: _planning_payload_plan_changes())
    monkeypatch.setattr(
        el_change,
        "load_reference_shares",
        lambda year, preset, org_like=None, include_status_tokens=None, exclude_status_tokens=None: {
            "0043898": 7.02,
            "0000163": 5.61,
            "0027121": 3.45,
            "0036565": 2.27,
            "0038018": 1.76,
            "0099999": 0.10,
        },
    )
    monkeypatch.setattr(
        el_change,
        "load_devorder_map",
        lambda year: {
            "0000170": {"active": 1, "date_until": "2030-12-31"},
            "0043898": {"active": 1, "date_until": "2028-09-30"},
            "0000163": {"active": 1, "date_until": "2030-12-31"},
            "0027121": {"active": 1, "date_until": "2027-12-31"},
            "0036565": {"active": 1, "date_until": "2033-12-31"},
            "0038018": {"active": 1, "date_until": "2029-12-01"},
            "0000237": {"active": 1, "date_until": "2032-06-30"},
            "0099999": {"active": 1, "date_until": "2030-12-31"},
        },
    )

    args = Namespace(
        command="plan-changes",
        mitarbeiter=["Mueller, Tobias Carsten"],
        mitarbeiter_file=None,
        from_month=None,
        to_month=None,
        zero_ea=["0000170", "0000237"],
        increase_ea=[],
        decrease_ea=[],
        rebalance=True,
        reference_preset="btl_all_ek",
        reference_org_like=None,
        reference_include_status=[],
        reference_exclude_status=[],
        max_step_per_ea_per_month=1,
        fill_strategy="fallback-active",
        require_open_devorder=True,
        year=2026,
        org_unit_id=161,
        apply=False,
        output=str(tmp_path / "plan.md"),
        notify_no_popup=True,
    )

    result = el_change.run(args)
    text = result.path.read_text(encoding="utf-8")
    assert "0000170" in text
    assert "0000237 - Gesperrte EA" in text
    assert "zero-ea" in text
    assert "blockiert:" not in text
    assert "0043898" in text
    assert "0000163" in text
    assert "0027121" in text
    assert "0036565" in text
    assert "0038018" in text
    assert "APR" in text


def test_single_change_blocks_locked_non_zero_write(monkeypatch, el_change, tmp_path):
    monkeypatch.setattr(el_change, "current_now", lambda: datetime(2026, 4, 17, 12, 0, 0))
    monkeypatch.setattr(el_change, "fetch_roles", lambda: [{"roleName": "UA-Leiter", "orgUnit": "EKEK/1"}])
    monkeypatch.setattr(el_change, "fetch_employee_hours", lambda year, org_unit_id: _employee_hours())
    monkeypatch.setattr(el_change, "fetch_planning", lambda user_id, year, org_unit_id: _planning_payload_locked_single_change())

    def _forbidden_post(payload):
        raise AssertionError("post_planning_update must not be called in dry-run")

    monkeypatch.setattr(el_change, "post_planning_update", _forbidden_post)

    args = Namespace(
        command="set-months",
        mitarbeiter="Mueller, Tobias Carsten",
        ea="0048207",
        months="apr,may",
        all_months=False,
        value=99.0,
        year=2026,
        org_unit_id=161,
        apply=False,
        output=str(tmp_path / "locked_non_zero.md"),
        notify_no_popup=True,
    )

    result = el_change.run(args)
    text = result.path.read_text(encoding="utf-8")
    assert el_change.LOCKED_MONTH_BLOCKED_MESSAGE in text
    assert "APR" in text
    assert "MAY" in text
    assert "1 |     1" in text


def test_single_change_allows_locked_zero_when_month_totals_remain_100(monkeypatch, el_change, tmp_path):
    monkeypatch.setattr(el_change, "current_now", lambda: datetime(2026, 4, 17, 12, 0, 0))
    monkeypatch.setattr(el_change, "fetch_roles", lambda: [{"roleName": "UA-Leiter", "orgUnit": "EKEK/1"}])
    monkeypatch.setattr(el_change, "fetch_employee_hours", lambda year, org_unit_id: _employee_hours())
    monkeypatch.setattr(
        el_change,
        "fetch_planning",
        lambda user_id, year, org_unit_id: _planning_payload_locked_single_change(total_other_apr=100, total_other_may=100),
    )

    def _forbidden_post(payload):
        raise AssertionError("post_planning_update must not be called in dry-run")

    monkeypatch.setattr(el_change, "post_planning_update", _forbidden_post)

    args = Namespace(
        command="set-months",
        mitarbeiter="Mueller, Tobias Carsten",
        ea="0048207",
        months="apr,may",
        all_months=False,
        value=0.0,
        year=2026,
        org_unit_id=161,
        apply=False,
        output=str(tmp_path / "locked_zero.md"),
        notify_no_popup=True,
    )

    result = el_change.run(args)
    text = result.path.read_text(encoding="utf-8")
    assert el_change.LOCKED_MONTH_BLOCKED_MESSAGE not in text
    assert "APR" in text
    assert "MAY" in text
    assert "1 |     0" in text


def test_plan_changes_missing_zero_ea_is_reported_not_aborted(monkeypatch, el_change, tmp_path):
    monkeypatch.setattr(el_change, "current_now", lambda: datetime(2026, 4, 17, 12, 0, 0))
    monkeypatch.setattr(el_change, "fetch_roles", lambda: [{"roleName": "UA-Leiter", "orgUnit": "EKEK/1"}])
    monkeypatch.setattr(el_change, "fetch_employee_hours", lambda year, org_unit_id: _employee_hours())
    monkeypatch.setattr(el_change, "fetch_planning", lambda user_id, year, org_unit_id: _planning_payload_plan_changes())
    monkeypatch.setattr(
        el_change,
        "load_reference_shares",
        lambda year, preset, org_like=None, include_status_tokens=None, exclude_status_tokens=None: {
            "0043898": 7.02,
            "0000163": 5.61,
            "0027121": 3.45,
            "0036565": 2.27,
            "0038018": 1.76,
            "0099999": 0.10,
        },
    )
    monkeypatch.setattr(
        el_change,
        "load_devorder_map",
        lambda year: {
            "0000170": {"active": 1, "date_until": "2030-12-31"},
            "0043898": {"active": 1, "date_until": "2028-09-30"},
            "0000163": {"active": 1, "date_until": "2030-12-31"},
            "0027121": {"active": 1, "date_until": "2027-12-31"},
            "0036565": {"active": 1, "date_until": "2033-12-31"},
            "0038018": {"active": 1, "date_until": "2029-12-01"},
            "0000237": {"active": 1, "date_until": "2032-06-30"},
            "0099999": {"active": 1, "date_until": "2030-12-31"},
        },
    )

    args = Namespace(
        command="plan-changes",
        mitarbeiter=["Mueller, Tobias Carsten"],
        mitarbeiter_file=None,
        from_month=None,
        to_month=None,
        zero_ea=["0000170", "0000268"],
        increase_ea=[],
        decrease_ea=[],
        rebalance=True,
        reference_preset="btl_all_ek",
        reference_org_like=None,
        reference_include_status=[],
        reference_exclude_status=[],
        max_step_per_ea_per_month=1,
        fill_strategy="fallback-active",
        require_open_devorder=True,
        year=2026,
        org_unit_id=161,
        apply=False,
        output=str(tmp_path / "plan_missing.md"),
        notify_no_popup=True,
    )

    result = el_change.run(args)
    text = result.path.read_text(encoding="utf-8")
    assert "0000268" in text
    assert "EA nicht im bestehenden Plan gefunden" in text
    assert "0043898" in text


def test_plan_changes_without_rebalance_aborts_if_month_totals_would_not_be_100(monkeypatch, el_change, tmp_path):
    monkeypatch.setattr(el_change, "current_now", lambda: datetime(2026, 4, 17, 12, 0, 0))
    monkeypatch.setattr(el_change, "fetch_roles", lambda: [{"roleName": "UA-Leiter", "orgUnit": "EKEK/1"}])
    monkeypatch.setattr(el_change, "fetch_employee_hours", lambda year, org_unit_id: _employee_hours())
    monkeypatch.setattr(el_change, "fetch_planning", lambda user_id, year, org_unit_id: _planning_payload_plan_changes())
    monkeypatch.setattr(
        el_change,
        "load_devorder_map",
        lambda year: {
            "0000170": {"active": 1, "date_until": "2030-12-31"},
            "0043898": {"active": 1, "date_until": "2028-09-30"},
            "0000163": {"active": 1, "date_until": "2030-12-31"},
            "0027121": {"active": 1, "date_until": "2027-12-31"},
            "0036565": {"active": 1, "date_until": "2033-12-31"},
            "0038018": {"active": 1, "date_until": "2029-12-01"},
            "0000237": {"active": 1, "date_until": "2032-06-30"},
            "0099999": {"active": 1, "date_until": "2030-12-31"},
        },
    )

    args = Namespace(
        command="plan-changes",
        mitarbeiter=["Mueller, Tobias Carsten"],
        mitarbeiter_file=None,
        from_month=None,
        to_month=None,
        zero_ea=["0000170"],
        increase_ea=[],
        decrease_ea=[],
        rebalance=False,
        reference_preset="btl_all_ek",
        reference_org_like=None,
        reference_include_status=[],
        reference_exclude_status=[],
        max_step_per_ea_per_month=1,
        fill_strategy="fallback-active",
        require_open_devorder=True,
        year=2026,
        org_unit_id=161,
        apply=False,
        output=str(tmp_path / "plan_invalid.md"),
        notify_no_popup=True,
    )

    with pytest.raises(el_change.ElChangeError, match="Monatssumme muss fuer alle betroffenen Monate 100 sein"):
        el_change.run(args)


def test_plan_changes_max_step_per_ea_per_month_is_used(monkeypatch, el_change, tmp_path):
    monkeypatch.setattr(el_change, "current_now", lambda: datetime(2026, 4, 17, 12, 0, 0))
    monkeypatch.setattr(el_change, "fetch_roles", lambda: [{"roleName": "UA-Leiter", "orgUnit": "EKEK/1"}])
    monkeypatch.setattr(el_change, "fetch_employee_hours", lambda year, org_unit_id: _employee_hours())
    monkeypatch.setattr(el_change, "fetch_planning", lambda user_id, year, org_unit_id: _planning_payload_large_gap())
    monkeypatch.setattr(
        el_change,
        "load_reference_shares",
        lambda year, preset, org_like=None, include_status_tokens=None, exclude_status_tokens=None: {
            "0099999": 90.0,
        },
    )
    monkeypatch.setattr(
        el_change,
        "load_devorder_map",
        lambda year: {
            "0000170": {"active": 1, "date_until": "2030-12-31"},
            "0099999": {"active": 1, "date_until": "2030-12-31"},
        },
    )

    args = Namespace(
        command="plan-changes",
        mitarbeiter=["Mueller, Tobias Carsten"],
        mitarbeiter_file=None,
        from_month="apr",
        to_month="apr",
        zero_ea=["0000170"],
        increase_ea=[],
        decrease_ea=[],
        rebalance=True,
        reference_preset="btl_all_ek",
        reference_org_like=None,
        reference_include_status=[],
        reference_exclude_status=[],
        max_step_per_ea_per_month=3,
        fill_strategy="fallback-active",
        require_open_devorder=True,
        year=2026,
        org_unit_id=161,
        apply=False,
        output=str(tmp_path / "plan_step.md"),
        notify_no_popup=True,
    )

    result = el_change.run(args)
    text = result.path.read_text(encoding="utf-8")
    assert "0099999" in text
    assert "0099999 - Rebalance EA" in text
    assert "rebalance (fallback-active)" in text
    assert "97" in text
    assert "100" in text


def test_main_calls_notify_on_success(monkeypatch, el_change, tmp_path, capsys):
    called = {}

    def _fake_run(args):
        path = tmp_path / "report.md"
        path.write_text("# report", encoding="utf-8")
        return el_change.RunResult(
            path=path,
            notify_message="Alles gut",
            mode="apply",
            readback="ok",
            changes=5,
            blocked=1,
            run_id="abc12345",
        )

    def _fake_notify(status, message, *, title, no_popup):
        called["status"] = status
        called["message"] = message
        called["title"] = title
        called["no_popup"] = no_popup

    monkeypatch.setattr(el_change, "run", _fake_run)
    monkeypatch.setattr(el_change, "notify_result", _fake_notify)

    rc = el_change.main(
        [
            "--notify-no-popup",
            "--year",
            "2026",
            "reset-ea",
            "--mitarbeiter",
            "Mueller, Tobias Carsten",
            "--ea",
            "0048207",
        ]
    )
    captured = capsys.readouterr()
    out = captured.out.strip()
    assert rc == 0
    assert called["status"] == "done"
    assert called["message"] == "Alles gut"
    assert called["title"] == "EL Change"
    assert called["no_popup"] is True
    lines = out.splitlines()
    assert lines[0].startswith("STATUS\t")
    assert "MODE=apply" in lines[0]
    assert "READBACK=ok" in lines[0]
    assert "CHANGES=5" in lines[0]
    assert "BLOCKED=1" in lines[0]
    assert "RUN_ID=abc12345" in lines[0]
    assert lines[-1].endswith("report.md")


def test_main_writes_status_line_on_error(monkeypatch, el_change, capsys):
    def _raise(args):
        raise el_change.ElChangeError("boom")

    monkeypatch.setattr(el_change, "run", _raise)
    monkeypatch.setattr(el_change, "notify_result", lambda *a, **k: None)

    rc = el_change.main(
        [
            "--notify-no-popup",
            "--year",
            "2026",
            "--apply",
            "reset-ea",
            "--mitarbeiter",
            "Mueller, Tobias Carsten",
            "--ea",
            "0048207",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 1
    err_lines = captured.err.strip().splitlines()
    status_lines = [line for line in err_lines if line.startswith("STATUS\t")]
    assert status_lines, err_lines
    assert "READBACK=failed" in status_lines[0]
    assert "MODE=apply" in status_lines[0]
    assert "ERROR=boom" in status_lines[0]


def test_plan_report_filename_distinguishes_dry_run_and_apply(monkeypatch, el_change, tmp_path):
    monkeypatch.setattr(el_change, "current_now", lambda: datetime(2026, 4, 17, 12, 0, 0))
    monkeypatch.setattr(el_change, "fetch_roles", lambda: [])
    monkeypatch.setattr(el_change, "fetch_employee_hours", lambda year, org_unit_id: _employee_hours())
    monkeypatch.setattr(el_change, "fetch_planning", lambda user_id, year, org_unit_id: _planning_payload_plan_changes())
    monkeypatch.setattr(
        el_change,
        "load_reference_shares",
        lambda year, preset, org_like=None, include_status_tokens=None, exclude_status_tokens=None: {
            "0043898": 7.02,
            "0000163": 5.61,
            "0027121": 3.45,
            "0036565": 2.27,
            "0038018": 1.76,
            "0099999": 0.10,
        },
    )
    monkeypatch.setattr(
        el_change,
        "load_devorder_map",
        lambda year: {
            "0000170": {"active": 1, "date_until": "2030-12-31"},
            "0043898": {"active": 1, "date_until": "2028-09-30"},
            "0000163": {"active": 1, "date_until": "2030-12-31"},
            "0027121": {"active": 1, "date_until": "2027-12-31"},
            "0036565": {"active": 1, "date_until": "2033-12-31"},
            "0038018": {"active": 1, "date_until": "2029-12-01"},
            "0000237": {"active": 1, "date_until": "2032-06-30"},
            "0099999": {"active": 1, "date_until": "2030-12-31"},
        },
    )

    def _make_args():
        return Namespace(
            command="plan-changes",
            mitarbeiter=["Mueller, Tobias Carsten"],
            mitarbeiter_file=None,
            from_month=None,
            to_month=None,
            zero_ea=["0000170"],
            increase_ea=[],
            decrease_ea=[],
            rebalance=True,
            reference_preset="btl_all_ek",
            reference_org_like=None,
            reference_include_status=[],
            reference_exclude_status=[],
            max_step_per_ea_per_month=1,
            fill_strategy="fallback-active",
            require_open_devorder=True,
            year=2026,
            org_unit_id=161,
            apply=False,
            output=None,
            notify_no_popup=True,
        )

    monkeypatch.setattr(el_change, "SESSIONS_DIR", tmp_path, raising=False)
    from report_utils import SESSIONS_DIR as _real_sessions  # noqa: F401
    import report_utils
    monkeypatch.setattr(report_utils, "SESSIONS_DIR", tmp_path)

    dry_args = _make_args()
    dry_result = el_change.run(dry_args)
    assert "plan_changes_dryrun" in dry_result.path.name
    assert dry_result.mode == "dryrun"
    assert dry_result.readback == "n/a"

    text = dry_result.path.read_text(encoding="utf-8")
    assert "## Status" in text
    assert text.index("## Status") < text.index("## Kontext")


def test_parse_months_rejects_unknown_month(el_change):
    with pytest.raises(el_change.ElChangeError, match="Unbekannter Monat"):
        el_change.parse_months("foo")


def test_plan_changes_parser_defaults_rebalance_for_zero_ea(el_change):
    parser = el_change.build_parser()
    args = parser.parse_args(
        [
            "--year",
            "2026",
            "plan-changes",
            "--mitarbeiter",
            "Mueller, Tobias Carsten",
            "--zero-ea",
            "0000170",
        ]
    )

    operations, do_rebalance = el_change.build_operation_lists(args, ["apr"])
    assert [op.ea for op in operations] == ["0000170"]
    assert args.rebalance is None
    assert do_rebalance is True


def test_plan_changes_parser_supports_no_rebalance_flag(el_change):
    parser = el_change.build_parser()
    args = parser.parse_args(
        [
            "--year",
            "2026",
            "plan-changes",
            "--mitarbeiter",
            "Mueller, Tobias Carsten",
            "--zero-ea",
            "0000170",
            "--no-rebalance",
        ]
    )

    _, do_rebalance = el_change.build_operation_lists(args, ["apr"])
    assert args.rebalance is False
    assert do_rebalance is False
