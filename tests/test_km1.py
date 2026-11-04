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


def test_fully_loaded_twin_rows_do_not_stand_in_for_base_rows():
    # Barclays 2018 Table 7: labels and values in separate blocks, each base row followed by a
    # "Fully loaded ECL accounting model" twin. The twin's value must not become the base row's.
    lines = ["1", "Common Equity Tier 1 (CET1)", "41,100", "40,400",
             "1a", "Fully loaded ECL accounting model",
             "2", "Tier 1", "2a", "Fully loaded ECL accounting model", "50,000",
             "3", "Total capital", "64,594",
             "4", "Total risk-weighted assets (RWA)", "311,926",
             "6", "Tier 1 ratio (%)", "17.0",
             "6a Fully loaded ECL accounting model Tier 1 ratio (%)", "16.4"]
    vals, labels = km1.parse_rows(lines)
    assert vals["1"][0] == "41,100"
    assert "2" not in vals                      # missing beats wrong
    assert vals["3"][0] == "64,594" and vals["4"][0] == "311,926"
    assert vals["6"][0] == "17.0"
    assert km1._confirm("2", "Tier 1 fully loaded") is None
    assert km1._confirm("2", "Tier 1") == "tier1_capital"


def test_single_digit_month_dates_keep_column_order():
    # UBS column headers: the first column must win, not the only December date
    assert km1.parse_dates("30.6.26 31.3.26 31.12.25 30.9.25") == [
        km1.date(2026, 6, 30), km1.date(2026, 3, 31), km1.date(2025, 12, 31), km1.date(2025, 9, 30)]
    assert km1.detect_units("Key metrics (KM1)\nUSD m, except where indicated")[0] == "USD"


def test_split_column_headers_are_joined_in_order():
    dates, left = km1.join_split_headers("31 December\n30 September\n30 June\n31 March\n31  December\n2023\n2023\n2023\n2023\n2022")
    assert [d.isoformat() for d in dates] == ["2023-12-31", "2023-09-30", "2023-06-30", "2023-03-31", "2022-12-31"] and left == 0
    dates, _ = km1.join_split_headers("Bank\n30 June\n2023\n30 June 2022\n30 June 2023")          # Aldermore
    assert [d.isoformat() for d in dates] == ["2023-06-30", "2022-06-30"]
    dates, _ = km1.join_split_headers("31 Dec\n22\n30 Jun\n22\n31 Dec\n21")                       # Co-operative Bank
    assert [d.isoformat() for d in dates] == ["2022-12-31", "2022-06-30", "2021-12-31"]
    dates, _ = km1.join_split_headers("31 Dec 24\n30 Jun 24\n31 Dec 231")                             # Vanquis, footnote on the year
    assert [d.isoformat() for d in dates] == ["2024-12-31", "2024-06-30", "2023-12-31"]
    dates, left = km1.join_split_headers("31 September\n30 June\n2022")                              # typo, and one year short
    assert dates == [km1.date(2022, 9, 30)] and left == 1


def test_first_unit_statement_wins():
    assert km1.detect_units("KM1 (Millions of Canadian dollars)\nTotal RWA increased by $29 billion")[1] == 1.0
    assert km1.detect_units("Key metrics £bn\n1 CET1 capital 40.7")[1] == 1000.0
    assert km1.detect_units("Key metrics £'000\n1 CET1 capital 40,700")[1] == 0.001


def test_narrative_date_prefers_the_as_at_phrase():
    lines = ["Table 4.1B Key metrics", "The Group adopted the framework from 1 January 2013. Table 4.1B shows capital as at 30 Sep 17.",
             "Common Equity Tier 1 capital", "34,000", "Tier 1 capital", "40,000", "Total capital", "48,000",
             "Total risk-weighted assets", "380,000", "Common Equity Tier 1 ratio", "10.1%", "Tier 1 ratio", "12.4%", "Total capital ratio", "14.6%"]
    import fitz
    doc = fitz.open(); page = doc.new_page(); y = 60
    for l in lines:
        page.insert_text((50, y), l, fontsize=10); y += 16
    import tempfile, os
    path = os.path.join(tempfile.mkdtemp(), "nab.pdf"); doc.save(path)
    res = km1.extract(path, currency_hint="AUD")
    assert res.reference_date == km1.date(2017, 9, 30)
    assert res.history == {}


