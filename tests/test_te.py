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


def test_the_last_exercise_is_read_first():
    assert next(iter(te.FILES)) == "TE2025" and "883401/tr_oth.csv" in te.FILES["TE2025"]


def test_every_amount_is_in_euros_and_no_ratio_has_a_currency(tmp_path):
    lei = "F3JS33DEI6XQ4ZBPTN86"
    head = '"LEI_Code","NSA","Period","Item","Label","ASSETS_FV","ASSETS_Stages","Exposure","Financial_instruments","Amount","Fin_end_year","n_quarters","Row","Column","Sheet"\n'
    rows = [("Common Equity Tier 1 (CET1) capital - transitional period", 0, "15000", "Key metrics"),
            ("Common Equity Tier 1 (as a percentage of risk exposure amount) - transitional definition", 0, "0.176", "Key metrics"),
            ("Total assets", 0, "325811.5", "Assets"),
            ("Gross carrying amount: financial assets at amortised cost, loans and advances", 0, "200000", "Assets"),
            ("Gross carrying amount: financial assets at amortised cost, loans and advances", 3, "700", "Assets")]
    body = "".join(f'"{lei}","SE","202506","1","{lab}","0","{st}","0","0","{amt}","0","2","1","1","{sh}"\n' for lab, st, amt, sh in rows)
    path = tmp_path / "tr_oth.csv"
    path.write_text(head + body)
    ad = te.TransparencyAdapter.__new__(te.TransparencyAdapter)
    from bankcredit.models import Entity
    ad.entities = [Entity(id="seb", name="SEB", short_name="SEB", country="SE", type="bank", region="eu", group="", lei=lei, tickers="", peer_group="eu", active=True)]
    facts = {f.metric: f for f in ad.parse("TE2025", str(path))}
    assert set(facts) == {"cet1_capital", "cet1_ratio", "total_assets", "npl_ratio"}
    assert all(f.currency == "EUR" and f.unit == "ccy_m" for m, f in facts.items() if m in ("cet1_capital", "total_assets"))
    assert facts["cet1_ratio"].currency == "" and facts["npl_ratio"].currency == "" and facts["npl_ratio"].value == 0.35
    assert all(f.reference_date == date(2025, 6, 30) and f.source == "eba_te" for f in facts.values())
