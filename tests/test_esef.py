from datetime import date

from bankcredit.adapters import esef


def _fact(concept, period, value, **dims):
    d = {"concept": concept, "entity": "scheme:LEI", "period": period, "unit": "iso4217:GBP"}
    d.update(dims)
    return {"value": str(value), "decimals": -6, "dimensions": d}


def test_ratios_from_a_filing_with_its_comparative():
    doc = {"facts": {
        "f1": _fact("ifrs-full:Assets", "2026-01-01T00:00:00", 60e9),
        "f2": _fact("ifrs-full:Assets", "2025-01-01T00:00:00", 56e9),
        "f3": _fact("ifrs-full:Equity", "2026-01-01T00:00:00", 3.1e9),
        "f4": _fact("ifrs-full:Equity", "2025-01-01T00:00:00", 2.9e9),
        "f5": _fact("ifrs-full:ProfitLoss", "2025-01-01T00:00:00/2026-01-01T00:00:00", 300e6),
        "f6": _fact("ifrs-full:ProfitLoss", "2025-01-01T00:00:00/2026-01-01T00:00:00", 290e6, **{"ifrs-full:ComponentsOfEquityAxis": "x"}),
        "f7": _fact("ifrs-full:InterestRevenueExpense", "2025-01-01T00:00:00/2026-01-01T00:00:00", 900e6),
        "f8": _fact("ifrs-full:AdministrativeExpense", "2025-01-01T00:00:00/2026-01-01T00:00:00", -400e6),
        "f9": _fact("ifrs-full:AmortisationIntangibleAssetsOtherThanGoodwill", "2025-01-01T00:00:00/2026-01-01T00:00:00", 20e6),
        "f10": _fact("ifrs-full:FeeAndCommissionIncome", "2025-01-01T00:00:00/2026-01-01T00:00:00", 50e6),
        "f11": _fact("ifrs-full:LoansAndAdvancesToCustomers", "2026-01-01T00:00:00", 50e9),
        "f12": _fact("ifrs-full:LoansAndAdvancesToCustomers", "2025-01-01T00:00:00", 48e9),
        "f13": _fact("ifrs-full:ImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLossLoansAndAdvances", "2025-01-01T00:00:00/2026-01-01T00:00:00", -49e6),
        "f14": _fact("ifrs-full:DepositsFromCustomers", "2026-01-01T00:00:00", 45e9),
        "f15": _fact("ifrs-full:ProfitLoss", "2025-06-01T00:00:00/2026-01-01T00:00:00", 1e6),      # a part year: ignored
        "f16": _fact("ifrs-full:ProfitLossBeforeTax", "2025-01-01T00:00:00/2026-01-01T00:00:00", 581e6),   # income = 581 + 420 + 49 = 1050
    }}
    by_end, ccy = esef.read_filing(doc)
    assert ccy == "GBP" and by_end[date(2025, 12, 31)]["profit"] == 300e6
    r = esef.ratios(by_end)
    y = r[date(2025, 12, 31)]
    assert y["total_assets"] == 60000 and y["deposits"] == 45000
    assert y["roe"] == 10.0                                  # 300 / avg(3100, 2900)
    assert round(y["roa"], 3) == round(300 / 58000 * 100, 3)
    assert round(y["nim"], 3) == round(900 / 58000 * 100, 3)
    assert round(y["efficiency_ratio"], 2) == round(420 / 1050 * 100, 2)
    assert y["cost_of_risk"] == 0.1
    assert date(2024, 12, 31) in r and "roe" not in r[date(2024, 12, 31)]      # opening balances only, no profit
