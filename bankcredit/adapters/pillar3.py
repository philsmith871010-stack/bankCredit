"""Pillar 3 PDF collector and KM1 extractor for firms without an API or data hub.

discover  -> one work item per locator (bankcredit/adapters/pillar3_locators.py) plus
             the FCA National Storage Mechanism poll, matched to entities by LEI
fetch     -> listing page HTML, candidate PDF links, download of unseen PDFs
parse     -> rules-based KM1 extraction (bankcredit/extract/km1.py); no AI service
validate  -> the extractor's own cross-checks decide loaded / unverified / review
load      -> facts (source "pillar3", method "pdf_rules") and the documents table;
             failures go to data/review/queue.json for the local review skill

PDFs are cached under data/cache/pdf (not committed); the documents table holds
the URL, hash and outcome so a run never downloads the same file twice.
"""
from __future__ import annotations

import calendar
import hashlib
import os
import html
import json
import logging
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit, quote

from .. import learn, review, store
from ..extract import km1, us
from ..models import Fact
from .base import Adapter, register
from .pillar3_locators import COUNTRY_CCY, LOCATORS

log = logging.getLogger("bankcredit.pillar3")

BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/128.0.0.0 Safari/537.36")
NSM_API = "https://api.data.fca.org.uk/search?index=nsm-search"
NSM_ARTEFACTS = "https://data.fca.org.uk/artefacts/"
# A link that names a reporting period or a disclosure section, so following it is likely to reach
# the files rather than the rest of the website.
INDEX_PAGE = re.compile(r"(?:19|20)\d\d(?:[-_/]?(?:q[1-4]|[1-4]q|h[12]|fy))?(?:/|/index|\.html?)?$|"
                        r"basel|pillar|disclos|regulatory|capital", re.I)
