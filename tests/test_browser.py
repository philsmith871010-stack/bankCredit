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


REPORT_HTML = """<html><head><title>Pillar 3 report 2Q26</title><style>body{color:red}</style>
<script>window.x=1</script></head><body><nav><a href="/">Home</a></nav>
<h1>UBS Group AG Pillar 3 report</h1><p>Key metrics (KM1) as of 30 June 2026, USD million</p>
<table>
<tr><th></th><th></th><th>30.6.26</th><th>31.3.26</th></tr>
<tr><td>1</td><td>Common Equity Tier 1 (CET1) capital</td><td>78,520</td><td>77,900</td></tr>
<tr><td>2</td><td>Tier 1 capital</td><td>95,100</td><td>94,300</td></tr>
<tr><td>3</td><td>Total capital</td><td>108,200</td><td>107,000</td></tr>
<tr><td>4</td><td>Total risk-weighted assets (RWA)</td><td>530,000</td><td>525,000</td></tr>
<tr><td>5</td><td>CET1 ratio (%)</td><td>14.8</td><td>14.8</td></tr>
<tr><td>6</td><td>Tier 1 ratio (%)</td><td>17.9</td><td>18.0</td></tr>
<tr><td>7</td><td>Total capital ratio (%)</td><td>20.4</td><td>20.4</td></tr>
<tr><td>13</td><td>Total exposure measure</td><td>1,650,000</td><td>1,640,000</td></tr>
<tr><td>14</td><td>Leverage ratio (%)</td><td>5.8</td><td>5.8</td></tr>
<tr><td>17</td><td>Liquidity coverage ratio (%)</td><td>190</td><td>188</td></tr>
</table><footer>Legal</footer></body></html>"""


def test_web_page_report_is_laid_out_and_read(tmp_path):
    from bankcredit.extract import km1
    assert B.html_to_pdf("<html><body><h1>Pillar 3</h1><p>nothing here</p></body></html>") is None
    pdf = B.html_to_pdf(REPORT_HTML)
    assert pdf and pdf.startswith(b"%PDF")
    path = tmp_path / "ubs.pdf"
    path.write_bytes(pdf)
    res = km1.extract(str(path), currency_hint="USD")
    assert res.values["cet1_capital"] == 78520 and res.values["tier1_ratio"] == 17.9
    assert res.values["lcr"] == 190


def test_fetch_document_falls_back_to_the_page_body():
    class Resp:
        status_code, content, headers = 200, REPORT_HTML.encode(), {"content-type": "text/html; charset=utf-8"}
        text = REPORT_HTML * 20
    class Session:
        def get(self, url, timeout=0):
            return Resp()
    data, how = B.fetch_document("https://example.org/pillar-3-report-2q26.html", Session(), None)
    assert how == "html" and data.startswith(b"%PDF")
