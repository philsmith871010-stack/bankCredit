"""Counterparty score, version two. A rating anchor with published ratio pillars; market overlay bounded.

The composite agency rating (median long-term grade across the agencies that rate the bank) is
40 percent of the public score. The other 60 percent comes from regulatory ratios, each turned
into a 0..100 sub-score by piecewise-linear interpolation against absolute thresholds (chosen from
Basel minimums and typical ranges), averaged within pillars and weighted. Missing ratio metrics do
not score zero: the ratio weight is re-scaled over what is available and the coverage fraction is
reported so the site can show "insufficient data" honestly. An unrated bank takes a below-neutral
rating sub-score and its final score is capped below band A: the absence of any agency assessment
is itself information. Likewise strong ratios lift a bank at most one band above its rating: the
BBB range stops below A and sub-investment grade below B. Bands: A 80+, B 65+, C 50+, D 35+, E below.
"""
from __future__ import annotations

from dataclasses import dataclass, field

VERSION = 2
RATING_WEIGHT = 40
# composite grade (1 = AAA ... 17 = CCC) -> sub-score
RATING_SCORE = {1: 100, 2: 95, 3: 91, 4: 87, 5: 81, 6: 75, 7: 69, 8: 60, 9: 52, 10: 44, 11: 33, 12: 25, 13: 17, 14: 10, 15: 5, 16: 2, 17: 0}
UNRATED_SCORE = 40.0          # below neutral: no agency has looked
UNRATED_CAP = 74.9            # an unrated bank cannot reach band A
# strong ratios cannot lift a bank more than one band above what its rating says:
# BBB range (grades 8-10) stops below A; sub-investment grade (11+) stops below B
GRADE_CAPS = [(7, 100.0), (10, 74.9), (17, 64.9)]

# (metric, thresholds as [(value, score), ...] ascending in value)
PILLARS = {
    "capital": (25, {
        "cet1_ratio": [(4.5, 0), (8.0, 30), (11.0, 55), (14.0, 80), (18.0, 95), (25.0, 100)],
        "leverage_ratio": [(3.0, 0), (4.0, 40), (5.0, 70), (6.5, 90), (9.0, 100)],
        "total_capital_ratio": [(8.0, 0), (12.0, 40), (16.0, 70), (20.0, 90), (26.0, 100)],
    }),
    "liquidity": (15, {
        "lcr": [(100, 0), (120, 40), (140, 65), (170, 85), (220, 100)],
        "nsfr": [(100, 0), (110, 40), (125, 70), (140, 90), (160, 100)],
    }),
    "asset_quality": (5, {
        "npl_ratio": [(0.2, 100), (1.0, 85), (2.0, 65), (4.0, 40), (8.0, 10), (15.0, 0)],
    }),
    "profitability": (5, {
        "roe": [(-5.0, 0), (2.0, 30), (6.0, 55), (10.0, 75), (15.0, 90), (25.0, 100)],
        "roa": [(-0.5, 0), (0.2, 30), (0.6, 55), (1.0, 75), (1.5, 90), (2.5, 100)],
        "efficiency_ratio": [(40.0, 100), (55.0, 80), (65.0, 60), (75.0, 35), (90.0, 10), (110.0, 0)],
    }),
    "stability": (10, {
        # headroom of CET1 over overall requirement, in percentage points
        "cet1_headroom": [(0.0, 0), (1.5, 35), (3.0, 60), (5.0, 80), (8.0, 100)],
    }),
}
BANDS = [(80, "A"), (65, "B"), (50, "C"), (35, "D"), (0, "E")]
OVERLAY_CAP = 10.0


def interp(value: float, points: list[tuple[float, float]]) -> float:
    pts = sorted(points)
    if value <= pts[0][0]:
        return pts[0][1]
    if value >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= value <= x1:
            return y0 + (y1 - y0) * (value - x0) / (x1 - x0)
    return pts[-1][1]