DERIVED_TEXT = KM1_TEXT.replace("""5
Common Equity Tier 1 ratio (%)
28.2 28.0 28.8
""", "").replace("""6
Tier 1 ratio (%)
28.2 28.0 28.8
""", "")


def test_ratio_is_derived_from_capital_over_rwa_when_the_row_is_absent(tmp_path):
    """SMFG states capital and risk-weighted assets without a ratio row. Arithmetic supplies the
    ratio, it is recorded as derived, and the derivation runs before the missing-core-row check
    so the document is not rejected for the row it does not need."""
    res = km1.extract(make_pdf(tmp_path, DERIVED_TEXT))
    assert res.ok, res.checks
    assert res.values["cet1_ratio"] == round(2575.0 / 9141.4 * 100, 2) == 28.17
    assert res.values["tier1_ratio"] == 28.17
    assert "cet1_ratio" in res.derived and "tier1_ratio" in res.derived
    assert res.values["total_capital_ratio"] == 28.3, "a stated ratio is never overwritten"
    assert "total_capital_ratio" not in res.derived


def test_a_derived_ratio_outside_the_plausible_range_is_not_taken(tmp_path):
    """The same bounds a read value gets. Capital stated in units against RWA in millions would
    otherwise yield a ratio of nearly nothing, or of thousands."""
    text = DERIVED_TEXT.replace("2,575.0 2,462.2 2,465.7", "9,000,000.0 9,000,000.0 9,000,000.0")
    res = km1.extract(make_pdf(tmp_path, text))
    assert "cet1_ratio" not in res.derived


FOOTNOTED = KM1_TEXT.replace("Common Equity Tier 1 ratio (%)", "Common Equity Tier 1 ratio (%)3") \
                    .replace("Tier 1 ratio (%)", "Tier 1 ratio (%)3")


def test_a_footnote_marker_on_a_row_label_does_not_hide_the_row(tmp_path):
    """Hong Kong KM1 prints "CET1 ratio (%)3". Stripping the bracket leaves the footnote digit
    stranded, the anchored label pattern misses, and the ratio is quietly derived from capital
    over RWA instead of read: a computed number published where a stated one exists."""
    res = km1.extract(make_pdf(tmp_path, FOOTNOTED))
    assert res.values["cet1_ratio"] == 28.2 and "cet1_ratio" not in res.derived
    assert res.values["tier1_ratio"] == 28.2 and "tier1_ratio" not in res.derived


def test_a_pre_floor_twin_does_not_stand_in_for_the_base_row(tmp_path):
    """The floored ratio is the one the template asks for. Normalising a label throws the
    qualifier away, so the two rows are indistinguishable by the time they are matched."""
    text = KM1_TEXT.replace("""5
Common Equity Tier 1 ratio (%)
28.2 28.0 28.8
""", """5
Common Equity Tier 1 ratio (%)
28.2 28.0 28.8
5b
Common Equity Tier 1 ratio (%) (pre-floor ratio)
31.9 31.7 32.5
""")
    res = km1.extract(make_pdf(tmp_path, text))
    assert res.values["cet1_ratio"] == 28.2, "the floored ratio, not the pre-floor twin"


def test_the_pre_floor_twin_is_rejected_whichever_row_comes_first(tmp_path):
    """First-match-wins would take whichever the bank happened to print above the other."""
    text = KM1_TEXT.replace("""5
Common Equity Tier 1 ratio (%)
28.2 28.0 28.8
""", """5b
Common Equity Tier 1 ratio (%) (pre-floor ratio)
31.9 31.7 32.5
5
Common Equity Tier 1 ratio (%)
28.2 28.0 28.8
""")
    res = km1.extract(make_pdf(tmp_path, text))
    assert res.values["cet1_ratio"] == 28.2


