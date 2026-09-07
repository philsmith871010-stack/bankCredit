"""SEC EDGAR XBRL company facts: regulatory capital ratios tagged in 10-Q and 10-K filings.

No key; a descriptive User-Agent is mandatory. Only some US holding companies tag
their Basel ratios with the standard us-gaap elements (Morgan Stanley, BNY, Goldman
Sachs in part); the rest keep them in unstructured tables, which the pillar3 adapter
reads from their Pillar 3 PDFs instead. Values are fractions in XBRL and stored as
percent, consolidated basis, confidence 0.95.
"""
from __future__ import annotations

import logging
import time
from datetime import date

from .. import store
from ..models import Entity, Fact
from .base import Adapter, register

log = logging.getLogger("bankcredit.edgar")

UA = {"User-Agent": "PWLBtoday Counterparty research (philsmith871010@gmail.com)", "Accept-Encoding": "gzip"}
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
TAGS = {   # us-gaap tag -> (metric, unit, scale)
    "CommonEquityTierOneCapitalRatio": ("cet1_ratio", "pct", 100),
    "TierOneRiskBasedCapitalToRiskWeightedAssets": ("tier1_ratio", "pct", 100),
    "CapitalToRiskWeightedAssets": ("total_capital_ratio", "pct", 100),
    "SupplementaryLeverageRatio": ("leverage_ratio", "pct", 100),
    "TierOneLeverageCapitalToAverageAssets": ("tier1_leverage", "pct", 100),
    "RiskWeightedAssets": ("rwa", "ccy_m", 1e-6),
    "CommonEquityTierOneCapital": ("cet1_capital", "ccy_m", 1e-6),
    "TierOneRiskBasedCapital": ("tier1_capital", "ccy_m", 1e-6),
}
SINCE = date(2019, 1, 1)
# accounts tags for the profitability ratios, read as annual (10-K) figures and computed as the ESEF adapter does
ACCOUNTS = {"Assets": ("assets", "instant"), "StockholdersEquity": ("equity", "instant"), "Deposits": ("deposits", "instant"),
            "LoansAndLeasesReceivableNetReportedAmount": ("loans", "instant"),
            "NetIncomeLoss": ("profit", "duration"), "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest": ("pretax", "duration"),
            "InterestIncomeExpenseNet": ("nii", "duration"), "NoninterestExpense": ("opex", "duration"), "Revenues": ("revenue", "duration"),
            "ProvisionForLoanLeaseAndOtherLosses": ("impairment", "duration"), "ProvisionForLoanLossesExpensed": ("impairment", "duration")}
ACCOUNTS_SINCE = date(2012, 1, 1)


@register
class EdgarAdapter(Adapter):
    name = "edgar"
    cadence = "quarterly"
    regions = ("us_ch",)

    def __init__(self):
        super().__init__()
        self.session.headers.update(UA)
        self._ciks: dict[str, int] | None = None

    def _cik(self, e: Entity) -> int | None:
        if self._ciks is None:
            r = self.session.get(TICKERS_URL, timeout=60)
            r.raise_for_status()
            self._ciks = {v["ticker"].upper(): int(v["cik_str"]) for v in r.json().values()}
        for t in (x.strip().upper() for x in e.tickers.split(",") if x.strip()):
            if "." not in t and t in self._ciks:
                return self._ciks[t]
        return None

    def discover(self):
        for e in self.entities:
            if e.country == "US" and e.tickers:
                yield e

    def fetch(self, e: Entity):
        cik = self._cik(e)
        if not cik:
            return None
        r = self.session.get(FACTS_URL.format(cik=cik), timeout=90)
        time.sleep(0.2)
        if r.status_code != 200:
            log.warning("edgar %s: %s", e.id, r.status_code)
            return None
        return {"cik": cik, "facts": r.json().get("facts", {}).get("us-gaap", {})}

    def parse(self, e: Entity, raw) -> list[Fact]:
        out = []
        url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={raw['cik']:010d}&type=10-Q"
        for tag, (metric, unit, scale) in TAGS.items():
            body = raw["facts"].get(tag)
            if not body:
                continue
            best: dict[date, dict] = {}
            for u, vals in body["units"].items():
                for v in vals:
                    if v.get("form") not in ("10-Q", "10-K") or not v.get("end"):
                        continue
                    end = date.fromisoformat(v["end"])
                    if end < SINCE or (v.get("start") and v["start"] != v["end"]):
                        continue                      # instants only
                    # for a given period end keep the latest filing (restated values)
                    if end not in best or v.get("filed", "") > best[end].get("filed", ""):
                        best[end] = v
            for end, v in best.items():
                out.append(Fact(entity_id=e.id, reference_date=end, metric=metric, value=round(float(v["val"]) * scale, 4),
                                unit=unit, currency="USD" if unit == "ccy_m" else "", basis="consolidated", source=self.name,
                                document=url, method="xbrl", confidence=0.95))
        out += self.accounts(e, raw)
        return out

    def accounts(self, e: Entity, raw) -> list[Fact]:
        """Annual balance sheet and income statement figures from the 10-K, turned into the same ratios
        the ESEF adapter computes, back to 2012."""
        from .esef import ratios
        by_end: dict[date, dict] = {}
        for tag, (code, kind) in ACCOUNTS.items():
            body = raw["facts"].get(tag)
            if not body:
                continue
            best: dict[date, dict] = {}
            for vals in body["units"].values():
                for v in vals:
                    if v.get("form") != "10-K" or not v.get("end"):
                        continue
                    end = date.fromisoformat(v["end"])
                    if end < ACCOUNTS_SINCE:
                        continue
                    if kind == "duration":
                        if not v.get("start") or not 350 <= (end - date.fromisoformat(v["start"])).days <= 380:
                            continue
                    elif v.get("start") and v["start"] != v["end"]:
                        continue
                    if end not in best or v.get("filed", "") > best[end].get("filed", ""):
                        best[end] = v
            for end, v in best.items():
                by_end.setdefault(end, {}).setdefault(code, float(v["val"]))
        url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={raw['cik']:010d}&type=10-K"
        out = []
        for d, m in ratios(by_end).items():
            for metric, val in m.items():
                amount = metric in ("total_assets", "deposits")
                out.append(Fact(entity_id=e.id, reference_date=d, metric=metric, value=val, unit="ccy_m" if amount else "pct",
                                currency="USD" if amount else "", basis="consolidated", source=self.name, document=url, method="xbrl",
                                confidence=0.9 if amount or metric in ("roe", "roa") else 0.8))
        return out

    def validate(self, records):
        return [r for r in records if (r.unit != "pct" or r.metric in ("roe", "roa", "nim", "efficiency_ratio", "cost_of_risk") or 0 < r.value < 80)]

    def load(self, records) -> int:
        return store.upsert("facts", records)
