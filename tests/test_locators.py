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


# ---- a document belongs to the locator that found it ------------------------------------------
def test_the_locator_matched_is_the_one_the_document_came_from():
    """An entity has several locators - TSB has one for its quarterly disclosures and one for its
    annual report - and they say different things about what the document is."""
    from bankcredit.adapters.pillar3 import Pillar3Adapter

    ara = ("https://www.tsb.co.uk/content/dam/tsb-public/documents/investors/"
           "financial-results-and-reports/2025/TSB-Bank-ARA-2025.pdf")
    quarterly = ("https://www.tsb.co.uk/content/dam/tsb-public/documents/investors/rns/"
                 "Q1-2026-Pillar-3-Quarterly-Disclosure.pdf")
    lsd = ("https://www.tsb.co.uk/content/dam/tsb-public/documents/investors/rns/LSD-document-Q2-2026.pdf")
    assert Pillar3Adapter._locator_for("tsb", ara).get("narrative")
    assert not Pillar3Adapter._locator_for("tsb", quarterly).get("narrative")
    assert not Pillar3Adapter._locator_for("tsb", lsd).get("narrative"), "the half-year Large Subsidiary Disclosure carries a KM1"


def test_a_narrative_locator_says_what_the_reviewer_should_do():
    """'no KM1 template found' reads as a failure. A source with no KM1 by nature is not one."""
    from bankcredit.adapters.pillar3_locators import LOCATORS

    for loc in LOCATORS:
        note = loc.get("narrative")
        if note:
            assert len(note) > 30 and "read" in note.lower(), loc["entity"]


# ---- an index page is followed on what its link says, not only on its address --------------------
def test_an_index_page_is_followed_on_its_link_text():
    """Bank of China (UK) lists one item page per Pillar 3 under an address that is only a posting
    stamp (t20260714_25679507.html); the anchor text is all that says what sits behind it. A page
    whose text says something else is left alone."""
    from bankcredit.adapters.pillar3 import Pillar3Adapter

    ad = Pillar3Adapter()
    loc = {"entity": "x", "page": "https://www.bankofchina.com/uk/aboutus/ab5/", "match": r"P\d+\.pdf"}
    body = ('<a href="./202607/t20260714_25679507.html">Bank of China (UK) Limited Pillar 3 Disclosure 31 December 2025</a>'
            '<a href="./202603/t20260331_25657715.html">2025 Gender Pay Gap Report</a>')
    assert ad._index_pages(loc, body) == ["https://www.bankofchina.com/uk/aboutus/ab5/202607/t20260714_25679507.html"]


def test_a_text_matched_document_is_dated_by_its_text_before_its_posting_stamp():
    """The PDF behind that item page is named P020260716391457618567.pdf, a posting stamp a day or
    two after the upload; the link text names the reporting date."""
    from bankcredit.adapters.pillar3 import Pillar3Adapter
    from bankcredit.adapters.pillar3_locators import LOCATORS, P3

    ad = Pillar3Adapter()
    loc = next(l for l in LOCATORS if l["entity"] == "bank-of-china-uk")
    sub = "https://www.bankofchina.com/uk/aboutus/ab5/202607/t20260714_25679507.html"
    body = ('<a href="https://pic.bankofchina.com/bocappd/uk/202607/P020260716391457618567.pdf">'
            'Bank of China (UK) Limited Pillar 3 Disclosure 31 December 2025</a>'
            '<a href="https://pic.bankofchina.com/bocappd/uk/202605/P020260506389809417235.pdf">'
            'Bank of China (UK) Limited Annual Report and Financial Statements 2025</a>')
    got = ad._matches(loc, sub, body)
    assert [(u.rsplit("/", 1)[-1], str(d)) for u, d, _ in got] == [("P020260716391457618567.pdf", "2025-12-31")]


def test_an_annual_url_template_is_tried_once_a_year_dated_to_the_year_end():
    """ICBC London's Pillar 3 sits at one address per year. Filled for every quarter, the template
    asked for the same missing file four times a run."""
    from datetime import date as _date
    from unittest import mock
    from bankcredit.adapters import pillar3 as p3
    loc = {"entity": "icbc-london", "kind": "pattern",
           "urls": ["https://example.org/download/{year}/{year}_pillar_3_disclosure.pdf"]}
    with mock.patch.object(p3, "date", wraps=_date) as d:
        d.today.return_value = _date(2027, 5, 1)
        got = p3.Pillar3Adapter._pattern_candidates(p3.Pillar3Adapter.__new__(p3.Pillar3Adapter), loc)
    urls = [u for u, _, _ in got]
    assert len(urls) == len(set(urls)), urls
    assert [(u.rsplit("/", 1)[-1], str(e)) for u, e, _ in got][:2] == [
        ("2027_pillar_3_disclosure.pdf", "2027-03-31"), ("2026_pillar_3_disclosure.pdf", "2026-12-31")]



# ---- Citigroup Inc. and the Citi subsidiaries that publish beside it ------------------------------
CITI = "https://www.citigroup.com/rcs/citigpa/storage/public/"
CITI_FILES = {
    "6-30-26-lcr-public-disclosure.pdf": "us_lcr",
    "q2-2025-lcr-public-disclosure.pdf": "us_lcr",
    "c-3-31-25-lcr-public-disclosure-final.pdf": "us_lcr",
    "c-12-31-24-lcr-public-disclosure.pdf": "us_lcr",
    "lcr093024.pdf": "us_lcr",
    "lcr240630.pdf": "us_lcr",
    "c-baseI-iii-adv-approach-06-30-2026.pdf": "us_capital",
    "c-basel-III-adv-approach-03-31-2025-forum.pdf": "us_capital",
    "1q26-basel-iii-advanced-approaches-disclosures.pdf": "us_capital",
    "2q-2025-baseI-iii-advanced-approach-disclosure.pdf": "us_capital",
    # Citibank Europe plc, Citigroup Global Markets Europe / Ltd, Citibank UK, Citibank Canada:
    # their own KM1s and LCRs, which once gave Citigroup an LCR of 128-148% against its own ~115%
    "cep-pillar-3-disclosures-q1-2026.pdf": None,
    "Pillar-3-Disclosures-Q4-2023.pdf": None,
    "cgme-pillar-3-disclosure-q2-2026.pdf": None,
    "cgml-pillar-3-disclosures-q4-2025.pdf": None,
    "cukl-pillar-3-disclosures-2025.pdf": None,
    "Canada/basel-III/citibank-canada-basel-iii-pillar-3-osfi-q2-2026-en.pdf": None,
    "12-31-25-nsfr-public-disclosure .pdf": None,
}


@pytest.mark.parametrize("name,template", CITI_FILES.items())
def test_citigroup_takes_only_its_own_lcr_and_capital_reports(name, template):
    claimed = [l.get("template") for l in LOCATORS if l["entity"] == "citigroup" and _takes(l, CITI + name)]
    assert claimed == ([template] if template else []), claimed


def test_a_citigroup_document_is_read_with_the_template_of_the_locator_that_found_it():
    from bankcredit.adapters.pillar3 import Pillar3Adapter
    assert Pillar3Adapter._locator_for("citigroup", CITI + "6-30-26-lcr-public-disclosure.pdf")["template"] == "us_lcr"
    assert Pillar3Adapter._locator_for("citigroup", CITI + "c-baseI-iii-adv-approach-06-30-2026.pdf")["template"] == "us_capital"
