"""Yahoo Finance daily closes for listed entities.

Uses the public chart endpoint (no key). One request per symbol; a full 2y
backfill the first time an entity is seen, 1mo top-ups after that. Also home to
the price-derived helpers (realised vol, 52-week drawdown) used by the export.
"""
from __future__ import annotations

import math
import time
from datetime import date, datetime, timezone
from typing import Iterable

import pandas as pd

from .. import store
from ..models import Entity, Price
from .base import Adapter, log, register

CHART_URL = "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": BROWSER_UA, "Accept": "application/json,text/plain,*/*"}
MAX_RETRIES = 2            # on 429 only
BACKOFF_SECONDS = 5.0      # doubled on each retry
TIMEOUT = 30


class SymbolNotFound(Exception):
    """Yahoo returned 404 or an empty result for the symbol."""


def get_chart(session, symbol: str, range_: str = "5d", interval: str = "1d") -> dict:
    """Return the first chart result for symbol. Raises SymbolNotFound on 404/empty.

    Retries at most MAX_RETRIES times on HTTP 429, with an increasing backoff
    (honouring Retry-After when present). Other HTTP errors raise.
    """
    url = CHART_URL.format(symbol=symbol)
    params = {"range": range_, "interval": interval, "includePrePost": "false"}
    attempt = 0
    while True:
        resp = session.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
        if resp.status_code == 429 and attempt < MAX_RETRIES:
            attempt += 1
            wait = float(resp.headers.get("Retry-After") or BACKOFF_SECONDS * (2 ** (attempt - 1)))
            log.warning("yahoo: 429 for %s, retry %d/%d in %.0fs", symbol, attempt, MAX_RETRIES, wait)
            time.sleep(wait)
            continue
        if resp.status_code == 404:
            raise SymbolNotFound(f"{symbol}: 404 {_error_text(resp)}")
        resp.raise_for_status()
        payload = resp.json()
        chart = payload.get("chart") or {}
        results = chart.get("result") or []
        if not results:
            raise SymbolNotFound(f"{symbol}: empty result {chart.get('error') or ''}".strip())
        return results[0]


def _error_text(resp) -> str:
    try:
        err = resp.json().get("chart", {}).get("error") or {}
        return f"{err.get('code', '')} {err.get('description', '')}".strip()
    except Exception:
        return resp.text[:120]


def closes_from_result(result: dict) -> list[tuple[date, float]]:
    """(date, close) pairs from a chart result, skipping null closes."""
    ts = result.get("timestamp") or []
    quotes = (result.get("indicators") or {}).get("quote") or [{}]
    closes = quotes[0].get("close") or []
    out = []
    for t, c in zip(ts, closes):
        if c is None:
            continue
        try:
            c = float(c)
        except (TypeError, ValueError):
            continue
        if math.isnan(c):
            continue
        d = datetime.fromtimestamp(t, tz=timezone.utc).date()
        out.append((d, c))
    return out


@register
class YahooPriceAdapter(Adapter):
    name = "yahoo"
    cadence = "daily"
    regions: tuple[str, ...] = ()

    def __init__(self):
        super().__init__()
        self.session.headers.update(HEADERS)
        self.not_found: list[str] = []
        self._have_prices: set[str] | None = None

    # ---- pipeline ----
    def discover(self) -> Iterable[tuple[Entity, str]]:
        for e in self.entities:
            for sym in (s.strip() for s in e.tickers.split(",")):
                if sym:
                    yield e, sym

    def _has_prices(self, entity_id: str) -> bool:
        if self._have_prices is None:
            df = store.read("prices")
            self._have_prices = set(df["entity_id"].unique()) if not df.empty and "entity_id" in df else set()
        return entity_id in self._have_prices

    def fetch(self, item):
        entity, symbol = item
        range_ = "1mo" if self._has_prices(entity.id) else "2y"
        try:
            return get_chart(self.session, symbol, range_)
        except SymbolNotFound as exc:
            log.warning("yahoo: symbol not found, skipping: %s", exc)
            self.not_found.append(symbol)
            return None

    def parse(self, item, raw) -> list[Price]:
        entity, symbol = item
        meta = raw.get("meta") or {}
        currency = meta.get("currency") or ""   # "GBp" = pence on the LSE; stored as-is
        return [
            Price(entity_id=entity.id, date=d, close=c, currency=currency, symbol=symbol, source=self.name)
            for d, c in closes_from_result(raw)
        ]

    def validate(self, records: list[Price]) -> list[Price]:
        return [r for r in records if r.close > 0]

    def load(self, records: list[Price]) -> int:
        n = store.upsert("prices", records)
        if records and self._have_prices is not None:
            self._have_prices.add(records[0].entity_id)
        return n


# ---- price-derived metrics (used by the export step) ----

def _closes(entity_id: str) -> pd.Series:
    """Daily close series (index=date, ascending) for an entity, or empty."""
    df = store.read("prices")
    if df.empty or "entity_id" not in df:
        return pd.Series(dtype=float)
    df = df[df["entity_id"] == entity_id]
    if df.empty:
        return pd.Series(dtype=float)
    # if an entity has several symbols, use the one with the longest history
    sym = df.groupby("symbol").size().idxmax()
    df = df[df["symbol"] == sym]
    s = pd.Series(df["close"].astype(float).values, index=pd.to_datetime(df["date"]))
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s[s > 0]


def realised_vol(entity_id: str, window: int = 30) -> float | None:
    """Annualised realised volatility (percent) of daily log returns over the last `window` trading days."""
    s = _closes(entity_id)
    if len(s) < window + 1:
        return None
    r = pd.Series(s.values[-(window + 1):]).apply(math.log).diff().dropna()
    if len(r) < 2:
        return None
    return float(r.std(ddof=1) * math.sqrt(252) * 100)


def drawdown_52w(entity_id: str) -> float | None:
    """Percent below the 52-week high (0 = at the high; positive = below it)."""
    s = _closes(entity_id)
    if s.empty:
        return None
    last_date = s.index[-1]
    window = s[s.index > last_date - pd.Timedelta(weeks=52)]
    if window.empty:
        return None
    high = float(window.max())
    if high <= 0:
        return None
    return float((1 - float(s.iloc[-1]) / high) * 100)
