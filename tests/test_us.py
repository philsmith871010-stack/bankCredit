import fitz

from bankcredit.extract import us


def _pdf(tmp_path, lines):
    doc = fitz.open()
    page = doc.new_page()
    y = 60
    for l in lines:
        page.insert_text((50, y), l, fontsize=10)
        y += 16
    path = tmp_path / "gs.pdf"
    doc.save(str(path))
    return str(path)


def test_requirement_blocks_are_not_read_as_actual_ratios(tmp_path):
    # Goldman's Table 1: minimums, then total requirements, then the actual ratios, same labels each time
    path = _pdf(tmp_path, [
        "Basel III Pillar 3 Disclosures as of June 30, 2026",
        "Table 1: Regulatory Capital Ratios",
        "Minimum capital ratios",
        "CET1 capital ratio 4.5%",
        "Tier 1 capital ratio 6.0%",
        "Total capital ratio 8.0%",
        "Total capital requirements including buffers",
        "CET1 capital ratio 10.4%",
        "Tier 1 capital ratio 11.9%",
        "Total capital ratio 13.9%",
        "Regulatory capital ratios as of June 30, 2026",
        "CET1 capital ratio 13.6%",
        "Tier 1 capital ratio 15.2%",
        "Total capital ratio 16.8%",
        "Supplementary leverage ratio 5.5%",
    ])
    res = us.extract_capital(path)
    assert res.values["cet1_ratio"] == 13.6
    assert res.values["tier1_ratio"] == 15.2 and res.values["total_capital_ratio"] == 16.8
    assert res.values["leverage_ratio"] == 5.5


# ---- one approach column per report --------------------------------------------------------------
def test_every_row_comes_from_the_standardized_column(tmp_path):
    """Wells Fargo heads Advanced then Standardized. Each row once took its own lower figure, so the
    ratios came from the Standardized column and the RWAs from the Advanced one (Tier 1 12.68% beside
    capital over RWA of 14.09%)."""
    path = _pdf(tmp_path, [
        "Table 1: Capital Components and Ratios Under Basel III",
        "June 30, 2026",
        "Advanced",
        "Approach",
        "Standardized",
        "Approach",
        "Common Equity Tier 1 Capital", "$", "137,698", "137,698",
        "Tier 1 Capital", "152,737", "152,737",
        "Risk-Weighted Assets", "1,140,242", "1,342,325",
        "Common Equity Tier 1 Capital Ratio 12.08 % 10.26 *",
        "Tier 1 Capital Ratio 13.40 11.38 *",
        "Total Capital Ratio 15.28 13.72 *",
    ])
    v = us.extract_capital(path).values
    assert (v["cet1_ratio"], v["tier1_ratio"], v["total_capital_ratio"]) == (10.26, 11.38, 13.72)
    assert v["rwa"] == 1342325
    assert abs(v["tier1_capital"] / v["rwa"] * 100 - v["tier1_ratio"]) < 0.05


def test_the_standardized_column_is_read_even_where_advanced_is_lower(tmp_path):
    """Citi's Advanced CET1 (11.90%) is the lower, but Citi's binding CET1 is the Standardized 13.48%,
    and the Standardized one is the ratio a US requirement is set against."""
    path = _pdf(tmp_path, [
        "Table 2: Risk-Based Capital Ratios",
        "Required Capital Ratios",
        "June 30, 2025",
        "Advanced",
        "Approaches(1)",
        "Standardized",
        "Approach(2)",
        "Advanced",
        "Approaches",
        "Standardized",
        "Approach",
        "CET1 Capital(3)", "$", "158,943", "$", "158,943",
        "Tier 1 Capital(3)", "176,619", "176,619",
        "Risk Weighted Assets(3)", "1,335,913", "1,178,756",
        "CET1 Capital Ratio(4) 10.5 % 12.1 % 11.90 % 13.48 %",
        "Tier 1 Capital Ratio(4) 12.0 13.6 13.22 14.98",
        "Total Capital Ratio(4) 14.0 15.6 15.28 18.06",
    ])
    v = us.extract_capital(path).values
    assert (v["cet1_ratio"], v["tier1_ratio"], v["total_capital_ratio"]) == (13.48, 14.98, 18.06)
    assert v["rwa"] == 1178756 and v["cet1_capital"] == 158943


