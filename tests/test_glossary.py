"""Every definition the site points at has to exist, and be worth reading.

The markers are written by hand in three places - the page builder, the policy script and the
compare script - so the keys drift silently unless something checks them against the glossary.
"""

import re
from pathlib import Path

from bankcredit.site import glossary

ROOT = Path(__file__).resolve().parent.parent / "bankcredit" / "site"


def test_every_term_is_placed_in_a_section():
    ordered = glossary.ordered()
    assert [k for _, k in ordered] == sorted({k for _, k in ordered}, key=[k for _, k in ordered].index)
    assert set(glossary.TERMS) == {k for _, k in ordered}


def test_every_definition_answers_in_one_sentence():
    for key, (title, short, rest) in glossary.TERMS.items():
        assert title and not title.endswith("."), key
        assert short.endswith("."), key
        assert len(short) <= 110, f"{key}: the first line is read in a popover, keep it to a breath"
        assert short.count(".") == 1 or "." in short[:-1], key
        assert len(rest) >= 80, f"{key}: say how it is built and what an ordinary value looks like"


def test_every_marker_points_at_a_real_term():
    keys = set(glossary.TERMS)
    used: set[str] = set()
    for src in [ROOT / "build.py", ROOT / "components.py"]:
        used |= set(re.findall(r'c\.info\(["\']([a-z0-9_]+)["\']', src.read_text(encoding="utf-8")))
        used |= set(re.findall(r'c\.term\(["\']([a-z0-9_]+)["\']', src.read_text(encoding="utf-8")))
    for src in (ROOT / "assets").glob("*.js"):
        text = src.read_text(encoding="utf-8")
        used |= set(re.findall(r"mk\(['\"]([a-z0-9_]+)['\"]\)", text))
        used |= set(re.findall(r'data-t="([a-z0-9_]+)"', text))
        gk = re.search(r"var GK=\{(.*?)\};", text, re.S)      # the analysis page's measure -> term map
        if gk:
            used |= set(re.findall(r":'([a-z0-9_]+)'", gk.group(1)))
    assert used, "no markers found at all - the wiring has gone"
    assert used <= keys, f"markers with no definition: {sorted(used - keys)}"


def test_the_payload_carries_the_section():
    import json
    p = json.loads(glossary.payload())
    assert len(p) == len(glossary.TERMS)
    assert all(len(v) == 4 and v[3] for v in p.values())
