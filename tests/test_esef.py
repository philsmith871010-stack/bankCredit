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


Y25 = "2025-01-01T00:00:00/2026-01-01T00:00:00"
Y24 = "2024-01-01T00:00:00/2025-01-01T00:00:00"


def _doc(*facts):
    return {"facts": {f"f{i}": f for i, f in enumerate(facts)}}


def _year(*extra):
    """A minimal full year: balances at both ends and profit, plus whatever the test adds."""
    return [_fact("ifrs-full:Assets", "2026-01-01T00:00:00", 100e9), _fact("ifrs-full:Assets", "2025-01-01T00:00:00", 100e9),
            _fact("ifrs-full:ProfitLoss", Y25, 1e9)] + list(extra)


def test_the_preferred_concept_wins_whatever_order_the_filing_lists_them():
    by_end, _ = esef.read_filing(_doc(*_year(
        _fact("ifrs-full:ImpairmentLossImpairmentGainAndReversalOfImpairmentLossDeterminedInAccordanceWithIFRS9", Y25, 90e6),
        _fact("ifrs-full:ImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLossLoansAndAdvances", Y25, 80e6),
        _fact("ifrs-full:ImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLossLoansAndAdvances", Y25, 5e6, **{"ifrs-full:SegmentsAxis": "x"}),
        _fact("ifrs-full:RevenueAndOperatingIncome", Y25, 3e9),
    )))
    v = by_end[date(2025, 12, 31)]
    assert v["impairment"] == 80e6                     # loans before all IFRS 9 impairment, and the segment fact ignored
    assert v["income_total"] == 3e9


def test_owners_profit_over_owners_equity_and_whole_profit_over_assets():
    by_end, _ = esef.read_filing(_doc(*_year(
        _fact("ifrs-full:Equity", "2026-01-01T00:00:00", 12e9), _fact("ifrs-full:Equity", "2025-01-01T00:00:00", 12e9),
        _fact("ifrs-full:EquityAttributableToOwnersOfParent", "2026-01-01T00:00:00", 8e9),
        _fact("ifrs-full:EquityAttributableToOwnersOfParent", "2025-01-01T00:00:00", 8e9),
        _fact("ifrs-full:ProfitLossAttributableToOwnersOfParent", Y25, 0.8e9),
    )))
    y = esef.ratios(by_end)[date(2025, 12, 31)]
    assert y["roe"] == 10.0                            # 0.8 / 8, not 1.0 / 8
    assert y["roa"] == 1.0                             # minorities' profit is earned on these assets too
    # without the owners' figures the whole profit goes over the whole equity
    by_end, _ = esef.read_filing(_doc(*_year(_fact("ifrs-full:Equity", "2026-01-01T00:00:00", 10e9),
                                             _fact("ifrs-full:EquityAttributableToOwnersOfParent", "2026-01-01T00:00:00", 8e9))))
    assert esef.ratios(by_end)[date(2025, 12, 31)]["roe"] == 10.0


def test_cost_to_income_counts_a_release_and_never_uses_income_net_of_provisions():
    costs = [_fact("ifrs-full:OperatingExpense", Y25, 500e6), _fact("ifrs-full:ProfitLossBeforeTax", Y25, 600e6)]
    release = _fact("ifrs-full:ImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLossLoansAndAdvances", Y25, -100e6)
    by_end, _ = esef.read_filing(_doc(*_year(*costs, release)))
    assert esef.ratios(by_end)[date(2025, 12, 31)]["efficiency_ratio"] == 50.0      # 500 / (600 + 500 - 100)
    # no impairment line: the bank's own total income, not pre-tax plus costs
    by_end, _ = esef.read_filing(_doc(*_year(*costs, _fact("ifrs-full:RevenueAndOperatingIncome", Y25, 1250e6))))
    assert esef.ratios(by_end)[date(2025, 12, 31)]["efficiency_ratio"] == 40.0
    # neither: no ratio
    by_end, _ = esef.read_filing(_doc(*_year(*costs)))
    assert "efficiency_ratio" not in esef.ratios(by_end)[date(2025, 12, 31)]


def test_staff_costs_are_added_to_an_admin_line_too_small_to_hold_them():
    by_end, _ = esef.read_filing(_doc(*_year(
        _fact("ifrs-full:AdministrativeExpense", Y25, 1688e6), _fact("ifrs-full:EmployeeBenefitsExpense", Y25, 3335e6),
        _fact("ifrs-full:DepreciationAndAmortisationExpense", Y25, 560e6), _fact("ifrs-full:ProfitLossBeforeTax", Y25, 5400e6),
        _fact("ifrs-full:ImpairmentLossImpairmentGainAndReversalOfImpairmentLossDeterminedInAccordanceWithIFRS9", Y25, 478e6),
    )))                                                # Erste 2025
    y = esef.ratios(by_end)[date(2025, 12, 31)]
    assert round(y["efficiency_ratio"], 1) == round(5583 / (5400 + 5583 + 478) * 100, 1)


def test_net_interest_only_from_a_like_for_like_pair():
    split = [_fact("ifrs-full:InterestRevenueCalculatedUsingEffectiveInterestMethod", Y25, 7961e6),
             _fact("ifrs-full:RevenueFromInterest", Y25, 50767e6), _fact("ifrs-full:InterestExpense", Y25, 43543e6)]
    by_end, _ = esef.read_filing(_doc(*_year(*split)))
    assert "nim" not in esef.ratios(by_end)[date(2025, 12, 31)]                    # Nykredit: interest income in two parts
    by_end, _ = esef.read_filing(_doc(*_year(*split, _fact("nyrr:NetInterestIncome", Y25, 15185e6))))
    assert esef.ratios(by_end)[date(2025, 12, 31)]["nim"] == 15.185                # its own net interest line
    by_end, _ = esef.read_filing(_doc(*_year(_fact("ifrs-full:RevenueFromInterest", Y25, 2e9), _fact("ifrs-full:InterestExpense", Y25, 1.5e9))))
    assert esef.ratios(by_end)[date(2025, 12, 31)]["nim"] == 0.5
    by_end, _ = esef.read_filing(_doc(*_year(_fact("ifrs-full:RevenueFromInterest", Y25, 1e9), _fact("ifrs-full:InterestExpense", Y25, 1.5e9))))
    assert "nim" not in esef.ratios(by_end)[date(2025, 12, 31)]                    # a computed negative margin is a broken pair


def test_a_restated_first_of_january_is_not_a_year_end():
    by_end, _ = esef.read_filing(_doc(
        _fact("ifrs-full:Assets", "2025-01-01T00:00:00", 100e9), _fact("ifrs-full:Assets", "2025-01-02T00:00:00", 140e9),
        _fact("ifrs-full:Assets", "2026-01-01T00:00:00", 100e9), _fact("ifrs-full:ProfitLoss", Y25, 1e9),
        _fact("ifrs-full:ProfitLoss", Y24, 1e9),
    ))
    assert date(2025, 1, 1) not in by_end and by_end[date(2024, 12, 31)]["assets"] == 100e9
    by_end[date(2023, 12, 31)] = {"assets": 10e9}                                  # two years back: not an opening balance
    by_end.pop(date(2024, 12, 31))
    assert esef.ratios(by_end)[date(2025, 12, 31)]["roa"] == 1.0
