"""What the Python tests cannot see: the site as a browser actually runs it.

Three faults in one evening got past a green suite of unit tests, because all three lived in the
browser rather than in the pipeline - a closed dialog that stayed on the page, an empty-string
site root that sent every fetch one directory too high, and a template line that shipped its own
source instead of the value. Each is caught here in a line or two.

The site is served under a subdirectory, as GitHub Pages serves it, because that is the only way
the root-path fault shows up at all: from a server rooted at site/ the broken path still resolves.

Skipped, never failed, where the browser or the build is missing - these run on a machine with
Chromium and a built site, and the rest of the suite stands on its own without them.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import json
import socketserver
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
ASSETS = ROOT / "bankcredit" / "site" / "assets"
BASE = "/bankCredit/"                                   # the project subdirectory Pages publishes under

playwright_api = pytest.importorskip("playwright.sync_api", reason="playwright not installed")

CHROMIUM_FALLBACKS = ["/opt/pw-browsers/chromium-1194/chrome-linux/chrome"]


def _stale() -> str:
    """The browser tests only mean something against a build of the current source."""
    if not (SITE / "index.html").exists():
        return "site/ has not been built (python -m bankcredit.cli build)"
    for src in ASSETS.glob("*.js"):
        built = SITE / "assets" / src.name
        if not built.exists() or built.read_bytes() != src.read_bytes():
            return f"site/ is older than {src.name}; rebuild before running the browser tests"
    return ""


pytestmark = pytest.mark.skipif(bool(_stale()), reason=_stale() or "built site missing")


@pytest.fixture(scope="module")
def server():
    """Serve the built site one directory down, so a fetch that escapes the site 404s here too."""
    root = SITE.parent / ".browser-test-root"
    link = root / "bankCredit"
    root.mkdir(exist_ok=True)
    with contextlib.suppress(FileNotFoundError):
        link.unlink()
    link.symlink_to(SITE, target_is_directory=True)
    handler = functools.partial(_QuietHandler, directory=str(root))
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        yield f"http://127.0.0.1:{httpd.server_address[1]}{BASE}"
        httpd.shutdown()
    with contextlib.suppress(OSError):
        link.unlink()
        root.rmdir()


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):        # a passing run should print nothing
        pass


@pytest.fixture(scope="module")
def browser():
    with playwright_api.sync_playwright() as p:
        for path in [None, *CHROMIUM_FALLBACKS]:
            try:
                b = p.chromium.launch(executable_path=path) if path else p.chromium.launch()
                break
            except Exception:                                    # noqa: BLE001 - try the next one
                b = None
        if b is None:
            pytest.skip("no chromium available")
        yield b
        b.close()


@pytest.fixture
def page(browser):
    pg = browser.new_page(viewport={"width": 1440, "height": 900})
    pg.errors, pg.bad = [], []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    pg.on("response", lambda r: pg.bad.append(f"{r.status} {r.url}") if r.status >= 400 else None)
    yield pg
    pg.close()


def visit(pg, server, path):
    pg.goto(server + path, wait_until="networkidle")
    pg.wait_for_timeout(900)
    return pg


# ---- the data arrives at all ---------------------------------------------------------------
def test_home_loads_its_data_under_a_subdirectory(page, server):
    """The fault that emptied the live site: data-root="" is the root, not a missing root."""
    visit(page, server, "index.html")
    assert page.eval_on_selector_all("#uni-body tr", "e => e.length") > 50
    assert "Loading" not in page.inner_text("#policy-body")
    assert not page.errors, page.errors
    assert not page.bad, page.bad


def test_the_analysis_tab_loads_its_own_data(page, server):
    """Analysis is a tab now: its markup, its script and its 444 KB of data all wait for the click."""
    visit(page, server, "index.html")
    assert page.eval_on_selector_all("#cp-metric option", "e => e.length") == 0
    page.eval_on_selector('.tab[data-tab="analysis"]', "e => e.click()")
    page.wait_for_timeout(2500)
    assert page.eval_on_selector_all("#cp-metric option", "e => e.length") > 5
    assert page.eval_on_selector_all("#dash svg", "e => e.length") == 4
    # the tab keeps the state the panel writes after it, so a reload comes back here
    assert page.evaluate("location.hash").startswith("#analysis&")
    assert not page.errors, page.errors


def test_the_old_analysis_address_carries_on(page, server):
    visit(page, server, "compare/index.html")
    assert page.evaluate("location.pathname").endswith("index.html")
    assert page.eval_on_selector(".tab.active", "e => e.dataset.tab") == "analysis"


def test_a_profile_renders_its_figures(page, server):
    visit(page, server, "banks/barclays.html")
    assert "%" in page.inner_text(".tiles")
    assert page.eval_on_selector_all(".sm", "e => e.length") > 3
    assert not page.errors, page.errors


# ---- the dialog ------------------------------------------------------------------------------
def _open_first_bank(pg):
    pg.eval_on_selector("#uni-body tr", "e => e.click()")
    pg.wait_for_timeout(1200)


def test_a_closed_dialog_leaves_nothing_behind(page, server):
    """A dialog is display:none unless [open]; setting display on the element overrode that and
    left a dead copy of the last bank sitting in the page."""
    visit(page, server, "index.html")
    _open_first_bank(page)
    assert page.eval_on_selector("#pol-modal", "e => e.open")
    page.eval_on_selector("#md-close", "e => e.click()")
    page.wait_for_timeout(400)
    assert page.eval_on_selector("#pol-modal", "e => getComputedStyle(e).display") == "none"
    assert page.eval_on_selector("#pol-modal", "e => e.getBoundingClientRect().height") == 0


def test_clicking_outside_a_dialog_closes_it(page, server):
    visit(page, server, "index.html")
    _open_first_bank(page)
    page.mouse.click(20, 20)
    page.wait_for_timeout(300)
    assert not page.eval_on_selector("#pol-modal", "e => e.open")


def test_the_dialog_head_sits_on_one_centre_line(page, server):
    """A pill with a height needs a box that centres its text; an anchor was not one."""
    visit(page, server, "index.html")
    _open_first_bank(page)
    mids = page.evaluate("""() => ['#md-close', '.md-head a.filter', '.md-sc'].map(s => {
      const r = document.querySelector(s).getBoundingClientRect();
      return Math.round(r.top + r.height / 2);
    })""")
    assert max(mids) - min(mids) <= 2, mids


def test_the_dialog_is_built_from_panels(page, server):
    visit(page, server, "index.html")
    _open_first_bank(page)
    heads = page.eval_on_selector_all("#md-body .cp-cell > h5 > span:first-child",
                                      "e => e.map(x => x.textContent.trim())")
    assert len(heads) == 4, heads
    assert page.query_selector("#md-body .cr-scale") or page.query_selector("#md-body .cp-rt-none")
    assert not page.errors, page.errors


def test_an_event_in_the_dialog_shows_its_whole_headline(page, server):
    """A dialog paints in the top layer, so a tooltip left on the body sits behind it."""
    visit(page, server, "index.html")
    _open_first_bank(page)
    row = page.query_selector("#md-body .md-news > div[data-tip]")
    if row is None:
        pytest.skip("the first bank has no events")
    headline = page.eval_on_selector("#md-body .md-news > div[data-tip] .hd", "e => e.textContent.trim()")
    row.hover()
    page.wait_for_timeout(350)
    tip = page.evaluate("""() => {
      const t = document.querySelector('.dtip');
      return {host: t.parentElement.tagName, hidden: t.hidden, text: t.textContent || ''};
    }""")
    assert tip["host"] == "DIALOG" and not tip["hidden"], tip
    assert headline[:40] in tip["text"], tip["text"]


def test_the_dialog_fills_from_the_detail_file(page, server):
    visit(page, server, "index.html")
    _open_first_bank(page)
    body = page.inner_text("#md-body")
    assert "Loading" not in body and len(body) > 200
    assert not page.bad, page.bad


# ---- the marks explain themselves ------------------------------------------------------------
def test_a_chart_mark_carries_a_tooltip(page, server):
    visit(page, server, "index.html")
    mark = page.query_selector(".pv-charts [data-tip]")
    if mark is None:
        pytest.skip("no policy stored in this browser, so the overview charts are not drawn")
    mark.hover()
    page.wait_for_timeout(350)
    assert len(page.inner_text(".dtip")) > 20


def test_a_definition_marker_opens_a_definition(page, server):
    visit(page, server, "index.html")
    page.eval_on_selector(".uni th .i", "e => e.click()")
    page.wait_for_timeout(300)
    assert len(page.inner_text(".tip")) > 40


# ---- an open counterparty card ---------------------------------------------------------------
# The card only exists once a policy is stored, so nothing else in the suite ever draws one. Its
# marks are absolutely positioned against a track they must stay inside, which is a browser fact.
def _seed(pg, server):
    """Approve the first name that exercises every mark, and leave its card closed."""
    rows = json.loads((SITE / "data" / "policy.json").read_text(encoding="utf-8"))["rows"]
    pick = next((r for r in rows
                 if r.get("score") is not None and len(r.get("ratings") or []) > 1
                 and (r.get("market_detail") or {}).get("bond_change30") is not None), None)
    if pick is None:
        pytest.skip("no covered name carries a score, two ratings and a bond signal")
    policy = [{"id": pick["id"], "tenor": 365, "added": "2026-01-01",
               "base": {"score": pick["score"], "band": pick["band"], "grade": pick["rating_grade"]}}]
    pg.goto(server + "index.html", wait_until="domcontentloaded")
    pg.evaluate("v => localStorage.setItem('counterparty.policy', v)", json.dumps(policy))
    visit(pg, server, "index.html")
    return pick


def _seed_and_open(pg, server):
    """The card opened in place once; everything it held is in the dialog now."""
    pick = _seed(pg, server)
    pg.eval_on_selector(".pol-card", "e => e.click()")
    pg.wait_for_timeout(700)
    return pick


def _seed_many(pg, server, n=6):
    """Approve the first n scored names, so the list has something to lay out."""
    rows = json.loads((SITE / "data" / "policy.json").read_text(encoding="utf-8"))["rows"]
    pick = [r for r in rows if r.get("score") is not None][:n]
    policy = [{"id": r["id"], "tenor": 365, "added": "2026-01-01",
               "base": {"score": r["score"], "band": r["band"], "grade": r["rating_grade"]}} for r in pick]
    pg.goto(server + "index.html", wait_until="domcontentloaded")
    pg.evaluate("v => localStorage.setItem('counterparty.policy', v)", json.dumps(policy))
    visit(pg, server, "index.html")
    return policy


@pytest.mark.parametrize(("width", "columns"), [(1440, 2), (1180, 1)])
def test_the_list_runs_in_two_columns_where_there_is_room(browser, server, width, columns):
    """A council with forty names wants them two abreast; a narrow window still gets one."""
    pg = browser.new_page(viewport={"width": width, "height": 900})
    try:
        _seed_many(pg, server)
        tops = pg.eval_on_selector_all(".pol-card", "e => e.map(c => Math.round(c.getBoundingClientRect().top))")
        assert len(tops) - len(set(tops)) == (len(tops) // 2 if columns == 2 else 0)
    finally:
        pg.close()


@pytest.mark.parametrize("width", [1920, 1440, 1280, 900, 560, 390])
def test_the_figures_stay_inside_their_card(browser, server, width):
    """Below the fold width the figures take the line beneath the name rather than the pavement."""
    pg = browser.new_page(viewport={"width": width, "height": 900})
    try:
        _seed_many(pg, server)
        over = pg.eval_on_selector_all(".pol-card", """e => e.map(c => {
          const s = c.querySelector('.cp-stats').getBoundingClientRect(), r = c.getBoundingClientRect();
          return Math.round(Math.max(s.right - r.right, r.left - s.left));
        })""")
        assert max(over) <= 0, f"figures overflow the card by {max(over)}px at {width}px"
    finally:
        pg.close()


@pytest.mark.parametrize("width", [1440, 1100, 900, 560])
def test_the_closed_row_keeps_remove_on_the_name_line(browser, server, width):
    """A grid rule meant for another row put remove in column three, on a row of its own."""
    pg = browser.new_page(viewport={"width": width, "height": 900})
    try:
        _seed(pg, server)
        box = pg.evaluate("""() => {
          const top = document.querySelector('.pol-card .cp-top');
          const r = e => e.getBoundingClientRect();
          return {rm: r(top.querySelector('.pol-rm')).top, name: r(top.querySelector('.cp-id')).bottom};
        }""")
        assert box["rm"] < box["name"], f"remove dropped below the name at {width}px"
    finally:
        pg.close()


def test_a_counterparty_is_one_line(page, server):
    """The card carried six figures and an expander holding five more panels, all of which the
    dialog now shows on a click. What is left is the name, what it is worth, what it is rated and
    how long you accept it for."""
    _seed_many(page, server, 4)
    assert page.eval_on_selector_all(".cp-exp, .cp-detail", "e => e.length") == 0
    labels = page.eval_on_selector_all(".pol-card .ck > span", "e => e.map(x => x.textContent.trim())")
    assert set(labels) == {"score", "rating"}, labels
    assert page.eval_on_selector(".pol-card", "e => e.getBoundingClientRect().height") < 100
    page.eval_on_selector(".pol-card", "e => e.click()")
    page.wait_for_timeout(700)
    assert page.evaluate("!!document.querySelector('dialog[open]')")
    assert not page.errors, page.errors


def test_the_tenor_can_be_changed_on_a_name_already_approved(page, server):
    """It was printed as if it were a fact about the bank. It is the one thing on the row that is
    the treasurer's own decision, and changing it meant removing the name and adding it again."""
    policy = _seed_many(page, server, 3)
    first = policy[0]["id"]
    sel = f'.pol-card[data-id="{first}"] .cp-ten select'
    assert page.eval_on_selector(sel, "e => e.value") == "365"
    page.select_option(sel, "1825")
    page.wait_for_timeout(500)
    stored = json.loads(page.evaluate("localStorage.getItem('counterparty.policy')"))
    assert [x["tenor"] for x in stored if x["id"] == first] == [1825]
    # the row is redrawn from what was stored, and the click did not open the dialog behind it
    assert page.eval_on_selector(sel, "e => e.value") == "1825"
    assert not page.evaluate("!!document.querySelector('dialog[open]')")
    assert not page.errors, page.errors


