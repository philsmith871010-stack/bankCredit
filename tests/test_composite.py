"""One rating from three, with no agency named on it."""
from __future__ import annotations

import pandas as pd

from bankcredit import composite as C
from bankcredit.export import public_events


def rows(*spec):
    return [{"agency": a, "value": v, "outlook": o, "date": "2026-05-01"} for a, v, o in spec]


def test_the_average_and_the_weakest_are_over_the_three_main_agencies_only():
    c = C.composite(rows(("fitch", "A+", "stable"), ("sp", "A", "negative"), ("moodys", "A2", "watch negative"), ("dbrs", "AAA", "")))
    assert c["n"] == 3 and c["avg"] == 5.67 and c["worst"] == 6
    assert c["letter"] == "A" and c["worst_letter"] == "A"
    assert c["tones"] == ["watch negative", "negative", "stable"], "worst first, and Moody's A2 reads as A"
    assert C.composite(rows(("dbrs", "AAA", "stable"))) is None
    assert C.composite([]) is None


def test_a_half_rounds_to_the_weaker_notch():
    c = C.composite(rows(("fitch", "A+", ""), ("sp", "A", "")))
    assert c["avg"] == 5.5 and c["letter"] == "A" and c["worst_letter"] == "A"


def test_the_words_never_name_an_agency():
    c = C.composite(rows(("fitch", "A+", "stable"), ("sp", "A", "negative"), ("moodys", "A2", "stable")))
    assert C.describe(c) == "A on average across all three, one on a negative outlook and two on a stable outlook"
    c = C.composite(rows(("fitch", "AA-", "stable"), ("sp", "A", "stable")))
    assert C.describe(c) == "A+ on average across two of the three, the weakest of them at A, both on a stable outlook"
    assert C.describe(C.composite(rows(("moodys", "Baa1", "positive")))) == "BBB+ on average across one of the three, on a positive outlook"
    assert C.describe(None) == "no public rating from any of the three main agencies"
    assert C.tone_words(["stable", "stable", "stable"]) == "all three on a stable outlook"
    assert C.tone_words(["stable", ""]) == "one on a stable outlook and one with no outlook published"
    assert C.tone_words([]) == ""


def test_the_register_labels_reduce_to_five_tones():
    assert C.tone("Placed under negative watch") == "watch negative"
    assert C.tone("watch positive") == "watch positive"
    assert C.tone("stable") == "stable" and C.tone("negative") == "negative" and C.tone("") == ""
    assert C.tone("developing") == "", "an evolving or developing outlook is not a direction"


def test_an_action_loses_its_agency_and_its_symbol():
    assert C.public_action("upgrade", "long") == "One of the three agencies upgraded its long-term rating"
    assert C.public_action("Placed under negative watch", "short") == "One of the three agencies placed its short-term rating under negative watch"
    assert C.public_action("affirmation", "long") == "One of the three agencies affirmed its long-term rating"
    assert C.public_action("new", "long") == "One of the three agencies assigned a new long-term rating"
    assert C.public_action("withdrawal", "long") == "One of the three agencies withdrew its long-term rating"


def test_the_events_a_page_sees_carry_no_attributed_action():
    ev = pd.DataFrame([
        {"entity_id": "x", "event_id": "1", "date": "2026-09-01", "type": "rating", "title": "Fitch upgrade: Long Term Issuer Default Rating A+", "detail": "long", "severity": "good"},
        {"entity_id": "x", "event_id": "2", "date": "2026-09-01", "type": "rating", "title": "Moody's placed under negative watch: Counterparty Risk Rating P-1", "detail": "short", "severity": "warn"},
        {"entity_id": "x", "event_id": "3", "date": "2026-09-01", "type": "rating", "title": "DBRS downgrade: Issuer Debt Rating A(L)", "detail": "long", "severity": "warn"},
        {"entity_id": "x", "event_id": "4", "date": "2026-09-01", "type": "news", "title": "Fitch says banks are fine - FT", "detail": "", "severity": "info"},
    ])
    out = public_events(ev)
    assert list(out.event_id) == ["1", "2", "4"], "an agency outside the three is not shown at all"
    assert list(out.title[:2]) == ["One of the three agencies upgraded its long-term rating",
                                   "One of the three agencies placed its short-term rating under negative watch"]
    assert out.title.iloc[2].startswith("Fitch says"), "a headline is news, not a rating"
    assert list(out.severity[:2]) == ["good", "warn"]
    assert public_events(pd.DataFrame()).empty
