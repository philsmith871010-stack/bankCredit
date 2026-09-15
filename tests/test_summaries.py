"""The written summary on every profile: dated arithmetic on every build, and a written layer
that is rewritten only when what it rests on has moved - and can never carry a figure the
data did not give it.
"""
from __future__ import annotations

import json
from datetime import date

import pytest

from bankcredit import summaries as S

TODAY = date(2026, 9, 16)


def bank(**over):
    b = {
        "id": "tsb", "name": "TSB Bank plc", "short": "TSB", "country": "GB", "type": "bank", "peer_group": "uk_mid",
        "score": 66.4, "band": "B", "percentile": 40, "peer": {"n": 16, "p50": 68.0}, "asof": "2026-06-30",
        "cet1": 14.0, "leverage": 5.0, "lcr": 150.0, "nsfr": 130.0,
        "peer_ratios": {"cet1_ratio": {"p25": 13.5, "p50": 13.8, "p75": 14.2, "n": 16}, "lcr": {"p25": 140, "p50": 160, "p75": 180, "n": 16}},
        "ratings": [{"agency": "fitch", "value": "A", "outlook": "stable", "date": "2026-05-01"},
                    {"agency": "dbrs", "value": "A(H)", "outlook": "", "date": "2026-05-01"}],
        "rating_composite": "A",
        "rating_history": {"moves": [{"date": "2026-05-01", "agency": "dbrs", "action": "upgrade", "value": "A(H)"},
                                     {"date": "2025-11-02", "agency": "fitch", "action": "upgrade", "value": "A"}]},
        "history": {"score": [["2026-03-31", 65.0], ["2026-06-30", 66.4]]},
        "series": {"lcr": [{"d": f"2025-{m:02d}-30", "v": v} for m, v in ((3, 170), (6, 165), (9, 160), (12, 155))] + [{"d": "2026-03-30", "v": 150}],
                   "cet1_ratio": [{"d": "2025-03-30", "v": 13.9}, {"d": "2026-03-30", "v": 14.0}]},
        "events": [{"date": "2026-08-10", "severity": "warn", "type": "news", "title": "TSB fined over outage - FT"},
                   {"date": "2026-01-10", "severity": "bad", "type": "news", "title": "old"},
                   {"date": "2026-09-01", "severity": "info", "type": "news", "title": "noise"}],
    }
    b.update(over)
    return b


def test_the_paragraph_reads_as_plain_english_and_never_quotes_the_sites_score():
    b = S.brief(bank(), TODAY)
    assert b["standing"] == "TSB is a bank in the UK, rated A by Fitch, with a stable outlook; the last move was Fitch's upgrade to A on 2 Nov 2025.", "DBRS is not one of the three"
    assert b["capital"] == "Capital is strong against UK mid-sized banks: CET1 of 14.0% is above the median (median 13.8%); leverage is 5.0%.", "no peer figure for leverage, so it is stated but not judged"
    assert b["liquidity"] == "Liquidity is on the weak side of UK mid-sized banks: LCR of 150% is below the median (median 160%); NSFR is 130%."
    assert b["trends"] == "Since 30 Mar 2025, LCR has fallen 20 points, while CET1 has been broadly flat (figures to 30 Jun 2026)."
    assert b["news"] == "Flagged in the last 90 days: 10 Aug 2026, warn: TSB fined over outage."
    text = S.brief_text(b)
    assert "noise" not in text and "old" not in text
    assert "score" not in text.lower() and "band" not in text.lower(), "the score and band depend on the reader's weightings"


def test_three_agencies_and_mixed_outlooks_read_naturally():
    b = S.brief(bank(ratings=[{"agency": "fitch", "value": "A+", "outlook": "stable"}, {"agency": "sp", "value": "A", "outlook": "negative"},
                             {"agency": "moodys", "value": "A2", "outlook": "stable"}], rating_history={"moves": []}), TODAY)
    assert b["standing"] == "TSB is a bank in the UK, rated A+ by Fitch, A by S&P and A2 by Moody's (Fitch stable, S&P negative, Moody's stable)."
    b = S.brief(bank(ratings=[{"agency": "fitch", "value": "A+", "outlook": "stable"}, {"agency": "sp", "value": "A", "outlook": "stable"}], rating_history={"moves": []}), TODAY)
    assert b["standing"] == "TSB is a bank in the UK, rated A+ by Fitch and A by S&P, both with a stable outlook."


