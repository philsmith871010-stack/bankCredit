"""CDS levels from DTCC's public swap-data dissemination files, no registration.

Two daily zip files on a public S3 bucket (docs section 14.1):
  SEC  security-based swaps: single-name CDS trades (reference entity name, seniority,
       coupon, upfront, capped notional) -> implied 5y spread per bank, median of the day
  CFTC index swaps: iTraxx and CDX trades with the traded spread -> index series

Single-name spreads are inferred from the upfront (protection seller pays for
investment-grade names below the 100bp coupon), so they are indicative; the
median across the day's trades and the trade count are stored. Written to the
`cds` table (entity_id, date, tier, level_bp, trades) and the `series` table
(ITRAXX_SNRFIN_5Y, ITRAXX_EUROPE_5Y, ITRAXX_XOVER_5Y, CDX_IG_5Y).
"""
from __future__ import annotations

import csv
import io
import logging
import re
import statistics
import zipfile
from datetime import date, datetime, timedelta

from .. import store
from .base import Adapter, register

log = logging.getLogger("bankcredit.dtcc")

SEC = "https://kgc0418-tdw-data-0.s3.amazonaws.com/sec/eod/SEC_CUMULATIVE_CREDITS_{:%Y_%m_%d}.zip"
CFTC = "https://kgc0418-tdw-data-0.s3.amazonaws.com/cftc/eod/CFTC_CUMULATIVE_CREDITS_{:%Y_%m_%d}.zip"
BACKFILL_DAYS = 45          # business days on the first run
INDEXES = {
    "ITRAXX EUROPE SENIOR FINANCIALS": ("ITRAXX_SNRFIN_5Y", "iTraxx Senior Financials 5y"),
    "ITRAXX EUROPE SNR FINANCIALS": ("ITRAXX_SNRFIN_5Y", "iTraxx Senior Financials 5y"),
    "ITRAXX EUROPE SUBORDINATED FINANCIALS": ("ITRAXX_SUBFIN_5Y", "iTraxx Sub Financials 5y"),
    "ITRAXX EUROPE SUB FINANCIALS": ("ITRAXX_SUBFIN_5Y", "iTraxx Sub Financials 5y"),
    "ITRAXX EUROPE": ("ITRAXX_EUROPE_5Y", "iTraxx Europe 5y"),
    "ITRAXX EUROPE CROSSOVER": ("ITRAXX_XOVER_5Y", "iTraxx Crossover 5y"),
    "CDX.NA.IG": ("CDX_IG_5Y", "CDX IG 5y"),
    "CDX NA IG": ("CDX_IG_5Y", "CDX IG 5y"),
}
# reference-entity name fragments (upper case) -> entity id
NAMES = {
    # ICE's abbreviated forms first, longer fragments before shorter ones they contain
    "LLOYDS BKG": "lloyds-banking-group", "LLOYDS BK PLC": "lloyds-bank", "BK OF SCOTLAND": "bank-of-scotland",
    "HSBC HLDGS": "hsbc-holdings", "HSBC BK": "hsbc-bank", "NATL WESTMINSTER BK": "natwest-bank",
    "STD CHARTERED": "standard-chartered", "BCO SANTANDER": "banco-santander", "BK OF AMERICA": "bank-of-america",
    "CR AGRICOLE": "credit-agricole", "DEUTSCHE BK": "deutsche-bank", "ING BK": "ing", "AUST & NEW ZLD": "anz",
    "COMWLTH BK": "commonwealth-bank", "NATL AUST BK": "nab", "BCO BPM": "banco-bpm", "SOC GEN": "societe-generale",
    "BARCLAYS BK": "barclays-bank",
    "BARCLAYS": "barclays", "HSBC HOLDINGS": "hsbc-holdings", "HSBC BANK": "hsbc-bank", "LLOYDS BANKING": "lloyds-banking-group",
    "LLOYDS BANK": "lloyds-bank", "NATWEST MARKETS": "natwest-markets", "NATWEST GROUP": "natwest-group", "NATIONAL WESTMINSTER": "natwest-bank",
    "STANDARD CHARTERED": "standard-chartered", "NATIONWIDE": "nationwide", "SANTANDER UK": "santander-uk",
    "DEUTSCHE BANK": "deutsche-bank", "COMMERZBANK": "commerzbank", "BNP PARIBAS": "bnp-paribas", "SOCIETE GENERALE": "societe-generale",
    "CREDIT AGRICOLE": "credit-agricole", "BPCE": "bpce", "CREDIT MUTUEL": "credit-mutuel", "ING BANK": "ing", "ING GROEP": "ing",
    "RABOBANK": "rabobank", "ABN AMRO": "abn-amro", "UNICREDIT": "unicredit", "INTESA": "intesa-sanpaolo", "BANCO SANTANDER": "banco-santander",
    "BILBAO": "bbva", "CAIXABANK": "caixabank", "SABADELL": "banco-sabadell", "NORDEA": "nordea", "DANSKE": "danske-bank",
    "SWEDBANK": "swedbank", "HANDELSBANKEN": "svenska-handelsbanken", "SKANDINAVISKA": "seb", "DNB": "dnb", "KBC": "kbc", "ERSTE": "erste",
    "RAIFFEISEN": "raiffeisen-bank-international", "UBS": "ubs", "JPMORGAN": "jpmorgan-chase", "CITIGROUP": "citigroup",
    "BANK OF AMERICA": "bank-of-america", "WELLS FARGO": "wells-fargo", "GOLDMAN SACHS": "goldman-sachs", "MORGAN STANLEY": "morgan-stanley",
    "BANK OF NEW YORK": "bny", "STATE STREET": "state-street", "MITSUBISHI UFJ": "mufg", "SUMITOMO MITSUI FIN": "smfg", "MIZUHO": "mizuho",
    "ROYAL BANK OF CANADA": "rbc", "TORONTO-DOMINION": "td-bank", "NOVA SCOTIA": "scotiabank", "BANK OF MONTREAL": "bmo",
    "CANADIAN IMPERIAL": "cibc", "COMMONWEALTH BANK": "commonwealth-bank", "WESTPAC": "westpac", "AUSTRALIA AND NEW ZEALAND": "anz",
    "NATIONAL AUSTRALIA": "nab", "MACQUARIE": "macquarie-bank", "DBS": "dbs", "OVERSEA-CHINESE": "ocbc", "UNITED OVERSEAS": "uob",
    "QATAR NATIONAL": "qnb", "FIRST ABU DHABI": "first-abu-dhabi-bank", "EMIRATES NBD": "emirates-nbd", "ABU DHABI COMMERCIAL": "adcb",
    "AIB": "aib", "BANK OF IRELAND": "bank-of-ireland", "BANCO BPM": "banco-bpm", "MEDIOBANCA": "mediobanca",
}


