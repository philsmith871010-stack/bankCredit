from datetime import date

from bankcredit.adapters import te


def test_labels_map_to_metrics_across_wording():
    assert te.metric_for("Common Equity Tier 1 (CET1) capital - transitional period") == "cet1_capital"
    assert te.metric_for("Tier 1 capital  - transitional period") == "tier1_capital"
    assert te.metric_for("Common Equity Tier 1 (as a percentage of risk exposure amount) - transitional definition") == "cet1_ratio"
    assert te.metric_for("Leverage ratio - using a transitional definition of Tier 1 capital") == "leverage_ratio"
    assert te.metric_for("Total risk exposure amount as if IFRS 9 or analogous ECLs transitional arrangements had not been applied") is None
    assert te.metric_for("Common Equity Tier 1 (CET1) capital - transitional period -  as if IFRS 9") is None


def test_period_codes():
    assert te.period_date(202406) == date(2024, 6, 30)
    assert te.period_date("201812") == date(2018, 12, 31)
    assert te.period_date(202405) is None
