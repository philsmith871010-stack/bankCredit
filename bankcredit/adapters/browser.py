"""Collect Pillar 3 documents from the sites that block scripted fetches (locators marked kind="browser").

Meant for the maintainer's Mac, on a residential connection, in three escalating steps:

  1. a plain request with a full browser header set: several "blocked" sites only reject data-centre
     addresses and unknown user agents;
  2. a headless Chromium (Playwright) with a persistent profile, which renders script-built PDF lists and
     passes the lighter bot checks;
  3. whatever is still blocked is reported by name, for the Claude-in-Chrome extension run by the review skill.

Every PDF found goes through Pillar3Adapter.process_file, so extraction, validation, the review queue and the
documents table behave exactly as for the pipeline's own collection. No AI service is involved.

    python -m bankcredit.cli browser [entity ...]      # BANKCREDIT_NO_PLAYWRIGHT=1 keeps to step 1
"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from datetime import date
from pathlib import Path
from urllib.parse import unquote, urljoin

import requests

from .. import store
from .pillar3 import MAX_NEW_PER_ENTITY, Pillar3Adapter, infer_period
from .pillar3_locators import LOCATORS

log = logging.getLogger("bankcredit.browser")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9", "Accept-Encoding": "gzip, deflate, br", "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Site": "none", "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}
CHALLENGE = re.compile(r"just a moment|cf-chl|challenge-platform|access denied|request unsuccessful|incapsula|akamai|"
                       r"bot detection|verify you are human|enable javascript and cookies", re.I)
PROFILE = store.DATA / "cache" / "browser-profile"


def looks_blocked(status: int, body: str) -> bool:
    return status != 200 or len(body) < 1500 or bool(CHALLENGE.search(body[:20000]))


GENERIC = re.compile(r"pillar[-_ %]?(?:3|iii)|basel[-_ %]?(?:3|iii).*disclos", re.I)
GENERIC_EXCLUDE = re.compile(r"gsib|g-sib|indicator|tlac|remuneration|glossary|appendix|chinese|-cn\b|template|policy|terms", re.I)
LINKS_SEEN = store.DATA / "review" / "browser-links.json"


def _pairs(body: str, links: list, adapter: Pillar3Adapter, page_url: str) -> list[tuple[str, str]]:
    """(url, anchor text) for every link on the page, HTML-scraped and DOM-rendered alike."""
    out, seen = [], set()
    for l in links:
        href, text = (l[0], l[1]) if isinstance(l, (list, tuple)) else (l, "")
        u = urljoin(page_url, href).split("#")[0]
        if u not in seen:
            seen.add(u); out.append((u, text))
    for u in adapter._links(page_url, body):
        u = u.split("#")[0]
        if u not in seen:
            seen.add(u); out.append((u, ""))
    return out


def candidates(loc: dict, body: str, links: list, adapter: Pillar3Adapter, generic: bool = False) -> list[tuple[str, date | None, str]]:
    """Links on a listing page that match the locator, newest first. With generic=True the locator's own
    pattern is set aside and anything that looks like a Pillar 3 document (by URL or by link text) is taken."""
    mrx = re.compile(loc["match"], re.I)
    xrx = re.compile(loc["exclude"], re.I) if loc.get("exclude") else None
    found = []
    for u, text in _pairs(body, links, adapter, loc["page"]):
        d = unquote(u)
        if re.search(r"\.(jpg|png|gif|svg|css|js|xlsx?|docx?|zip)(\?|$)", d, re.I):
            continue
        if generic:
            ok = (GENERIC.search(d) or GENERIC.search(text)) and not GENERIC_EXCLUDE.search(d + " " + text) \
                 and (d.lower().endswith(".pdf") or ".pdf" in d.lower() or re.search(r"download|document|media|file", d, re.I) or GENERIC.search(text))
        else:
            ok = mrx.search(d) and not (xrx and xrx.search(d))
        if not ok:
            continue
        ye = loc.get("year_end", "12-31")
        name = d.rsplit("/", 1)[-1][:120] or text[:120]
        found.append((u, infer_period(name, ye) or infer_period(d, ye) or infer_period(text, ye), name if name else text[:120]))
    found.sort(key=lambda x: (x[1] or date(1900, 1, 1)), reverse=True)
    return found


def remember_links(entity: str, body: str, links: list, adapter: Pillar3Adapter, page_url: str) -> None:
    """Keep the document-looking links a page offered, so a locator pattern can be tuned without a browser."""
    try:
        seen = json.loads(LINKS_SEEN.read_text()) if LINKS_SEEN.exists() else {}
    except Exception:
        seen = {}
    docs = [{"url": u, "text": t} for u, t in _pairs(body, links, adapter, page_url)
            if re.search(r"\.pdf|download|document|disclos|pillar|basel|report", u + " " + t, re.I)][:60]
    seen[entity] = {"page": page_url, "checked": date.today().isoformat(), "links": docs}
    LINKS_SEEN.parent.mkdir(parents=True, exist_ok=True)
    LINKS_SEEN.write_text(json.dumps(seen, indent=1, ensure_ascii=False))


class Browser:
    """One headless Chromium with a persistent profile, opened lazily and shared across sites."""

    def __init__(self):
        self.ctx = None
        self.pw = None
        self.error = None

    def open(self):
        if self.ctx or self.error:
            return self.ctx
        try:
            from playwright.sync_api import sync_playwright
            self.pw = sync_playwright().start()
            PROFILE.mkdir(parents=True, exist_ok=True)
            exe = os.environ.get("BANKCREDIT_CHROMIUM") or None      # a system Chromium instead of Playwright's own build
            self.ctx = self.pw.chromium.launch_persistent_context(str(PROFILE), headless=True, user_agent=HEADERS["User-Agent"],
                                                                  viewport={"width": 1366, "height": 900}, locale="en-GB",
                                                                  executable_path=exe)
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            log.warning("browser: Playwright unavailable (%s); pip install playwright && playwright install chromium", exc)
        return self.ctx

    def listing(self, url: str) -> tuple[int, str, list]:
        ctx = self.open()
        if not ctx:
            return 0, "", []
        page = ctx.new_page()
        try:
            r = page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)                       # script-built lists and cookie banners settle
            status = r.status if r else 0
            body = page.content()
            links = page.eval_on_selector_all("a[href]", "els => els.map(e => [e.href, (e.textContent || '').trim().slice(0, 120)])")
            return status, body, links
        except Exception as exc:
            log.warning("browser: %s -> %s", url, exc)
            return 0, "", []
        finally:
            page.close()

    def download(self, url: str) -> bytes | None:
        ctx = self.open()
        if not ctx:
            return None
        try:
            r = ctx.request.get(url, timeout=120000, headers={"Accept": "application/pdf,*/*"})
            data = r.body() if r.ok else None
            return data if data and data.startswith(b"%PDF") else None
        except Exception as exc:
            log.warning("browser: download %s -> %s", url, exc)
            return None

    def close(self):
        try:
            if self.ctx:
                self.ctx.close()
            if self.pw:
                self.pw.stop()
        except Exception:
            pass


def collect(entity_ids: list[str] | None = None, max_new: int = MAX_NEW_PER_ENTITY) -> dict:
    """Try every browser-kind locator. Returns {entity_id: outcome} where outcome is 'collected n',
    'nothing new', 'no matching links', or 'blocked' (needs the Chrome extension)."""
    ad = Pillar3Adapter()
    session = requests.Session()
    session.headers.update(HEADERS)
    use_pw = not os.environ.get("BANKCREDIT_NO_PLAYWRIGHT")
    browser = Browser()
    out: dict[str, str] = {}
    locs = [l for l in LOCATORS if l.get("kind") == "browser" and (not entity_ids or l["entity"] in entity_ids)]
    for loc in locs:
        ent = loc["entity"]
        body, links, via = "", [], "request"
        try:
            r = session.get(loc["page"], timeout=60)
            if not looks_blocked(r.status_code, r.text):
                body = r.text
        except requests.RequestException as exc:
            log.info("browser: %s plain request failed (%s)", ent, exc)
        if not body and use_pw:
            status, body, links = browser.listing(loc["page"])
            via = "playwright"
            if looks_blocked(status, body):
                body = ""
        if not body:
            out[ent] = "blocked" if (use_pw and not browser.error) else "blocked (no Playwright)"
            continue
        remember_links(ent, body, links, ad, loc["page"])
        allc = candidates(loc, body, links, ad)
        how = "locator"
        if not allc:
            allc = candidates(loc, body, links, ad, generic=True)
            how = "generic"
        cands = [c for c in allc if c[0] not in ad.seen][:max_new]
        if not cands:
            out[ent] = "nothing new" if allc else "no matching links (see data/review/browser-links.json)"
            continue
        n = 0
        for url, _hint, title in cands:
            data = None
            try:
                rr = session.get(url, timeout=120)
                if rr.status_code == 200 and rr.content.startswith(b"%PDF"):
                    data = rr.content
            except requests.RequestException:
                pass
            if data is None and via == "playwright":
                data = browser.download(url)
            if data is None:
                log.warning("browser: %s could not fetch %s", ent, url)
                continue
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False, prefix=title[:40].replace("/", "_") + "_") as tmp:
                tmp.write(data)
            try:
                status, _res = ad.process_file(ent, tmp.name, url, title, origin="browser")
                log.info("browser: %s %s -> %s", ent, title, status)
                n += 1
            finally:
                Path(tmp.name).unlink(missing_ok=True)
        out[ent] = (f"collected {n}" + (" (generic match)" if how == "generic" else "")) if n else "download failed"
    browser.close()
    return out
