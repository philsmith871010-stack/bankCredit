"""Bank bond quotes from Börse Frankfurt's website API (docs section 16.3), no key.

One daily sweep of the exchange's bond list (about 36,000 bonds, 500 a page) gives
every listed bond's last price, exchange-computed yield, coupon and currency in a
minute. Names are matched to our entities by issuer tokens; fixed-coupon senior
lines with two to eight years to run are kept as each bank's reference bonds.

Terms: free for non-commercial, non-redistributed use. Quotes stay in the private
tables and drive the market signal as a yield change against the benchmark; the
site shows the change, never the level.

Tables: bonds (isin key) and bond_quotes (isin + date).
"""
from __future__ import annotations

import hashlib
import logging
import re
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

import requests

from .. import store
from .base import Adapter, register

log = logging.getLogger("bankcredit.bonds")

API = "https://api.boerse-frankfurt.de/"
SITE = "https://live.deutsche-boerse.com/"
SALT_FALLBACK = "af5a8d16eb5dc49f8a72b26fd9185475c7a"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
PAGE = 500
WORKERS = 8
MAX_BONDS_PER_ENTITY = 4
HISTORY_DAYS = 45          # history fetched once for each bond new to the table, so a change exists from day one
CURRENCIES = {"EUR", "GBP", "USD"}

# issuer token (lower case, matched at the start of the bond name) -> entity id; longer tokens first
ISSUERS = [
    # adviser-list counterparties added 7 September 2026 (most specific names first)
    ("bnp paribas fortis", "bnp-paribas-fortis"), ("op corporate bank", "op-corporate-bank"), ("op yrityspankki", "op-corporate-bank"),
    ("credit agricole corporate", "credit-agricole-cib"), ("crédit agricole corporate", "credit-agricole-cib"), ("credit agricole cib", "credit-agricole-cib"),
    ("credit industriel", "cic"), ("crédit industriel", "cic"), ("landwirtschaftliche rentenbank", "rentenbank"), ("rentenbank", "rentenbank"),
    ("norddeutsche landesbank", "nord-lb"), ("nord/lb", "nord-lb"), ("nrw.bank", "nrw-bank"), ("nrw bank", "nrw-bank"), ("bng bank", "bng-bank"),
    ("nederlandse waterschapsbank", "nwb-bank"), ("lloyds bank corporate", "lloyds-bank-corporate-markets"),
    ("smbc bank international", "smbc-bank-international"), ("santander financial services", "santander-financial-services"),
    ("landesbank baden", "lbbw"), ("bayerische landesbank", "bayernlb"), ("landesbank hessen", "helaba"), ("dz bank", "dz-bank"),
    ("barclays bank uk", "barclays-bank-uk"), ("barclays bank plc", "barclays-bank"), ("barclays plc", "barclays"), ("barclays", "barclays"),
    ("hsbc holdings", "hsbc-holdings"), ("hsbc uk bank", "hsbc-uk"), ("hsbc bank plc", "hsbc-bank"), ("hsbc bank", "hsbc-bank"),
    ("lloyds banking", "lloyds-banking-group"), ("lloyds bank", "lloyds-bank"), ("bank of scotland", "bank-of-scotland"),
    ("natwest group", "natwest-group"), ("national westminster", "natwest-bank"), ("natwest markets", "natwest-markets"),
    ("standard chartered", "standard-chartered"), ("santander uk", "santander-uk"), ("nationwide building", "nationwide"), ("nationwide", "nationwide"),
    ("virgin money", "virgin-money-uk"), ("clydesdale", "clydesdale-bank"), ("tsb bank", "tsb"), ("co-operative bank", "co-operative-bank"),
    ("metro bank", "metro-bank"), ("osb group", "osb-group"), ("onesavings", "osb-group"), ("shawbrook", "shawbrook"), ("aldermore", "aldermore"),
    ("close brothers", "close-brothers"), ("paragon", "paragon"), ("secure trust", "secure-trust-bank"), ("vanquis", "vanquis"), ("investec", "investec"),
    ("yorkshire building", "yorkshire-bs"), ("coventry building", "coventry-bs"), ("skipton", "skipton-bs"), ("leeds building", "leeds-bs"),
    ("principality", "principality-bs"), ("west bromwich", "west-brom-bs"), ("nottingham building", "nottingham-bs"),
    ("deutsche bank", "deutsche-bank"), ("commerzbank", "commerzbank"), ("bnp paribas", "bnp-paribas"), ("societe generale", "societe-generale"),
    ("credit agricole", "credit-agricole"), ("crédit agricole", "credit-agricole"), ("bpce", "bpce"), ("credit mutuel", "credit-mutuel"),
    ("ing groep", "ing"), ("ing bank", "ing"), ("rabobank", "rabobank"), ("abn amro", "abn-amro"), ("unicredit", "unicredit"), ("intesa", "intesa-sanpaolo"),
    ("banco santander totta", None), ("banco santander", "banco-santander"), ("bbva", "bbva"), ("banco bilbao", "bbva"), ("caixabank", "caixabank"), ("sabadell", "banco-sabadell"),
    ("nordea", "nordea"), ("danske", "danske-bank"), ("swedbank", "swedbank"), ("svenska handelsbanken", "svenska-handelsbanken"), ("handelsbanken", "svenska-handelsbanken"),
    ("skandinaviska", "seb"), ("dnb bank", "dnb"), ("dnb", "dnb"), ("kbc", "kbc"), ("erste", "erste"), ("raiffeisen bank int", "raiffeisen-bank-international"),
    ("ubs group", "ubs"), ("ubs ag", "ubs"), ("jpmorgan", "jpmorgan-chase"), ("jp morgan", "jpmorgan-chase"), ("citigroup", "citigroup"),
    ("bank of america", "bank-of-america"), ("wells fargo", "wells-fargo"), ("goldman sachs", "goldman-sachs"), ("morgan stanley", "morgan-stanley"),
    ("bank of new york", "bny"), ("state street", "state-street"), ("northern trust", "northern-trust"),
    ("royal bank of canada", "rbc"), ("toronto-dominion", "td-bank"), ("toronto dominion", "td-bank"), ("bank of nova scotia", "scotiabank"),
    ("bank of montreal", "bmo"), ("canadian imperial", "cibc"), ("national bank of canada", "national-bank-of-canada"),
    ("anz new zealand", None), ("anz bank new zealand", None), ("australia and new zealand", "anz"), ("australia & new zealand", "anz"), ("anz", "anz"), ("commonwealth bank", "commonwealth-bank"),
    ("national australia", "nab"), ("westpac", "westpac"), ("macquarie bank", "macquarie-bank"), ("macquarie group", None),
    ("dbs group", "dbs"), ("dbs bank", "dbs"), ("oversea-chinese", "ocbc"), ("united overseas", "uob"), ("mitsubishi ufj", "mufg"),
    ("sumitomo mitsui financial", "smfg"), ("mizuho", "mizuho"), ("sumitomo mitsui trust", "sumitomo-mitsui-trust"),
    ("qatar national", "qnb"), ("first abu dhabi", "first-abu-dhabi-bank"), ("emirates nbd", "emirates-nbd"), ("abu dhabi commercial", "adcb"),
    ("aib group", "aib"), ("allied irish", "aib"), ("bank of ireland", "bank-of-ireland"), ("banco bpm", "banco-bpm"), ("mediobanca", "mediobanca"),
]
SUB_TOKENS = re.compile(r"\b(und|perp|nachr|sub|tier|at1|t2|flr|fl\b|var)\b|/und|\bund\b", re.I)


