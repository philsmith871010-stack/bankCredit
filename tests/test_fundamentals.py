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
