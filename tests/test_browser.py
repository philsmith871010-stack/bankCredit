from bankcredit.adapters import browser as B
from bankcredit.adapters.pillar3 import Pillar3Adapter


def test_generic_candidates_take_pillar3_links_by_text_or_url():
    ad = Pillar3Adapter()
    loc = {"entity": "x", "page": "https://example.org/about/", "match": r"never-matches\.pdf"}
    links = [["https://example.org/media/1234/download", "Pillar 3 Disclosures 31 December 2025"],
             ["https://example.org/docs/remuneration-pillar-3-2025.pdf", "Remuneration"],
             ["https://example.org/docs/annual-report-2025.pdf", "Annual report"],
             ["https://example.org/docs/basel-iii-disclosures-2024.pdf", ""]]
    assert B.candidates(loc, "", links, ad) == []
    got = B.candidates(loc, "", links, ad, generic=True)
    urls = [u for u, _d, _t in got]
    assert "https://example.org/media/1234/download" in urls            # matched by anchor text
    assert "https://example.org/docs/basel-iii-disclosures-2024.pdf" in urls
    assert not any("remuneration" in u or "annual" in u for u in urls)
    assert got[0][1].isoformat() == "2025-12-31"                          # newest first, date from the text


def test_blocked_detection():
    assert B.looks_blocked(403, "x" * 5000)
    assert B.looks_blocked(200, "<html>Just a moment...</html>" + " " * 3000)
    assert not B.looks_blocked(200, "<html>" + "real content " * 500 + "</html>")


def test_subpages_follow_report_hubs_on_the_same_host():
    ad = Pillar3Adapter()
    loc = {"entity": "furness-bs", "page": "https://www.furnessbs.co.uk/about-us/", "match": r"pillar.*\.pdf"}
    links = [["https://www.furnessbs.co.uk/financial-reports/", "Financial reports"],
             ["https://www.furnessbs.co.uk/media/x/savings-tcs.pdf", "Savings T&Cs"],
             ["https://twitter.com/furnessbs", "Twitter"],
             ["https://www.furnessbs.co.uk/about-us/", "About us"],
             ["https://www.furnessbs.co.uk/careers/", "Careers"]]
    assert B.subpages(loc, "", links, ad) == ["https://www.furnessbs.co.uk/financial-reports/"]
    assert B.document_links("", links, ad, loc["page"]) == 1


def test_locator_text_key_tells_opaque_downloads_apart():
    ad = Pillar3Adapter()
    loc = {"entity": "jpmorgan-chase", "page": "https://example.org/ir/", "match": r"static-files",
           "text": r"pillar ?3|liquidity coverage", "exclude": r"financial statement|securities llc"}
    links = [["https://example.org/static-files/aaa", "Basel III Pillar 3 Regulatory Capital Disclosures Report – Q2 2026"],
             ["https://example.org/static-files/bbb", "JPMorgan Chase Bank, N.A. Consolidated Financial Statements 2025"],
             ["https://example.org/static-files/ccc", "J.P. Morgan Securities LLC Statement of Financial Condition"],
             ["https://example.org/static-files/ddd", "Liquidity Coverage Ratio Disclosure Q1 2026"]]
    got = [u for u, _d, _t in B.candidates(loc, "", links, ad)]
    assert got == ["https://example.org/static-files/aaa", "https://example.org/static-files/ddd"]
    generic = [u for u, _d, _t in B.candidates(loc, "", links, ad, generic=True)]
    assert "https://example.org/static-files/bbb" not in generic