def test_a_contents_page_is_never_read_as_the_template(tmp_path):
    """A contents page lists "KM1 Key metrics ... 12" and scores like the template, but the
    numbers beside its entries are page numbers. Read as a table it fills the capital rows with
    them, and the ratios derived from those are nonsense."""
    contents = """Contents
1 Introduction 3
KM1 Key metrics 12
OV1 Overview of RWA 14
LR1 Leverage ratio summary 20
CR1 Credit quality of assets 24
LIQ1 Liquidity coverage ratio 30
"""
    assert km1.looks_like_contents(contents), "a listing with no figures in it"
    assert not km1.looks_like_contents(KM1_TEXT), "a real table, whatever words are on the page"
    import fitz
    doc = fitz.open()
    for block in (contents, KM1_TEXT):
        page, y = doc.new_page(), 40
        for line in block.splitlines():
            page.insert_text((40, y), line, fontsize=8)
            y += 11
    p = tmp_path / "withcontents.pdf"
    doc.save(str(p))
    res = km1.extract(str(p))
    assert res.ok, res.checks
    assert res.page == 2, "the real table, not the contents listing"
    assert res.values["cet1_ratio"] == 28.2


def test_the_template_is_found_deep_in_a_long_report(tmp_path):
    """A full annual Pillar 3 report runs to well over a hundred pages and prints KM1 inside it.
    A page budget that stops early sees only the front matter."""
    import fitz
    doc = fitz.open()
    for _ in range(80):
        page = doc.new_page()
        page.insert_text((40, 40), "Introduction and risk management commentary", fontsize=8)
    page = doc.new_page()
    y = 40
    for line in KM1_TEXT.splitlines():
        page.insert_text((40, y), line, fontsize=8)
        y += 11
    p = tmp_path / "long.pdf"
    doc.save(str(p))
    res = km1.extract(str(p))
    assert res.ok and res.page == 81, (res.page, res.checks)
    assert res.values["cet1_ratio"] == 28.2


def test_a_derived_ratio_must_be_one_the_validator_would_accept(tmp_path):
    """A capital row misread as a percentage gives an implied ratio near zero. Deriving it turns
    one misread row into a published figure of 0.0 and an error the document is then held for."""
    text = DERIVED_TEXT.replace("2,575.0 2,462.2 2,465.7", "13.5 13.4 13.6")
    res = km1.extract(make_pdf(tmp_path, text, name="tiny.pdf"))
    assert res.values.get("cet1_ratio") is None
    assert "cet1_ratio" not in res.derived


def test_a_real_table_is_not_a_contents_page_because_of_its_header():
    """Scotiabank prints "Back to Table of Contents" in the running header of every page, its own
    KM1 page included. Keying on the word rather than the shape loses the bank three quarters."""
    header = "Back to Table of Contents\nKM1: Key metrics (at consolidated group level)\n"
    assert not km1.looks_like_contents(header + KM1_TEXT)


def test_a_narrative_page_naming_the_template_is_not_read_as_one():
    """A page that mentions KM1 without tabulating it has no figures to take."""
    prose = ("Contents\n1 Overview 3\n2 Own funds 7\nKM1 Key metrics 12\n"
             "OV1 Overview of RWA 14\nLR1 Leverage summary 20\nCR1 Credit quality 24\n")
    assert km1.looks_like_contents(prose)


def test_a_space_after_the_decimal_point_does_not_truncate_the_value(tmp_path):
    """The HKMA disclosure statements set every percentage as "16. 6%". Left alone the number
    ends at the point, and the value read for the row is whatever follows it - in a numbered
    template, the next row's number. Standard Chartered HK reported a CET1 ratio of 5.00."""
    spaced = KM1_TEXT.replace("28.2 28.0 28.8", "28. 2% 28. 0% 28. 8%")
    res = km1.extract(make_pdf(tmp_path, spaced, name="spaced.pdf"))
    assert res.values["cet1_ratio"] == 28.2, res.values.get("cet1_ratio")


def test_the_normaliser_joins_only_a_split_number():
    assert km1._norm_text("16. 6%") == "16.6%"
    assert km1._norm_text("2,575. 0") == "2,575.0"
    assert km1._norm_text("Total capital ratio (%)") == "Total capital ratio (%)"


