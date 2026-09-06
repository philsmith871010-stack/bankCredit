"""ICE Clear Credit end-of-day settlement prices for cleared five-year single-name CDS.

Open JSON, no login, current day only (docs section 14.2): a daily snapshot builds
the history. Each cleared bank name settles every business day, so this is the
steadier source; DTCC trade prints fill names ICE does not clear. ICE's terms
restrict redistribution: the levels stay in the private cds table and drive the
overlay and the direction glyph; they are never shown.

Instrument names encode ticker.tier.currency.docclause.coupon.maturity, e.g.
BACR.SNRFOR.EUR.MM14.100.2031-06-20. Clean price in percent of par is turned
into a rough par spread with a flat risky annuity.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime

from .. import store
from .base import Adapter, register
from .dtcc import NAMES

log = logging.getLogger("bankcredit.ice")

URL = "https://www.ice.com/api/cds-settlement-prices/icc-single-names"
TIERS = {"SNRFOR": "senior", "SNRLAC": "senior_bailin", "SUBLT2": "sub"}


def rough_spread_bp(price: float, coupon_bp: float, years: float) -> float:
    years = max(0.5, years)
    annuity = (1 - 1.03 ** (-years)) / 0.03 * 0.97
    return coupon_bp - (price - 100) * 100 / annuity


@register
class ICEAdapter(Adapter):
    name = "ice"
    cadence = "daily"

    def discover(self):
        yield "today"

    def fetch(self, item):
        r = self.session.get(URL, timeout=90, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 Chrome/128 Safari/537.36"})
        r.raise_for_status()
        return r.json()

    def parse(self, item, raw) -> list[dict]:
        best: dict[tuple, tuple] = {}
        for r in raw:
            parts = (r.get("instrumentName") or "").split(".")
            if len(parts) < 6:
                continue
            tier = TIERS.get(parts[1])
            ref = (r.get("name") or "").upper()
            ent = next((e for frag, e in NAMES.items() if frag in ref), None)
            if not tier or not ent:
                continue
            try:
                coupon = float(parts[4]); price = float(r["eodPrice"])
                mat = date.fromisoformat(parts[5][:10]); day = date.fromisoformat(str(r["clearingDate"])[:10])
            except (ValueError, KeyError):
                continue
            years = (mat - day).days / 365.25
            if not (4.0 <= years <= 5.6) or coupon not in (100.0, 500.0, 25.0):
                continue
            sp = rough_spread_bp(price, coupon, years)
            if not (0 < sp < 3000):
                continue
            # prefer the 2014 definitions, EUR for European names, closest to five years
            rank = (0 if "14" in parts[3] else 1, 0 if parts[2] in ("EUR", "USD") else 1, abs(years - 5.0))
            key = (ent, day.isoformat(), tier)
            if key not in best or rank < best[key][0]:
                best[key] = (rank, sp)
        return [{"entity_id": e, "date": d, "tier": t, "level_bp": round(sp, 1), "trades": None, "source": "ice"}
                for (e, d, t), (_, sp) in best.items()]

    def validate(self, records):
        return records

    def load(self, records) -> int:
        return store.upsert("cds", records)