def test_every_mark_stays_inside_its_own_track(page, server):
    """left:100% on a 10px dot hangs half of it outside the panel; the scales clamp instead."""
    _seed_and_open(page, server)
    stray = page.evaluate("""() => {
      const out = [];
      const check = (mark, track, what) => {
        const m = mark.getBoundingClientRect(), t = track.getBoundingClientRect();
        if (m.left < t.left - 6 || m.right > t.right + 6) out.push(what);
      };
      document.querySelectorAll('dialog .cr-scale').forEach(t =>
        t.querySelectorAll('.cr-dot,.cr-c').forEach(m => check(m, t, 'rating ' + m.className)));
      return out;
    }""")
    assert stray == [], stray


# ---- the page fits the screen ----------------------------------------------------------------
@pytest.mark.parametrize("path", ["index.html", "compare/index.html", "banks/barclays.html"])
@pytest.mark.parametrize("width", [1440, 390])
def test_no_page_scrolls_sideways(browser, server, path, width):
    pg = browser.new_page(viewport={"width": width, "height": 900})
    try:
        pg.goto(server + path, wait_until="networkidle")
        pg.wait_for_timeout(800)
        over = pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        assert over <= 1, f"{path} at {width}px overflows by {over}px"
    finally:
        pg.close()


def test_every_asset_the_page_names_carries_the_build():
    """New HTML with yesterday's script is how a tab arrived with nothing behind it."""
    html = (SITE / "index.html").read_text(encoding="utf-8")
    for ref in ("assets/site.css", "assets/app.js", "assets/policy.js",
                "data/panels/analysis.html", "assets/compare.js"):
        assert f'{ref}?v=' in html, f"{ref} is named without the build it belongs to"


