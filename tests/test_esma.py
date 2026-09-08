"""Smoke test for the ESMA ratings adapter against the live Solr endpoint (three entities)."""
import os
import tempfile
import shutil
from datetime import date
from pathlib import Path

SMOKE_DIR = "/tmp/esma-smoke"
os.environ.setdefault("BANKCREDIT_DATA", tempfile.mkdtemp(prefix="smoke-"))

import pytest  # noqa: E402

from bankcredit import store  # noqa: E402
from bankcredit.adapters.esma import ESMARatingsAdapter, agency_code, outlook, rating_type  # noqa: E402

SMOKE_IDS = ["nationwide", "barclays-bank", "dbs"]


@pytest.fixture(scope="module")
def ratings():
    shutil.rmtree(SMOKE_DIR, ignore_errors=True)
    adapter = ESMARatingsAdapter()
    picked = [e for e in adapter.entities if e.id in SMOKE_IDS]
    assert len(picked) == 3
    adapter.discover = lambda: picked
    total, status = adapter.run()
    assert status == "ok", status
    df = store.read("ratings")
    cols = ["entity_id", "agency", "rating_type", "horizon", "value", "outlook", "action", "action_date"]
    print("\n" + df[cols].sort_values(["entity_id", "agency", "rating_type", "horizon"]).to_string(index=False))
    return df


def _one(df, **where):
    sub = df
    for k, v in where.items():
        sub = sub[sub[k] == v]
    assert len(sub) == 1, f"{where}: {len(sub)} rows"
    return sub.iloc[0]


def test_nationwide(ratings):
    assert _one(ratings, entity_id="nationwide", agency="fitch", rating_type="idr", horizon="long")["value"] == "AA-"
    assert _one(ratings, entity_id="nationwide", agency="sp", rating_type="issuer", horizon="long")["value"] == "A+"


def test_barclays_bank(ratings):
    row = _one(ratings, entity_id="barclays-bank", agency="fitch", rating_type="idr", horizon="long")
    assert row["value"]


def test_dbs(ratings):
    row = _one(ratings, entity_id="dbs", agency="moodys", rating_type="deposit", horizon="long")
    assert row["value"]


def test_no_duplicates_and_no_empty(ratings):
    assert ratings["value"].str.len().gt(0).all()
    assert not ratings.duplicated(["entity_id", "agency", "rating_type", "horizon"]).any()
    assert not (ratings["rating_type"] == "other").any()


def test_actions_feed():
    adapter = ESMARatingsAdapter()
    ent = next(e for e in adapter.entities if e.id == "nationwide")
    rows = adapter.actions(ent, date(2026, 1, 1))
    assert rows, "expected at least one rating action for Nationwide in 2026"
    assert all(r["date"] and r["date"] >= date(2026, 1, 1) for r in rows)
    fitch = [r for r in rows if r["agency"] == "fitch" and r["rating_type"] == "idr" and r["horizon"] == "long"]
    assert any(r["action"] == "Upgrade" and r["value"] == "AA-" for r in fitch)
    for r in sorted(rows, key=lambda r: r["date"], reverse=True)[:10]:
        print(r["date"], r["agency"], r["rating_type"], r["horizon"], r["action"], r["value"])


def test_mappings():
    assert agency_code("Standard & Poor's Credit Market Services Europe Limited") == "sp"
    assert agency_code("Moody's Investors Service Ltd") == "moodys"
    assert agency_code("Kroll Bond Rating Agency") == "kbra"
    assert agency_code("Japan Credit Rating Agency Ltd") == "jcr"
    assert agency_code("Capital Intelligence Ratings Ltd") == "capital"
    assert rating_type("Long Term Issuer Default Rating") == "idr"
    assert rating_type("Long Term Issuer Default Rating (xgs)") == "other"
    assert rating_type("Resolution Counterparty Rating") == "resolution_counterparty"
    assert rating_type("Counterparty Risk Rating") == "counterparty"
    assert rating_type("Credit Rating - Deposits") == "deposit"
    assert rating_type("Issuer Debt Rating") == "issuer"
    assert rating_type("Certificate Of Deposit") == "other"
    assert rating_type("Derivative Counterparty Rating") == "other"
    assert outlook("Maintained under stable outlook") == "stable"
    assert outlook("Placed under negative watch") == "watch negative"
    assert outlook("Removed under negative watch") == ""
    assert outlook("Placed under evolving watch") == ""
    assert outlook("") == ""


WITHDRAWN_DOCS = [
    {"craName": "Moody's Investors Service Ltd", "ratingValueLabel": "Baa2",
     "issuerRatingName": "Counterparty Risk Rating", "timeHorizonDescr": "Long Term",
     "ratingStatusLabel": "Withdrawal", "lastActionTypeLabel": "Withdrawn",
     "racValidityDatetimeStr": "2022-02-01T00:00:00Z", "id": "w1"},
    {"craName": "Fitch Ratings Ltd", "ratingValueLabel": "A-",
     "issuerRatingName": "Issuer Rating", "timeHorizonDescr": "Long Term",
     "ratingStatusLabel": "Stable", "lastActionTypeLabel": "Affirmed",
     "racValidityDatetimeStr": "2026-03-01T00:00:00Z", "id": "l1"},
]


def test_a_withdrawn_rating_is_kept_out_of_the_scored_ratings():
    """A withdrawn rating must never reach a score. It is worth keeping and showing - an agency
    that rated a bank and stopped says more than a bare "unrated" - but not in the same table."""
    from bankcredit.models import Entity
    from bankcredit.adapters.esma import ESMARatingsAdapter
    a = ESMARatingsAdapter.__new__(ESMARatingsAdapter)
    ent = Entity(id="somebank", name="Some Bank", short_name="Some", country="GB",
                 type="bank", region="uk", active=True)
    live = a.validate(a.parse(ent, WITHDRAWN_DOCS))
    assert [r.value for r in live] == ["A-"], "only the live rating scores"
    assert [(r.agency, r.value) for r in a._withdrawn] == [("moodys", "Baa2")]


def test_a_live_rating_wins_over_a_withdrawn_one_of_the_same_kind():
    """An agency that withdrew and later re-rated must not appear in both tables at once."""
    from bankcredit.models import Entity
    from bankcredit.adapters.esma import ESMARatingsAdapter
    a = ESMARatingsAdapter.__new__(ESMARatingsAdapter)
    ent = Entity(id="somebank", name="Some Bank", short_name="Some", country="GB",
                 type="bank", region="uk", active=True)
    docs = [dict(WITHDRAWN_DOCS[0]),
            dict(WITHDRAWN_DOCS[0], ratingValueLabel="Baa1", ratingStatusLabel="Stable",
                 lastActionTypeLabel="Upgraded", racValidityDatetimeStr="2026-01-01T00:00:00Z", id="l2")]
    live = a.validate(a.parse(ent, docs))
    keys = {(r.entity_id, r.agency, r.rating_type, r.horizon) for r in live}
    kept = [r for r in a._withdrawn if (r.entity_id, r.agency, r.rating_type, r.horizon) not in keys]
    assert [r.value for r in live] == ["Baa1"] and kept == []
