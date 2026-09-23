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

from bankcredit.site.build import HOME_TABS_HIDDEN

# Two tabs are held back while their scope is settled. Their tests go with them rather than being
# deleted: flipping the flag in build.py brings back the coverage along with the pages.
held = lambda tab: pytest.mark.skipif(tab in HOME_TABS_HIDDEN,
                                      reason=f"the {tab} tab is held back; see HOME_TABS_HIDDEN")

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
    assert "names" in page.inner_text("#uni-count2")
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
    # three panels: where the names stand today, where the measure has been, how the order moved
    assert page.eval_on_selector_all("#dash svg", "e => e.length") == 3
    assert page.query_selector("#cp-metric2") is None, "the second measure and its bubble chart are gone"
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


@pytest.mark.parametrize(("width", "columns"), [(1600, 4), (1100, 3), (760, 2), (420, 1)])
def test_the_list_runs_in_as_many_columns_as_fit(browser, server, width, columns):
    """A council holds plenty of names and a row is now only a name, a score, a rating and a
    tenor, so it takes about 300px: four abreast on a desk, one on a phone."""
    pg = browser.new_page(viewport={"width": width, "height": 900})
    try:
        _seed_many(pg, server, 8)
        lefts = pg.eval_on_selector_all(".pol-card", "e => e.map(c => Math.round(c.getBoundingClientRect().left))")
        assert len(set(lefts)) == columns, sorted(set(lefts))
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
    assert set(labels) == {"score", "agency rating"}, labels
    # a row in a column of four, matched to the tallest card beside it; the open card was 400
    assert page.eval_on_selector(".pol-card", "e => e.getBoundingClientRect().height") < 130
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
    assert "analysis.html" in seen
    assert page.eval_on_selector_all("#cp-metric option", "e => e.length") == 0, "warming should not build"
    page.eval_on_selector('.tab[data-tab="analysis"]', "e => e.click()")
    page.wait_for_timeout(2000)
    assert page.eval_on_selector_all("#cp-metric option", "e => e.length") > 0


# ---- tabs, not one long page -----------------------------------------------------------------
def test_the_policy_page_is_tabs(page, server):
    """The approved names ran the length of the page with the shortlist under them."""
    _seed_many(page, server, 4)
    tabs = page.eval_on_selector_all(".tabs-card .tab", "e => e.map(x => x.dataset.tab)")
    expected = [t for t in ["policy", "likeforlike", "ratings", "events", "analysis"] if t not in HOME_TABS_HIDDEN]
    assert tabs == expected
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
    assert named[2:6] == ["Agency rating", "CET1", "LEV", "LCR"], heads
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


def test_a_profile_draws_the_average_the_weakest_and_the_tones_and_names_no_agency(page, server):
    """The ladder used to carry a band per agency. It now carries the average of the three main
    agencies as one step line, the weakest of them dashed beneath, and a lane counting how many
    of the three held each outlook or watch: nothing on it says which agency said what."""
    who = _with_history()
    visit(page, server, f"banks/{who}.html")
    page.eval_on_selector('.tab[data-tab="ratings"]', "e => e.click()")
    page.wait_for_timeout(300)
    assert page.eval_on_selector_all(".ladder", "e => e.length") == 1
    # two step lines: the average, and the weakest
    assert page.eval_on_selector_all(".ladder path.avg", "e => e.length") == 1
    assert page.eval_on_selector_all(".ladder path.worst", "e => e.length") <= 1
    d = page.eval_on_selector(".ladder path.avg", "e => e.getAttribute('d')")
    assert "H" in d and "V" in d or "H" in d, d
    titles = page.eval_on_selector_all(".ladder title", "e => e.map(x => x.textContent)")
    assert any(t.startswith("average ") and " from " in t for t in titles), titles
    assert any(t.startswith("rated by ") for t in titles), "the tone lane says how many held each outlook"
    panel = page.eval_on_selector('.panel[data-panel="ratings"]', "e => e.textContent")
    for name in ("Fitch", "Moody", "S&P", "DBRS"):
        assert panel.count(name) == (1 if name in ("Fitch", "Moody", "S&P") else 0), \
            f"{name} appears only in the note saying which three agencies are averaged"
    assert page.eval_on_selector_all(".rl-key .rl-k", "e => e.length") >= 6
    assert page.eval_on_selector_all(".rh-list li", "e => e.length") >= 1
    moves = page.eval_on_selector_all(".rh-list li", "e => e.map(x => x.textContent)")
    assert all("one of the three" in m for m in moves), moves
    assert not page.errors, page.errors