def _num(s: str) -> float:
    return float((s or "0").replace(",", "").replace("+", "") or 0)


def implied_spread_bp(row: dict) -> tuple[float, float] | None:
    """(spread bp, tenor years) from coupon, upfront and notional. Direction is not disclosed,
    so the upfront is assumed to be paid by the protection seller (names trading below the coupon)."""
    try:
        notional = _num(row["Notional amount-Leg 1"])
        upfront = _num(row["Other payment amount"])
        coupon = float(row["Fixed rate-Leg 1"] or 0) * 1e4
        exp = date.fromisoformat(row["Expiration Date"][:10])
        ex = date.fromisoformat(row["Execution Timestamp"][:10])
    except (ValueError, KeyError):
        return None
    if notional <= 0 or coupon <= 0 or upfront == 0:
        return None            # no upfront reported: the level would just echo the coupon
    t = (exp - ex).days / 365.25
    if t <= 0.5:
        return None
    annuity = (1 - 1.03 ** (-t)) / 0.03 * 0.97
    return coupon - (upfront / notional) * 1e4 / annuity, t


@register
class DTCCAdapter(Adapter):
    name = "dtcc"
    cadence = "daily"

    def __init__(self):
        super().__init__()
        self.session.headers.pop("User-Agent", None)
        have = store.read("series")
        self.have = set(have[have.source == "DTCC"].date.astype(str).str[:10]) if not have.empty and "source" in have else set()

    def discover(self):
        d = date.today()
        out, n = [], 0
        while n < BACKFILL_DAYS:
            d -= timedelta(days=1)
            if d.weekday() >= 5:
                continue
            n += 1
            if d.isoformat() not in self.have:
                out.append(d)
            elif len(self.have) > 5:
                break               # steady state: stop at the first day already loaded
        return sorted(out)

    def _rows(self, url: str) -> list[dict]:
        r = self.session.get(url, timeout=120)
        if r.status_code != 200:
            return []
        z = zipfile.ZipFile(io.BytesIO(r.content))
        rows = []
        for n in z.namelist():
            if n.endswith(".csv"):
                rows += list(csv.DictReader(io.TextIOWrapper(z.open(n), encoding="utf-8", errors="ignore")))
        return rows

    def fetch(self, day: date):
        sec, cftc = self._rows(SEC.format(day)), self._rows(CFTC.format(day))
        return {"day": day, "sec": sec, "cftc": cftc} if (sec or cftc) else None

    def parse(self, day, raw) -> dict:
        d = raw["day"].isoformat()
        # ---- index prints: traded spread, 5y tenor only
        idx: dict[str, list[float]] = {}
        for r in raw["cftc"]:
            name = (r.get("UPI Underlier Name") or "").upper().strip()
            key = INDEXES.get(name)
            if not key or (r.get("Action type") not in ("NEWT", "")):
                continue
            try:
                sp = float(r.get("Spread-Leg 1") or 0) * 1e4
                exp = date.fromisoformat(r["Expiration Date"][:10]); ex = date.fromisoformat(r["Execution Timestamp"][:10])
            except (ValueError, KeyError):
                continue
            t = (exp - ex).days / 365.25
            if sp > 0 and 4.4 <= t <= 5.6:
                idx.setdefault(key[0], []).append(sp)
        series = [{"series_id": sid, "date": d, "value": round(statistics.median(v), 1), "unit": "bp",
                   "label": next(l for k, (s, l) in INDEXES.items() if s == sid), "source": "DTCC", "trades": len(v)}
                  for sid, v in idx.items() if len(v) >= 3]
        # ---- single names
        names: dict[tuple[str, str], list[float]] = {}
        for r in raw["sec"]:
            if r.get("Action type") not in ("NEWT", ""):
                continue
            ref = (r.get("Underlying Asset Name") or r.get("UPI Underlier Name") or "").upper()
            ent = next((e for frag, e in NAMES.items() if frag in ref), None)
            if not ent:
                continue
            fisn = (r.get("UPI FISN") or "")
            tier = "sub" if re.search(r"\bSub\b", fisn) else "senior"
            got = implied_spread_bp(r)
            if not got:
                continue
            sp, t = got
            if 4.0 <= t <= 6.0 and 0 < sp < 2000:
                names.setdefault((ent, tier), []).append(sp)
        cds = [{"entity_id": ent, "date": d, "tier": tier, "level_bp": round(statistics.median(v), 1), "trades": len(v), "source": "dtcc"}
               for (ent, tier), v in names.items()]
        return {"series": series, "cds": cds}

    def validate(self, records):
        return records

    def load(self, records) -> int:
        return store.upsert("series", records["series"]) + store.upsert("cds", records["cds"])
