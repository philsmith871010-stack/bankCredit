"""Events feed: rating actions, new disclosures and credit-relevant news, no AI service.

Three collectors write to the `events` table (key: entity_id + event_id):

  rating      ESMA European Rating Platform action history (type_s:child records on the
              entity's live issuer-level ratings), last 400 days
  disclosure  every Pillar 3 document the pillar3 adapter loaded (documents table)
  news        Google News RSS search per entity, kept only when the headline matches
              a credit vocabulary and none of the consumer-product noise words

Severity is rules-based: downgrade, watch negative, default, enforcement, loss,
restatement -> warn or bad; upgrade, positive outlook -> good; everything else info.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime

from .. import store
from ..models import Entity
from .base import Adapter, register
from .esma import ESMARatingsAdapter

log = logging.getLogger("bankcredit.events")

GNEWS = "https://news.google.com/rss/search"
SLEEP = 1.0
NEWS_ONLY = bool(os.environ.get("BANKCREDIT_NEWS_ONLY"))      # the intraday run: headlines only, no register or documents
AGENCY_QUERY = '(Moody\'s OR Fitch OR "S&P" OR DBRS) (downgrade OR downgrades OR upgrade OR upgrades OR outlook OR "rating action" OR "placed on") (bank OR "building society" OR lender)'
SINCE_DAYS = 400
NEWS_DAYS = 120
EDITION = {"GB": ("en-GB", "GB", "GB:en"), "US": ("en-US", "US", "US:en"), "AU": ("en-AU", "AU", "AU:en"),
           "CA": ("en-CA", "CA", "CA:en"), "SG": ("en-SG", "SG", "SG:en"), "HK": ("en-HK", "HK", "HK:en")}

# Headline must contain one of these (credit relevance)...
CREDIT = re.compile(r"\b(rating|ratings|downgrad\w*|upgrad\w*|outlook|watch|moody'?s|fitch|s&p|dbrs|kbra|scope ratings|"
                    r"capital|cet1|tier ?1|tier ?2|at1|coco|mrel|tlac|leverage|liquidity|deposit outflow|deposits? (fell|dropped|flight)|"
                    r"loss|losses|impairment|provision|write-?down|bad loan|non-?performing|npl|"
                    r"fine[ds]?|penalt\w*|enforcement|sanction\w*|regulator|pra\b|fca\b|ecb\b|bafin|finma|apra|osfi|mas\b|"
                    r"stress test|resolution|bail-?in|restructur\w*|merger|acqui\w*|takeover|bid for|sale of|dispos\w*|"
                    r"results|profit|earnings|dividend|buy-?back|guidance|cost of risk|"
                    r"bond|notes? (offering|issue)|issuance|debt|senior|subordinated|covered bond|securiti[sz]ation|cds\b|spread\w*|"
                    r"default|insolven\w*|administration|rescue|bailout|run on|lawsuit|litigation|fraud|money laundering|aml\b|"
                    r"ceo|chief executive|chair\b|chairman|cfo|resign\w*|steps down|appoint\w*|"
                    r"cyber|outage|data breach|it failure|job cuts?|cut[s]? [\d,]+ jobs|redundanc\w*|layoffs?)", re.I)
# routine housekeeping and commentary that says nothing about the bank's credit
ROUTINE = re.compile(r"\b(buy-?backs?|share (re)?purchase|transactions? in week|treasury shares|voting rights|total number of shares|"
                     r"shares? acquired|acquires? [\d,]+ shares|stake in [A-Z]|position in [A-Z]|holdings? (in|of) [A-Z]|13f|"
                     r"etf\b|spdr|fund declares|distribution per|cents per unit|asset servic\w*|custodian|appoint\w* .* (analyst|economist|strategist)|"
                     r"marathon|sponsor\w*|tournament|festival|scholarship|"
                     r"stock (heads|opens|closes|slips|rises|falls|edges|gains|drops)|shares? (open|close|slip|rise|fall|edge|gain|drop)s? (higher|lower|after|ahead)|"
                     r"why is [A-Z].* (delivering|extending|posting)|weekly recap|"
                     r"(sees|expects|forecasts?|predicts?) .* (dollar|euro|sterling|yen|kospi|s&p 500|ftse|nikkei|oil|gold|bitcoin|fed|ecb|boe)|"
                     r"[–-] (commerzbank|rabobank|ing|danske|nordea|seb|swedbank|dnb|ubs|barclays|hsbc|natwest|lloyds|goldman sachs|morgan stanley|citi|jpmorgan)\s*$)", re.I)
# ...and none of these (retail product and lifestyle noise)
NOISE = re.compile(r"\b(savings? (rate|account)|isa\b|mortgage rate|fixed rate|best buy|cashback|switch(ing)? (offer|bonus)|"
                   r"current account|credit card|app\b|branch (opening|closure|closing)|house price|hpi\b|"
                   r"sponsor\w*|charity|football|rugby|cricket|awards?\b|customer service|scam warning|"
                   r"job(s)? (cut)?s? at|hiring|apprentice)\b", re.I)
# equity-research and stock-promotion noise: the bank as analyst, valuation pieces, holdings filings
ANALYST = re.compile(r"\b(upgrades|downgrades|initiates|reiterates|maintains|raises|cuts|lowers|trims|lifts)\b[^\n]{0,60}\b(stock|shares|price target|to (buy|sell|hold|neutral|overweight|underweight|outperform|underperform))\b", re.I)
STOCKSPAM = re.compile(r"\b(undervalued|overvalued|fair value|should you buy|worth buying|stock looks|stock (holds|rallies|slips|jumps|dips)|"
                       r"price target|analyst(s)? (say|says|expect)|shares? in [A-Z]|acquires new (shares|stake)|sells shares|position in|"
                       r"\$[A-Z]{2,5}\b|13f|top \d+ (stocks|shares)|dividend season|buy rating|sell rating|hold rating|insider (buying|selling))\b", re.I)
BLOCKED_SOURCES = {"marketbeat", "simplywall.st", "simply wall st", "kalkine", "stock titan", "ad hoc news", "ad-hoc-news",
                   "finance.biggo.com", "defense world", "etf daily news", "americanbankingnews", "tickerreport", "zacks",
                   "seeking alpha", "seekingalpha", "the motley fool", "gurufocus", "vt markets", "fxstreet", "iam patent", "connect cre",
                   "insidermonkey", "benzinga", "investorplace", "the globe and mail", "tipranks", "stockinvest", "marketscreener",
                   "tradingview", "investing.com", "yahoo finance", "the manila times", "sharecast", "morningstar", "moomoo",
                   "ainvest", "nasdaq.com", "streetinsider", "fintel", "quiver", "wallstreetzen", "coincodex", "medianet"}


def blocked_source(source: str) -> bool:
    low = (source or "").lower()
    return any(b in low for b in BLOCKED_SOURCES)
# bank economists' macro views, deal-by-deal property news, auto-generated bond and transcript pages
ECON = re.compile(r"\b(inflation|eurozone|gdp|economist|forex|fx\b|eur/usd|gbp/usd|usd/|treasury yields?|rate (cut|hike|rise)s?|"
                  r"bond (risk |coupon )?profile|earnings call transcript|dividend watch|income stocks?|directors.? deals|"
                  r"fund pays|portfolio for|patent|sponsor)\b", re.I)
BAD = re.compile(r"\b(default|insolven\w*|administration|bailout|rescue|run on|bail-?in|resolution|fraud|money laundering|"
                 r"restatement|going concern|breach)\b", re.I)
WARN = re.compile(r"\b(downgrad\w*|negative|loss|losses|impairment|fine[ds]?|penalt\w*|enforcement|sanction\w*|lawsuit|job cuts?|redundanc\w*|layoffs?|"
                  r"litigation|cyber|outage|deposit outflow|resign\w*|steps down|write-?down|provision)\b", re.I)
# Short names that are ordinary words or place names: query the full name and require a banking word next to it.
AMBIGUOUS = {"nationwide", "starling", "coventry", "leeds", "skipton", "nottingham", "newcastle", "cumberland", "family",
             "progressive", "metro", "principality", "leek", "furness", "suffolk", "saffron", "darlington", "melton",
             "monmouthshire", "hinckley and rugby", "yorkshire", "west brom", "paragon", "chase", "first direct", "atom",
             "virgin money uk", "co-operative bank", "handelsbanken plc", "national bank of canada", "westpac", "nab"}
BANKWORD = r"(building society|bank|banking|bs\b|plc|group|lender|society)"
GOOD = re.compile(r"\b(upgrad\w*|positive outlook|outlook (revised )?to positive|record profit|beats?|raised guidance)\b", re.I)


def severity(title: str) -> str:
    if BAD.search(title):
        return "bad"
    if WARN.search(title):
        return "warn"
    if GOOD.search(title):
        return "good"
    return "info"


def rating_severity(action: str, value: str = "") -> str:
    low = (action or "").lower()
    if "default" in low:
        return "bad"
    if "downgrade" in low or ("watch" in low and "negative" in low) or "negative" in low:
        return "warn"
    if "upgrade" in low or "positive" in low:
        return "good"
    return "info"


@register
class EventsAdapter(Adapter):
    name = "events"
    cadence = "daily"

    def __init__(self):
        super().__init__()
        self.esma = ESMARatingsAdapter()
        self.session.headers["User-Agent"] = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
                                              "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

    def discover(self):
        only = {x for x in os.environ.get("BANKCREDIT_ONLY", "").split(",") if x}
        for e in self.entities:
            if not only or e.id in only:
                yield e
        yield "agency-sweep"                      # one query per edition for rating actions across the whole universe
        if not NEWS_ONLY:
            yield "documents"

    # ---- fetch ----
    def fetch(self, item):
        if item == "documents":
            return {"documents": store.read("documents")}
        if item == "agency-sweep":
            items = []
            for hl, gl, ceid in (EDITION["GB"], EDITION["US"]):
                try:
                    r = self.session.get(GNEWS, params={"q": AGENCY_QUERY, "hl": hl, "gl": gl, "ceid": ceid}, timeout=60)
                    time.sleep(SLEEP)
                    if r.status_code == 200:
                        items += ET.fromstring(r.content).findall(".//item")
                except Exception as exc:
                    log.warning("events: agency sweep failed: %s", exc)
            return {"sweep": items}
        e: Entity = item
        out = {"actions": [], "news": []}
        if not NEWS_ONLY:
            try:
                out["actions"] = self.esma.actions(e, date.today() - timedelta(days=SINCE_DAYS))
            except Exception as exc:
                log.warning("events %s: esma actions failed: %s", e.id, exc)
        try:
            hl, gl, ceid = EDITION.get(e.country, ("en-GB", "GB", "GB:en"))
            q = f'"{e.name}"' if (len(e.short_name) <= 3 or e.short_name.lower() in AMBIGUOUS) else f'"{e.short_name}"'
            r = self.session.get(GNEWS, params={"q": q, "hl": hl, "gl": gl, "ceid": ceid}, timeout=60)
            time.sleep(SLEEP)
            if r.status_code == 200:
                out["news"] = ET.fromstring(r.content).findall(".//item")
            else:
                log.warning("events %s: google news %s", e.id, r.status_code)
        except Exception as exc:
            log.warning("events %s: news failed: %s", e.id, exc)
        return out

    # ---- parse ----
    def parse(self, item, raw) -> list[dict]:
        rows = []
        if item == "documents":
            docs = raw["documents"]
            if docs.empty:
                return rows
            for d in docs[docs.status.isin(["loaded", "unverified"])].itertuples():
                pub = str(getattr(d, "published", "") or "")[:10]
                ref = str(d.reference_date or "")[:10]
                pub = pub if pub[:2] == "20" else ""                  # a missing stamp reads as "nan" or "None"
                ref = ref if ref[:2] == "20" else ""
                when = pub if pub and pub >= ref else ref            # the PDF's own stamp, else the period end; never our fetch time
                if not when:
                    continue
                rows.append({"entity_id": d.entity_id, "event_id": f"doc:{(d.sha256 or d.url)[:16]}",
                             "date": when, "type": "disclosure",
                             "title": f"Pillar 3 report" + (f" for the period to {ref}" if ref else "") + (" published" if pub else "") + f": {d.title}",
                             "source": "FCA NSM" if d.origin == "nsm" else "firm website", "url": d.url,
                             "severity": "info", "detail": d.status})
            return rows
        if item == "agency-sweep":
            return sweep_rows(self.entities, raw["sweep"])
        e: Entity = item
        for a in raw["actions"]:
            if not a.get("date"):
                continue
            agency = {"fitch": "Fitch", "sp": "S&P", "moodys": "Moody's", "dbrs": "DBRS", "kbra": "KBRA", "scope": "Scope", "jcr": "JCR"}.get(a["agency"], a["agency"])
            rows.append({"entity_id": e.id, "event_id": f"esma:{a['event_id']}", "date": a["date"].isoformat(), "type": "rating",
                         "title": f"{agency} {a['action'].lower()}: {a['rating_name']} {a['value']}".strip(),
                         "source": "ESMA European Rating Platform", "url": "https://registers.esma.europa.eu/publication/searchRegister?core=esma_registers_radar",
                         "severity": rating_severity(a["action"], a["value"]), "detail": a.get("horizon", "")})
        cutoff = datetime.utcnow() - timedelta(days=NEWS_DAYS)
        for it in raw["news"]:
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            src = it.find("source")
            source = src.text.strip() if src is not None and src.text else "news"
            try:
                when = parsedate_to_datetime(it.findtext("pubDate") or "").replace(tzinfo=None)
            except Exception:
                continue
            if when < cutoff or not title or not link:
                continue
            if NOISE.search(title) or not CREDIT.search(title):
                continue
            if blocked_source(source) or STOCKSPAM.search(title) or ANALYST.search(title) or ECON.search(title) or ROUTINE.search(title):
                continue
            # the entity must actually be named in the headline (Google widens queries)
            if not keep_headline(e, title, source):
                continue
            rows.append({"entity_id": e.id, "event_id": "news:" + hashlib.sha1(link.encode()).hexdigest()[:16],
                         "date": when.date().isoformat(), "type": "news", "title": title[:240], "source": source[:60],
                         "url": link, "severity": severity(title), "detail": ""})
        return rows

    def validate(self, records):
        return [r for r in records if r["title"] and r["date"]]

    def load(self, records) -> int:
        return store.upsert("events", records)

    def run(self):
        result = super().run()
        prune_news()
        return result


# first words that identify nothing on their own: the whole short name must appear
GENERIC_FIRST = {"bank", "banco", "banque", "credit", "crédit", "national", "first", "royal", "standard", "united", "state",
                 "commonwealth", "northern", "western", "society", "the", "goldman", "morgan", "bank-of", "co-operative"}


def _news_row(entity_id: str, title: str, link: str, source: str, when) -> dict:
    return {"entity_id": entity_id, "event_id": "news:" + hashlib.sha1(link.encode()).hexdigest()[:16],
            "date": when.date().isoformat(), "type": "news", "title": title[:240], "source": source[:60],
            "url": link, "severity": severity(title), "detail": ""}


def sweep_rows(entities, items) -> list[dict]:
    """Rating-action headlines for the whole universe, attributed to every entity actually named in them."""
    rows, cutoff = [], datetime.utcnow() - timedelta(days=NEWS_DAYS)
    for it in items:
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        src = it.find("source")
        source = src.text.strip() if src is not None and src.text else "news"
        try:
            when = parsedate_to_datetime(it.findtext("pubDate") or "").replace(tzinfo=None)
        except Exception:
            continue
        if when < cutoff or not title or not link:
            continue
        for e in entities:
            if keep_headline(e, title, source):
                rows.append(_news_row(e.id, title, link, source, when))
    return rows


def keep_headline(entity: Entity, title: str, source: str) -> bool:
    """The full news filter, applied to a stored row as well as to a fresh one."""
    if NOISE.search(title) or not CREDIT.search(title):
        return False
    if blocked_source(source) or STOCKSPAM.search(title) or ANALYST.search(title) or ECON.search(title) or ROUTINE.search(title):
        return False
    short, low = entity.short_name.lower(), title.lower()
    # the bank as commentator, analyst or asset manager is not news about the bank
    if re.search(rf"\b{re.escape(short)}(?:'s)?\b[^.]{{0,40}}\b(says|said|sees|favou?rs|backs|charts|breaks down|research (report|note|analysis)|strategist|economist|"
                 rf"analysts?|asset manag\w*|alternatives|wealth|private bank|research)\b", low) \
            or re.search(rf"\b(analysts?|strategists?|economists?) at {re.escape(short)}\b|according to {re.escape(short)}\b|advises? on .* {re.escape(short)}\b", low):
        return False
    if re.search(rf"\b{re.escape(short)}\b\s+(upgrades?|downgrades?|initiates|reiterates|raises|cuts|lifts|trims|lowers|sees|expects|says|names|picks)\b", low) \
            or re.search(rf"\b(upgraded|downgraded|initiated|reiterated|raised|cut|lowered)\b[^.]{{0,80}}\bby {re.escape(short)}\b", low):
        return False
    if short in AMBIGUOUS:
        return bool(re.search(rf"\b{re.escape(short)}\b[^.]{{0,30}}{BANKWORD}|{BANKWORD}[^.]{{0,20}}\b{re.escape(short)}\b", low))
    first = short.split()[0]
    probe = first if (len(first) > 3 and first not in GENERIC_FIRST) else short
    return bool(re.search(rf"\b{re.escape(probe)}", low))


VERDICTS = store.DATA / "review" / "news_verdicts.json"


def load_verdicts() -> dict:
    """{event_id: {"keep": bool, "severity": str|None, "why": str}} written by the news-review skill on the Mac."""
    try:
        return json.loads(VERDICTS.read_text()) if VERDICTS.exists() else {}
    except Exception:
        return {}


def prune_news() -> int:
    """Re-apply the current news rules and the reviewer's verdicts to stored rows, so improvements clean history too."""
    from ..entities import load as load_entities
    ev = store.read("events")
    if ev.empty:
        return 0
    ents = {e.id: e for e in load_entities()}
    verdicts = load_verdicts()
    keep, sev = [], []
    for r in ev.itertuples():
        if r.type != "news":
            keep.append(True); sev.append(r.severity)
            continue
        v = verdicts.get(r.event_id)
        e = ents.get(r.entity_id)
        ok = bool(e) and keep_headline(e, str(r.title), str(r.source))
        if v is not None:
            ok = ok and bool(v.get("keep", True))
        keep.append(ok)
        sev.append(v.get("severity") or r.severity if v and v.get("severity") in ("bad", "warn", "good", "info") else r.severity)
    ev = ev.assign(severity=sev)
    dropped = int(len(keep) - sum(keep))
    ev[keep].to_parquet(store.path("events"), index=False)
    if dropped:
        log.info("events: pruned %d news rows under the current rules and verdicts", dropped)
    return dropped