MAX_NEW_PER_ENTITY = int(os.environ.get("BANKCREDIT_MAX_NEW", "3"))    # newest unseen PDFs fetched per run (raise for a one-off deep pass)
LINK_RE = re.compile(r"""(?:https?:)?//[^\s"'<>\\)]+|/[^\s"'<>\\)]+""")
# an href attribute keeps its literal spaces (OCBC names files "Pillar 3 Disclosures.pdf"); those are
# percent-encoded rather than truncated at the first space
HREF_RE = re.compile(r"(?:href|src|data-href)\s*=\s*[\"']([^\"']+)[\"']", re.I)
ANCHOR_RE = re.compile(r"<a\b[^>]*?href\s*=\s*[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)
SLEEP = 1.0


# ---- period inference from a URL or headline ----------------------------
def _month_end(y: int, m: int) -> date:
    while m > 12:
        m -= 12; y += 1
    while m < 1:
        m += 12; y -= 1
    return date(y, m, calendar.monthrange(y, m)[1])


def _shift(d: date, months: int) -> date:
    y, m = d.year, d.month + months
    while m > 12:
        m -= 12; y += 1
    while m < 1:
        m += 12; y -= 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


TAGS = {"q1": 1, "q2": 2, "q3": 3, "q4": 4, "h1": 2, "hy": 2, "half year": 2, "half-year": 2, "halfyear": 2,
        "half yearly": 2, "half-yearly": 2, "interim": 2, "h2": 4}


def infer_period(text: str, year_end: str = "12-31") -> date | None:
    """Best-effort period end from a filename or headline; None if nothing recognisable."""
    t = unquote(text).lower().replace("%20", " ").replace("_", " ")
    t = re.sub(r"\b(?:pillar|basel)\s?-?\s?(?:3|iii)\b|\btier\s?-?[12]\b", " ", t)   # "pillar-3-june-2024" is not 3 June
    t = re.sub(r"\b(first|second|third|fourth)[ -]quarter\b", lambda m: "q" + str("first second third fourth".split().index(m.group(1)) + 1), t)
    ye_m, ye_d = (int(x) for x in year_end.split("-"))
    explicit = [d for d in km1.parse_dates(t.replace("-", " "), explicit_only=True)
                if d.day >= 28 or (d.month, d.day) == (ye_m, ye_d)]
    if explicit:
        return max(explicit)
    m = re.search(r"\b(20\d{2})[ -]+" + km1.MON + r"\b", t)                      # "2025-march"
    if m:
        return _month_end(int(m.group(1)), km1.MONTHS[m.group(2)[:3]])
    m = re.search(r"(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])", t)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    tag = re.search(r"\b(q[1-4]|h[12]|hy|half[ -]?year(?:ly)?|interim)(?=\d{2}\b|\b)", t)
    span = re.search(r"\b(20\d{2})[-/](?:20)?(\d{2})\b", t)          # 2025-2026 or 2025-26
    year = None
    if span:
        year = 2000 + int(span.group(2))
    else:
        m = re.search(r"\b(20\d{2})\b", t)
        if m:
            year = int(m.group(1))
        elif tag:
            m = re.search(r"\b(?:q[1-4]|h[12]|hy)\s?-?(\d{2})\b(?!\d)", t)   # Q126, H126
            if m:
                year = 2000 + int(m.group(1))
    if year is None:
        return None
    if not tag:
        return date(year, ye_m, ye_d)
    n = TAGS.get(tag.group(1), 2)
    if (ye_m, ye_d) == (12, 31):
        return _month_end(year, 3 * n)
    end = _shift(date(year, ye_m, ye_d), -(4 - n) * 3)
    if ye_d >= 28:
        return _month_end(end.year, end.month)
    return end if end.day >= 15 else _month_end(end.year, end.month - 1)


# ---- adapter ------------------------------------------------------------
@register
class Pillar3Adapter(Adapter):
    name = "pillar3"
    cadence = "daily"
    # One request per bank, and each bank is a different website: six at a time is six different
    # hosts, not six knocks on one door. This is where the daily run spends most of its time.
    workers = 6

    def __init__(self):
        super().__init__()
        self.session.headers["User-Agent"] = BROWSER_UA
        self.session.headers["Accept"] = "text/html,application/xhtml+xml,application/pdf,*/*"
        self.session.headers["Accept-Language"] = "en-GB,en;q=0.9"
        self.by_id = {e.id: e for e in self.entities}
        self.cache = store.DATA / "cache" / "pdf"
        self.docs = store.read("documents")
        self.seen = set(self.docs.url) if not self.docs.empty else set()
        self._pages: dict[str, str] = {}
        self._nsm: list[dict] | None = None

    # ---- discover ----
    def discover(self):
        only = {x for x in os.environ.get("BANKCREDIT_ONLY", "").split(",") if x}
        for loc in LOCATORS:
            if loc["entity"] in self.by_id and (not only or loc["entity"] in only):
                yield dict(loc, id=loc["entity"])
        if not only or "nsm" in only:
            yield {"id": "nsm", "kind": "nsm-poll"}

    def _pattern_candidates(self, loc: dict) -> list[tuple[str, date | None, str]]:
        """URL templates filled for the last six fiscal quarters, newest first."""
        ye_m, ye_d = (int(x) for x in loc.get("year_end", "12-31").split("-"))
        today = date.today()
        out = []
        fy = today.year + (1 if (today.month, today.day) > (ye_m, ye_d) else 0)
        for y in (fy, fy - 1, fy - 2):
            for q in (4, 3, 2, 1):
                end = _shift(date(y, ye_m, ye_d), -(4 - q) * 3)
                if ye_d >= 28:
                    end = _month_end(end.year, end.month)
                if end > today:
                    continue
                for tpl in loc["urls"]:
                    u = tpl.format(year=y, yy=f"{y % 100:02d}", q=q, qend=end.isoformat(),
                                   qword=("first", "second", "third", "fourth")[q - 1],
                                   mm=f"{end.month:02d}", dd=f"{end.day:02d}", yymmdd=end.strftime("%y%m%d"))
                    out.append((u, end, u.rsplit("/", 1)[-1]))
        return out[:12]

    # ---- fetch ----
    def _get_page(self, url: str) -> str:
        if url not in self._pages:
            r = self.session.get(url, timeout=60)
            time.sleep(SLEEP)
            self._pages[url] = r.text if r.status_code == 200 else ""
            if r.status_code != 200:
                log.warning("listing %s -> %s", url, r.status_code)
        return self._pages[url]

    def _anchor_text(self, body: str) -> dict[str, str]:
        """{href: visible text} for every anchor on the page.

        Some banks give their documents opaque addresses - Handelsbanken serves them as numeric
        ids under /contents/v1/document/, JPMorgan as static-files - so the only thing that says
        which report a link is, is what the link says."""
        out: dict[str, str] = {}
        raw = html.unescape(body).replace("\\/", "/")
        for m in ANCHOR_RE.finditer(raw):
            href, inner = m.group(1), m.group(2)
            text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", inner)).strip()
            if href and text and href not in out:
                out[href] = text[:200]
        return out

    def _links(self, page_url: str, body: str) -> list[str]:
        raw = html.unescape(body).replace("\\/", "/")
        out, seen = [], set()
        cands = [quote(m.group(1), safe=":/?&=%#+,;@$!*'()~") for m in HREF_RE.finditer(raw)]
        cands += [m.group(0) for m in LINK_RE.finditer(raw)]
        for u in cands:
            if u.startswith("//"):
                u = "https:" + u
            try:
                u = urljoin(page_url, u).split("#")[0]
            except ValueError:
                continue
            u = re.sub(r'["\'\\].*$', "", u)
            if u not in seen:
                seen.add(u); out.append(u)
        return out

    def _matches(self, loc: dict, page_url: str, body: str) -> list[tuple[str, date | None, str]]:
        mrx = re.compile(loc["match"], re.I)
        xrx = re.compile(loc["exclude"], re.I) if loc.get("exclude") else None
        trx = re.compile(loc["text"], re.I) if loc.get("text") else None
        ye = loc.get("year_end", "12-31")
        texts = {}
        if trx:
            anchors = self._anchor_text(body)
            texts = {urljoin(page_url, h).split("#")[0]: t for h, t in anchors.items()}
        found = []
        for u in self._links(page_url, body):
            d = unquote(u)
            if not mrx.search(d) or (xrx and xrx.search(d)):
                continue
            if re.search(r"\.(jpg|png|gif|svg|css|js|xlsx?|docx?)(\?|$)", d, re.I):
                continue
            text = texts.get(u.split("#")[0], "")
            if trx and not (trx.search(text) and not (xrx and xrx.search(text))):
                continue          # an opaque address says nothing; its link text is the only label
            name = d.rsplit("/", 1)[-1][:120]
            found.append((u, infer_period(name, ye) or infer_period(d, ye) or infer_period(text, ye),
                          (text[:120] if trx else name) or name))
        return found

    def _index_pages(self, loc: dict, body: str, limit: int = 6) -> list[str]:
        """Same-host pages this listing links that look like a period's own index.

        Several banks publish an index of quarters rather than a list of files: MUFG's Basel 3
        page links to basel3/2026-3q/index.html and the PDFs live one level down. Without this
        the locator's pattern is tested against a page that has no documents on it at all."""
        from urllib.parse import urlparse
        host = urlparse(loc["page"]).netloc.replace("www.", "")
        page = loc["page"].rstrip("/")
        out = []
        for u in self._links(loc["page"], body):
            if urlparse(u).netloc.replace("www.", "") != host or u.rstrip("/") == page:
                continue
            if re.search(r"\.(pdf|jpg|png|svg|css|js|xlsx?|docx?|zip)(\?|$)|#|mailto:", u, re.I):
                continue
            if not INDEX_PAGE.search(u) or u in out:
                continue
            out.append(u)
            if len(out) >= limit:
                break
        return out

    def _candidates(self, loc: dict) -> list[tuple[str, date | None, str]]:
        """(url, inferred period, title) for links on the listing page that match the locator,
        following one level into per-period index pages when the listing itself holds no files."""
        body = self._get_page(loc["page"])
        if not body:
            return []
        found = self._matches(loc, loc["page"], body)
        if not found and loc.get("follow", True):
            for sub in self._index_pages(loc, body):
                sbody = self._get_page(sub)
                if sbody:
                    found += self._matches(loc, sub, sbody)
        seen, unique = set(), []
        for f in found:
            if f[0] not in seen:
                seen.add(f[0]); unique.append(f)
        unique.sort(key=lambda x: (x[1] or date(1900, 1, 1)), reverse=True)
        return unique

    def _nsm_hits(self) -> list[dict]:
        if self._nsm is None:
            since = (date.today() - timedelta(days=int(os.environ.get("BANKCREDIT_NSM_DAYS", "400")))).isoformat()
            body = {"from": 0, "size": 300, "sortorder": "desc",
                    "criteriaObj": {"criteria": [{"name": "headline", "value": "Pillar 3"}],
                                    "dateCriteria": [{"name": "publication_date",
                                                      "value": {"from": f"{since}T00:00:00Z", "to": "2035-01-01T23:59:59Z"}}]}}
            try:
                r = self.session.post(NSM_API, json=body, timeout=90,
                                      headers={"Origin": "https://data.fca.org.uk", "Referer": "https://data.fca.org.uk/"})
                r.raise_for_status()
                self._nsm = [h["_source"] for h in r.json()["hits"]["hits"]]
            except Exception as exc:
                log.warning("NSM search failed: %s", exc)
                self._nsm = []
        return self._nsm

    def _download(self, url: str, entity_id: str) -> tuple[Path, str] | None:
        r = self.session.get(url, timeout=120)
        time.sleep(SLEEP)
        if r.status_code != 200 or not r.content.startswith(b"%PDF"):
            log.warning("%s: %s not a PDF (%s)", entity_id, url, r.status_code)
            return None
        sha = hashlib.sha256(r.content).hexdigest()
        p = self.cache / entity_id / f"{sha[:16]}.pdf"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(r.content)
        return p, sha

    def fetch(self, item: dict):
        """Returns a list of (entity_id, url, path, sha, hint_date, title, origin) for unseen PDFs."""
        work = []
        if item.get("kind") == "nsm-poll":
            lei_map = {e.lei: e for e in self.entities if e.lei}
            for s in self._nsm_hits():
                link = s.get("download_link") or ""
                if not link.lower().endswith(".pdf"):
                    continue
                ent = lei_map.get((s.get("lei") or "").strip())
                if not ent:
                    continue
                url = NSM_ARTEFACTS + link
                if url in self.seen:
                    continue
                if re.search(r"chart pack|remuneration|glossary", s.get("headline", ""), re.I):
                    continue
                loc = next((l for l in LOCATORS if l["entity"] == ent.id), {})
                hint = infer_period(s.get("headline", ""), loc.get("year_end", "12-31"))
                work.append((ent.id, url, None, None, hint, s.get("headline", "").strip(), "nsm"))
        elif item.get("kind", "html") == "html":
            new = [c for c in self._candidates(item) if c[0] not in self.seen][:MAX_NEW_PER_ENTITY]
            for url, hint, title in new:
                work.append((item["id"], url, None, None, hint, title, "site"))
        elif item.get("kind") == "pattern":
            found = 0
            for url, hint, title in self._pattern_candidates(item):
                if url in self.seen or found >= MAX_NEW_PER_ENTITY:
                    continue
                try:
                    r = self.session.get(url, timeout=60, stream=True)
                    ok = r.status_code == 200 and next(r.iter_content(5), b"").startswith(b"%PDF")
                    r.close()
                except Exception:
                    ok = False
                time.sleep(SLEEP)
                if ok:
                    work.append((item["id"], url, None, None, hint, title, "site"))
                    found += 1
        else:
            return None   # nsm-only and browser kinds are served by the NSM poll or the Mac skill
        out = []
        for ent, url, _, _, hint, title, origin in work:
            got = self._download(url, ent)
            if got:
                out.append((ent, url, got[0], got[1], hint, title, origin))
            else:
                self._record(ent, url, "", None, None, "error", 0.0, "download failed or not a PDF", title, origin, {})
        return out or None

    # ---- parse ----
    def parse(self, item, raw) -> list:
        results = []
        for ent, url, path, sha, hint, title, origin in raw:
            e = self.by_id[ent]
            loc = self._locator_for(ent, url)
            h = learn.hint_for(ent)
            ccy = loc.get("currency") or h.get("currency") or COUNTRY_CCY.get(e.country, "")
            try:
                res = self._extract(loc, str(path), hint, ccy, h)
            except Exception as exc:
                self._record(ent, url, sha, None, None, "error", 0.0, f"extract failed: {exc}", title, origin, {})
                continue
            results.append((ent, url, path, sha, title, origin, res))
        return results

    # ---- validate / load ----
    def validate(self, records: list) -> list:
        return records

    def load(self, records: list) -> int:
        n = 0
        for ent, url, path, sha, title, origin, res in records:
            checks = "; ".join(f"{s}:{m}" for s, m in res.checks)
            if not res.values:
                self._record(ent, url, sha, res.page, res.reference_date, "no_km1", 0.0, checks, title, origin, res.values, self.published_on(path))
                loc = self._locator_for(ent, url)
                hint = infer_period(title or url, loc.get("year_end", "12-31"))
                if (hint is None or hint >= date(2022, 1, 1)) and not learn.skip_matches(ent, url):
                    # A source the locator declares narrative has no KM1 by nature: the reviewer is
                    # being asked to read a capital table out of prose, not to explain a failure.
                    reason = loc.get("narrative") or "no KM1 template found"
                    review.add(self._queue_item(ent, url, path, sha, res, title, reason))
                continue
            if res.ok:
                status = "loaded" if res.confidence >= 0.9 else "unverified"
                # the reviewer's answers for this document outlive a re-read: rows the rules cannot reach stay,
                # and a rules value never overwrites a manual one on the same key
                held = store.read("facts")
                held = held[(held.document == url) & (held.method == "pdf_manual")] if not held.empty else held
                manual_keys = set(zip(held.entity_id, held.reference_date.astype(str).str[:10], held.metric, held.basis)) if not held.empty else set()
                fresh = [f for f in self._facts(ent, url, res) if (f.entity_id, f.reference_date.isoformat(), f.metric, f.basis) not in manual_keys]
                store.drop("facts", ne={"method": "pdf_manual"}, document=url, source=self.name)
                n += store.upsert("facts", fresh)
                review.remove((sha or hashlib.sha1(url.encode()).hexdigest())[:12])
                if status == "loaded" and res.reference_date:
                    learn.remember_verified(ent, res.reference_date, res.values)
            else:
                status = "review"
                review.add(self._queue_item(ent, url, path, sha, res, title, checks))
            self._record(ent, url, sha, res.page, res.reference_date, status, res.confidence, checks, title, origin, res.values, self.published_on(path))
        return n

    def process_file(self, entity_id: str, path: str, url: str = "", title: str = "", origin: str = "local") -> tuple[str, km1.Result]:
        """Extract and load one PDF already on disk (downloaded by hand or by a browser). Returns (status, result)."""
        data = Path(path).read_bytes()
        if not data.startswith(b"%PDF"):
            raise ValueError(f"{path} is not a PDF")
        sha = hashlib.sha256(data).hexdigest()
        cached = self.cache / entity_id / f"{sha[:16]}.pdf"
        cached.parent.mkdir(parents=True, exist_ok=True)
        if not cached.exists():
            cached.write_bytes(data)
        url = url or f"file:{Path(path).name}"
        e = self.by_id[entity_id]
        loc = next((l for l in LOCATORS if l["entity"] == entity_id), {})
        ccy = loc.get("currency") or COUNTRY_CCY.get(e.country, "")
        res = self._extract(loc, str(cached), infer_period(Path(path).name, loc.get("year_end", "12-31")), ccy)
        self.load([(entity_id, url, cached, sha, title or Path(path).name, origin, res)])
        row = self.docs = store.read("documents")
        status = row[row.url == url].status.iloc[-1] if not row.empty and (row.url == url).any() else "error"
        return status, res

    def reprocess(self, entity_id: str | None = None) -> dict:
        """Re-run extraction on every cached PDF (after an extractor change). Returns status counts."""
        docs = store.read("documents")
        counts: dict[str, int] = {}
        if docs.empty:
            return counts
        # Facts are replaced document by document as each cached PDF is re-read (load() drops a document's
        # facts before writing its new ones). Documents cached elsewhere, and reviewer answers, are left alone;
        # run `review ingest` afterwards so answers to items this pass re-queues are applied again.
        # oldest first, so the continuity baseline for each bank advances with its documents
        docs = docs.assign(_ref=docs.reference_date.fillna("9999")).sort_values(["entity_id", "_ref"])
        for r in docs.itertuples():
            if entity_id and r.entity_id != entity_id:
                continue
            if not r.sha256:
                continue
            path = self.cache / r.entity_id / f"{r.sha256[:16]}.pdf"
            if not path.exists():
                continue
            e = self.by_id.get(r.entity_id)
            loc = next((l for l in LOCATORS if l["entity"] == r.entity_id), {})
            ccy = loc.get("currency") or (COUNTRY_CCY.get(e.country, "") if e else "")
            hint = infer_period(r.title or "", loc.get("year_end", "12-31"))
            try:
                res = self._extract(self._locator_for(r.entity_id, r.url), str(path), hint, ccy, learn.hint_for(r.entity_id))
            except Exception as exc:
                self._record(r.entity_id, r.url, r.sha256, None, None, "error", 0.0, f"extract failed: {exc}", r.title, r.origin, {})
                counts["error"] = counts.get("error", 0) + 1
                continue
            if not res.ok:
                # a re-read that now fails must not take the reviewer's answers with it: those were
                # read by a person from this document and are the only figures it will ever yield
                store.drop("facts", ne={"method": "pdf_manual"}, document=r.url, source=self.name)
            self.load([(r.entity_id, r.url, path, r.sha256, r.title, r.origin, res)])
            status = "loaded" if res.ok and res.confidence >= 0.9 else "unverified" if res.ok else "review" if res.values else "no_km1"
            counts[status] = counts.get(status, 0) + 1
        return counts

    @staticmethod
    def _extract(loc: dict, path: str, hint, ccy: str, hints: dict | None = None) -> km1.Result:
        hints = hints or {}
        tpl = (loc or {}).get("template", "km1")
        if tpl == "us_capital":
            res = us.extract_capital(path, hint_date=hint)
        elif tpl == "us_lcr":
            res = us.extract_lcr(path, hint_date=hint)
        else:
            res = km1.extract(path, hint_date=hint, currency_hint=ccy, year_end=(loc or {}).get("year_end", "12-31"),
                              page_hint=hints.get("page"))
            if hints.get("trust_labels"):       # the reviewer confirmed this bank's table carries no row numbers
                res.checks = [c for c in res.checks if "label only" not in c[1]]
        # continuity with the last verified figures: agreement earns a little confidence, contradiction goes to review
        ent = (loc or {}).get("entity")
        if ent and res.values and res.fixed_confidence is None:
            verdict, msg = learn.continuity(ent, res.values, res.reference_date)
            if verdict == "ok":
                res.confidence_bonus = learn.CONTINUITY_BONUS
                res.checks.append(("info", msg))
            elif verdict == "contradiction":
                res.checks.append(("error", "disagrees with the last verified disclosure: " + msg))
        return res

    @staticmethod
    def published_on(path) -> str | None:
        """The date the document was produced, from the PDF's own creation stamp (the publication date, near
        enough, and months after the period it reports); None when the file carries no stamp."""
        try:
            import fitz
            m = fitz.open(str(path)).metadata or {}
            stamp = m.get("creationDate") or m.get("modDate") or ""
            mm = re.search(r"D:(\d{4})(\d{2})(\d{2})", stamp)
            if mm and 2000 <= int(mm.group(1)) <= date.today().year + 1:
                return f"{mm.group(1)}-{mm.group(2)}-{mm.group(3)}"
        except Exception:
            pass
        return None

    @staticmethod
    def _locator_for(entity_id: str, url: str = "") -> dict:
        """The locator that produced a document: match on URL when an entity has several."""
        cands = [l for l in LOCATORS if l["entity"] == entity_id]
        for l in cands:
            if url and (l.get("match") and re.search(l["match"], unquote(url), re.I) or any(u.split("{")[0] in url for u in l.get("urls", []))):
                return l
        return cands[0] if cands else {}

    def _facts(self, ent: str, url: str, res: km1.Result) -> list[Fact]:
        kinds = km1.KIND
        out = []
        for metric, value in res.values.items():
            if metric not in km1.PUBLISH:
                continue
            pct = kinds.get(metric) == "pct"
            out.append(Fact(entity_id=ent, reference_date=res.reference_date, metric=metric, value=float(value),
                            unit="pct" if pct else "ccy_m", currency="" if pct else res.currency,
                            basis="consolidated", source=self.name, document=url, page=res.page,
                            method="pdf_rules", confidence=res.confidence))
        # the template's earlier columns give history; they never replace a figure read from that period's own document
        if getattr(res, "history", None):
            have = store.read("facts")
            have = have[(have.entity_id == ent) & (have.source == self.name) & (have.method != "pdf_rules_prior")] if not have.empty else have
            taken = set(zip(have.reference_date.astype(str).str[:10], have.metric)) if not have.empty else set()
            for d, vals in res.history.items():
                if res.reference_date and d >= res.reference_date.isoformat():
                    continue
                for metric, value in vals.items():
                    if metric not in km1.PUBLISH or (d, metric) in taken:
                        continue
                    pct = kinds.get(metric) == "pct"
                    out.append(Fact(entity_id=ent, reference_date=date.fromisoformat(d), metric=metric, value=float(value),
                                    unit="pct" if pct else "ccy_m", currency="" if pct else res.currency,
                                    basis="consolidated", source=self.name, document=url, page=res.page,
                                    method="pdf_rules_prior", confidence=min(res.confidence, 0.85)))
        return out

    @staticmethod
    def _locator_for(ent: str, url: str) -> dict:
        """The locator this document actually came from, not merely the first one for the entity.

        An entity often has several - TSB has one for its quarterly disclosures and one for its
        annual report - and they say different things about what the document is.
        """
        for l in LOCATORS:
            if l["entity"] != ent:
                continue
            try:
                if re.search(l.get("match", ""), url, re.I):
                    return l
            except re.error:
                continue
        return next((l for l in LOCATORS if l["entity"] == ent), {})

    def _queue_item(self, ent, url, path, sha, res, title, reason) -> dict:
        return {"id": (sha or hashlib.sha1(url.encode()).hexdigest())[:12], "entity_id": ent, "url": url,
                "local": str(path.relative_to(store.DATA)) if path else "", "title": title,
                "page": res.page, "reference_date": res.reference_date.isoformat() if res.reference_date else None,
                "currency": res.currency, "values": res.values, "checks": res.checks, "reason": reason}

    def _record(self, ent, url, sha, page, ref, status, conf, message, title, origin, values, published: str | None = None) -> None:
        row = {"entity_id": ent, "url": url, "sha256": sha or "", "title": title, "origin": origin,
               "page": page, "reference_date": ref.isoformat() if ref else None, "status": status,
               "confidence": conf, "message": message[:500], "values": json.dumps(values, default=str),
               "fetched_at": datetime.utcnow().isoformat(timespec="seconds"), "published": published}
        store.upsert("documents", [row])
        self.seen.add(url)