def test_columns_headed_by_a_year_alone_are_dated_to_the_year_end(tmp_path):
    """An annual-only filer heads its columns "2025  2024". Read as no dates at all, the fallback
    takes one from the narrative - for Handelsbanken the board meeting that approved the dividend,
    three months after the period the figures describe."""
    text = KM1_TEXT.replace("a b c\n31 Dec 25 30 Sep 25 30 Jun 25", "2025\n2024\n2023") \
                   .replace("The Board of Directors met", "x")
    res = km1.extract(make_pdf(tmp_path, "The Board of Directors met on 18 March 2026\n" + text, name="years.pdf"))
    assert res.reference_date == date(2025, 12, 31), res.reference_date
    assert not any("narrative" in m for _, m in res.checks)


def test_a_bare_year_run_is_required_before_years_are_read_as_columns():
    """A lone number in a header is as likely to be a row count; a table's own figures must never
    be taken for its column dates."""
    assert km1.bare_year_columns("2025\n2024\n") == [date(2025, 12, 31), date(2024, 12, 31)]
    assert km1.bare_year_columns("2025\n") == [], "one year is not a run"
    assert km1.bare_year_columns("2025\n2019\n") == [], "not consecutive"
    assert km1.bare_year_columns("2,575\n9,141\n") == [], "figures are not years"
    assert km1.bare_year_columns("2025\n2024\n", "03-31") == [date(2025, 3, 31), date(2024, 3, 31)]



def test_a_space_before_the_thousands_is_read_as_one_number(tmp_path):
    """Investec prints "2 604" where others print "2,604". Read token by token, the amount became
    two values and every figure on the row shifted one column: CET1 capital of 2, a ratio of 604."""
    spaced = KM1_TEXT.replace(",", " ")
    res = km1.extract(make_pdf(tmp_path, spaced, name="spaced-thousands.pdf"))
    assert res.ok, res.checks
    assert res.values["cet1_capital"] == 2575.0 and res.values["rwa"] == 9141.4
    assert res.values["cet1_ratio"] == 28.2


def test_the_space_join_is_conservative():
    # joined: a page with no comma-grouped numbers and more than one spaced amount
    assert km1._norm_text("1 Common Equity Tier 1 (CET1)\n2 604 2 590 2 580\n") == "1 Common Equity Tier 1 (CET1)\n2,604 2,590 2,580\n"
    assert km1._norm_text("1 234 567 and 12 345") == "1,234,567 and 12,345"
    # left alone: a page that groups with commas, a single occurrence, percentages, dates, years
    assert km1._norm_text("2,575.0 2 604 2 590") == "2,575.0 2 604 2 590"
    assert km1._norm_text("Table 1 234") == "Table 1 234"
    assert km1._norm_text("198% 190% 185%\n31 Dec 2025 30 Sep 2025") == "198% 190% 185%\n31 Dec 2025 30 Sep 2025"


# ---- metric accuracy: units, dates, columns, bases --------------------------------------------
def test_a_currency_code_before_000s_is_thousands():
    """FAB prints "All numbers in AED 000s"; read as millions its CET1 was AED 92,996,560m."""
    for head in ("All numbers in AED 000s", "USD'000", "HK$'000", "Amounts in thousands of US dollars", "(000s)"):
        assert km1.detect_units(head + "\n1 Common Equity Tier 1 92,996,560")[1] == 0.001, head


def test_the_unit_statement_nearest_the_table_wins():
    """A "bn" in the commentary above the table must not multiply its £m figures by a thousand."""
    text = ("Capital strengthened by £1.2bn in the period, and the Group's CET1 capital is now £40bn, an increase of\n"
            "UK KM1 Key metrics\n£m\n1\nCommon Equity Tier 1 (CET1) capital\n40,700\n")
    anchor = text.index("1\nCommon")
    assert km1.detect_units(text, anchor)[1] == 1.0
    assert km1.detect_units("Key metrics\n£'000\n" + "x" * 50 + "\n1 CET1 capital 40,700\nRWA rose £2bn\n", 60)[1] == 0.001