# ---- something is always on screen while something is on its way ------------------------------
def test_the_page_opens_on_a_skeleton_not_a_word(page, server):
    """A slow connection used to get the word "Loading" in grey; it gets the shape now."""
    html = (SITE / "index.html").read_text(encoding="utf-8")
    assert 'class="sk-cards"' in html and "sk-tr" in html
    assert "Loading" not in html
    visit(page, server, "index.html")
    assert page.eval_on_selector_all(".sk", "e => e.length") == 0, "the skeleton outstayed the data"


def test_nothing_speculative_starts_before_the_list_is_drawn(page, server):
    """Warming from the load event took the pipe: on a throttled line the list itself went from
    two seconds to six, because 430 KB of panels nobody had asked for were downloading first."""
    _seed_many(page, server, 4)
    # measured in the page, at the instant the first card lands: asking from here would be a
    # round trip later, by which time the warming has run whatever the order was
    page.goto(server + "index.html", wait_until="commit")
    early = page.evaluate("""async () => {
      let w = 0;
      while (!document.querySelector('.pol-card') && w < 20000) { await new Promise(r => setTimeout(r, 8)); w += 8; }
      return performance.getEntriesByType('resource').map(e => e.name)
        .filter(n => n.includes('/panels/') || n.includes('/detail/'));
    }""")
    assert early == [], f"speculative fetches began before the list: {early}"
    page.wait_for_timeout(2500)
    late = page.evaluate("""() => performance.getEntriesByType('resource')
        .map(e => e.name).filter(n => n.includes('/panels/'))""")
    assert late, "the panels were never warmed"


