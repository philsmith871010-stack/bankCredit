"""The history the monitor compares a name against (export._monitor_history): enough of each name's
past, kept compact because every covered name rides in policy.json, to read its state on whatever
day the reader approved it."""
from __future__ import annotations

from datetime import date

from bankcredit.export import _monitor_history


class Book:
    """The three calls the monitor history makes on a rating timeline."""

    def composite_steps(self):
        return [["2019-04-04", 6.5], ["2024-12-18", 7.0], ["2026-05-12", 6.0], ["2026-09-16", 6.5]]

    def tone_steps(self):
        return [["2023-06-09", 2, 0, 0, 0, 0, 2], ["2025-11-21", 2, 0, 0, 0, 0, 2], ["2026-10-23", 2, 0, 0, 0, 1, 1]]

    def moves(self):                                   # newest first, as the timeline returns them
        return [{"date": "2026-09-16", "action": "downgrade", "notches": 1},
                {"date": "2026-05-12", "action": "upgrade", "notches": 2},
                {"date": "2020-10-20", "action": "downgrade", "notches": 1}]


TODAY = date(2026, 11, 4)
BACK = [{"date": "2022-12-31", "score": 80.0}, {"date": "2026-03-31", "score": 82.5}, {"date": "2026-09-30", "score": 82.7}]
SERIES = {
    "cet1_ratio": [{"d": "2026-03-31", "v": 19.6}, {"d": "2026-06-30", "v": 19.1}, {"d": "2026-09-30", "v": None}],
    "total_capital_ratio": [{"d": "2026-03-31", "v": 24.0}, {"d": "2026-06-30", "v": 23.5}],
    "overall_capital_requirement": [{"d": "2026-06-30", "v": 12.1}, {"d": "2025-12-31", "v": 11.0}],
}


def test_a_baseline_anywhere_in_the_window_reads_the_state_in_force_that_day():
    h = _monitor_history(BACK, Book(), SERIES, TODAY)
    # three years back is 2023-11-05: the 2019 average was still in force then, so it is kept
    assert h["r"] == [["2019-04-04", 6.5], ["2024-12-18", 7.0], ["2026-05-12", 6.0], ["2026-09-16", 6.5]]
    assert h["t"][0][0] == "2023-06-09", "the tone in force at the window's start"
    assert h["s"] == [["2026-03-31", 82.5], ["2026-09-30", 82.7]], "the 2022 quarter is outside the window"


def test_moves_run_oldest_first_and_stay_inside_the_window():
    h = _monitor_history(BACK, Book(), SERIES, TODAY)
    assert h["m"] == [["2026-05-12", "upgrade", 2], ["2026-09-16", "downgrade", 1]]


def test_headroom_takes_capital_and_requirement_from_the_same_period():
    h = _monitor_history(BACK, Book(), SERIES, TODAY)
    assert h["h"] == [["2026-06-30", 11.4]], "March has no requirement and December no capital"
    assert h["c"] == [["2026-03-31", 19.6], ["2026-06-30", 19.1]], "a period without a figure is left out"


def test_a_name_without_a_rating_timeline_still_carries_its_figures():
    h = _monitor_history(BACK, None, SERIES, TODAY)
    assert "r" not in h and "m" not in h
    assert h["c"] and h["s"]