def salt(session: requests.Session) -> str:
    try:
        home = session.get(SITE, timeout=60, headers={"User-Agent": UA}).text
        m = re.search(r'src="([^"]*main[^"]*\.js)"', home)
        if m:
            u = m.group(1) if m.group(1).startswith("http") else SITE + m.group(1).lstrip("/")
            js = session.get(u, timeout=120, headers={"User-Agent": UA}).text
            m2 = re.search(r'tracing:\{salt:"([0-9a-f]+)"\}', js)
            if m2:
                return m2.group(1)
    except Exception as exc:
        log.warning("bonds: salt refresh failed (%s); using the last known value", exc)
    return SALT_FALLBACK


def headers(url: str, s: str) -> dict:
    now = datetime.now(timezone.utc)
    cd = now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"
    return {"Client-Date": cd, "X-Client-TraceId": hashlib.md5((cd + url + s).encode()).hexdigest(),
            "X-Security": hashlib.md5(datetime.now().strftime("%Y%m%d%H%M").encode()).hexdigest(),
            "User-Agent": UA, "Accept": "application/json, text/plain, */*", "Origin": SITE.rstrip("/"), "Referer": SITE,
            "Content-Type": "application/json; charset=UTF-8"}


def match_issuer(name: str) -> str | None:
    low = name.lower()
    for tok, ent in ISSUERS:
        if low.startswith(tok):
            return ent
    return None


def maturity_year(name: str) -> int | None:
    m = re.search(r"\b(\d{2})/(\d{2}|und)\b", name)
    if not m or m.group(2) == "und":
        return None
    y = 2000 + int(m.group(2))
    return y


def ytm(price: float, coupon: float, years: float) -> float | None:
    """Rough yield to maturity (annual coupon, clean price near par), for changes rather than levels."""
    if price <= 0 or years <= 0.2:
        return None
    return round((coupon + (100 - price) / years) / ((100 + price) / 2) * 100, 3)


