"""Key figures from results announcements on the FCA National Storage Mechanism.

Some issuers never publish a standalone Pillar 3 PDF at the level we assess: their capital,
asset quality and profitability ratios only ever appear in the key-figures table of a quarterly
results release. Those releases are filed on the NSM, where they are free, dated and addressable
by LEI, so this adapter reads the table straight out of the announcement.

For each configured entity the NSM is searched by LEI, the English releases whose headline
matches are fetched, and the first numeric column of the key-figures table is taken as the
period the headline names. Only labels in ROWS are read; everything else in the release is
ignored. The publication date on the NSM record is the publication date of the figures, which
is what the site shows.
"""
from __future__ import annotations

import html
import logging
import re
from datetime import date, datetime, timedelta

from ..models import Fact
from .. import store
from .base import Adapter, register

log = logging.getLogger("bankcredit.nsm_release")
API = "https://api.data.fca.org.uk/search?index=nsm-search"
ARTEFACTS = "https://data.fca.org.uk/artefacts/"
LOOKBACK_DAYS = 900

# entity id -> headline regex identifying that entity's own results release (not the parent's)
ISSUERS = {
    # OP stopped filing to the NSM after the October 2025 release (the group renamed to OP Pohjola and
    # its UK-listed programme lapsed); the figures held will go stale in mid-2027 unless a second
    # backend is added for the Finnish OAM.
    "op-corporate-bank": r"OP Corporate Bank plc.{0,3}s (?:Interim Report|Half-year Financial Report|Financial Statements Bulletin)",
}

# label regex -> canonical metric. Order matters: the first match wins.
ROWS: list[tuple[str, str]] = [
    (r"^CET1 (?:capital )?ratio", "cet1_ratio"),
    (r"^Tier 1 (?:capital )?ratio", "tier1_ratio"),
    (r"^(?:Total capital ratio|Capital adequacy ratio|Own funds ratio)", "total_capital_ratio"),
    (r"^Leverage ratio", "leverage_ratio"),
    (r"^(?:LCR|Liquidity coverage ratio)", "lcr"),
    (r"^(?:NSFR|Net stable funding ratio)", "nsfr"),
    (r"^Cost/income ratio", "efficiency_ratio"),
    (r"^Return on equity", "roe"),
    (r"^Ratio of non-performing exposures", "npl_ratio"),
    (r"^Ratio of impairment loss on receivables", "cost_of_risk"),
]

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], 1)}
_MONTH_END = {1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30, 7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}


def period_end(headline: str) -> date | None:
    """The end of the reporting period a results headline names ("1 January-30 June 2025")."""
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\s*$", headline.strip())
    if not m:
        m = re.search(r"[-–—]\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", headline)
    if not m:
        return None
    day, month, year = int(m.group(1)), MONTHS.get(m.group(2).lower()), int(m.group(3))
    if not month:
        return None
    try:
        return date(year, month, min(day, _MONTH_END[month] + (1 if month == 2 and year % 4 == 0 else 0)))
    except ValueError:
        return None


def _rows(body: str) -> list[list[str]]:
    text = html.unescape(body)
    out = []
    for m in re.finditer(r"<tr[^>]*>(.*?)</tr>", text, re.S | re.I):
        cells = [re.sub(r"<[^>]+>", "", c).replace("\xa0", " ").strip()
                 for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", m.group(1), re.S | re.I)]
        if cells:
            out.append(cells)
    return out


def _number(cell: str) -> float | None:
    c = cell.replace(",", "").replace("−", "-").replace("*", "").strip()
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", c):
        return None
    return float(c)


def key_figures(body: str) -> dict[str, float]:
    """{metric: value} from the first numeric column of the key-figures table."""
    out: dict[str, float] = {}
    for cells in _rows(body):
        label = cells[0]
        metric = next((m for pat, m in ROWS if re.match(pat, label, re.I)), None)
        if metric is None or metric in out:
            continue
        value = next((v for v in (_number(c) for c in cells[1:]) if v is not None), None)
        if value is not None:
            out[metric] = value
    return out


@register
class NsmReleaseAdapter(Adapter):
    name = "nsm_release"
    cadence = "quarterly"

    def discover(self):
        for ent in self.entities:
            if ent.id in ISSUERS and ent.lei:
                yield ent

    def _hits(self, lei: str) -> list[dict]:
        since = (date.today() - timedelta(days=LOOKBACK_DAYS)).isoformat()
        body = {"from": 0, "size": 100, "sortorder": "desc",
                "criteriaObj": {"criteria": [{"name": "lei", "value": lei}],
                                "dateCriteria": [{"name": "publication_date",
                                                  "value": {"from": f"{since}T00:00:00Z",
                                                            "to": "2035-01-01T23:59:59Z"}}]}}
        r = self.session.post(API, json=body, timeout=90,
                              headers={"Origin": "https://data.fca.org.uk",
                                       "Referer": "https://data.fca.org.uk/"})
        r.raise_for_status()
        return [h["_source"] for h in r.json()["hits"]["hits"]]

    def fetch(self, ent):
        pattern = ISSUERS[ent.id]
        out = []
        for s in self._hits(ent.lei):
            link = s.get("download_link") or ""
            headline = (s.get("headline") or "").strip()
            if not link.endswith("-en.html") or not re.search(pattern, headline, re.I):
                continue
            end = period_end(headline)
            if end is None:
                log.warning("%s: no period in %r", ent.id, headline)
                continue
            r = self.session.get(ARTEFACTS + link, timeout=90)
            if r.status_code != 200:
                log.warning("%s: %s -> %s", ent.id, link, r.status_code)
                continue
            out.append((ARTEFACTS + link, end, s.get("publication_date", "")[:10], r.text))
        return out or None

    def parse(self, ent, raw) -> list[Fact]:
        facts: list[Fact] = []
        seen: set[tuple[date, str]] = set()
        for url, end, published, body in raw:
            for metric, value in key_figures(body).items():
                if (end, metric) in seen:
                    continue
                seen.add((end, metric))
                facts.append(Fact(entity_id=ent.id, reference_date=end, metric=metric, value=value,
                                  unit="pct", source=self.name, document=url,
                                  method="nsm_release", confidence=0.9))
        return facts

    def validate(self, records):
        keep = []
        for f in records:
            if f.metric in ("cet1_ratio", "tier1_ratio", "total_capital_ratio") and not 0 < f.value < 80:
                continue
            if f.metric in ("lcr", "nsfr") and not 50 < f.value < 1000:
                continue
            if f.metric in ("npl_ratio", "cost_of_risk") and not -5 < f.value < 40:
                continue
            keep.append(f)
        return keep

    def load(self, records) -> int:
        for ent in {f.entity_id for f in records}:
            store.drop("facts", entity_id=ent, source=self.name)
        return store.upsert("facts", records)
