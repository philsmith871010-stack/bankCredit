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


def candidates(loc: dict, body: str, links: list[str], adapter: Pillar3Adapter) -> list[tuple[str, date | None, str]]:
    """Links on a listing page (from its HTML and from the rendered DOM) that match the locator, newest first."""
    mrx = re.compile(loc["match"], re.I)
    xrx = re.compile(loc["exclude"], re.I) if loc.get("exclude") else None
    seen, found = set(), []
    for u in adapter._links(loc["page"], body) + [urljoin(loc["page"], l) for l in links]:
        u = u.split("#")[0]
        d = unquote(u)
        if u in seen or not mrx.search(d) or (xrx and xrx.search(d)) or re.search(r"\.(jpg|png|gif|svg|css|js|xlsx?|docx?)(\?|$)", d, re.I):
            continue
        seen.add(u)
        ye = loc.get("year_end", "12-31")
        found.append((u, infer_period(d.rsplit("/", 1)[-1], ye) or infer_period(d, ye), d.rsplit("/", 1)[-1][:120]))
    found.sort(key=lambda x: (x[1] or date(1900, 1, 1)), reverse=True)
    return found


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

    def listing(self, url: str) -> tuple[int, str, list[str]]:
        ctx = self.open()
        if not ctx:
            return 0, "", []
        page = ctx.new_page()
        try:
            r = page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)                       # script-built lists and cookie banners settle
            status = r.status if r else 0
            body = page.content()
            links = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
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
        cands = [c for c in candidates(loc, body, links, ad) if c[0] not in ad.seen][:max_new]
        if not cands:
            out[ent] = "nothing new" if any(c[0] in ad.seen for c in candidates(loc, body, links, ad)) else "no matching links"
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
        out[ent] = f"collected {n}" if n else "download failed"
    browser.close()
    return out
