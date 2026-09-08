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
