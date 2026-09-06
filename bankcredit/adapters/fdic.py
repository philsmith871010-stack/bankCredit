"""FDIC BankFind Suite `financials` adapter.

Pulls quarterly Call Report ratios for the lead bank subsidiary of each US
holding company (entities with an `fdic_cert`). No API key is needed. Balance
sheet fields come back in USD thousands and are converted to millions here.

Docs: docs/data-sources-investigation.md section 3.1.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Iterable

from .. import store
from ..models import Entity, Fact
from .base import Adapter, register

log = logging.getLogger("bankcredit.fdic")

BASE = "https://api.fdic.gov/banks/financials"
FIELDS = (
    "CERT,REPDTE,ASSET,DEP,DEPINS,DEPUNINS,BRO,RBCT1CER,IDT1RWAJR,RBCRWAJ,RBC1AAJ,"
    "RWAJ,RBCT1J,NCLNLS,NCLNLSR,NTLNLS,NTLNLSR,LNATRES,ELNATR,ROA,ROE,NIMY,EEFFR,"
    "NETINC,CHBAL,SC,SCAF,SCHA,SCHF,EQTOT"
)
LIMIT = 40

# canonical metric -> (FDIC field, unit)
RATIOS = {
    "cet1_ratio": "RBCT1CER",
    "tier1_ratio": "IDT1RWAJR",
    "total_capital_ratio": "RBCRWAJ",
    "tier1_leverage": "RBC1AAJ",      # US Tier 1 leverage on average assets; not the Basel leverage ratio
    "npl_ratio": "NCLNLSR",
    "roa": "ROA",
    "roe": "ROE",
    "nim": "NIMY",
    "efficiency_ratio": "EEFFR",
}
AMOUNTS = {  # USD thousands in the API -> stored as USD millions
    "rwa": "RWAJ",
    "tier1_capital": "RBCT1J",
    "total_assets": "ASSET",
    "deposits": "DEP",
    "uninsured_deposits": "DEPUNINS",
}
# Sanity bounds for percent metrics. Default 0..60 catches garbage in capital,
# leverage and NPL ratios; efficiency ratios routinely exceed 60 and returns go
# negative in loss quarters, so those get their own realistic ranges.
RATIO_BOUNDS = {"efficiency_ratio": (0.0, 200.0), "roa": (-50.0, 50.0), "roe": (-100.0, 100.0), "nim": (-50.0, 50.0)}
RATIO_DEFAULT = (0.0, 60.0)


def request_url(cert: str) -> str:
    return (
        f"{BASE}?filters=CERT:{cert}&fields={FIELDS}"
        f"&sort_by=REPDTE&sort_order=DESC&limit={LIMIT}&format=json"
    )


@register
class FDICAdapter(Adapter):
    name = "fdic"
    cadence = "quarterly"
    regions = ("us_ch",)

    def __init__(self):
        super().__init__()
        self.cache_dir = store.DATA / "cache" / "fdic"

    # ---- discover ----
    def discover(self) -> Iterable[Entity]:
        for e in self.entities:
            if e.fdic_cert.strip():
                yield e

    # ---- fetch (with a per-day on-disk cache) ----
    def _cache_path(self, cert: str):
        return self.cache_dir / f"{cert}_{date.today():%Y%m%d}.json"

    def fetch(self, item: Entity) -> dict:
        cert = item.fdic_cert.strip()
        url = request_url(cert)
        cp = self._cache_path(cert)
        if cp.exists():
            log.info("fdic cache hit for cert %s (%s)", cert, cp.name)
            payload = json.loads(cp.read_text())
        else:
            resp = self.session.get(url, timeout=60)
            resp.raise_for_status()
            payload = resp.json()
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cp.write_text(json.dumps(payload))
        payload["_url"] = url
        return payload

    # ---- parse ----
    def parse(self, item: Entity, raw: dict) -> list[Fact]:
        url = raw.get("_url", request_url(item.fdic_cert))
        out: list[Fact] = []
        for row in raw.get("data", []):
            d = row.get("data", row)
            repdte = str(d.get("REPDTE") or "")
            try:
                ref = datetime.strptime(repdte, "%Y%m%d").date()
            except ValueError:
                log.warning("fdic %s: bad/missing REPDTE %r, skipped", item.id, repdte)
                continue
            common = dict(entity_id=item.id, reference_date=ref, basis="lead_bank",
                          source=self.name, document=url, method="api", confidence=1.0)
            for metric, code in RATIOS.items():
                v = d.get(code)
                if v is not None:
                    out.append(Fact(metric=metric, value=float(v), unit="pct", **common))
            for metric, code in AMOUNTS.items():
                v = d.get(code)
                if v is not None:
                    out.append(Fact(metric=metric, value=float(v) / 1000.0, unit="ccy_m",
                                    currency="USD", **common))
            fv, ac = d.get("SCHF"), d.get("SCHA")
            if fv is not None and ac is not None:
                out.append(Fact(metric="htm_unrealised_loss", value=(float(fv) - float(ac)) / 1000.0,
                                unit="ccy_m", currency="USD", **common))
        return out

    # ---- validate ----
    def validate(self, records: list[Fact]) -> list[Fact]:
        kept, dropped = [], []
        for r in records:
            if r.reference_date is None:
                dropped.append((r, "missing reference_date"))
            elif r.unit == "pct":
                lo, hi = RATIO_BOUNDS.get(r.metric, RATIO_DEFAULT)
                if lo <= r.value <= hi:
                    kept.append(r)
                else:
                    dropped.append((r, f"ratio {r.value} outside {lo:g}..{hi:g}"))
            else:
                kept.append(r)
        for r, why in dropped:
            log.warning("fdic dropped %s %s %s: %s", r.entity_id, r.reference_date, r.metric, why)
        if dropped:
            log.info("fdic validate: kept %d, dropped %d", len(kept), len(dropped))
        return kept

    # ---- load ----
    def load(self, records: list[Fact]) -> int:
        return store.upsert("facts", records)
