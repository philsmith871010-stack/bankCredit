"""The results-release reader: key figures out of an announcement's own table."""
from datetime import date

from bankcredit.adapters import nsm_release as N

RELEASE = """
<p>OP Corporate Bank plc's CET1 ratio remained at 13.9% (14.1).</p>
<table>
 <tr><td>&euro; million</td><td>Q1/2025</td><td>Q1/2024</td><td>Change, %</td><td>Q1-4/2024</td></tr>
 <tr><td>Earnings before tax</td><td>184</td><td>142</td><td>29.6</td><td>566</td></tr>
 <tr><td>Cost/income ratio, %</td><td>34.1</td><td>36.5</td><td>-2.3*</td><td>38.6</td></tr>
 <tr><td>CET1 ratio, %</td><td>13.9</td><td>13.3</td><td>0.6*</td><td>14.1</td></tr>
 <tr><td>Ratio of non-performing exposures to exposures, %</td><td>1.6</td><td>2.2</td><td>-0.6*</td><td>1.8</td></tr>
 <tr><td>Ratio of impairment loss on receivables to loan and guarantee portfolio, %</td><td>0.02</td><td>0.16</td><td>-0.14*</td><td>0.00</td></tr>
</table>
"""


def test_key_figures_take_the_reporting_period_not_the_comparative():
    """The first numeric column is the period the headline names; every later column is a
    comparative and taking one would date this quarter's figure to last year's."""
    v = N.key_figures(RELEASE)
    assert v["cet1_ratio"] == 13.9
    assert v["efficiency_ratio"] == 34.1
    assert v["npl_ratio"] == 1.6
    assert v["cost_of_risk"] == 0.02
    assert "roe" not in v, "only labels the map names are read"


def test_period_end_reads_the_reporting_period_from_the_headline():
    assert N.period_end("OP Corporate Bank plc's Interim Report 1 January-31 March 2025") == date(2025, 3, 31)
    assert N.period_end("OP Corporate Bank plc's Half-year Financial Report 1 January-30 June 2025") == date(2025, 6, 30)
    assert N.period_end("OP Corporate Bank plc's Financial Statements Bulletin 1 January-31 December 2024") == date(2024, 12, 31)
    assert N.period_end("OP Corporate Bank plc's financial calendar for 2026") is None


def test_the_issuer_pattern_does_not_match_a_sibling_or_the_parent():
    """One LEI's filings carry the group's releases and its other subsidiaries'; a parent's
    figures must never stand for the subsidiary we are assessing."""
    import re
    pattern = N.ISSUERS["op-corporate-bank"]
    assert re.search(pattern, "OP Corporate Bank plc's Interim Report 1 January-31 March 2025")
    assert not re.search(pattern, "OP Financial Group's Financial Statements Bulletin 1 January-31 December 2022")
    assert not re.search(pattern, "OP Mortgage Bank's Half-year Financial Report 1 January-30 June 2025")
    assert not re.search(pattern, "OP Pohjola's Interim Report for 1 January-30 September 2025")


def test_implausible_figures_are_dropped():
    from bankcredit.models import Fact
    adapter = N.NsmReleaseAdapter.__new__(N.NsmReleaseAdapter)
    def f(metric, value):
        return Fact(entity_id="x", reference_date=date(2025, 3, 31), metric=metric, value=value)
    kept = {r.metric for r in adapter.validate([f("cet1_ratio", 13.9), f("cet1_ratio", 139.0),
                                                f("lcr", 430.0), f("lcr", 4.3),
                                                f("npl_ratio", 1.6), f("npl_ratio", 96.0)])}
    assert kept == {"cet1_ratio", "lcr", "npl_ratio"}
    assert len(adapter.validate([f("cet1_ratio", 13.9), f("cet1_ratio", 139.0)])) == 1
