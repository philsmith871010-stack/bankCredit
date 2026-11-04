"""Annual accounts from ESEF filings on filings.xbrl.org (the open register of European Single
Electronic Format reports: every issuer with securities on an EU or UK regulated market, which
includes most banks and the larger building societies through their listed debt).

Each filing is fetched as xBRL-JSON and its undimensioned IFRS facts read: total assets,
customer deposits, equity, profit, net interest income, operating costs and the loan impairment
charge. From those the profitability ratios a treasurer looks at are computed on the same
definitions for every filer: return on equity (owners' profit over owners' equity, or the whole
profit over the whole equity) and on assets (the whole profit), both over the average of opening
and closing balances; net interest margin (net interest income over average assets); cost to
income (operating costs over total operating income before impairments); and cost of risk
(impairment charge over customer loans). A filing carries its prior year too, so the history
starts a year before the first filing. Nothing here is scored until the ratio's inputs are
both present.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import requests

from .. import store
from ..models import Entity, Fact
from .base import Adapter, register

log = logging.getLogger("bankcredit.esef")
API = "https://filings.xbrl.org/api/filings"
HOST = "https://filings.xbrl.org"
CACHE = store.DATA / "cache" / "esef"
MAX_FILINGS = 8
# On 1 November 2026 the register closed the connection on about two thirds of the filers in both
# of that day's runs, and every one of them was lost for the fortnight, because each request was
# tried once. A dropped connection, a timeout, a 429 or a 5xx is now tried again after a pause;
# anything else (a 404, a filing that is not JSON) is an answer, not a hiccup, and is not retried.
WAITS = (5, 20, 60)               # seconds before the second, third and fourth attempts
# A register that is down, not merely busy, would cost every request the whole wait. After this many
# requests have failed even with their retries, the rest of the run tries each request once.
GIVE_UP_AFTER = 3
TRANSIENT = (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError)


def get(session, url: str, timeout: int, waits=WAITS, sleep=None):
    """GET with a retry on the failures that pass: the response, or the last error raised."""
    sleep = sleep or time.sleep          # looked up per call, so a test can stand in for the pause
    for attempt in range(len(waits) + 1):
        try:
            r = session.get(url, timeout=timeout)
        except TRANSIENT as exc:
            if attempt == len(waits):
                raise
            log.info("esef: %s on attempt %d, retrying in %ss", type(exc).__name__, attempt + 1, waits[attempt])
        else:
            if (r.status_code != 429 and r.status_code < 500) or attempt == len(waits):
                return r
            log.info("esef: HTTP %s on attempt %d, retrying in %ss", r.status_code, attempt + 1, waits[attempt])
        sleep(waits[attempt])

# concept -> (code, kind). Where several concepts give one code they are listed in order of preference,
# and the first of them a filing tags wins whatever order its facts come in.
CONCEPTS = [
    ("ifrs-full:Assets", "assets", "instant"),
    ("ifrs-full:DepositsFromCustomers", "deposits", "instant"),
    ("ifrs-full:LoansAndAdvancesToCustomers", "loans", "instant"),
    # owners' profit goes over owners' equity and the whole profit over the whole equity, never one over the other
    ("ifrs-full:EquityAttributableToOwnersOfParent", "equity_parent", "instant"),
    ("ifrs-full:Equity", "equity", "instant"),
    ("ifrs-full:ProfitLoss", "profit", "duration"),
    ("ifrs-full:ProfitLossAttributableToOwnersOfParent", "profit_parent", "duration"),
    ("ifrs-full:ProfitLossBeforeTax", "pretax", "duration"),
    ("ifrs-full:InterestRevenueExpense", "nii", "duration"),
    # total interest income, the only kind that nets against total interest expense; the effective-interest
    # subtotal leaves out interest on loans at fair value (Nykredit's mortgages), so it only marks that the
    # filer split its interest income and a total cannot be trusted to be one
    ("ifrs-full:InterestIncome", "interest_income", "duration"),
    ("ifrs-full:RevenueFromInterest", "interest_income", "duration"),
    ("ifrs-full:InterestRevenueCalculatedUsingEffectiveInterestMethod", "interest_eir", "duration"),
    ("ifrs-full:InterestExpense", "interest_expense", "duration"),
    ("ifrs-full:OperatingExpense", "opex", "duration"),
    ("ifrs-full:AdministrativeExpense", "admin", "duration"),
    ("ifrs-full:GeneralAndAdministrativeExpense", "admin", "duration"),
    ("ifrs-full:EmployeeBenefitsExpense", "staff", "duration"),
    ("ifrs-full:DepreciationAndAmortisationExpense", "da", "duration"),
    ("ifrs-full:AmortisationIntangibleAssetsOtherThanGoodwill", "amort", "duration"),
    ("ifrs-full:DepreciationPropertyPlantAndEquipment", "depr", "duration"),
    # credit impairment, loans first; a charge is positive and a net release negative
    ("ifrs-full:ImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLossLoansAndAdvances", "impairment", "duration"),
    ("ifrs-full:ImpairmentLossRecognisedInProfitOrLossLoansAndAdvances", "impairment", "duration"),
    ("ifrs-full:ImpairmentLossImpairmentGainAndReversalOfImpairmentLossDeterminedInAccordanceWithIFRS9", "impairment", "duration"),
    ("ifrs-full:ImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLossFinancialAssets", "impairment", "duration"),
    ("ifrs-full:ImpairmentLossOnFinancialAssets", "impairment", "duration"),
    # every impairment on the income statement: enough to rebuild income from pre-tax profit, too wide for cost of risk
    ("ifrs-full:ImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss", "impairment_any", "duration"),
    # total operating income as the bank reports it; plain Revenue is last because a bancassurer puts
    # gross premiums or gross interest there (Lloyds: 37bn one year, 6bn the next)
    ("ifrs-full:RevenueAndOperatingIncome", "income_total", "duration"),
    ("ifrs-full:Revenue", "revenue", "duration"),
]
# Filers' own concepts for lines IFRS has no element for, by local name: net interest income
# (Danske, Nykredit), total income, and profit before impairments (income less costs).
EXTENSIONS = {
    "NetInterestIncome": "nii", "InterestIncomeNet": "nii",
    "TotalIncome": "income_total", "NetOperatingIncome": "income_total", "TotalOperatingIncome": "income_total",
    "NetBankingIncome": "income_total", "RevenuesFromContinuingActivities": "income_total",
    "TotalNetInterestIncomeAndNetNonInterestIncome": "income_total",
    "OperatingIncomeBeforeExpectedCreditLossAndImpairmentCharges": "income_total",
    "ProfitBeforeLoanImpairmentCharges": "pre_impairment", "ProfitBeforeImpairmentLossesReleases": "pre_impairment",
    "ProfitLossFromOperatingActivitiesBeforeImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss": "pre_impairment",
    "GrossOperatingIncome": "pre_impairment", "GrossOperatingIncomeFromContinuingActivities": "pre_impairment",
    "OperatingProfitBeforeImpairmentsAndProvisions": "pre_impairment",
}
CODES = {c: (k, kind) for c, k, kind in CONCEPTS}
RANK = {c: i for i, (c, _, _) in enumerate(CONCEPTS)}
STOCK = {"assets": "total_assets", "deposits": "deposits"}
# costs a filer writes with the taxonomy's sign are positive; one that writes them negative writes its
# impairment charge negative too, so the sign of its costs says which way its impairment line points
COSTS = ("opex", "admin", "staff", "interest_expense")


def _concept(concept: str):
    """(code, kind, rank) for a concept read here, or None."""
    if concept in CODES:
        return CODES[concept] + (RANK[concept],)
    prefix, _, local = concept.partition(":")
    if prefix != "ifrs-full" and local in EXTENSIONS:
        return EXTENSIONS[local], "duration", len(CONCEPTS)
    return None


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
    durations: dict[date, dict] = {}
    instants: dict[date, dict] = {}
    year_ends: set[date] = set()
    ccy = ""
    for f in doc.get("facts", {}).values():
        dims = f.get("dimensions", {})
        hit = _concept(dims.get("concept", ""))
        if hit is None or any(d not in ("concept", "entity", "period", "unit", "language") for d in dims):
            continue
        code, kind, rank = hit
        period = dims.get("period", "")
        if kind == "duration":
            s, e = _start(period), _end(period)
            if s is None or not 350 <= (e - s).days <= 380:       # full years only
                continue
            year_ends.update((e, s - timedelta(days=1)))
            into = durations
        else:
            if "/" in period:
                continue
            e = _end(period)
            into = instants
        try:
            v = float(f["value"])
        except (TypeError, ValueError):
            continue
        unit = dims.get("unit", "")
        if unit.startswith("iso4217:"):
            ccy = ccy or unit.split(":")[1]
        held = into.setdefault(e, {}).get(code)
        if held is None or rank < held[0]:                       # the preferred concept, wherever it sits in the file
            into[e][code] = (rank, v)
    out: dict[date, dict] = {}
    for e, vals in durations.items():
        out.setdefault(e, {}).update({k: v for k, (_, v) in vals.items()})
    # A balance sheet date is a year end of the filing's own full years, or the opening of one. An
    # IFRS 17 restatement's 1 January balance is neither, and would otherwise become a year of its own
    # and the opening balance the next year averaged with.
    for e, vals in instants.items():
        if e in year_ends or not year_ends:
            out.setdefault(e, {}).update({k: v for k, (_, v) in vals.items()})
    return out, ccy


def ratios(by_end: dict) -> dict:
    """{period end: {metric: value}} with amounts in millions and ratios in percent."""
    ends = sorted(by_end)
    out: dict[date, dict] = {}
    for i, e in enumerate(ends):
        v = by_end[e]
        # the opening balance is the prior year end's, not whatever date came before
        prev = by_end[ends[i - 1]] if i and 350 <= (e - ends[i - 1]).days <= 380 else {}
        m: dict[str, float] = {}
        for code, metric in STOCK.items():
            if code in v:
                m[metric] = v[code] / 1e6
        # net interest income as reported, or total interest income less total interest expense; an
        # effective-interest subtotal beside the total means the total may be only the rest of it
        nii, reported = v.get("nii"), "nii" in v
        if nii is None and "interest_income" in v and "interest_expense" in v and "interest_eir" not in v:
            nii = v["interest_income"] - abs(v["interest_expense"])
        opex = v.get("opex")
        if opex is None and "admin" in v:
            # many banks tag only other administrative expenses with the admin concept, staff costs apart;
            # an admin line smaller than staff costs cannot contain them
            staff = abs(v.get("staff", 0) or 0)
            opex = abs(v["admin"]) + (staff if staff > abs(v["admin"]) else 0) \
                + abs(v.get("da", 0) or (abs(v.get("amort", 0)) + abs(v.get("depr", 0))))
        if opex is None and "income_total" in v and "pre_impairment" in v:
            opex = v["income_total"] - v["pre_impairment"]       # Societe Generale: net banking income less gross operating income
        inverted = sum(v[c] for c in COSTS if c in v) < 0
        charge = v.get("impairment", v.get("impairment_any"))
        if charge is not None and inverted:
            charge = -charge
        # Total income is exact as pre-tax profit plus costs plus the impairment charge, a net release
        # taking income down. Without an impairment line that sum is income net of provisions and
        # overstates cost to income, so the bank's own total income is used, then profit before
        # impairments plus costs; with none of them there is no ratio.
        income = None
        if "pretax" in v and opex is not None and charge is not None:
            income = v["pretax"] + abs(opex) + charge
        elif "income_total" in v:
            income = v["income_total"]
        elif "pre_impairment" in v and opex is not None:
            income = v["pre_impairment"] + abs(opex)
        elif "revenue" in v:
            income = v["revenue"]

        def avg(code):
            if code not in v:
                return None
            return (v[code] + prev[code]) / 2 if code in prev else v[code]
        if "profit_parent" in v and avg("equity_parent"):
            m["roe"] = v["profit_parent"] / avg("equity_parent") * 100
        elif "profit" in v and avg("equity"):
            m["roe"] = v["profit"] / avg("equity") * 100
        if "profit" in v and avg("assets"):
            m["roa"] = v["profit"] / avg("assets") * 100
        if nii is not None and avg("assets") and (nii >= 0 or reported):
            m["nim"] = nii / avg("assets") * 100
        if opex is not None and income and income > 0:
            ci = abs(opex) / income * 100
            if 20 <= ci <= 150:                       # outside that the income line is incomplete
                m["efficiency_ratio"] = ci
        if "impairment" in v and avg("loans"):
            m["cost_of_risk"] = (-v["impairment"] if inverted else v["impairment"]) / avg("loans") * 100
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

    def _get(self, url: str, timeout: int):
        """One request, retried while the register still looks merely busy."""
        lost = getattr(self, "_lost", 0)
        try:
            r = get(self.session, url, timeout, waits=WAITS if lost < GIVE_UP_AFTER else ())
        except TRANSIENT:
            self._lost = lost + 1
            raise
        if r.status_code == 429 or r.status_code >= 500:
            self._lost = lost + 1
        return r

    def _filings(self, e: Entity) -> list[dict]:
        flt = json.dumps([{"name": "entity.identifier", "op": "eq", "val": e.lei}])
        r = self._get(f"{API}?filter={quote(flt)}&page%5Bsize%5D={MAX_FILINGS}&sort=-period_end", timeout=60)
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
                r = self._get(HOST + a["json_url"], timeout=180)
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
