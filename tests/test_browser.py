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
