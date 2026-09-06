"""Smoke test for the Yahoo price adapter against the live endpoint.

Writes only to BANKCREDIT_DATA=/tmp/yahoo-smoke, never to the repo's data/ directory.
"""
import os
import tempfile
import shutil
from datetime import date, timedelta

SMOKE_DIR = "/tmp/yahoo-smoke"
os.environ.setdefault("BANKCREDIT_DATA", tempfile.mkdtemp(prefix="smoke-"))

import pytest  # noqa: E402

from bankcredit import store  # noqa: E402
from bankcredit.adapters.yahoo import YahooPriceAdapter, drawdown_52w, realised_vol  # noqa: E402

SYMBOLS = {"barclays": "BARC.L", "deutsche-bank": "DBK.DE", "commonwealth-bank": "CBA.AX"}


@pytest.fixture(scope="module")
def prices():
    shutil.rmtree(SMOKE_DIR, ignore_errors=True)  # force the 2y backfill path

    adapter = YahooPriceAdapter()
    ents = {e.id: e for e in adapter.entities}
    items = [(ents[eid], sym) for eid, sym in SYMBOLS.items()]
    adapter.discover = lambda: iter(items)

    total, status = adapter.run()
    assert status == "ok", status
    assert not adapter.not_found, adapter.not_found
    assert total >= 600
    return store.read("prices")


@pytest.mark.parametrize("entity_id,symbol", list(SYMBOLS.items()))
def test_history(prices, entity_id, symbol):
    df = prices[(prices.entity_id == entity_id) & (prices.symbol == symbol)]
    assert len(df) >= 200, f"{symbol}: only {len(df)} closes"
    assert (df.close > 0).all()
    assert df.source.eq("yahoo").all()
    assert df.currency.iloc[0] in {"GBp", "EUR", "AUD"}
    latest = date.fromisoformat(max(df.date))
    assert latest >= date.today() - timedelta(days=7), f"{symbol}: latest close {latest} is stale"
    assert min(df.date) <= (date.today() - timedelta(days=700)).isoformat()


@pytest.mark.parametrize("entity_id", list(SYMBOLS))
def test_metrics(prices, entity_id):
    vol = realised_vol(entity_id)
    dd = drawdown_52w(entity_id)
    print(f"\n{entity_id:20s} realised_vol_30d={vol:6.2f}%  drawdown_52w={dd:6.2f}%")
    assert vol is not None and 0 < vol < 200
    assert dd is not None and 0 <= dd < 100


def test_missing_entity_returns_none(prices):
    assert realised_vol("no-such-entity") is None
    assert drawdown_52w("no-such-entity") is None


def test_resolver_uses_search_and_caches(tmp_path, monkeypatch):
    from bankcredit.adapters import yahoo as Y
    from bankcredit import store
    from bankcredit.models import Entity
    monkeypatch.setattr(store, "DATA", tmp_path)

    class R:
        status_code = 200
        def json(self):
            return {"quotes": [{"symbol": "BN9.DE", "exchange": "GER", "quoteType": "EQUITY"},
                               {"symbol": "BNY", "exchange": "NYQ", "quoteType": "EQUITY"}]}

    class S:
        calls = 0
        def get(self, *a, **k):
            S.calls += 1
            return R()

    ad = Y.YahooPriceAdapter.__new__(Y.YahooPriceAdapter)
    ad.session = S()
    e = Entity(id="bny", name="The Bank of New York Mellon Corporation", short_name="BNY", country="US", type="holding",
               region="us_ch", group="", lei="", tickers="BK", fdic_cert="", peer_group="us", active=True)
    assert ad._resolve(e) == "BNY"                       # the home-market listing, not the Frankfurt line
    assert ad._resolve(e) == "BNY" and S.calls == 1      # cached
