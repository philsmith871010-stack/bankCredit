from datetime import date

import fitz

from bankcredit.adapters.pillar3 import infer_period
from bankcredit.extract import km1

KM1_TEXT = """UK KM1 - Key metrics template
a b c
31 Dec 25 30 Sep 25 30 Jun 25
£m £m £m
Available own funds (amounts)
1
Common Equity Tier 1 (CET1) capital
2,575.0 2,462.2 2,465.7
2
Tier 1 capital
2,575.0 2,462.2 2,465.7
3
Total capital
2,590.0 2,502.2 2,505.7
Risk-weighted exposure amounts (RWEAs)
4
Total risk-weighted exposure amount
9,141.4 8,802.3 8,559.3
Capital ratios (as a % of RWEAs)
5
Common Equity Tier 1 ratio (%)
28.2 28.0 28.8
6
Tier 1 ratio (%)
28.2 28.0 28.8
7
Total capital ratio (%)
28.3 28.4 29.3
UK 7d
Total SREP own funds requirements (%)
10.6 10.6 10.0
11
Combined buffer requirement (%)
4.3 4.3 4.3
UK 11a Overall capital requirements (%)
14.9 14.9 14.3
12
CET1 available after meeting the total SREP own
funds requirements (%)
17.8 17.8 19.3
Leverage ratio
13
Total exposure measure excluding claims on central
banks
38,477.2 38,439.9 37,570.0
14
Leverage ratio excluding claims on central banks
(%)
6.7 6.4 6.6
Liquidity Coverage Ratio
15
Total high-quality liquid assets (HQLA) (Weighted
value -average)
5,702.4 5,906.6 6,012.7
16
Total net cash outflows (adjusted value)
3,059.6 3,100.2 3,155.0
17
Liquidity coverage ratio (%)
186.7 190.8 191.0
Net Stable Funding Ratio
18
Total available stable funding
35,805.4 35,153.8 34,584.6
19
Total required stable funding
25,867.5 25,179.6 24,899.7
20
Net Stable Funding Ratio (%)
138.4 139.6 138.9
7
"""


def make_pdf(tmp_path, text, name="t.pdf"):
    doc = fitz.open()
    page = doc.new_page()
    y = 40
    for line in text.splitlines():
        page.insert_text((40, y), line, fontsize=8)
        y += 11
    p = tmp_path / name
    doc.save(str(p))
    return str(p)


def test_parse_rows_confirms_labels_and_keeps_first_occurrence():
    lines = [l for l in KM1_TEXT.splitlines() if l.strip()]
    vals, labels = km1.parse_rows(lines)
    assert vals["1"][0] == "2,575.0" and vals["4"][0] == "9,141.4"
    assert vals["11a"][0] == "14.9"
    assert vals["14"][0] == "6.7" and "leverage" in labels["14"].lower()
    assert "7" in vals and vals["7"][0] == "28.3"      # the trailing page number "7" did not clobber row 7


def test_extract_end_to_end(tmp_path):
    res = km1.extract(make_pdf(tmp_path, KM1_TEXT))
    assert res.ok, res.checks
    assert res.reference_date == date(2025, 12, 31)
    assert res.values["cet1_ratio"] == 28.2 and res.values["rwa"] == 9141.4
    assert res.values["lcr"] == 186.7 and res.values["nsfr"] == 138.4
    assert res.currency == "GBP" and res.confidence >= 0.9


def test_thousands_are_scaled_and_bad_ratio_is_an_error(tmp_path):
    text = KM1_TEXT.replace("£m £m £m", "£000 £000 £000").replace("28.2 28.0 28.8", "18.2 28.0 28.8", 1)
    res = km1.extract(make_pdf(tmp_path, text))
    assert abs(res.values["cet1_capital"] - 2.575) < 1e-6
    assert any(s == "error" and "cet1_ratio" in m for s, m in res.checks)
    assert not res.ok


def test_no_template(tmp_path):
    res = km1.extract(make_pdf(tmp_path, "Remuneration disclosures\nNothing to see here\n"))
    assert not res.values and not res.ok


def test_infer_period():
    assert infer_period("Q126-BPLC-Pillar-3.pdf") == date(2026, 3, 31)
    assert infer_period("H126 Barclays PLC Pillar 3 Report.pdf") == date(2026, 6, 30)
    assert infer_period("260508-hbuk-pillar-3-disclosures-at-31-march-2026.pdf") == date(2026, 3, 31)
    assert infer_period("interim-pillar-3-disclosures-2025-2026.pdf", "04-04") == date(2025, 9, 30)
    assert infer_period("pillar-3-disclosures-q1-2026-27.pdf", "04-04") == date(2026, 6, 30)
    assert infer_period("cbplc-dec25-quarterly-pillar3-disclosure.pdf", "09-30") == date(2025, 12, 31)
    assert infer_period("Santander UK 2026 Half Yearly ACRMD.pdf") == date(2026, 6, 30)
    assert infer_period("2023-interim-pillar-3-report-FINAL.pdf", "09-30") == date(2023, 3, 31)
    assert infer_period("nwg-pillar-3-report.pdf") is None


def test_prior_columns_follow_header_dates():
    from datetime import date
    from bankcredit.extract.km1 import prior_columns
    dates = [date(2026, 6, 30), date(2026, 3, 31), date(2025, 12, 31)]
    picked = [("cet1_capital", ["2,575", "2,540", "2,500"], "1"), ("rwa", ["9,141", "9,100", "9,000"], "2"),
              ("cet1_ratio", ["28.2%", "27.9%", "27.8%"], "3"), ("lcr", ["186.7", "180.1"], "17")]   # LCR has one column short: ignored
    h = prior_columns(picked, dates, True, 1.0)
    assert set(h) == {"2026-03-31", "2025-12-31"}
    assert h["2026-03-31"]["cet1_ratio"] == 27.9 and h["2025-12-31"]["rwa"] == 9000.0 and "lcr" not in h["2026-03-31"]
    # ascending headers (oldest first) are read the other way round
    h2 = prior_columns([("cet1_ratio", ["27.8%", "27.9%", "28.2%"], "3")], list(reversed(dates)), False, 1.0)
    assert h2["2026-03-31"]["cet1_ratio"] == 27.9
    # a prior column failing the capital arithmetic is dropped
    bad = [("cet1_capital", ["2,575", "1,000"], "1"), ("rwa", ["9,141", "9,100"], "2"), ("cet1_ratio", ["28.2%", "27.9%"], "3")]
    assert prior_columns(bad, dates[:2], True, 1.0) == {}


def test_curly_apostrophe_thousands_are_scaled():
    from bankcredit.extract.km1 import detect_units, _norm_text
    assert detect_units(_norm_text("31 Mar 2023 £\u2019000 31 Mar 2022 £\u2019000 Common Equity Tier 1"))[1] == 0.001
