"""EBA Pillar 3 Data Hub adapter: KM1 key metrics (template K_61.00) for EU/EEA banks.

Source: the public EDAP report (https://edap-public.eba.europa.eu/Report/index/MTE1), read
through its Power BI model (see _powerbi.py). One work item per accepted reference date.
Facts are pulled per country to stay under the 30,000-row window cap and merged.

Environment hooks (mainly for tests):
  BANKCREDIT_EBA_COUNTRIES   comma-separated hub country names to restrict the pull,
                             e.g. "Netherlands,Ireland". Default: every country in the model.
"""
from __future__ import annotations

import collections
import datetime as dt
import os
import re
import unicodedata
from typing import Iterable

from .. import store
from ..models import Fact
from . import Adapter, register
from ._powerbi import P3DH_URL, WINDOW, Hub, col, datetime_lit, eq, measure, src, text
from .base import log

TEMPLATE = "K_61.00"          # KM1 key metrics
CURRENT_COLUMN = "0010"       # column a: current period T

# KM1 row code -> (metric, kind). kind: pct (capital-type ratio), liq (LCR/NSFR), amount (EUR)
ROW_MAP = {
    "0010": ("cet1_capital", "amount"),
    "0020": ("tier1_capital", "amount"),
    "0030": ("total_capital", "amount"),
    "0040": ("rwa", "amount"),
    "0050": ("cet1_ratio", "pct"),
    "0060": ("tier1_ratio", "pct"),
    "0070": ("total_capital_ratio", "pct"),
    "0190": ("overall_capital_requirement", "pct"),
    "0210": ("leverage_exposure", "amount"),
    "0220": ("leverage_ratio", "pct"),
    "0320": ("lcr", "liq"),
    "0350": ("nsfr", "liq"),
}
# Substring that must appear in the dm_Row label for each mapped code (case-insensitive,
# after collapsing whitespace). Used to verify the mapping against the table version in use.
ROW_EXPECT = {
    "0010": "common equity tier 1 (cet1) capital",
    "0020": "tier 1 capital",
    "0030": "total capital",
    "0040": "total risk-weighted exposure amount",
    "0050": "common equity tier 1 ratio",
    "0060": "tier 1 ratio",
    "0070": "total capital ratio",
    "0190": "overall capital requirements",
    "0210": "leverage ratio total exposure measure",
    "0220": "leverage ratio",
    "0320": "liquidity coverage ratio",
    "0350": "nsfr",
}
# Validation bounds in the stored unit (percent for ratios, EUR millions for amounts).
BOUNDS = {"pct": (0.0, 80.0), "liq": (0.0, 10000.0), "amount": (0.0, float("inf"))}

# ISO alpha-2 -> country name as spelt in dm_Entity.Country
COUNTRY = {
    "AT": "Austria", "BE": "Belgium", "BG": "Bulgaria", "HR": "Croatia", "CY": "Cyprus", "CZ": "Czech",
    "DK": "Denmark", "EE": "Estonia", "FI": "Finland", "FR": "France", "DE": "Germany", "GR": "Greece",
    "HU": "Hungary", "IS": "Iceland", "IE": "Ireland", "IT": "Italy", "LV": "Latvia", "LI": "Liechtenstein",
    "LT": "Lithuania", "LU": "Luxembourg", "MT": "Malta", "NL": "Netherlands", "NO": "Norway", "PL": "Poland",
    "PT": "Portugal", "RO": "Romania", "SK": "Slovakia", "SI": "Slovenia", "ES": "Spain", "SE": "Sweden",
}

