"""EBA EU-wide Transparency Exercise: quarterly capital and leverage figures for about 120 EU banks (and UK
banks until 2020), published once a year as CSV with no key. Each exercise carries four reference dates,
so the series runs back to 2014 when the files are stacked.

Only the key-metrics rows are read (own funds, risk exposure, capital ratios, leverage). Amounts are in EUR
millions whatever the bank's currency, so they are stored with currency EUR; ratios are ratios. Figures load
under source "eba_te" and never outrank a bank's own Pillar 3 or the Pillar 3 data hub for the same date
(the export ranks sources), so they extend history rather than replace it.

Files are cached under data/cache/te/; the runner re-downloads them on the quarterly run.
"""
from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path

import pandas as pd

from .. import store
from ..models import Fact
from .base import Adapter, register

log = logging.getLogger("bankcredit.te")

CACHE = store.DATA / "cache" / "te"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

# exercise -> the "other" file (key metrics, capital, leverage, RWA); newest first
FILES = {
    "TE2024": "https://www.eba.europa.eu/assets/TE2024/Full_database/256109/tr_oth.csv",
    "TE2023": "https://www.eba.europa.eu/assets/TE2023/Full_database/837203/tr_oth.csv",
    "TE2022": "https://www.eba.europa.eu/assets/TE2022/Full_database/tr_oth.csv",
    "TE2021": "https://www.eba.europa.eu/assets/TE2021/Full_database/tr_oth.csv",
    "TE2020A": "https://www.eba.europa.eu/sites/default/files/document_library/Risk%20Analysis%20and%20Data/EU%20Wide%20Transparency%20Exercise/2020/Autumn%202020/Full%20database/tr_oth_2.csv",
    "TE2020S": "https://eba.europa.eu/sites/default/files/document_library/Risk%20Analysis%20and%20Data/EU%20Wide%20Transparency%20Exercise/2020/Full%20database/885655/tr_oth.csv",
    "TE2019": "https://www.eba.europa.eu/sites/default/files/document_library/Risk%20Analysis%20and%20Data/EU%20Wide%20Transparency%20Exercise/2019/Full%20database/tr_oth.csv",
    "TE2018": "https://www.eba.europa.eu/sites/default/files/documents/10180/2518657/85f729ae-90cd-4eb3-ad78-8e87081e157e/tr_oth.csv",
    "TE2017": "https://www.eba.europa.eu/sites/default/files/documents/10180/2027702/acf4b8b4-07d7-40fe-a0b1-7dd067041a71/tr_oth.csv",
    "TE2016": "https://www.eba.europa.eu/sites/default/files/documents/10180/1681546/de2d50e2-5dac-4592-b57c-1503f5f5a600/tr_oth.csv",
}

# label patterns are stable across exercises where item codes are not
LABELS = [
    # key-metrics sheet (2021 onwards) and the capital / leverage sheets (2015 onwards); transitional definitions throughout
    ("cet1_capital", r"^common equity tier 1 \(cet1\) capital\s*-\s*transitional period$|^common equity tier 1 capital \(net of deductions and after applying transitional adjustments\)$"),
    ("tier1_capital", r"^tier 1 capital\s*-\s*transitional period$|^tier 1 capital \(net of deductions and after transitional adjustments\)$"),
    ("total_capital", r"^total capital\s*-\s*transitional period$|^own funds$"),
    ("rwa", r"^total risk exposure amount$"),
    ("cet1_ratio", r"^common equity tier 1 \(as a percentage of risk exposure amount\)\s*-\s*transitional definition$|^common equity tier 1 capital ratio \(transitional period\)$"),
    ("tier1_ratio", r"^tier 1 \(as a percentage of risk exposure amount\)\s*-\s*transitional definition$|^tier 1 capital ratio \(transitional period\)$"),
    ("total_capital_ratio", r"^total capital \(as a percentage of risk exposure amount\)\s*-\s*transitional definition$|^total capital ratio \(transitional period\)$"),
    ("leverage_exposure", r"^leverage ratio total exposure measure\s*-\s*using a transitional definition of tier 1 capital$|^total leverage ratio exposures\s*-\s*using a transitional definition of tier 1 capital$"),
    ("leverage_ratio", r"^leverage ratio\s*-\s*using a transitional definition of tier 1 capital$"),
]
PCT = {"cet1_ratio", "tier1_ratio", "total_capital_ratio", "leverage_ratio"}


