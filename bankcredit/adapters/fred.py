"""Benchmark credit spreads from FRED (ICE BofA option-adjusted spread indices).

The keyless fredgraph CSV endpoint works from a laptop and not from a data centre: from a hosted
runner it hangs and then closes the connection, so every scheduled run logged this adapter as
failed and collected nothing. There are no FRED rows in the store at all, and there never were.

The supported route is the FRED API, which needs a free key. Set FRED_API_KEY (a repository
secret in the pipeline) and this collects; without one it skips and says so, rather than printing
a red line every morning for a source nobody has turned on.

Values are in percent; stored as basis points in the `series` table (key: series_id + date).
"""
from __future__ import annotations

import logging
import os

from .. import store
from .base import Adapter, register

log = logging.getLogger("bankcredit.fred")

API = "https://api.stlouisfed.org/fred/series/observations"
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
    # A public data API, one small CSV per series, and it is slow to first byte rather than busy.
    workers = 4

    def skip(self) -> str | None:
        if not os.environ.get("FRED_API_KEY"):
            return ("no FRED_API_KEY: the ICE BofA spread indices are not collected. The keyless "
                    "CSV endpoint does not answer a hosted runner; a free key at "
                    "fred.stlouisfed.org/docs/api/api_key.html turns this on.")
        return None

    def discover(self):
        # one request per series: smaller responses, and one slow series does not sink the rest
        yield from SERIES

    def fetch(self, item):
        r = self.session.get(API, timeout=(15, 30), params={
            "series_id": item, "api_key": os.environ["FRED_API_KEY"], "file_type": "json",
            "observation_start": "2015-01-01"})
        r.raise_for_status()
        return r.json()

    def parse(self, item, raw) -> list[dict]:
        rows = []
        for rec in (raw or {}).get("observations", []):
            v, d = rec.get("value"), rec.get("date")
            if v and v != "." and d:
                rows.append({"series_id": item, "date": d, "value": round(float(v) * 100, 1),
                             "unit": "bp", "label": SERIES[item][0], "source": "FRED"})
        return rows

    def validate(self, records):
        return [r for r in records if r["date"] and 0 <= r["value"] < 5000]

    def load(self, records) -> int:
        return store.upsert("series", records)