def test_nothing_published_names_an_agency_against_a_rating(server):
    """The JSON the pages read carries the average, the weakest and the tones, and no agency key."""
    policy = json.loads((SITE / "data" / "policy.json").read_text(encoding="utf-8"))
    for r in policy["rows"]:
        assert "ratings" not in r and "short_ratings" not in r, r["id"]
        if r.get("rating"):
            assert set(r["rating"]) == {"n", "avg", "worst", "letter", "worst_letter", "tones", "date"}, r["rating"]
    for sv in policy["sovereigns"].values():
        assert "agencies" not in sv
    for f in list((SITE / "data" / "detail").glob("*.json"))[:20]:
        text = f.read_text(encoding="utf-8")
        assert '"agency"' not in text and "ratings_all" not in text, f.name
        for e in json.loads(text).get("events") or []:
            if e.get("type") == "rating":
                assert e["title"].startswith("One of the three agencies"), e


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


def test_the_rating_history_lives_on_the_ratings_tab_and_the_tile_stays_clean(page, server):
    """The ratings tile used to end in a "Rating history" link. The tile is the summary; the
    history is one tab away and is not advertised on the tile."""
    who = _with_history()
    visit(page, server, f"banks/{who}.html")
    assert page.eval_on_selector_all(".tile-ratings a", "e => e.length") == 0, "no link on the tile"
    page.eval_on_selector('.tab[data-tab="ratings"]', "e => e.click()")
    page.wait_for_timeout(400)
    assert page.eval_on_selector_all(".panel.active", "e => e.map(x => x.dataset.panel)") == ["ratings"]
    assert page.eval_on_selector_all(".ladder", "e => e.length") == 1
    assert not page.errors, page.errors


@held("ratings")
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


# ---- a shared link opens on something ---------------------------------------------------------
def test_a_first_visit_opens_empty_on_the_table_it_chooses_from(page, server):
    """The page used to open on an example list, a box of the strongest names and a histogram
    with nothing on it. It opens on an instruction and the whole covered universe, sortable,
    filterable and addable, and nothing else is pushed at the reader."""
    visit(page, server, "index.html")
    page.wait_for_timeout(1000)
    assert page.eval_on_selector_all(".pol-card", "e => e.length") == 0
    assert "Your list is empty" in page.inner_text(".pol-empty")
    assert page.eval_on_selector_all(".pe-top, .pe-fig, .pol-form, #pol-name", "e => e.length") == 0
    assert page.eval_on_selector("#uni-open", "e => e.textContent") == "Choose from every covered name"
    page.eval_on_selector("#uni-open", "e => e.click()")
    page.wait_for_timeout(300)
    assert page.eval_on_selector("#uni-dlg", "e => e.open"), "the table opens over the page"
    assert page.eval_on_selector_all("#uni-body tr.uni-row", "e => e.length") > 100
    page.eval_on_selector("#uni-close", "e => e.click()")
    page.wait_for_timeout(200)
    # nothing was laid in the browser behind the reader's back
    assert page.evaluate("localStorage.getItem('counterparty.policy')") in (None, "[]")
    # the example is one link away, and says it is an example
    page.eval_on_selector("#pol-demo", "e => e.click()")
    page.wait_for_timeout(600)
    assert page.eval_on_selector_all(".pol-card", "e => e.length") >= 12
    assert page.eval_on_selector_all(".pol-demo", "e => e.length") == 1
    page.eval_on_selector("#pol-demo-x", "e => e.click()")
    page.wait_for_timeout(400)
    assert page.eval_on_selector_all(".pol-card", "e => e.length") == 0
    visit(page, server, "index.html")
    page.wait_for_timeout(900)
    assert page.eval_on_selector_all(".pol-card", "e => e.length") == 0, "cleared stays cleared"
    assert not page.errors, page.errors


