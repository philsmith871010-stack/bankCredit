"""Annual and quarterly accounts for listed banks from Yahoo Finance's fundamentals feed, the
same public endpoint the quote page reads. Four annual and five quarterly points per name:
total assets, customer deposits, equity, profit, net interest income, operating costs. Ratios
are computed as the ESEF adapter computes them, so a Singapore bank and a building society
read on one definition. It fills in the listed names outside the ESEF register (Asia, the
Gulf, Australia, Canada, Germany's listed pair) and is ranked below ESEF and regulator data
where both exist.
"""
from __future__ import annotations

import logging
from datetime import date

from .. import store
from ..models import Entity, Fact
from .base import Adapter, register
from .esef import ratios
from .yahoo import HEADERS

log = logging.getLogger("bankcredit.fundamentals")
URL = "https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{symbol}"
# Yahoo's NetIncome and StockholdersEquity are the owners' share and go together into return on
# equity; return on assets takes the profit with minorities in, as the ESEF reading does. TotalRevenue
# is a bank's net operating income, the income cost to income needs, since the feed has no impairment
# line to rebuild it from pre-tax profit (pre-tax plus costs is income net of provisions).
ANNUAL = {"annualTotalAssets": "assets", "annualTotalDeposits": "deposits",
          "annualStockholdersEquity": "equity_parent", "annualTotalEquityGrossMinorityInterest": "equity",
          "annualNetIncome": "profit_parent", "annualNetIncomeIncludingNoncontrollingInterests": "profit",
          "annualPretaxIncome": "pretax", "annualNetInterestIncome": "nii",
          "annualOperatingExpense": "opex", "annualTotalRevenue": "income_total"}
QUARTERLY = {"quarterlyTotalAssets": "assets", "quarterlyTotalDeposits": "deposits", "quarterlyStockholdersEquity": "equity"}
# Entities whose ticker is a listed parent's. The share price is the nearest market signal a subsidiary
# without a listing of its own has, so the price adapter reads the ticker; the accounts behind it are
# the group's, so they are not read here. DBS Bank stays: DBS Group Holdings is a non-operating holding
# company over that one bank, and its accounts are the bank's to within rounding.
GROUP_TICKER = {
    "macquarie-bank": "MQG.AX is Macquarie Group, whose non-bank half Macquarie Bank does not own",
    "investec": "INVP.L reports the Investec plc and Investec Ltd DLC, about twice Investec plc",
}


@register
class FundamentalsAdapter(Adapter):
    name = "fundamentals"
    cadence = "quarterly"

    def __init__(self):
        super().__init__()
        self.session.headers.update(HEADERS)

    def discover(self):
        # configured tickers only: a name search returns the parent, a bond line or another bank entirely
        # (TSB found Permanent TSB), and a parent's accounts must never stand for a subsidiary's
        return [e for e in self.entities if (e.tickers or "").strip() and e.id not in GROUP_TICKER]

    def fetch(self, e: Entity):
        symbol = next((t.strip() for t in (e.tickers or "").split(",") if t.strip()), None)
        if not symbol:
            return None
        types = ",".join(list(ANNUAL) + list(QUARTERLY))
        import time
        r = self.session.get(URL.format(symbol=symbol), params={"type": types, "period1": 1262304000, "period2": int(time.time()) + 86400}, timeout=60)   # a far-future end returns nothing
        if r.status_code != 200:
            log.warning("fundamentals: %s (%s) -> %s", e.id, symbol, r.status_code)
            return None
        try:
            return {"symbol": symbol, "result": r.json()["timeseries"]["result"]}
        except (KeyError, ValueError):
            return None

    def parse(self, e: Entity, raw) -> list[Fact]:
        if not raw:
            return []
        annual: dict[date, dict] = {}
        quarterly: dict[date, dict] = {}
        ccy = ""
        for block in raw["result"]:
            t = block["meta"]["type"][0]
            code = ANNUAL.get(t) or QUARTERLY.get(t)
            for v in block.get(t, []):
                try:
                    d = date.fromisoformat(v["asOfDate"])
                    val = float(v["reportedValue"]["raw"])
                except (KeyError, TypeError, ValueError):
                    continue
                ccy = ccy or v.get("currencyCode", "")
                (annual if t in ANNUAL else quarterly).setdefault(d, {})[code] = val
        out = []
        doc = f"https://finance.yahoo.com/quote/{raw['symbol']}/financials"
        for d, m in ratios(annual).items():
            for metric, val in m.items():
                if metric == "efficiency_ratio" and "opex" not in annual.get(d, {}):
                    continue
                out.append(self._fact(e, d, metric, val, ccy, doc))
        annual_dates = set(annual)
        for d, v in quarterly.items():
            if d in annual_dates:
                continue
            for code, metric in (("assets", "total_assets"), ("deposits", "deposits")):
                if code in v:
                    out.append(self._fact(e, d, metric, round(v[code] / 1e6, 2), ccy, doc))
        log.info("fundamentals: %s (%s) -> %d facts", e.id, raw["symbol"], len(out))
        return out

    def _fact(self, e, d, metric, val, ccy, doc) -> Fact:
        amount = metric in ("total_assets", "deposits")
        return Fact(entity_id=e.id, reference_date=d, metric=metric, value=val, unit="ccy_m" if amount else "pct",
                    currency=ccy if amount else "", basis="consolidated", source=self.name, document=doc, method="api",
                    confidence=0.8 if amount or metric in ("roe", "roa") else 0.7)

    def validate(self, records):
        return [r for r in records if r.unit != "pct" or -100 < r.value < 200]

    def load(self, records) -> int:
        for ent in {f.entity_id for f in records}:
            store.drop("facts", entity_id=ent, source=self.name)
        return store.upsert("facts", records)