def test_a_heavy_panel_is_warmed_before_it_is_asked_for(page, server):
    """The bytes arrive on an idle browser; only the building waits for the click."""
    seen = []
    page.on("response", lambda r: seen.append(r.url.rsplit("/", 1)[-1].split("?")[0]))
    visit(page, server, "index.html")
    page.wait_for_timeout(2500)
    assert "ratings.html" in seen and "events.html" in seen
    assert page.eval_on_selector_all("#board tbody tr", "e => e.length") == 0, "warming should not build"
    page.eval_on_selector('.tab[data-tab="ratings"]', "e => e.click()")
    page.wait_for_timeout(400)
    assert page.eval_on_selector_all("#board tbody tr", "e => e.length") > 20


# ---- tabs, not one long page -----------------------------------------------------------------
def test_the_policy_page_is_tabs(page, server):
    """The approved names ran the length of the page with the shortlist under them."""
    _seed_many(page, server, 4)
    tabs = page.eval_on_selector_all(".tabs-card .tab", "e => e.map(x => x.dataset.tab)")
    assert tabs == ["policy", "likeforlike", "universe", "ratings", "events", "analysis"]
    assert page.eval_on_selector_all('[data-panel="policy"] .pol-card', "e => e.length") == 4
    assert page.eval_on_selector("#tn-policy", "e => e.textContent") == "4"
    page.eval_on_selector('.tab[data-tab="likeforlike"]', "e => e.click()")
    page.wait_for_timeout(400)
    drawn = page.eval_on_selector_all("#pol-ll .ll-r", "e => e.length")
    assert drawn > 0
    # a shortlist of like things is a table: the same eight figures in the same eight places
    assert page.eval_on_selector_all("#pol-ll table.ll-t2", "e => e.length") == 1
    heads = page.eval_on_selector_all("#pol-ll .ll-t2 thead th", "e => e.map(x => x.textContent.trim())")
    named = [h for h in heads if h]
    assert named[0] == "Name" and named[1].startswith("Score"), heads
    assert named[2:6] == ["Rating", "CET1", "LEV", "LCR"], heads
    # the count on the tab is every distinct name the shortlist turns up, so never fewer than one
    # tenor's worth of cards
    assert int(page.eval_on_selector("#tn-ll", "e => e.textContent")) >= drawn
    assert not page.errors, page.errors