def test_the_table_opens_over_the_page_from_the_add_names_button(page, server):
    """With names held the page leads with them; the table is one blue button away, beside the
    Cards and Table switch, and opens over the page rather than under the list."""
    _seed_many(page, server, 3)
    assert not page.eval_on_selector("#uni-dlg", "e => e.open")
    assert page.eval_on_selector("#uni-open", "e => e.textContent") == "Add names"
    assert page.eval_on_selector("#uni-open", "e => e.closest('.pol-summary') !== null"), "up beside the view switch"
    assert page.eval_on_selector("#uni-open", "e => getComputedStyle(e).backgroundColor") == "rgb(42, 120, 214)"
    page.eval_on_selector("#uni-open", "e => e.click()")
    page.wait_for_timeout(300)
    assert page.eval_on_selector("#uni-dlg", "e => e.open")
    # a name held shows as such in the table, and the chip pulls the held names out on their own
    assert page.eval_on_selector_all("#uni-body tr.uni-mine", "e => e.length") == 3
    page.eval_on_selector('#uni-chips [data-uf="mine"]', "e => e.click()")
    page.wait_for_timeout(300)
    assert page.eval_on_selector_all("#uni-body tr.uni-row", "e => e.length") == 3
    page.eval_on_selector('#uni-chips [data-uf="top"]', "e => e.click()")
    page.wait_for_timeout(300)
    assert page.eval_on_selector_all("#uni-body tr.uni-row", "e => e.length") == 5, "the five strongest standings"
    # an add from the open table does not fold it: the reader is choosing several
    page.eval_on_selector('#uni-chips [data-uf="top"]', "e => e.click()")
    page.wait_for_timeout(300)
    page.eval_on_selector("#uni-body tr.uni-row:not(.uni-mine) .pol-add-ll", "e => e.click()")
    page.wait_for_timeout(500)
    assert page.eval_on_selector_all(".pol-card", "e => e.length") == 4
    assert page.eval_on_selector("#uni-dlg", "e => e.open"), "an add does not close the table"
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    assert not page.eval_on_selector("#uni-dlg", "e => e.open")
    assert not page.errors, page.errors


def test_the_weightings_come_first_and_change_in_a_dialog(page, server):
    """The score is the reader's arithmetic, so what it rests on is the first thing on the page."""
    visit(page, server, "index.html")
    page.wait_for_timeout(900)
    top = page.eval_on_selector("#wt-line", "e => e.getBoundingClientRect().top")
    tabs = page.eval_on_selector(".tabs-card", "e => e.getBoundingClientRect().top")
    assert top < tabs
    line = page.inner_text("#wt-vals")
    assert "agency rating" in line and "%" in line and "starting point" in line
    page.eval_on_selector("#wt-change", "e => e.click()")
    page.wait_for_timeout(300)
    assert page.eval_on_selector("#wt-dlg", "e => e.open")
    page.eval_on_selector("#wt-rating", "e => { e.value = 0; e.dispatchEvent(new Event('input', {bubbles: true})) }")
    page.wait_for_timeout(400)
    page.eval_on_selector("#wt-close", "e => e.click()")
    page.wait_for_timeout(200)
    assert not page.eval_on_selector("#wt-dlg", "e => e.open")
    assert "set by you" in page.inner_text("#wt-vals")
    assert not page.errors, page.errors


def test_a_name_is_watched_from_the_table_and_listed_under_the_portfolio(page, server):
    """Watching lived only on the profile, and Analysis then offered a set nobody knew how to
    fill. The star is on every row of the table now, and the names followed sit under the list."""
    _seed_many(page, server, 2)
    page.eval_on_selector("#uni-open", "e => e.click()")
    page.wait_for_timeout(300)
    assert page.eval_on_selector_all("#pol-watch", "e => e.length") == 0
    who = page.eval_on_selector("#uni-body tr.uni-row:not(.uni-mine)", "e => e.dataset.id")
    page.eval_on_selector(f'#uni-body tr[data-id="{who}"] .uni-star', "e => e.click()")
    page.wait_for_timeout(400)
    assert json.loads(page.evaluate("localStorage.getItem('counterparty.watch')")) == [who]
    assert page.eval_on_selector_all(f'#pol-watch tr[data-id="{who}"]', "e => e.length") == 1
    assert page.eval_on_selector(f'#uni-body tr[data-id="{who}"] .uni-star', "e => e.classList.contains('on')")
    page.eval_on_selector('#uni-chips [data-uf="watch"]', "e => e.click()")
    page.wait_for_timeout(300)
    assert page.eval_on_selector_all("#uni-body tr.uni-row", "e => e.map(x => x.dataset.id)") == [who]
    # the profile's star reads the same list
    visit(page, server, f"banks/{who}.html")
    assert page.eval_on_selector(".watch, .watch-btn", "e => e.classList.contains('on')")
    # adding a watched name to the list is the stronger form of attention, so it leaves the watch list
    visit(page, server, "index.html")
    page.wait_for_timeout(900)
    page.eval_on_selector(f'#pol-watch tr[data-id="{who}"] .pol-add-ll', "e => e.click()")
    page.wait_for_timeout(500)
    assert page.eval_on_selector_all(".pol-card", "e => e.length") == 3
    assert json.loads(page.evaluate("localStorage.getItem('counterparty.watch')")) == []
    assert page.eval_on_selector_all("#pol-watch", "e => e.length") == 0
    assert not page.errors, page.errors


