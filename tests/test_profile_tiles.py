"""The profile page's headline tiles say in words whether a figure is good or bad.

A ratio used to show a number and a sparkline and leave the reader to know that 12.6 percent is
tight for a UK bank and 24 percent is not. Each tile now judges the figure against the requirement
first - the bank's own, where it has been collected - and then against its peer group, and says
which, with the figures it judged against underneath.
"""
from __future__ import annotations

from bankcredit.site import build, components as c


def pts(*vals, src="pillar3", method="pdf_rules", conf=0.95):
    return [{"d": f"2026-{3 * i + 3:02d}-30", "v": v, "src": src, "method": method, "conf": conf, "doc": "x", "page": 5}
            for i, v in enumerate(vals)]


PEERS = {"cet1_ratio": {"p25": 13.5, "p50": 13.8, "p75": 14.2, "n": 15}}


def test_the_requirement_is_the_banks_own_where_it_is_published():
    assert build.requirement("cet1_ratio", {"cet1_requirement": pts(11.2)}, "GB") == (11.2, "CET1 requirement")
    assert build.requirement("cet1_ratio", {"overall_capital_requirement": pts(15.9)}, "GB") == (4.5, "Pillar 1 minimum"), \
        "the overall requirement is a total-capital figure; a CET1 ratio judged against it reads as a breach"
    assert build.requirement("total_capital_ratio", {"overall_capital_requirement": pts(15.9)}, "GB") == (15.9, "overall requirement")
    assert build.requirement("cet1_ratio", {}, "GB") == (4.5, "Pillar 1 minimum")
    assert build.requirement("leverage_ratio", {}, "GB") == (3.25, "UK minimum")
    assert build.requirement("leverage_ratio", {}, "DE") == (3.0, "Basel minimum")
    assert build.requirement("lcr", {}, "GB") == (100.0, "minimum")
    assert build.requirement("rwa", {}, "GB") == (None, ""), "a currency amount has no floor"


def test_the_verdict_is_the_requirement_first_then_the_peers():
    assert build.ratio_verdict(12.6, PEERS["cet1_ratio"], 15.9, "overall requirement") == ("bad", "Below the 15.9% overall requirement")
    assert build.ratio_verdict(14.5, PEERS["cet1_ratio"], 11.2) == ("good", "Top quarter of peers")
    assert build.ratio_verdict(14.0, PEERS["cet1_ratio"], 11.2) == ("good", "Above peer median")
    assert build.ratio_verdict(13.6, PEERS["cet1_ratio"], 11.2) == ("warn", "Below peer median")
    assert build.ratio_verdict(13.0, PEERS["cet1_ratio"], 11.2) == ("warn", "Bottom quarter of peers")
    assert build.ratio_verdict(13.0, None, 11.2, "minimum") == ("good", "Above the 11.2% minimum")
    assert build.ratio_verdict(None, PEERS["cet1_ratio"], 11.2) == ("na", "Not published")


def test_a_ratio_tile_carries_the_verdict_the_headroom_and_the_peers():
    series = {"cet1_ratio": pts(13.9, 14.0), "cet1_requirement": pts(11.2)}
    html = build.tile("cet1_ratio", "CET1 ratio", "%", 1, series, PEERS, "GB")
    assert 'class="tile-vd good"' in html and "Above peer median" in html
    assert "+2.8 over the 11.2% CET1 requirement" in html
    assert "median 13.8%" in html and "13.5–14.2%" in html and "15 names" in html
    assert "vs Mar 26" in html, "the move names the period it is against"


def test_a_currency_tile_keeps_to_the_value_and_the_move():
    html = build.tile("rwa", "Risk-weighted assets", "m", 0, {"rwa": pts(230000, 231500)}, PEERS, "GB")
    assert "tile-vd" not in html and "Peers:" not in html
    assert "231.5" in html and "bn" in html


def test_the_sparkline_draws_the_requirement_only_when_it_is_near():
    near = c.spark([13.9, 14.0, 13.7, 14.1], req=12.5)
    far = c.spark([13.9, 14.0, 13.7, 14.1], req=4.5)
    assert "stroke-dasharray" in near, "a requirement one point below the data is worth drawing"
    assert "stroke-dasharray" not in far, "one nine points below flattens the line to say nothing"
