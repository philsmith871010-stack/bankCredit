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
        "rating": {"n": 1, "avg": 6.0, "worst": 6, "letter": "A", "worst_letter": "A", "tones": ["stable"], "date": "2026-05-01"},
        "rating_composite": "A",
        "rating_history": {"moves": [{"date": "2025-11-02", "action": "upgrade", "notches": 1, "avg": 6.0, "worst": 6}]},
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
    assert b["standing"] == "TSB is a bank in the UK, rated A on average across one of the three, on a stable outlook; the last move was a one-notch upgrade by one of the three on 2 Nov 2025.", "no agency is named"
    assert b["capital"] == "Capital is strong against UK mid-sized banks: CET1 of 14.0% is above the median (median 13.8%); leverage is 5.0%.", "no peer figure for leverage, so it is stated but not judged"
    assert b["liquidity"] == "Liquidity is on the weak side of UK mid-sized banks: LCR of 150% is below the median (median 160%); NSFR is 130%."
    assert b["trends"] == "Since 30 Mar 2025, LCR has fallen 20 points, while CET1 has been broadly flat (figures to 30 Jun 2026)."
    assert b["news"] == "Flagged in the last 90 days: 10 Aug 2026, warn: TSB fined over outage."
    text = S.brief_text(b)
    assert "noise" not in text and "old" not in text
    assert "score" not in text.lower() and "band" not in text.lower(), "the score and band depend on the reader's weightings"


def three(tones=("stable", "negative", "stable"), avg=5.67, worst=6):
    from bankcredit.composite import grade_letter, sort_tones
    return {"n": 3, "avg": avg, "worst": worst, "letter": grade_letter(avg), "worst_letter": grade_letter(worst),
            "tones": sort_tones(tones), "date": "2026-05-01"}


def test_three_agencies_and_mixed_outlooks_read_naturally_and_name_nobody():
    b = S.brief(bank(rating=three(), rating_history={"moves": []}), TODAY)
    assert b["standing"] == "TSB is a bank in the UK, rated A on average across all three, one on a negative outlook and two on a stable outlook."
    b = S.brief(bank(rating=dict(three(("stable", "stable"), 5.5, 6), n=2), rating_history={"moves": []}), TODAY)
    assert b["standing"] == "TSB is a bank in the UK, rated A on average across two of the three, the weakest of them at A, both on a stable outlook.".replace("the weakest of them at A, ", "")
    assert "Fitch" not in S.brief_text(b) and "Moody" not in S.brief_text(b)


def test_a_withdrawal_a_first_rating_and_a_two_notch_move_read_as_english():
    assert S._last_move({"action": "downgrade", "notches": 2, "date": "2024-05-24"}) == "a two-notch downgrade by one of the three on 24 May 2024"
    assert S._last_move({"action": "withdrawal", "notches": None, "date": "2026-03-25"}) == "a withdrawal by one of the three on 25 Mar 2026"
    assert S._last_move({"action": "new", "notches": None, "date": "2026-07-13"}) == "a new rating from one of the three on 13 Jul 2026"


def test_an_unscored_unrated_name_still_gets_an_honest_paragraph():
    b = S.brief(bank(score=None, unscored="unrated", rating=None, rating_composite=None, unrated=True, events=[], type="building_society"), TODAY)
    assert b["standing"] == "TSB is a building society in the UK with no public rating from any of the three main agencies."
    assert b["news"] == "Nothing has been flagged in the last 90 days."


def test_the_fingerprint_is_what_a_written_summary_rests_on():
    fp = S.fingerprint(bank())
    assert fp == {"band": "B", "composite": "A", "worst": "A", "outlooks": "stable", "n": 1, "asof": "2026-06-30", "last_flagged": "2026-08-10"}


def test_what_moved_since_is_said_in_words():
    then = S.fingerprint(bank())
    now = S.fingerprint(bank(band="C", rating=dict(three(("negative", "stable"), 6.5, 7), n=2), rating_composite="A-", asof="2026-09-30",
                             events=[{"date": "2026-09-12", "severity": "bad", "title": "x"}]))
    got = S.changes_since(then, now)
    assert got == ["band moved from B to C", "average rating moved from A to A-", "weakest rating moved from A to A-",
                   "outlooks moved from stable to negative, stable", "rated by two of the three (was one of the three)",
                   "figures updated to 30 Sep 2026 (were 30 Jun 2026)", "a flagged event on 12 Sep 2026 postdates it"]
    assert S.changes_since(then, then) == []


def summary(**over):
    s = {"id": "tsb", "written": "2026-09-16", "background": "TSB is a UK retail bank owned by Sabadell.",
         "synthesis": "Capital is sound, with CET1 of 14.0% a touch above the peer median of 13.8%, and the one agency that rates the bank has it at A with a stable outlook. Liquidity is the weak spot: LCR at 150% sits below the group's 160% and has come down 20 points over four periods. One adverse headline, a fine over an outage, in the last 90 days.",
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
    quoted = bank(peer_ratios={"cet1_ratio": {"p25": 13.5, "p50": 13.7, "p75": 14.2, "n": 16}, "lcr": {"p25": 140, "p50": 160, "p75": 180, "n": 16}})
    assert S.why_due(S.load("tsb"), quoted, TODAY) == "no longer holds: figures not in the paragraph it was written from: 13.8", \
        "the fingerprint is unchanged, but the median it quotes has moved"
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
    named = S.check(summary(synthesis="Fitch rates the bank A with a stable outlook and Moody's has it at A2, which is comfortable for a bank of its size and funding model, and its capital at 14.0% is above the peer median."), para)
    assert any("names a rating agency (Fitch, Moody)" in f for f in named), named
    assert any("own rating symbol" in f for f in named), named


def test_the_profile_shows_both_layers_and_says_what_moved(tmp_path, monkeypatch):
    from bankcredit.site import build
    monkeypatch.setattr(S, "SUMMARIES", tmp_path)
    b = bank()
    html = build.summary_block(b, "2026-09-16T05:00:00Z")
    assert "TSB is a bank in the UK, rated A on average" in html and "No written summary yet" in html
    (tmp_path / "tsb.json").write_text(json.dumps(summary()))
    html = build.summary_block(b, "2026-09-16T05:00:00Z")
    assert "owned by Sabadell" in html and "Written 16 Sep 2026 from figures to 30 Jun 2026." in html
    assert "brief-stale" not in html
    html = build.summary_block(bank(band="C"), "2026-09-16T05:00:00Z")
    assert "Since then: band moved from B to C. This summary predates that." in html
    quoted = bank(peer_ratios={"cet1_ratio": {"p25": 13.5, "p50": 13.7, "p75": 14.2, "n": 16}, "lcr": {"p25": 140, "p50": 160, "p75": 180, "n": 16}})
    html = build.summary_block(quoted, "2026-09-16T05:00:00Z")
    assert "owned by Sabadell" not in html and "rests on figures that have since moved" in html, "a stale figure is never shown as current"
