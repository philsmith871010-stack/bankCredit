"""Benchmark credit spreads from FRED (ICE BofA option-adjusted spread indices), no key.

The fredgraph CSV endpoint serves several series in one request. Values are in
percent; stored as basis points in the `series` table (key: series_id + date).
"""
from __future__ import annotations

import csv
import io
import logging

from .. import store
from .base import Adapter, register

log = logging.getLogger("bankcredit.fred")

URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
SERIES = {
    "BAMLC0A0CM": ("US IG corporate", "ICE BofA US Corporate OAS"),
    "BAMLH0A0HYM2": ("US high yield", "ICE BofA US High Yield OAS"),
    "BAMLHE00EHYIOAS": ("Euro high yield", "ICE BofA Euro High Yield OAS"),
    "BAMLEMEBCRPIEOAS": ("Emerging markets", "ICE BofA Emerging Markets Corporate Plus OAS"),
    "BAMLC0A3CA": ("US single-A", "ICE BofA Single-A US Corporate OAS"),
    "BAMLC0A4CBBB": ("US BBB", "ICE BofA BBB US Corporate OAS"),
}


@register
class FredAdapter(Adapter):
    name = "fred"
    cadence = "daily"

    def discover(self):
        # one request per series: smaller responses, and one slow series does not sink the rest
        yield from SERIES

    def fetch(self, item):
        last = None
        for attempt in range(3):
            try:
                r = self.session.get(URL, params={"id": item}, timeout=(20, 120),
                                     headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 Chrome/128 Safari/537.36"})
                r.raise_for_status()
                return r.text
            except Exception as exc:          # FRED is slow to first byte at times; retry with a pause
                last = exc
                import time
                time.sleep(5 * (attempt + 1))
        raise RuntimeError(f"{item}: {last}")

    def parse(self, item, raw) -> list[dict]:
        rows = []
        for rec in csv.DictReader(io.StringIO(raw)):
            d = rec.get("observation_date") or rec.get("DATE")
            for sid in SERIES:
                v = rec.get(sid)
                if v and v != ".":
                    rows.append({"series_id": sid, "date": d, "value": round(float(v) * 100, 1), "unit": "bp",
                                 "label": SERIES[sid][0], "source": "FRED"})
        return rows

    def validate(self, records):
        return [r for r in records if r["date"] and 0 <= r["value"] < 5000]

    def load(self, records) -> int:
        return store.upsert("series", records)