def test_amounts_beyond_any_bank_are_rescaled():
    res = km1.Result(values={"cet1_capital": 92996560.0, "rwa": 652036770.0, "cet1_ratio": 14.26}, currency="AED",
                     history={"2024-06-30": {"rwa": 620464998.0, "cet1_ratio": 13.96}})
    km1.check_size(res)
    assert res.values["rwa"] == 652036.77 and round(res.history["2024-06-30"]["rwa"], 3) == 620464.998
    assert res.values["cet1_ratio"] == 14.26 and any("thousands" in m for _, m in res.checks)
    big = km1.Result(values={"rwa": 110984102.0}, currency="JPY")          # MUFG's ¥111tn RWA is real
    km1.check_size(big)
    assert big.values["rwa"] == 110984102.0


def test_a_footnote_glued_to_the_year_does_not_lose_the_column():
    """Lloyds prints "31 Mar / 20222" and "Q1 20182": the year with footnote 2 attached. Unread, the
    first column took the second column's date, a quarter early."""
    dates, left = km1.join_split_headers("31 Mar \n20222\n31 Dec \n2021\n30 Sep \n2021")
    assert dates == [date(2022, 3, 31), date(2021, 12, 31), date(2021, 9, 30)] and left == 0
    assert km1.parse_dates("Q1 20182\nQ4 2017\nQ3 2017")[:2] == [date(2018, 3, 31), date(2017, 12, 31)]
    assert km1.parse_dates("Jun-24\nMar-24\nDec-23\nSep-231\nJun-23")[3] == date(2023, 9, 30)


def test_the_creation_stamp_decides_between_header_and_file_name():
    checks = []
    # NatWest's Q1 2026 header read as 30 June, weeks after the PDF was made: the file name is right
    assert km1.choose_reference(date(2026, 6, 30), date(2026, 3, 31), date(2026, 4, 30), checks) == date(2026, 3, 31)
    # Secure Trust's interim dated to the year before: both could be reported, the later one is
    assert km1.choose_reference(date(2025, 12, 31), date(2026, 6, 30), date(2026, 8, 12), checks) == date(2026, 6, 30)
    # a file name that names only the year: the header's quarter stands, the year end is still ahead
    assert km1.choose_reference(date(2024, 3, 31), date(2024, 12, 31), date(2024, 5, 1), checks) == date(2024, 3, 31)
    # no stamp: the header is direct evidence and is kept
    assert km1.choose_reference(date(2025, 12, 31), date(2026, 6, 30), None, checks) == date(2025, 12, 31)
    # no stamp, but a "Q1 2018" report cannot hold December 2019's figures
    assert km1.choose_reference(date(2019, 12, 31), date(2018, 3, 31), None, checks) == date(2018, 3, 31)


def test_a_stray_day_moves_to_the_period_end():
    checks = []
    assert km1.snap_to_period_end(date(2023, 12, 3), "12-31", checks) == date(2023, 12, 31)
    assert km1.snap_to_period_end(date(2022, 12, 30), "12-31", checks) == date(2022, 12, 31)
    assert km1.snap_to_period_end(date(2025, 4, 4), "04-04", checks) == date(2025, 4, 4)      # Nationwide's year end
    assert km1.snap_to_period_end(date(2025, 9, 30), "04-04", checks) == date(2025, 9, 30)
    assert km1.snap_to_period_end(date(2023, 3, 14), "12-31", checks) == date(2023, 3, 14)   # a board date, not a slip


def test_a_reference_date_after_the_pdf_was_made_is_not_taken(tmp_path):
    res = km1.extract(make_pdf(tmp_path, KM1_TEXT), hint_date=date(2025, 9, 30), published=date(2025, 11, 5))
    assert res.reference_date == date(2025, 9, 30) and not res.history
    res = km1.extract(make_pdf(tmp_path, KM1_TEXT, "b.pdf"), published=date(2025, 11, 5))
    assert any(s == "error" and "after the document was produced" in m for s, m in res.checks)


def test_leverage_rows_that_fail_their_arithmetic_are_left_out(tmp_path):
    """Metro's annual KM1 gave the half-year leverage rows (7.90% against 5.96% implied); the
    document loads, without them."""
    text = KM1_TEXT.replace("6.7 6.4 6.6", "9.9 6.4 6.6")
    res = km1.extract(make_pdf(tmp_path, text))
    assert res.ok, res.checks
    assert "leverage_ratio" not in res.values and "leverage_exposure" not in res.values
    assert not any(s == "error" for s, _ in res.checks)