def test_the_shortlist_shows_one_tenor_at_a_time(page, server):
    """Four tenors ran down one page, each list defined by what the one above had already used."""
    rows = json.loads((SITE / "data" / "policy.json").read_text(encoding="utf-8"))["rows"]
    pick = [r for r in rows if r.get("score") is not None][:3]
    if len(pick) < 3:
        pytest.skip("not enough scored names to seed three tenors")
    policy = [{"id": r["id"], "tenor": t, "added": "2026-01-01",
               "base": {"score": r["score"], "band": r["band"], "grade": r["rating_grade"]}}
              for r, t in zip(pick, (90, 365, 730))]
    page.goto(server + "index.html", wait_until="domcontentloaded")
    page.evaluate("v => localStorage.setItem('counterparty.policy', v)", json.dumps(policy))
    visit(page, server, "index.html")
    page.eval_on_selector('.tab[data-tab="likeforlike"]', "e => e.click()")
    page.wait_for_timeout(400)
    chips = page.eval_on_selector_all("#pol-ll .ll-t", "e => e.map(x => x.dataset.t)")
    assert chips == ["730", "365", "90"], chips
    shown = page.eval_on_selector_all("#pol-ll .ll-pane:not([hidden])", "e => e.map(x => x.dataset.t)")
    assert shown == ["730"], "one tenor is on screen, not all of them"
    # a shorter tenor accepts a weaker name, so its list can only be the longer one's or larger
    counts = page.eval_on_selector_all("#pol-ll .ll-t .cnt", "e => e.map(x => +x.textContent)")
    assert counts == sorted(counts), counts
    page.eval_on_selector('#pol-ll .ll-t[data-t="90"]', "e => e.click()")
    page.wait_for_timeout(200)
    assert page.eval_on_selector_all("#pol-ll .ll-pane:not([hidden])", "e => e.map(x => x.dataset.t)") == ["90"]
    assert page.eval_on_selector_all("#pol-ll .ll-t.active", "e => e.map(x => x.dataset.t)") == ["90"]
    assert page.eval_on_selector_all("#pol-ll .ll-pane:not([hidden]) .ll-r", "e => e.length") > 0
    assert not page.errors, page.errors