def test_names_on_the_same_spot_of_the_tenor_chart_become_one_marker(page, server):
    """Two dots on top of each other could only speak for the one on top."""
    _seed_many(page, server, 6)               # six names at 12 months, scores within a few points
    assert page.eval_on_selector_all(".pv-n", "e => e.length") >= 1
    assert sum(int(x) for x in page.eval_on_selector_all(".pv-n", "e => e.map(x => x.textContent)")) + \
        page.eval_on_selector_all("figure:has(.pv-n) circle[r='4.5']", "e => e.length") == 6
    assert not page.errors, page.errors


def test_a_definition_opened_by_hovering_closes_when_the_pointer_leaves(page, server):
    """It stayed until it was clicked away, and a reader who had only brushed a mark was stuck with it."""
    visit(page, server, "index.html")
    page.wait_for_timeout(900)
    page.hover("#wt-line .i")
    page.wait_for_timeout(400)
    assert not page.eval_on_selector(".tip", "e => e.hidden")
    page.mouse.move(600, 700)
    page.wait_for_timeout(400)
    assert page.eval_on_selector(".tip", "e => e.hidden"), "a hover-opened box goes when the pointer does"
    page.click("#wt-line .i")
    page.wait_for_timeout(300)
    page.mouse.move(600, 700)
    page.wait_for_timeout(400)
    assert not page.eval_on_selector(".tip", "e => e.hidden"), "a clicked box stays"
    assert not page.errors, page.errors


def test_a_three_letter_composite_fits_its_chip(page, server):
    """The composite was drawn in a box sized for a two-character grade; AAA and BBB+ were clipped."""
    for who in ("nwb-bank", "bng-bank", "barclays", "lloyds-banking-group"):
        visit(page, server, f"banks/{who}.html")
        w = page.eval_on_selector(".tile-ratings .band", "e => [e.scrollWidth, e.clientWidth, e.textContent]")
        assert w[0] <= w[1], (who, w)
    assert not page.errors, page.errors


def test_a_name_added_to_the_analysis_set_can_be_removed_again(page, server):
    """The cross on its chip only unpinned it; the name stayed in every panel in grey."""
    visit(page, server, "index.html#analysis")
    page.wait_for_timeout(1800)
    page.fill("#cp-q", "monzo")
    page.wait_for_timeout(300)
    page.eval_on_selector("#cp-sugg button", "e => e.click()")
    page.wait_for_timeout(600)
    assert page.eval_on_selector_all('#c-table tr[data-id="monzo"]', "e => e.length") == 1
    assert page.eval_on_selector_all('.pinchip-x[data-id="monzo"] .cp-rmx', "e => e.length") == 1
    assert "unpin" in page.inner_text("#cp-pins") and "Added to the set" in page.inner_text("#cp-pins")
    page.eval_on_selector('.cp-rmx[data-id="monzo"]', "e => e.click()")
    page.wait_for_timeout(500)
    assert page.eval_on_selector_all('#c-table tr[data-id="monzo"]', "e => e.length") == 0
    assert page.eval_on_selector_all('.dash [data-id="monzo"], #c-table [data-id="monzo"], #cp-pins [data-id="monzo"]', "e => e.length") == 0, "gone from every panel"
    assert not page.errors, page.errors


