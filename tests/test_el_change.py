from __future__ import annotations

from argparse import Namespace

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


def test_parse_months_accepts_german_and_english(el_change):
    assert el_change.parse_months("apr,mai,july") == ["apr", "may", "jul"]


def test_parse_months_all_months(el_change):
    assert el_change.parse_months(None, all_months=True) == el_change.MONTH_ORDER


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


def test_run_dry_run_writes_report_without_post(monkeypatch, el_change, tmp_path):
    monkeypatch.setattr(el_change, "fetch_roles", lambda: [{"roleName": "UA-Leiter", "orgUnit": "EKEK/1"}])
    monkeypatch.setattr(el_change, "fetch_employee_hours", lambda year, org_unit_id: _employee_hours())
    monkeypatch.setattr(el_change, "fetch_planning", lambda user_id, year, org_unit_id: _planning_payload())

    def _forbidden_post(payload):
        raise AssertionError("post_planning_update must not be called in dry-run")

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
        output=str(tmp_path / "dry-run.md"),
    )

    path = el_change.run(args)
    text = path.read_text(encoding="utf-8")
    assert "dry-run" in text
    assert "0048207" in text
    assert "Kein Write ausgefuehrt" in text


def test_run_apply_posts_and_verifies(monkeypatch, el_change, tmp_path):
    posted = {}
    refreshed = _planning_payload()
    refreshed["planningExceptions"][0]["percentInApr"] = 0
    refreshed["planningExceptions"][0]["percentInMay"] = 0
    refreshed["planningExceptions"][0]["percentInJun"] = 0
    refreshed["planningExceptions"][0]["percentInJul"] = 0
    planning_calls = iter([_planning_payload(), refreshed])

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
        months="apr,may,jun,jul",
        all_months=False,
        value=0.0,
        year=2026,
        org_unit_id=161,
        apply=True,
        output=str(tmp_path / "apply.md"),
    )

    path = el_change.run(args)
    payload_entry = posted["payload"]["planningExceptions"][0]
    assert payload_entry["percentInApr"] == 0
    assert payload_entry["percentInMay"] == 0
    assert payload_entry["percentInJun"] == 0
    assert payload_entry["percentInJul"] == 0

    text = path.read_text(encoding="utf-8")
    assert "apply" in text
    assert "Readback erfolgreich." in text


def test_parse_months_rejects_unknown_month(el_change):
    with pytest.raises(el_change.ElChangeError, match="Unbekannter Monat"):
        el_change.parse_months("foo")