# Hub entity name -> our entity id, for names that differ from entities.csv. Compared after
# normalisation (case, accents, punctuation). Explicit aliases skip the country check.
ALIASES = {
    "Coöperatieve Rabobank U.A.": "rabobank",
    "Coöperatieve Centrale Raiffeisen-Boerenleenbank B.A": "rabobank",
    "COMMERZBANK Aktiengesellschaft": "commerzbank",
    "Deutsche Bank AG": "deutsche-bank",
    "DEUTSCHE BANK AKTIENGESELLSCHAFT": "deutsche-bank",
    "Société générale S.A.": "societe-generale",
    "Groupe BPCE": "bpce",
    "Confédération Nationale du Crédit Mutuel": "credit-mutuel",
    "CONFEDERATION NATIONALE CREDIT MUTUEL": "credit-mutuel",
    "Landesbank Hessen-Thüringen Girozentrale": "helaba",
    "Landesbank Baden-Württemberg": "lbbw",
    "Bayerische Landesbank": "bayernlb",
    "DZ BANK AG Deutsche Zentral-Genossenschaftsbank, Frankfurt am Main": "dz-bank",
    "Groupe Crédit Agricole": "credit-agricole",          # top-level group, not Crédit Agricole S.A.
    "Skandinaviska Enskilda Banken - group": "seb",
    "Skandinaviska Enskilda Banken - gruppen": "seb",
    "Svenska Handelsbanken - group": "svenska-handelsbanken",
    "Svenska Handelsbanken - gruppen": "svenska-handelsbanken",
    "Swedbank - group": "swedbank",
    "Swedbank - Grupp": "swedbank",
    "Nordea Bank - group": "nordea",
    "Nordea Bank Abp": "nordea",
    "DNB BANK ASA": "dnb",
    "OP Osuuskunta": "op-financial-group",
    "Nykredit Realkredit A/S": "nykredit",
    "KBC Groep": "kbc",
    "KBC Groupe": "kbc",
    "Belfius Bank": "belfius",
    "UniCredit S.p.A.": "unicredit",
    "UNICREDIT, SOCIETA' PER AZIONI": "unicredit",
    "Bank of Ireland Group plc": "bank-of-ireland",
    "AIB Group plc": "aib",
}

# Consolidation preference when several hub rows map to the same entity: lower is better.
TYPE_RANK = {"Large highest EEA": 0, "Other highest EEA": 1, None: 2, "": 2, "Large subsidiaries": 3}

FACT_SOURCES = [src(a, e) for a, e in [("e", "dm_Entity"), ("t", "dm_Template"), ("i", "dm_ReportInstance"),
                                       ("tb", "dm_Table"), ("r", "dm_Row"), ("c", "dm_Column"),
                                       ("f", "fact_Value"), ("v", "Measure P3")]]
FACT_SELECT = [col("e", "ENT_NAM"), col("e", "EntityCode"), col("e", "Country"), col("e", "InstitutionType"),
               col("tb", "TableCode"), col("r", "HeaderCode"), col("c", "HeaderCode"), measure("v", "FactValue")]
FACT_FIELDS = ["name", "lei", "country", "type", "table", "row", "column", "value"]


def norm(name: str | None) -> str:
    """Case-, accent- and punctuation-insensitive form of an entity name."""
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).casefold()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())


