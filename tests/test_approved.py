"""The approved list: a council's names down the left, one card at a time on the right.

An alternative to the home page's policy tab while the shape is decided. It is drawn from its own
slim files, so what those files say - the score's move this month, the four ratios' recent path,
the flags the list column shows - is worked out once, in the build, and tested here rather than in
a browser.
"""
from __future__ import annotations

import json
from datetime import date

from bankcredit.site import build

TODAY = date(2026, 9, 15)


def bank(**over):
    """A profile file with just enough in it to draw a card."""
    b = {
        "id": "tsb", "name": "TSB Bank plc", "short": "TSB", "country": "GB", "type": "bank", "region": "uk",
        "peer_group": "uk_mid", "score": 66.0, "band": "B", "age_days": 76, "asof": "2026-06-30",
        "cet1": 14.0, "leverage": 5.0, "lcr": 150.0, "nsfr": 130.0,
        "ratings": [{"agency": "fitch", "value": "A", "outlook": "stable", "date": "2026-05-01"}],
        "rating_composite": "A", "sovereign": {"country": "GB", "name": "United Kingdom", "composite": "AA", "grade": 3, "n": 6},
        "history": {"snapshots": [["2026-08-30", 64.0, 7], ["2026-09-01", 65.0, 7], ["2026-09-14", 66.0, 7]],
                    "score": [["2025-12-31", 61.0], ["2026-03-31", 63.0], ["2026-06-30", 65.0]]},
        "rating_history": {"moves": [{"date": "2026-09-02", "agency": "fitch", "action": "upgrade"}]},
        "events": [{"event_id": "news:1", "date": "2026-09-10", "type": "news", "title": "TSB fined", "source": "FT",
                    "url": "https://x", "severity": "warn", "detail": "long text nobody needs"},
                   {"event_id": "doc:1", "date": "2026-09-09", "type": "disclosure", "title": "Pillar 3", "severity": "info"}],
        "series": {"lcr": [{"d": "2026-03-31", "v": 155.0, "src": "p3", "doc": "x"}, {"d": "2026-06-30", "v": 150.0, "src": "p3", "doc": "y"},
                           {"d": "2026-06-30", "v": 151.0, "src": "p3", "doc": "z"}]},
        "prices": [{"d": "2026-09-13", "c": 100.0}, {"d": "2026-09-14", "c": None}],
        "score_detail": {"pillars": {"capital": [80.0, 25]}, "inputs": {"cet1_ratio": [14.0, 80]}},
        "peer_ratios": {"cet1_ratio": {"p25": 13, "p50": 14, "p75": 15, "n": 9}, "roe": {"p50": 9}},
    }
    b.update(over)
    return b


def test_the_card_says_how_the_score_has_moved_since_the_month_began():
    card = build.approved_card(bank(), TODAY)
    assert card["delta"] == 1.0 and card["delta_since"] == "2026-09-01", "against the last snapshot on or before the 1st"
    assert "score" in card["flags"], "a point or more is worth a mark in the list"


def test_the_list_flags_are_the_daily_glance():
    card = build.approved_card(bank(), TODAY)
    assert "rating" in card["flags"], "a rating action in the last 30 days"
    assert "news" in card["flags"], "a flagged headline in the last 30 days"
    assert "stale" not in card["flags"]
    old = build.approved_card(bank(age_days=200, unscored="no figures"), TODAY)
    assert "stale" in old["flags"] and "unscored" in old["flags"]


def test_the_card_carries_only_what_it_draws():
    card = build.approved_card(bank(), TODAY)
    assert card["events"][0]["title"] == "TSB fined" and "detail" not in card["events"][0]
    assert all(e["type"] in ("rating", "news") for e in card["events"]), "documents are not news"
    assert card["trend"]["lcr"] == [["2026-03-31", 155.0], ["2026-06-30", 151.0]], "one reading per period, the last written"
    assert card["spark"] == [100.0], "a missing close is not a point"
    assert set(card["peer_ratios"]) == {"cet1_ratio"}, "only the four ratios the tiles show"
    assert card["sovereign"] == {"country": "GB", "name": "United Kingdom", "composite": "AA", "grade": 3}
    assert card["pillars"] == {"capital": [80.0, 25]}


def test_a_thin_profile_still_makes_a_card():
    """A name with no history, no ratings and no series must not stop the build."""
    card = build.approved_card({"id": "x", "name": "X", "score": None, "unscored": "no figures"}, TODAY)
    assert card["delta"] is None and card["flags"] == ["unscored"] and card["trend"]["lcr"] == []


def test_the_page_is_built_with_its_own_assets_and_a_way_in(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "OUT", tmp_path)
    html = build.page_approved("2026-09-15T05:00:00Z")
    assert 'data-root="../"' in html, "fetches walk up from approved/ to the site root"
    assert "assets/approved.css" in html and "assets/approved.js" in html
    for anchor in ('id="list"', 'id="detail"', 'id="q"', 'id="sort"', 'id="share"'):
        assert anchor in html
    home = build.page_home({"generated": "2026-09-15T05:00:00Z", "rows": [], "benchmarks": []},
                           {"runs": [], "documents": []}, "2026-09-15T05:00:00Z")
    assert 'data-tab="approved"' in home and "alternative view" in home, "a tab, named as the alternative it is"
    assert 'data-panel="approved"' in home and "assets/approved.js" in home, "its script comes with the panel on first click"
    panels = build.home_panels({"generated": "2026-09-15T05:00:00Z", "rows": [], "benchmarks": []}, {"runs": [], "documents": []}, "2026-09-15T05:00:00Z")
    assert 'id="list"' in panels["approved"], "the panel fragment is the view's markup"


def test_the_data_files_are_written_for_every_bank(tmp_path, monkeypatch):
    src = tmp_path / "json" / "banks"; src.mkdir(parents=True)
    (src / "tsb.json").write_text(json.dumps(bank()))
    (src / "broken.json").write_text("{not json")
    monkeypatch.setattr(build.store, "DATA", tmp_path)
    monkeypatch.setattr(build, "OUT", tmp_path / "site")
    assert build.write_approved("2026-09-15T05:00:00Z") == 1, "one unreadable file must not stop the rest"
    listing = json.loads((tmp_path / "site" / "data" / "approved" / "list.json").read_text())
    assert listing["generated"].startswith("2026-09-15") and listing["rows"][0]["id"] == "tsb"
    assert set(listing["rows"][0]) == set(build.APPROVED_LIST)
    assert (tmp_path / "site" / "data" / "approved" / "tsb.json").exists()
