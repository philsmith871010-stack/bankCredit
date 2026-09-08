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


def test_the_analysis_page_loads_its_own_data(page, server):
    visit(page, server, "compare/index.html")
    assert page.eval_on_selector_all("#cp-metric option", "e => e.length") > 5
    assert not page.errors, page.errors


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


# ---- nothing ships its own source ------------------------------------------------------------
@pytest.mark.parametrize("name", ["index.html", "compare/index.html", "admin/index.html", "banks/barclays.html"])
def test_no_page_ships_an_unrendered_placeholder(name):
    """A plain string where an f-string was meant puts {c.info("rating")} on the page as text."""
    html = (SITE / name).read_text(encoding="utf-8")
    for tell in ['{c.', '{e.', '{esc(', 'None</', '>undefined<']:
        assert tell not in html, f"{name} contains {tell!r}"