@dataclass
class ScoreResult:
    public_score: float | None
    coverage: float
    pillars: dict = field(default_factory=dict)      # pillar -> (score or None, weight used)
    overlay: float = 0.0
    final_score: float | None = None
    band: str = ""
    inputs: dict = field(default_factory=dict)
    unrated: bool = False


def band_for(score: float | None) -> str:
    if score is None:
        return ""
    for floor, b in BANDS:
        if score >= floor:
            return b
    return "E"


# Substitutes scored on their own scale when the canonical metric is absent:
# US banks report Tier 1 leverage on average assets (4% minimum, 5% well capitalised), not Basel leverage.
ALTERNATES = {"leverage_ratio": ("tier1_leverage", [(4.0, 0), (5.0, 40), (6.5, 70), (8.0, 90), (10.0, 100)])}


def rating_score(grade: float | None) -> float:
    """Sub-score for a composite grade on the AAA..CCC scale (1..17); below neutral when unrated."""
    if grade is None:
        return UNRATED_SCORE
    return float(RATING_SCORE[max(1, min(17, int(grade + 0.5)))])


def score_cap(grade: float | None) -> float:
    """Highest final score the composite grade allows (UNRATED_CAP when no agency rates the bank)."""
    if grade is None:
        return UNRATED_CAP
    g = int(grade + 0.5)
    for upper, cap in GRADE_CAPS:
        if g <= upper:
            return cap
    return GRADE_CAPS[-1][1]


def compute(latest: dict[str, float], overlay: float = 0.0, rating_grade: float | None = None) -> ScoreResult:
    """latest: metric code -> latest value. overlay: signed adjustment from the private layer, capped.
    rating_grade: composite agency grade, 1 (AAA) to 17 (CCC), or None when no agency rates the bank."""
    latest = dict(latest)
    if "cet1_ratio" in latest and "overall_capital_requirement" in latest and "cet1_headroom" not in latest:
        # approximate CET1 headroom as CET1 ratio minus overall requirement (KM1 row) when a CET1-specific requirement is absent
        latest["cet1_headroom"] = latest["cet1_ratio"] - latest["overall_capital_requirement"]
    if "cet1_ratio" in latest and "cet1_requirement" in latest:
        latest["cet1_headroom"] = latest["cet1_ratio"] - latest["cet1_requirement"]
    pillars, weighted, weight_used, inputs = {}, 0.0, 0.0, {}
    for name, (weight, metrics) in PILLARS.items():
        subs = []
        for m, pts in metrics.items():
            if m in latest and latest[m] is not None:
                s = interp(float(latest[m]), pts)
                subs.append(s)
                inputs[m] = (latest[m], round(s))
            elif m in ALTERNATES and latest.get(ALTERNATES[m][0]) is not None:
                alt, alt_pts = ALTERNATES[m]
                s = interp(float(latest[alt]), alt_pts)
                subs.append(s)
                inputs[alt] = (latest[alt], round(s))
        if subs:
            p = sum(subs) / len(subs)
            pillars[name] = (round(p, 1), weight)
            weighted += p * weight
            weight_used += weight
        else:
            pillars[name] = (None, 0)
    total_weight = sum(w for w, _ in PILLARS.values())
    coverage = weight_used / total_weight
    rs = rating_score(rating_grade)
    pillars["rating"] = (round(rs, 1), RATING_WEIGHT)
    if weight_used == 0:
        return ScoreResult(None, 0.0, pillars, 0.0, None, "", inputs, unrated=rating_grade is None)
    ratios = weighted / weight_used
    public = (ratios * total_weight + rs * RATING_WEIGHT) / (total_weight + RATING_WEIGHT)
    ov = max(-OVERLAY_CAP, min(OVERLAY_CAP, overlay))
    final = max(0.0, min(100.0, public + ov))
    cap = score_cap(rating_grade)
    public, final = min(public, cap), min(final, cap)
    band = band_for(final) if coverage >= 0.5 else "?"
    return ScoreResult(round(public, 1), round(coverage, 2), pillars, ov, round(final, 1), band, inputs, unrated=rating_grade is None)
