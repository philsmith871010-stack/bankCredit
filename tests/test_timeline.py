"""Rebuilding past ratings from the register's action log."""
from __future__ import annotations

import pandas as pd
import pytest

from bankcredit import timeline


def acts(rows):
    """rows: (parent, agency, date, code, value[, rating_type, currency, rating_name])"""
    out = []
    for i, r in enumerate(rows):
        parent, agency, d, code, value = r[:5]
        rtype = r[5] if len(r) > 5 else "issuer"
        ccy = r[6] if len(r) > 6 else "Foreign currency"
        name = r[7] if len(r) > 7 else "issuer credit rating"
        out.append({"entity_id": "x", "event_id": f"a{i}", "parent_id": parent, "agency": agency,
                    "date": d, "action_code": code, "action": code, "value": value,
                    "rating_type": rtype, "horizon": "long", "currency": ccy, "rating_name": name})
    return pd.DataFrame(out)


def test_a_rating_holds_its_value_until_the_day_it_changes():
    b = timeline.Book(acts([("p1", "sp", "2015-07-01", "OR", "A"),
                            ("p1", "sp", "2019-05-02", "UP", "A+")]))
    assert [x["value"] for x in b.state_at("2016-01-01")] == ["A"]
    assert [x["value"] for x in b.state_at("2019-05-01")] == ["A"]
    assert [x["value"] for x in b.state_at("2019-05-02")] == ["A+"]
    assert [x["value"] for x in b.state_at("2026-01-01")] == ["A+"]
    assert b.state_at("2015-06-30") == [], "nothing before the platform's first day"


def test_an_affirmation_is_not_a_change():
    b = timeline.Book(acts([("p1", "sp", "2015-07-01", "OR", "A"),
                            ("p1", "sp", "2018-01-01", "AF", "A"),
                            ("p1", "sp", "2020-01-01", "AF", "A")]))
    assert b.agency_steps()[0]["steps"] == [["2015-07-01", "A", 6]]
    assert b.composite_steps() == [["2015-07-01", 6.0]]
    assert b.moves() == []


def test_an_outlook_move_leaves_the_rating_where_it_was():
    b = timeline.Book(acts([("p1", "sp", "2015-07-01", "OR", "A"),
                            ("p1", "sp", "2019-01-01", "OT", ""),
                            ("p1", "sp", "2019-06-01", "WR", "")]))
    assert [x["value"] for x in b.state_at("2020-01-01")] == ["A"]
    assert len(b.dates) == 1


def test_a_withdrawn_rating_is_not_a_rating():
    b = timeline.Book(acts([("p1", "sp", "2015-07-01", "OR", "A"),
                            ("p1", "sp", "2021-03-01", "WD", "")]))
    assert [x["value"] for x in b.state_at("2021-02-28")] == ["A"]
    assert b.state_at("2021-06-01") == []
    assert b.composite_at("2021-06-01") is None
    assert [m["action"] for m in b.moves()] == ["withdrawal"]


def test_an_agency_that_rates_again_after_withdrawing_starts_a_new_spell():
    """A downgrade from nothing would be worse than saying nothing."""
    b = timeline.Book(acts([("p1", "sp", "2015-07-01", "OR", "A"),
                            ("p1", "sp", "2020-01-01", "WD", ""),
                            ("p2", "sp", "2023-01-01", "NW", "BBB")]))
    assert [(m["date"], m["action"]) for m in b.moves()] == [("2023-01-01", "new"), ("2020-01-01", "withdrawal")]
    assert [x["value"] for x in b.state_at("2024-01-01")] == ["BBB"]


def test_the_composite_is_the_median_of_whatever_stood_that_day():
    b = timeline.Book(acts([("p1", "sp", "2015-07-01", "OR", "A"),          # 6
                            ("p2", "moodys", "2015-07-01", "OR", "A3"),     # 7
                            ("p3", "fitch", "2018-01-01", "NW", "A+")]))    # 5
    assert b.composite_at("2016-01-01") == 6.5
    assert b.composite_at("2019-01-01") == 6.0
    assert b.composite_at("2014-01-01") is None


def test_an_agency_speaks_once_however_many_records_it_holds():
    """Foreign currency ahead of local, the headline rating type ahead of a debt-class variant -
    the rules the adapter applies to today's ratings, so the history joins up with the present."""
    rows = acts([("p1", "sp", "2015-07-01", "OR", "A", "issuer", "Foreign currency"),
                 ("p2", "sp", "2015-07-01", "OR", "BBB", "deposit", "Local currency")])
    b = timeline.Book(rows)
    assert [x["value"] for x in b.state_at("2020-01-01")] == ["A"]
    assert b.composite_at("2020-01-01") == 6.0


def test_a_move_carries_the_direction_and_the_distance():
    b = timeline.Book(acts([("p1", "sp", "2015-07-01", "OR", "BBB"),
                            ("p1", "sp", "2019-01-01", "UP", "A"),
                            ("p1", "sp", "2022-01-01", "DG", "BBB+")]))
    ups = [m for m in b.moves() if m["action"] == "upgrade"]
    downs = [m for m in b.moves() if m["action"] == "downgrade"]
    assert (ups[0]["from"], ups[0]["value"], ups[0]["notches"]) == ("BBB", "A", 3)
    assert (downs[0]["from"], downs[0]["value"], downs[0]["notches"]) == ("A", "BBB+", 2)


def test_nothing_at_all_is_not_an_error():
    b = timeline.Book(pd.DataFrame())
    assert not b
    assert b.state_at("2020-01-01") == [] and b.composite_at("2020-01-01") is None
    assert timeline.by_entity(None) == {} and timeline.by_entity(pd.DataFrame()) == {}


def test_a_short_term_rating_is_not_on_the_long_term_ladder():
    rows = acts([("p1", "sp", "2015-07-01", "OR", "A")])
    rows.loc[0, "horizon"] = "short"
    assert not timeline.Book(rows)


@pytest.mark.parametrize("code", ["NW", "OR", "AF", "UP", "DG"])
def test_every_action_that_carries_a_rating_sets_one(code):
    b = timeline.Book(acts([("p1", "sp", "2015-07-01", code, "AA-")]))
    assert [x["value"] for x in b.state_at("2020-01-01")] == ["AA-"]