def parse_value(v) -> float | None:
    """Fact values arrive as strings with a type suffix, e.g. '0.202276D' or '5310639136.17D'."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().rstrip("DFLdfl")
    try:
        return float(s)
    except ValueError:
        return None


def scale(value: float, kind: str) -> float:
    """Bring a raw hub value into the stored unit.

    Ratios are meant to be decimals (0.186 = 18.6 percent) but a minority of filers report
    them already in percent, so: capital-type ratios <= 1 are decimals; LCR/NSFR below 20
    are decimals (an LCR of 1.5 is 150 percent, 175 is already percent). Amounts are EUR
    full units -> millions.
    """
    if kind == "amount":
        return value / 1e6
    if kind == "liq":
        return value * 100 if abs(value) < 20 else value
    return value * 100 if abs(value) <= 1.0 else value


@register
class EBAHubAdapter(Adapter):
    name = "eba"
    cadence = "quarterly"
    regions = ("eu",)
    document = P3DH_URL
    max_dates = 8

    def __init__(self):
        super().__init__()
        self.hub = Hub(self.session)
        env = os.environ.get("BANKCREDIT_EBA_COUNTRIES", "").strip()
        self.countries: list[str] | None = [c.strip() for c in env.split(",") if c.strip()] or None
        self._labels_checked = False
        self.row_labels: dict[str, str] = {}
        self.stats: dict[dt.date, dict] = {}         # per reference date match statistics
        self.unmatched: collections.Counter = collections.Counter()   # hub name -> dates seen
        self.matched: dict[str, str] = {}             # hub name -> entity id
        # matching indexes
        self._by_lei = {e.lei: e.id for e in self.entities if e.lei}
        self._by_name: dict[str, list] = collections.defaultdict(list)
        for e in self.entities:
            self._by_name[norm(e.name)].append(e)
        ids = {e.id for e in self.entities}
        self._alias = {norm(k): v for k, v in ALIASES.items() if v in ids}

    # ---- discover ---------------------------------------------------------------
    def discover(self) -> Iterable[dt.date]:
        """Accepted, current reference dates in the model, most recent first (max `max_dates`)."""
        rows = self.hub.query([src("i", "dm_ReportInstance")],
                              [col("i", "ReferenceDate"), col("i", "IsCurrent"), col("i", "IsAccepted")])
        dates = set()
        for ref, current, accepted in rows:
            if ref is None or not current or not accepted:
                continue
            dates.add(dt.datetime.fromtimestamp(ref / 1000, tz=dt.timezone.utc).date())
        out = sorted(dates, reverse=True)[: self.max_dates]
        log.info("eba: %d accepted reference dates: %s", len(out), [d.isoformat() for d in out])
        return out

    # ---- fetch ------------------------------------------------------------------
    def hub_countries(self) -> list[str]:
        if self.countries:
            return self.countries
        rows = self.hub.query([src("e", "dm_Entity")], [col("e", "Country")])
        return sorted({r[0] for r in rows if r and r[0]})

    def _facts(self, reference_date: dt.date, country: str, row_code: str | None = None) -> list[list]:
        filters = [eq("t", "TemplateCode", text(TEMPLATE)),
                   eq("i", "ReferenceDate", datetime_lit(reference_date.isoformat())),
                   eq("i", "IsCurrent", "1L"), eq("i", "IsAccepted", "true"),
                   eq("c", "HeaderCode", text(CURRENT_COLUMN)),
                   eq("e", "Country", text(country))]
        if row_code:
            filters.append(eq("r", "HeaderCode", text(row_code)))
        return self.hub.query(FACT_SOURCES, FACT_SELECT, filters)

    def fetch(self, item: dt.date) -> list[dict]:
        """KM1 current-period facts for one reference date, paged per country (and per row if needed)."""
        rows: list[list] = []
        for country in self.hub_countries():
            part = self._facts(item, country)
            if len(part) >= WINDOW:            # window cap hit: page by row code instead
                log.warning("eba: %s %s hit the %d-row window; paging by row code", item, country, WINDOW)
                part = []
                for code in self.row_codes():
                    sub = self._facts(item, country, code)
                    if len(sub) >= WINDOW:
                        raise RuntimeError(f"eba: {item} {country} row {code} exceeds the window cap")
                    part.extend(sub)
            rows.extend(part)
        log.info("eba: %s: %d KM1 facts from %d countries (%d queries so far)",
                 item, len(rows), len(self.hub_countries()), self.hub.calls)
        return [dict(zip(FACT_FIELDS, r)) for r in rows]

    # ---- parse ------------------------------------------------------------------
    def load_row_labels(self) -> dict[str, str]:
        """dm_Row labels for the KM1 table in use; printed once and checked against ROW_EXPECT."""
        if self._labels_checked:
            return self.row_labels
        rows = self.hub.query([src("t", "dm_Template"), src("tb", "dm_Table"), src("r", "dm_Row")],
                              [col("t", "TemplateCode"), col("tb", "TableCode"), col("r", "HeaderCode"),
                               col("r", "HeaderLabel")],
                              [eq("t", "TemplateCode", text(TEMPLATE))])
        self.row_labels = {r[2]: " ".join(str(r[3] or "").split()) for r in rows if r[2]}
        print(f"eba: KM1 ({TEMPLATE}) rows in the hub model:")
        for code in sorted(self.row_labels):
            mapped = ROW_MAP.get(code, ("", ""))[0]
            print(f"  {code}  {self.row_labels[code]:95s} {'-> ' + mapped if mapped else ''}")
        for code, expect in ROW_EXPECT.items():
            label = self.row_labels.get(code, "").casefold()
            if expect not in label:
                log.warning("eba: KM1 row %s label %r does not match expected %r; check ROW_MAP",
                            code, self.row_labels.get(code), expect)
        self._labels_checked = True
        return self.row_labels

    def row_codes(self) -> list[str]:
        return sorted(self.load_row_labels())

    def match(self, name: str, lei: str | None, country: str | None) -> str | None:
        """Map a hub entity to our entity id: LEI first, then explicit alias, then name + country."""
        if lei and lei in self._by_lei:
            return self._by_lei[lei]
        n = norm(name)
        if n in self._alias:
            return self._alias[n]
        for e in self._by_name.get(n, []):
            if not country or COUNTRY.get(e.country) == country:
                return e.id
        return None

    def parse(self, item: dt.date, raw: list[dict]) -> list[Fact]:
        self.load_row_labels()
        # group facts by hub entity row (name, lei, type, country)
        by_hub: dict[tuple, dict[str, float]] = collections.defaultdict(dict)
        for r in raw:
            if r["table"] != TEMPLATE or r["column"] != CURRENT_COLUMN or r["row"] not in ROW_MAP:
                continue
            v = parse_value(r["value"])
            if v is None:
                continue
            by_hub[(r["name"], r["lei"], r["type"], r["country"])][r["row"]] = v
        # match, then keep the highest-consolidation hub row per entity
        best: dict[str, tuple] = {}
        unmatched = 0
        for key in by_hub:
            name, lei, itype, country = key
            eid = self.match(name, lei, country)
            if eid is None:
                unmatched += 1
                self.unmatched[name] += 1
                continue
            self.matched[name] = eid
            rank = (TYPE_RANK.get(itype, 2), name)
            if eid not in best or rank < best[eid][0]:
                best[eid] = (rank, key)
        facts: list[Fact] = []
        for eid, (_, key) in best.items():
            for code, value in by_hub[key].items():
                metric, kind = ROW_MAP[code]
                facts.append(Fact(
                    entity_id=eid, reference_date=item, metric=metric, value=scale(value, kind),
                    unit="ccy_m" if kind == "amount" else "pct", currency="EUR" if kind == "amount" else "",
                    basis="consolidated", source=self.name, document=self.document, method="xbrl",
                    confidence=1.0))
        self.stats[item] = {"hub_entities": len(by_hub), "matched_hub_entities": len(by_hub) - unmatched,
                            "unmatched_hub_entities": unmatched, "our_entities": len(best),
                            "our_entities_total": len(self.entities), "facts": len(facts)}
        log.info("eba: %s: %s", item, self.stats[item])
        return facts

    # ---- validate / load --------------------------------------------------------
    def validate(self, records: list[Fact]) -> list[Fact]:
        kinds = {metric: kind for metric, kind in ROW_MAP.values()}
        out = []
        for f in records:
            lo, hi = BOUNDS[kinds[f.metric]]
            if f.value is None or f.value != f.value or not (lo < f.value <= hi):
                log.warning("eba: dropping %s %s %s = %r (outside %s..%s)",
                            f.entity_id, f.reference_date, f.metric, f.value, lo, hi)
                continue
            out.append(f)
        return out

    def load(self, records: list[Fact]) -> int:
        return store.upsert("facts", records)
