"""Every asset the pages fetch has to resolve under a project subpath.

The site is published at /bankCredit/, not at a domain root, so a fetch that
walks up out of the page's directory leaves the site. The home page carries
data-root="", which is falsy in JavaScript: reading it with `||` sent every
fetch to ../ and broke the whole page on Pages while it kept working against a
local server rooted at site/.
"""

import re
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "bankcredit" / "site" / "assets"


def test_root_is_read_without_a_falsy_test():
    for js in ASSETS.glob("*.js"):
        src = js.read_text(encoding="utf-8")
        for line in src.splitlines():
            if "data-root" not in line and "dataset.root" not in line:
                continue
            assert "||" not in line, f"{js.name}: an empty data-root is the site root, not a missing one"


def test_every_fetch_starts_from_the_resolved_root():
    """A path may only be relative to the page's own root, never written into the call."""
    for js in ASSETS.glob("*.js"):
        src = js.read_text(encoding="utf-8")
        for call in re.findall(r"fetch\(\s*(.{0,4})", src):
            assert not call.startswith(("'../", '"../', "'/", '"/')), f"{js.name}: fetch({call}...) is not root-relative"


def test_the_home_page_declares_the_site_root():
    build = (Path(__file__).resolve().parent.parent / "bankcredit" / "site" / "build.py").read_text(encoding="utf-8")
    assert 'data-root=""' in build
