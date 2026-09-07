from bankcredit import score as S


FULL = {"cet1_ratio": 27.0, "leverage_ratio": 8.0, "total_capital_ratio": 28.0, "lcr": 1000.0, "nsfr": 700.0, "cet1_headroom": 7.5}


def test_rating_anchor_and_unrated_cap():
    aaa = S.compute(FULL, 0.0, 1.0)
    single_a = S.compute(FULL, 0.0, 6.0)
    none = S.compute(FULL, 0.0, None)
    assert aaa.final_score > single_a.final_score > none.final_score
    assert aaa.band == "A" and none.band == "B" and none.unrated
    assert none.final_score <= S.UNRATED_CAP
    assert none.pillars["rating"] == (S.UNRATED_SCORE, S.RATING_WEIGHT)
    assert aaa.coverage == single_a.coverage == none.coverage == 0.83   # ratio coverage, the rating is not "data"


def test_missing_ratios_rescale_and_no_ratios_means_no_score():
    part = S.compute({"cet1_ratio": 14.0, "leverage_ratio": 5.0}, 0.0, 5.0)
    assert part.public_score is not None and part.coverage == round(25 / 60, 2)
    assert S.compute({}, 0.0, 1.0).public_score is None


def test_overlay_cannot_lift_unrated_into_band_a():
    r = S.compute(FULL, 10.0, None)
    assert r.final_score <= S.UNRATED_CAP and r.band == "B"


def test_rating_caps_the_band():
    bbb = S.compute(FULL, 0.0, 9.0)          # BBB with perfect ratios
    bb = S.compute(FULL, 0.0, 12.0)          # BB
    assert bbb.band == "B" and bbb.final_score <= 74.9
    assert bb.band == "C" and bb.final_score <= 64.9
    assert S.compute(FULL, 0.0, 7.0).band == "A"    # A- is not capped