# ---- the rating history the register publishes ------------------------------------------------
def _with_history():
    """A bank whose profile carries a rebuilt rating history, or a reason to skip."""
    for f in sorted((SITE / "data" / "detail").glob("*.json")):
        b = json.loads(f.read_text(encoding="utf-8"))
        h = b.get("rating_history") or {}
        if len(h.get("composite") or []) >= 2:
            return f.stem
    pytest.skip("no rating history in this build (python -m bankcredit.cli ratings-history)")


def test_a_profile_draws_the_ratings_it_held_and_the_tone_under_them(page, server):
    """Five step lines on one notch axis was spaghetti: most banks live inside two notches, so the
    agencies sat on top of each other and the composite disappeared beneath them."""
    who = _with_history()
    visit(page, server, f"banks/{who}.html")
    page.eval_on_selector('.tab[data-tab="ratings"]', "e => e.click()")
    page.wait_for_timeout(300)
    assert page.eval_on_selector_all(".ladder", "e => e.length") == 1
    # one line only, and it is a step rather than a line drawn between two points
    paths = page.eval_on_selector_all(".ladder path", "e => e.map(x => x.getAttribute('d'))")
    steps = [d for d in paths if "H" in d]
    assert len(steps) == 1, paths
    # a block per rating held, each one carrying the dates it was held between
    blocks = page.eval_on_selector_all(".ladder g title", "e => e.map(x => x.textContent)")
    assert sum(1 for t in blocks if " from " in t) >= 2, blocks
    assert any("outlook from" in t for t in blocks), "the outlook is the point of the second layer"
    assert page.eval_on_selector_all(".rl-key .rl-k", "e => e.length") >= 5
    assert page.eval_on_selector_all(".rh-list li", "e => e.length") >= 1
    assert not page.errors, page.errors


def test_the_dialog_carries_the_path_the_composite_took(page, server):
    who = _with_history()
    rows = json.loads((SITE / "data" / "policy.json").read_text(encoding="utf-8"))["rows"]
    r = next((x for x in rows if x["id"] == who), None)
    if r is None:
        pytest.skip("that name is not on the policy list")
    policy = [{"id": who, "tenor": 365, "added": "2026-01-01",
               "base": {"score": r["score"], "band": r["band"], "grade": r["rating_grade"]}}]
    page.goto(server + "index.html", wait_until="domcontentloaded")
    page.evaluate("v => localStorage.setItem('counterparty.policy', v)", json.dumps(policy))
    visit(page, server, "index.html")
    page.eval_on_selector(".pol-card", "e => e.click()")
    page.wait_for_timeout(700)
    assert page.eval_on_selector_all("dialog .rp", "e => e.length") == 1
    assert "since 20" in page.eval_on_selector("dialog .rp-t", "e => e.textContent")
    assert not page.errors, page.errors