def test_no_typeface_is_preloaded_ahead_of_the_data(page, server):
    """50 KB of Inter in the same queue as the 18 KB the list is drawn from cost a second on a
    slow line, and every face carries font-display:swap, so nothing waits to be readable."""
    html = (SITE / "index.html").read_text(encoding="utf-8")
    assert 'as="font"' not in html, "a typeface is preloaded ahead of the data again"
    assert "font-display:swap" in (SITE / "assets" / "site.css").read_text(encoding="utf-8")


# ---- whose judgement the score is -------------------------------------------------------------
def test_the_starting_weights_reproduce_the_published_score(page, server):
    """The browser recomputes every score from the pillar sub-scores. Left alone it must agree with
    what the pipeline published, to the decimal, or the weighting panel is quietly rewriting the
    site rather than handing it over."""
    visit(page, server, "index.html")
    page.wait_for_timeout(900)
    off = page.evaluate("""() => fetch('data/policy.json').then(r => r.json()).then(j => {
      const w = window.CPW.weights();
      return j.rows.filter(e => e.score != null)
        .map(e => [e.id, e.score, window.CPW.rescore(e, w).score])
        .filter(([id, was, now]) => Math.abs(was - now) > 0.05);
    })""")
    assert off == [], off[:5]


def test_a_weight_the_reader_sets_moves_every_score_on_the_site(page, server):
    _seed_many(page, server, 3)
    page.eval_on_selector("#wt-change", "e => e.click()")
    page.wait_for_timeout(400)
    assert page.eval_on_selector_all(".wt-s", "e => e.map(x => x.dataset.k)") == [
        "capital", "liquidity", "asset_quality", "profitability", "stability", "rating"]
    before = page.eval_on_selector_all(".pol-card .ck-score b", "e => e.map(x => x.textContent.trim())")
    page.eval_on_selector("#wt-rating", "e => { e.value = 0; e.dispatchEvent(new Event('input', {bubbles: true})) }")
    page.wait_for_timeout(600)
    page.eval_on_selector("#wt-close", "e => e.click()")
    page.wait_for_timeout(300)
    after = page.eval_on_selector_all(".pol-card .ck-score b", "e => e.map(x => x.textContent.trim())")
    assert after != before, (before, after)
    assert json.loads(page.evaluate("localStorage.getItem('counterparty.weights')"))["rating"] == 0
    assert not page.errors, page.errors


def test_the_panel_says_what_this_is_not(page, server):
    visit(page, server, "index.html")
    page.eval_on_selector("#wt-change", "e => e.click()")
    page.wait_for_timeout(400)
    said = page.eval_on_selector(".wt-foot", "e => e.textContent").lower()
    for phrase in ("not a credit rating", "not advice", "the judgement is yours",
                   "credit rating agency regulations"):
        assert phrase in said, phrase


def test_a_profile_shows_the_readers_weights_not_ours(page, server):
    """A profile is built once for everyone, so it carries the starting weights in its HTML. It has
    to follow the reader's, or the number on the name disagrees with the number on the list."""
    visit(page, server, "banks/barclays.html")
    built = page.eval_on_selector(".score-fig .huge", "e => e.textContent")
    assert page.eval_on_selector_all(".score-yours", "e => e.length") == 0, "nothing to say by default"
    page.evaluate("""localStorage.setItem('counterparty.weights', JSON.stringify(
        {capital: 60, liquidity: 15, asset_quality: 5, profitability: 5, stability: 10, rating: 5}))""")
    visit(page, server, "banks/barclays.html")
    assert page.eval_on_selector(".score-fig .huge", "e => e.textContent") != built
    assert page.eval_on_selector(".score-yours", "e => e.textContent") == "your weights"
    assert "w 60" in page.eval_on_selector_all(".pillar .pw", "e => e.map(x => x.textContent)")
    assert not page.errors, page.errors


# ---- the home page is not the whole universe three times over --------------------------------
def test_the_home_page_stays_small():
    """Two tabs nobody had clicked were 426 KB of the home page's 441 KB."""
    kb = (SITE / "index.html").stat().st_size / 1024
    assert kb < 60, f"index.html is {kb:.0f} KB; the heavy panels belong in data/panels"
    for name in ("ratings", "events"):
        fragment = SITE / "data" / "panels" / f"{name}.html"
        if name in HOME_TABS_HIDDEN:
            assert not fragment.exists(), "a tab that is held back publishes nothing, not even a fragment"
        else:
            assert fragment.exists()


