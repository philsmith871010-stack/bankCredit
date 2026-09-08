from bankcredit import score as S


FULL = {"cet1_ratio": 27.0, "leverage_ratio": 8.0, "total_capital_ratio": 28.0, "lcr": 1000.0, "nsfr": 700.0, "cet1_headroom": 7.5}


def test_rating_anchor_and_unrated_cap():
    aaa = S.compute(FULL, 0.0, 1.0)
    single_a = S.compute(FULL, 0.0, 6.0)
    none = S.compute(FULL, 0.0, None)
    assert aaa.final_score > single_a.final_score
    assert aaa.band == "A"
    assert none.final_score is None and none.unrated and none.reason == "unrated"      # ratios alone earn no score
    assert aaa.coverage == single_a.coverage == none.coverage == 0.83   # ratio coverage, the rating is not "data"


def test_missing_ratios_rescale_and_no_ratios_means_no_score():
    part = S.compute({"cet1_ratio": 14.0, "leverage_ratio": 5.0}, 0.0, 5.0)
    assert part.public_score is not None and part.coverage == round(25 / 60, 2)
    assert S.compute({}, 0.0, 1.0).public_score is None
    only_liq = S.compute({"lcr": 150.0, "nsfr": 120.0}, 0.0, 5.0)               # a rating and liquidity but no capital: no score
    assert only_liq.public_score is None and only_liq.reason == "no capital ratios"


def test_overlay_cannot_lift_bbb_into_band_a():
    r = S.compute(FULL, 10.0, 9.0)
    assert r.final_score <= 74.9 and r.band == "B"


def test_rating_caps_the_band():
    bbb = S.compute(FULL, 0.0, 9.0)          # BBB with perfect ratios
    bb = S.compute(FULL, 0.0, 12.0)          # BB
    assert bbb.band == "B" and bbb.final_score <= 74.9
    assert bb.band == "C" and bb.final_score <= 64.9
    assert S.compute(FULL, 0.0, 7.0).band == "A"    # A- is not capped


def test_a_recorded_reason_replaces_the_generic_withheld_message(tmp_path, monkeypatch):
    """Three entities have their capital measured somewhere other than at this entity. Saying
    "no capital ratios" about them implies we are behind on collection, which is not true, and
    "does not publish Basel ratios" is wrong for one whose group publishes them."""
    import json
    from bankcredit import export, store

    ref = tmp_path / "reference"
    ref.mkdir()
    (ref / "capital-not-published.json").write_text(json.dumps({
        "_note": "ignored",
        "somebank": {"short": "capital reported at group level", "reason": "the group publishes them"},
    }))
    monkeypatch.setattr(store, "DATA", tmp_path)

    npub = export.capital_not_published()
    assert "_note" not in npub, "the note is documentation, not an entity"
    assert npub["somebank"]["short"] == "capital reported at group level"


def test_the_shipped_records_each_carry_a_reason_and_a_source():
    """A withheld score that states a reason has to be able to show its working. Read from the
    repository rather than through store.DATA, which the tests point at a scratch directory."""
    import json
    from pathlib import Path
    shipped = Path(__file__).resolve().parents[1] / "data" / "reference" / "capital-not-published.json"
    records = {k: v for k, v in json.loads(shipped.read_text()).items() if not k.startswith("_")}
    assert records, "the file holds at least one record"
    for entity, r in records.items():
        assert r.get("short"), entity
        assert r.get("reason"), entity
        assert r.get("source", "").startswith("http"), entity
        assert r.get("standing"), entity