def test_an_lcr_far_from_its_own_inputs_is_left_out(tmp_path):
    res = km1.extract(make_pdf(tmp_path, KM1_TEXT.replace("186.7 190.8 191.0", "427.0 190.8 191.0")))
    assert "lcr" not in res.values and res.ok
    # an average of month-end ratios a few points off the ratio of averages stays
    res = km1.extract(make_pdf(tmp_path, KM1_TEXT.replace("186.7 190.8 191.0", "205.0 190.8 191.0"), "b.pdf"))
    assert res.values["lcr"] == 205.0


def test_a_cet1_basis_overall_requirement_is_not_loaded(tmp_path):
    """Standard Chartered's row 11a read 10.38%: CET1 4.5% plus Pillar 2A's CET1 part plus buffers."""
    res = km1.extract(make_pdf(tmp_path, KM1_TEXT.replace("14.9 14.9 14.3", "10.4 10.4 10.3")))
    assert "overall_capital_requirement" not in res.values and res.ok
    assert not any(s == "error" for s, _ in res.checks)
    # above 10.5 but short of the total SREP requirement plus the combined buffer (10.6 + 4.3)
    res = km1.extract(make_pdf(tmp_path, KM1_TEXT.replace("14.9 14.9 14.3", "12.0 12.0 12.0"), "b.pdf"))
    assert "overall_capital_requirement" not in res.values
    res = km1.extract(make_pdf(tmp_path, KM1_TEXT, "c.pdf"))
    assert res.values["overall_capital_requirement"] == 14.9 and res.values["total_srep_requirement"] == 10.6
    assert "total_srep_requirement" in km1.PUBLISH


def test_a_helper_row_out_of_range_does_not_send_the_document_to_review(tmp_path):
    res = km1.extract(make_pdf(tmp_path, KM1_TEXT.replace("4.3 4.3 4.3", "43.0 4.3 4.3")))
    assert "combined_buffer" not in res.values and res.ok


def test_small_subsidiaries_keep_their_high_ratios():
    """Bank of Baroda UK: CET1 220%, leverage 85%."""
    res = km1.Result(values={"cet1_capital": 220.0, "tier1_capital": 220.0, "rwa": 100.0, "cet1_ratio": 220.0,
                             "tier1_ratio": 220.0, "leverage_exposure": 258.8, "leverage_ratio": 85.0}, currency="GBP",
                     template="UK KM1")
    km1.validate(res)
    assert res.ok and res.values["leverage_ratio"] == 85.0, res.checks
    h = km1.prior_columns([("lcr", ["1,450", "1,520"], "17"), ("nsfr", ["160", "158"], "20")],
                          [date(2025, 12, 31), date(2025, 6, 30)], True, 1.0)
    assert h["2025-06-30"]["lcr"] == 1520.0              # Close Brothers and Vanquis hold more than ten times their outflows


def test_a_continuation_line_is_not_read_as_a_label():
    lines = ["CET1 available after meeting the", "total SREP own funds", "requirements", "7.09%", "7.35%",
             "Total capital", "as if IFRS 9 transitional arrangements had not been applied", "52,318", "53,035",
             "Overall capital requirements", "15.24%"]
    got = km1.parse_by_label(lines)
    assert "total_srep_requirement" not in got and "total_capital" not in got
    assert got["overall_capital_requirement"] == ["15.24%"]
    assert km1.VARIANT_RE.search("Tier 1 capital as if IFRS 9 or analogous ECLs transitional arrangements had not been applied")


def test_a_leverage_requirement_row_is_never_the_leverage_ratio():
    eu = ["13", "Total exposure measure", "100,000", "EU 14a", "Additional own funds requirements to address the risk of excessive leverage (%)",
          "0.00%", "EU 14c", "Total SREP leverage ratio requirements (%)", "3.00%"]
    vals, _ = km1.parse_rows(eu)
    assert "14" not in vals
    uk = ["13", "Total exposure measure excluding claims on central banks", "100,000",
          "14b", "Leverage ratio including claims on central banks (%)", "4.2%",
          "14c", "Average leverage ratio excluding claims on central banks (%)", "4.6%"]
    vals, _ = km1.parse_rows(uk)
    assert "14" not in vals