@pytest.mark.parametrize(("tab", "rows"), [
    pytest.param("ratings", "#board tbody tr", marks=held("ratings")),
    pytest.param("events", "#events .event", marks=held("events"))])
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


# ---- long lists stand a page at a time -------------------------------------------------------
@held("events")
def test_a_long_feed_stands_a_page_at_a_time(page, server):
    """Three hundred events rendered at once was thirty thousand pixels, and the oldest was
    unreachable. The rows are all in the page; only a page of them stands on it."""
    visit(page, server, "index.html")
    page.eval_on_selector('.tab[data-tab="events"]', "e => e.click()")
    page.wait_for_timeout(900)
    held = page.eval_on_selector_all("#events .event", "e => e.length")
    assert held > 100, "the feed still carries every event it was built with"
    shown = lambda: page.eval_on_selector_all("#events .event", "e => e.filter(x => !x.hidden).length")
    first = shown()
    assert 0 < first < held, "only a page of them is on screen"
    assert f"{first} of {held}" in page.inner_text("#ev-more")
    page.eval_on_selector("#ev-more .more", "e => e.click()")
    page.wait_for_timeout(300)
    assert shown() > first, "the control reveals the next page"
    assert not page.errors, page.errors


@held("events")
def test_a_change_of_filter_starts_the_list_at_the_top_again(page, server):
    """Otherwise a reader who has paged deep into 'All' meets a filtered list already exhausted."""
    visit(page, server, "index.html")
    page.eval_on_selector('.tab[data-tab="events"]', "e => e.click()")
    page.wait_for_timeout(900)
    step = page.eval_on_selector("#ev-more", "e => +e.dataset.step")
    page.eval_on_selector("#ev-more .more", "e => e.click()")
    page.wait_for_timeout(250)
    page.eval_on_selector("#event-filters button:nth-child(2)", "e => e.click()")
    page.wait_for_timeout(300)
    shown = page.eval_on_selector_all("#events .event", "e => e.filter(x => !x.hidden).length")
    assert shown <= step, "the reveal count resets when what qualifies changes"
    assert not page.errors, page.errors


