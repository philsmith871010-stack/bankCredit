"""The locator table: each entity's pattern has to name its own documents and refuse its siblings'."""
import re

import pytest

from bankcredit.adapters.pillar3_locators import LOCATORS

LLOYDS = ("lloyds-banking-group", "lloyds-bank", "bank-of-scotland", "lloyds-bank-corporate-markets")
# what the one shared page actually serves, in both of the naming styles Lloyds uses
FILES = {
    "2026-lbg-hy-pillar-3.pdf": "lloyds-banking-group",
    "2026-lb-hy-pillar-3.pdf": "lloyds-bank",
    "2026-bos-hy-pillar-3.pdf": "bank-of-scotland",
    "2026-lbcm-hy-pillar-3.pdf": "lloyds-bank-corporate-markets",
    "lloyds-bank-plc-pillar-3-disclosures-2025.pdf": "lloyds-bank",
    "bank-of-scotland-plc-pillar-3-2025.pdf": "bank-of-scotland",
    "lbg-capital-instruments-main-features.pdf": None,     # no metrics in it; nobody should take it
}


def _takes(loc: dict, name: str) -> bool:
    return bool(re.search(loc["match"], name, re.I)) and not (
        loc.get("exclude") and re.search(loc["exclude"], name, re.I))


@pytest.mark.parametrize("name,owner", FILES.items())
def test_each_lloyds_document_is_claimed_by_exactly_its_own_entity(name, owner):
    """All four publish from one page. A bare Pillar 3 pattern on the group took Bank of Scotland's
    and LBCM's quarterlies and queued them as the group's own reports."""
    claimed = [l["entity"] for l in LOCATORS if l["entity"] in LLOYDS and _takes(l, name)]
    assert claimed == ([owner] if owner else []), claimed


def test_every_locator_names_an_entity_and_compiles():
    """The same check the health report runs, so a broken pattern fails here rather than silently
    collecting nothing for a quarter."""
    from bankcredit import health
    assert health._faults() == []


ANCHORS = '''
<a href="/tron/gbpu/info/contents/v1/document/52-278301">Annual report (pdf 2.0 MB)</a>
<a href="/tron/gbpu/info/contents/v1/document/52-278302">Risk and capital - information according to Pillar 3 (pdf)</a>
<a href="/tron/gbpu/info/contents/v1/document/52-265185">Risk and capital - information according to Pillar 3 (pdf)</a>
<a href="/en/about-us/careers">Careers</a>
'''


def test_a_document_with_an_opaque_address_is_identified_by_its_link_text():
    """Handelsbanken serves its reports as numeric ids that trigger a download, so nothing in the
    address says which report it is. The annual report sits on the identical path beside it."""
    from bankcredit.adapters.pillar3 import Pillar3Adapter
    ad = Pillar3Adapter()
    loc = next(l for l in LOCATORS if l["entity"] == "handelsbanken-plc")
    page = loc["page"]
    got = ad._matches(loc, page, ANCHORS)
    urls = [u for u, _, _ in got]
    assert len(urls) == 2, got
    assert all(u.endswith(("52-278302", "52-265185")) for u in urls)
    assert all("Pillar 3" in title for _, _, title in got), "the title is what the link said"


def test_link_text_matching_does_not_disturb_a_locator_that_has_none():
    from bankcredit.adapters.pillar3 import Pillar3Adapter
    ad = Pillar3Adapter()
    loc = {"entity": "x", "page": "https://b.example/i", "match": r"\.pdf$"}
    body = '<a href="/a/pillar-3-2025.pdf">whatever</a><a href="/b/notes.txt">Pillar 3</a>'
    assert [u for u, _, _ in ad._matches(loc, loc["page"], body)] == ["https://b.example/a/pillar-3-2025.pdf"]