CET1_REQ_TEXT = KM1_TEXT.replace("UK 7d\n", "UK 7a\nAdditional CET1 SREP requirements (%)\n2.4 2.4 2.4\n"
                                             "UK 7b\nAdditional AT1 SREP requirements (%)\n0.8 0.8 0.8\nUK 7d\n")


def test_the_bank_specific_cet1_requirement_is_built(tmp_path):
    """4.5% Pillar 1, the CET1 part of Pillar 2A (UK 7a) and the combined buffer (row 11)."""
    res = km1.extract(make_pdf(tmp_path, CET1_REQ_TEXT))
    assert res.ok, res.checks
    assert res.values["cet1_requirement"] == round(4.5 + 2.4 + 4.3, 2) and "cet1_requirement" in km1.PUBLISH
    assert res.values["total_capital_ratio"] == 28.3       # rows 7a and 7b do not disturb row 7
    eu = KM1_TEXT.replace("UK 7d\n", "EU 7a\nAdditional own funds requirements to address risks other than the risk of excessive leverage (%)\n"
                                     "2.0 2.0 2.0\nEU 7b\nof which: to be made up of CET1 capital (percentage points)\n1.13 1.13 1.13\nUK 7d\n")
    res = km1.extract(make_pdf(tmp_path, eu, "eu.pdf"))
    assert res.values["cet1_requirement"] == round(4.5 + 1.13 + 4.3, 2)


def test_tier1_capital_that_fails_its_ratio_is_left_out():
    res = km1.Result(values={"cet1_capital": 826.0, "tier1_capital": 1068.0, "rwa": 6437.0, "cet1_ratio": 12.8,
                             "tier1_ratio": 12.8, "leverage_ratio": 5.0}, currency="GBP", template="UK KM1")
    km1.validate(res)
    assert "tier1_capital" not in res.values and "tier1_ratio" not in res.values and res.ok


def test_the_rwa_row_survives_a_hyphen_on_its_own_line():
    vals, labels = km1.parse_rows(["4", "Total risk", "-weighted exposure amount", "250,893", "244,711"])
    assert vals["4"] == ["250,893", "244,711"] and km1._confirm("4", labels["4"]) == "rwa"


def _facts(rows):
    import pandas as pd
    return pd.DataFrame([dict(entity_id="x", reference_date=d, metric=m, value=v, currency="GBP", source=src,
                              method=meth, document=doc) for d, m, v, src, meth, doc in rows])


def test_amounts_a_thousand_times_the_banks_own_record_are_rescaled():
    from bankcredit.adapters.pillar3 import check_scale
    res = km1.Result(values={"cet1_capital": 124259.0, "rwa": 693154.0, "cet1_ratio": 17.93}, currency="GBP",
                     reference_date=date(2025, 12, 31), history={"2024-12-31": {"rwa": 601928.0}})
    check_scale(res, _facts([("2024-12-31", "rwa", 601.9, "pillar3", "pdf_manual", "a")]), {})
    assert round(res.values["rwa"], 3) == 693.154 and round(res.history["2024-12-31"]["rwa"], 3) == 601.928
    # the rules' own baseline, which may share the slip, scales down but never up
    ok = km1.Result(values={"rwa": 693.0}, currency="GBP", reference_date=date(2026, 12, 31))
    check_scale(ok, _facts([]), {"reference_date": "2025-12-31", "values": {"rwa": 693154.0}, "method": "pdf_rules"})
    assert ok.values["rwa"] == 693.0
    slip = km1.Result(values={"rwa": 701000.0}, currency="GBP", reference_date=date(2026, 12, 31))
    check_scale(slip, _facts([]), {"reference_date": "2025-12-31", "values": {"rwa": 693.0}, "method": "pdf_rules"})
    assert slip.values["rwa"] == 701.0