def test_without_headings_the_lower_cet1_column_is_read_for_every_row(tmp_path):
    path = _pdf(tmp_path, [
        "Capital ratios as of June 30, 2026",
        "Common equity tier 1 capital ratio 12.5% 11.0%",
        "Tier 1 capital ratio 13.0% 13.5%",
        "Total capital ratio 15.0% 16.0%",
    ])
    v = us.extract_capital(path).values
    assert (v["cet1_ratio"], v["tier1_ratio"], v["total_capital_ratio"]) == (11.0, 13.5, 16.0)


def test_goldmans_standardized_ratios_come_from_its_statement_not_its_advanced_table(tmp_path):
    """Goldman's Table 2 is on the Advanced approach, in columns of this quarter and the last; the
    binding Standardized ratios are stated in prose. CET1 15.1% to 13.3% was the Advanced series."""
    path = _pdf(tmp_path, [
        "Basel III Pillar 3 Disclosures as of March 31, 2026",
        "As of March 2026, the firm's Standardized ratios were 12.5% for CET1 capital, 14.1% for Tier 1",
        "capital and 15.9% for Total capital.",
        "Regulatory capital ratios are required to be calculated under the Advanced Capital Rules.",
        "Table 2: Risk-Based Capital and Leverage Ratios",
        "As of",
        "$ in millions",
        "March",
        "2026",
        "December",
        "2025",
        "CET1 capital $ 101,800 $ 104,297",
        "RWAs $ 763,768 $ 691,470",
        "CET1 capital ratio 13.3% 15.1%",
        "Tier 1 capital ratio 15.1% 17.2%",
        "Total capital ratio 16.6% 18.6%",
        "Tier 1 leverage ratio", "5.9%", "6.6%",
    ])
    v = us.extract_capital(path).values
    assert (v["cet1_ratio"], v["tier1_ratio"], v["total_capital_ratio"]) == (12.5, 14.1, 15.9)
    assert "rwa" not in v, "its RWAs are the Advanced ones"
    assert v["tier1_leverage"] == 5.9, "the second column is last quarter, not an actual beside a requirement"


def test_bnys_entity_matrix_gives_the_holding_companys_standardized_figures(tmp_path):
    """BNY's table has one row per legal entity and SA | AA under each of RWA, CET1, Tier 1, Total."""
    lines = ["Basel III RWA and risk-based capital ratios -", "Standardized and Advanced Approaches", "June 30, 2026",
             "RWA", "CET1", "Tier 1", "Total Capital", "(dollar amounts in millions)"]
    lines += ["SA", "AA"] * 4
    lines += ["BHC:", "The Bank of New York Mellon Corporation", "$ 196,108 $ 174,050",
              "11.0%", "12.4%", "13.4%", "15.1%", "14.2%", "15.8%",
              "Depository institution subsidiaries:", "The Bank of New York Mellon", "154,537 139,283",
              "14.6", "16.2", "14.6", "16.2", "14.8", "16.2"]
    v = us.extract_capital(_pdf(tmp_path, lines)).values
    assert (v["rwa"], v["cet1_ratio"], v["tier1_ratio"], v["total_capital_ratio"]) == (196108, 11.0, 13.4, 14.2)


def test_an_advanced_only_table_is_flagged(tmp_path):
    """JPMorgan's Pillar 3 tables are Advanced only; read as if binding they overstate its ratios."""
    path = _pdf(tmp_path, [
        "Regulatory capital metrics as of June 30, 2026",
        "The following tables present the Advanced risk-based",
        "and leverage-based capital metrics for JPMorgan Chase & Co.",
        "CET1 capital ratio 14.2 %",
        "Tier 1 capital ratio 15.2",
        "Total capital ratio 16.3",
        "Tier 1 leverage ratio 6.6 %",
    ])
    res = us.extract_capital(path)
    assert res.values["cet1_ratio"] == 14.2
    assert any("Advanced approach only" in m for s, m in res.checks if s == "warn")
