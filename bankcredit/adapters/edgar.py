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
        return out

    def validate(self, records):
        return [r for r in records if (r.unit != "pct" or 0 < r.value < 80)]

    def load(self, records) -> int:
        return store.upsert("facts", records)
