"""The score series Analysis draws: quarter ends back six years, then today's score.

From 1 November 2026 a month of daily snapshots filled the whole 32-point window and pushed every
quarter end out of it. Analysis groups by quarter, so the trend drew one point and the rank over
time said there was not enough history."""
from datetime import date, timedelta

from bankcredit.export import COMPARE_POINTS, compare_rows


def test_daily_snapshots_never_crowd_out_the_quarter_ends():
    quarters = [[f"{y}-{m}", 60.0 + i] for i, (y, m) in enumerate((y, m) for y in range(2021, 2027)
                                                                  for m in ("03-31", "06-30", "09-30", "12-31"))
                if f"{y}-{m}" <= "2026-09-30"]
    start = date(2026, 10, 1)
    daily = [[(start + timedelta(days=i)).isoformat(), 70.0 + i / 100, 5.0] for i in range(COMPARE_POINTS + 10)]
    row = {"id": "x", "short": "X", "name": "X", "region": "uk", "type": "bank", "country": "GB", "peer_group": "uk_large",
           "band": "B", "score": 70.0, "rating_grade": 5, "rating_composite": "A",
           "history": {"score": quarters, "snapshots": daily}}
    s = compare_rows([row], {}, {})[0]["series"]["score"]
    assert s[:-1] == quarters[-(len(s) - 1):], "the quarter ends are all still there"
    assert s[-1] == daily[-1][:2], "and the newest snapshot stands for the current quarter"
    assert len({d[:7] for d, _ in s}) == len(s), "one point per quarter"