def test_an_unscored_unrated_name_still_gets_an_honest_paragraph():
    b = S.brief(bank(score=None, unscored="unrated", ratings=[], rating_composite=None, unrated=True, events=[], type="building_society"), TODAY)
    assert b["standing"] == "TSB is a building society in the UK with no public rating from Fitch, S&P or Moody's."
    assert b["news"] == "Nothing has been flagged in the last 90 days."


def test_the_fingerprint_is_what_a_written_summary_rests_on():
    fp = S.fingerprint(bank())
    assert fp == {"band": "B", "composite": "A", "ratings": {"fitch": "A stable"}, "asof": "2026-06-30", "last_flagged": "2026-08-10"}


def test_what_moved_since_is_said_in_words():
    then = S.fingerprint(bank())
    now = S.fingerprint(bank(band="C", ratings=[{"agency": "fitch", "value": "A-", "outlook": "negative"}], asof="2026-09-30",
                             events=[{"date": "2026-09-12", "severity": "bad", "title": "x"}]))
    got = S.changes_since(then, now)
    assert got == ["band moved from B to C", "Fitch moved from A stable to A- negative",
                   "figures updated to 30 Sep 2026 (were 30 Jun 2026)", "a flagged event on 12 Sep 2026 postdates it"]
    assert S.changes_since(then, then) == []


def summary(**over):
    s = {"id": "tsb", "written": "2026-09-16", "background": "TSB is a UK retail bank owned by Sabadell.",
         "synthesis": "Capital is sound, with CET1 of 14.0% a touch above the peer median of 13.8%, and Fitch rates the bank A with a stable outlook. Liquidity is the weak spot: LCR at 150% sits below the group's 160% and has come down 20 points over four periods. One adverse headline, a fine over an outage, in the last 90 days.",
         "inputs": S.fingerprint(bank())}
    s.update(over)
    return s


def test_a_summary_is_owed_when_new_moved_or_old(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "SUMMARIES", tmp_path)
    assert S.why_due(None, bank(), TODAY) == "no summary yet"
    (tmp_path / "tsb.json").write_text(json.dumps(summary()))
    assert S.why_due(S.load("tsb"), bank(), TODAY) is None, "nothing has moved, it stands"
    assert S.why_due(S.load("tsb"), bank(band="C"), TODAY) == "band moved from B to C"
    assert S.why_due(S.load("tsb"), bank(), date(2027, 1, 1)) == "written 107 days ago"
    items = S.due({"tsb": bank(band="C"), "other": bank(id="other")}, TODAY)
    assert [i["id"] for i in items] == ["tsb", "other"]
    assert items[0]["previous"] == "TSB is a UK retail bank owned by Sabadell." and items[0]["brief"].startswith("TSB is a bank in the UK")


def test_a_figure_the_paragraph_did_not_give_fails_the_check():
    para = S.brief_text(S.brief(bank(), TODAY))
    assert S.check(summary(), para) == []
    bad = summary(synthesis="TSB has a CET1 ratio of 14.0% and total assets of 46bn, up from 41bn, which is comfortable for a bank of its size and funding model.")
    assert "figures not in the paragraph it was written from: 41, 46" in S.check(bad, para)
    assert S.check(summary(synthesis="Fine."), para) == ["10 words; 40 to 220 is the range"]
    assert "dated wording: 'recently'" in S.check(summary(background="TSB recently changed hands."), para)
    assert S.check({"id": "tsb"}, para) == ["missing written", "missing background", "missing synthesis", "missing inputs"]
    scored = S.check(summary(synthesis="TSB scores 66 and sits in band B, which is fine for most treasurers at most tenors, and its capital at 14.0% is above the peer median."), para)
    assert any("score or band" in f for f in scored), scored


def test_the_profile_shows_both_layers_and_says_what_moved(tmp_path, monkeypatch):
    from bankcredit.site import build
    monkeypatch.setattr(S, "SUMMARIES", tmp_path)
    b = bank()
    html = build.summary_block(b, "2026-09-16T05:00:00Z")
    assert "TSB is a bank in the UK, rated A by Fitch" in html and "No written summary yet" in html
    (tmp_path / "tsb.json").write_text(json.dumps(summary()))
    html = build.summary_block(b, "2026-09-16T05:00:00Z")
    assert "owned by Sabadell" in html and "Written 16 Sep 2026 from figures to 30 Jun 2026." in html
    assert "brief-stale" not in html
    html = build.summary_block(bank(band="C"), "2026-09-16T05:00:00Z")
    assert "Since then: band moved from B to C. This summary predates that." in html