def history(bond: dict, s: str) -> list[dict]:
    """Daily closes for one bond over the last HISTORY_DAYS from the exchange's price-history endpoint."""
    today = date.today()
    params = {"limit": 100, "offset": 0, "isin": bond["isin"], "mic": "XFRA",
              "minDate": str(today - timedelta(days=HISTORY_DAYS)), "maxDate": str(today)}
    url = API + "v1/data/price_history?" + urllib.parse.urlencode(params)
    years = bond["maturity_year"] - today.year + 0.5
    out = []
    try:
        r = requests.get(url, headers=headers(url, s), timeout=60)
        for d in (r.json().get("data") or []) if r.status_code == 200 else []:
            y = ytm(float(d["close"]), bond["coupon"], years)
            if y is not None and d.get("date"):
                out.append({"isin": bond["isin"], "date": d["date"][:10], "price": float(d["close"]), "yield": round(y, 3),
                            "yield_exch": None, "source": "frankfurt"})
    except Exception as exc:
        log.warning("bonds: history for %s failed (%s)", bond["isin"], exc)
    return out


@register
class BondsAdapter(Adapter):
    name = "bonds"
    cadence = "daily"

    def discover(self):
        yield "sweep"

    def fetch(self, item):
        s = salt(self.session)
        url = API + "v1/search/bond_search"

        def page(offset: int):
            for attempt in range(3):
                try:
                    r = requests.post(url, headers=headers(url, s), json={"lang": "en", "offset": offset, "limit": PAGE}, timeout=120)
                    if r.status_code == 200:
                        return r.json()
                    log.warning("bonds: page %d -> %s", offset, r.status_code)
                except requests.RequestException as exc:
                    log.warning("bonds: page %d failed (%s)", offset, exc)
                time.sleep(2 + 3 * attempt)
            return None

        first = page(0)
        if not first:
            return None
        total = int(first.get("recordsTotal") or 0)
        out = list(first.get("data") or [])
        offsets = list(range(PAGE, total, PAGE))
        # each page takes about 15 s server-side whatever its size, so fetch them concurrently
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            for j in ex.map(page, offsets):
                out += (j or {}).get("data") or []
        log.info("bonds: swept %d of %s bonds", len(out), total)
        if len(out) < 0.9 * total:
            log.warning("bonds: sweep incomplete (%d of %d); keeping what came back", len(out), total)
        return out or None

    def parse(self, item, raw) -> dict:
        today = date.today()
        bonds, quotes, seen_names = {}, [], set()
        for d in raw:
            name = ((d.get("name") or {}).get("originalValue") or "").strip()
            ent = match_issuer(name)
            if not ent:
                continue
            kd = d.get("keyData") or {}
            ccy = (kd.get("currency") or {}).get("originalValue") or ""
            coupon = kd.get("coupon")
            price = d.get("lastQuote")
            when = (d.get("dateTimeLastQuote") or "")[:10]
            my = maturity_year(name)
            if ccy not in CURRENCIES or coupon is None or price is None or not when or my is None:
                continue
            years = my - today.year + 0.5
            if not (1.5 <= years <= 8.5) or SUB_TOKENS.search(name):
                continue
            # The stored yield is our own approximation from the price so that today's quote and the backfilled
            # history are on one basis; the exchange's yield rides alongside for reference.
            y = ytm(float(price), float(coupon), years)
            ye = kd.get("yield")
            if y is None or not (-2 < y < 25) or name in seen_names:
                continue
            seen_names.add(name)                # 144A and Reg S lines of one bond carry the same name and price
            bonds[d["isin"]] = {"isin": d["isin"], "entity_id": ent, "name": name, "coupon": float(coupon), "currency": ccy,
                                "maturity_year": my, "source": "frankfurt"}
            quotes.append({"isin": d["isin"], "date": when, "price": float(price), "yield": round(float(y), 3),
                           "yield_exch": round(float(ye), 3) if ye is not None else None, "source": "frankfurt"})
        # keep a handful per entity: the most recently quoted, mid-curve first
        by_ent: dict[str, list] = {}
        for q in quotes:
            by_ent.setdefault(bonds[q["isin"]]["entity_id"], []).append(q)
        keep_isins = set()
        for ent, qs in by_ent.items():
            qs.sort(key=lambda q: (q["date"], -abs(bonds[q["isin"]]["maturity_year"] - today.year - 5)), reverse=True)
            keep_isins.update(q["isin"] for q in qs[:MAX_BONDS_PER_ENTITY])
        return {"bonds": [b for i, b in bonds.items() if i in keep_isins], "quotes": [q for q in quotes if q["isin"] in keep_isins]}

    def validate(self, records):
        return records

    def load(self, records) -> int:
        have = store.read("bond_quotes")
        known = set(have["isin"]) if not have.empty else set()
        new = [b for b in records["bonds"] if b["isin"] not in known]
        if new:
            s = salt(self.session)
            with ThreadPoolExecutor(max_workers=WORKERS) as ex:
                for rows in ex.map(lambda b: history(b, s), new):
                    records["quotes"] += rows
            log.info("bonds: backfilled %d-day history for %d new bonds", HISTORY_DAYS, len(new))
        return store.upsert("bonds", records["bonds"]) + store.upsert("bond_quotes", records["quotes"])