def test_the_profile_links_to_its_own_rating_history(page, server):
    """"All ratings" pointed at a page that had been retired, so it landed the reader back on the
    policy page with no rating history anywhere on the site."""
    who = _with_history()
    visit(page, server, f"banks/{who}.html")
    href = page.eval_on_selector(".tile-ratings .tile-foot a", "e => e.getAttribute('href')")
    assert href == "#ratings", href
    page.eval_on_selector(".tile-ratings .tile-foot a", "e => e.click()")
    page.wait_for_timeout(400)
    assert page.eval_on_selector_all(".panel.active", "e => e.map(x => x.dataset.panel)") == ["ratings"]
    assert page.eval_on_selector_all(".ladder", "e => e.length") == 1
    assert not page.errors, page.errors


def test_the_ratings_grid_plots_the_register_not_our_snapshots(page, server):
    """The last column plotted the composite on each daily build. Snapshots began four days
    earlier, so all 152 rows carried the same flat line and the same "4d"."""
    visit(page, server, "index.html")
    page.eval_on_selector('.tab[data-tab="ratings"]', "e => e.click()")
    page.wait_for_timeout(900)
    heads = page.eval_on_selector_all("#board thead th", "e => e.map(x => x.textContent.trim())")
    assert heads[-1].startswith("Path"), heads
    # one column per agency that rates a meaningful share, then one for all the rest
    assert "KBRA" not in heads and "Scope" not in heads, heads
    paths = page.eval_on_selector_all("#board tbody td:last-child", "e => e.map(x => x.textContent.trim())")
    assert sum(1 for p in paths if "notch" in p or p == "flat") > 40, paths[:6]
    assert not any("4d" in p for p in paths)
    assert not page.errors, page.errors


# ---- the home page is not the whole universe three times over --------------------------------
def test_the_home_page_stays_small():
    """Two tabs nobody had clicked were 426 KB of the home page's 441 KB."""
    kb = (SITE / "index.html").stat().st_size / 1024
    assert kb < 60, f"index.html is {kb:.0f} KB; the heavy panels belong in data/panels"
    for name in ("ratings", "events"):
        assert (SITE / "data" / "panels" / f"{name}.html").exists()


@pytest.mark.parametrize(("tab", "rows"), [("ratings", "#board tbody tr"), ("events", "#events .event")])
def test_a_deferred_panel_fills_and_still_filters(page, server, tab, rows):
    visit(page, server, "index.html")
    assert page.eval_on_selector_all(rows, "e => e.length") == 0
    page.eval_on_selector(f'.tab[data-tab="{tab}"]', "e => e.click()")
    page.wait_for_timeout(900)
    assert page.eval_on_selector_all(rows, "e => e.length") > 20
    # the wiring runs again on arrival, so the panel's own filters work
    button = page.query_selector(".gfilter" if tab == "ratings" else "#event-filters button:nth-child(2)")
    assert button is not None
    button.click()
    page.wait_for_timeout(300)
    shown = page.eval_on_selector_all(rows, "e => e.filter(x => !x.hidden && x.style.display !== 'none').length")
    assert 0 < shown < page.eval_on_selector_all(rows, "e => e.length")
    assert not page.errors, page.errors
    assert not page.bad, page.bad


# ---- nothing ships its own source ------------------------------------------------------------
@pytest.mark.parametrize("name", ["index.html", "compare/index.html", "admin/index.html", "banks/barclays.html"])
def test_no_page_ships_an_unrendered_placeholder(name):
    """A plain string where an f-string was meant puts {c.info("rating")} on the page as text."""
    html = (SITE / name).read_text(encoding="utf-8")
    for tell in ['{c.', '{e.', '{esc(', 'None</', '>undefined<']:
        assert tell not in html, f"{name} contains {tell!r}"