def metric_for(label: str) -> str | None:
    low = re.sub(r"\s+", " ", str(label).replace("\xa0", " ").replace("\ufffd", " ")).strip().lower()
    for m, rx in LABELS:
        if re.match(rx, low):
            return m
    return None


def period_date(p) -> date | None:
    s = str(int(p)) if isinstance(p, float) else str(p)
    if not re.fullmatch(r"\d{6}", s):
        return None
    y, mth = int(s[:4]), int(s[4:])
    last = {3: 31, 6: 30, 9: 30, 12: 31}.get(mth)
    return date(y, mth, last) if last else None


@register
class TransparencyAdapter(Adapter):
    name = "te"
    cadence = "quarterly"

    def discover(self):
        for k in FILES:
            yield k

    def fetch(self, item):
        CACHE.mkdir(parents=True, exist_ok=True)
        path = CACHE / f"{item}_tr_oth.csv"
        if not path.exists() or path.stat().st_size < 100000:
            r = self.session.get(FILES[item], timeout=600, headers={"User-Agent": UA})
            if r.status_code != 200 or len(r.content) < 100000:
                log.warning("te: %s -> %s (%d bytes)", item, r.status_code, len(r.content))
                return None
            path.write_bytes(r.content)
        return str(path)

    def parse(self, item, raw) -> list[Fact]:
        by_lei = {e.lei: e for e in self.entities if e.lei}
        # older exercises are cp1252 and name their columns differently; take what is there
        wanted = {"lei_code": "LEI_Code", "period": "Period", "label": "Label", "amount": "Amount", "sheet": "Sheet"}
        try:
            head = pd.read_csv(raw, nrows=2, encoding="utf-8")
            enc = "utf-8"
        except UnicodeDecodeError:
            head = pd.read_csv(raw, nrows=2, encoding="cp1252")
            enc = "cp1252"
        cols = {c: wanted[c.strip().lower()] for c in head.columns if c.strip().lower() in wanted}
        df = pd.read_csv(raw, usecols=list(cols), low_memory=False, encoding=enc, encoding_errors="replace", thousands=",").rename(columns=cols)
        if "Sheet" in df:
            df = df[df.Sheet.isin(["Key metrics", "Leverage", "Capital"])]
        df = df[df.LEI_Code.isin(by_lei)]
        out, seen = [], set()
        for r in df.itertuples():
            m = metric_for(r.Label)
            if not m:
                continue
            d = period_date(r.Period)
            if d is None or pd.isna(r.Amount):
                continue
            try:
                v = float(str(r.Amount).replace(",", ""))
            except ValueError:
                continue
            if m in PCT:
                v = v * 100 if v < 1.5 else v
                if not (0 < v < 80):
                    continue
            key = (r.LEI_Code, d, m)
            if key in seen:
                continue
            seen.add(key)
            e = by_lei[r.LEI_Code]
            out.append(Fact(entity_id=e.id, reference_date=d, metric=m, value=round(v, 4), unit="pct" if m in PCT else "ccy_m",
                            currency="" if m in PCT else "EUR", basis="consolidated", source="eba_te",
                            document=FILES[item], page=None, method="csv", confidence=0.9))
        log.info("te: %s -> %d facts for %d entities", item, len(out), len({f.entity_id for f in out}))
        return out

    def validate(self, records):
        return records

    def load(self, records) -> int:
        return store.upsert("facts", records)
