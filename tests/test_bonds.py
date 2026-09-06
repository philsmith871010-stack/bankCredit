from datetime import date, timedelta

import pandas as pd

from bankcredit.adapters import bonds as B
from bankcredit import export


def test_issuer_matching_prefers_longest_token():
    assert B.match_issuer("Barclays Bank PLC 3,25% 24/29") == "barclays-bank"
    assert B.match_issuer("Barclays PLC 4,375% 23/28") == "barclays"
    assert B.match_issuer("HSBC Holdings PLC 1,5% 21/27") == "hsbc-holdings"
    assert B.match_issuer("NatWest Markets PLC 0,8% 20/25") is None
    assert B.match_issuer("Zypern, Republik 3,25% 26/36") is None


def test_maturity_year_and_perpetuals():
    assert B.maturity_year("Deutsche Bank AG 4% 24/29") == 2029
    assert B.maturity_year("Deutsche Bank AG 6% 20/und") is None
    assert B.SUB_TOKENS.search("Lloyds Banking Group PLC 5,125% 21/und Sub")


def test_ytm_direction():
    assert B.ytm(100.0, 4.0, 5) == 4.0
    assert B.ytm(95.0, 4.0, 5) > 4.0


def _q(isin, d, y):
    return {"isin": isin, "date": str(d), "price": 100.0, "yield": y, "source": "frankfurt"}


def test_bond_changes_are_relative_to_peers_in_currency():
    today = date.today()
    bonds = pd.DataFrame([{"isin": "A1", "entity_id": "a", "currency": "EUR"}, {"isin": "B1", "entity_id": "b", "currency": "EUR"},
                          {"isin": "C1", "entity_id": "c", "currency": "EUR"}])
    quotes = pd.DataFrame([_q("A1", today - timedelta(days=31), 3.0), _q("A1", today, 3.60),     # +60 bp
                           _q("B1", today - timedelta(days=31), 3.0), _q("B1", today, 3.10),     # +10 bp
                           _q("C1", today - timedelta(days=31), 3.0), _q("C1", today, 3.10)])    # +10 bp
    out = export._bond_changes(bonds, quotes)
    assert out["a"]["bond_change30"] == 50.0          # 60 less the peer median of 10
    assert out["b"]["bond_change30"] == 0.0
    assert out["a"]["bond_window"] == 31 and out["a"]["bond_count"] == 1


def test_bond_changes_skip_stale_and_short_histories():
    today = date.today()
    bonds = pd.DataFrame([{"isin": "A1", "entity_id": "a", "currency": "EUR"}, {"isin": "B1", "entity_id": "b", "currency": "EUR"}])
    quotes = pd.DataFrame([_q("A1", today - timedelta(days=40), 3.0), _q("A1", today - timedelta(days=20), 3.5),   # stale
                           _q("B1", today - timedelta(days=2), 3.0), _q("B1", today, 3.5)])                        # too short
    assert export._bond_changes(bonds, quotes) == {}


def test_market_uses_bonds_only_without_fresh_cds():
    empty = pd.DataFrame()
    sig = export._market(empty, empty, {"bond_change30": 35.0, "bond_count": 2, "bond_asof": str(date.today()), "bond_window": 30})
    assert sig["direction"] == "down" and sig["label"] == "Bonds widening"
    today = date.today()
    cds = pd.DataFrame([{"entity_id": "a", "date": str(today - timedelta(days=31)), "tier": "senior", "source": "ice", "level_bp": 50.0},
                        {"entity_id": "a", "date": str(today), "tier": "senior", "source": "ice", "level_bp": 40.0}])
    sig = export._market(empty, cds, {"bond_change30": 35.0, "bond_count": 2, "bond_asof": str(today), "bond_window": 30})
    assert sig["direction"] == "up"                  # the CDS wins when it is fresh
    assert export._overlay({"bond_change30": 35.0}, []) == -1.0
    assert export._overlay({"cds5y": 40.0, "cds_change30": -12.0, "bond_change30": 35.0}, []) == 1.5


def test_cds_move_is_split_against_itraxx():
    today = date.today()
    empty = pd.DataFrame()
    cds = pd.DataFrame([{"entity_id": "a", "date": str(today - timedelta(days=31)), "tier": "senior", "source": "ice", "level_bp": 50.0},
                        {"entity_id": "a", "date": str(today), "tier": "senior", "source": "ice", "level_bp": 70.0}])
    index = pd.DataFrame([{"date": str(today - timedelta(days=31)), "value": 60.0}, {"date": str(today), "value": 78.0}])
    sig = export._market(empty, cds, None, index)
    assert sig["cds_change30"] == 20.0 and sig["cds_index_change30"] == 18.0 and sig["cds_excess30"] == 2.0
    assert sig["label"] == "Widening (with the market)"
    index.loc[1, "value"] = 61.0
    assert export._market(empty, cds, None, index)["label"] == "Widening (bank-specific)"
    assert "cds_excess30" not in export._market(empty, cds, None, None) or export._market(empty, cds, None, None)["cds_excess30"] is None
