"""The series behind the Analysis tab, as compare_rows() writes them into compare.json."""
from __future__ import annotations

import calendar
from datetime import date, timedelta

from bankcredit import export


def quarter_end(d: str) -> str:
    """The quarter a date falls in, named by its last day, as compare.js buckets every series."""
    y, m = int(d[:4]), int(d[5:7])
    qm = (m + 2) // 3 * 3
    return f"{y}-{qm:02d}-{calendar.monthrange(y, qm)[1]:02d}"


def days(first: str, n: int) -> list[list]:
    """n daily snapshots from `first`, [date, score, grade] as the board row carries them, each
    score a little higher than the day before so that the latest one is the one to look for."""
    d0 = date.fromisoformat(first)
    return [[(d0 + timedelta(days=i)).isoformat(), round(60 + i / 10, 1), 6.0] for i in range(n)]


def board_row(back: list[list], snaps: list[list]) -> dict:
    return {"id": "x", "short": "X", "name": "X Bank", "region": "UK", "type": "bank", "country": "GB",
            "peer_group": "uk_large", "band": "B", "score": snaps[-1][1], "rating_grade": 6.0,
            "rating_composite": "A", "history": {"score": back, "snapshots": snaps}}


def test_the_score_steps_by_quarter_like_the_ratios_beside_it():
    """The pipeline adds a snapshot every day. Taken as they were, a month of them filled all 32
    points, and rank over time had one quarter to draw: "Not enough history in the set"."""
    back = [["2025-06-30", 61.0], ["2025-09-30", 62.0], ["2025-12-31", 63.0],
            ["2026-03-31", 64.0], ["2026-06-30", 65.0], ["2026-09-30", 66.0]]
    snaps = days("2026-09-07", 60)          # as the live history runs: begun before the last quarter end
    row = board_row(back, snaps)
    series = export.compare_rows([row], {})[0]["series"]["score"]
    quarters = [quarter_end(d) for d, _v in series]
    assert len(quarters) == len(set(quarters)), f"one point per quarter, not {series}"
    assert len(set(quarters)) >= 2, "the panels that bucket by quarter need two quarters at least"
    assert series[:6] == back, "the quarterly history is kept as it is"
    assert series[6:] == [snaps[-1][:2]], "then the latest snapshot, for the quarter it falls in"
    assert len(row["history"]["snapshots"]) == 60, "the profile's daily chart keeps every snapshot"


def test_each_quarter_after_the_history_takes_its_own_latest_snapshot():
    back = [["2026-03-31", 64.0], ["2026-06-30", 65.0]]
    snaps = days("2026-08-15", 60)          # mid-August into October: two quarters after the history
    series = export.compare_rows([board_row(back, snaps)], {})[0]["series"]["score"]
    assert [d for d, _v in series] == ["2026-03-31", "2026-06-30", "2026-09-30", "2026-10-13"]