def test_figures_that_repeat_another_period_are_flagged():
    from bankcredit.adapters.pillar3 import check_repeats
    other = _facts([("2025-03-31", m, v, "pillar3", "pdf_rules", "q1") for m, v in
                    (("cet1_capital", 35122.0), ("rwa", 253596.0), ("tier1_capital", 42629.0), ("leverage_exposure", 909072.0))])
    res = km1.Result(values={"cet1_capital": 35122.0, "rwa": 253596.0, "tier1_capital": 42629.0, "cet1_ratio": 13.8},
                     reference_date=date(2025, 6, 30))
    check_repeats(res, other)
    assert any(s == "error" and "2025-03-31" in m for s, m in res.checks)
    # Metro: only the leverage and liquidity block repeats the half year; those rows go, the rest stay
    h1 = _facts([("2025-06-30", "leverage_exposure", 13560.0, "pillar3", "pdf_rules", "h1"),
                 ("2025-06-30", "leverage_ratio", 7.9, "pillar3", "pdf_rules", "h1"),
                 ("2025-06-30", "lcr", 427.0, "pillar3", "pdf_rules", "h1"),
                 ("2025-06-30", "cet1_capital", 826.0, "pillar3", "pdf_rules", "h1")])
    fy = km1.Result(values={"cet1_capital": 808.0, "rwa": 6442.0, "leverage_exposure": 13560.0, "leverage_ratio": 7.9,
                            "lcr": 427.0, "nsfr": 150.0}, reference_date=date(2025, 12, 31))
    check_repeats(fy, h1)
    assert set(fy.values) == {"cet1_capital", "rwa", "nsfr"} and not any(s == "error" for s, _ in fy.checks)


def test_tier1_above_cet1_without_any_at1_goes_to_review():
    from bankcredit.adapters.pillar3 import check_tier1
    near = _facts([("2025-12-31", "cet1_capital", 808.0, "pillar3", "pdf_rules", "fy"),
                   ("2025-12-31", "tier1_capital", 808.0, "pillar3", "pdf_rules", "fy")])
    res = km1.Result(values={"cet1_capital": 867.0, "tier1_capital": 1109.0}, reference_date=date(2026, 6, 30))
    check_tier1(res, near)
    assert any(s == "error" and "AT1" in m for s, m in res.checks)
    at1 = _facts([("2025-12-31", "cet1_capital", 808.0, "pillar3", "pdf_rules", "fy"),
                  ("2025-12-31", "tier1_capital", 1050.0, "pillar3", "pdf_rules", "fy")])
    res = km1.Result(values={"cet1_capital": 867.0, "tier1_capital": 1109.0}, reference_date=date(2026, 6, 30))
    check_tier1(res, at1)
    assert not res.checks


def test_a_year_digit_on_the_next_line_is_joined(tmp_path):
    """Standard Chartered's header reads "31.03.2" over "3": unread, the document took the file name's date."""
    text = KM1_TEXT.replace("31 Dec 25 30 Sep 25 30 Jun 25", "31.03.2\n3\n31.12.2 2\n30.09.2 2")
    res = km1.extract(make_pdf(tmp_path, text))
    assert res.period_dates[:2] == [date(2023, 3, 31), date(2022, 12, 31)]


def test_a_document_no_locator_claims_is_not_read_with_the_first_one():
    """Citibank Europe's KM1 filed under Citigroup went through Citigroup's LCR extractor because the
    first locator was taken whatever the URL. A UK bank's NSM copy, which no listing pattern matches,
    is still read with its KM1 locator."""
    from bankcredit.adapters.pillar3 import Pillar3Adapter as P
    from bankcredit.adapters.pillar3_locators import LOCATORS
    cep = "https://www.citigroup.com/rcs/citigpa/storage/public/cep-pillar-3-disclosures-q2-2026.pdf"
    assert P._locator_for("citigroup", cep) == {} and P._unclaimed("citigroup", {})
    nsm = "https://data.fca.org.uk/artefacts/NSM/Portal/NI-000126938/NI-000126938.pdf"
    assert P._locator_for("tsb", nsm) == next(l for l in LOCATORS if l["entity"] == "tsb")
    assert P._locator_for("standard-chartered", nsm).get("entity") == "standard-chartered"
    wf = "https://www.wellsfargo.com/assets/pdf/about/investor-relations/lcr-disclosures/2026-first-quarter-lcr-disclosure.pdf"
    assert P._locator_for("wells-fargo", wf)["template"] == "us_lcr"     # URL templates claim their documents too
    assert not P._unclaimed("no-such-bank", {})                          # no locators at all: read as KM1, as before