def test_the_shortlist_opens_on_a_tenor_that_has_something_to_show(page, server):
    """The longest tenor is the strictest; on a strong list nothing clears it, and the tab used to
    open on a page whose whole content was a sentence saying there was nothing to show."""
    rows = json.loads((SITE / "data" / "policy.json").read_text(encoding="utf-8"))["rows"]
    pick = [r for r in rows if r.get("score") is not None]
    if len(pick) < 3:
        pytest.skip("not enough scored names")
    best, mid = pick[0], pick[len(pick) // 2]          # the strongest name at the longest tenor
    policy = [{"id": r["id"], "tenor": t, "added": "2026-01-01",
               "base": {"score": r["score"], "band": r["band"], "grade": r["rating_grade"]}}
              for r, t in ((best, 1825), (mid, 365))]
    page.goto(server + "index.html", wait_until="domcontentloaded")
    page.evaluate("v => localStorage.setItem('counterparty.policy', v)", json.dumps(policy))
    visit(page, server, "index.html")
    page.eval_on_selector('.tab[data-tab="likeforlike"]', "e => e.click()")
    page.wait_for_timeout(500)
    counts = page.eval_on_selector_all("#pol-ll .ll-t", "e => e.map(x => +x.querySelector('.cnt').textContent)")
    active = page.eval_on_selector_all("#pol-ll .ll-t.active", "e => e.map(x => +x.querySelector('.cnt').textContent)")
    if any(counts):
        assert active and active[0] > 0, "the open tenor is one that turns something up"
    assert not page.errors, page.errors


# ---- the tables a reader sorts and scans scroll in a window ----------------------------------
def test_a_long_table_scrolls_in_its_own_window(page, server):
    """Paging a sorted list meant clicking through sixteen pages to read it, and the column
    headings left the screen on the way. Every row is here; the window is what moves."""
    visit(page, server, "index.html#universe")
    page.wait_for_timeout(700)
    rows = page.eval_on_selector_all("#uni-body tr", "e => e.length")
    assert rows > 100, "the whole list is in the page, not a page of it"
    box = page.eval_on_selector("#uni-body", """e => {
      const b = e.closest('.scrollbox');
      return b ? [Math.round(b.clientHeight), Math.round(b.scrollHeight)] : null }""")
    assert box, "the table sits in a scrolling window"
    assert box[1] > box[0] * 2, f"the window is shorter than what it holds: {box}"
    # and the page itself stays short
    assert page.evaluate("document.documentElement.scrollHeight") < 1800
    assert "scroll for the rest" in page.inner_text("#uni-count2")
    assert not page.errors, page.errors


def test_the_column_headings_stay_while_the_rows_move(page, server):
    """A heading that scrolls away takes the meaning of every column with it."""
    visit(page, server, "index.html#universe")
    page.wait_for_timeout(700)
    top = page.eval_on_selector("#uni-table thead th", "e => Math.round(e.getBoundingClientRect().top)")
    page.eval_on_selector("#uni-body", "e => { e.closest('.scrollbox').scrollTop = 1400 }")
    page.wait_for_timeout(250)
    moved = page.eval_on_selector("#uni-body tr", "e => Math.round(e.getBoundingClientRect().top)")
    after = page.eval_on_selector("#uni-table thead th", "e => Math.round(e.getBoundingClientRect().top)")
    assert abs(after - top) <= 2, f"the heading moved from {top} to {after}"
    assert moved < top, "the rows did move"
    assert not page.errors, page.errors


def test_the_shortlist_shows_every_name_that_clears_the_bar(page, server):
    """It used to stop at the 24 strongest, so the rest were unreachable at any tenor."""
    rows = json.loads((SITE / "data" / "policy.json").read_text(encoding="utf-8"))["rows"]
    weak = [r for r in rows if r.get("score") is not None][-40:]
    if len(weak) < 2:
        pytest.skip("not enough scored names")
    policy = [{"id": r["id"], "tenor": t, "added": "2026-01-01",
               "base": {"score": r["score"], "band": r["band"], "grade": r["rating_grade"]}}
              for r, t in zip(weak[:2], (365, 90))]      # two tenors, so the chips carry counts
    page.goto(server + "index.html", wait_until="domcontentloaded")
    page.evaluate("v => localStorage.setItem('counterparty.policy', v)", json.dumps(policy))
    visit(page, server, "index.html")
    page.eval_on_selector('.tab[data-tab="likeforlike"]', "e => e.click()")
    page.wait_for_timeout(600)
    drawn = page.eval_on_selector_all(".ll-pane:not([hidden]) .ll-r", "e => e.length")
    counted = page.eval_on_selector(".ll-t.active .cnt", "e => +e.textContent")
    assert drawn == counted, f"the chip counts {counted} and the table draws {drawn}"
    assert page.query_selector(".ll-pane:not([hidden]) .scrollbox"), "and it scrolls in a window"
    assert not page.errors, page.errors


# ---- the policy as a table, and plain tables that sort ---------------------------------------
def test_the_policy_can_be_read_as_a_table_and_sorted(page, server):
    """A policy of twenty names is a column of figures to some readers and a set of cards to
    others; the choice is theirs, kept, and the table sorts on any column."""
    _seed_many(page, server, 4)
    page.eval_on_selector("#pol-view-table", "e => e.click()")
    page.wait_for_timeout(400)
    assert page.eval_on_selector_all("#pol-table tbody tr.pol-tr", "e => e.length") == 4
    assert page.eval_on_selector_all('[data-panel="policy"] .pol-card', "e => e.length") == 0
    heads = page.eval_on_selector_all("#pol-table thead th", "e => e.map(x => x.textContent.trim())")
    assert heads[:9] == ["Name", "Score", "Agency rating", "CET1", "Lev", "LCR", "NSFR", "Figures", "News 30d"], heads
    page.eval_on_selector('#pol-table th[data-k="score"]', "e => e.click()")
    page.wait_for_timeout(300)
    scores = page.eval_on_selector_all("#pol-table tbody tr.pol-tr td:nth-child(2)", "e => e.map(x => parseFloat(x.textContent))")
    assert scores == sorted(scores, reverse=True), scores
    page.eval_on_selector('#pol-table th[data-k="score"]', "e => e.click()")
    page.wait_for_timeout(300)
    scores = page.eval_on_selector_all("#pol-table tbody tr.pol-tr td:nth-child(2)", "e => e.map(x => parseFloat(x.textContent))")
    assert scores == sorted(scores), scores
    page.reload(wait_until="networkidle"); page.wait_for_timeout(900)
    assert page.eval_on_selector_all("#pol-table tbody tr.pol-tr", "e => e.length") == 4, "the choice is kept"
    page.eval_on_selector("#pol-view-cards", "e => e.click()")
    page.wait_for_timeout(300)
    assert page.eval_on_selector_all('[data-panel="policy"] .pol-card', "e => e.length") == 4
    assert not page.errors, page.errors


def test_a_profiles_metrics_table_sorts_on_its_headings(page, server):
    visit(page, server, "banks/barclays-bank.html")
    page.eval_on_selector('.tab[data-tab="sources"]', "e => e.click()")
    page.wait_for_timeout(300)
    page.eval_on_selector('table.sortable th[data-sortable]:nth-child(2)', "e => e.click()")
    page.wait_for_timeout(200)
    vals = page.eval_on_selector_all("table.sortable tbody tr td:nth-child(2)", "e => e.map(x => parseFloat(x.textContent.replace(/,/g,'')))")
    assert len(vals) > 5 and vals == sorted(vals), vals
    assert not page.errors, page.errors


def test_a_profiles_flagged_events_come_first(page, server):
    visit(page, server, "banks/barclays-bank.html")
    page.eval_on_selector('.tab[data-tab="events"]', "e => e.click()")
    page.wait_for_timeout(300)
    sev = page.eval_on_selector_all("#pevents .event .chip", "e => e.map(x => x.textContent.trim())")
    flagged = [s for s in sev if s in ("bad", "warn", "good")]
    assert sev[:len(flagged)] == flagged, "every flagged event precedes every unflagged one"
    assert page.eval_on_selector_all("#pevents .ev-divider", "e => e.length") == (1 if flagged and len(flagged) < len(sev) else 0)


# ---- the universe's column chooser ---------------------------------------------------------
def test_more_columns_can_be_brought_into_the_universe_table_and_stay(page, server):
    """The four ratios a policy is written around are always there; the rest of what is held
    comes in on request, sortable, and the choice is kept."""
    visit(page, server, "index.html#universe")
    page.wait_for_timeout(1500)
    assert page.eval_on_selector_all("#uni-table thead th.uni-x", "e => e.length") == 0
    page.eval_on_selector("#uni-cols-btn", "e => e.click()")
    page.wait_for_timeout(200)
    assert not page.eval_on_selector("#uni-cols-menu", "e => e.hidden")
    page.eval_on_selector('#uni-cols-menu input[data-col="roe"]', "e => e.click()")
    page.wait_for_timeout(400)
    heads = page.eval_on_selector_all("#uni-table thead th", "e => e.map(x => x.textContent.trim())")
    fig = [i for i, h in enumerate(heads) if h.startswith("Figures")][0]     # the heading carries its info mark
    assert "ROE" in heads and heads.index("ROE") < fig, heads
    page.eval_on_selector('#uni-table th[data-sort="roe"]', "e => e.click()")
    page.wait_for_timeout(300)
    first = page.eval_on_selector("#uni-body tr:first-child td.uni-x", "e => e.textContent.trim()")
    assert first not in ("", "—"), "sorted on the new column, the first row has a figure"
    page.reload(wait_until="networkidle"); page.wait_for_timeout(1500)
    assert page.eval_on_selector_all("#uni-table thead th.uni-x", "e => e.length") == 1, "the choice is kept"
    assert not page.errors, page.errors
    assert not page.bad, page.bad


def test_a_long_name_never_widens_the_page_on_a_phone(browser, server):
    pg = browser.new_page(viewport={"width": 400, "height": 800})
    try:
        pg.goto(server + "banks/coventry-bs.html", wait_until="networkidle"); pg.wait_for_timeout(600)
        assert not pg.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth + 1"), "the page scrolls sideways"
    finally:
        pg.close()


def test_every_modal_softens_the_page_behind_it(page, server):
    """A box over a page that stays sharp is a box on a busy page."""
    visit(page, server, "index.html")
    page.wait_for_timeout(900)
    blur = page.evaluate("""() => {
      const s = [...document.styleSheets].flatMap(ss => { try { return [...ss.cssRules] } catch (e) { return [] } });
      const r = s.find(r => r.selectorText === 'dialog::backdrop');
      return r ? r.style.backdropFilter || r.style.getPropertyValue('backdrop-filter') : null }""")
    assert blur and "blur" in blur, blur
    assert not page.errors, page.errors
