"""Core records. Everything is long-format, time-stamped and sourced."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Optional


@dataclass
class Entity:
    id: str                      # stable slug, e.g. "nationwide-bs"
    name: str
    short_name: str
    country: str                 # ISO 3166-1 alpha-2
    type: str                    # bank | building_society | subsidiary | holding
    region: str                  # uk | eu | aus_can | asia | gulf | us_ch
    group: str = ""              # parent slug if part of a group
    lei: str = ""
    tickers: str = ""            # comma-separated Yahoo symbols, e.g. "BARC.L"
    fdic_cert: str = ""
    peer_group: str = ""
    active: bool = True


@dataclass
class Fact:
    entity_id: str
    reference_date: date
    metric: str                  # canonical metric code, see METRICS
    value: float
    unit: str = "pct"            # pct | ccy_m | ratio | count
    currency: str = ""
    basis: str = "consolidated"
    source: str = ""             # adapter name
    document: str = ""           # url or hash
    page: Optional[int] = None
    method: str = ""             # api | xbrl | pdf_llm | xlsx
    confidence: float = 1.0
    loaded_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Rating:
    entity_id: str
    agency: str                  # fitch | sp | moodys | dbrs | kbra | scope | jcr
    rating_type: str             # issuer | deposit | idr | counterparty | resolution_counterparty
    horizon: str                 # long | short
    value: str
    outlook: str = ""
    action: str = ""
    action_date: Optional[date] = None
    source_id: str = ""
    loaded_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Price:
    entity_id: str
    date: date
    close: float
    currency: str
    symbol: str
    source: str = "yahoo"


# Canonical metric codes (KM1-aligned). Values in percent unless stated.
METRICS = {
    "cet1_ratio": "CET1 capital ratio",
    "tier1_ratio": "Tier 1 capital ratio",
    "total_capital_ratio": "Total capital ratio",
    "leverage_ratio": "Leverage ratio",
    "tier1_leverage": "Tier 1 leverage ratio (US definition, average assets)",
    "lcr": "Liquidity coverage ratio",
    "nsfr": "Net stable funding ratio",
    "rwa": "Risk-weighted assets (currency millions)",
    "cet1_capital": "CET1 capital (currency millions)",
    "tier1_capital": "Tier 1 capital (currency millions)",
    "total_capital": "Total capital (currency millions)",
    "leverage_exposure": "Leverage exposure measure (currency millions)",
    "cet1_requirement": "Overall CET1 requirement incl. buffers",
    "overall_capital_requirement": "Overall capital requirement",
    "total_assets": "Total assets (currency millions)",
    "npl_ratio": "Non-performing or noncurrent loan ratio",
    "roa": "Return on assets",
    "roe": "Return on equity",
    "nim": "Net interest margin",
    "efficiency_ratio": "Cost-to-income or efficiency ratio",
    "deposits": "Total deposits (currency millions)",
    "uninsured_deposits": "Estimated uninsured deposits (currency millions)",
    "htm_unrealised_loss": "Held-to-maturity securities fair value minus amortised cost (currency millions; negative = unrealised loss)",
}


def to_dict(obj) -> dict:
    d = asdict(obj)
    for k, v in d.items():
        if isinstance(v, (date, datetime)):
            d[k] = v.isoformat()
    return d
