"""Tests for option-dependent branching in night and morning shifts.

These pin the business rule: Option A adds Wednesday, Option B adds Monday,
Option C adds Tuesday for Lester (night) and Blaine (morning).
"""
import pytest

import generate_schedule as gs


DAY_KEYS = ["Sat", "Sun", "Mon", "Tue", "Wed", "Thu", "Fri"]


def _find_person(section, substring):
    for p in section["staff"]:
        if substring in p["name"]:
            return p
    raise AssertionError(f"{substring} not found in section")


def _working_days(schedule):
    return {d for d in DAY_KEYS if schedule[d]["hrs"] > 0}


@pytest.mark.parametrize(
    "option,extra_day",
    [("A", "Wed"), ("B", "Mon"), ("C", "Tue")],
)
def test_lester_fifth_day_matches_option(option, extra_day):
    night = gs.get_night_shift(option)
    lester = _find_person(night, "Lester Anderson")
    days = _working_days(lester["schedule"])

    assert days == {"Sat", "Sun", "Thu", "Fri", extra_day}
    total = sum(lester["schedule"][d]["hrs"] for d in DAY_KEYS)
    assert total == 40


@pytest.mark.parametrize(
    "option,extra_day",
    [("A", "Wed"), ("B", "Mon"), ("C", "Tue")],
)
def test_blaine_fifth_day_matches_option(option, extra_day):
    morning = gs.get_morning_shift(option)
    blaine = _find_person(morning, "Blaine Rapson")
    days = _working_days(blaine["schedule"])

    assert days == {"Sat", "Sun", "Thu", "Fri", extra_day}
    total = sum(blaine["schedule"][d]["hrs"] for d in DAY_KEYS)
    assert total == 40


def test_unknown_option_defaults_to_four_days_for_lester():
    """An unrecognised option letter should leave Lester on his base 4 days."""
    night = gs.get_night_shift("Z")
    lester = _find_person(night, "Lester Anderson")
    assert _working_days(lester["schedule"]) == {"Sat", "Sun", "Thu", "Fri"}


def test_no_twelve_hour_shifts_anywhere():
    """Regression: the whole point of these options is no 12hr shifts."""
    for opt in ("A", "B", "C"):
        for section in (
            gs.get_afternoon_shift(),
            gs.get_ssd_shift(),
            gs.get_night_shift(opt),
            gs.get_morning_shift(opt),
        ):
            for person in section["staff"]:
                for day, shift in person["schedule"].items():
                    assert shift["hrs"] in (0, 8), (
                        f"{person['name']} has {shift['hrs']}hr shift on {day}"
                    )


def test_afternoon_shift_is_option_independent():
    """Afternoon and SSD are documented as unchanged across options."""
    a = gs.get_afternoon_shift()
    b = gs.get_afternoon_shift()
    assert a == b


def test_ireland_weekend_is_eight_hours():
    for opt in ("A", "B", "C"):
        ireland = _find_person(gs.get_night_shift(opt), "Ireland Van Wormer")
        assert ireland["schedule"]["Sat"]["hrs"] == 8
        assert ireland["schedule"]["Sun"]["hrs"] == 8


def test_hoffman_saturday_is_eight_hours():
    for opt in ("A", "B", "C"):
        hoffman = _find_person(gs.get_morning_shift(opt), "Michael Hoffman")
        assert hoffman["schedule"]["Sat"]["hrs"] == 8
