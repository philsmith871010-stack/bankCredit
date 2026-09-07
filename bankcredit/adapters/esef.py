"""Annual accounts from ESEF filings on filings.xbrl.org (the open register of European Single
Electronic Format reports: every issuer with securities on an EU or UK regulated market, which
includes most banks and the larger building societies through their listed debt).

Each filing is fetched as xBRL-JSON and its undimensioned IFRS facts read: total assets,
customer deposits, equity, profit, net interest income, operating costs and the loan impairment
charge. From those the profitability ratios a treasurer looks at are computed on the same
definitions for every filer: return on equity and on assets (profit over the average of opening
and closing balances), net interest margin (net interest income over average assets), cost to
income (operating costs over net interest, fee and other operating income) and cost of risk
(impairment charge over customer loans). A filing carries its prior year too, so the history
starts a year before the first filing. Nothing here is scored until the ratio's inputs are
both present.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from .. import store
from ..models import Entity, Fact
from .base import Adapter, register

log = logging.getLogger("bankcredit.esef")
API = "https://filings.xbrl.org/api/filings"
HOST = "https://filings.xbrl.org"
CACHE = store.DATA / "cache" / "esef"
MAX_FILINGS = 8

# concept -> (code, kind); the first concept found wins for a code
CONCEPTS = [
    ("ifrs-full:Assets", "assets", "instant"),
    ("ifrs-full:DepositsFromCustomers", "deposits", "instant"),
    ("ifrs-full:LoansAndAdvancesToCustomers", "loans", "instant"),
    ("ifrs-full:EquityAttributableToOwnersOfParent", "equity", "instant"),
    ("ifrs-full:Equity", "equity", "instant"),
    ("ifrs-full:ProfitLoss", "profit", "duration"),
    ("ifrs-full:ProfitLossBeforeTax", "pretax", "duration"),
    ("ifrs-full:InterestRevenueExpense", "nii", "duration"),
    ("ifrs-full:InterestRevenueCalculatedUsingEffectiveInterestMethod", "interest_income", "duration"),
    ("ifrs-full:InterestIncome", "interest_income", "duration"),
    ("ifrs-full:InterestExpense", "interest_expense", "duration"),
    ("ifrs-full:FeeAndCommissionIncome", "fee_income", "duration"),
    ("ifrs-full:FeeAndCommissionExpense", "fee_expense", "duration"),
    ("ifrs-full:MiscellaneousOtherOperatingIncome", "other_income", "duration"),
    ("ifrs-full:OtherOperatingIncome", "other_income", "duration"),
    ("ifrs-full:OperatingExpense", "opex", "duration"),
    ("ifrs-full:AdministrativeExpense", "admin", "duration"),
    ("ifrs-full:DepreciationAndAmortisationExpense", "da", "duration"),
    ("ifrs-full:AmortisationIntangibleAssetsOtherThanGoodwill", "amort", "duration"),
    ("ifrs-full:DepreciationPropertyPlantAndEquipment", "depr", "duration"),
    ("ifrs-full:ImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLossLoansAndAdvances", "impairment", "duration"),
    ("ifrs-full:ImpairmentLossRecognisedInProfitOrLossLoansAndAdvances", "impairment", "duration"),
    ("ifrs-full:ImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLossFinancialAssets", "impairment", "duration"),
]
CODES = {c: (k, kind) for c, k, kind in CONCEPTS}
STOCK = {"assets": "total_assets", "deposits": "deposits"}


def _end(period: str) -> date:
    """xBRL-JSON writes an instant as the start of the following day and a duration as start/end."""
    p = period.split("/")[-1]
    return (datetime.fromisoformat(p[:19]) - timedelta(days=1)).date()


def _start(period: str) -> date | None:
    if "/" not in period:
        return None
    return datetime.fromisoformat(period.split("/")[0][:19]).date()


def read_filing(doc: dict) -> tuple[dict, str]:
    """{period end: {code: value}} for the undimensioned consolidated facts, and the currency."""
    out: dict[date, dict] = {}
    ccy = ""
    for f in doc.get("facts", {}).values():
        dims = f.get("dimensions", {})
        concept = dims.get("concept")
        if concept not in CODES or any(d not in ("concept", "entity", "period", "unit", "language") for d in dims):
            continue
        code, kind = CODES[concept]
        period = dims.get("period", "")
        if kind == "duration":
            s, e = _start(period), _end(period)
            if s is None or not 350 <= (e - s).days <= 380:       # full years only
                continue
        else:
            if "/" in period:
                continue
            e = _end(period)
        try:
            v = float(f["value"])
        except (TypeError, ValueError):
            continue
        unit = dims.get("unit", "")
        if unit.startswith("iso4217:"):
            ccy = ccy or unit.split(":")[1]
        out.setdefault(e, {}).setdefault(code, v)                  # first (undimensioned, most specific) wins
    return out, ccy


def ratios(by_end: dict) -> dict:
    """{period end: {metric: value}} with amounts in millions and ratios in percent."""
    ends = sorted(by_end)
    out: dict[date, dict] = {}
    for i, e in enumerate(ends):
        v = by_end[e]
        prev = by_end[ends[i - 1]] if i else {}
        m: dict[str, float] = {}
        for code, metric in STOCK.items():
            if code in v:
                m[metric] = v[code] / 1e6
        nii = v.get("nii")
        if nii is None and "interest_income" in v and "interest_expense" in v:
            nii = v["interest_income"] - abs(v["interest_expense"])
        opex = v.get("opex")
        if opex is None and "admin" in v:
            opex = abs(v["admin"]) + abs(v.get("da", 0) or (abs(v.get("amort", 0)) + abs(v.get("depr", 0))))
        # total income is exact as pre-tax profit plus costs and impairments (trading and other income
        # included); net interest plus fees is the fallback and understates a markets business
        income = None
        if "pretax" in v and opex is not None:
            income = v["pretax"] + abs(opex) + abs(v.get("impairment", 0) or 0)
        elif "revenue" in v:
            income = v["revenue"]
        elif nii is not None:
            income = nii + abs(v.get("fee_income", 0)) - abs(v.get("fee_expense", 0)) + (v.get("other_income", 0) or 0)

        def avg(code):
            if code not in v:
                return None
            return (v[code] + prev[code]) / 2 if code in prev else v[code]
        if "profit" in v and avg("equity"):
            m["roe"] = v["profit"] / avg("equity") * 100
        if "profit" in v and avg("assets"):
            m["roa"] = v["profit"] / avg("assets") * 100
        if nii is not None and avg("assets"):
            m["nim"] = nii / avg("assets") * 100
        if opex is not None and income and income > 0:
            ci = abs(opex) / income * 100
            if 20 <= ci <= 150:                       # outside that the income line is incomplete
                m["efficiency_ratio"] = ci
        if "impairment" in v and avg("loans"):
            m["cost_of_risk"] = abs(v["impairment"]) / avg("loans") * 100
        # only durations that belong to a balance sheet date (a filing's own year or its comparative)
        if m and ("assets" in v or "profit" in v):
            out[e] = {k: round(x, 4) for k, x in m.items() if x == x}
    return out


@register
class EsefAdapter(Adapter):
    name = "esef"
    cadence = "quarterly"

    def discover(self):
        return [e for e in self.entities if e.lei]

    def _filings(self, e: Entity) -> list[dict]:
        flt = json.dumps([{"name": "entity.identifier", "op": "eq", "val": e.lei}])
        r = self.session.get(f"{API}?filter={quote(flt)}&page%5Bsize%5D={MAX_FILINGS}&sort=-period_end", timeout=60)
        if r.status_code != 200:
            log.warning("esef: %s listing -> %s", e.id, r.status_code)
            return []
        seen, out = set(), []
        for d in r.json().get("data", []):
            a = d.get("attributes", {})
            if not a.get("json_url") or a.get("error_count", 0) > 5 or a["period_end"] in seen:
                continue
            seen.add(a["period_end"])
            out.append(a)
        return out

    def fetch(self, e: Entity):
        CACHE.mkdir(parents=True, exist_ok=True)
        docs = []
        for a in self._filings(e):
            path = CACHE / f"{e.lei}-{a['period_end']}.json"
            if not path.exists():
                r = self.session.get(HOST + a["json_url"], timeout=180)
                if r.status_code != 200 or not r.content.startswith(b"{"):
                    log.warning("esef: %s %s -> %s", e.id, a["period_end"], r.status_code)
                    continue
                path.write_bytes(r.content)
            docs.append((a, path))
        return docs

    def parse(self, e: Entity, raw) -> list[Fact]:
        merged: dict[date, dict] = {}
        ccy = ""
        sources: dict[date, str] = {}
        for a, path in sorted(raw, key=lambda x: x[0]["period_end"]):        # older first: a newer filing's restatement wins
            try:
                by_end, c = read_filing(json.loads(path.read_text()))
            except Exception as exc:
                log.warning("esef: %s %s unreadable (%s)", e.id, a["period_end"], exc)
                continue
            ccy = c or ccy
            for d, vals in by_end.items():
                merged.setdefault(d, {}).update(vals)
                sources[d] = HOST + a.get("viewer_url", a["json_url"])
        out = []
        for d, m in ratios(merged).items():
            for metric, v in m.items():
                out.append(Fact(entity_id=e.id, reference_date=d, metric=metric, value=v,
                                unit="ccy_m" if metric in ("total_assets", "deposits") else "pct",
                                currency=ccy if metric in ("total_assets", "deposits") else "",
                                basis="consolidated", source=self.name, document=sources.get(d, ""), method="xbrl",
                                confidence=0.85 if metric in ("total_assets", "deposits", "roe", "roa") else 0.75))
        log.info("esef: %s -> %d facts over %d year ends", e.id, len(out), len(set(f.reference_date for f in out)))
        return out

    def load(self, records) -> int:
        # a re-read replaces what this source held for the entity, so a dropped or restated ratio does not linger
        for ent in {f.entity_id for f in records}:
            store.drop("facts", entity_id=ent, source=self.name)
        return store.upsert("facts", records)
