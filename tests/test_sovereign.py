"""Sovereign ratings: the right issuer, the right agencies, and nothing that only looks like one."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from bankcredit.adapters.sovereign import AGENCY_ALLOW, SovereignRatingsAdapter, _names
from bankcredit.export import _sovereigns

rank = SovereignRatingsAdapter._rank


def doc(cra="Fitch Ratings Limited", name="Long-term rating", value="AA", hz="Long Term",
        status="Maintained under stable outlook", issuer="United Kingdom", when="2026-08-14"):
    return {"craName": cra, "issuerRatingName": name, "ratingValueLabel": value,
            "timeHorizonDescr": hz, "ratingStatusLabel": status, "issuerName": issuer,
            "racValidityDatetimeStr": when, "id": f"{cra}-{name}-{when}",
            "localForeignCurrencyValue": "Foreign currency", "lastActionTypeLabel": "Affirmation"}


def parse(docs, cc="GB"):
    a = SovereignRatingsAdapter.__new__(SovereignRatingsAdapter)
    return a.parse((cc, {"issuer": "United Kingdom"}), docs)


# ---- which filings count as the sovereign's own rating ---------------------------------------
@pytest.mark.parametrize("name", ["", "Long-term rating", "Issuer Credit Rating",
                                  "LT Issuer Credit Rating", "Long Term Issuer Default Rating"])
def test_the_headline_names_rank_first(name):
    """Scope writes 'Long-term rating' and JCR files no name at all; the bank mapper calls both
    'other' and drops them, which left three countries with nothing."""
    assert rank(name) == 0


def test_a_governments_own_bonds_are_accepted_but_ranked_below_the_issuer_rating():
    assert rank("Senior Unsecured Debt Rating") == 1


@pytest.mark.parametrize("name", ["Short-Term Rating", "Covered Bond Rating",
                                  "Structured Finance Rating", "Subordinated Debt Rating"])
def test_everything_else_is_left_out(name):
    assert rank(name) is None


def test_the_issuer_rating_wins_where_an_agency_files_both():
    got = parse([doc(name="Senior Unsecured Debt Rating", value="AA-"),
                 doc(name="Issuer Credit Rating", value="AA")])
    assert [r.value for r in got] == ["AA"]


# ---- who counts as an agency -----------------------------------------------------------------
def test_a_country_risk_score_is_not_a_credit_rating():
    """The register carries the Economist Intelligence Unit, which had France at BBB while S&P and
    Fitch had AA-. Averaging the two would have said something false."""
    got = parse([doc(cra="The Economist Intelligence Unit Ltd", name="", value="BBB"),
                 doc(cra="Fitch Ratings Limited", value="AA-")])
    assert [(r.agency, r.value) for r in got] == [("fitch", "AA-")]
    assert "the" not in AGENCY_ALLOW


def test_a_withdrawn_rating_is_not_collected():
    assert parse([doc(status="Withdrawal")]) == []


def test_a_short_horizon_filing_is_not_collected():
    assert parse([doc(hz="Short Term", name="Short-Term Rating", value="F1+")]) == []


# ---- one country, several spellings ----------------------------------------------------------
def test_a_country_carries_every_name_the_register_files_it_under():
    """France is 'French Republic' to Scope and 'Republic of France' to S&P."""
    meta = {"issuer": "French Republic", "also": ["France", "Republic of France"]}
    assert _names(meta) == ["French Republic", "France", "Republic of France"]


def test_the_reference_file_covers_every_country_the_universe_holds():
    # the repo's own reference data, not the scratch directory the suite runs against
    repo = Path(__file__).resolve().parent.parent / "data" / "reference" / "sovereigns.json"
    ref = json.loads(repo.read_text(encoding="utf-8"))
    assert len(ref) >= 20
    assert all("issuer" in v and "short" in v for v in ref.values())


# ---- the composite shown beside a bank -------------------------------------------------------
def test_the_composite_is_the_median_of_the_agencies():
    df = pd.DataFrame([{"entity_id": "GB", "agency": a, "value": v, "outlook": "stable",
                        "action_date": "2026-08-14"}
                       for a, v in [("fitch", "AA-"), ("kbra", "AA"), ("scope", "AA")]])
    out = _sovereigns(df)["GB"]
    assert out["composite"] == "AA" and out["n"] == 3
    assert [a["agency"] for a in out["agencies"]] == ["fitch", "kbra", "scope"]


def test_no_sovereign_data_means_no_claim():
    assert _sovereigns(pd.DataFrame()) == {}
