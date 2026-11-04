from datetime import date

from bankcredit.adapters import fundamentals as F
from bankcredit.models import Entity


def _block(t, rows):
    return {"meta": {"type": [t]}, t: [{"asOfDate": d, "currencyCode": "SGD", "reportedValue": {"raw": v}} for d, v in rows]}


def test_yahoo_rows_become_the_same_ratios(monkeypatch):
    raw = {"symbol": "D05.SI", "result": [
        _block("annualTotalAssets", [("2024-12-31", 700e9), ("2025-12-31", 740e9)]),
        _block("annualStockholdersEquity", [("2024-12-31", 60e9), ("2025-12-31", 64e9)]),
        _block("annualNetIncome", [("2025-12-31", 10e9)]),
        _block("annualNetInterestIncome", [("2025-12-31", 14e9)]),
        _block("annualOperatingExpense", [("2025-12-31", 8e9)]),
        _block("annualTotalRevenue", [("2025-12-31", 20e9)]),
        _block("quarterlyTotalAssets", [("2025-12-31", 740e9), ("2026-03-31", 750e9)]),
    ]}
    ad = F.FundamentalsAdapter.__new__(F.FundamentalsAdapter)
    e = Entity(id="dbs", name="DBS", short_name="DBS", country="SG", type="bank", region="asia", group="", lei="", tickers="D05.SI", peer_group="asia", active=True)
    facts = ad.parse(e, raw)
    by = {(f.reference_date, f.metric): f.value for f in facts}
    assert by[(date(2025, 12, 31), "roe")] == round(10 / 62 * 100, 4)
    assert by[(date(2025, 12, 31), "efficiency_ratio")] == 40.0
    assert by[(date(2026, 3, 31), "total_assets")] == 750000 and (date(2025, 12, 31), "total_assets") in by
    assert all(f.currency == "SGD" for f in facts if f.metric == "total_assets")


def _entity(eid, ticker):
    return Entity(id=eid, name=eid, short_name=eid, country="AT", type="bank", region="eu", group="", lei="", tickers=ticker, peer_group="eu", active=True)


def test_owners_return_on_owners_equity_whole_profit_on_assets_and_revenue_for_cost_to_income():
    raw = {"symbol": "EBS.VI", "result": [            # Erste 2024-25 as the feed has them
        _block("annualTotalAssets", [("2024-12-31", 353736e6), ("2025-12-31", 368574e6)]),
        _block("annualStockholdersEquity", [("2024-12-31", 23135e6), ("2025-12-31", 26297e6)]),
        _block("annualTotalEquityGrossMinorityInterest", [("2024-12-31", 30768e6), ("2025-12-31", 34664e6)]),
        _block("annualNetIncome", [("2025-12-31", 3510e6)]),
        _block("annualNetIncomeIncludingNoncontrollingInterests", [("2025-12-31", 4297e6)]),
        _block("annualPretaxIncome", [("2025-12-31", 5400e6)]),
        _block("annualOperatingExpense", [("2025-12-31", 5984e6)]),
        _block("annualTotalRevenue", [("2025-12-31", 11761e6)]),
    ]}
    ad = F.FundamentalsAdapter.__new__(F.FundamentalsAdapter)
    by = {(f.reference_date, f.metric): f.value for f in ad.parse(_entity("erste-group", "EBS.VI"), raw)}
    y = date(2025, 12, 31)
    assert by[(y, "roe")] == round(3510 / ((23135 + 26297) / 2) * 100, 4)
    assert by[(y, "roa")] == round(4297 / ((353736 + 368574) / 2) * 100, 4)     # 1.19, as the ESEF reading has it
    assert by[(y, "efficiency_ratio")] == round(5984 / 11761 * 100, 4)          # not 5984 / (5400 + 5984): that is net of provisions


def test_a_parent_listing_gives_a_price_but_not_accounts():
    ad = F.FundamentalsAdapter.__new__(F.FundamentalsAdapter)
    ad.entities = [_entity("macquarie-bank", "MQG.AX"), _entity("investec", "INVP.L"), _entity("dbs", "D05.SI"), _entity("tsb", "")]
    assert [e.id for e in ad.discover()] == ["dbs"]
